#!/usr/bin/env python3
"""Check declared geometry against PhotoCraft type.info; does not judge visual quality."""
import argparse
import json
import math
from pathlib import Path

from verify_outputs import exact_output, image_size, sha256_file


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('expected finite numeric geometry')
    return value


def rect(value):
    if not isinstance(value, list) or len(value) != 4:
        raise ValueError('rect must be [x0,y0,x1,y1], not [x,y,width,height]')
    x0, y0, x1, y1 = map(number, value)
    if x1 <= x0 or y1 <= y0:
        raise ValueError('rect must have positive area')
    return x0, y0, x1, y1


def contains(outer, inner, tolerance=0):
    return (inner[0] >= outer[0] - tolerance and inner[1] >= outer[1] - tolerance
            and inner[2] <= outer[2] + tolerance and inner[3] <= outer[3] + tolerance)


def overlaps(a, b):
    return min(a[2], b[2]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[1], b[1])


def cell_for(group, item):
    if 'grid' not in group:
        return rect(item['cell'])
    grid = group['grid']
    x0, y0, x1, y1 = rect(grid['rect'])
    n, col = grid['columns'], item['column']
    if type(n) is not int or n <= 0 or type(col) is not int or not 0 <= col < n:
        raise ValueError('invalid grid columns or column index')
    gap = number(grid.get('gap_px', 0))
    width = (x1 - x0 - gap * (n - 1)) / n
    if gap < 0 or width <= 0:
        raise ValueError('grid has no usable cell width')
    left = x0 + col * (width + gap)
    return left, y0, left + width, y1


