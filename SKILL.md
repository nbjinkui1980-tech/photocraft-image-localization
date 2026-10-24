---
name: photocraft-image-localization
description: Translate or revise text in local images with Codex vision and PhotoCraft MCP, preserving artwork and exporting editable PCraft plus preview images. Use for image localization, source-to-target review, typography repair, or batch revision in PhotoCraft.
---

# PhotoCraft image localization

Use Codex to read and translate images and PhotoCraft MCP to edit them. PhotoCraft is the editor, not the OCR or translation model. Do not call an external translation service or image generation model unless the user requests it.

## Choose the requested mode

- **Translate:** localize source images into a target language.
- **Back-check:** pair visible source phrases with current translations and classify each as accurate, needs polishing, mistranslated, missing, or uncertain.
- **Layout review:** inspect current outputs for typography, alignment, contrast, spacing, overflow, and occlusion; edit only images with visible problems.
- **Revise and replace:** create a verified new version, then remove prior related outputs only when the user explicitly requests deletion.

## Target language

Support the language or locale specified by the user, including multiple targets when requested. Use one output set and terminology table per target, with a language tag such as `en`, `vi`, `th`, `ja`, or `ar`. Do not assume Vietnamese. Preserve accents, select fonts that support the actual script, and preview shaping and reading direction for RTL or complex scripts. If the available renderer cannot render the script correctly, report that limitation instead of exporting a known-broken result. Follow the user's terminology preference; English material names are an option, not a universal default.

## Shared workflow

1. Enumerate source images, target language, current output variants, and the exact requested scope. Inspect each relevant image at original resolution.
2. Before editing, build a source-to-target ledger for every clear phrase and a protected-elements ledger for logos, brand marks, product identifiers, numbers, units, standards, icons, and required original-language marks. Preserve claim strength. Mark uncertain text instead of inventing it. For terminology and report-image rules, read [references/translation-policy.md](references/translation-policy.md).
3. Open the source or newest editable `.pcraft` with PhotoCraft. Discover current commands with `command_list`; do not rely on remembered command identifiers or parameters.
4. Preserve the original image. For raster text removal, use tight glyph-shaped selections and content-aware repair. Prefer a sampled background fill on flat areas. Use modest feathering or blur only on already smooth backgrounds. Do not hide damage with an opaque panel or redraw a large background region.
5. Add or update editable text layers. Match the original hierarchy while adapting the layout to the target language. Repeated labels, rows, columns, and cards must use a shared grid and shared typography rather than independent placements. Read [references/layout-review.md](references/layout-review.md) when text length or typography is part of the task. After creating or resizing a text layer, intersect the bounds returned by `type.create` (or `type.info`) with the protected-elements ledger boxes; report any overlap instead of shipping it.
6. Run content review before visual review. At original size, check protected elements, residual glyphs, repair seams, missing or wrong text, font fallback, hierarchy, alignment, line spacing, contrast, margins, overflow, and overlap. Correct visible defects before continuing. Verify every repair patch at ≥100% zoom before saving: when the render preview is smaller than the canvas, duplicate and crop to each repair site. A reduced full-frame preview cannot reveal patch seams or subtle tone mismatches. Any repair applied after a review resets that image's review status — re-review the changed areas at ≥100%. Before repairing a defect, zoom into the source and record the defect's exact bounding box; after repairing, compare before and after across that same region at a verified pixel scale. Treat grid samples and scan results as supporting evidence only. Never verify a repair with a few point samples or a full-frame preview — point samples land on clean pixels beside the defect, and small-crop previews are rescaled in ways that can both invent phantom artifacts and hide real ones.
7. Save a distinct `.pcraft` and `.png`. Verify that both are non-empty and that the PNG dimensions match the source. Report failures individually; never silently skip an image.

## Batch and multi-agent work

Use multiple agents only when the user explicitly requests them. Assign disjoint image ranges and exclusive file ownership. Confirm each worker has an independent PhotoCraft session before concurrent editing. File ownership alone does not isolate the active document. If session isolation is unavailable or unknown, parallelize analysis only and serialize all PhotoCraft edit/select/save sequences through one owner. Workers must not delete shared old outputs. The lead agent performs merged visual review, mechanical verification, and authorized cleanup.

For batch review, read [references/batch-review.md](references/batch-review.md). When one image reveals a repeatable defect, inspect every image in the approved batch for the same pattern. A user correction to an example image becomes an acceptance criterion for matching structures in that batch, while unrelated images and content remain out of scope.

PhotoCraft action batches replay identical coordinates and parameters. For varied images, inspect and place text image by image rather than applying one coordinate set to the whole batch.

## Output replacement

When deletion is authorized, first create a new uniquely named version. Delete an older variant only after its replacement PNG and PCraft exist, are non-empty, match source dimensions, and pass visual review. Reopen each saved PCraft in PhotoCraft and confirm its editable layers and rendered appearance before authorizing cleanup. Preserve source images and unaffected outputs. After cleanup, confirm every source still has one current PNG and one current PCraft.

Reusable helpers are in `scripts/`:

- `extract_pcraft_text.py`: extract editable text from PCraft manifests.
- `contact_sheets.swift`: build review sheets from PNG files.
- `verify_outputs.py`: check pairs and dimensions with macOS `sips`.
- `diff_scan.swift`: flag small-but-consistent tone-mismatch cells (patch seams) between source and output; large text-edit diffs are counted only. Effective only on flat solid or light-gradient backgrounds; it cannot isolate residual glyphs or smears inside text-edit zones, and loses selectivity on low-contrast or textured art — there, ≥100% zoomed human review is the only reliable check.
- `find_dark.swift`: scan a rect for pixels below a luminance threshold and print their bbox plus an ASCII map. Use only to locate pixels below the selected threshold in a valid, fully in-bounds region. It reports scanned pixel count and rejects empty or out-of-bounds regions. Zero matches cannot prove absence of residual text: faint, colored, or light glyphs may be missed and legitimate artwork may match. There is no light-pixel mode; inspect light text visually.
- `cleanup_versions.py`: list old variants by default; deletion requires explicit `--delete`.

For exact-list cleanup usage and required evidence, read [references/output-cleanup.md](references/output-cleanup.md). Integrity scripts do not certify visual quality or renderer compatibility.
