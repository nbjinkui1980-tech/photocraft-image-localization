---
name: photocraft-image-localization
description: Translate or revise text in local images with Codex vision and PhotoCraft MCP, preserving artwork and exporting editable PCraft plus preview images. Use for image localization, source-to-target review, typography repair, or batch revision in PhotoCraft.
---

# PhotoCraft image localization

Use Codex for image understanding and translation, and PhotoCraft MCP for editing. Honor existing authorization for external translation services or image-model repair; otherwise do not invoke them.

## Select the requested scope

- **Review / back-check:** read images and text, pair source and target phrases, and report accurate, polish-only, mistranslated, missing, or uncertain items. Do not modify image files.
- **Layout repair:** preserve confirmed wording, brands, numbers, and artwork; adjust the affected typography and geometry. Line breaks and approved casing may change.
- **Translation / content revision:** verify meaning and terminology, then reflow the affected text. Do not rewrite unrelated approved phrases.
- **Revise and replace:** verify new outputs, then remove exact old variants only when deletion is authorized.

Apply corrections across matching structures in the approved batch. Keep isolated-image requests limited to that image. Recheck changed areas and dependent groups after each revision; do not restart all work after a small adjustment.

## Target language and font preflight

Use the user's language or locale, one output set and terminology table per target (`en`, `vi`, `th`, `ja`, `ar`, etc.). English material names are a task preference, not a universal default. For ambiguous text or claims, preserve uncertainty; do not invent product functions or formal brand spellings. Read [translation-policy](references/translation-policy.md).

Before batch editing, render representative **actual target phrases** containing accents, non-Latin characters, numbers, and mixed English terms in a scratch document. Inspect missing-font warnings, partial glyph fallback, mark placement, and any RTL joining or direction. Font-family equality alone is not proof of consistent rendering. Use one supported style per role; if rendering is unsupported, report the limitation rather than export known-broken text. Do not claim untested languages are verified.

## Prepare and edit

1. Enumerate original sources, current variants, target languages, and affected images. Record source phrases, confirmed translations, protected regions, layer IDs, and current outputs in one task JSON using [task-state](references/task-state.md). Reuse the current entries on resume and invalidate reviews when file hashes change.
2. Verify source meaning, units, names, and claim strength **before** expensive background repair. Define cells, guides, styles, and viewing-size requirements for repeated structures. Trial-render long translations on a scratch copy. Validate one representative per recurring layout, then apply its rules without reusing unrelated image coordinates. Agent checks suffice unless genuine ambiguity requires user input.
3. Discover relevant PhotoCraft commands and allowed read/write roots once per session; refresh after a relevant error or capability change. Keep document identity explicit. Separate fixed action replay from MCP `command_batch`: each MCP step can have different parameters. Batch already-planned edits on one document; inspect each result. Batches are not atomic: keep successful earlier steps and resume from the failure after inspecting state, never blindly replay the whole batch.
4. Before selection expansion, fill, blur, clone, or other raster repair, check its full effect region against the protected regions. Run `check_layout.py --phase pre-repair` for declared rectangular extents; narrow the operation if it intersects protection. Keep source pixels available for recovery. Avoid whole-image repainting, opaque cover panels, and blur on detailed texture. Use gradients only on smooth gradient backgrounds.
5. Verify the cleaned background locally before adding text. Edit or create editable text layers. Apply shared styles, cell geometry, and per-line alignment from [layout-review](references/layout-review.md). Wrap first, adjust layout second, and reduce shared size only while still readable. Do not independently shrink a long field to force a fit.
6. Save a uniquely named working PCraft and collect current `type.info` results for the checked text groups. Bind the snapshot to that saved file's hash and run `check_layout.py` as documented in [task-state](references/task-state.md). Also inspect uncovered text and protected pixels visually; the geometry tool does not assess the entire raster image.
7. Export a pending candidate PNG and run the original-size region comparison and delivery gate in [source-comparison](references/source-comparison.md). Inspect unexpected changes and every editable region, then reopen the saved PCraft and review the actual deliverables. Use a full-frame preview for composition, verified 1:1 crops for repairs and brand details, and intended display size for readability. After repairs, repeat review of affected regions and dependent groups. Report failed or unrepairable images individually.

## Batch production

For any batch, follow the command sequence in [fast-pipeline](references/fast-pipeline.md): `task_tool.py` scaffolds and records task evidence, `review_sheet.py` produces one set of 1:1 review pages per image, and `batch_verify.py --jobs` checks the batch in parallel. Do not hand-edit hashes or review fields. For multiple images or target languages, also read [batch-production](references/batch-production.md). Prepare session capabilities once, and cache font checks only for matching language/font/render settings. Validate one clean-background PCraft per original and duplicate it for each language; keep the original as the final comparison baseline. Plan complete per-image text edits before MCP batches, retain full results locally, and return short summaries plus necessary previews. Reuse unchanged evidence and resume only stale/pending stages; never skip each final image's visual review.

Use `batch_verify.py` after candidate export and type-info collection to chain integrity, clean-base, plan, geometry and pixel checks. It does not perform MCP editing or visual approval. In production mode, bind candidate and reviewed plans with `candidate_plan_sha256` and `review_plan_sha256` as described in the reference. Both adaptation and production modes use the same delivery/cleanup standards.

