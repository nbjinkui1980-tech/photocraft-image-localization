#!/usr/bin/env python3
"""Native raster, delivery-gate and cleanup regressions. Requires macOS and Swift."""
import contextlib
import copy
import io
import json
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

from cleanup_versions import cleanup
from compare_source import compare, policy_for, require_delivery
from verify_outputs import pair_hashes, sha256_file
from batch_verify import run_batch

SCRIPTS = Path(__file__).resolve().parent


def image_file(path, edits=None, width=13, height=11, gray=False):
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    data = bytearray()
    for y in range(height):
        data.append(0)
        for x in range(width):
            data.extend((edits or {}).get((x, y), (255,) if gray else (255, 255, 255, 255)))
    path.write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 0 if gray else 6, 0, 0, 0))
                     + chunk(b'IDAT', zlib.compress(data)) + chunk(b'IEND', b''))


class SourceComparison(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.build.cleanup)
        cls.engine = Path(cls.build.name) / 'compare-pixels'
        run = subprocess.run(['swiftc', '-module-cache-path', str(Path(cls.build.name) / 'cache'),
                              str(SCRIPTS / 'compare_pixels.swift'), '-o', str(cls.engine)], capture_output=True, text=True, timeout=60)
        if run.returncode:
            raise RuntimeError(run.stderr)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.src = self.root / 'source.png'; self.out = self.root / 'item-ja-v2.png'
        self.pc = self.root / 'item-ja-v2.pcraft'
        image_file(self.src); image_file(self.out)
        # The archive fixture has matching dimensions, without claiming PhotoCraft editability.
        import zipfile
        with zipfile.ZipFile(self.pc, 'w') as z:
            z.writestr('manifest.json', json.dumps({'document': {'size': {'width': 13, 'height': 11}, 'layers': [{'id': 1}]}}))
        self.entry = {'source': str(self.src), 'source_sha256': sha256_file(self.src), 'png': self.out.name, 'pcraft': self.pc.name,
                      'protected': [{'id': 'logo', 'rect': [0, 0, 3, 3]}],
                      'comparison': {'editable': [{'id': 'caption', 'rect': [4, 2, 9, 6]}],
                                     'report': str(self.root / 'qa' / 'report.json')}}

    def scan(self):
        return compare(self.entry, self.root, [str(self.engine)])

    def review(self):
        self.entry.update(photocraft_reopened=True, visual_passed=True,
                          review_hashes=pair_hashes(self.src, self.out, self.pc),
                          review_report_sha256=sha256_file(Path(self.entry['comparison']['report'])),
                          reviewed_editable_ids=[r['id'] for r in self.entry['comparison']['editable']])

    def test_identical_and_delivery(self):
        report = self.scan(); self.assertEqual(report['status'], 'pass')
        self.assertEqual(report['raster']['pixels_scanned'], 143)
        self.assertEqual(report['raster']['protected']['pixels'], 9)
        with self.assertRaises(ValueError): require_delivery(self.entry, self.root)
        self.review(); require_delivery(self.entry, self.root)

    def test_batch_computes_then_resumes_without_rescan(self):
        result = run_batch([self.entry], self.root, lambda: [str(self.engine)])
        self.assertEqual(result[0]['status'], 'needs_review')
        self.assertEqual(result[0]['pixel_check'], 'computed')
        self.review()
        def no_engine():
            raise AssertionError('resume must reuse unchanged report')
        result = run_batch([self.entry], self.root, no_engine)
        self.assertEqual(result[0]['status'], 'ready')
        self.assertEqual(result[0]['pixel_check'], 'reused')

    def test_bottom_right_single_pixel_detected(self):
        image_file(self.out, {(12, 10): (0, 0, 0, 255)})
        report = self.scan()
        self.assertEqual(report['status'], 'fail')
        self.assertEqual(report['raster']['unexpected_pixels'], 1)
        self.assertEqual(report['raster']['unchanged']['violation_bbox'], [12, 10, 13, 11])

    def test_top_left_logo_change_detected(self):
        image_file(self.out, {(0, 0): (0, 0, 0, 255)})
        report = self.scan()
        self.assertEqual(report['raster']['protected_regions'][0]['stats']['violation_bbox'], [0, 0, 1, 1])
        self.review()
        with self.assertRaisesRegex(ValueError, 'comparison failed'): require_delivery(self.entry, self.root)

    def test_allowed_change_still_requires_region_review(self):
        image_file(self.out, {(4, 2): (0, 0, 0, 255)})
        report = self.scan(); self.assertEqual(report['status'], 'pass')
        self.assertEqual(report['raster']['editable']['changed_pixels'], 1)
        self.review(); self.entry['reviewed_editable_ids'] = []
        with self.assertRaisesRegex(ValueError, 'review every editable'): require_delivery(self.entry, self.root)

    def test_protected_edit_overlap_rejected(self):
        self.entry['comparison']['editable'][0]['rect'] = [2, 2, 5, 5]
        with self.assertRaisesRegex(ValueError, 'intersects protection'): self.scan()

    def test_tolerance_is_explicit_and_reported(self):
        image_file(self.out, {(12, 10): (254, 255, 255, 255)})
        self.entry['comparison'].update(channel_tolerance=1, tolerance_reason='synthetic calibration fixture')
        report = self.scan(); self.assertEqual(report['status'], 'pass')
        self.assertEqual(report['raster']['unchanged']['changed_pixels'], 1)
        self.assertEqual(report['raster']['unchanged']['max_channel_delta'], 1)

    def test_invalid_policy(self):
        for tolerance in (-1, 255, True, float('nan'), 1):
            with self.subTest(tolerance=tolerance):
                entry = copy.deepcopy(self.entry); entry['comparison']['channel_tolerance'] = tolerance
                with self.assertRaises(ValueError): policy_for(entry, (13, 11))
        for box in ([0, 0, 0, 1], [-1, 0, 3, 3], [0, 0, 14, 11], [0, 0, 1.5, 3]):
            entry = copy.deepcopy(self.entry); entry['protected'][0]['rect'] = box
            with self.assertRaises(ValueError): policy_for(entry, (13, 11))

    def test_all_editable_cannot_pass(self):
        self.entry['protected'] = []; self.entry['comparison']['editable'][0]['rect'] = [0, 0, 13, 11]
        with self.assertRaisesRegex(ValueError, 'No preserved pixels'): self.scan()

    def test_gray_and_alpha_are_compared(self):
        image_file(self.src, gray=True); self.entry['source_sha256'] = sha256_file(self.src)
        report = self.scan(); self.assertEqual(report['status'], 'pass')
        self.entry['comparison']['report'] = str(self.root / 'qa' / 'alpha.json')
        image_file(self.out, {(12, 10): (255, 255, 255, 0)})
        report = self.scan(); self.assertEqual(report['raster']['unexpected_pixels'], 1)

    def test_stale_files_policy_and_report_block(self):
        self.scan(); self.review()
        original = self.out.read_bytes()
        image_file(self.out, {(4, 2): (0, 0, 0, 255)})
        with self.assertRaisesRegex(ValueError, 'stale review'): require_delivery(self.entry, self.root)
        self.out.write_bytes(original)
        self.entry['comparison']['editable'][0]['rect'][2] = 10
        with self.assertRaisesRegex(ValueError, 'regions/tolerance changed'): require_delivery(self.entry, self.root)
        self.entry['comparison']['editable'][0]['rect'][2] = 9
        path = Path(self.entry['comparison']['report']); path.write_text(path.read_text() + '\n')
        with self.assertRaisesRegex(ValueError, 'changed reviewed'): require_delivery(self.entry, self.root)

    def test_failure_prevents_cleanup_for_entire_set(self):
        old = self.root / 'item-ja-v1.png'; old.write_bytes(b'keep')
        image_file(self.out, {(0, 0): (0, 0, 0, 255)})
        self.scan(); self.review(); self.entry['old_files'] = [old.name]
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaisesRegex(ValueError, 'comparison failed'):
            cleanup(self.root, [self.entry], delete=True)
        self.assertTrue(old.exists())

    def test_successful_cleanup_and_other_language_preserved(self):
        old = self.root / 'item-ja-v1.png'; old.write_bytes(b'old')
        other = self.root / 'item-vi.png'; other.write_bytes(b'keep')
        self.scan(); self.review(); self.entry['old_files'] = [old.name]
        with contextlib.redirect_stdout(io.StringIO()): cleanup(self.root, [self.entry], delete=True)
        self.assertFalse(old.exists()); self.assertTrue(other.exists())

    def test_difference_image_tampering_blocks(self):
        report = self.scan(); self.review()
        Path(report['diff_image']).write_bytes(b'bad')
        with self.assertRaisesRegex(ValueError, 'difference image'): require_delivery(self.entry, self.root)

    def test_no_overwrite_and_dimension_mismatch(self):
        self.scan()
        with self.assertRaisesRegex(ValueError, 'already exists'): self.scan()
        image_file(self.out, width=14)
        with self.assertRaisesRegex(ValueError, 'dimensions'): self.scan()

    def test_cli_check_requires_evidence(self):
        self.scan()
        task = self.root / 'task.json'; task.write_text(json.dumps([self.entry]))
        run = subprocess.run([sys.executable, str(SCRIPTS / 'compare_source.py'), str(task), str(self.root),
                              '--png', self.out.name, '--check'], capture_output=True, text=True)
        self.assertNotEqual(run.returncode, 0)
        self.review(); task.write_text(json.dumps([self.entry]))
        run = subprocess.run([sys.executable, str(SCRIPTS / 'compare_source.py'), str(task), str(self.root),
                              '--png', self.out.name, '--check'], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)


if __name__ == '__main__':
    unittest.main()
