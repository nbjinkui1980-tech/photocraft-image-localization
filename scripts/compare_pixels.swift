#!/usr/bin/env swift
// Native-resolution comparison in a common sRGB premultiplied RGBA8 raster.
import Foundation
import CoreGraphics
import ImageIO

struct ScanError: Error, CustomStringConvertible {
    let description: String
    init(_ message: String) { description = message }
}
struct Region: Codable { let id: String; let rect: [Int] }
struct Config: Decodable {
    let source: String
    let output: String
    let diff_image: String
    let protected: [Region]
    let editable: [Region]
    let channel_tolerance: Int
}
struct Stats: Codable {
    var pixels = 0
    var changed_pixels = 0
    var above_tolerance_pixels = 0
    var max_channel_delta = 0
    var changed_bbox: [Int]? = nil
    var violation_bbox: [Int]? = nil
    mutating func add(_ delta: Int, _ x: Int, _ y: Int, _ tolerance: Int) {
        pixels += 1
        max_channel_delta = max(max_channel_delta, delta)
        if delta > 0 {
            changed_pixels += 1
            changed_bbox = merged(changed_bbox, x, y)
        }
        if delta > tolerance {
            above_tolerance_pixels += 1
            violation_bbox = merged(violation_bbox, x, y)
        }
    }
}
struct RegionStats: Codable { let id: String; let rect: [Int]; let stats: Stats }
struct Result: Codable {
    let width: Int
    let height: Int
    let pixels_scanned: Int
    let pixel_space: String
    let protected: Stats
    let unchanged: Stats
    let editable: Stats
    let protected_regions: [RegionStats]
    let editable_regions: [RegionStats]
    let unexpected_pixels: Int
}

func merged(_ old: [Int]?, _ x: Int, _ y: Int) -> [Int] {
    guard let old = old else { return [x, y, x + 1, y + 1] }
    return [min(old[0], x), min(old[1], y), max(old[2], x + 1), max(old[3], y + 1)]
}

func raster(_ path: String) throws -> (Int, Int, [UInt8]) {
    guard let src = CGImageSourceCreateWithURL(URL(fileURLWithPath: path) as CFURL, nil),
          CGImageSourceGetCount(src) == 1 else { throw ScanError("Unreadable or multi-frame image: \(path)") }
    let props = CGImageSourceCopyPropertiesAtIndex(src, 0, nil) as? [CFString: Any]
    let orientation = (props?[kCGImagePropertyOrientation] as? NSNumber)?.intValue ?? 1
    guard orientation == 1 else { throw ScanError("Normalize EXIF orientation in a working copy before declaring regions: \(path)") }
    guard let img = CGImageSourceCreateImageAtIndex(src, 0, nil) else { throw ScanError("Cannot decode image: \(path)") }
    let w = img.width, h = img.height
    guard w > 0, h > 0, w <= 50_000_000 / h else { throw ScanError("Image exceeds the 50-million-pixel scan limit") }
    guard let space = CGColorSpace(name: CGColorSpace.sRGB) else { throw ScanError("sRGB unavailable") }
    var bytes = [UInt8](repeating: 0, count: w * h * 4)
    try bytes.withUnsafeMutableBytes { buffer in
        guard let ctx = CGContext(data: buffer.baseAddress, width: w, height: h, bitsPerComponent: 8,
                                  bytesPerRow: w * 4, space: space,
                                  bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue | CGBitmapInfo.byteOrder32Big.rawValue)
        else { throw ScanError("Cannot allocate raster context") }
        ctx.setBlendMode(.copy)
        ctx.interpolationQuality = .none
        ctx.draw(img, in: CGRect(x: 0, y: 0, width: w, height: h))
    }
    return (w, h, bytes)
}

func validate(_ regions: [Region], _ width: Int, _ height: Int) throws {
    var names = Set<String>()
    for region in regions {
        let r = region.rect
        guard !region.id.isEmpty, names.insert(region.id).inserted, r.count == 4,
              r[0] >= 0, r[1] >= 0, r[2] > r[0], r[3] > r[1], r[2] <= width, r[3] <= height
        else { throw ScanError("Invalid/duplicate/out-of-bounds region: \(region.id)") }
    }
}

