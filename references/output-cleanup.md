# Output verification and exact-list cleanup

Reuse the task JSON described in `task-state.md`. For each target-language set, run:

```sh
python3 scripts/verify_outputs.py SOURCE_DIR OUTPUT_DIR --suffix=-en-v2 IMAGE_BASE
python3 scripts/verify_outputs.py SOURCE_DIR OUTPUT_DIR --suffix=-en-v2 --hashes IMAGE_BASE
```

This checks dimensions, ZIP checksums and the PCraft manifest/layer-tree presence. It does not fully parse every layer payload or prove editability. Reopen the **saved** PCraft through PhotoCraft, confirm editable text and correct rendering, inspect the exported PNG, and check protected regions. Capture fingerprints before and after that review; they must match. Record the returned `review_hashes` and set the review flags only after these checks pass. Do not simply refresh fingerprints to bypass stale approval.

Cleanup entry (retain the task item’s protected/editable regions and comparison evidence):

```json
[
  {
    "source": "/absolute/source/item.jpg",
    "source_sha256": "ACTUAL_SOURCE_SHA256",
    "png": "item-en-v2.png",
    "pcraft": "item-en-v2.pcraft",
    "protected": [],
    "comparison": {
      "editable": [],
      "channel_tolerance": 0,
      "report": "/absolute/work/qa/item-en-v2-comparison.json"
    },
    "reviewed_editable_ids": [],
    "review_report_sha256": "ACTUAL_REPORT_SHA256",
    "old_files": ["item-en-v1.png", "item-en-v1.pcraft"],
    "photocraft_reopened": true,
    "visual_passed": true,
    "review_hashes": {"source": "ACTUAL_SHA256", "png": "ACTUAL_SHA256", "pcraft": "ACTUAL_SHA256"}
  }
]
```

Empty region lists above are valid only for an unchanged image; localized images must declare real editable regions and review each one. Run the comparison/gate in `source-comparison.md`; deletion invokes that gate again.

Hashes bind review to bytes; flags record agent/user evidence and cannot themselves perform visual review. Any source or output change invalidates deletion eligibility. Older boolean-only manifests remain usable for a dry run, but deletion requires hashes, a passing region comparison, and renewed review. Keep other languages and separately approved variants out of `old_files`.

Run `python3 scripts/cleanup_versions.py OUTPUT_DIR TASK.json` to preview the exact filenames. After verifying the list matches the user's deletion authorization, add `--delete`. All entries are checked before the first deletion; one failed replacement blocks that cleanup set. Keep failed images pending and retain their older files.

Stop concurrent editing during cleanup. The script rechecks replacement integrity and fingerprints before deletion, but is not a filesystem transaction or an adversarial race guard. Sources and all declared replacements are protected. Deletion errors may leave partial cleanup: report actual remaining files, never claim rollback. Afterward confirm one current pair per requested source/language, respecting deliberately retained alternatives. Do not use the obsolete suffix-based deletion interface.

Production entries additionally require a matching `review_plan_sha256`. Shared clean-background caches are dependencies, not superseded language variants; do not include them in cleanup while referenced by any pending language. Batch verification never deletes files.
