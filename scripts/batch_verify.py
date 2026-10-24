#!/usr/bin/env python3
"""Resume deterministic checks for saved candidates; no editing, approval or deletion."""
import argparse
from contextlib import ExitStack
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from check_layout import check
from compare_source import (ENGINE, compare, files_for, production_hash,
                            require_comparison, require_delivery)
from verify_outputs import image_size, sha256_file


def check_clean_base(entry):
    ref = entry.get('production', {}).get('clean_base')
    if ref is None:
        return
    task, root = Path(ref['task']), Path(ref['output_dir'])
    if not task.is_absolute() or not root.is_absolute():
        raise ValueError('clean-base task and output_dir must be absolute')
    matches = [e for e in json.loads(task.read_text()) if e['png'] == ref['png']]
    if len(matches) != 1:
        raise ValueError('clean base not uniquely identified')
    base = matches[0]
    if base['source_sha256'] != entry['source_sha256'] or base['protected'] != entry['protected']:
        raise ValueError('clean base has a different source or protection policy')
    report = require_delivery(base, root)
    if report['file_hashes']['pcraft'] != ref['pcraft_sha256']:
        raise ValueError('clean base changed; regenerate dependent language variants')


def check_item(entry, root, engine):
    files_for(entry, root)
    if 'production' in entry and entry.get('candidate_plan_sha256') != production_hash(entry):
        raise ValueError('candidate does not match current production plan; edit before verification')
    check_clean_base(entry)
    if entry.get('layout', {}).get('groups'):
        if list(image_size(Path(entry['source']))) != entry['layout']['canvas']:
            raise ValueError('layout canvas differs from source')
        snapshot_path = Path(entry['type_snapshot'])
        if not snapshot_path.is_absolute():
            raise ValueError('type_snapshot must be absolute')
        snapshot = json.loads(snapshot_path.read_text())
        if snapshot['pcraft_sha256'] != sha256_file(root / entry['pcraft']):
            raise ValueError('stale layout snapshot; collect type.info again')
        problems = check(entry, snapshot['types'])
        if problems:
            raise ValueError('\n'.join(problems))
    report_path = Path(entry['comparison']['report'])
    if report_path.exists():
        require_comparison(entry, root)
        pixel_status = 'reused'
    else:
        report = compare(entry, root, engine())
        if report['status'] != 'pass':
            raise ValueError(f"pixel check failed: {report['raster']['unexpected_pixels']} unexpected pixels; see {report_path}")
        pixel_status = 'computed'
    try:
        require_delivery(entry, root)
        return {'status': 'ready', 'pixel_check': pixel_status}
    except (ValueError, KeyError, OSError) as error:
        return {'status': 'needs_review', 'pixel_check': pixel_status, 'reason': str(error)}


def run_batch(entries, root, engine):
    if not isinstance(entries, list) or not entries:
        raise ValueError('expected a nonempty task list')
    names = [e['png'] for e in entries]
    if len(names) != len(set(names)):
        raise ValueError('duplicate candidate PNG names; use distinct language/version names')
    rows = []
    for entry in entries:
        start = time.monotonic()
        try:
            result = check_item(entry, root, engine)
        except Exception as error:
            result = {'status': 'failed', 'reason': str(error)}
        rows.append({'png': entry['png'], 'target_language': entry.get('target_language'),
                     **result, 'elapsed_seconds': round(time.monotonic() - start, 3)})
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('task', type=Path)
    parser.add_argument('output_dir', type=Path)
    parser.add_argument('--summary', required=True, type=Path, help='Fresh .json QA summary path')
    args = parser.parse_args()
    entries = json.loads(args.task.read_text())
    summary = args.summary.resolve()
    if summary.suffix != '.json' or summary.exists():
        raise SystemExit('use a fresh .json summary path')
    reserved = {args.task.resolve()}
    for entry in entries:
        reserved.add(Path(entry['comparison']['report']).resolve())
        for key in ('source', 'type_snapshot'):
            if entry.get(key): reserved.add(Path(entry[key]).resolve())
    if summary in reserved:
        raise SystemExit('summary path conflicts with task evidence')
    with ExitStack() as stack:
        compiled = None

        def engine():
            nonlocal compiled
            if compiled is None:
                temp = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix='photocraft-batch-')))
                binary = temp / 'compare-pixels'
                result = subprocess.run(['swiftc', '-module-cache-path', str(temp / 'modules'),
                                         str(ENGINE), '-o', str(binary)], capture_output=True, text=True)
                if result.returncode:
                    raise ValueError(f'comparison compiler failed: {result.stderr}')
                compiled = [str(binary)]
            return compiled

        rows = run_batch(entries, args.output_dir.resolve(strict=True), engine)
    summary.parent.mkdir(parents=True, exist_ok=True)
    with summary.open('x') as out:
        json.dump(rows, out, ensure_ascii=False, indent=2)
    counts = {status: sum(r['status'] == status for r in rows) for status in ('ready', 'needs_review', 'failed')}
    print(json.dumps({'counts': counts, 'details': str(summary)}, ensure_ascii=False))
    for row in rows:
        if row['status'] != 'ready':
            print(json.dumps({'png': row['png'], 'status': row['status'], 'reason': row.get('reason', '')[:500]}, ensure_ascii=False))
    if counts['failed'] or counts['needs_review']:
        sys.exit(1)


if __name__ == '__main__':
    main()
