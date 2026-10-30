# Batch adaptation of existing localized outputs

Use this when you already have localized outputs (for example a `v1` set) and want to
bring them to the delivery standard — task JSON, original-size comparison, delivery
gate — or apply wording/typography corrections, across many images. This is distinct
from production mode ([batch-production](batch-production.md): build a clean base from
the source, then duplicate per language) and from single-image adaptation. Here the
base is an **existing localized output**, not the source, so the background repair is
already done and the per-image cost is the evidence pipeline, not inpainting.

For a new set, run `calibrate_adaptation.py PAIRS.json` first: it does the baseline
classification and the tolerance/gap measurement below in one pass and reports
recommended parameters. The sections that follow explain what it is doing and when to
override it.

## Step 0 — classify each base: is the source baseline valid?

The delivery gate compares the candidate against the **original source**. That is only
meaningful if the existing output preserved the source background outside the text. Do
not assume it: some outputs re-render the background (a lighter gradient, a graded or
replaced photo) and will fail the source comparison across the whole canvas by design.

```sh
python3 scripts/swift_tool.py classify_baseline SOURCE CANDIDATE
```

It grid-samples both images and reports the median per-channel difference and the
fraction of samples above tolerance:

- **Preserved:** median ≈ 0 and only sparse (text-area) samples exceed tolerance. The
  source is a valid baseline; proceed.
- **Redesigned:** high median and most samples differ (a re-lightened gradient measures
  median 13 with ~77% of samples > 6). The source baseline is invalid for the existing
  output. Decide *why* it was redesigned:
  - **Unintentional repaint** (the localizer re-rendered the whole background instead of
    preserving it): rebuild from the source in production mode — clean the source text
    onto a verified clean base, localize on it, and gate against the source as usual.
    This yields a better output than the repaint (the original background is preserved).
    The rebuild uses the same delivery gate; the clean base is verified against the
    source before text is added. See [batch-production](batch-production.md).
  - **Intentional redesign** (the new background is the accepted design): keep it and
    gate the new candidate against the prior output, not the source — point the task's
    comparison reference at the prior output under an explicit, recorded policy.
  Never declare the whole image editable to force a pass — the gate rejects masks with
  no preserved pixels, and the mask would hide the redesigned background.

## Derive editable regions fast, then verify

Hand-measuring protected/editable masks per image is the batch bottleneck and is
error-prone: a repair feather or antialias rim 1–4 px outside a hand-drawn mask fails
the gate as "unexpected pixels". Derive the mask from the change footprint instead:

```sh
python3 scripts/swift_tool.py repairmap SOURCE V1PNG TOL MIN_AREA DILATE   # per-fragment rects + baseline stats
python3 scripts/cluster_rects.py REPAIRMAP.json --gap 40 --margin 6   # canvas size read from REPAIRMAP.json
```

- `repairmap` diffs source vs the existing output and emits connected-component rects
  of the changed footprint (removed source text + localized text + repair), plus the
  canvas `width`/`height`. Its pixel decoding matches `compare_pixels.swift`, including alpha.
- `cluster_rects` grows each rect by `--margin`, then merges boxes whose edges are at most
  `--gap` px apart on both axes. Pass `--width/--height` for older repairmap files without
  canvas size; the helper refuses to guess it. Text over a **clean**
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

The delivery gate's `channel_tolerance` must cover the diffuse background noise floor of
the specific source set, which varies with JPEG compression and color handling. Do not
copy it from another set. Measure it:

- For a whole set at once, run `calibrate_adaptation.py PAIRS.json`. It classifies each
  output, measures each preserved one's background floor with `background_floor.swift`
  (strong text removed, the ringing halo dilated away, the residual background ceiling is
  the floor), recommends `channel_tolerance` and the cluster `gap`/`margin` scaled to the
  set's image width, and validates coverage on a sample. A `floor_max` far above
  `floor_p999` is a thin hot tail — a suspected localized defect (repair seam, missed
  mark), not diffuse noise; locate it with `outside_editable_scan.swift` and fix or
  exclude it rather than raising the tolerance to hide it.
- For one image under the policy's strictest reading, calibrate with an unedited
  PhotoCraft roundtrip (open the source, export a PNG unchanged, compare): use the
  measured maximum, with a `tolerance_reason`. For a preserved output the
  `background_floor` ceiling equals this roundtrip floor, because the output's
  background is the editor's own rendering of the source.

Either way, record the value and the reason in the task entry.

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