def check(entry, infos=None, phase='layout', canvas_size=None):
    # pre-repair only needs the canvas and protection, which exist for photos and single
    # headlines that carry no layout.groups; take the canvas from the source there and keep
    # layout.canvas for the geometry phase.
    if phase == 'pre-repair':
        if canvas_size is None:
            width, height = map(number, entry['layout']['canvas'])
        else:
            width, height = map(number, canvas_size)
    else:
        width, height = map(number, entry['layout']['canvas'])
    canvas = rect([0, 0, width, height])
    spec = entry.get('layout', {})
    tolerance = number(spec.get('tolerance_px', 2))
    if tolerance < 0:
        raise ValueError('negative tolerance')
    protected = [(zone['id'], rect(zone['rect'])) for zone in entry['protected']]
    for name, box in protected:
        if not contains(canvas, box):
            raise ValueError(f'protected region outside canvas: {name}')
    issues = []
    if phase == 'pre-repair':
        if not entry.get('repairs'):
            raise ValueError('no repair regions declared')
        for repair in entry['repairs']:
            box = rect(repair['rect'])
            margin = number(repair['effect_margin_px'])
            if margin < 0:
                raise ValueError('effect margin must cover feather/filter reach')
            reach = (box[0] - margin, box[1] - margin, box[2] + margin, box[3] + margin)
            if not contains(canvas, reach):
                issues.append(f"repair {repair['id']}: effect reaches outside canvas")
            for name, protected_box in protected:
                if overlaps(reach, protected_box):
                    issues.append(f"repair {repair['id']}: touches protected {name}")
        return issues

    if not spec.get('groups') or not isinstance(infos, list):
        raise ValueError('layout groups and type.info results required')
    by_id = {info['layer']: info for info in infos}
    if len(by_id) != len(infos):
        raise ValueError('duplicate type.info layer IDs')
    seen, boxes = set(), []
    for group in spec['groups']:
        expected = group['style']
        required = {'font_family', 'size_pt', 'weight', 'color', 'leading_pt', 'horizontal_scale', 'vertical_scale'}
        if not required <= expected.keys():
            raise ValueError('group style must declare font, size, weight, color, leading and scales')
        if number(expected['size_pt']) < number(group['min_size_pt']):
            issues.append(f"{group['id']}: style below declared readable minimum")
        padding = number(group.get('padding_px', 0))
        if padding < 0 or group['align'] not in {'left', 'center', 'right'}:
            raise ValueError('invalid padding or alignment')
        if not group['items']:
            raise ValueError('empty layout group')
        if 'grid' in group:
            columns = [item['column'] for item in group['items']]
            if sorted(columns) != list(range(group['grid']['columns'])):
                raise ValueError('equal-column group must have one item per column')
        for item in group['items']:
            layer = item['layer']
            if layer in seen:
                raise ValueError('a layer must belong to exactly one layout group')
            seen.add(layer)
            if layer not in by_id:
                issues.append(f'{layer}: missing type.info')
                continue
            info = by_id[layer]
            if info.get('orientation') != 'Horizontal' or info.get('warp') is not None:
                issues.append(f'{layer}: unsupported rotated/vertical/warped layout; manual review required')
                continue
            a, b, c, d, e, f = map(number, info['transform'])
            if a <= 0 or d <= 0 or abs(b) > 1e-6 or abs(c) > 1e-6:
                issues.append(f'{layer}: unsupported transform; manual review required')
                continue
            if abs(a - 1) > 1e-6 or abs(d - 1) > 1e-6:
                issues.append(f'{layer}: scaled text; normalize transform and set size in points')
            box = rect(info['bounds'])
            cell = cell_for(group, item)
            inner = rect([cell[0] + padding, cell[1] + padding, cell[2] - padding, cell[3] - padding])
            if not contains(canvas, cell) or not contains(canvas, box) or not contains(inner, box, tolerance):
                issues.append(f'{layer}: rendered bounds outside cell or canvas')
            for name, protected_box in protected:
                if overlaps(box, protected_box):
                    issues.append(f'{layer}: overlaps protected {name}')
            boxes.append((layer, box))
            if not info.get('runs'):
                issues.append(f'{layer}: missing character styles')
            for run in info.get('runs', []):
                for key, value in expected.items():
                    actual = run['style'].get(key)
                    equal = actual == value
                    if isinstance(value, (float, int)) and not isinstance(value, bool):
                        equal = isinstance(actual, (float, int)) and math.isfinite(actual) and abs(actual - value) < 1e-5
                    if not equal:
                        issues.append(f'{layer}: style mismatch {key}')
            if info.get('warnings'):
                issues.append(f"{layer}: renderer warnings: {info['warnings']}")
            lines = info.get('lines', [])
            if not lines:
                issues.append(f'{layer}: no rendered lines')
            for line in lines:
                if line['start'] == line['end']:
                    continue
                left, right = a * number(line['x0']) + e, a * number(line['x1']) + e
                target = {'left': inner[0], 'center': (inner[0] + inner[2]) / 2, 'right': inner[2]}[group['align']]
                anchor = {'left': left, 'center': (left + right) / 2, 'right': right}[group['align']]
                if abs(anchor - target) > tolerance:
                    issues.append(f'{layer}: line {line["start"]} alignment differs by {anchor - target:.2f}px')
            baseline = item.get('baseline_y', group.get('baseline_y'))
            if baseline is not None and lines and abs(d * number(lines[0]['baseline']) + f - number(baseline)) > tolerance:
                issues.append(f'{layer}: first baseline mismatch')
    for i, (layer, box) in enumerate(boxes):
        for other, other_box in boxes[i + 1:]:
            if overlaps(box, other_box):
                issues.append(f'{layer}: overlaps text layer {other}')
    return sorted(set(issues))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('task', type=Path)
    parser.add_argument('output_dir', type=Path)
    parser.add_argument('--png', required=True, help='Exact filename identifying one task item')
    parser.add_argument('--phase', choices=['layout', 'pre-repair'], default='layout')
    args = parser.parse_args()
    try:
        entries = [entry for entry in json.loads(args.task.read_text()) if entry['png'] == args.png]
        if len(entries) != 1:
            raise ValueError('expected exactly one matching task item')
        entry = entries[0]
        source = Path(entry['source'])
        if not source.is_absolute() or sha256_file(source) != entry['source_sha256']:
            raise ValueError('source path/hash changed; refresh protected regions and layout')
        source_size = list(image_size(source))
        infos = None
        canvas_size = source_size
        if args.phase == 'layout':
            # The geometry phase needs the declared grid; it must match the source exactly.
            if source_size != entry['layout']['canvas']:
                raise ValueError('layout canvas differs from source dimensions')
            pcraft = exact_output(args.output_dir.resolve(strict=True), entry['pcraft'])
            snapshot_path = Path(entry['type_snapshot'])
            if not snapshot_path.is_absolute():
                raise ValueError('type_snapshot must be an absolute path')
            snapshot = json.loads(snapshot_path.read_text())
            if snapshot['pcraft_sha256'] != sha256_file(pcraft):
                raise ValueError('stale type.info snapshot; collect again from the saved PCraft')
            infos = snapshot['types']
        elif 'layout' in entry and 'canvas' in entry.get('layout', {}) and source_size != entry['layout']['canvas']:
            # If a canvas is declared anyway, keep it honest.
            raise ValueError('layout canvas differs from source dimensions')
        issues = check(entry, infos, args.phase, canvas_size)
        if issues:
            raise ValueError('\n'.join(issues))
        print(f'{args.phase} geometry passed; visual review and protected-pixel comparison still required')
    except (ValueError, KeyError, TypeError, OSError) as error:
        raise SystemExit(str(error))


if __name__ == '__main__':
    main()
