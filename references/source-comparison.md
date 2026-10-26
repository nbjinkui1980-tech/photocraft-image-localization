# Original-size comparison and delivery gate

## Declare allowed changes before editing

Use the existing task JSON. Retain the original as `source` and pin `source_sha256`. Declare `protected` regions for logos, product details, icons and required marks. Declare `comparison.editable` as the union of tight old-text repair areas and planned new-text footprints, including necessary antialiasing/feather/filter margins. Use integer corner coordinates `[x0,y0,x1,y1]` with an exclusive right/bottom edge.

Protected and editable regions must not intersect. Everything outside editable regions is checked, even if it was not explicitly identified as protected. Do not derive editable areas from all observed differences or expand them simply to make a failed result pass. Revisit the approved layout if a genuine text reflow needs a new footprint; then rerun the comparison and affected visual review. Whole-image editable masks with no preserved pixels are rejected.

Deriving a mask from observed differences is distinct from expanding one to hide a failure, and is permitted only as a verified starting point: when adapting an **existing** output whose edits are already authorized (its background repair and localized text are known, accepted changes), the source-vs-output difference footprint *is* that authorized edit set, so `repairmap.swift` + `cluster_rects.py` may generate the initial editable regions. The derivation is valid only if it is then proven, not assumed: the comparison must report zero unexpected pixels, nothing outside the mask may change, and the difference image plus full render must confirm the mask covers only text/repair, never product or artwork. If the gate fails, fix the layout or the derivation — never widen the mask to pass. See [batch-adaptation](batch-adaptation.md).

Add this block to each task item:

```json
{
  "protected": [{"id": "brand", "rect": [880, 500, 1340, 600]}],
  "comparison": {
    "editable": [
      {"id": "old-heading", "rect": [100, 160, 620, 340]},
      {"id": "translated-heading", "rect": [100, 230, 920, 330]}
    ],
    "channel_tolerance": 0,
    "report": "/absolute/work/qa/item-en-v2-comparison.json"
  },
  "reviewed_editable_ids": []
}
```

These are illustrative coordinates. Use the actual authorized regions. Store reports in a separate QA directory, not alongside source/candidate files. Select a fresh report filename on every comparison attempt; existing reports and their difference images are not overwritten.

## Compare the exported candidate

Export a candidate PNG first: comparison needs the actual deliverable bytes, not only an editor preview. Keep it marked pending. Run:

```sh
python3 scripts/compare_source.py TASK.json OUTPUT_DIR --png=item-en-v2.png
```

The helper checks the candidate pair, then compares **every pixel at original dimensions**, including single-pixel right/bottom edge changes. Both images are decoded into the same sRGB, premultiplied RGBA8 representation. Alpha is compared as well. There is no resize, alignment optimization, automatic background repair or region expansion. This is equality/tolerance of normalized rendered pixels, not equality of compressed bytes, hidden RGB under full transparency, or higher-bit-depth samples.

Default `channel_tolerance: 0` flags any channel change in preserved areas. A nonzero value requires `tolerance_reason`, calibrated from an unedited export roundtrip rather than chosen to hide detected defects. Reports retain counts of *all* changed pixels and maximum channel deltas even below tolerance. Any single preserved pixel above tolerance fails; there is no allowed-change percentage that can hide a small erased logo.

The command writes a JSON report with counts and bounding boxes for protected, unchanged and editable regions, plus a native-size `.diff.png`:

- black: identical normalized pixels;
- cyan: changes inside declared editable regions;
- amber: preserved-region differences within explicit tolerance;
- red: unexpected preserved-region changes above tolerance.

Exit 0 means pixel preservation passed under the declared policy, not that the image is ready. Exit 2 means detected violations; the report/difference image is still saved for diagnosis. Exit 1 means invalid input, unsupported decoding or another execution failure; do not treat it as a pass. The native helper rejects mismatched dimensions, non-normal EXIF orientation, multiple frames and images over 50 million pixels rather than silently normalize or downsample them. Report these limitations; do not silently replace the original source with a different baseline.

## Review regions and finish delivery

Inspect each reported anomaly with matching source/candidate crops at 1:1 scale. Fix unintended changes with PhotoCraft and compare the saved candidate again. Inspect each editable region for residual source text, repair seams, texture damage, translation accuracy, font issues, overflow and occlusion. Pixel differences inside those regions are expected and cannot certify these qualities. Also run declared layout checks and inspect the full image at intended viewing size.

Reopen the saved PCraft and inspect the exported PNG. Capture `verify_outputs.py --hashes` fingerprints before and after review; they must match. After real review, set `photocraft_reopened` and `visual_passed`, record `review_hashes`, put every reviewed editable region ID into `reviewed_editable_ids`, clear resolved `issues`, and record the comparison JSON's SHA-256 as `review_report_sha256`. Compute it with the existing `sha256_file` helper or a platform SHA-256 command. Prefer `task_tool.py record-review --before REVIEW_DIR/review.json` (see [fast-pipeline](fast-pipeline.md)), which writes these fields from the actual bytes and refuses a pass the gate would reject. Do not fabricate engine results or refresh approval hashes without re-review.

Then run the delivery gate:

```sh
python3 scripts/compare_source.py TASK.json OUTPUT_DIR --png=item-en-v2.png --check
```

This requires matching current source/PNG/PCraft bytes, an unchanged region/tolerance policy, a passing full-resolution report, its intact difference image, successful review flags, review of every editable region and no unresolved issues. Any edit to files, masks or tolerance invalidates prior evidence. Run this check before claiming delivery or copying candidates to a final destination. It governs the supplied workflow; it does not intercept arbitrary direct MCP export calls or independently prove that recorded visual review happened.

`cleanup_versions.py --delete` invokes this same gate for every item and rechecks before deleting. Missing/stale/failed comparison evidence blocks cleanup even if old boolean flags say passed. Older task manifests remain usable for dry-run listing but must gain current comparison evidence before deletion.
