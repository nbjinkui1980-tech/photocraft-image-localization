#!/usr/bin/env python3
"""Cluster small rectangles into per-text-group bounding boxes.

Use after repairmap.swift derives a changed-pixel footprint (source vs an
existing localized output). repairmap emits per-fragment rects; text over a
photo or textured background fragments into many tiny rects, while a whole
inpainted text element is the real editable unit. Clustering merges fragments
whose edges come within GAP px into one bounding box and adds MARGIN px.

usage: cluster_rects.py REPAIRMAP.json [--gap 40] [--margin 6] [--width W --height H]

Prints JSON: {"boxes": [[x0,y0,x1,y1], ...], "fragments": N, "max_box_area_pct": F}
Review the box list: a box covering ~100% of the canvas is rejected by the
delivery gate ("no preserved area checked"); shrink --gap so distinct text
elements stay separate instead of merging into one frame-spanning box.
"""
import argparse
import json


def cluster(rects, gap, margin, width, height):
    boxes = [[max(0, r[0] - margin), max(0, r[1] - margin),
              min(width, r[2] + margin), min(height, r[3] + margin)] for r in rects]
    changed = True
    while changed:
        changed = False
        i = 0
        while i < len(boxes):
            j = i + 1
            while j < len(boxes):
                a, b = boxes[i], boxes[j]
                if (min(a[2] + gap, b[2] + gap) > max(a[0] - gap, b[0] - gap)
                        and min(a[3] + gap, b[3] + gap) > max(a[1] - gap, b[1] - gap)):
                    boxes[i] = [min(a[0], b[0]), min(a[1], b[1]),
                                max(a[2], b[2]), max(a[3], b[3])]
                    boxes.pop(j)
                    changed = True
                else:
                    j += 1
            i += 1
    boxes.sort(key=lambda r: (r[1], r[0]))
    return boxes


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('repairmap')
    ap.add_argument('--gap', type=int, default=40)
    ap.add_argument('--margin', type=int, default=6)
    ap.add_argument('--width', type=int)
    ap.add_argument('--height', type=int)
    args = ap.parse_args()
    data = json.load(open(args.repairmap))
    rects = data.get('rects', data if isinstance(data, list) else [])
    width = args.width or max((r[2] for r in rects), default=0)
    height = args.height or max((r[3] for r in rects), default=0)
    boxes = cluster(rects, args.gap, args.margin, width, height)
    area = width * height or 1
    max_pct = max(((b[2]-b[0])*(b[3]-b[1]) for b in boxes), default=0) / area * 100
    print(json.dumps({'boxes': boxes, 'fragments': len(rects),
                      'max_box_area_pct': round(max_pct, 1)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
