#!/usr/bin/env swift
// Decide whether an existing localized output PRESERVED the source background
// (so the original source is a valid pixel-comparison baseline) or REDESIGNED it
// (a different gradient/photo/grade; comparing to the source would flag the whole
// background and the source baseline is invalid).
//
// Grid-samples both images and reports the median per-channel difference and the
// fraction of samples above a tolerance. Preserved background: median ~0 and only
// text-area samples exceed tolerance. Redesigned: high median and most samples differ.
//
// usage: classify_baseline.swift SOURCE CANDIDATE [STEP=60] [TOL=6]
// prints JSON: {"median":N,"over":N,"total":N,"frac":F,"verdict":"preserved|redesigned"}
import Foundation
import AppKit

func fail(_ s: String) -> Never { FileHandle.standardError.write((s+"\n").data(using:.utf8)!); exit(2) }
struct Img { let w: Int; let h: Int; let stride: Int; let bytes: [UInt8]; let rowBytes: Int }
func load(_ path: String) -> Img {
    guard let img = NSImage(contentsOfFile: path), let tiff = img.tiffRepresentation,
          let rep = NSBitmapImageRep(data: tiff), !rep.isPlanar, rep.bitsPerSample == 8,
          let data = rep.bitmapData else { fail("cannot read \(path)") }
    let stride = rep.bitsPerPixel / 8
    return Img(w: rep.pixelsWide, h: rep.pixelsHigh, stride: stride,
               bytes: Array(UnsafeBufferPointer(start: data, count: rep.bytesPerRow * rep.pixelsHigh)),
               rowBytes: rep.bytesPerRow)
}
@inline(__always) func rgb(_ im: Img, _ x: Int, _ y: Int) -> (Int,Int,Int) {
    let i = y * im.rowBytes + x * im.stride
    return (Int(im.bytes[i]), Int(im.bytes[i+1]), Int(im.bytes[i+2]))
}

let a = CommandLine.arguments
guard a.count >= 3 else { fail("usage: classify_baseline.swift SOURCE CANDIDATE [STEP] [TOL]") }
let step = a.count > 3 ? Int(a[3]) ?? 60 : 60
let tol = a.count > 4 ? Int(a[4]) ?? 6 : 6
let im1 = load(a[1]), im2 = load(a[2])
guard im1.w == im2.w && im1.h == im2.h else { fail("size mismatch") }
var diffs: [Int] = []
var y = 30
while y < im1.h - 30 {
    var x = 30
    while x < im1.w - 30 {
        let c1 = rgb(im1,x,y), c2 = rgb(im2,x,y)
        diffs.append(max(abs(c1.0-c2.0), max(abs(c1.1-c2.1), abs(c1.2-c2.2))))
        x += step
    }
    y += step
}
diffs.sort()
let total = diffs.count
let median = total > 0 ? diffs[total/2] : 0
let over = diffs.filter { $0 > tol }.count
let frac = total > 0 ? Double(over)/Double(total) : 0
// redesigned when differences are widespread AND not confined to sparse text pixels
let verdict = (frac > 0.45 && median > tol) ? "redesigned" : "preserved"
let out: [String: Any] = ["median": median, "over": over, "total": total,
                          "frac": round(frac*1000)/1000, "tol": tol, "verdict": verdict]
let data = try! JSONSerialization.data(withJSONObject: out)
print(String(data: data, encoding: .utf8)!)
