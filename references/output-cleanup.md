# Output verification and exact-list cleanup

Run `python3 scripts/verify_outputs.py SOURCE_DIR OUTPUT_DIR --suffix=-en-v2 IMAGE_BASE` for each target-language set. This checks image dimensions and PCraft archive/manifest integrity. Then reopen the saved PCraft through PhotoCraft, confirm editable layers, render it, and inspect the result. Also inspect the exported PNG.

Cleanup uses an explicit JSON list. Example (substitute actual paths and verified filenames):

```json
[
  {
    "source": "/absolute/source/item.jpg",
    "png": "item-en-v2.png",
    "pcraft": "item-en-v2.pcraft",
    "old_files": ["item-en-v1.png", "item-en-v1.pcraft"],
    "photocraft_reopened": true,
    "visual_passed": true
  }
]
```

Set review flags to true only after those checks actually pass. They record human/agent evidence; they do not perform the checks. Include only older variants explicitly authorized for replacement, never other languages or separately approved alternatives.

Run `python3 scripts/cleanup_versions.py OUTPUT_DIR MANIFEST.json` to preview the exact list. After verifying it matches the authorized set, add `--delete`. Every replacement is mechanically checked before any deletion. Sources and all listed replacements are protected across the whole manifest. Deletion errors can leave partial cleanup; report actual remaining files and never claim rollback. Do not use the previous suffix-based cleanup interface.