## Batch adaptation of existing outputs

To bring an existing localized set (for example `v1` outputs) up to the delivery standard, or to apply batch wording/typography corrections on it, read [batch-adaptation](references/batch-adaptation.md). The background repair is already done, so the cost is the evidence pipeline, but two pitfalls dominate. First, classify each base with `classify_baseline.swift`: only a background preserved outside the text may keep the original source as the comparison baseline; a re-rendered gradient/photo makes the whole canvas differ and must be excluded or gated against the prior output instead. Second, derive editable regions from the change footprint with `repairmap.swift` + `cluster_rects.py` rather than hand-measuring, then require zero unexpected pixels and review the difference image. For poster/headline layouts an empty `layout.groups` skips per-layer type snapshots (the main per-image cost); keep snapshots for structured grids.

## Batch coordination

Read [batch-review](references/batch-review.md) for repeated defects. Use multiple agents only when explicitly requested. Assign disjoint files and the same layout/terminology criteria. Concurrent PhotoCraft editing requires verified independent sessions. Otherwise parallelize analysis only and serialize all document select/edit/save sequences through one owner. Workers never delete shared old outputs.

The lead checks cross-image consistency and actual saved outputs. Do not accept a collage alone as proof of original-size repair quality or legible mobile text.

## Verify and replace

Require a passing `compare_source.py --check` for each image before marking it delivered or publishing its candidate files. A missing, failed or stale comparison blocks acceptance and old-version deletion. Candidate export is necessary for the check and is not delivery. Use `verify_outputs.py` for archive/dimension checks, and `--hashes` to capture source/PNG/PCraft fingerprints before and after review. Only record passed review against identical bytes. File changes invalidate the prior review automatically at cleanup. Read [output-cleanup](references/output-cleanup.md) for exact filenames and hash-bound deletion. Preserve originals, unaffected variants, and other target languages.

Helpers in `scripts/` (run Swift helpers as `python3 scripts/swift_tool.py NAME ARGS...` for a cached optimized build):

- `task_tool.py`: `init` task entries, `fresh-report`, `record-plan`, and `record-review` bound to the reviewed bytes; refuses to record a pass the delivery gate would reject.
- `review_sheet.py` / `review_sheet.swift`: per-image 1:1 source/candidate/diff region pages plus a display-size overview and a hash manifest for `record-review --before`.
- `swift_tool.py`: compile-once cache for all Swift helpers.

- `batch_verify.py`: compact per-item verification summary, validated pixel-report reuse, and continuation after individual failures.
- `extract_pcraft_text.py`: JSONL text, visibility flags, style runs, transforms and paragraphs; not a rendered-visibility guarantee.
- `check_layout.py`: declared cell/style/per-line alignment, collision and pre-repair protection checks. Requires current PhotoCraft evidence for final layout checks.
- `compare_source.py` / `compare_pixels.swift`: full-resolution protected/unchanged-region checks, difference reports/images and a delivery gate tied to file hashes and region policy. Editable-region quality still requires visual review.
- `contact_sheets.swift`: batch composition previews. Use fresh review directories to avoid stale sheets.
- `verify_outputs.py`, `cleanup_versions.py`: integrity checks, fingerprints, and explicit-list cleanup (dry run by default).
- `diff_scan.swift`: downsampled tone-difference hints on smooth backgrounds; not proof of a clean repair.
- `find_dark.swift`: below-threshold pixel counts in a valid region. Zero matches cannot rule out faint, colored or light residual text; legitimate art can also match. No light-pixel mode is provided.
- `classify_baseline.swift`: grid-sample a source and an existing output to decide whether the background is preserved (valid source baseline) or redesigned (exclude or gate against the prior output).
- `repairmap.swift`: connected-component rects of the change footprint between two images, plus baseline statistics and canvas size. Use to derive editable masks for batch adaptation.
- `cluster_rects.py`: merge footprint fragments whose edges lie within `--gap` px into per-text-group editable boxes; reports the largest box's canvas share, which must stay well below whole-canvas coverage.
- `outside_editable_scan.swift`: list above-tolerance source-vs-candidate pixels that fall outside the declared editable regions, to locate and diagnose `compare_source.py` failures. (Distinct from `diff_scan.swift`, which is a downsampled tone-difference hint.)

`classify_baseline`, `repairmap` and `outside_editable_scan` decode pixels exactly like `compare_pixels.swift` (sRGB premultiplied RGBA8, alpha included), so their counts agree with the delivery gate. Keep their shared loader block identical when changing any of them.

Run `python3 scripts/test_workflow.py` for layout/cleanup regressions, `python3 scripts/test_source_comparison.py` for original-comparison/delivery regressions, `python3 scripts/test_scans.py` for scan regressions, `python3 scripts/test_adaptation.py` for batch-adaptation helper regressions, and `python3 scripts/test_tools.py` for task/review/cache/parallel tooling regressions when those helpers change. Image dimensions and Swift helpers currently require macOS. Do not equate script success with translation, visual, or cross-platform acceptance.
