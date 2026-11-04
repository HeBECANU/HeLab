# UI layout audit (2026-11-04, Side on Ground)

Tony in Chat, testing e4c403c: Settings › Cache was "too crowded"; then "do an audit of all other similar UI
and check", "fix a-f, then audit again".

## The script

`layout_audit.py` opens every Settings tab (880×620 and 800×500), the main window (empty, a folder loaded,
two plots, and 1100×700) and each dialog in `tests/test_accessible_names.py`'s `DIALOGS`, in HeLab's look
(Fusion, SF Mono 12, as `helab/main.py` sets). For each it saves a screenshot and records, in
`findings.json`:

- **squeezed:** a button, combo, spin box or line edit shorter than its size hint;
- **label cut:** a one-line label narrower than its text;
- **touching:** a label's text ending under 5 px from the next widget on its row;
- **outside window:** a widget past its window's edge, outside any scroll area.

It isn't part of the suite (it reuses the accessible-names test's builders and writes into
`.ai/temp/ui-audit/`). To run it, copy it in and use a real display, since the offscreen platform
elides tab titles differently:

```bash
cp .ai/sessions/2026-11-04-claude-ui-audit/layout_audit.py tests/test_zz_layout_audit_tmp.py
HELAB_SHOW_GUI=1 pytest -q -p no:randomly tests/test_zz_layout_audit_tmp.py
rm tests/test_zz_layout_audit_tmp.py
```

Then look at the screenshots, not only the findings: the first pass missed the constants' cut-off value
boxes (pyqtgraph's `compactHeight`).

## Found and fixed

- Settings › Cache: no scroll area, so a short window squeezed the rows (cut buttons and the policy box);
  names ran into values (Fusion puts no gap between labels). The tab now scrolls, and its spacing comes from
  `helab/views/gaps.py`.
- Lab parameters and Folder constants: pyqtgraph caps a spin box at its font's height (`compactHeight`).
  These boxes now take their own height (`UnitSpinBox.sizeHint`), centred in the row.
- Folder constants dialog: it opened 890×1450 pt with rows spread apart, because each wrapped source was
  sized at its 14-character minimum. Now its names are 46 characters wide, the rows scroll, and it fits the
  screen (about 990×615 pt).
- Plot side panel: one Run column sized to its buttons (the second shows only for two actions); no "Group:"
  label (the group's name was cut to "Basic p"); a gap after "TXY:".
- TXY converter: a gap after the labels, and cell padding in the profiles table. Data roots: the count on its
  own line (six buttons fit at 800 px), and cell padding. Lab parameters' status on two lines, not three.
  Manual .helab-root: no wrap in the JSON.

## Left as they are

- Compact by design (33 findings): the parameter tree's reset buttons, the toolbar's hover-menu buttons,
  and the folder summary's one-line buttons (fixed 3-line summary).
- "Preset:" keeps its 2 px gap: at the panel's 250 px minimum (`tests/test_main_split.py`) a wider gap
  pushed Delete… past the edge.
- The plot's "Data source: …" line is cut in an 1100 px window (a plain QLabel; it could elide with a tooltip).
- Settings › Scripts is still a placeholder.
