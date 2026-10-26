#!/usr/bin/env swift
// Derive the changed footprint between source and the v1 localized PNG (text+repair areas).
// usage: repairmap.swift SOURCE V1PNG TOL MIN_AREA DILATE
// prints JSON: {"baseline_max":N,"count":N,"rects":[[x0,y0,x1,y1],...]}
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
guard a.count == 6, let tol = Int(a[3]), let minArea = Int(a[4]), let dilate = Int(a[5]) else {
    fail("usage: repairmap.swift SOURCE V1PNG TOL MIN_AREA DILATE")
}
let im1 = load(a[1]), im2 = load(a[2])
guard im1.w == im2.w && im1.h == im2.h else { fail("size mismatch") }
let w = im1.w, h = im1.h
var flag = [Bool](repeating: false, count: w*h)
var anyDiff = 0
for y in 0..<h { for x in 0..<w {
    let c1 = rgb(im1,x,y), c2 = rgb(im2,x,y)
    let d = max(abs(c1.0-c2.0), max(abs(c1.1-c2.1), abs(c1.2-c2.2)))
    if d > tol { flag[y*w+x] = true; anyDiff += 1 }
}}
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
    if inComp[y*w+x] { continue }
    let c1 = rgb(im1,x,y), c2 = rgb(im2,x,y)
    let d = max(abs(c1.0-c2.0), max(abs(c1.1-c2.1), abs(c1.2-c2.2)))
    if d > baseline { baseline = d }
    if d > tol {
        outCount += 1
        bx0 = min(bx0,x); by0 = min(by0,y); bx1 = max(bx1,x); by1 = max(by1,y)
    }
}}
let outBBox: [Int] = outCount > 0 ? [bx0,by0,bx1+1,by1+1] : []
let out: [String: Any] = ["baseline_max": baseline, "components": rects.count, "diff_pixels": anyDiff,
                          "outside_count": outCount, "outside_bbox": outBBox, "rects": merged]
let data = try! JSONSerialization.data(withJSONObject: out)
print(String(data: data, encoding: .utf8)!)
