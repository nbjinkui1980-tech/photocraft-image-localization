#!/usr/bin/env python3
"""Cluster small rectangles into per-text-group bounding boxes.

Use after repairmap.swift derives a changed-pixel footprint (source vs an
existing localized output). repairmap emits per-fragment rects; text over a
photo or textured background fragments into many tiny rects, while a whole
inpainted text element is the real editable unit. Each rect is first grown by
MARGIN px; boxes whose edges are then at most GAP px apart on both axes merge
into one bounding box (GAP 0 merges only touching/overlapping boxes).

usage: cluster_rects.py REPAIRMAP.json [--gap 40] [--margin 6] [--width W --height H]

The canvas size comes from --width/--height, else from the repairmap JSON
("width"/"height", emitted by current repairmap.swift); it is never guessed.

Prints JSON: {"boxes": [[x0,y0,x1,y1], ...], "fragments": N, "max_box_area_pct": F}
Review the box list: a box covering ~100% of the canvas is rejected by the
delivery gate ("no preserved area checked"); shrink --gap so distinct text
elements stay separate instead of merging into one frame-spanning box.
"""
import argparse
import json


def near(a, b, gap):
    """True when the empty space between two [x0,y0,x1,y1) boxes is at most gap on both axes."""
    return (max(a[0], b[0]) - min(a[2], b[2]) <= gap
            and max(a[1], b[1]) - min(a[3], b[3]) <= gap)


def _find(parent, i):
    root = i
    while parent[root] != root:
        root = parent[root]
    while parent[i] != root:
        parent[i], i = root, parent[i]
    return root


def _merge_pass(boxes, gap, cell):
    """One connected-components pass: union boxes within gap, return each group's bounding box.

    A uniform grid keyed by (gap+1) registers each box under the cells of its gap-expanded
    extent, so any within-gap pair shares a cell and no neighbour ring is needed. Comparisons
    stay local to populated cells instead of scanning all pairs.
    """
    n = len(boxes)
    parent = list(range(n))
    grid = {}
    for i, b in enumerate(boxes):
        lo_x, lo_y = (b[0] - gap) // cell, (b[1] - gap) // cell
        hi_x, hi_y = (b[2] + gap) // cell, (b[3] + gap) // cell
        seen = set()
        for cx in range(lo_x, hi_x + 1):
            for cy in range(lo_y, hi_y + 1):
                bucket = grid.setdefault((cx, cy), [])
                for j in bucket:
                    if j not in seen:
                        seen.add(j)
                        if near(b, boxes[j], gap):
                            parent[_find(parent, i)] = _find(parent, j)
                bucket.append(i)
    groups = {}
    for i in range(n):
        root = _find(parent, i)
        b = boxes[i]
        g = groups.get(root)
        if g is None:
            groups[root] = list(b)
        else:
            g[0], g[1] = min(g[0], b[0]), min(g[1], b[1])
            g[2], g[3] = max(g[2], b[2]), max(g[3], b[3])
    return list(groups.values())


def cluster(rects, gap, margin, width, height):
    """Merge boxes transitively, where a merged box can then reach a further box.

    Matches the original iterate-to-fixed-point merge: each pass unions boxes that are
    within gap and replaces every group with its bounding box; the grown boxes may reach
    further boxes on the next pass, so passes repeat until the count stops shrinking. The
    per-pass spatial grid keeps each pass near-linear in the footprint instead of O(n^2).
    """
    if gap < 0 or margin < 0:
        raise ValueError('gap and margin must be non-negative')
    boxes = [[max(0, r[0] - margin), max(0, r[1] - margin),
              min(width, r[2] + margin), min(height, r[3] + margin)] for r in rects]
    cell = gap + 1
    previous = None
    while len(boxes) != previous:
        previous = len(boxes)
        boxes = _merge_pass(boxes, gap, cell)
    boxes.sort(key=lambda r: (r[1], r[0]))
    return boxes


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('repairmap')
    ap.add_argument('--gap', type=int, default=40)
    ap.add_argument('--margin', type=int, default=6)
    ap.add_argument('--width', type=int)
    ap.add_argument('--height', type=int)
    args = ap.parse_args()
    with open(args.repairmap) as stream:
        data = json.load(stream)
    meta = data if isinstance(data, dict) else {}
    rects = meta.get('rects', []) if isinstance(data, dict) else data
    width = args.width or meta.get('width')
    height = args.height or meta.get('height')
    if not (isinstance(width, int) and isinstance(height, int) and width > 0 and height > 0):
        raise SystemExit('canvas size unknown: pass --width/--height or use repairmap output with width/height')
    try:
        boxes = cluster(rects, args.gap, args.margin, width, height)
    except ValueError as error:
        raise SystemExit(str(error))
    area = width * height
    max_pct = max(((b[2]-b[0])*(b[3]-b[1]) for b in boxes), default=0) / area * 100
    print(json.dumps({'boxes': boxes, 'fragments': len(rects),
                      'max_box_area_pct': round(max_pct, 1)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
