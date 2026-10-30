#!/usr/bin/env swift
// Measure the background noise floor between a source and an existing localized output:
// the per-channel difference over pixels that are NOT text and NOT the text-edge halo.
// This is the value channel_tolerance must reach for the delivery gate on this pair.
//
// Method: strong changes (diff > TEXT_TOL) are treated as text/artwork edits and removed,
// then dilated by DILATE px to also remove the antialias/JPEG ringing halo around them.
// The remaining pixels are background; their diff distribution (p50/p99/p99.9/max) is the
// floor. floor_max >> floor_p999 means a thin hot tail — a possible localized defect
// (repair seam, missed mark), not diffuse noise; locate it with outside_editable_scan.swift.
//
// Pixels are decoded exactly like compare_pixels.swift (sRGB premultiplied RGBA8).
//
// usage: background_floor.swift SOURCE CANDIDATE [TEXT_TOL=30] [DILATE=10]
// prints JSON: {"floor_max":N,"floor_p999":N,"floor_p99":N,"floor_p50":N,
//               "background_pixels":N,"strong_pixels":N,"text_tol":N,"dilate":N}
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
guard (3...5).contains(a.count) else { fail("usage: background_floor.swift SOURCE CANDIDATE [TEXT_TOL] [DILATE]") }
guard let textTol = a.count > 3 ? Int(a[3]) : 30, (0...254).contains(textTol),
      let dilate = a.count > 4 ? Int(a[4]) : 10, dilate >= 0 else {
    fail("TEXT_TOL must be 0...254 and DILATE >= 0")
}
let im1 = load(a[1]), im2 = load(a[2])
guard im1.w == im2.w && im1.h == im2.h else { fail("size mismatch") }
let w = im1.w, h = im1.h
// strong-change mask (text/artwork edits)
var strong = [Bool](repeating: false, count: w*h)
var strongCount = 0
for i in 0..<(w*h) where delta(im1, im2, i) > textTol { strong[i] = true; strongCount += 1 }
// dilate to cover the text-edge ringing halo (separable box, two passes per px of radius)
if dilate > 0 && strongCount > 0 {
    var tmp = [Bool](repeating: false, count: w*h)
    for _ in 0..<dilate {
        // horizontal
        for y in 0..<h {
            var run = 0
            for x in 0..<w {
                if strong[y*w+x] { run = 1 } // mark self
                tmp[y*w+x] = run == 1 || (x > 0 && strong[y*w+x-1]) || (x+1 < w && strong[y*w+x+1])
            }
        }
        // vertical
        for x in 0..<w {
            for y in 0..<h {
                strong[y*w+x] = tmp[y*w+x] || (y > 0 && tmp[(y-1)*w+x]) || (y+1 < h && tmp[(y+1)*w+x])
            }
        }
    }
}
// histogram of background diffs
var hist = [Int](repeating: 0, count: 256)
var bgCount = 0
for i in 0..<(w*h) where !strong[i] {
    hist[delta(im1, im2, i)] += 1
    bgCount += 1
}
func percentile(_ p: Double) -> Int {
    guard bgCount > 0 else { return 0 }
    let target = Int((p * Double(bgCount)).rounded(.up))
    var acc = 0
    for v in 0..<256 { acc += hist[v]; if acc >= target { return v } }
    return 255
}
var floorMax = 0
for v in stride(from: 255, through: 0, by: -1) where hist[v] > 0 { floorMax = v; break }
let out: [String: Any] = ["floor_max": floorMax, "floor_p999": percentile(0.999),
                          "floor_p99": percentile(0.99), "floor_p50": percentile(0.5),
                          "background_pixels": bgCount, "strong_pixels": strongCount,
                          "text_tol": textTol, "dilate": dilate]
let data = try! JSONSerialization.data(withJSONObject: out, options: [.sortedKeys])
print(String(data: data, encoding: .utf8)!)
