import AppKit
import Foundation

let args = Array(CommandLine.arguments.dropFirst())
guard args.count >= 2 else {
    fputs("usage: contact_sheets.swift OUTPUT_DIR IMAGE...\n", stderr)
    exit(1)
}
let outputDir = URL(fileURLWithPath: args[0], isDirectory: true)
let files = args.dropFirst().map { URL(fileURLWithPath: $0) }
try FileManager.default.createDirectory(at: outputDir, withIntermediateDirectories: true)

for file in files {
    guard NSImage(contentsOf: file) != nil else {
        fputs("Cannot read image: \(file.path)\n", stderr)
        exit(1)
    }
}
var rendered = 0
let cell = NSSize(width: 720, height: 900)
let labelHeight: CGFloat = 44
for start in stride(from: 0, to: files.count, by: 4) {
    let page = Array(files[start..<min(start + 4, files.count)])
    let canvas = NSImage(size: NSSize(width: cell.width * 2, height: cell.height * 2))
    canvas.lockFocus()
    NSColor(calibratedWhite: 0.12, alpha: 1).setFill()
    NSRect(origin: .zero, size: canvas.size).fill()
    for (offset, file) in page.enumerated() {
        guard let source = NSImage(contentsOf: file) else { fputs("Image became unreadable\n", stderr); exit(1) }
        rendered += 1
        let col = offset % 2
        let row = 1 - offset / 2
        let origin = NSPoint(x: CGFloat(col) * cell.width, y: CGFloat(row) * cell.height)
        let box = NSRect(x: origin.x + 10, y: origin.y + labelHeight + 10,
                         width: cell.width - 20, height: cell.height - labelHeight - 20)
        let scale = min(box.width / source.size.width, box.height / source.size.height)
        let size = NSSize(width: source.size.width * scale, height: source.size.height * scale)
        source.draw(in: NSRect(x: box.midX - size.width / 2, y: box.midY - size.height / 2,
                              width: size.width, height: size.height))
        (file.lastPathComponent as NSString).draw(
            at: NSPoint(x: origin.x + 12, y: origin.y + 10),
            withAttributes: [.font: NSFont.boldSystemFont(ofSize: 22), .foregroundColor: NSColor.white]
        )
    }
    canvas.unlockFocus()
    guard let tiff = canvas.tiffRepresentation,
          let bitmap = NSBitmapImageRep(data: tiff),
          let png = bitmap.representation(using: .png, properties: [:]) else { fputs("PNG encoding failed\n", stderr); exit(1) }
    try png.write(to: outputDir.appendingPathComponent(String(format: "sheet-%02d.png", start / 4 + 1)))
}

guard rendered == files.count else { exit(1) }
print("Rendered \(rendered) of \(files.count) images")
