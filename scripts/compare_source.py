#!/usr/bin/env python3
"""Compare a saved candidate with its source, or check its delivery evidence."""
import argparse
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

from verify_outputs import exact_output, image_size, pair_hashes, sha256_file, verify_pair

ENGINE = Path(__file__).with_name('compare_pixels.swift')


def policy_for(entry, size):
    cfg = entry['comparison']
    tolerance = cfg.get('channel_tolerance', 0)
    if type(tolerance) is not int or not 0 <= tolerance <= 254:
        raise ValueError('channel_tolerance must be an integer in 0...254')
    reason = cfg.get('tolerance_reason', '')
    if not isinstance(reason, str) or (tolerance and not reason.strip()):
        raise ValueError('nonzero tolerance requires a documented calibration reason')
    result = {'channel_tolerance': tolerance, 'tolerance_reason': reason}
    for key, regions in [('protected', entry['protected']), ('editable', cfg['editable'])]:
        if not isinstance(regions, list):
            raise ValueError(f'{key} must be an explicit region list')
        result[key] = []
        ids = set()
        for region in regions:
            name, rect = region['id'], region['rect']
            if not isinstance(name, str) or not name or name in ids:
                raise ValueError('region IDs must be nonempty and unique within each list')
            if not isinstance(rect, list) or len(rect) != 4 or any(type(v) is not int for v in rect):
                raise ValueError('pixel rect must be integer [x0,y0,x1,y1]')
            x0, y0, x1, y1 = rect
            if not (0 <= x0 < x1 <= size[0] and 0 <= y0 < y1 <= size[1]):
                raise ValueError(f'region outside source: {name}')
            ids.add(name)
            result[key].append({'id': name, 'rect': rect})
    for edit in result['editable']:
        a = edit['rect']
        for protected in result['protected']:
            b = protected['rect']
            if min(a[2], b[2]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[1], b[1]):
                raise ValueError('editable region intersects protection')
    return result


