# Task state and geometry evidence

Keep one task JSON list in the task workspace. Each item represents **one source + target language**, and retains current output filenames, unresolved issues, original/target phrases, layer IDs, protected regions and geometry. Update existing items instead of creating competing lists. Do not treat the newest timestamp or a suffix named `final` as evidence of approval.

Use absolute source/snapshot paths. Output names are plain filenames relative to the output directory. `source_sha256` pins the source used to locate protection. `review_hashes` pins the reviewed source/PNG/PCraft bytes and is required for deletion. `comparison` records editable masks, tolerance and a fresh report path; `review_report_sha256` binds the reviewed report and `reviewed_editable_ids` tracks local repair/translation reviews. `photocraft_reopened` and `visual_passed` start false and change only after actual checks. For pure photos or ordinary single headlines, omit unnecessary layout groups and skip the geometry helper; still review the output visually.

Example geometry for two equal columns (adapt all numbers and styles to the actual image):

```json
[
  {
    "source": "/absolute/inputs/item.jpg",
    "source_sha256": "SHA256_OF_ORIGINAL",
    "target_language": "en",
    "png": "item-en-v2.png",
    "pcraft": "item-en-v2.pcraft",
    "old_files": ["item-en-v1.png", "item-en-v1.pcraft"],
    "phrases": [{"key": "material", "source_text": "织物", "target_text": "TEXTILE", "layer": 12, "status": "confirmed"}],
    "protected": [{"id": "logo", "rect": [20, 10, 180, 70]}],
    "repairs": [{"id": "old-caption", "rect": [40, 220, 160, 250], "effect_margin_px": 4}],
    "layout": {
      "canvas": [640, 480],
      "tolerance_px": 2,
      "groups": [{
        "id": "materials",
        "grid": {"rect": [20, 300, 620, 400], "columns": 2, "gap_px": 24},
        "padding_px": 12,
        "align": "center",
        "baseline_y": 345,
        "min_size_pt": 22,
        "style": {
          "font_family": "Arial", "size_pt": 24, "weight": 700,
          "color": {"mode": "Rgb", "c": [0, 0, 0, 0], "alpha": 1},
          "leading_pt": 30, "horizontal_scale": 1, "vertical_scale": 1
        },
        "items": [{"layer": 12, "column": 0}, {"layer": 13, "column": 1}]
      }]
    },
    "type_snapshot": "/absolute/work/item-en-types.json",
    "comparison": {
      "editable": [
        {"id": "old-caption", "rect": [36, 216, 164, 254]},
        {"id": "material-left", "rect": [32, 312, 296, 388]},
        {"id": "material-right", "rect": [344, 312, 608, 388]}
      ],
      "channel_tolerance": 0,
      "report": "/absolute/work/qa/item-en-v2-comparison.json"
    },
    "reviewed_editable_ids": [],
    "issues": [],
    "photocraft_reopened": false,
    "visual_passed": false
  }
]
```

## Geometry contract

All rectangles use `[x0,y0,x1,y1]` in document pixels, with positive area. Convert `doc_inspect` bounds `[x,y,width,height]` before using them. `type.info`/`type.create` use corner bounds; inspect the current schema rather than assuming all commands use the same convention.

A grid divides its container into equal columns after subtracting gaps; each group must declare one item per column. Separate header/value groups may share horizontal boundaries with different vertical bands and baselines. For irregular rows, omit `grid` and give each item `cell` and optionally `baseline_y`; repeated labels/values should share their respective horizontal origins. Alignment applies to **every rendered line**, not just the widest one. Padding applies on all four sides. Choose `min_size_pt` from intended viewing size and check it visually; do not use a universal point-size threshold across canvas sizes.

Declare font, size, weight, color, leading (number or null), and character scales. Optional expected style keys such as `caps`, `italic`, or `tracking` are also compared. Normalize layer transforms to translation for these regular grids; the checker rejects scaled, rotated, vertical or warped text for automatic acceptance. Use manual geometry review for intentionally transformed designs instead of treating unsupported geometry as a pass. All checked text boxes are tested for cell/canvas containment, mutual collisions and protected-region overlap. Conservative bounding-box hits require inspection, not automatic erasure.

For pre-repair checks, declare every operation's affected region plus expansion/feather/filter reach as `effect_margin_px`. Run:

```sh
python3 scripts/check_layout.py TASK.json OUTPUT_DIR --png=item-en-v2.png --phase=pre-repair
```

This checks the **declared** reach only; verify the actual MCP selection and parameters match it. It does not sandbox the editor. After repair, compare protected-region crops against the source before accepting them; geometric non-overlap alone cannot detect an earlier erased logo.

## Collect final layout evidence

Save the candidate PCraft, then collect `type.info` for each declared layer from that same document without editing between collection and validation. Store the decoded results verbatim:

```json
{"pcraft_sha256": "SHA256_OF_SAVED_CANDIDATE", "types": ["REPLACE_WITH_DECODED_TYPE_INFO_OBJECTS"]}
```

Use actual objects, not the illustrative string above. Keep returned `runs`, `lines`, `transform`, `orientation`, `warp`, `warnings`, and `bounds`; do not invent bounds or copy them from the desired specification. Snapshot hashes prevent accidental reuse against a different saved candidate, but cannot certify how the observations were obtained.

```sh
python3 scripts/check_layout.py TASK.json OUTPUT_DIR --png=item-en-v2.png
```

After changing text, geometry, fonts, or raster content, save again, recollect relevant evidence, and repeat affected review. Keep the same task entry and mark it pending until the new bytes pass. Geometry success is not visual or translation approval. Read `output-cleanup.md` before deleting anything.

Final acceptance also requires the original-size region comparison described in `source-comparison.md`. Geometry success, ZIP integrity or a boolean review flag alone does not authorize delivery or cleanup.

For multilingual production, add the optional clean-base reference and candidate/review plan hashes described in `batch-production.md`. These supplement file and pixel evidence. The original remains the comparison source; the cleaned background never replaces it.
