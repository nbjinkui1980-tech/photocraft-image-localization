#!/usr/bin/env python3
"""Resume deterministic checks for saved candidates; no editing, approval or deletion."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sys
import time

from check_layout import check
from compare_source import (compare, files_for, production_hash,
                            require_comparison, require_delivery)
import swift_tool
from verify_outputs import image_size, sha256_file, verification_cache


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


def run_batch(entries, root, engine, jobs=1):
    """Check every item; independent items run on up to JOBS threads, rows keep task order."""
    if not isinstance(entries, list) or not entries:
        raise ValueError('expected a nonempty task list')
    names = [e['png'] for e in entries]
    if len(names) != len(set(names)):
        raise ValueError('duplicate candidate PNG names; use distinct language/version names')
    reports = [str(Path(e.get('comparison', {}).get('report', f'missing-{i}')).resolve()) for i, e in enumerate(entries)]
    if len(reports) != len(set(reports)):
        jobs = 1  # shared report paths would race on exclusive creation; keep the serial semantics

    def one(entry):
        start = time.monotonic()
        try:
            with verification_cache():
                result = check_item(entry, root, engine)
        except Exception as error:
            result = {'status': 'failed', 'reason': str(error)}
        return {'png': entry['png'], 'target_language': entry.get('target_language'),
                **result, 'elapsed_seconds': round(time.monotonic() - start, 3)}

    if jobs <= 1 or len(entries) == 1:
        return [one(entry) for entry in entries]
    # Work is dominated by the native comparison subprocess and hashing, both outside the GIL.
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        return list(pool.map(one, entries))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('task', type=Path)
    parser.add_argument('output_dir', type=Path)
    parser.add_argument('--summary', required=True, type=Path, help='Fresh .json QA summary path')
    parser.add_argument('--jobs', type=int, default=min(8, os.cpu_count() or 1),
                        help='Items checked in parallel (default: min(8, CPU count))')
    args = parser.parse_args()
    if args.jobs < 1:
        raise SystemExit('--jobs must be at least 1')
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
    # Compiled lazily (only when a fresh comparison is needed) and cached across runs.
    rows = run_batch(entries, args.output_dir.resolve(strict=True),
                     lambda: swift_tool.command('compare_pixels'), args.jobs)
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
