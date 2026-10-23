# PhotoCraft Image Localization

An agent skill for translating local images, reviewing translation accuracy, and repairing typography with PhotoCraft MCP. Produces editable `.pcraft` documents and PNG previews while protecting source artwork and brand marks.

## Requirements

- An agent that can read local images, understand the requested languages, and invoke MCP tools.
- A running PhotoCraft MCP server with access to the source and output directories.
- Python 3 for text extraction and cleanup helpers.
- macOS for the current `sips` dimension checks and AppKit/Swift contact-sheet helper. Windows/Linux equivalents are not included.

This repository contains workflow instructions and helper scripts, not PhotoCraft or a translation model. English, Vietnamese, Thai, Japanese, Arabic, and other user-specified targets are supported by the workflow; actual language and script rendering depend on the agent, installed fonts, and editor.

## Install

Clone or copy this repository into the skills directory supported by your agent. For Codex, place it at `~/.codex/skills/photocraft-image-localization`. Do not overwrite an existing installation without reviewing local changes.

For agents without a skill loader, instruct the agent to read `SKILL.md` and follow the linked references. Configure PhotoCraft MCP separately using its own installation instructions. Tool naming and MCP configuration depend on the agent host.

## Example request

> Use photocraft-image-localization to translate images in inputs/ into English. Preserve originals, logos, numbers, and product claims. Save editable PCraft documents and PNG previews into outputs/. Review translation and layout for every image and report failures.

Multiple agents are optional and require explicit user instruction. Concurrent editing requires isolated PhotoCraft sessions; otherwise serialize editing.

## Helpers

- `python3 scripts/extract_pcraft_text.py DOCUMENT.pcraft`: JSONL editable text with layer IDs, visibility, and transforms. Hidden layers are omitted by default.
- `swift scripts/contact_sheets.swift REVIEW_DIR IMAGE.png ...`: review sheets, with failure reporting.
- `python3 scripts/verify_outputs.py SOURCE_DIR OUTPUT_DIR --suffix=-en-v2 IMAGE_BASE`: archive and dimension verification. This does not replace editor reopen or visual review.
- See `references/output-cleanup.md` for exact-list cleanup. Cleanup previews by default and deletes only with `--delete` after authorized verification.

## Review boundaries

Compare protected elements with the source, review text at original resolution and typical viewing size, and use shared grids for repeated rows and columns. Image-model editing and external translation services require user authorization. Small unreadable report text must be reported rather than invented.

## Distribution status

Initial distribution of the locally developed skill. Cross-agent and cross-platform compatibility has not been validated. No license grant is included in this release; obtain permission from the repository owner before redistribution or modification beyond rights otherwise provided by law or the hosting service.
