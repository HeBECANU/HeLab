# Findings (real display, Fusion, SF Mono 12; 2026-11-05)

Raw: 440 items in `.ai/temp/text-audit/findings.json`. Grouped here, most serious first, each with the size
it shows at. "Long name" is the 85-character run folder of `LONG_PARTS`. Plot settings and the Scripts panel
are left to the Basic plots v2 floor.

| # | Where | Size | What | Proposed fix |
|---|---|---|---|---|
| T1 | Main window, centre hint ("Loaded <folder> — run a script to plot it") | any; 1100×700 and 900×600 worst | A long name doesn't break, so the plots area can't go below 648 px. The window can't go below 1105 px (527 empty). At 1100×700 the left panel is squeezed to its 127–165 px least width (Folder details values show 3 characters), and the name is cut. | Elide the name in the hint (middle, ~40 characters), with the whole name in its tooltip. |
| T2 | Status bar, the tab's Live phrase | 1440×860 and 1100×700 | With a long name, "· 1,234 new shots · latest shot 3 · 1 min 3 s ago" falls off the end: 119 of 164 characters shown, and the tooltip doesn't have the phrase. | Elide the folder name inside the phrase (middle, ~32 characters), so the counts and the age stay. |
| T3 | Every `ElidedLabel`: Folder details rows, the folder summary's three lines, the status bar | left panel ≤ 250 px (any window), and 1100×700 | Cut values have no tooltip with the rest: Files, TXY, Data, Loaded, Disk cache and All I/O rows show 3–19 characters (e.g. "16:…", "3 E…"); the summary's "Status scan: …" shows 13 of 60. | `ElidedLabel` puts its full text first in its tooltip whenever it is elided (one change). |
| T4 | Tooltips, app-wide | any | 58 plain-text tooltips have a line wider than 800 px, and 29 wider than 1500 px (up to 3444 px). Qt wraps a plain tooltip only once it is wider than the screen, so these are one line across most of a laptop screen, or wrapped to the screen's full width. Worst: TXY list's (465 characters), Check of cached data (403), RAM budget (393), Folder icons I/O (380, path), Converted TXY count (377), Disk cache off (path). | An app-wide filter that wraps a plain-text tooltip wider than ~600 px (shown as rich text, escaped, newlines kept). Every tooltip's look changes, so this needs Tony's OK. |
| T5 | Copy root dialog ("It's a copy…") | as opened | A radio button holds the whole path: the dialog opens **2868 px** wide with a long path, past any screen. | Elide the path in the radio text (middle), with the whole path in its tooltip. |
| T6 | Large folder dialog | as opened | The message's first line holds the long name: the dialog opens 1119 px wide and can't be narrowed. | Word-wrap the message. |
| T7 | Folder summary's "Arm auto-convert" button | left panel ≤ ~250 px | The button's text is cut ("Arm auto-convert" in 133 of 146 px). | Elide with a tooltip, or a shorter label at narrow widths (needs Tony's wording). |
| T8 | Settings › Data roots, "Clear cached analysis…" | 800×500 (the dialog's least size) and 700×450 | The button's text is cut (156 of 177 px). The dialog's contents want 821 px. | Give the button row a second line, or shorten it to "Clear analysis…" (wording). |
| T9 | Activity window, Task column | as opened (1080×440) and 640×420 | "Check folder status" shows as "Check…" (60 of 149 px); the tooltip has it. The window's buttons hold it ≥ 778 px. | Size the Task column to its contents once (low). |
| T10 | Root duplicates list; Missing shots list | 640×420 | One path cell is cut without a tooltip; "1 TXY file" is cut by 1 px. | Low: a tooltip on the path cell. |
| T11 | Settings › Lab parameters names with notes; TXY converter's profile description | 800×500 | They wrap to 5–6 lines in narrow columns. This is by design (notes under each name, A56.4's descriptions). | None proposed. |

Checked and fine: Manual marker and Place root wrap a long path over 8–14 lines, readably. Folder constants'
991 px is Side's fixed layout and doesn't depend on the path. The old I/O traces box wraps. The Debug icons
window's cut cells are a developer window (skipped).

## Suite tests proposed (cheap, stable offscreen)

- A long folder name doesn't raise the main window's minimum width. Load a long-named folder and compare
  `minimumSizeHint().width()` with the empty window's. Fails today: 575 → 1326 offscreen. Goes with T1.
- `ElidedLabel`: when elided, its tooltip starts with the full text. A unit test that goes with T3.
- With a long path, the Copy root and Large folder dialogs open no wider than 900 px. Goes with T5 and T6.
- Once T4 is in, no plain-text tooltip line over 800 px in the Settings tabs and `DIALOGS` (the wrap filter
  then makes it pass). Alternatively, a unit test of the filter itself.

## After the fixes (real display, the same cases but the message boxes)

The message-box cases were left out of this run: on the real display the first one waited for a click
(no change there: they fitted before). Fixed (Side's and Tony's OKs, 2026-11-05):

- T1: the main window's least width with the long name loaded is 527 px, the same as empty (was 1105). The
  plots area's least width is 70 px (was 648). The hint breaks the name across lines (zero-width spaces,
  `explorer_text.breakable`), its wording unchanged.
- T2: the status bar's Live phrase shortens the folder name in the middle (40 characters,
  `explorer_text.middle`): at 1440×860 and 1100×700 it shows whole, the age included. The tooltip names the
  whole path. Only at 900×600 is its end cut, with the app's counts after it.
- T3: an elided `ElidedLabel` shows its full text first in the tooltip it shows (`hover_tip`).
- T4 (Tony's OK): `helab/views/tooltips.py` wraps plain-text tooltips at 600 px app-wide (installed in
  `main`; Folder tree tooltips too); rich text and tooltips that fit stay as they are.
- T5: It's a copy… opens 676 px wide (was 2868): the path is shortened in the middle, whole in the tooltip.
- T6: Load a large folder? wraps its message: no longer over 900 px.
- T7 (Tony: a new line when tight): Arm auto-convert moves to a fourth summary line only while the Live line
  can't hold it beside "Live updates off"; at normal widths the summary keeps its three lines. The audit's
  "button text cut" for it (133 of 146 px) is Fusion's size hint against the button's own stylesheet: the
  text shows whole in the screenshots.
- T8 (Tony: a second row when tight): Data roots' buttons are a `WrapRow` (`helab/views/wrap_row.py`): one
  row while they fit, else two (the location's, its cached data's). Settings' contents now want 745 px.
- T9, T10: not changed. T9's cut Task cells have tooltips, and columns 1 on are already sized on each
  refresh (column 0 left as it was). T10's cuts are 1 px, from the audit's padding estimate.
