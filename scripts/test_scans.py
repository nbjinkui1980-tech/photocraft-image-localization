#!/usr/bin/env python3
"""Regression checks for scan coverage and argument validation; macOS/Swift required."""
import subprocess
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent


def run(*args):
    return subprocess.run(list(map(str, args)), capture_output=True, text=True, timeout=60)


def main():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        fixture = root / 'fixture.swift'
        fixture.write_text('''import AppKit
let dir = CommandLine.arguments[1]
for (name, width, height, kind) in [("source",100,100,0),("right",100,100,1),("bottom",100,100,2),("tiny",3,3,0)] {
 let r = NSBitmapImageRep(bitmapDataPlanes:nil,pixelsWide:width,pixelsHigh:height,bitsPerSample:8,samplesPerPixel:4,hasAlpha:true,isPlanar:false,colorSpaceName:.deviceRGB,bytesPerRow:0,bitsPerPixel:0)!
 for y in 0..<height { for x in 0..<width {
   let value = (kind == 1 && x >= 96) || (kind == 2 && y >= 96) ? 0.96 : 1.0
   r.setColor(NSColor(deviceRed:value,green:value,blue:value,alpha:1),atX:x,y:y)
 } }
 try r.representation(using:.png,properties:[:])!.write(to:URL(fileURLWithPath:dir + "/" + name + ".png"))
}
''')
        result = run('swift', fixture, root)
        assert result.returncode == 0, result.stderr
        # Compile once; exercise the real script entry points repeatedly.
        for name in ('diff_scan', 'find_dark'):
            result = run('swiftc', SCRIPTS / f'{name}.swift', '-o', root / name)
            assert result.returncode == 0, result.stderr
        source = root / 'source.png'
        for side in ('right', 'bottom'):
            result = run(root / 'diff_scan', source, root / f'{side}.png')
            assert result.returncode == 0 and 'suspect cells (' in result.stdout, result.stdout + result.stderr
            assert ('x=96' if side == 'right' else 'y=96') in result.stdout, result.stdout
        result = run(root / 'diff_scan', root / 'tiny.png', root / 'tiny.png')
        assert result.returncode == 0 and 'no suspect' in result.stdout, result.stderr
        for params in [('0',), ('abc',), ('48', 'nan'), ('48', '30', '20')]:
            assert run(root / 'diff_scan', source, source, *params).returncode != 0
        for rect in [('0','0','0','10'),('0','0','-1','10'),('-1','0','10','10'),('99','0','2','10'),('100','0','1','1')]:
            result = run(root / 'find_dark', source, *rect)
            assert result.returncode == 1, result.stderr
        for threshold in ('nan','256','-1','abc'):
            assert run(root / 'find_dark', source, 0, 0, 1, 1, threshold).returncode == 1
        result = run(root / 'find_dark', root / 'right.png', 96, 0, 4, 100, 250)
        assert result.returncode == 0 and 'darkPixels=400' in result.stdout and 'scannedPixels=400' in result.stdout, result.stdout
        result = run(root / 'find_dark', source, 0, 0, 100, 100)
        assert result.returncode == 0 and 'darkPixels=0' in result.stdout and 'scannedPixels=10000' in result.stdout
    print('PASS: right/bottom edge coverage, tiny images, invalid parameters, exact pixel counts, clean image')


if __name__ == '__main__':
    main()
