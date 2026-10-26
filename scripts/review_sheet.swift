#!/usr/bin/env swift
// Render review pages for one candidate: every region as stacked source / candidate / diff
// crops at exact 1:1 pixels (split into tiles when larger than a page), plus an overview of
// source and candidate at the intended display width. Invoked by review_sheet.py.
// usage: review_sheet.swift CONFIG.json
// CONFIG: {"source","output","diff","out_dir","page_px","display_width","context_px",
//          "regions":[{"id","kind","rect":[x0,y0,x1,y1]}]}
// prints JSON: {"pages":[{"file","width","height","tiles":[{"region","kind","rect"}]}],"overview":{...}}
import Foundation
import CoreGraphics
import CoreText
import ImageIO

struct Region: Decodable { let id: String; let kind: String; let rect: [Int] }
struct Config: Decodable {
    let source: String; let output: String; let diff: String; let out_dir: String
    let page_px: Int; let display_width: Int; let context_px: Int; let regions: [Region]
}
struct Fail: Error, CustomStringConvertible { let description: String }

func load(_ path: String) throws -> CGImage {
    guard let src = CGImageSourceCreateWithURL(URL(fileURLWithPath: path) as CFURL, nil),
          CGImageSourceGetCount(src) == 1,
          let img = CGImageSourceCreateImageAtIndex(src, 0, nil) else { throw Fail(description: "cannot decode \(path)") }
    let props = CGImageSourceCopyPropertiesAtIndex(src, 0, nil) as? [CFString: Any]
    guard ((props?[kCGImagePropertyOrientation] as? NSNumber)?.intValue ?? 1) == 1 else {
        throw Fail(description: "normalize EXIF orientation first: \(path)")
    }
    return img
}

let labelH = 18, gutter = 12, gap = 4
let space = CGColorSpace(name: CGColorSpace.sRGB)!
let font = CTFontCreateWithName("Menlo" as CFString, 12, nil)

