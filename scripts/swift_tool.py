#!/usr/bin/env python3
"""Compile Swift helpers once with -O and reuse the binary across runs.

Cache key: helper source bytes + swiftc version, so editing a helper or upgrading
the toolchain recompiles automatically. Cache root: $PHOTOCRAFT_TOOL_CACHE or
~/.cache/photocraft-image-localization. Run a helper:

    python3 scripts/swift_tool.py repairmap SOURCE V1PNG 0 1 2

which is equivalent to `swift scripts/repairmap.swift ...`, about 4-5x faster on
large images and without per-call compilation.
"""
import hashlib
import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
_lock = threading.Lock()
_version = None


def cache_root():
    return Path(os.environ.get('PHOTOCRAFT_TOOL_CACHE') or Path.home() / '.cache' / 'photocraft-image-localization')


def compiler_version():
    global _version
    if _version is None:
        _version = subprocess.run(['swiftc', '--version'], capture_output=True, text=True, check=True).stdout
    return _version


def binary(name, source=None):
    """Return the path of an optimized binary for scripts/NAME.swift (or SOURCE), compiling on first use."""
    source = Path(source) if source else SCRIPTS / f'{name}.swift'
    if not source.is_file():
        raise ValueError(f'unknown Swift helper: {source}')
    digest = hashlib.sha256(source.read_bytes() + compiler_version().encode()).hexdigest()[:20]
    root = cache_root()
    target = root / f'{source.stem}-{digest}'
    with _lock:
        if target.is_file() and os.access(target, os.X_OK):
            return target
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='build-', dir=root) as temp:
            built = Path(temp) / source.stem
            run = subprocess.run(['swiftc', '-O', '-module-cache-path', str(root / 'module-cache'),
                                  str(source), '-o', str(built)], capture_output=True, text=True)
            if run.returncode:
                raise ValueError(f'{source.name} failed to compile: {run.stderr.strip()}')
            os.replace(built, target)  # atomic: concurrent runs never see a partial binary
    return target


def command(name):
    return [str(binary(name))]


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    try:
        path = binary(sys.argv[1])
    except (ValueError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error))
    os.execv(str(path), [str(path), *sys.argv[2:]])


if __name__ == '__main__':
    main()
