#!/usr/bin/env python3
import argparse
import contextlib
import hashlib
import json
import os
import re
import subprocess
import threading
import zipfile
from pathlib import Path

_scope = threading.local()


@contextlib.contextmanager
def verification_cache():
    """Within one thread, reuse hashes/dimensions/archive checks for files whose stat is unchanged.

    Any rewrite changes inode, size, mtime or ctime and forces recomputation, so the
    before/after change checks keep working. Scope it to one item's checks.
    """
    previous = getattr(_scope, 'memo', None)
    _scope.memo = {} if previous is None else previous
    try:
        yield
    finally:
        _scope.memo = previous


def _memoized(kind, paths, compute):
    memo = getattr(_scope, 'memo', None)
    if memo is None:
        return compute()
    key = [kind]
    for path in paths:
        st = os.stat(path)
        key.append((str(Path(path).resolve()), st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns))
    key = tuple(key)
    if key not in memo:
        memo[key] = compute()
    return memo[key]


def exact_output(root, name):
    if not isinstance(name, str) or Path(name).name != name or name in {'.', '..'} or any(c in name for c in '*?[]\\'):
        raise ValueError(f'expected exact output filename: {name}')
    path = root / name
    if path.is_symlink() or path.suffix.lower() not in {'.png', '.pcraft'}:
        raise ValueError(f'unsupported output or symlink: {name}')
    return path


def sha256_file(path):
    def compute():
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(chunk)
        return digest.hexdigest()
    return _memoized('sha256', [path], compute)


def pair_hashes(source, png, pcraft):
    return {key: sha256_file(path) for key, path in
            [('source', source), ('png', png), ('pcraft', pcraft)]}


def image_size(path):
    def compute():
        output = subprocess.check_output(['sips', '-g', 'pixelWidth', '-g', 'pixelHeight', str(path)], text=True, stderr=subprocess.DEVNULL)
        values = tuple(map(int, re.findall(r'(?:pixelWidth|pixelHeight): (\d+)', output)))
        if len(values) != 2 or min(values) <= 0:
            raise ValueError(f'invalid image dimensions: {path}')
        return values
    return _memoized('size', [path], compute)


def verify_pair(source, png, pcraft):
    for path in (source, png, pcraft):
        if path.is_symlink() or not path.is_file() or path.stat().st_size == 0:
            raise ValueError(f'missing, empty, or symlink file: {path}')
    # Failures raise and are never memoized; a success is reused only for unchanged files.
    _memoized('pair', [source, png, pcraft], lambda: _verify_pair(source, png, pcraft))


def _verify_pair(source, png, pcraft):
    expected = image_size(source)
    if image_size(png) != expected:
        raise ValueError('PNG dimensions differ from source')
    with zipfile.ZipFile(pcraft) as archive:
        if archive.testzip() is not None:
            raise ValueError('PCraft archive checksum failure')
        doc = json.loads(archive.read('manifest.json'))['document']
        size = doc['size']
        if (size['width'], size['height']) != expected:
            raise ValueError('PCraft dimensions differ from source')
        if not isinstance(doc.get('layers'), list) or not doc['layers']:
            raise ValueError('PCraft has no layer tree')


def main():
    parser = argparse.ArgumentParser(description='Check archive integrity and dimensions; not a PhotoCraft reopen or visual test')
    parser.add_argument('source_dir', type=Path)
    parser.add_argument('output_dir', type=Path)
    parser.add_argument('--suffix', required=True, help='Language/version suffix, e.g. -en-v2 or -th-v2')
    parser.add_argument('--hashes', action='store_true', help='Print JSON file fingerprints; does not mark visual review passed')
    parser.add_argument('bases', nargs='+')
    args = parser.parse_args()
    failures = []
    fingerprints = []
    if any(c in args.suffix for c in '/\\*?[]') or not args.suffix.startswith('-'):
        raise SystemExit('suffix must start with a hyphen and contain no path separators or wildcards')
    for base in args.bases:
        try:
            if not base or base in {'.', '..'} or Path(base).name != base or any(c in base for c in '*?[]\\'):
                raise ValueError('base must be an exact filename stem')
            sources = [p for p in args.source_dir.iterdir() if p.stem == base and p.suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp'}]
            if len(sources) != 1:
                raise ValueError('expected exactly one source')
            verify_pair(sources[0], args.output_dir / f'{base}{args.suffix}.png', args.output_dir / f'{base}{args.suffix}.pcraft')
            if args.hashes:
                fingerprints.append({'base': base, 'review_hashes': pair_hashes(
                    sources[0], args.output_dir / f'{base}{args.suffix}.png', args.output_dir / f'{base}{args.suffix}.pcraft')})
        except Exception as error:
            failures.append(f'{base}: {error}')
    if failures:
        raise SystemExit('\n'.join(failures))
    if args.hashes:
        print(json.dumps(fingerprints, indent=2))
    else:
        print(f'Integrity/dimensions passed for {len(args.bases)} pairs; PhotoCraft reopen and visual review still required')


if __name__ == '__main__':
    main()
