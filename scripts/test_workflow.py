#!/usr/bin/env python3
"""Small deterministic regressions; image dimension tests require macOS sips."""
import copy
import contextlib
import io
import json
import struct
import subprocess
import sys
import tempfile
import unittest
import zipfile
import zlib
from pathlib import Path

from check_layout import check
from cleanup_versions import cleanup, exact_output
from compare_source import policy_for, policy_hash
from compare_source import production_hash
from batch_verify import run_batch, check_clean_base
from extract_pcraft_text import walk
from verify_outputs import pair_hashes, sha256_file, verify_pair

SCRIPTS = Path(__file__).resolve().parent


def png(path, width=8, height=8, shade=255):
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    path.write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
                     + chunk(b'IDAT', zlib.compress((b'\0' + bytes([shade] * 3) * width) * height)) + chunk(b'IEND', b''))


def archive(path, width=8, layers=None):
    with zipfile.ZipFile(path, 'w') as out:
        out.writestr('manifest.json', json.dumps({'document': {'size': {'width': width, 'height': 8},
                                                              'layers': [{'id': 1}] if layers is None else layers}}))


class Outputs(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.source, self.png, self.pcraft = [self.root / name for name in ('source.png', 'item-th-v2.png', 'item-th-v2.pcraft')]
        png(self.source); png(self.png); archive(self.pcraft)
        self.old = self.root / 'item-th-v1.png'; self.old.write_bytes(b'old output')
        self.entry = {'source': str(self.source), 'png': self.png.name, 'pcraft': self.pcraft.name,
                      'old_files': [self.old.name], 'photocraft_reopened': True, 'visual_passed': True,
                      'review_hashes': pair_hashes(self.source, self.png, self.pcraft)}
        self.entry.update(source_sha256=sha256_file(self.source), protected=[], reviewed_editable_ids=[],
                          comparison={'editable': [], 'report': str(self.root / 'qa' / 'report.json')})
        # Synthetic gate evidence; real native pixel scanning is covered by test_source_comparison.py.
        qa = self.root / 'qa'; qa.mkdir()
        diff = qa / 'report.diff.png'; png(diff)
        zero = {'pixels': 0, 'changed_pixels': 0, 'above_tolerance_pixels': 0, 'max_channel_delta': 0}
        policy = policy_for(self.entry, (8, 8))
        report = {'schema_version': 1, 'status': 'pass', 'file_hashes': self.entry['review_hashes'],
                  'policy': policy, 'policy_sha256': policy_hash(policy), 'diff_image': str(diff),
                  'diff_sha256': sha256_file(diff),
                  'raster': {'width': 8, 'height': 8, 'pixels_scanned': 64, 'protected': zero,
                             'editable': zero, 'unchanged': dict(zero, pixels=64), 'unexpected_pixels': 0,
                             'protected_regions': [], 'editable_regions': []}}
        path = qa / 'report.json'; path.write_text(json.dumps(report))
        self.entry['review_report_sha256'] = sha256_file(path)

    def clean(self, entries=None, delete=True):
        with contextlib.redirect_stdout(io.StringIO()):
            cleanup(self.root, entries if entries is not None else [self.entry], delete)

    def test_valid_pair(self):
        verify_pair(self.source, self.png, self.pcraft)

    def test_batch_reuses_current_pixel_evidence(self):
        def no_engine():
            raise AssertionError('unchanged evidence must not rerun pixel scanning')
        result = run_batch([self.entry], self.root, no_engine)
        self.assertEqual(result[0]['status'], 'ready')
        self.assertEqual(result[0]['pixel_check'], 'reused')
        self.assertTrue(self.old.exists())

    def test_batch_does_not_approve_visual_review(self):
        self.entry['visual_passed'] = False
        result = run_batch([self.entry], self.root, lambda: [])
        self.assertEqual(result[0]['status'], 'needs_review')
        self.assertFalse(self.entry['visual_passed'])

    def test_batch_continues_after_one_failure(self):
        bad = dict(self.entry, png='missing-en.png', pcraft='missing-en.pcraft')
        result = run_batch([bad, self.entry], self.root, lambda: [])
        self.assertEqual([r['status'] for r in result], ['failed', 'ready'])
        self.assertTrue(self.old.exists())

    def test_production_plan_change_invalidates_reuse(self):
        self.entry.update(production={'renderer': 'test-1', 'fonts': {'Arial': 'test-fingerprint'}},
                          phrases=[{'target_text': 'Hello'}], target_language='en')
        value = production_hash(self.entry)
        self.entry.update(candidate_plan_sha256=value, review_plan_sha256=value)
        self.assertEqual(run_batch([self.entry], self.root, lambda: [])[0]['status'], 'ready')
        self.entry['phrases'][0]['target_text'] = 'Goodbye'
        self.assertEqual(run_batch([self.entry], self.root, lambda: [])[0]['status'], 'failed')
        with self.assertRaisesRegex(ValueError, 'production plan changed'): self.clean()
        self.assertTrue(self.old.exists())

    def test_clean_base_requires_matching_verified_bytes(self):
        task = self.root / 'clean-task.json'; task.write_text(json.dumps([self.entry]))
        variant = dict(self.entry, production={'clean_base': {'task': str(task), 'output_dir': str(self.root),
                                                            'png': self.entry['png'], 'pcraft_sha256': sha256_file(self.pcraft)}})
        check_clean_base(variant)
        variant['production']['clean_base']['pcraft_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'clean base changed'): check_clean_base(variant)

    def test_dry_run_and_exact_cleanup(self):
        other = self.root / 'item-en-approved.png'; other.write_bytes(b'keep')
        self.clean(delete=False); self.assertTrue(self.old.exists())
        self.clean(); self.assertFalse(self.old.exists())
        self.assertTrue(other.exists()); self.assertTrue(self.png.exists()); self.assertTrue(self.source.exists())

    def test_stale_file_refuses_deletion(self):
        for key in ('source', 'png', 'pcraft'):
            with self.subTest(key=key):
                path = getattr(self, key); data = path.read_bytes()
                if key == 'pcraft':
                    archive(path, layers=[{'id': 2}])
                else:
                    png(path, shade=240)
                with self.assertRaisesRegex(ValueError, 'stale review'):
                    self.clean()
                self.assertTrue(self.old.exists()); path.write_bytes(data)

    def test_old_boolean_only_record_refuses_deletion(self):
        self.entry.pop('review_hashes')
        with self.assertRaisesRegex(ValueError, 'stale review'):
            self.clean()
        self.assertTrue(self.old.exists())

    def test_review_not_passed(self):
        self.entry['visual_passed'] = False
        with self.assertRaises(ValueError): self.clean()
        self.assertTrue(self.old.exists())

    def test_corrupt_archive(self):
        self.pcraft.write_bytes(b'bad')
        with self.assertRaises(zipfile.BadZipFile): self.clean()
        self.assertTrue(self.old.exists())

    def test_dimensions_and_empty_layers(self):
        for kwargs in ({'width': 9}, {'layers': []}):
            with self.subTest(kwargs=kwargs):
                archive(self.pcraft, **kwargs)
                with self.assertRaises(ValueError): verify_pair(self.source, self.png, self.pcraft)
        archive(self.pcraft); png(self.png, width=9)
        with self.assertRaises(ValueError): verify_pair(self.source, self.png, self.pcraft)

    def test_sources_and_replacements_protected(self):
        for path in (self.source, self.png, self.pcraft):
            self.entry['old_files'] = [path.name]
            with self.assertRaisesRegex(ValueError, 'source or replacement'): self.clean()
            self.assertTrue(path.exists())

    def test_all_entries_checked_before_deleting(self):
        bad = dict(self.entry, visual_passed=False)
        with self.assertRaises(ValueError): self.clean([self.entry, bad])
        self.assertTrue(self.old.exists())

    def test_cross_entry_source_protection(self):
        other_source = self.root / 'source-two.png'; png(other_source)
        a = dict(self.entry, old_files=[other_source.name])
        b = dict(self.entry, source=str(other_source), old_files=[])
        b['review_hashes'] = pair_hashes(other_source, self.png, self.pcraft)
        with self.assertRaisesRegex(ValueError, 'source or replacement'): self.clean([a, b])
        self.assertTrue(other_source.exists())

    def test_no_paths_globs_or_symlinks(self):
        for name in ('../x.png', '/tmp/x.png', '*.png', 'x\\y.png'):
            with self.assertRaises(ValueError): exact_output(self.root, name)
        link = self.root / 'link.png'; link.symlink_to(self.old)
        with self.assertRaises(ValueError): exact_output(self.root, link.name)

    def test_missing_comparison_blocks_cleanup(self):
        self.entry.pop('comparison')
        with self.assertRaises(KeyError): self.clean()
        self.assertTrue(self.old.exists())

    def test_changed_comparison_report_blocks_cleanup(self):
        report = Path(self.entry['comparison']['report'])
        report.write_text(report.read_text() + '\n')
        with self.assertRaisesRegex(ValueError, 'changed reviewed'): self.clean()
        self.assertTrue(self.old.exists())

    def test_hashes_cli_and_invalid_suffix(self):
        cmd = [sys.executable, str(SCRIPTS / 'verify_outputs.py'), str(self.root), str(self.root)]
        # Source and output stems must differ; use the existing source as the CLI base.
        png(self.root / 'source-ja-v2.png'); archive(self.root / 'source-ja-v2.pcraft')
        result = subprocess.run(cmd + ['--suffix=-ja-v2', '--hashes', 'source'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(json.loads(result.stdout)[0]['review_hashes']['png']), 64)
        result = subprocess.run(cmd + ['--suffix=-x/../../oops', 'source'], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)

    def test_pre_repair_cli_without_layout(self):
        # No layout key at all: pre-repair must still run, using the 8x8 source dimensions.
        task = self.root / 'task.json'
        entry = {'source': str(self.source), 'source_sha256': sha256_file(self.source), 'png': self.png.name,
                 'pcraft': self.pcraft.name, 'protected': [{'id': 'logo', 'rect': [0, 0, 3, 3]}],
                 'repairs': [{'id': 'cap', 'rect': [4, 4, 7, 7], 'effect_margin_px': 0}]}
        task.write_text(json.dumps([entry]))
        cmd = [sys.executable, str(SCRIPTS / 'check_layout.py'), str(task), str(self.root),
               '--png', self.png.name, '--phase', 'pre-repair']
        result = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('pre-repair geometry passed', result.stdout)
        # A repair whose feather reaches the logo is reported.
        entry['repairs'] = [{'id': 'cap', 'rect': [3, 3, 7, 7], 'effect_margin_px': 1}]
        task.write_text(json.dumps([entry]))
        self.assertNotEqual(subprocess.run(cmd, capture_output=True, text=True).returncode, 0)

    def test_stale_geometry_snapshot_cli(self):
        task = self.root / 'task.json'; snapshot = self.root / 'snapshot.json'
        entry = dict(self.entry, source_sha256=sha256_file(self.source), layout={'canvas': [8, 8]},
                     type_snapshot=str(snapshot))
        snapshot.write_text(json.dumps({'pcraft_sha256': '0' * 64, 'types': []}))
        task.write_text(json.dumps([entry]))
        result = subprocess.run([sys.executable, str(SCRIPTS / 'check_layout.py'), str(task), str(self.root),
                                 '--png', self.png.name], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('stale type.info', result.stderr)


class Layout(unittest.TestCase):
    def setUp(self):
        style = {'font_family': 'Example', 'size_pt': 20, 'weight': 700, 'color': {'mode': 'Rgb', 'c': [0, 0, 0, 0], 'alpha': 1},
                 'leading_pt': 26, 'horizontal_scale': 1, 'vertical_scale': 1}
        group = {'id': 'footer', 'grid': {'rect': [0, 0, 400, 100], 'columns': 4, 'gap_px': 0},
                 'align': 'center', 'baseline_y': 40, 'padding_px': 10, 'min_size_pt': 18,
                 'style': style, 'items': [{'layer': i, 'column': i} for i in range(4)]}
        self.entry = {'layout': {'canvas': [400, 200], 'groups': [group], 'tolerance_px': 2},
                      'protected': [{'id': 'logo', 'rect': [0, 140, 80, 200]}],
                      'repairs': [{'id': 'old-title', 'rect': [150, 140, 200, 170], 'effect_margin_px': 2}]}
        self.infos = [{'layer': i, 'text': 'AB\nC', 'orientation': 'Horizontal', 'warp': None,
                       'transform': [1, 0, 0, 1, 50 + i * 100, 40],
                       'bounds': [30 + i * 100, 20, 70 + i * 100, 70],
                       'runs': [{'style': copy.deepcopy(style)}],
                       'lines': [{'start': 0, 'end': 2, 'x0': -20, 'x1': 20, 'baseline': 0},
                                 {'start': 3, 'end': 4, 'x0': -10, 'x1': 10, 'baseline': 26}]} for i in range(4)]

    def test_equal_columns_and_centered_multiline(self):
        self.assertEqual(check(self.entry, self.infos), [])
        self.assertEqual(check(self.entry, phase='pre-repair'), [])

    def test_second_line_alignment(self):
        self.infos[1]['lines'][1].update(x0=-20, x1=0)
        self.assertTrue(any('alignment' in x for x in check(self.entry, self.infos)))

    def test_last_column_overflow(self):
        self.infos[3]['bounds'][2] = 420
        self.assertTrue(any('outside cell' in x for x in check(self.entry, self.infos)))

    def test_font_size_and_scale(self):
        self.infos[1]['runs'][0]['style']['size_pt'] = 17
        self.infos[2]['transform'][0] = .8
        issues = check(self.entry, self.infos)
        self.assertTrue(any('style mismatch size_pt' in x for x in issues))
        self.assertTrue(any('scaled text' in x for x in issues))

    def test_group_below_readable_minimum(self):
        self.entry['layout']['groups'][0]['min_size_pt'] = 22
        self.assertTrue(any('readable minimum' in x for x in check(self.entry, self.infos)))

    def test_repair_margin_protects_logo(self):
        self.entry['repairs'][0].update(rect=[82, 145, 110, 160], effect_margin_px=4)
        self.assertTrue(any('protected logo' in x for x in check(self.entry, phase='pre-repair')))

    def test_pre_repair_without_layout_groups(self):
        # A photo/single-headline item carries no layout.groups (even no layout); pre-repair
        # takes the canvas from the source dimensions rather than requiring layout.canvas.
        entry = {'source': '/x.jpg', 'protected': [{'id': 'logo', 'rect': [0, 140, 80, 200]}],
                 'repairs': [{'id': 'old-title', 'rect': [150, 140, 200, 170], 'effect_margin_px': 2}]}
        self.assertEqual(check(entry, phase='pre-repair', canvas_size=[400, 200]), [])
        reaching = dict(entry, repairs=[{'id': 'edge', 'rect': [150, 140, 200, 170], 'effect_margin_px': 40}])
        self.assertTrue(any('outside canvas' in x for x in check(reaching, phase='pre-repair', canvas_size=[400, 200])))
        self.assertTrue(any('protected' in x for x in check(
            dict(entry, repairs=[{'id': 'r', 'rect': [60, 150, 110, 170], 'effect_margin_px': 4}]),
            phase='pre-repair', canvas_size=[400, 200])))

    def test_text_overlap_and_baseline(self):
        self.infos[1]['bounds'] = self.infos[0]['bounds'][:]
        self.infos[2]['transform'][5] += 12
        issues = check(self.entry, self.infos)
        self.assertTrue(any('overlaps text' in x for x in issues))
        self.assertTrue(any('baseline' in x for x in issues))

    def test_missing_or_invalid_evidence(self):
        self.assertTrue(any('missing type.info' in x for x in check(self.entry, self.infos[:-1])))
        self.infos[0]['bounds'][0] = float('nan')
        with self.assertRaises(ValueError): check(self.entry, self.infos)

    def test_protected_text_and_font_warning(self):
        self.entry['protected'] = [{'id': 'logo', 'rect': [30, 20, 40, 40]}]
        self.infos[1]['warnings'] = ['Missing font']
        issues = check(self.entry, self.infos)
        self.assertTrue(any('overlaps protected logo' in x for x in issues))
        self.assertTrue(any('renderer warnings' in x for x in issues))

    def test_extraction_preserves_runs_and_hidden_ancestors(self):
        content = {'kind': 'text', 'text': 'Đỏ', 'runs': [{'len': 5, 'style': {'size_pt': 22}}],
                   'transform': {'m': [1, 0, 0, 1, 0, 0]}}
        rows = list(walk([{'id': 9, 'visible': False, 'content': {'children': [{'id': 10, 'content': content}]}}]))
        self.assertFalse(rows[0]['visible']); self.assertEqual(rows[0]['parents'], (9,))
        self.assertEqual(rows[0]['runs'], content['runs'])


if __name__ == '__main__':
    unittest.main()
