#!/usr/bin/env swift
// Find source-vs-candidate pixels above tolerance that fall OUTSIDE declared editable rects.
// usage: diffscan.swift TASK.json PNG_NAME OUTPUT_DIR
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

let args = Array(CommandLine.arguments.dropFirst())
guard args.count == 3 else { fail("usage: diffscan.swift TASK.json PNG_NAME OUTPUT_DIR") }
let taskData = try! Data(contentsOf: URL(fileURLWithPath: args[0]))
let entries = try! JSONSerialization.jsonObject(with: taskData) as! [[String: Any]]
guard let entry = entries.first(where: { ($0["png"] as? String) == args[1] }) else { fail("png not in task") }
let srcPath = entry["source"] as! String
let outdir = args[2]
let cmp = entry["comparison"] as! [String: Any]
let tol = cmp["channel_tolerance"] as! Int
var editable: [[Int]] = []
for r in cmp["editable"] as! [[String: Any]] { editable.append((r["rect"] as! [NSNumber]).map { $0.intValue }) }

let a = load(srcPath), b = load("\(outdir)/\(args[1])")
guard a.w == b.w && a.h == b.h else { fail("size mismatch") }
let w = a.w, h = a.h

@inline(__always) func inEditable(_ x: Int, _ y: Int) -> Bool {
    for r in editable { if x >= r[0] && x < r[2] && y >= r[1] && y < r[3] { return true } }
    return false
}
var visited = [Bool](repeating: false, count: w*h)
var flagged = [Bool](repeating: false, count: w*h)
var total = 0
for y in 0..<h { for x in 0..<w {
    let ca = rgb(a, x, y), cb = rgb(b, x, y)
    let d = max(abs(ca.0-cb.0), max(abs(ca.1-cb.1), abs(ca.2-cb.2)))
    if d > tol && !inEditable(x, y) { flagged[y*w+x] = true; total += 1 }
}}
print("unexpected_by_policy: \(total)")
let dx=[1,-1,0,0], dy=[0,0,1,-1]
var comps: [(Int,Int,Int,Int,Int)] = []
for y in 0..<h { for x in 0..<w {
    let idx = y*w+x
    if !flagged[idx] || visited[idx] { continue }
    var stack=[(x,y)]; visited[idx]=true
    var x0=x,y0=y,x1=x,y1=y,n=0
    while let (cx,cy)=stack.popLast() {
        n+=1; x0=min(x0,cx); y0=min(y0,cy); x1=max(x1,cx); y1=max(y1,cy)
        for k in 0..<4 {
            let nx=cx+dx[k], ny=cy+dy[k]
            if nx<0||ny<0||nx>=w||ny>=h { continue }
            let ni=ny*w+nx
            if flagged[ni] && !visited[ni] { visited[ni]=true; stack.append((nx,ny)) }
        }
    }
    comps.append((x0,y0,x1+1,y1+1,n))
}}
comps.sort { $0.4 > $1.4 }
for c in comps { print("bbox=[\(c.0),\(c.1),\(c.2),\(c.3)] count=\(c.4)") }
