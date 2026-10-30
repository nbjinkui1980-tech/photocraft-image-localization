# Changelog

All notable capability changes to this skill. The delivery gates and review standards
do not change between entries unless said so explicitly.

## 2026-10-30 — Batch adaptation + calibration + rebuild path + RTL validation

Adds the ability to bring an **existing localized set** up to the delivery standard (or
apply batch wording/typography corrections) without hand-measuring each image, and to
handle the backgrounds that mode cannot:

- **Baseline classification** — `classify_baseline.swift`: grid-sample a source and an
  existing output to decide whether its background is preserved (the source stays a valid
  pixel-comparison baseline) or redesigned (a re-rendered gradient/photo). Redesigned
  outputs must not be gated against the source.
- **Editable-region derivation** — `repairmap.swift` + `cluster_rects.py`: derive the
  changed footprint (removed source text + localized text + repair) from the
  source-vs-output difference, then cluster fragments into per-text-group editable boxes.
  Far faster and less error-prone than hand-measuring masks.
- **Cross-set calibration** — `background_floor.swift` + `calibrate_adaptation.py`:
  measure a set's diffuse background noise ceiling and recommend `channel_tolerance` and
  cluster `gap`/`margin` for it, instead of reusing another set's values. Classifies,
  validates coverage on a sample, and flags thin hot tails (suspect localized defects)
  for review rather than hiding them behind a high tolerance.
- **Redesigned-background decision** (batch-adaptation.md): unintentional repaint →
  rebuild from the source in production mode (verified clean base, then localize);
  intentional redesign → gate against the prior output, not the source.
- **Failure diagnosis** — `outside_editable_scan.swift`: list above-tolerance pixels that
  fall outside the declared editable regions, using the same decoder as the delivery gate.

Verified end to end on a 20-image zh→vi brochure batch (every gate green) and on
non-Latin rendering: Japanese, Korean, Chinese, Thai, Devanagari, Arabic and Hebrew all
render with the right macOS fonts and no missing-glyph fallback; RTL orders and joins
correctly (default `auto` direction suffices for glyph order; use explicit
`direction: rtl` + `align: right` for RTL paragraph layout). See the font-preflight
section of SKILL.md.

Reference docs: `batch-adaptation.md` (this mode), `batch-production.md` (clean-base
production), `fast-pipeline.md` (command sequence), plus `source-comparison.md`,
`task-state.md`, `layout-review.md`, `batch-review.md`, `translation-policy.md`,
`output-cleanup.md`.

Regression suites: `test_workflow.py`, `test_source_comparison.py`, `test_scans.py`,
`test_adaptation.py` (batch-adaptation helpers), `test_calibrate.py` (calibration),
`test_tools.py` (task/review/cache/parallel tooling).

Platform: macOS + PhotoCraft MCP only.