def policy_hash(policy):
    return hashlib.sha256(json.dumps(policy, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def files_for(entry, root):
    source = Path(entry['source'])
    if not source.is_absolute():
        raise ValueError('source must be absolute')
    png, pcraft = exact_output(root, entry['png']), exact_output(root, entry['pcraft'])
    if png.suffix != '.png' or pcraft.suffix != '.pcraft' or png.stem != pcraft.stem:
        raise ValueError('candidate must be a matching PNG/PCraft pair')
    verify_pair(source, png, pcraft)
    if sha256_file(source) != entry.get('source_sha256'):
        raise ValueError('source hash changed or missing; review region declarations')
    return source, png, pcraft


def report_path(entry, files):
    path = Path(entry['comparison']['report'])
    if not path.is_absolute() or path.suffix != '.json' or path.is_symlink():
        raise ValueError('comparison report must be an absolute non-symlink .json path')
    if any(path.parent.resolve() == file.parent.resolve() for file in files):
        raise ValueError('store comparison reports in a separate QA directory')
    return path


def validate_raster(result, policy, size):
    if (result['width'], result['height']) != size or result['pixels_scanned'] != size[0] * size[1]:
        raise ValueError('comparison did not cover every original-size pixel')
    for key in ('protected', 'editable', 'unchanged'):
        stats = result[key]
        values = [stats[k] for k in ('pixels', 'changed_pixels', 'above_tolerance_pixels', 'max_channel_delta')]
        if any(type(v) is not int or v < 0 for v in values):
            raise ValueError('invalid pixel statistics')
        if not 0 <= values[2] <= values[1] <= values[0] or values[3] > 255:
            raise ValueError('inconsistent pixel statistics')
    if sum(result[k]['pixels'] for k in ('protected', 'editable', 'unchanged')) != result['pixels_scanned']:
        raise ValueError('region coverage does not add up')
    if result['protected']['pixels'] + result['unchanged']['pixels'] == 0:
        raise ValueError('no preserved area checked')
    for key in ('protected', 'editable'):
        rows = result[key + '_regions']
        if [{'id': r['id'], 'rect': r['rect']} for r in rows] != policy[key]:
            raise ValueError('comparison region inventory differs from task')
    violations = sum(result[k]['above_tolerance_pixels'] for k in ('protected', 'unchanged'))
    if result['unexpected_pixels'] != violations:
        raise ValueError('inconsistent violation count')
    return violations


def compare(entry, root, engine=None):
    files = files_for(entry, root)
    size = image_size(files[0])
    policy = policy_for(entry, size)
    path = report_path(entry, files)
    diff = path.with_suffix('.diff.png')
    if path.exists() or diff.exists() or diff.is_symlink():
        raise ValueError('report/diff already exists; choose a fresh QA report filename')
    path.parent.mkdir(parents=True, exist_ok=True)
    before = pair_hashes(*files)
    with tempfile.TemporaryDirectory(prefix='pixel-check-', dir=path.parent) as temporary:
        temp = Path(temporary)
        config = {**policy, 'source': str(files[0]), 'output': str(files[1]), 'diff_image': str(temp / 'diff.png')}
        (temp / 'config.json').write_text(json.dumps(config))
        command = engine if engine is not None else ['swift', str(ENGINE)]
        run = subprocess.run([*command, str(temp / 'config.json')], capture_output=True, text=True)
        if run.returncode not in (0, 2):
            raise ValueError(f'pixel comparison failed: {run.stderr.strip()}')
        raster = json.loads(run.stdout)
        violations = validate_raster(raster, policy, size)
        if (run.returncode == 0) != (violations == 0):
            raise ValueError('comparison exit status disagrees with report')
        if before != pair_hashes(*files):
            raise ValueError('files changed during comparison; rerun after editing stops')
        # Exclusive creation protects existing QA artifacts as well as candidate files.
        with diff.open('xb') as dest:
            dest.write((temp / 'diff.png').read_bytes())
        report = {'schema_version': 1, 'status': 'pass' if violations == 0 else 'fail',
                  'file_hashes': before, 'policy_sha256': policy_hash(policy), 'policy': policy,
                  'raster': raster, 'diff_image': str(diff), 'diff_sha256': sha256_file(diff)}
        with path.open('x') as dest:
            json.dump(report, dest, ensure_ascii=False, indent=2)
    return report


def require_comparison(entry, root):
    """Validate reusable pixel evidence without claiming visual or editorial approval."""
    files = files_for(entry, root)
    current = pair_hashes(*files)
    path = report_path(entry, files)
    report = json.loads(path.read_text())
    size = image_size(files[0])
    policy = policy_for(entry, size)
    if report.get('schema_version') != 1 or report.get('file_hashes') != current:
        raise ValueError('stale comparison files or unsupported report')
    if report.get('policy_sha256') != policy_hash(policy) or report.get('policy') != policy:
        raise ValueError('comparison regions/tolerance changed; rerun comparison and review')
    violations = validate_raster(report['raster'], policy, size)
    if report.get('status') != 'pass' or violations:
        raise ValueError(f'original comparison failed: {violations} unexpected pixels')
    diff = path.with_suffix('.diff.png')
    if report.get('diff_image') != str(diff) or diff.is_symlink() or report.get('diff_sha256') != sha256_file(diff):
        raise ValueError('comparison difference image missing or changed')
    return report


def require_delivery(entry, root):
    files = files_for(entry, root)
    if entry.get('photocraft_reopened') is not True or entry.get('visual_passed') is not True:
        raise ValueError('PhotoCraft reopen and visual review are required')
    if entry.get('issues', []):
        raise ValueError('unresolved issues block delivery')
    if entry.get('review_hashes') != pair_hashes(*files):
        raise ValueError('missing or stale review hashes')
    path = report_path(entry, files)
    if entry.get('review_report_sha256') != sha256_file(path):
        raise ValueError('missing or changed reviewed comparison report')
    if 'production' in entry and entry.get('review_plan_sha256') != production_hash(entry):
        raise ValueError('translation/style/production plan changed; repeat affected editing and review')
    report = require_comparison(entry, root)
    policy = report['policy']
    ids = [region['id'] for region in policy['editable']]
    reviewed = entry.get('reviewed_editable_ids')
    if not isinstance(reviewed, list) or any(not isinstance(x, str) for x in reviewed) or sorted(reviewed) != sorted(ids):
        raise ValueError('review every editable region for residual text, repair seams and layout')
    return report


def production_hash(entry):
    return policy_hash({key: entry.get(key) for key in
                        ('source_sha256', 'target_language', 'phrases', 'layout', 'protected', 'production')})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('task', type=Path)
    parser.add_argument('output_dir', type=Path)
    parser.add_argument('--png', required=True)
    parser.add_argument('--check', action='store_true', help='Gate delivery using current comparison and visual review evidence')
    args = parser.parse_args()
    try:
        entries = [e for e in json.loads(args.task.read_text()) if e['png'] == args.png]
        if len(entries) != 1:
            raise ValueError('expected one matching source/language entry')
        entry = entries[0]
        if Path(entry['comparison']['report']).resolve() == args.task.resolve():
            raise ValueError('comparison report cannot overwrite task state')
        root = args.output_dir.resolve(strict=True)
        if args.check:
            require_delivery(entry, root)
            print('Delivery evidence passed for current bytes and region policy')
        else:
            result = compare(entry, root)
            print(json.dumps({'status': result['status'], 'unexpected_pixels': result['raster']['unexpected_pixels'],
                              'report': entry['comparison']['report'], 'diff_image': result['diff_image']}, ensure_ascii=False))
            if result['status'] == 'fail':
                raise SystemExit(2)
            print('Pixel preservation passed; editable-region and visual review still required')
    except (ValueError, KeyError, TypeError, OSError) as error:
        raise SystemExit(str(error))


if __name__ == '__main__':
    main()
