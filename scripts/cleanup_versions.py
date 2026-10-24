#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
from verify_outputs import exact_output, pair_hashes, verify_pair
from compare_source import require_delivery


def cleanup(root, entries, delete=False):
    root = root.resolve(strict=True)
    if not isinstance(entries, list) or not entries:
        raise ValueError('manifest must be a non-empty list')
    protected, targets, replacements = set(), set(), []
    for entry in entries:
        source = Path(entry['source'])
        if not source.is_absolute():
            raise ValueError('source path must be absolute')
        png = exact_output(root, entry['png'])
        pcraft = exact_output(root, entry['pcraft'])
        if png.suffix != '.png' or pcraft.suffix != '.pcraft' or png.stem != pcraft.stem:
            raise ValueError('replacement must be a matching PNG/PCraft pair')
        verify_pair(source, png, pcraft)
        if delete:
            if entry.get('photocraft_reopened') is not True or entry.get('visual_passed') is not True:
                raise ValueError('record successful PhotoCraft reopen and visual review before deletion')
            hashes = entry.get('review_hashes')
            if hashes != pair_hashes(source, png, pcraft):
                raise ValueError(f'missing or stale review hashes: {png.name}; repeat review')
            require_delivery(entry, root)
            replacements.append((source, png, pcraft, hashes, entry))
        protected.update((source.resolve(), png.resolve(), pcraft.resolve()))
        if not isinstance(entry['old_files'], list):
            raise ValueError('old_files must be an exact filename list')
        for name in entry['old_files']:
            old = exact_output(root, name)
            if not old.is_file():
                raise ValueError(f'old file missing: {name}')
            targets.add(old)
    if targets & protected:
        raise ValueError('cleanup list includes a source or replacement')
    for path in sorted(targets):
        print(path)
    if delete:
        # Recheck the entire batch before the first unlink; stop editing during cleanup.
        for source, png, pcraft, hashes, entry in replacements:
            verify_pair(source, png, pcraft)
            if pair_hashes(source, png, pcraft) != hashes:
                raise ValueError('replacement changed during cleanup preparation')
            require_delivery(entry, root)
        for path in sorted(targets):
            path.unlink()
    print('deleted' if delete else 'would delete', len(targets), 'explicitly listed files')


def main():
    parser = argparse.ArgumentParser(description='Exact-list cleanup; dry run unless --delete')
    parser.add_argument('output_dir', type=Path)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--delete', action='store_true')
    args = parser.parse_args()
    entries = json.loads(args.manifest.read_text())
    cleanup(args.output_dir, entries, args.delete)


if __name__ == '__main__':
    main()
