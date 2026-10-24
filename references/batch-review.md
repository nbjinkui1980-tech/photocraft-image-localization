# Batch review and correction propagation

## Detect repeated problems

Build contact sheets for the current output set and inspect both the whole batch and original-size candidates. Group findings by pattern rather than only by filename:

- missing or covered logo and brand marks;
- same-level labels with different sizes, colors, casing, or weight;
- rows whose labels or values start on different guide lines;
- unevenly distributed columns;
- long translations leaving their intended cell;
- repeated supporting text that is too small or low contrast;
- repeated repair seams, residual glyphs, or opaque patches;
- solid-color repair patches on gradient or textured backgrounds (visible rectangles) — use locally sampled gradient fills with feathered edges only on smooth gradient backgrounds. On textured artwork, use texture-matched repair and preserve contours; report a limitation if natural reconstruction is unavailable.

When one pattern is confirmed, scan every image in the approved batch for that pattern. Do not assume that fixing the example image closes the batch issue.

## Apply user corrections

Treat screenshots and explicit corrections from the conversation as acceptance criteria. Extract the general rule behind the example, then apply it to matching structures in the current batch. Examples:

- “the brand disappeared” means compare every revised image with its source for protected marks;
- “same-column titles look inconsistent” means use one shared typography style and one alignment guide for the entire column;
- “four columns are uneven” means calculate cell boundaries or centers from the container, not from the source text widths;
- “the translation is longer” means wrap or reflow inside that cell before reducing font size or moving adjacent columns.

Do not propagate a correction to unrelated designs or change approved wording unless the user requested content revision.

## Multi-agent handoff

Give each worker a disjoint file list, confirmed terminology and the same layout/acceptance criteria. One lead owns the task JSON; workers return their assigned item updates without concurrently rewriting the shared manifest. Track file hashes so resumed tasks reuse only still-valid reviews. Concurrent PhotoCraft editing additionally requires verified independent sessions; otherwise one owner serializes editing while workers analyze images. Workers report problem images and untouched images separately. The lead agent then:

1. verifies all new PNG/PCraft pairs and dimensions, then runs native-size source comparison with each item’s declared regions;
2. reviews combined contact sheets for cross-worker consistency;
3. opens questionable outputs at original size (crop-zoomed to ≥100% — the capped render preview is not original size);
4. requests focused repair when a shared rule is still violated;
5. passes `compare_source.py --check`, records file-bound review hashes and deletes exact old variants only after every replacement in that cleanup set passes.
