#!/usr/bin/env swift
// find_dark.swift <image> <x> <y> <w> <h> [lumThreshold=180] — report dark-pixel clusters in a rect
import Cocoa

let a = CommandLine.arguments
guard a.count >= 6, let img = NSImage(contentsOfFile: a[1]),
      let tiff = img.tiffRepresentation, let rep = NSBitmapImageRep(data: tiff),
      let x0 = Int(a[2]), let y0 = Int(a[3]), let w = Int(a[4]), let h = Int(a[5]) else {
    print("usage: find_dark.swift <image> <x> <y> <w> <h> [lum]"); exit(1)
}
guard a.count <= 7,
      let thresh = Double(a.count > 6 ? a[6] : "180"), thresh.isFinite,
      thresh >= 0, thresh <= 255,
      x0 >= 0, y0 >= 0, w > 0, h > 0,
      x0 < rep.pixelsWide, y0 < rep.pixelsHigh,
      w <= rep.pixelsWide - x0, h <= rep.pixelsHigh - y0 else {
    fputs("Require a positive rectangle entirely inside the image and luminance in 0...255\n", stderr)
    exit(1)
}
var scanned = 0
var dark: [(Int, Int, Double)] = []
var minLum = 255.0
for y in y0..<(y0 + h) {
    for x in x0..<(x0 + w) {
        guard let c = rep.colorAt(x: x, y: y)?.usingColorSpace(.deviceRGB) else {
            fputs("Cannot read pixel in RGB\n", stderr); exit(1)
        }
        scanned += 1
        let lum = 0.299 * c.redComponent + 0.587 * c.greenComponent + 0.114 * c.blueComponent
        let l255 = lum * 255
        if l255 < minLum { minLum = l255 }
        if l255 < thresh { dark.append((x, y, l255)) }
    }
}
print(String(format: "region (%d,%d,%d,%d) minLum=%.1f darkPixels=%d", x0, y0, w, h, minLum, dark.count))
if !dark.isEmpty {
    let xs = dark.map { $0.0 }, ys = dark.map { $0.1 }
    print("dark bbox: x \(xs.min()!)-\(xs.max()!), y \(ys.min()!)-\(ys.max()!)")
    // print a small ascii map
    let minX = xs.min()!, minY = ys.min()!
    let maxX = xs.max()!, maxY = ys.max()!
    if maxX - minX < 120 && maxY - minY < 60 {
        for y in minY...maxY {
            var line = ""
            for x in minX...maxX {
                line += dark.contains(where: { $0.0 == x && $0.1 == y }) ? "#" : "."
            }
            print(line)
        }
    }
}

print("scannedPixels=\(scanned); dark means luminance < \(thresh). Zero matches is not proof of no residual text; light/color fragments and legitimate artwork need visual review.")
