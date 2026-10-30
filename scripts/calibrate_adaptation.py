#!/usr/bin/env python3
"""Calibrate batch-adaptation parameters for a NEW set of existing localized outputs.

The batch-adaptation defaults (channel_tolerance, cluster gap/margin) were derived on one
set and are not universal. This tool measures a new set and reports what to use:

1. classify_baseline: is each output's background preserved (source is a valid baseline)
   or redesigned (exclude it, or gate against the prior output instead)?
2. background_floor: the diffuse background noise ceiling, which is the minimum
   channel_tolerance the delivery gate needs. floor_max >> floor_p999 means a thin hot
   tail (a possible localized defect such as a repair seam) — review those images with
   outside_editable_scan.swift before trusting a high tolerance.
3. cluster gap/margin, scaled from the set's typical width (the reference defaults
   gap=40 / margin=6 were tuned at 1440 px wide).

usage:
  calibrate_adaptation.py PAIRS.json [--text-tol 30] [--dilate 40]
                                     [--gap-ratio 0.0278] [--margin-ratio 0.0042]
                                     [--max-box-pct 70] [--validate N] [--out REPORT.json]

PAIRS.json is a list of {"source": ..., "candidate": ...} (or [source, candidate]) items.
Requires macOS; Swift helpers run through swift_tool.py (compile-once cached).
"""
import argparse
import json
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import swift_tool  # noqa: E402
from cluster_rects import cluster  # noqa: E402


def run_json(binary, *args):
    run = subprocess.run([str(binary), *map(str, args)], capture_output=True, text=True, timeout=300)
    if run.returncode != 0:
        raise RuntimeError(f'{Path(binary).name} failed: {run.stderr.strip()}')
    return json.loads(run.stdout)


def load_pairs(path):
    data = json.loads(Path(path).read_text())
    pairs = []
    for item in data:
        if isinstance(item, dict):
            pairs.append((item['source'], item['candidate']))
        else:
            pairs.append((item[0], item[1]))
    return pairs


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('pairs')
    ap.add_argument('--text-tol', type=int, default=30)
    ap.add_argument('--dilate', type=int, default=40)
    ap.add_argument('--gap-ratio', type=float, default=0.0278)
    ap.add_argument('--margin-ratio', type=float, default=0.0042)
    ap.add_argument('--max-box-pct', type=float, default=70.0)
    ap.add_argument('--validate', type=int, default=3, help='validate coverage on up to N preserved images (0=off)')
    ap.add_argument('--out', help='write the full JSON report here')
    args = ap.parse_args()

    pairs = load_pairs(args.pairs)
    classify_bin = swift_tool.binary('classify_baseline')
    floor_bin = swift_tool.binary('background_floor')
    repairmap_bin = swift_tool.binary('repairmap')
    scan_bin = swift_tool.binary('outside_editable_scan')

    rows = []
    for source, candidate in pairs:
        cls = run_json(classify_bin, source, candidate)
        row = {'source': source, 'candidate': candidate, 'verdict': cls['verdict'],
               'classify_median': cls['median'], 'classify_frac': cls['frac']}
        if cls['verdict'] == 'preserved':
            floor = run_json(floor_bin, source, candidate, args.text_tol, args.dilate)
            row.update(floor_max=floor['floor_max'], floor_p999=floor['floor_p999'],
                       floor_p99=floor['floor_p99'], background_pixels=floor['background_pixels'])
            # A thin hot tail above the diffuse floor is a suspected localized defect, not noise.
            row['suspect_tail'] = floor['floor_max'] > max(8, floor['floor_p999'] + 4)
        rows.append(row)

    preserved = [r for r in rows if r['verdict'] == 'preserved']
    redesigned = [r for r in rows if r['verdict'] == 'redesigned']
    widths = []
    for r in preserved:
        # repairmap emits the canvas size; use it for scaling.
        rm = run_json(repairmap_bin, r['source'], r['candidate'], 4, 25, 0)
        widths.append(rm['width'])
        r['width'], r['height'] = rm['width'], rm['height']
    median_width = statistics.median(widths) if widths else 1440
    gap = max(8, round(median_width * args.gap_ratio))
    margin = max(4, round(median_width * args.margin_ratio))
    tol = max((r['floor_max'] for r in preserved), default=0)

    # Validate coverage with the recommended parameters on a sample of preserved images.
    validations = []
    for r in preserved[: max(0, args.validate)]:
        rm = run_json(repairmap_bin, r['source'], r['candidate'], tol, 1, 0)
        boxes = cluster(rm['rects'], gap, margin, rm['width'], rm['height'])
        area = rm['width'] * rm['height']
        max_pct = max(((b[2]-b[0])*(b[3]-b[1]) for b in boxes), default=0) / area * 100
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            task = tmp / 'task.json'
            editable = [{'id': f'e{i}', 'rect': b} for i, b in enumerate(boxes)]
            task.write_text(json.dumps([{'png': Path(r['candidate']).name, 'source': r['source'],
                                         'comparison': {'editable': editable, 'channel_tolerance': tol}}]))
            run = subprocess.run([str(scan_bin), str(task), Path(r['candidate']).name,
                                  str(Path(r['candidate']).parent)],
                                 capture_output=True, text=True, timeout=300)
            uncovered = run.stdout.splitlines()[0].split(':')[1].strip() if run.returncode == 0 else 'error'
        ok = uncovered == '0' and max_pct < args.max_box_pct
        validations.append({'candidate': r['candidate'], 'boxes': len(boxes),
                            'uncovered_pixels': uncovered, 'max_box_area_pct': round(max_pct, 1), 'ok': ok})

    report = {
        'recommended': {
            'channel_tolerance': tol,
            'repairmap': {'tol': tol, 'min_area': 1, 'dilate': 0},
            'cluster': {'gap': gap, 'margin': margin},
            'background_floor': {'text_tol': args.text_tol, 'dilate': args.dilate},
        },
        'tolerance_reason': (f'Measured diffuse background noise ceiling (background_floor text_tol='
                             f'{args.text_tol}, dilate={args.dilate}) across {len(preserved)} preserved '
                             f'output(s); the text/ringing footprint is captured by the clustered editable boxes.'),
        'preserved': len(preserved),
        'redesigned': len(redesigned),
        'redesigned_images': [r['candidate'] for r in redesigned],
        'suspect_tail_images': [r['candidate'] for r in preserved if r.get('suspect_tail')],
        'median_width': median_width,
        'validation': validations,
        'per_image': rows,
    }
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report['recommended'], ensure_ascii=False))
    print(json.dumps({'preserved': report['preserved'], 'redesigned': report['redesigned'],
                      'redesigned_images': report['redesigned_images'],
                      'suspect_tail_images': report['suspect_tail_images'],
                      'validation_ok': all(v['ok'] for v in validations) if validations else None},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
