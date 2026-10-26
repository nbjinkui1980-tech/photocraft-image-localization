#!/usr/bin/env python3
"""Build the review pages for one candidate after compare_source.py has written its report.

Writes into a fresh directory:
  regions-NN.png  every editable (and optionally protected) region as source / candidate /
                  diff crops at exact 1:1 pixels, tiled to fit PAGE px so a vision model
                  sees them without downscaling;
  overview.png    source | candidate at the intended display width;
  review.json     the file hashes these pages were rendered from. Pass it to
                  `task_tool.py record-review --before` so approval binds to the same bytes.

Pages are review material only; they do not judge or approve anything.

usage: review_sheet.py TASK.json OUTPUT_DIR --png NAME --out-dir FRESH_DIR
       [--display-width 750] [--page 1568] [--context 16] [--include-protected]
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

import swift_tool
from compare_source import files_for, report_path
from verify_outputs import pair_hashes, sha256_file, verification_cache


def build(entry, root, out_dir, display_width=750, page=1568, context=16, include_protected=False, engine=None):
    with verification_cache():
        files = files_for(entry, root)
        current = pair_hashes(*files)
        path = report_path(entry, files)
        if not path.is_file():
            raise ValueError('no comparison report; run compare_source.py first')
        report = json.loads(path.read_text())
        if report.get('file_hashes') != current:
            raise ValueError('comparison report is stale for the current files; compare again with a fresh report')
        diff = Path(report['diff_image'])
        if report.get('diff_sha256') != sha256_file(diff):
            raise ValueError('comparison difference image missing or changed')
    out_dir = Path(out_dir)
    if out_dir.exists():
        raise ValueError('choose a fresh review directory; existing review material is never reused')
    # A fresh directory can never be the source/output directory, so pages never mix with deliverables.
    policy = report['policy']
    regions = [{'id': r['id'], 'kind': 'editable', 'rect': r['rect']} for r in policy['editable']]
    if include_protected:
        regions += [{'id': r['id'], 'kind': 'protected', 'rect': r['rect']} for r in policy['protected']]
    out_dir.mkdir(parents=True)
    config = out_dir / 'sheet-config.json'
    config.write_text(json.dumps({'source': str(files[0]), 'output': str(files[1]), 'diff': str(diff),
                                  'out_dir': str(out_dir), 'page_px': page, 'display_width': display_width,
                                  'context_px': context, 'regions': regions}))
    command = engine if engine is not None else swift_tool.command('review_sheet')
    run = subprocess.run([*command, str(config)], capture_output=True, text=True)
    config.unlink()
    if run.returncode:
        raise ValueError(f'review sheet rendering failed: {run.stderr.strip()}')
    rendered = json.loads(run.stdout)
    if pair_hashes(*files) != current:
        raise ValueError('files changed while rendering; regenerate the review pages')
    manifest = {'schema_version': 1, 'png': entry['png'], 'file_hashes': current,
                'report': str(path), 'report_sha256': sha256_file(path),
                'regions': [r['id'] for r in regions if r['kind'] == 'editable'],
                'pages': [p['file'] for p in rendered['pages']], 'overview': rendered['overview']}
    with (out_dir / 'review.json').open('x') as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('task', type=Path)
    parser.add_argument('output_dir', type=Path)
    parser.add_argument('--png', required=True)
    parser.add_argument('--out-dir', required=True, type=Path)
    parser.add_argument('--display-width', type=int, default=750)
    parser.add_argument('--page', type=int, default=1568)
    parser.add_argument('--context', type=int, default=16)
    parser.add_argument('--include-protected', action='store_true')
    args = parser.parse_args()
    try:
        entries = [e for e in json.loads(args.task.read_text()) if e['png'] == args.png]
        if len(entries) != 1:
            raise ValueError('expected one matching source/language entry')
        manifest = build(entries[0], args.output_dir.resolve(strict=True), args.out_dir.resolve(),
                         args.display_width, args.page, args.context, args.include_protected)
    except (ValueError, KeyError, TypeError, OSError) as error:
        raise SystemExit(str(error))
    print(json.dumps({'pages': manifest['pages'], 'overview': manifest['overview']['file'],
                      'manifest': str(args.out_dir.resolve() / 'review.json')}, ensure_ascii=False))


if __name__ == '__main__':
    sys.exit(main())