final class Page {
    let ctx: CGContext; let w: Int; let h: Int
    init(_ w: Int, _ h: Int) throws {
        self.w = w; self.h = h
        guard let c = CGContext(data: nil, width: w, height: h, bitsPerComponent: 8, bytesPerRow: 0, space: space,
                                bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else { throw Fail(description: "page alloc") }
        ctx = c
        ctx.setFillColor(CGColor(srgbRed: 0.13, green: 0.13, blue: 0.13, alpha: 1))
        ctx.fill(CGRect(x: 0, y: 0, width: w, height: h))
    }
    // Top-left page coordinates; CGContext is bottom-left.
    func image(_ img: CGImage, x: Int, y: Int, w dw: Int, h dh: Int, exact: Bool) {
        ctx.interpolationQuality = exact ? .none : .high
        ctx.draw(img, in: CGRect(x: x, y: h - y - dh, width: dw, height: dh))
    }
    func text(_ s: String, x: Int, y: Int) {
        let attrs: [CFString: Any] = [kCTFontAttributeName: font,
                                      kCTForegroundColorAttributeName: CGColor(srgbRed: 1, green: 1, blue: 1, alpha: 1)]
        let line = CTLineCreateWithAttributedString(CFAttributedStringCreate(nil, s as CFString, attrs as CFDictionary))
        ctx.textPosition = CGPoint(x: x, y: h - y - labelH + 5)
        CTLineDraw(line, ctx)
    }
    func save(_ path: String) throws {
        guard let img = ctx.makeImage(),
              let dest = CGImageDestinationCreateWithURL(URL(fileURLWithPath: path) as CFURL, "public.png" as CFString, 1, nil)
        else { throw Fail(description: "cannot create \(path)") }
        CGImageDestinationAddImage(dest, img, nil)
        guard CGImageDestinationFinalize(dest) else { throw Fail(description: "cannot write \(path)") }
    }
}

func textWidth(_ s: String) -> Int {
    let attrs: [CFString: Any] = [kCTFontAttributeName: font]
    let line = CTLineCreateWithAttributedString(CFAttributedStringCreate(nil, s as CFString, attrs as CFDictionary))
    return Int(CTLineGetTypographicBounds(line, nil, nil, nil).rounded(.up)) + 2
}

struct Tile { let region: Region; let rect: [Int]; let index: Int; let count: Int
    var w: Int { rect[2] - rect[0] }; var h: Int { rect[3] - rect[1] }
    // Full description once; the candidate/diff rows only name the layer.
    var header: String {
        let part = count > 1 ? " \(index + 1)/\(count)" : ""
        return "\(region.kind) \(region.id)\(part) [\(rect[0]),\(rect[1]),\(rect[2]),\(rect[3])] 1:1 source"
    }
    let labelW: Int  // header width, capped to the page so blocks always fit
    var blockW: Int { max(w, labelW) }; var blockH: Int { 3 * (h + labelH) + 2 * gap }
}

func run() throws -> [String: Any] {
    let cfg = try JSONDecoder().decode(Config.self, from: Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1])))
    let src = try load(cfg.source), out = try load(cfg.output), diff = try load(cfg.diff)
    let W = src.width, H = src.height
    guard out.width == W, out.height == H, diff.width == W, diff.height == H else { throw Fail(description: "dimension mismatch") }
    guard cfg.page_px >= 256, cfg.display_width > 0, cfg.context_px >= 0 else { throw Fail(description: "invalid page settings") }
    let maxW = cfg.page_px - 2 * gutter
    let maxH = (cfg.page_px - 2 * gutter - 3 * labelH - 2 * gap) / 3

    var tiles: [Tile] = []
    for region in cfg.regions {
        let r = region.rect
        guard r.count == 4, r[0] >= 0, r[1] >= 0, r[2] > r[0], r[3] > r[1], r[2] <= W, r[3] <= H else {
            throw Fail(description: "invalid region \(region.id)")
        }
        let c = [max(0, r[0] - cfg.context_px), max(0, r[1] - cfg.context_px),
                 min(W, r[2] + cfg.context_px), min(H, r[3] + cfg.context_px)]
        let cols = (c[2] - c[0] + maxW - 1) / maxW, rows = (c[3] - c[1] + maxH - 1) / maxH
        let tw = (c[2] - c[0] + cols - 1) / cols, th = (c[3] - c[1] + rows - 1) / rows
        var n = 0
        for row in 0..<rows { for col in 0..<cols {
            let x0 = c[0] + col * tw, y0 = c[1] + row * th
            var t = Tile(region: region, rect: [x0, y0, min(c[2], x0 + tw), min(c[3], y0 + th)],
                         index: n, count: rows * cols, labelW: 0)
            t = Tile(region: region, rect: t.rect, index: n, count: t.count, labelW: min(maxW, textWidth(t.header)))
            tiles.append(t)
            n += 1
        }}
    }
    // Shelf packing: left-to-right rows of blocks, new page when the page height is full.
    var pages: [[(Tile, Int, Int)]] = [[]]
    var x = gutter, y = gutter, shelf = 0
    for t in tiles {
        if x > gutter && x + t.blockW > cfg.page_px - gutter { x = gutter; y += shelf + gutter; shelf = 0 }
        if y > gutter && y + t.blockH > cfg.page_px - gutter { pages.append([]); x = gutter; y = gutter; shelf = 0 }
        pages[pages.count - 1].append((t, x, y))
        x += t.blockW + gutter; shelf = max(shelf, t.blockH)
    }
    var pageInfo: [[String: Any]] = []
    for (i, items) in pages.enumerated() where !items.isEmpty {
        let pw = items.map { $0.1 + $0.0.blockW }.max()! + gutter
        let ph = items.map { $0.2 + $0.0.blockH }.max()! + gutter
        let page = try Page(pw, ph)
        var rows: [[String: Any]] = []
        for (t, px, py) in items {
            let crop = CGRect(x: t.rect[0], y: t.rect[1], width: t.w, height: t.h)
            var cy = py
            for (name, img) in [(t.header, src), ("candidate", out), ("diff (cyan editable, red unexpected)", diff)] {
                page.text(name, x: px, y: cy)
                cy += labelH
                guard let piece = img.cropping(to: crop) else { throw Fail(description: "crop failed") }
                page.image(piece, x: px, y: cy, w: t.w, h: t.h, exact: true)
                cy += t.h + gap
            }
            rows.append(["region": t.region.id, "kind": t.region.kind, "rect": t.rect])
        }
        let file = (cfg.out_dir as NSString).appendingPathComponent(String(format: "regions-%02d.png", i + 1))
        try page.save(file)
        pageInfo.append(["file": file, "width": pw, "height": ph, "tiles": rows])
    }
    // Overview: source | candidate at the intended display width (scaled further only to fit a page).
    var scale = min(1.0, Double(cfg.display_width) / Double(W))
    scale = min(scale, Double(cfg.page_px - 3 * gutter) / Double(2 * W), Double(cfg.page_px - 2 * gutter - labelH) / Double(H))
    let ow = max(1, Int((Double(W) * scale).rounded())), oh = max(1, Int((Double(H) * scale).rounded()))
    let overview = try Page(3 * gutter + 2 * ow, 2 * gutter + labelH + oh)
    let pct = String(format: "%.0f%%", scale * 100)
    overview.text("source \(ow)px (\(pct))", x: gutter, y: gutter)
    overview.text("candidate \(ow)px (\(pct))", x: 2 * gutter + ow, y: gutter)
    overview.image(src, x: gutter, y: gutter + labelH, w: ow, h: oh, exact: false)
    overview.image(out, x: 2 * gutter + ow, y: gutter + labelH, w: ow, h: oh, exact: false)
    let ofile = (cfg.out_dir as NSString).appendingPathComponent("overview.png")
    try overview.save(ofile)
    return ["pages": pageInfo, "overview": ["file": ofile, "display_width": ow, "scale": scale]]
}

do {
    guard CommandLine.arguments.count == 2 else { throw Fail(description: "usage: review_sheet.swift CONFIG.json") }
    let result = try run()
    print(String(data: try JSONSerialization.data(withJSONObject: result, options: [.sortedKeys]), encoding: .utf8)!)
} catch {
    FileHandle.standardError.write("\(error)\n".data(using: .utf8)!)
    exit(1)
}
