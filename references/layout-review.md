# Layout review

Review at original size and at a reduced size representative of ordinary viewing. Define actual cells, padding, styles, minimum readable size and guides in the task JSON before editing; use current PhotoCraft type.info evidence with check_layout.py. A passing numeric check does not establish visual balance.

- Preserve a clear title, feature, and supporting-text hierarchy.
- Keep same-level labels consistent in font, weight, size, color, casing, and line spacing. Do not resize each label independently merely to make it fit. When one item does not fit, first wrap within its cell, then adjust the group layout or column widths while protecting artwork. Only then moderately reduce the shared group size if it remains readable at the intended viewing size. Recheck every item against cell and protected-element bounds. If none of these options works, report the constraint rather than shrinking the group until unreadable.
- Use deliberate line breaks for longer target-language text.
- Prefer reflowing or repositioning text before shrinking it below comfortable reading size. A longer translation must wrap inside its own region; it must not push the next row or column away from the shared grid.
- Maintain safe margins and align related labels and values to a shared baseline or column.
- For repeated rows, define one label origin and one value origin, then apply them to every row. Choose left, right, or center alignment deliberately and keep it consistent.
- For repeated columns, divide the available container into explicit cells. Align each header and value to its cell center or shared left edge. Verify that the first and last columns retain comparable outer margins.
- Measure actual rendered bounds after changing font size or text. Reject a layer whose bounds leave its cell or canvas even if the text appears acceptable in a reduced preview.
- Do not cover products, icons, leader lines, report evidence, or important texture.
- Center label text optically, including vertically.
- Preserve the source palette where readable; increase contrast when supporting text disappears into the background.
- Keep text layers editable.

Compare the finished image with the source before acceptance. Reject a preview when a logo, brand mark, icon, identifier, or required original-language mark has disappeared or been covered.

Never assume a new text layer covers an underlying defect — verify the repair itself before placing text.

When rebuilding a shape's interior color field, inset the mask to stay clear of the silhouette's rim, highlights, and attachments (tails, rounded corners) — repair only the inner wall, never pave over the shape's border.

Reject a preview with residual source glyphs, obvious repair seams, clipped text, crowding, inconsistent alignment, unequal column distribution, unreadably small copy, or a layout that materially changes the source hierarchy.


For local repair review, record the affected region and inspect matching source/before/after crops at a verified 1:1 pixel scale. If the render preview is capped below canvas size, duplicate the document and crop the scratch copy; never crop the deliverable. Preserve the original copy for comparison. A reduced whole-image preview is useful for composition but cannot certify seam removal. Threshold scans and point samples are supporting evidence only. Any later repair invalidates the prior review for its affected regions and dependent layout groups.

Protect logos and original-language brand marks before raster operations as well as before text placement. Compare these regions with the original after repair; use local pixel differences as a flag when geometry and color handling are comparable, and inspect differences rather than accepting or rejecting from a threshold alone. Restore a mistakenly removed brand from the original pixels, preserving its geometry, instead of regenerating its lettering.

Use the full-resolution comparison report from `compare_source.py` to locate any preserved-region change. Threshold scans are not a substitute for that gate. For editable regions, inspect both repaired background and final text at 1:1 scale, then record the reviewed region IDs.
