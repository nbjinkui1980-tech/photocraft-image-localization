#!/usr/bin/env python3
"""Batch-adaptation helper regressions: classify_baseline, repairmap, cluster_rects,
outside_editable_scan and contact_sheets. Requires macOS and Swift."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import random
import time

from cluster_rects import cluster
from test_source_comparison import image_file


def brute_cluster(rects, gap, margin, width, height):
    """Reference: the original iterate-to-fixed-point merge, kept to pin cluster()'s output."""
    def edge_gap(a, b):
        return max(a[0], b[0]) - min(a[2], b[2]), max(a[1], b[1]) - min(a[3], b[3])
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
                gx, gy = edge_gap(a, b)
                if gx <= gap and gy <= gap:
                    boxes[i] = [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])]
                    boxes.pop(j); changed = True
                else:
                    j += 1
            i += 1
    boxes.sort(key=lambda r: (r[1], r[0]))
    return boxes

SCRIPTS = Path(__file__).resolve().parent
TOOLS = ('classify_baseline', 'repairmap', 'outside_editable_scan', 'compare_pixels', 'contact_sheets')


def block(x0, y0, x1, y1, value):
    return {(x, y): value for y in range(y0, y1) for x in range(x0, x1)}


class ClusterRects(unittest.TestCase):
    def test_gap_is_edge_distance(self):
        self.assertEqual(len(cluster([[0, 0, 10, 10], [50, 0, 60, 10]], 40, 0, 200, 20)), 1)  # 40 px apart
        self.assertEqual(len(cluster([[0, 0, 10, 10], [51, 0, 61, 10]], 40, 0, 200, 20)), 2)  # 41 px apart
        self.assertEqual(len(cluster([[0, 0, 10, 10], [70, 0, 80, 10]], 40, 0, 200, 20)), 2)  # old code merged this

    def test_gap_requires_both_axes(self):
        self.assertEqual(len(cluster([[0, 0, 10, 10], [5, 100, 15, 110]], 40, 0, 200, 200)), 2)

    def test_zero_gap_touching_and_overlap(self):
        self.assertEqual(cluster([[0, 0, 10, 10], [10, 0, 20, 10]], 0, 0, 50, 50), [[0, 0, 20, 10]])
        self.assertEqual(len(cluster([[0, 0, 10, 10], [11, 0, 20, 10]], 0, 0, 50, 50)), 2)

    def test_margin_clamped_and_chained(self):
        self.assertEqual(cluster([[2, 2, 5, 5]], 0, 6, 8, 8), [[0, 0, 8, 8]])
        chain = [[0, 0, 5, 5], [15, 0, 20, 5], [30, 0, 35, 5]]
        self.assertEqual(cluster(chain, 10, 0, 100, 100), [[0, 0, 35, 5]])

    def test_invalid_parameters(self):
        for gap, margin in ((-1, 0), (0, -1)):
            with self.assertRaises(ValueError):
                cluster([[0, 0, 1, 1]], gap, margin, 10, 10)

    def test_matches_brute_force_reference(self):
        rng = random.Random(7)
        for _ in range(200):
            w = h = 400
            rects = [[x := rng.randrange(0, w - 5), y := rng.randrange(0, h - 5),
                      x + rng.randrange(1, 20), y + rng.randrange(1, 20)]
                     for _ in range(rng.randrange(0, 40))]
            gap, margin = rng.randrange(0, 30), rng.randrange(0, 8)
            self.assertEqual(cluster([list(r) for r in rects], gap, margin, w, h),
                             brute_cluster(rects, gap, margin, w, h))

    def test_transitive_chain_merges_into_one(self):
        chain = [[i * 10, 0, i * 10 + 3, 3] for i in range(50)]  # each 7 px from the next
        self.assertEqual(cluster(chain, 7, 0, 600, 10), [[0, 0, 493, 3]])
        self.assertEqual(len(cluster(chain, 6, 0, 600, 10)), 50)  # 7 > 6: none merge

    def test_scales_to_dense_footprint(self):
        rng = random.Random(1)
        rects = [[x := rng.randrange(0, 1994), y := rng.randrange(0, 1994), x + 3, y + 3] for _ in range(4000)]
        start = time.monotonic()
        boxes = cluster(rects, 10, 2, 2000, 2000)
        self.assertLess(time.monotonic() - start, 2.0)  # old O(n^3) path took far longer here
        self.assertTrue(all(b[2] > b[0] and b[3] > b[1] for b in boxes))

    def test_cli_canvas_size(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'map.json'
            path.write_text(json.dumps({'rects': [[0, 0, 10, 10]], 'width': 100, 'height': 50}))
            run = subprocess.run([sys.executable, SCRIPTS / 'cluster_rects.py', path, '--margin', '0'],
                                 capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(json.loads(run.stdout)['max_box_area_pct'], 2.0)
            path.write_text(json.dumps([[0, 0, 10, 10]]))
            run = subprocess.run([sys.executable, SCRIPTS / 'cluster_rects.py', path],
                                 capture_output=True, text=True)
            self.assertNotEqual(run.returncode, 0)
            self.assertIn('canvas size unknown', run.stderr)
            run = subprocess.run([sys.executable, SCRIPTS / 'cluster_rects.py', path, '--width', '20', '--height', '20',
                                  '--margin', '0'], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(json.loads(run.stdout)['boxes'], [[0, 0, 10, 10]])


class NativeHelpers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = tempfile.TemporaryDirectory()
        cls.bin = {}
        for name in TOOLS:
            binary = Path(cls.build.name) / name
            run = subprocess.run(['swiftc', '-module-cache-path', str(Path(cls.build.name) / 'cache'),
                                  str(SCRIPTS / f'{name}.swift'), '-o', str(binary)],
                                 capture_output=True, text=True, timeout=180)
            if run.returncode:
                raise RuntimeError(f'{name}: {run.stderr}')
            cls.bin[name] = str(binary)

    @classmethod
    def tearDownClass(cls):
        cls.build.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def tool(self, name, *args):
        return subprocess.run([self.bin[name], *map(str, args)], capture_output=True, text=True, timeout=60)

    def png(self, name, edits=None, width=100, height=100, gray=False):
        path = self.root / name
        image_file(path, edits, width, height, gray)
        return path

    # classify_baseline
    def test_classify_preserved_and_redesigned(self):
        src = self.png('src.png')
        text = self.png('text.png', block(40, 40, 60, 60, (0, 0, 0, 255)))
        regraded = self.png('regraded.png', block(0, 0, 100, 100, (230, 230, 230, 255)))
        result = json.loads(self.tool('classify_baseline', src, text, 10).stdout)
        self.assertEqual(result['verdict'], 'preserved')
        result = json.loads(self.tool('classify_baseline', src, regraded, 10).stdout)
        self.assertEqual((result['verdict'], result['median']), ('redesigned', 25))

    def test_classify_small_image_is_sampled(self):
        src = self.png('src.png', width=40, height=40)
        regraded = self.png('regraded.png', block(0, 0, 40, 40, (200, 200, 200, 255)), 40, 40)
        run = self.tool('classify_baseline', src, regraded, 5)
        self.assertEqual(run.returncode, 0, run.stderr)
        result = json.loads(run.stdout)
        self.assertGreater(result['total'], 0)
        self.assertEqual(result['verdict'], 'redesigned')

    def test_classify_grayscale(self):
        src = self.png('g.png', gray=True)
        dark = self.png('gd.png', block(0, 0, 100, 100, (100,)), gray=True)
        result = json.loads(self.tool('classify_baseline', src, dark, 10).stdout)
        self.assertEqual((result['verdict'], result['median']), ('redesigned', 155))

    def test_classify_rejects_bad_arguments(self):
        src = self.png('src.png')
        for params in (('0',), ('-5',), ('abc',), ('10', '300'), ('10', '-1')):
            self.assertNotEqual(self.tool('classify_baseline', src, src, *params).returncode, 0, params)
        self.assertNotEqual(self.tool('classify_baseline', src, self.png('o.png', width=50)).returncode, 0)

    # repairmap
    def test_repairmap_footprint(self):
        src = self.png('src.png')
        out = self.png('out.png', {**block(10, 20, 30, 25, (0, 0, 0, 255)), **block(99, 99, 100, 100, (0, 0, 0, 255))})
        run = self.tool('repairmap', src, out, 0, 1, 0)
        self.assertEqual(run.returncode, 0, run.stderr)
        result = json.loads(run.stdout)
        self.assertEqual(sorted(result['rects']), [[10, 20, 30, 25], [99, 99, 100, 100]])
        self.assertEqual((result['width'], result['height'], result['diff_pixels']), (100, 100, 101))
        # MIN_AREA drops the single pixel, which is then reported outside the footprint.
        result = json.loads(self.tool('repairmap', src, out, 0, 2, 2).stdout)
        self.assertEqual(result['rects'], [[8, 18, 32, 27]])
        self.assertEqual((result['outside_count'], result['outside_bbox']), (1, [99, 99, 100, 100]))

    def test_repairmap_alpha_and_gray(self):
        src = self.png('src.png')
        alpha = self.png('alpha.png', block(5, 5, 8, 8, (255, 255, 255, 0)))
        self.assertEqual(json.loads(self.tool('repairmap', src, alpha, 0, 1, 0).stdout)['rects'], [[5, 5, 8, 8]])
        gsrc = self.png('g.png', gray=True)
        gout = self.png('go.png', block(50, 60, 52, 61, (0,)), gray=True)
        self.assertEqual(json.loads(self.tool('repairmap', gsrc, gout, 0, 1, 0).stdout)['rects'], [[50, 60, 52, 61]])

    def test_repairmap_rejects_bad_arguments(self):
        src = self.png('src.png')
        for params in (('-1', '1', '0'), ('255', '1', '0'), ('0', '0', '0'), ('0', '1', '-1'), ('x', '1', '0')):
            self.assertNotEqual(self.tool('repairmap', src, src, *params).returncode, 0, params)

    # outside_editable_scan agrees with the delivery engine
    def scan_both(self, src, out, editable, tolerance=0):
        outdir = self.root / 'out'
        outdir.mkdir(exist_ok=True)
        target = outdir / 'cand.png'
        target.write_bytes(out.read_bytes())
        regions = [{'id': f'e{i}', 'rect': r} for i, r in enumerate(editable)]
        task = self.root / 'task.json'
        task.write_text(json.dumps([{'source': str(src), 'png': 'cand.png',
                                     'comparison': {'editable': regions, 'channel_tolerance': tolerance}}]))
        scan = self.tool('outside_editable_scan', task, 'cand.png', outdir)
        self.assertEqual(scan.returncode, 0, scan.stderr)
        count = int(scan.stdout.splitlines()[0].split(':')[1])
        config = self.root / 'config.json'
        config.write_text(json.dumps({'source': str(src), 'output': str(target), 'diff_image': str(self.root / 'd.png'),
                                      'protected': [], 'editable': regions, 'channel_tolerance': tolerance}))
        engine = self.tool('compare_pixels', config)
        self.assertIn(engine.returncode, (0, 2), engine.stderr)
        return count, json.loads(engine.stdout)['unexpected_pixels'], scan.stdout

    def test_outside_scan_matches_engine_on_alpha(self):
        src = self.png('src.png')
        out = self.png('out.png', {**block(10, 10, 20, 20, (0, 0, 0, 255)),
                                   **block(90, 0, 92, 3, (255, 255, 255, 128))})
        count, engine, stdout = self.scan_both(src, out, [[10, 10, 20, 20]])
        self.assertEqual((count, engine), (6, 6))
        self.assertIn('bbox=[90,0,92,3] count=6', stdout)

    def test_outside_scan_matches_engine_on_gray_and_tolerance(self):
        src = self.png('g.png', gray=True)
        out = self.png('go.png', {**block(0, 0, 4, 1, (250,)), **block(96, 96, 100, 100, (200,))}, gray=True)
        self.assertEqual(self.scan_both(src, out, [])[:2], (20, 20))
        self.assertEqual(self.scan_both(src, out, [], tolerance=10)[:2], (16, 16))
        self.assertEqual(self.scan_both(src, out, [[96, 96, 100, 100]], tolerance=10)[:2], (0, 0))

    def test_outside_scan_rejects_malformed_task(self):
        src = self.png('src.png')
        task = self.root / 'task.json'
        for comparison in ({'editable': [], 'channel_tolerance': -1},
                           {'editable': [{'id': 'a', 'rect': [5, 5, 5, 9]}], 'channel_tolerance': 0},
                           {'editable': [{'id': 'a', 'rect': [0, 0, 1.5, 2]}], 'channel_tolerance': 0}):
            task.write_text(json.dumps([{'source': str(src), 'png': 'src.png', 'comparison': comparison}]))
            self.assertNotEqual(self.tool('outside_editable_scan', task, 'src.png', self.root).returncode, 0, comparison)
        task.write_text(json.dumps([]))
        self.assertNotEqual(self.tool('outside_editable_scan', task, 'src.png', self.root).returncode, 0)

    # contact_sheets
    def test_contact_sheets_pages(self):
        images = [self.png(f'i{n}.png', width=30, height=20) for n in range(5)]
        sheets = self.root / 'sheets'
        run = self.tool('contact_sheets', sheets, *images)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn('Rendered 5 of 5', run.stdout)
        self.assertEqual(sorted(p.name for p in sheets.iterdir()), ['sheet-01.png', 'sheet-02.png'])
        bad = self.root / 'bad.png'
        bad.write_bytes(b'not an image')
        self.assertNotEqual(self.tool('contact_sheets', self.root / 'x', images[0], bad).returncode, 0)


if __name__ == '__main__':
    unittest.main()
