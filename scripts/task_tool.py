#!/usr/bin/env python3
"""Task JSON bookkeeping so the agent does not hand-edit hashes and evidence fields.

  init           create one entry per source x language (hashes, names, fresh report path,
                 detected older versions); existing entries are left untouched
  fresh-report   point an entry at a new, unused comparison report path
  record-plan    production mode: record candidate_plan_sha256 after the saved candidate
                 implements the current plan
  record-review  write review results bound to the bytes the review pages were rendered from

The tool records what the reviewer asserts; it never decides visual quality itself.
Writes are atomic (temp file + rename); do not run several writers on one task file.
"""
import argparse
import copy
import json
import os
import re
import tempfile
import time
from pathlib import Path

from compare_source import files_for, production_hash, report_path, require_comparison, require_delivery
from verify_outputs import image_size, pair_hashes, sha256_file, verification_cache

SOURCE_SUFFIXES = {'.jpg', '.jpeg', '.png', '.webp'}


def load(task):
    entries = json.loads(Path(task).read_text())
    if not isinstance(entries, list):
        raise ValueError('task must be a JSON list')
    return entries


def save(task, entries):
    task = Path(task)
    fd, temp = tempfile.mkstemp(prefix='.task-', suffix='.json', dir=task.parent)
    with os.fdopen(fd, 'w') as stream:
        json.dump(entries, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    os.replace(temp, task)


def find(entries, png):
    matches = [e for e in entries if e.get('png') == png]
    if len(matches) != 1:
        raise ValueError(f'expected one entry for {png}, found {len(matches)}')
    return matches[0]


def fresh_report(qa_dir, stem):
    qa_dir = Path(qa_dir)
    stamp = time.strftime('%Y%m%d-%H%M%S')
    for n in range(1000):
        path = qa_dir / f'{stem}-cmp-{stamp}{"" if n == 0 else f"-{n}"}.json'
        if not path.exists() and not path.with_suffix('.diff.png').exists():
            return path
    raise ValueError('cannot find a free report name')


def cmd_init(args):
    source_dir, output_dir, qa_dir = (p.resolve() for p in (args.source_dir, args.output_dir, args.qa_dir))
    if not source_dir.is_dir() or not output_dir.is_dir():
        raise ValueError('source and output directories must exist')
    if qa_dir in {source_dir, output_dir}:
        raise ValueError('QA directory must differ from source and output directories')
    if not re.fullmatch(r'v\d+', args.version):
        raise ValueError('version must look like v2')
    langs = [l.strip() for l in args.langs.split(',') if l.strip()]
    if not langs or any(not re.fullmatch(r'[A-Za-z]{2,3}(-[A-Za-z0-9]+)*', l) for l in langs):
        raise ValueError('languages must be codes such as en,vi,th,pt-BR')
    task = args.task.resolve()
    entries = load(task) if task.exists() else []
    known = {e.get('png') for e in entries}
    sources = sorted(p for p in source_dir.iterdir() if p.is_file() and p.suffix.lower() in SOURCE_SUFFIXES)
    stems = [p.stem for p in sources]
    if len(stems) != len(set(stems)):
        raise ValueError('two sources share a filename stem; rename one first')
    added = skipped = 0
    for source in sources:
        width, height = image_size(source)
        digest = sha256_file(source)
        for lang in langs:
            stem = f'{source.stem}-{lang}-{args.version}'
            if f'{stem}.png' in known:
                skipped += 1
                continue
            pattern = re.compile(rf'{re.escape(source.stem)}-{re.escape(lang)}-(v\d+)\.(png|pcraft)')
            old = sorted(p.name for p in output_dir.iterdir()
                         if (m := pattern.fullmatch(p.name)) and m.group(1) != args.version and p.is_file())
            qa_dir.mkdir(parents=True, exist_ok=True)
            entries.append({
                'source': str(source), 'source_sha256': digest, 'target_language': lang,
                'png': f'{stem}.png', 'pcraft': f'{stem}.pcraft', 'old_files': old,
                'phrases': [], 'protected': [], 'repairs': [],
                'layout': {'canvas': [width, height], 'groups': []},
                'comparison': {'editable': [], 'channel_tolerance': 0,
                               'report': str(fresh_report(qa_dir, stem))},
                'reviewed_editable_ids': [], 'issues': [],
                'photocraft_reopened': False, 'visual_passed': False})
            known.add(f'{stem}.png')
            added += 1
    save(task, entries)
    print(json.dumps({'task': str(task), 'added': added, 'existing': skipped, 'sources': len(sources),
                      'languages': langs}, ensure_ascii=False))


def cmd_fresh_report(args):
    entries = load(args.task)
    entry = find(entries, args.png)
    current = Path(entry['comparison']['report'])
    path = fresh_report(current.parent, Path(entry['png']).stem)
    entry['comparison']['report'] = str(path)
    # Evidence bound to the previous report no longer applies.
    entry.pop('review_report_sha256', None)
    entry['visual_passed'] = False
    save(args.task, entries)
    print(path)


def cmd_record_plan(args):
    entries = load(args.task)
    entry = find(entries, args.png)
    if 'production' not in entry:
        raise ValueError('record-plan applies to production entries only')
    with verification_cache():
        files_for(entry, args.output_dir.resolve(strict=True))
    entry['candidate_plan_sha256'] = production_hash(entry)
    save(args.task, entries)
    print(entry['candidate_plan_sha256'])


def cmd_record_review(args):
    entries = load(args.task)
    entry = find(entries, args.png)
    root = args.output_dir.resolve(strict=True)
    before = json.loads(args.before.read_text())
    before = before.get('file_hashes', before)
    with verification_cache():
        files = files_for(entry, root)
        current = pair_hashes(*files)
        if before != current:
            raise ValueError('files changed since the review material was generated; review again')
        path = report_path(entry, files)
        if args.visual_passed:
            require_comparison(entry, root)
    ids = [r['id'] for r in entry['comparison']['editable']]
    if args.reviewed_ids == 'all':
        reviewed = ids
    else:
        reviewed = [x for x in (args.reviewed_ids or '').split(',') if x]
        unknown = sorted(set(reviewed) - set(ids))
        if unknown:
            raise ValueError(f'unknown editable region IDs: {unknown}')
    issues = [] if args.clear_issues else list(entry.get('issues', []))
    issues += args.issue
    if args.visual_passed and issues:
        raise ValueError('cannot pass visual review with unresolved issues; fix them or use --clear-issues')
    updated = copy.deepcopy(entry)
    updated.update(photocraft_reopened=bool(args.reopened), visual_passed=bool(args.visual_passed),
                   review_hashes=current, reviewed_editable_ids=reviewed, issues=issues)
    if path.is_file():
        updated['review_report_sha256'] = sha256_file(path)
    if 'production' in updated and args.visual_passed:
        plan = production_hash(updated)
        if updated.get('candidate_plan_sha256') != plan:
            raise ValueError('candidate was not recorded against the current plan; run record-plan after editing')
        updated['review_plan_sha256'] = plan
    status = 'recorded (not delivered)'
    if args.visual_passed:
        require_delivery(updated, root)  # refuse to write a pass the gate would reject
        status = 'delivery gate passed'
    entry.clear()
    entry.update(updated)
    save(args.task, entries)
    print(json.dumps({'png': args.png, 'status': status, 'issues': issues,
                      'reviewed_editable_ids': reviewed,
                      'unreviewed': sorted(set(ids) - set(reviewed))}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('init', help='create entries for every source x language')
    p.add_argument('task', type=Path); p.add_argument('source_dir', type=Path)
    p.add_argument('output_dir', type=Path); p.add_argument('qa_dir', type=Path)
    p.add_argument('--langs', required=True); p.add_argument('--version', required=True)
    p.set_defaults(run=cmd_init)
    p = sub.add_parser('fresh-report', help='assign a new unused comparison report path')
    p.add_argument('task', type=Path); p.add_argument('--png', required=True)
    p.set_defaults(run=cmd_fresh_report)
    p = sub.add_parser('record-plan', help='record candidate_plan_sha256 for a production entry')
    p.add_argument('task', type=Path); p.add_argument('output_dir', type=Path); p.add_argument('--png', required=True)
    p.set_defaults(run=cmd_record_plan)
    p = sub.add_parser('record-review', help='record review results bound to reviewed bytes')
    p.add_argument('task', type=Path); p.add_argument('output_dir', type=Path); p.add_argument('--png', required=True)
    p.add_argument('--before', required=True, type=Path,
                   help='review.json from review_sheet.py (or a JSON of source/png/pcraft hashes) captured before review')
    p.add_argument('--reviewed-ids', help='comma-separated editable region IDs actually inspected, or "all"')
    p.add_argument('--reopened', action='store_true', help='the saved PCraft was reopened in PhotoCraft and text is editable')
    p.add_argument('--visual-passed', action='store_true', help='the reviewer approved the candidate')
    p.add_argument('--issue', action='append', default=[], help='record an unresolved issue (repeatable)')
    p.add_argument('--clear-issues', action='store_true', help='drop previously recorded issues that are now fixed')
    p.set_defaults(run=cmd_record_review)
    args = parser.parse_args()
    if getattr(args, 'visual_passed', False) and not args.reopened:
        raise SystemExit('--visual-passed requires --reopened: reopen the saved PCraft first')
    try:
        args.run(args)
    except (ValueError, KeyError, TypeError, OSError) as error:
        raise SystemExit(str(error))


if __name__ == '__main__':
    main()
