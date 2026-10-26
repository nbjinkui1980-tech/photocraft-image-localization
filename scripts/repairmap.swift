#!/usr/bin/env swift
// Derive the changed footprint between source and the v1 localized PNG (text+repair areas).
// usage: repairmap.swift SOURCE V1PNG TOL MIN_AREA DILATE
// prints JSON: {"baseline_max":N,"count":N,"rects":[[x0,y0,x1,y1],...]}
// Pixels are decoded exactly like compare_pixels.swift (sRGB premultiplied RGBA8, alpha
// included, top-left origin), so the footprint matches what the delivery gate measures.
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
guard a.count == 6, let tol = Int(a[3]), let minArea = Int(a[4]), let dilate = Int(a[5]),
      (0...254).contains(tol), minArea >= 1, dilate >= 0 else {
    fail("usage: repairmap.swift SOURCE V1PNG TOL(0-254) MIN_AREA(>=1) DILATE(>=0)")
}
let im1 = load(a[1]), im2 = load(a[2])
guard im1.w == im2.w && im1.h == im2.h else { fail("size mismatch") }
let w = im1.w, h = im1.h
var flag = [Bool](repeating: false, count: w*h)
var anyDiff = 0
for i in 0..<(w*h) where delta(im1, im2, i) > tol { flag[i] = true; anyDiff += 1 }
// components
let dx=[1,-1,0,0], dy=[0,0,1,-1]
var visited = [Bool](repeating:false, count:w*h)
var rects: [[Int]] = []
var inComp = [Bool](repeating:false, count:w*h)
for y in 0..<h { for x in 0..<w {
    let idx = y*w+x
    if !flag[idx] || visited[idx] { continue }
    var stack=[(x,y)]; visited[idx]=true
    var x0=x,y0=y,x1=x,y1=y,n=0
    while let (cx,cy)=stack.popLast() {
        n+=1; x0=min(x0,cx); y0=min(y0,cy); x1=max(x1,cx); y1=max(y1,cy)
        for k in 0..<4 {
            let nx=cx+dx[k], ny=cy+dy[k]
            if nx<0||ny<0||nx>=w||ny>=h { continue }
            let ni=ny*w+nx
            if flag[ni] && !visited[ni] { visited[ni]=true; stack.append((nx,ny)) }
        }
    }
    if n >= minArea {
        let rx0=max(0,x0-dilate), ry0=max(0,y0-dilate), rx1=min(w,x1+1+dilate), ry1=min(h,y1+1+dilate)
        rects.append([rx0,ry0,rx1,ry1])
        for yy in ry0..<ry1 { for xx in rx0..<rx1 { inComp[yy*w+xx]=true } }
    }
}}
// merge overlapping rects
var merged = rects
var changedMerge = true
while changedMerge {
    changedMerge = false
    outer: for i in 0..<merged.count { for j in (i+1)..<merged.count {
        let A=merged[i], B=merged[j]
        if min(A[2],B[2]) > max(A[0],B[0]) && min(A[3],B[3]) > max(A[1],B[1]) {
            merged[i] = [min(A[0],B[0]), min(A[1],B[1]), max(A[2],B[2]), max(A[3],B[3])]
            merged.remove(at: j); changedMerge = true; break outer
        }
    }}
}
// baseline max diff outside components + count/bbox of >tol pixels outside components
var baseline = 0, outCount = 0
var bx0 = w, by0 = h, bx1 = -1, by1 = -1
for y in 0..<h { for x in 0..<w {
    let i = y*w+x
    if inComp[i] { continue }
    let d = delta(im1, im2, i)
    if d > baseline { baseline = d }
    if d > tol {
        outCount += 1
        bx0 = min(bx0,x); by0 = min(by0,y); bx1 = max(bx1,x); by1 = max(by1,y)
    }
}}
let outBBox: [Int] = outCount > 0 ? [bx0,by0,bx1+1,by1+1] : []
let out: [String: Any] = ["baseline_max": baseline, "components": rects.count, "diff_pixels": anyDiff,
                          "outside_count": outCount, "outside_bbox": outBBox, "rects": merged,
                          "width": w, "height": h]
let data = try! JSONSerialization.data(withJSONObject: out)
print(String(data: data, encoding: .utf8)!)
