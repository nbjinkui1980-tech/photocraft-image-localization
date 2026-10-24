# Multilingual batch production

## Modes and shared preparation

Use adaptation mode for a new language/script, font, renderer/export configuration or layout family. Use production mode for requested batches with validated configuration. Both modes require the same per-image delivery gate. A one-image request normally needs one agent, not an agent team.

Once per session, discover necessary MCP commands, read/write roots and session isolation. Once per language/font combination, trial-render representative actual strings; new glyph coverage or script combinations require a new trial. Cache the evidence with renderer version, installed font fingerprint, resolution and export/color settings. Revalidate on changes or relevant errors. Do not reuse one image's JPEG roundtrip tolerance on unrelated source profiles or decoder paths without establishing the same calibration applies.

Group similar layouts, verify one representative's styles/cells, then instantiate the rules with each image's actual coordinates. Do not re-run source OCR, terminology analysis or font tests for unchanged inputs merely because another language is being produced.

## Clean a source once

Keep a lossless, editable clean-background PCraft and its PNG per source. It must contain no translated text layers. Preserve the original, brands, product art, age/size numbers and icons. Review the clean background at 1:1 scale **before** any language text can hide defects. Save a clean-base task item using the existing source/region comparison and review schema; run its delivery gate before caching it. The clean-base task is separate from final language outputs and is not a deliverable translation.

For each language, duplicate the verified clean PCraft through PhotoCraft and create independent editable text layers. Reuse the source transcription and protected regions. Keep the original image as `source` for final pixel comparison; never switch the comparison baseline to the cleaned image, which could hide earlier damage.

Reuse only when source hash, protection policy, clean PCraft hash and clean-base review evidence match. A changed repair footprint or damaged/modified background requires a new clean-base revision and review of dependent variants. Do not remove this shared cache while other languages still need it. Do not add it to a language's `old_files`.

## Plan edits before issuing commands

Resolve translations and task terminology once per language. For each image, prepare text, font, style group, cell, alignment and intended line breaks in the existing task entry. Trial-fit difficult strings before raster repair. Language-specific direction, glyph shaping and wrapping remain independent; do not copy Vietnamese sizes/positions to Arabic or Japanese without checking.

Execute planned steps for one active document using MCP `command_batch`. Check every step's success and capture resulting IDs/bounds. Batch only operations whose inputs are already known; use checkpoints when later steps depend on generated IDs or uncertain repairs. On partial failure, inspect the current document and continue from the failed step, not from the start.

Keep full MCP JSON locally or in tool-orchestration state. Emit only counts, warnings, failed steps and the bounds needed for the next decision. Do not repeatedly return whole manifests, layer caches or command catalogs. If the host supports orchestration, parse each result before emitting it; do not claim reduced model context when the host already exposed the full result. Reuse original-size crop reviews only for unchanged clean backgrounds. Each final language image still needs composition/readability review, and new text/background intersections need local inspection.

## Task fields and resuming

Continue using one task JSON list, one item per source/language. Add optional `production` metadata for production-mode entries:

```json
{
  "production": {
    "renderer": "actual-version-and-export-config",
    "fonts": {"chosen-font": "installed-file-or-verified-font-fingerprint"},
    "clean_base": {
      "task": "/absolute/work/clean/task.json",
      "output_dir": "/absolute/work/clean/outputs",
      "png": "item-clean-v1.png",
      "pcraft_sha256": "ACTUAL_CLEAN_PCRAFT_HASH"
    }
  },
  "candidate_plan_sha256": "PLAN_HASH_AFTER_EXECUTING_THIS_PLAN",
  "review_plan_sha256": "SAME_PLAN_HASH_AFTER_REVIEW"
}
```

Omit `clean_base` when no shared clean base is used. Compute the plan hash using `compare_source.production_hash(entry)`. It covers source hash, target language, confirmed phrases, layout, protected regions and production metadata. Record `candidate_plan_sha256` only after the saved candidate actually implements that plan; record `review_plan_sha256` only after review. These records bind workflow state, not proof that edits or review happened. Never refresh hashes just to bypass a stale plan. Existing non-production entries remain supported; their file/pixel/visual checks are unchanged.

On resume:

- changed original or clean base: redo affected source preparation and language variants;
- changed translation/style/font: update affected text and its dependent groups, then save/review;
- unchanged candidate and current pixel report: reuse the report; no need to scan pixels again;
- missing/stale type snapshot: collect current `type.info`, not guessed bounds;
- failed/stale pixel report: fix the defect or refresh approved plan, select a **fresh** report path, then rerun;
- missing visual/reopen evidence: perform those checks; a mechanical script must not approve them.

## One command for deterministic checks

After MCP has saved candidates and captured current type snapshots, run:

```sh
python3 scripts/batch_verify.py TASK.json OUTPUT_DIR --summary=/absolute/work/qa/batch-check-01.json
```

The helper validates each candidate, optional clean-base evidence and production plan, declared geometry, and original-size pixel preservation. It compiles the Swift comparison helper once per invocation only when a new comparison is needed, using a writable temporary module cache. It reuses only matching successful pixel reports. Each item ends as `ready`, `needs_review`, or `failed`; other items continue after an individual failure. Full details and per-item elapsed seconds go to the summary; console output contains counts and bounded exception descriptions. Exit 0 means all entries are ready; exit 1 means at least one item needs review or failed. Existing summary files are not overwritten.

It does not translate, edit via MCP, save PCraft, collect type.info, mark visual approval, change the task manifest or delete anything. The agent performs those operations through PhotoCraft, updates genuine evidence, then resumes the same checks. `ready` still relies on recorded visual judgments. Keep cleanup a separate explicit action using the existing exact-list gate.

## Parallelism and measurements

Parallelize translation/analysis and independent local checks when authorized and useful. Concurrent editor mutation requires independently verified MCP sessions; otherwise keep one editor owner and prepare other images while it works. Avoid simultaneous task-manifest writers.

Measure representative batches before claiming speedups: record total elapsed time, actual MCP call count and retry count, languages per source, and cache reuse. The helper measures verification elapsed time only. Record tokens only when the host supplies real usage; never estimate token savings from file sizes or image pixel counts. Do not build a scheduler or add dependencies merely to run this workflow.
