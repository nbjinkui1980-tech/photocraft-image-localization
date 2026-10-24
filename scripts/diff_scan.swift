#!/usr/bin/env swift
// diff_scan.swift <source> <output> [cellPx=48] [minDiff=2.5] [majorDiff=25]
// Compares a localized output against its source at quarter scale.
// Prints "suspect" regions: cells whose mean color diff is small-but-consistent
// (patch seams, tone mismatches). Large diffs (text replacement) are counted only.
import Cocoa

let a = CommandLine.arguments
guard a.count >= 3,
      let img1 = NSImage(contentsOfFile: a[1]), let t1 = img1.tiffRepresentation, let r1 = NSBitmapImageRep(data: t1),
      let img2 = NSImage(contentsOfFile: a[2]), let t2 = img2.tiffRepresentation, let r2 = NSBitmapImageRep(data: t2) else {
    fputs("usage: diff_scan.swift <source> <output> [cellPx] [minDiff] [majorDiff]\n", stderr); exit(1)
}
guard r1.pixelsWide == r2.pixelsWide, r1.pixelsHigh == r2.pixelsHigh else {
    fputs("dimension mismatch: \(r1.pixelsWide)x\(r1.pixelsHigh) vs \(r2.pixelsWide)x\(r2.pixelsHigh)\n", stderr); exit(1)
}
guard a.count <= 6,
      let cell = Int(a.count > 3 ? a[3] : "48"), cell > 0,
      let minDiff = Double(a.count > 4 ? a[4] : "2.5"), minDiff.isFinite,
      let majorDiff = Double(a.count > 5 ? a[5] : "25"), majorDiff.isFinite,
      minDiff > 0, minDiff < majorDiff, majorDiff <= 255 else {
    fputs("Require cellPx > 0 and 0 < minDiff < majorDiff <= 255\n", stderr); exit(1)
}
let q = 4
// shortcut: downsampling can hide fine defects; use original-size review for glyph fragments.
let W = max(1, (r1.pixelsWide + q - 1) / q)
let H = max(1, (r1.pixelsHigh + q - 1) / q)
let qc = max(1, cell / q)

func small(_ rep: NSBitmapImageRep) -> NSBitmapImageRep {
    let out = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: W, pixelsHigh: H,
                               bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
                               colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: out)
    NSGraphicsContext.current?.imageInterpolation = .high
    rep.draw(in: NSRect(x: 0, y: 0, width: W, height: H))
    NSGraphicsContext.restoreGraphicsState()
    return out
}
let s1 = small(r1), s2 = small(r2)

var suspects: [(x: Int, y: Int, w: Int, h: Int, d: Double)] = []
var major = 0
var maxSeen = 0.0
for cy in stride(from: 0, to: H, by: qc) {
    for cx in stride(from: 0, to: W, by: qc) {
        let xEnd = cx + min(qc, W - cx), yEnd = cy + min(qc, H - cy)
        var sum = 0.0
        for y in cy..<yEnd {
            for x in cx..<xEnd {
                guard let p = s1.colorAt(x: x, y: y), let q2 = s2.colorAt(x: x, y: y) else { fputs("Cannot read sampled pixel\n", stderr); exit(1) }
                sum += abs(p.redComponent - q2.redComponent) + abs(p.greenComponent - q2.greenComponent) + abs(p.blueComponent - q2.blueComponent)
            }
        }
        let mean = sum / Double((xEnd - cx) * (yEnd - cy)) * 255.0 / 3.0
        if mean > maxSeen { maxSeen = mean }
        if mean >= majorDiff { major += 1 } else if mean >= minDiff { let x = cx * r1.pixelsWide / W, y = cy * r1.pixelsHigh / H
            suspects.append((x, y, xEnd * r1.pixelsWide / W - x, yEnd * r1.pixelsHigh / H - y, mean)) }
    }
}

print("major-change cells (inspect; may include unintended edits): \(major); max cell diff: \(String(format: "%.1f", maxSeen))")
if suspects.isEmpty {
    print("no suspect tone-mismatch cells (threshold \(minDiff))")
} else {
    print("suspect cells (\(suspects.count)):")
    for s in suspects {
        print(String(format: "  x=%d y=%d %dx%d meanDiff=%.2f", s.x, s.y, s.w, s.h, s.d))
    }
}

print("Heuristic scan only; no findings does not establish a clean repair.")
