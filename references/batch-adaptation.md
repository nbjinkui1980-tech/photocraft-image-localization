# Batch adaptation of existing localized outputs

Use this when you already have localized outputs (for example a `v1` set) and want to
bring them to the delivery standard — task JSON, original-size comparison, delivery
gate — or apply wording/typography corrections, across many images. This is distinct
from production mode ([batch-production](batch-production.md): build a clean base from
the source, then duplicate per language) and from single-image adaptation. Here the
base is an **existing localized output**, not the source, so the background repair is
already done and the per-image cost is the evidence pipeline, not inpainting.

## Step 0 — classify each base: is the source baseline valid?

The delivery gate compares the candidate against the **original source**. That is only
meaningful if the existing output preserved the source background outside the text. Do
not assume it: some outputs re-render the background (a lighter gradient, a graded or
replaced photo) and will fail the source comparison across the whole canvas by design.

```sh
swift scripts/classify_baseline.swift SOURCE CANDIDATE
```

It grid-samples both images and reports the median per-channel difference and the
fraction of samples above tolerance:

- **Preserved:** median ≈ 0 and only sparse (text-area) samples exceed tolerance. The
  source is a valid baseline; proceed.
- **Redesigned:** high median and most samples differ (a re-lightened gradient measures
  median 13 with ~77% of samples > 6). The source baseline is invalid. Exclude the
  image, or gate it against the **prior output** (not the source) under an explicit
  policy. Never declare the whole image editable to force a pass — the gate rejects
  masks with no preserved pixels, and the mask would hide the redesigned background.

## Derive editable regions fast, then verify

Hand-measuring protected/editable masks per image is the batch bottleneck and is
error-prone: a repair feather or antialias rim 1–4 px outside a hand-drawn mask fails
the gate as "unexpected pixels". Derive the mask from the change footprint instead:

```sh
swift scripts/repairmap.swift SOURCE V1PNG TOL MIN_AREA DILATE   # per-fragment rects + baseline stats
python3 scripts/cluster_rects.py REPAIRMAP.json --gap 40 --margin 6 --width W --height H
```

- `repairmap` diffs source vs the existing output and emits connected-component rects
  of the changed footprint (removed source text + localized text + repair).
- `cluster_rects` merges fragments into per-text-group boxes. Text over a **clean**
  background yields a few group boxes. Text over a **photo/texture** fragments into many
  tiny rects; the real editable unit there is the whole inpainted text element, so
  cluster into that element's box — but never let one box reach ~100% of the canvas
  (shrink `--gap` so distinct elements stay separate).

If you re-word a layer into a **longer** translation that can exceed the existing text
footprint, add that layer's rendered `type.info` bounds plus a small margin as an extra
editable region. Same-length or shorter replacements stay inside the derived mask.

**The derived mask is a starting candidate, not a pass.** Run `compare_source.py`; it
must report zero unexpected pixels. Then read the difference image (cyan must be
confined to text) and the full render. If the gate fails, revisit the layout or the
mask derivation — do not expand masks to hide the failure (see
[source-comparison](source-comparison.md)). The exception is absorbing genuine text-edge
antialias/JPEG-ringing rims into the footprint via the cluster margin, which is part of
the text/repair area by definition.

## Tolerance

Calibrate per source with an **unedited PhotoCraft roundtrip** (open the source, export
a PNG unchanged, compare): use the measured maximum, with a `tolerance_reason`. Do not
copy a tolerance from another image — it is a property of that source's compression and
color handling, not a global constant.

## Layout snapshot is optional for simple layouts

`batch_verify.py` runs the geometry check (`check_layout`) only when `layout.groups` is
non-empty. For posters, banners and single headlines, leave `groups` empty and rely on
the pixel gate plus visual review — this skips per-layer `type.info` collection, the
main per-image cost. Keep groups and bound type snapshots for structured grids
(columns, tables, aligned label/value rows) where geometry evidence matters; collect
them as in [task-state](task-state.md).

## Measured timing (macOS)

- PhotoCraft open / edit / save / export / close: **~0.26 s** per image.
- Full-resolution `compare_source` (report + difference image): **~2 s** per image.
- Delivery gate (`batch_verify`, reusing the report): **~0.14 s** per image.
- Steady state ≈ **2.5 s per image** of machine time. Plan review time separately.

## Review standards are unchanged

Batch speed does not relax delivery: reopen every saved PCraft and confirm the text is
editable, set `photocraft_reopened`/`visual_passed` only after real review, inspect
every editable region (difference image plus full render at intended size), record
`review_hashes` and `review_report_sha256`, then run `batch_verify.py`. Keep
`reviewed_editable_ids` complete. See [source-comparison](source-comparison.md) and
[task-state](task-state.md). Report any image that fails classification, comparison, or
review individually; do not silently drop it from the batch.
