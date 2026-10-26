# Fast per-image pipeline

Use these commands so the agent does not hand-write hashes, report names or evidence fields. They change no acceptance rule: the same comparison, review and delivery gate apply.

```sh
# 1. Once per batch: one entry per source x language, with hashes, names, canvas,
#    fresh report path and detected older versions (existing entries untouched).
python3 scripts/task_tool.py init TASK.json SOURCE_DIR OUTPUT_DIR QA_DIR --langs en,vi --version v2

# 2. Translate once per batch: collect every source phrase into the entries' `phrases`
#    and settle the terminology table before any editing. Then fill `protected`,
#    `comparison.editable` (and `layout.groups` for grids) per image.

# 3. Edit in PhotoCraft (one planned command_batch per document where possible),
#    save PCraft, export the candidate PNG, collect type.info if layout.groups is set.
#    Production entries: python3 scripts/task_tool.py record-plan TASK.json OUTPUT_DIR --png NAME

# 4. Pixel comparison (compiled, cached helper).
python3 scripts/compare_source.py TASK.json OUTPUT_DIR --png=NAME.png
#    A failed or stale attempt needs a new report path:
python3 scripts/task_tool.py fresh-report TASK.json --png NAME.png

# 5. Review material in one fresh directory: 1:1 source/candidate/diff tiles per region
#    plus an overview at the intended display width, and the hashes they show.
python3 scripts/review_sheet.py TASK.json OUTPUT_DIR --png NAME.png --out-dir QA_DIR/review-NAME-01 [--include-protected]

# 6. Inspect every page, reopen the saved PCraft in PhotoCraft, then record what you saw.
python3 scripts/task_tool.py record-review TASK.json OUTPUT_DIR --png NAME.png \
  --before QA_DIR/review-NAME-01/review.json --reviewed-ids all --reopened --visual-passed
#    Defects instead: omit --visual-passed and add --issue "..." (repeatable); fix, compare
#    with a fresh report, regenerate pages, record again with --clear-issues.

# 7. Whole batch, in parallel; reuses matching reports, never edits or deletes.
python3 scripts/batch_verify.py TASK.json OUTPUT_DIR --summary=QA_DIR/batch-check-01.json [--jobs 8]
```

`record-review` refuses to write when the files differ from `--before`, the comparison is missing/failed/stale, issues remain, or the delivery gate would reject the result, so a written pass always satisfies `compare_source.py --check`. Pass `--reviewed-ids all` only after actually inspecting every region on the pages; otherwise list the IDs you inspected.

The review pages show 1:1 pixels within `--page` (default 1568 px, the size most vision inputs keep unscaled), so one image read replaces many crop requests. Pages are review material, not a verdict. Brand details that need closer inspection still deserve a dedicated crop.

Swift helpers run through `scripts/swift_tool.py NAME ARGS...`: compiled with `-O` once per source/toolchain into `~/.cache/photocraft-image-localization` (override with `PHOTOCRAFT_TOOL_CACHE`). Measured on a 2000x2000 image: pixel comparison about 0.6 s instead of 2.8 s, repairmap about 1 s instead of 5 s.
