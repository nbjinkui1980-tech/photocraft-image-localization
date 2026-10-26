#!/usr/bin/env swift
// Decide whether an existing localized output PRESERVED the source background
// (so the original source is a valid pixel-comparison baseline) or REDESIGNED it
// (a different gradient/photo/grade; comparing to the source would flag the whole
// background and the source baseline is invalid).
//
// Grid-samples both images and reports the median per-channel difference and the
// fraction of samples above a tolerance. Preserved background: median ~0 and only
// text-area samples exceed tolerance. Redesigned: high median and most samples differ.
// Pixels are decoded exactly like compare_pixels.swift (sRGB premultiplied RGBA8).
// Samples skip a border of up to 30 px (smaller on small images); zero samples is an error.
//
// usage: classify_baseline.swift SOURCE CANDIDATE [STEP=60] [TOL=6]
// prints JSON: {"median":N,"over":N,"total":N,"frac":F,"verdict":"preserved|redesigned"}
import Foundation
import CoreGraphics
import ImageIO
func fail(_ s: String) -> Never { FileHandle.standardError.write((s+"\n").data(using:.utf8)!); exit(2) }
// --- shared raster loader: keep identical to compare_pixels.swift raster() ---
struct Img { let w: Int; let h: Int; let bytes: [UInt8] }
func load(_ path: String) -> Img {
    guard let src = CGImageSourceCreateWithURL(URL(fileURLWithPath: path) as CFURL, nil),
          CGImageSourceGetCount(src) == 1 else { fail("unreadable or multi-frame image: \(path)") }
    let props = CGImageSourceCopyPropertiesAtIndex(src, 0, nil) as? [CFString: Any]
    guard ((props?[kCGImagePropertyOrientation] as? NSNumber)?.intValue ?? 1) == 1 else {
        fail("normalize EXIF orientation in a working copy first: \(path)")
    }
    guard let img = CGImageSourceCreateImageAtIndex(src, 0, nil) else { fail("cannot decode image: \(path)") }
    let w = img.width, h = img.height
    guard w > 0, h > 0, w <= 50_000_000 / h else { fail("image exceeds the 50-million-pixel scan limit") }
    guard let space = CGColorSpace(name: CGColorSpace.sRGB) else { fail("sRGB unavailable") }
    var bytes = [UInt8](repeating: 0, count: w * h * 4)
    let ok = bytes.withUnsafeMutableBytes { buffer -> Bool in
        guard let ctx = CGContext(data: buffer.baseAddress, width: w, height: h, bitsPerComponent: 8,
                                  bytesPerRow: w * 4, space: space,
                                  bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue | CGBitmapInfo.byteOrder32Big.rawValue)
        else { return false }
        ctx.setBlendMode(.copy)
        ctx.interpolationQuality = .none
        ctx.draw(img, in: CGRect(x: 0, y: 0, width: w, height: h))
        return true
    }
    guard ok else { fail("cannot allocate raster context") }
    return Img(w: w, h: h, bytes: bytes)
}
@inline(__always) func delta(_ a: Img, _ b: Img, _ i: Int) -> Int {
    let o = i * 4
    var d = 0
    for c in 0..<4 { d = max(d, abs(Int(a.bytes[o + c]) - Int(b.bytes[o + c]))) }
    return d
}
// --- end shared raster loader ---
let a = CommandLine.arguments
guard (3...5).contains(a.count) else { fail("usage: classify_baseline.swift SOURCE CANDIDATE [STEP] [TOL]") }
guard let step = a.count > 3 ? Int(a[3]) : 60, step > 0,
      let tol = a.count > 4 ? Int(a[4]) : 6, (0...254).contains(tol) else {
    fail("STEP must be a positive integer and TOL an integer in 0...254")
}
let im1 = load(a[1]), im2 = load(a[2])
guard im1.w == im2.w && im1.h == im2.h else { fail("size mismatch") }
// Border skip shrinks on small images so they are still sampled instead of silently "preserved".
let marginX = min(30, (im1.w - 1) / 2), marginY = min(30, (im1.h - 1) / 2)
var diffs: [Int] = []
var y = marginY
while y < im1.h - marginY {
    var x = marginX
    while x < im1.w - marginX {
        diffs.append(delta(im1, im2, y * im1.w + x))
        x += step
    }
    y += step
}
let total = diffs.count
guard total > 0 else { fail("no samples taken; cannot classify") }
diffs.sort()
let median = diffs[total/2]
let over = diffs.filter { $0 > tol }.count
let frac = Double(over)/Double(total)
// redesigned when differences are widespread AND not confined to sparse text pixels
let verdict = (frac > 0.45 && median > tol) ? "redesigned" : "preserved"
let out: [String: Any] = ["median": median, "over": over, "total": total,
                          "frac": round(frac*1000)/1000, "tol": tol, "verdict": verdict]
let data = try! JSONSerialization.data(withJSONObject: out)
print(String(data: data, encoding: .utf8)!)
