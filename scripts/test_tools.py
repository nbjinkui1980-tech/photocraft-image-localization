#!/usr/bin/env python3
"""Regressions for the speed/bookkeeping tools: swift_tool cache, verification cache,
parallel batch_verify, task_tool and review_sheet. Requires macOS and Swift."""
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zipfile
import zlib
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parent
CACHE = tempfile.TemporaryDirectory(prefix='photocraft-tool-cache-')
os.environ['PHOTOCRAFT_TOOL_CACHE'] = CACHE.name  # isolate before importing the tools

import swift_tool  # noqa: E402
import verify_outputs  # noqa: E402
from batch_verify import run_batch  # noqa: E402
from compare_source import compare, require_delivery  # noqa: E402
from review_sheet import build  # noqa: E402
from test_source_comparison import image_file  # noqa: E402
from verify_outputs import sha256_file, verification_cache, verify_pair  # noqa: E402


def read_png(path):
    """Minimal decoder for 8-bit RGB/RGBA non-interlaced PNGs; returns (w, h, rows of tuples)."""
    data = path.read_bytes()
    pos, idat, header = 8, b'', None
    while pos < len(data):
        length, kind = struct.unpack('>I4s', data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + length]
        if kind == b'IHDR':
            header = struct.unpack('>IIBBBBB', body)
        elif kind == b'IDAT':
            idat += body
        pos += 12 + length
    w, h, depth, color, _, _, interlace = header
    assert depth == 8 and color in (2, 6) and interlace == 0, header
    bpp = 4 if color == 6 else 3
    raw, stride, rows, prev = zlib.decompress(idat), w * bpp, [], bytearray(w * bpp)
    for y in range(h):
        kind, line = raw[y * (stride + 1)], bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for i in range(stride):
            a = line[i - bpp] if i >= bpp else 0
            b, c = prev[i], prev[i - bpp] if i >= bpp else 0
            if kind == 1: line[i] = (line[i] + a) & 255
            elif kind == 2: line[i] = (line[i] + b) & 255
            elif kind == 3: line[i] = (line[i] + (a + b) // 2) & 255
            elif kind == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        rows.append([tuple(line[x * bpp:x * bpp + 3]) for x in range(w)])
        prev = line
    return w, h, rows


def pcraft(path, width, height):
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('manifest.json', json.dumps({'document': {'size': {'width': width, 'height': height},
                                                                   'layers': [{'id': 1}]}}))


def task_tool(*args):
    return subprocess.run([sys.executable, SCRIPTS / 'task_tool.py', *map(str, args)], capture_output=True, text=True)


class SwiftToolCache(unittest.TestCase):
    def test_compiles_once_and_rebuilds_on_change(self):
        first = swift_tool.binary('find_dark')
        stamp = first.stat().st_mtime_ns
        self.assertEqual(swift_tool.binary('find_dark'), first)
        self.assertEqual(first.stat().st_mtime_ns, stamp)
        with tempfile.TemporaryDirectory() as directory:
            copy = Path(directory) / 'find_dark.swift'
            copy.write_text((SCRIPTS / 'find_dark.swift').read_text() + '\n// changed\n')
            self.assertNotEqual(swift_tool.binary('find_dark', copy), first)

    def test_cli_runs_helper(self):
        with tempfile.TemporaryDirectory() as directory:
            src = Path(directory) / 's.png'
            image_file(src, None, 20, 20)
            run = subprocess.run([sys.executable, SCRIPTS / 'swift_tool.py', 'classify_baseline', src, src],
                                 capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(json.loads(run.stdout)['verdict'], 'preserved')
        self.assertNotEqual(subprocess.run([sys.executable, SCRIPTS / 'swift_tool.py', 'nope'],
                                           capture_output=True, text=True).returncode, 0)


class Fixture(unittest.TestCase):
    W, H = 300, 200

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        (self.root / 'src').mkdir(); (self.root / 'out').mkdir()
        self.out = self.root / 'out'

    def tearDown(self):
        self.tmp.cleanup()

    def item(self, name='item', lang='en', edits=None):
        src = self.root / 'src' / f'{name}.png'
        if not src.exists():
            image_file(src, None, self.W, self.H)
        png = self.out / f'{name}-{lang}-v2.png'
        image_file(png, edits if edits is not None else {(x, y): (200, 30, 30, 255) for x in range(20, 40) for y in range(10, 20)},
                   self.W, self.H)
        pcraft(self.out / f'{name}-{lang}-v2.pcraft', self.W, self.H)
        return {'source': str(src), 'source_sha256': sha256_file(src), 'target_language': lang,
                'png': png.name, 'pcraft': f'{name}-{lang}-v2.pcraft', 'protected': [{'id': 'logo', 'rect': [250, 150, 290, 190]}],
                'comparison': {'editable': [{'id': 'title', 'rect': [16, 8, 44, 22]}], 'channel_tolerance': 0,
                               'report': str(self.root / 'qa' / f'{name}-{lang}.json')},
                'reviewed_editable_ids': [], 'issues': [], 'photocraft_reopened': False, 'visual_passed': False}


class VerificationCache(Fixture):
    def test_reuses_unchanged_and_rechecks_changed(self):
        entry = self.item()
        files = (Path(entry['source']), self.out / entry['png'], self.out / entry['pcraft'])
        original = zipfile.ZipFile.testzip
        with mock.patch.object(zipfile.ZipFile, 'testzip', autospec=True, side_effect=original) as calls:
            with verification_cache():
                for _ in range(3):
                    verify_pair(*files)
                self.assertEqual(calls.call_count, 1)
                pcraft(files[2], self.W, self.H + 1)  # rewrite: different stat, now invalid
                with self.assertRaises(ValueError):
                    verify_pair(*files)
            pcraft(files[2], self.W, self.H)
            verify_pair(*files); verify_pair(*files)  # outside a scope nothing is cached
            self.assertEqual(calls.call_count, 4)

    def test_hash_recomputed_after_rewrite(self):
        path = self.root / 'f.png'
        path.write_bytes(b'a')
        with verification_cache():
            first = sha256_file(path)
            path.write_bytes(b'b')
            self.assertNotEqual(sha256_file(path), first)


class ParallelBatch(Fixture):
    def test_parallel_matches_serial(self):
        entries = [self.item(f'i{n}') for n in range(6)]
        entries[2]['pcraft'] = 'missing.pcraft'
        entries[4]['comparison']['editable'] = []  # red block now falls outside: pixel failure
        engine = lambda: swift_tool.command('compare_pixels')
        parallel = run_batch(entries, self.out, engine, jobs=4)
        for entry in entries:
            report = Path(entry['comparison']['report'])
            report.unlink(missing_ok=True); report.with_suffix('.diff.png').unlink(missing_ok=True)
        serial = run_batch(entries, self.out, engine, jobs=1)
        strip = lambda rows: [(r['png'], r['status'], r.get('pixel_check')) for r in rows]
        self.assertEqual(strip(parallel), strip(serial))
        self.assertEqual([r['status'] for r in parallel],
                         ['needs_review', 'needs_review', 'failed', 'needs_review', 'failed', 'needs_review'])
        reused = run_batch(entries, self.out, lambda: self.fail('no recompute expected'), jobs=4)
        self.assertEqual([r.get('pixel_check') for r in reused if r['status'] != 'failed'], ['reused'] * 4)


class TaskTool(Fixture):
    def test_init_detects_versions_and_is_idempotent(self):
        image_file(self.root / 'src' / 'a.png', None, 30, 20)
        image_file(self.root / 'src' / 'b.jpg.png', None, 30, 20)
        for name in ('a-en-v1.png', 'a-en-v1.pcraft', 'a-vi-v1.png', 'a-en-v2.png', 'a-en-v10x.png', 'b.jpg-en-v1.png'):
            (self.out / name).write_bytes(b'x')
        task = self.root / 'task.json'
        run = task_tool('init', task, self.root / 'src', self.out, self.root / 'qa', '--langs', 'en,vi', '--version', 'v2')
        self.assertEqual(run.returncode, 0, run.stderr)
        entries = json.loads(task.read_text())
        self.assertEqual(len(entries), 4)
        by = {e['png']: e for e in entries}
        self.assertEqual(by['a-en-v2.png']['old_files'], ['a-en-v1.pcraft', 'a-en-v1.png'])
        self.assertEqual(by['a-vi-v2.png']['old_files'], ['a-vi-v1.png'])
        self.assertEqual(by['b.jpg-en-v2.png']['old_files'], ['b.jpg-en-v1.png'])
        self.assertEqual(by['a-en-v2.png']['layout']['canvas'], [30, 20])
        self.assertEqual(len({e['comparison']['report'] for e in entries}), 4)
        self.assertTrue(all(Path(e['source']).is_absolute() and e['source_sha256'] for e in entries))
        run = task_tool('init', task, self.root / 'src', self.out, self.root / 'qa', '--langs', 'en,vi,th', '--version', 'v2')
        self.assertEqual(json.loads(run.stdout)['added'], 2)
        self.assertEqual(len(json.loads(task.read_text())), 6)
        for bad in (('--langs', 'en', '--version', '2'), ('--langs', 'e n', '--version', 'v2')):
            self.assertNotEqual(task_tool('init', task, self.root / 'src', self.out, self.root / 'qa', *bad).returncode, 0)
        self.assertNotEqual(task_tool('init', task, self.root / 'src', self.out, self.out,
                                      '--langs', 'en', '--version', 'v2').returncode, 0)

    def test_fresh_report(self):
        entry = self.item()
        entry['review_report_sha256'] = 'old'
        task = self.root / 'task.json'
        task.write_text(json.dumps([entry]))
        Path(entry['comparison']['report']).parent.mkdir()
        run = task_tool('fresh-report', task, '--png', entry['png'])
        self.assertEqual(run.returncode, 0, run.stderr)
        new = json.loads(task.read_text())[0]
        self.assertNotEqual(new['comparison']['report'], entry['comparison']['report'])
        self.assertNotIn('review_report_sha256', new)
        Path(new['comparison']['report']).write_text('{}')
        again = task_tool('fresh-report', task, '--png', entry['png']).stdout.strip()
        self.assertNotEqual(again, new['comparison']['report'])


class ReviewFlow(Fixture):
    def prepare(self, entry=None):
        self.entry = entry or self.item()
        self.task = self.root / 'task.json'
        self.task.write_text(json.dumps([self.entry]))
        self.assertEqual(compare(self.entry, self.out)['status'], 'pass')
        self.manifest = build(self.entry, self.out, self.root / 'qa' / 'review-1', page=256, display_width=200)

    def record(self, *extra):
        return task_tool('record-review', self.task, self.out, '--png', self.entry['png'],
                         '--before', self.root / 'qa' / 'review-1' / 'review.json', *extra)

    def test_full_review_records_and_passes_gate(self):
        self.prepare()
        run = self.record('--reviewed-ids', 'all', '--reopened', '--visual-passed')
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)['status'], 'delivery gate passed')
        saved = json.loads(self.task.read_text())[0]
        require_delivery(saved, self.out)
        self.assertEqual(saved['reviewed_editable_ids'], ['title'])

    def test_refusals(self):
        self.prepare()
        self.assertIn('requires --reopened', self.record('--reviewed-ids', 'all', '--visual-passed').stderr)
        self.assertIn('unknown editable', self.record('--reviewed-ids', 'nope', '--reopened', '--visual-passed').stderr)
        partial = self.record('--reviewed-ids', '', '--reopened', '--visual-passed')
        self.assertNotEqual(partial.returncode, 0)  # gate demands every editable region reviewed
        self.assertIn('review every editable region', partial.stderr)
        self.assertFalse(json.loads(self.task.read_text())[0]['visual_passed'])  # nothing written
        run = self.record('--reviewed-ids', 'all', '--issue', 'seam under title')
        self.assertEqual(json.loads(run.stdout)['status'], 'recorded (not delivered)')
        self.assertIn('unresolved issues', self.record('--reviewed-ids', 'all', '--reopened', '--visual-passed').stderr)
        self.assertEqual(self.record('--reviewed-ids', 'all', '--reopened', '--visual-passed', '--clear-issues').returncode, 0)
        image_file(self.out / self.entry['png'], {(0, 0): (0, 0, 0, 255)}, self.W, self.H)  # edit after review pages
        self.assertIn('files changed since', self.record('--reviewed-ids', 'all', '--reopened', '--visual-passed').stderr)

    def test_review_sheet_is_exact_and_tiled(self):
        entry = self.item(edits={(x, y): ((x * 7) % 256, (y * 5) % 256, 99, 255) for x in range(0, 300) for y in range(40, 60)})
        entry['comparison']['editable'] = [{'id': 'wide', 'rect': [0, 40, 300, 60]}]
        self.prepare(entry)
        pages = [Path(p) for p in self.manifest['pages']]
        self.assertTrue(all(p.is_file() for p in pages))
        self.assertEqual(self.manifest['file_hashes']['png'], sha256_file(self.out / entry['png']))
        # page 256 -> tiles at most 232 px wide, so a 300 px region (+context) splits in two.
        w, h, rows = read_png(pages[0])
        first_tile_w = 150
        candidate_top = 12 + 18 + (60 + 16 - 24) + 4 + 18  # gutter+label, source tile (y 24..76), gap, label
        for dx in (0, 5, 149):
            for dy in (16, 20, 35):  # tile rows map to source y = 24 + dy
                self.assertEqual(rows[candidate_top + dy][12 + dx], ((dx * 7) % 256, ((24 + dy) * 5) % 256, 99))
        self.assertGreaterEqual(w, 12 + first_tile_w)
        self.assertTrue(Path(self.manifest['overview']['file']).is_file())
        with self.assertRaises(ValueError):  # never reuse a review directory
            build(entry, self.out, self.root / 'qa' / 'review-1')

    def test_sheet_requires_current_report(self):
        entry = self.item()
        with self.assertRaises(ValueError):
            build(entry, self.out, self.root / 'qa' / 'r')
        compare(entry, self.out)
        image_file(self.out / entry['png'], None, self.W, self.H)
        with self.assertRaises(ValueError):
            build(entry, self.out, self.root / 'qa' / 'r2')


if __name__ == '__main__':
    try:
        unittest.main()
    finally:
        CACHE.cleanup()
