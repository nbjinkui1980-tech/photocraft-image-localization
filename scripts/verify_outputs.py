#!/usr/bin/env python3
import argparse
import json
import re
import subprocess
import zipfile
from pathlib import Path


def image_size(path):
    output = subprocess.check_output(['sips', '-g', 'pixelWidth', '-g', 'pixelHeight', str(path)], text=True, stderr=subprocess.DEVNULL)
    values = tuple(map(int, re.findall(r'(?:pixelWidth|pixelHeight): (\d+)', output)))
    if len(values) != 2 or min(values) <= 0:
        raise ValueError(f'invalid image dimensions: {path}')
    return values


def verify_pair(source, png, pcraft):
    for path in (source, png, pcraft):
        if path.is_symlink() or not path.is_file() or path.stat().st_size == 0:
            raise ValueError(f'missing, empty, or symlink file: {path}')
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
    parser.add_argument('bases', nargs='+')
    args = parser.parse_args()
    failures = []
    for base in args.bases:
        try:
            if Path(base).name != base or any(c in base for c in '*?[]'):
                raise ValueError('base must be an exact filename stem')
            sources = [p for p in args.source_dir.iterdir() if p.stem == base and p.suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp'}]
            if len(sources) != 1:
                raise ValueError('expected exactly one source')
            verify_pair(sources[0], args.output_dir / f'{base}{args.suffix}.png', args.output_dir / f'{base}{args.suffix}.pcraft')
        except Exception as error:
            failures.append(f'{base}: {error}')
    if failures:
        raise SystemExit('\n'.join(failures))
    print(f'Integrity/dimensions passed for {len(args.bases)} pairs; PhotoCraft reopen and visual review still required')


if __name__ == '__main__':
    main()
