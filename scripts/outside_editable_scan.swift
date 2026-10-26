#!/usr/bin/env swift
// Find source-vs-candidate pixels above tolerance that fall OUTSIDE declared editable rects.
// Pixels are decoded exactly like compare_pixels.swift (sRGB premultiplied RGBA8, alpha
// included), so "unexpected_by_policy" equals the gate's protected+unchanged violations.
// usage: outside_editable_scan.swift TASK.json PNG_NAME OUTPUT_DIR
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
let args = Array(CommandLine.arguments.dropFirst())
guard args.count == 3 else { fail("usage: outside_editable_scan.swift TASK.json PNG_NAME OUTPUT_DIR") }
guard let taskData = try? Data(contentsOf: URL(fileURLWithPath: args[0])),
      let entries = (try? JSONSerialization.jsonObject(with: taskData)) as? [[String: Any]] else {
    fail("task must be a JSON list")
}
guard let entry = entries.first(where: { ($0["png"] as? String) == args[1] }) else { fail("png not in task") }
guard let srcPath = entry["source"] as? String,
      let cmp = entry["comparison"] as? [String: Any],
      let tol = cmp["channel_tolerance"] as? Int, (0...254).contains(tol),
      let regions = cmp["editable"] as? [[String: Any]] else {
    fail("task entry needs source, comparison.channel_tolerance (0...254) and comparison.editable")
}
var editable: [[Int]] = []
for r in regions {
    guard let rect = r["rect"] as? [Int], rect.count == 4, rect[2] > rect[0], rect[3] > rect[1] else {
        fail("editable rect must be integer [x0,y0,x1,y1] with positive area")
    }
    editable.append(rect)
}
let a = load(srcPath), b = load("\(args[2])/\(args[1])")
guard a.w == b.w && a.h == b.h else { fail("size mismatch") }
let w = a.w, h = a.h
var editableMask = [Bool](repeating: false, count: w*h)
for r in editable {
    for y in max(0, r[1])..<min(h, r[3]) { for x in max(0, r[0])..<min(w, r[2]) { editableMask[y*w+x] = true } }
}
var visited = [Bool](repeating: false, count: w*h)
var flagged = [Bool](repeating: false, count: w*h)
var total = 0
for i in 0..<(w*h) where !editableMask[i] && delta(a, b, i) > tol { flagged[i] = true; total += 1 }
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
