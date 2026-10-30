#!/usr/bin/env python3
"""Regressions for background_floor.swift and calibrate_adaptation.py (macOS/Swift required)."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from test_source_comparison import image_file
import swift_tool

SCRIPTS = Path(__file__).resolve().parent


def solid(path, width, height, value):
    image_file(path, {(x, y): value for y in range(height) for x in range(width)}, width, height)


class BackgroundFloor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bin = swift_tool.binary('background_floor')  # compile-once cached build

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.src = self.root / 'source.png'; self.out = self.root / 'candidate.png'
        solid(self.src, 120, 120, (100, 100, 100, 255))

    def floor(self, *args):
        run = subprocess.run([str(self.bin), str(self.src), str(self.out), *map(str, args)],
                             capture_output=True, text=True, timeout=60)
        self.assertEqual(run.returncode, 0, run.stderr)
        return json.loads(run.stdout)

    def test_identical_has_zero_floor(self):
        solid(self.out, 120, 120, (100, 100, 100, 255))
        r = self.floor(30, 10)
        self.assertEqual(r['floor_max'], 0)
        self.assertEqual(r['strong_pixels'], 0)

    def test_uniform_noise_floor_excludes_strong_text(self):
        # Background raised by 10 everywhere; one strong 20x20 text block in the middle.
        edits = {(x, y): (110, 110, 110, 255) for y in range(120) for x in range(120)}
        for y in range(50, 70):
            for x in range(50, 70):
                edits[(x, y)] = (0, 0, 0, 255)  # strong text, diff 100 > text_tol
        image_file(self.out, edits, 120, 120)
        r = self.floor(30, 10)
        self.assertEqual(r['floor_max'], 10)
        self.assertGreater(r['strong_pixels'], 0)
        self.assertLess(r['strong_pixels'], 120 * 120)

    def test_hot_tail_below_text_tol_is_detected(self):
        # Diffuse noise 4, plus one background pixel at 20 (< text_tol 30): a thin hot tail.
        edits = {(x, y): (104, 104, 104, 255) for y in range(120) for x in range(120)}
        edits[(100, 100)] = (120, 120, 120, 255)
        image_file(self.out, edits, 120, 120)
        r = self.floor(30, 10)
        self.assertEqual(r['floor_p99'], 4)
        self.assertEqual(r['floor_max'], 20)


class CalibrateAdaptation(unittest.TestCase):
    def test_calibrate_mixed_set(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            # Preserved: uniform +4 shift (within tolerance); redesigned: uniform +100.
            src_p = root / 'a-src.png'; cand_p = root / 'a-cand.png'
            solid(src_p, 100, 100, (100, 100, 100, 255)); solid(cand_p, 100, 100, (104, 104, 104, 255))
            src_r = root / 'b-src.png'; cand_r = root / 'b-cand.png'
            solid(src_r, 100, 100, (100, 100, 100, 255)); solid(cand_r, 100, 100, (200, 200, 200, 255))
            pairs = root / 'pairs.json'
            pairs.write_text(json.dumps([{'source': str(src_p), 'candidate': str(cand_p)},
                                         {'source': str(src_r), 'candidate': str(cand_r)}]))
            run = subprocess.run([sys.executable, str(SCRIPTS / 'calibrate_adaptation.py'), str(pairs),
                                  '--validate', '1'], capture_output=True, text=True, timeout=600)
            self.assertEqual(run.returncode, 0, run.stderr)
            lines = [json.loads(line) for line in run.stdout.strip().split('\n') if line.strip()]
            recommended, summary = lines[0], lines[1]
            self.assertEqual(recommended['channel_tolerance'], 4)
            self.assertEqual(recommended['cluster']['gap'], 8)  # width 100 * 0.0278, clamped to >= 8
            self.assertEqual(summary['preserved'], 1)
            self.assertEqual(summary['redesigned'], 1)
            self.assertEqual(summary['redesigned_images'], [str(cand_r)])


if __name__ == '__main__':
    unittest.main()