func saveDiff(_ data: [UInt8], _ width: Int, _ height: Int, _ path: String) throws {
    guard let space = CGColorSpace(name: CGColorSpace.sRGB),
          let provider = CGDataProvider(data: Data(data) as CFData),
          let image = CGImage(width: width, height: height, bitsPerComponent: 8, bitsPerPixel: 32,
                              bytesPerRow: width * 4, space: space,
                              bitmapInfo: CGBitmapInfo(rawValue: CGImageAlphaInfo.premultipliedLast.rawValue | CGBitmapInfo.byteOrder32Big.rawValue),
                              provider: provider, decode: nil, shouldInterpolate: false, intent: .defaultIntent),
          let dest = CGImageDestinationCreateWithURL(URL(fileURLWithPath: path) as CFURL, "public.png" as CFString, 1, nil)
    else { throw ScanError("Cannot create difference PNG") }
    CGImageDestinationAddImage(dest, image, nil)
    guard CGImageDestinationFinalize(dest) else { throw ScanError("Cannot save difference PNG") }
}

func compare(_ cfg: Config) throws -> Result {
    guard (0...254).contains(cfg.channel_tolerance) else { throw ScanError("Invalid channel tolerance") }
    let (w, h, source) = try raster(cfg.source)
    let (ow, oh, output) = try raster(cfg.output)
    guard w == ow, h == oh else { throw ScanError("Source/output dimensions differ") }
    try validate(cfg.protected, w, h)
    try validate(cfg.editable, w, h)
    let count = w * h
    var mask = [UInt8](repeating: 0, count: count)
    for region in cfg.protected {
        let r = region.rect
        for y in r[1]..<r[3] { for x in r[0]..<r[2] { mask[y * w + x] = 2 } }
    }
    for region in cfg.editable {
        let r = region.rect
        for y in r[1]..<r[3] {
            for x in r[0]..<r[2] {
                guard mask[y * w + x] != 2 else { throw ScanError("Editable region overlaps protection: \(region.id)") }
                mask[y * w + x] = 1
            }
        }
    }
    var delta = [UInt8](repeating: 0, count: count)
    var diff = [UInt8](repeating: 0, count: count * 4)
    var protected = Stats(), unchanged = Stats(), editable = Stats()
    for i in 0..<count {
        let x = i % w, y = i / w, offset = i * 4
        var d = 0
        for channel in 0..<4 { d = max(d, abs(Int(source[offset + channel]) - Int(output[offset + channel]))) }
        delta[i] = UInt8(d)
        switch mask[i] {
        case 2: protected.add(d, x, y, cfg.channel_tolerance)
        case 1: editable.add(d, x, y, cfg.channel_tolerance)
        default: unchanged.add(d, x, y, cfg.channel_tolerance)
        }
        // Black=identical, cyan=editable change, amber=within tolerance, red=unexpected change.
        if d > 0 {
            if mask[i] == 1 { diff[offset + 1] = 200; diff[offset + 2] = 255 }
            else if d <= cfg.channel_tolerance { diff[offset] = 255; diff[offset + 1] = 180 }
            else { diff[offset] = 255 }
        }
        diff[offset + 3] = 255
    }
    guard protected.pixels + unchanged.pixels > 0 else {
        throw ScanError("No preserved pixels left to check; editable regions cover the whole image")
    }
    func regionStats(_ regions: [Region]) -> [RegionStats] {
        return regions.map { region in
            var stats = Stats()
            let r = region.rect
            for y in r[1]..<r[3] {
                for x in r[0]..<r[2] { stats.add(Int(delta[y * w + x]), x, y, cfg.channel_tolerance) }
            }
            return RegionStats(id: region.id, rect: r, stats: stats)
        }
    }
    try saveDiff(diff, w, h, cfg.diff_image)
    return Result(width: w, height: h, pixels_scanned: count,
                  pixel_space: "sRGB premultiplied RGBA8; original dimensions; top-left coordinates",
                  protected: protected, unchanged: unchanged, editable: editable,
                  protected_regions: regionStats(cfg.protected), editable_regions: regionStats(cfg.editable),
                  unexpected_pixels: protected.above_tolerance_pixels + unchanged.above_tolerance_pixels)
}

do {
    guard CommandLine.arguments.count == 2 else { throw ScanError("usage: compare_pixels.swift CONFIG.json") }
    let cfg = try JSONDecoder().decode(Config.self, from: Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1])))
    let result = try compare(cfg)
    let encoder = JSONEncoder(); encoder.outputFormatting = [.sortedKeys]
    print(String(decoding: try encoder.encode(result), as: UTF8.self))
    exit(result.unexpected_pixels == 0 ? 0 : 2)
} catch {
    fputs("\(error)\n", stderr)
    exit(1)
}
