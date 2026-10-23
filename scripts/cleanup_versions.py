#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
from verify_outputs import verify_pair


def exact_output(root, name):
    if not isinstance(name, str) or Path(name).name != name or name in {'.', '..'} or any(c in name for c in '*?[]\\'):
        raise ValueError(f'expected exact output filename: {name}')
    path = root / name
    if path.is_symlink() or path.suffix.lower() not in {'.png', '.pcraft'}:
        raise ValueError(f'unsupported output or symlink: {name}')
    return path


def main():
    parser = argparse.ArgumentParser(description='Exact-list cleanup; dry run unless --delete')
    parser.add_argument('output_dir', type=Path)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--delete', action='store_true')
    args = parser.parse_args()
    root = args.output_dir.resolve(strict=True)
    entries = json.loads(args.manifest.read_text())
    protected, targets = set(), set()
    for entry in entries:
        source = Path(entry['source']).absolute()
        png = exact_output(root, entry['png'])
        pcraft = exact_output(root, entry['pcraft'])
        if png.suffix != '.png' or pcraft.suffix != '.pcraft' or png.stem != pcraft.stem:
            raise ValueError('replacement must be a matching PNG/PCraft pair')
        verify_pair(source, png, pcraft)
        if args.delete and (entry.get('photocraft_reopened') is not True or entry.get('visual_passed') is not True):
            raise ValueError('record successful PhotoCraft reopen and visual review before deletion')
        protected.update((source.resolve(), png.resolve(), pcraft.resolve()))
        for name in entry['old_files']:
            old = exact_output(root, name)
            if not old.is_file():
                raise ValueError(f'old file missing: {name}')
            targets.add(old)
    if targets & protected:
        raise ValueError('cleanup list includes a source or replacement')
    for path in sorted(targets):
        print(path)
    if args.delete:
        for path in sorted(targets):
            path.unlink()
    print('deleted' if args.delete else 'would delete', len(targets), 'explicitly listed files')


if __name__ == '__main__':
    main()
