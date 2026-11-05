# Design: Basic plots v2 (LR-10, LR-12, LR-13; Addendum 1: LR-2, LR-3, LR-4)

Worker on floor "Basic Plots v2", branch `agent/basic-plots-v2`, base `a1d3c2c`, `dev/v0.0.9` merged at `7ea6622`
(Addendum 1). Step 1 of the brief: no code yet. Questions for Tony are `Q~n`; things CoCo can settle are marked
**(CoCo)**.

## 0. The constraint that shapes everything: v1's files stay byte for byte

A bundled analysis records its file's SHA-256 (`AnalysisIdentity.file_hash`). The hash goes into a result's reuse
key (`results.py:278`, `result_cache.py:83`), and a preset or reopened plot whose hash differs gets a note
(`presets.py:472`). So any edit to `helab/scripts/standard/basic_plots.py`, `scatter_3d.py` or `transfer_fractions.py`,
even moving a helper out with no change in behaviour, marks every saved v1 result outdated and notes every v1
preset. Therefore:

- **v1's three plot modules are not edited at all.** A new test pins their SHA-256 (`test_basic_plots_v2_v1_frozen`),
  plus their analysis ids, versions and parameter names and defaults, so a later edit has to be deliberate.
- Shared code that already lives in `helab/analysis/` (stats, selection, overlay, backends, orders, panes, empty)
  is reused as it is. New shared logic goes into new Qt-free modules in `helab/analysis/` (listed in `PURE`).
- v2 may **import** v1's pure drawing helpers that it uses unchanged (`DecadeLogAxis`, `nan_empty`,
  `plotly_update`, `matplotlib_update`, the histogram/scatter figure builders) rather than copy them. v1 is frozen,
  so they can't change under v2. Moving them to `helab/analysis/` would mean editing v1. The alternative is to copy
  them into v2, which gives v2 a file hash that covers all its code but leaves about 400 duplicated lines.
  **(CoCo)** Proposed: import. v2's own logic is new code either way.
- The same applies to the DLD port: `dld/shot_times.py`'s `fallback_text` and the X-axis spec in `dld/shot_trends.py`
  are the model, but those files aren't touched. v2 gets its own copies of the wording in the new helper module.

`helab/scripts/standard/group.py` and `__init__.py` record no hash (`MODULES` lists only the three plot modules), so
the group's naming and registration can change there without touching any saved result.

## 1. LR-12: "Basic plots v1" several times in the group menu

### What the code does

- The selector (`TreePanelWidget.group_selector`, a `QComboBox`) is filled in one place, `_update_groups`
  (`script_tree.py:1173`): `clear()`, then `addItems(self.script_manager.get_groups())`.
- `ScriptsManager.get_groups()` returns `list(self._groups.keys())`, the keys of a dict. One group name can't appear
  twice.
- Nothing else adds to the selector or shows group names (grep: `group_selector`, `get_groups`, `metadata.group`);
  Debug › Script Group copies the selector's items after `menu.clear()`.

### What I tried (a throwaway probe test, removed)

- The selector after start and after three `_refresh()` calls reads `['Basic plots v1', 'DLD Front Panel Port']`
  offscreen, on macOS's own platform (cocoa), and under the Fusion and Windows styles.
- **One real difference, on Windows:** under the Windows styles the popup isn't widened to its contents (Qt widens
  it only for styles with `SH_ComboBox_Popup`, i.e. macOS and Fusion). Its width is the combo's own, which is
  `AdjustToMinimumContentsLengthWithIcon` with a minimum of 4 characters (Q33.2), and its view elides in the
  middle (`ElideMiddle`). At the panel's usual width the probe saw `'Basic…ts v1'` and `'DLD F… Port'`. With more
  groups, or a narrower panel, the entries can come to look alike.

### Cause: not found yet

Tony's details are asked through CoCo (which machine, a screenshot, the script folders loaded, the menu or the
tree). Possibilities that fit "four entries reading the same", to check against his answer:

1. Windows' popup at the combo's width, with middle elision (above). Real, but on its own it doesn't make two
   different names read the same.
2. The tree, not the selector: the four plots of "Basic plots v1" under the group node, with names cut in a narrow
   first column.
3. Groups from loaded script folders whose names differ only in invisible ways (trailing space, a different dash):
   they're distinct keys that look alike once elided.

### The fix (whatever the cause)

- **The Windows popup, as CoCo asked:** the popup is as wide as its longest name and never elides
  (`view().setTextElideMode(ElideNone)`; the view's minimum width set from `sizeHintForColumn(0)` plus the frame
  and scroll bar, after each `_update_groups`), capped at the screen's available width. The combo itself still
  shrinks with the panel (Q33.2).
- **Each name once:** the selector lists display names built as an ordered, de-duplicated list (§2), and a test
  holds it.
- If Tony's answer shows another cause, it's fixed in step 2 with a test that reproduces it first.

### Tests (`tests/test_basic_plots_v2_groups.py`)

- The selector lists each name once: at start; after Load Scripts… of a folder whose scripts use the groups
  `"Basic plots v1"`, `"Basic Plots"` and `"Lab"`; after Reload, after removing the folder, and after repeated
  `_refresh()`.
- Under `QStyleFactory.create("Windows")`, the open popup's view is at least as wide as its longest name's text, and
  its elide mode is `ElideNone`.
- A reproduction of the real cause, once known.

## 2. The group and the tree

### Choice: two groups shown as one, "Basic Plots", with version nodes

- v1 keeps its group string `"Basic plots v1"` (`standard/group.py`, unchanged). v2's group is `"Basic plots v2"`
  (`standard_v2/group.py`). The manager keeps them as two groups, as today.
- A family declares that these groups are shown as one: `helab/scripts/standard/__init__.py` gets
  `FAMILY = "Basic Plots"` and `FAMILY_GROUPS = (standard_v2.group.NAME, group.NAME)`, newest first, each with its
  node label (`"v2"`, `"v1"`, from each package's `group.VERSION`). `script_tree` reads `standard.FAMILY*`. The
  mechanism stays general (a tuple of families) but holds only this one family.
- **The selector** lists "Basic Plots" once, where "Basic plots v1" was (first), then "DLD Front Panel Port", then
  the loaded folders' groups in load order. The groups in the family aren't listed on their own.
- **The tree for "Basic Plots":** the version nodes are **top-level items** ("v2", then "v1"), each holding its
  group's scripts. Only the newest is expanded when the group is listed. No "Basic Plots" node above them: the
  selector already names the family, and top-level nodes keep the depth every walker expects
  (`HelabMainWindow._fill_run_menu`, `_fit_run_columns` and the tests' `script_button`). Each node's tooltip is
  "Basic plots v2: the newest" or "Basic plots v1: the first plots, kept so saved results and presets open".
- **Other groups look as they do now:** one top-level node named after the group, expanded (the DLD port, user
  groups, the load-errors node at the end).
- A user group whose name is a family's name ("Basic Plots") or one of its groups' names ("Basic plots v1") joins
  the family's tree: in the first case as a node after the versions named after the group; in the second, as
  today, its scripts sit beside the bundled ones in that version's node. Either way the selector lists the name
  once.
- **Expansion state:** each listing expands the newest version only. A node the user opens or closes keeps that
  state for the session while the selector switches groups (memory only, by family and node label).
- **The selector's saved choice:** none today, and none added. HeLab starts on the first group, which is now
  "Basic Plots". (`Q~5` asks whether to remember it.)
- **`find_script`** (reopen, presets) looks plots up by analysis id over every group, so the family changes nothing
  there.

### Run buttons' accessible names under a family **(CoCo)**

v1 and v2 both have "Counts per shot", so both buttons would read "Plot Counts per shot", and Debug › Run Plot would
list that name twice (its `items()` keeps the last one). IDs stay unique, since they come from the analysis id
(`run_helab_v2_counts_per_shot_plot`). Proposed: the newest version's buttons keep the plain name and older versions
add theirs, "Plot Counts per shot (v1)". The Debug menu and tests that say "Plot Counts per shot" then reach v2,
which is what a user clicking the first visible button gets. The alternative is to suffix every version, which
changes `test_debug_runner_menu.py`'s strings.

## 3. v2's layout

- **Package:** `helab/scripts/standard_v2/` (new): `__init__.py` (`MODULES`), `group.py` (`VERSION = 2`,
  `NAME = "Basic plots v2"`), `counts_per_shot.py`, `txy_histograms.py`, `scatter_3d.py`, `transfer_fractions.py`,
  `histograms_2d.py`. `script_tree._load_default_scripts` registers `standard_v2.MODULES`, then `standard.MODULES`,
  then `dld.MODULES` (v2's scripts first in the manager, matching the tree's order).
- **Analysis ids are new and versions start at 1**, so no v1 result, preset or reuse key is ever taken for v2's:
  `helab.v2.counts_per_shot`, `helab.v2.txy_histograms`, `helab.v2.scatter_3d`, `helab.v2.transfer_fractions`,
  `helab.v2.xy_histogram`, `helab.v2.xt_histogram`, `helab.v2.yt_histogram`.
- **Names in the tree** (the v2 node): 3D scatter, Counts per shot, T, X, Y histograms, XY histogram, XT histogram,
  YT histogram, Transfer fractions. These are the same names as v1, so presets, the Debug menu and the manual still
  read naturally. (`Q~3` covers the names of the three new plots.)
- **Libraries:** every v2 plot offers PyQtGraph, Plotly and Matplotlib, as v1 does (Drawing › Library), with the
  same defaults (PyQtGraph for 2D, Plotly for the 3D scatter).
- **What v2 changes, plot by plot:**
  - *Counts per shot:* the X axis setting (§4) and Plot info (§7).
  - *Transfer fractions:* the X axis setting on its per-shot panel (§4) and Plot info. Its T histogram is unchanged.
  - *T, X, Y histograms* and *3D scatter:* no shot axis. v2 keeps v1's behaviour under new ids, so the set is
    complete, Plot info applies, and later changes go to v2 only. (`Q~2` asks whether Tony wants anything else.)
  - *XY, XT, YT histograms:* new (§5).
- **New Qt-free modules in `helab/analysis/`, listed in `PURE`:**
  - `shot_axis.py`: the X axis spec, x values for the chosen shots in either mode, fallback flags, untimed shots,
    line breaks at gaps, and the wording.
  - `histogram2d.py`: 2D binning (automatic or set bins per axis, ranges from the selection) and the flattened
    axis's filter.

## 4. The shot axis: Shot ID / Shot time

- **Which plots:** Counts per shot (its only axis) and Transfer fractions (the per-shot panel). Neither the
  T, X, Y histograms, the 3D scatter nor the 2D histograms has a shot axis.
- **The setting:** `X axis` (`x_axis`), a choice of `Shot ID` (default, so v2 opens as v1 looks) or `Shot time`,
  in the plot's Plot group (Counts per shot's "Plot" group; Transfer fractions' "Fractions" group). Tip: "Shot ID,
  or when the shot was taken: its raw d<N>.txt file's time, else its TXY file's (amber triangles: when it was
  converted). Shots without a time are left out." It's a parameter: changing it reruns the plot, and since the
  axis type changes, the plot is drawn anew (`update` returns False).
- **Shot time's axis:** local clock time. PyQtGraph uses `DateAxisItem` (its labels go from seconds to dates as the
  user zooms). Plotly gets a date axis (x as local `datetime`s). Matplotlib uses `matplotlib.dates` with the local
  zone and an `AutoDateLocator`/`ConciseDateFormatter`. The axis label reads "Shot time". Hover and tooltip text
  read "shot 1235 · 14:03:12".
- **Gaps between runs:** points keep their markers, and the line is broken where the interval to the previous shot
  is over 10× the median interval of the chosen shots (a stall or a new run). The gap then shows as empty axis, not
  a long diagonal. (`Q~4`: break the line, or points only.) Shot ID mode draws as v1 does: line and markers, no
  breaks.
- **Fallbacks:** `DatasetView.fallback_times` (the TXY file's mtime) are drawn as amber triangles
  (`FALLBACK_COLOUR` as in Shot times), in Shot time mode only. They're listed in a key line ("● raw file time ·
  ▼ TXY file time (no raw file)", the triangle entry only when one is drawn) and counted in the title note
  ("⚠ 3 TXY times (no raw file)") and in the dock's first line (`describe_run`), worded as `dld/shot_times.py`
  does. In Shot ID mode the time plays no part, so nothing is marked.
- **A shot with no time at all** (no raw time and no fingerprint): left out in Shot time mode and counted, as in
  "2 without a time left out". If none of the chosen shots has a time, the plot says "None of the chosen shots has a
  time".
- **Live:** new shots are appended in either mode. `update` sets new data on the same items, keeping zoom and pan.
  Unzoomed, the time axis follows the new shots. The Shots settings (all / last N / range) still choose by shot
  number in both modes.
- **Transfer fractions in Shot time mode:** each order's line against time, with the same breaks and fallback
  triangles (one triangle series per order, in its colour with an amber outline, so the order stays readable; the
  key says it once). The newest-shot highlight is unchanged.

## 5. XY, XT, YT histograms (LR-13)

- **What:** the events of the chosen shots binned on two axes, with the third axis summed (flattened) over the
  selection. Three tree entries share one class with a `plane` attribute (`XY`, `XT`, `YT`).
- **Orientation:** XY has X horizontal and Y vertical, with equal aspect (both are lengths). XT and YT have T
  horizontal and X (or Y) vertical, with free aspect. Never rotated.
- **Units:** s and m with SI prefixes, as Basic plots keep (axis labels "T (s)", "X (m)", using PyQtGraph's
  automatic SI prefix).
- **Ranges (View range, `range_specs`, as v1's histograms):**
  - *auto-crop keep %* (default 99 %): each shown axis covers its exact shortest window holding that share of its
    events (`stats.shortest_range`, as v1's 1D histograms). The flattened axis isn't cut: every event of the chosen
    shots counts.
  - *manual T/X/Y*: each axis with a set range bounds the events, **the flattened one included**, so manual T on the
    XY plot images one T window (one cloud or order). Unset axes (min = max) use their full extent, and a reversed
    one is noted as in v1. (`Q~6`.)
- **Bins:** `Bins (horizontal)` and `Bins (vertical)`, each 0 = automatic (Freedman–Diaconis on that axis, as v1),
  capped at 1,000 per axis for the image (`MAX_BINS_2D`), and up to 2,000 when set by hand (`stats.MAX_BINS`). The
  title says "200 × 180 bins (automatic)".
- **Colour scale:** `Colour scale` linear (default) / log. Log leaves empty bins blank (NaN, the background), and the
  colour bar shows decades. Colour map viridis, with a colour bar on the right.
- **Library:** PyQtGraph `ImageItem` (`axisOrder="row-major"`, `setRect` in data coordinates) with a `ColorBarItem`
  (not interactive), as the DLD port's Density images do. Plotly uses a `Heatmap` (log as `z = log10`, with
  bar ticks relabelled). Matplotlib uses `pcolormesh` with `LogNorm` and `figure.colorbar`.
- **Live:** `update` sets the new image and rect on the same items, keeping zoom and pan (auto range stays off once
  zoomed). A change of plane, scale or library draws anew.
- **Parameters:** Shots, View range, `Histogram` group (Bins horizontal, Bins vertical, Colour scale). No newest-shot
  highlight (an overlay on an image reads badly; `Q~6`).
- **Result:** a frozen dataclass of NumPy arrays (`counts` int64 2D, two edge arrays) plus scalars and tuples,
  saved through `result_codec` as v1's are. The title reads "XY · 200 × 180 bins (automatic) · 1,234,567 of
  1,240,000 events · T summed" (T limited: "T 12.3–14.1 ms").
- **RAM:** 1,000 × 1,000 int64 is 8 MB per result, within what the RAM budget already counts.

## 6. LR-2: the Plot button's second name

- While any plot of a script is open, that script's **Plot** button reads `NEW_PLOT_TEXT` (one constant in
  `script_tree.py`: `"New"`, Tony's pick for Q65.2, 2026-11-05). Its tooltip reads "Open another
  Counts per shot plot (1 open)". It still opens another plot. With none open it reads "Plot" again.
- The count is by script (`metadata.script_id`): v1's and v2's Counts per shot are counted apart. It covers the
  first action only when it's "Plot"; Density images' "Find hot spots" keeps its name.
- It's updated on `plotsChanged` (a plot opened, closed or reopened, `_forget_instance`) and whenever the tree is
  rebuilt; then `_fit_run_columns` runs (the column fits "Plot" or "New").
- **The accessible name doesn't change** ("Plot Counts per shot"), so the Debug menu and runners keep finding it.
  The visible text and the accessible description do.
- Tests: in `test_basic_plots_v2_groups.py` (or `_buttons.py`), the button reads "Plot", opens a plot and reads
  "New" with "(1 open)", reads "(2 open)" after a second, and "Plot" again after both close. v1 and v2 are counted
  apart.

## 7. LR-4 "Plot info" and LR-3's long texts

### Where each piece of info shows today

| Info | Settings page (`instance.py`) | Dock above the plot (`workspace._wrap_plot`) | Inside the plot (v1 title) | Elsewhere |
|---|---|---|---|---|
| Folder name | "Input: run_042 · rev 1 · following Live" (tooltip: path) | line 1 "Data source: run_042 · …" | title starts "run_042 · rev 1 ·" (`source_title`) | |
| Full path | input tooltip | line 1 tooltip (record) | | |
| Revision | input line | line 1 | title | |
| Live state | input line ("following Live" / "stays with this plot") | line 1 (`plotFollow`: "3 shots waiting…") | | |
| Shots used | | line 1 ("shots 51–60 (10 of 60)") | title (`shots_text`) | |
| Events, bins, outside | | | title | |
| Analysis id, version | | line 1 | | tree tooltip |
| Saved-result mark | | line 1 ("from disk cache, computed …") | | |
| Settings in short | | line 2 | | floating strip |
| TXY source | TXY row's note ("HeLab converts with …") | record tooltip | | |
| Data root, signature, covers, parameters | | record tooltip | | |
| Run state, failures, notes | status line | amber error line | | |
| Preset notes | Presets row | | | |
| Fallback times (v2) | | line 1 (`describe_run`) | title note | |

### Proposal

- **A "Plot info" section at the top of each plot's settings page** (`plots/plot_info.py`, new, made by
  `instance.py`). It's a `SettingsToggle`-style header, "▸ Plot info · run_042 · rev 1 · following Live", one
  elided line with the full text in the tooltip. **Closed by default** (`Q~7`); open or closed lasts the session
  per plot, as the floating settings section's state does. Open, it shows wrapped lines (word wrap, and paths
  break after each separator):
  1. Input: the full path, then "rev 1 · following Live (3 shots waiting)" or "stays with this plot";
  2. Shots: "51–60 (10 of 60)", plus the fallback-time and untimed notes for v2's shot-time plots;
  3. TXY: the list in short and "HeLab converts with m19v1 · …" (the note moves here from the TXY row);
  4. Analysis: "helab.v2.counts_per_shot v1 · sha256 1a2b…", plus the saved-result mark;
  5. Settings: the short form (dock line 2's text);
  6. Record: data root, signature, covers (the rest of `describe`).
- **The settings page keeps** the Presets row, the TXY row (its button and Keep on one line; the note moves into
  Plot info), the parameters, Rerun and **the status line**, which stays visible: it's the run's feedback and its
  failures are amber. It's one line, elided, with the full text in a wrapping tooltip.
- **The dock keeps one line above the plot:** "Data source: run_042 · rev 1 · following Live" (or "Showing
  previously loaded data: …"). The stale prefix is the safety signal and belongs on the plot. Shots, id, the
  saved-result mark and the settings line move to Plot info. Its tooltip is the record, wrapped. The amber error
  line stays.
- **Inside the plot (v2 only, Tony):** v2's PyQtGraph titles drop the folder and revision (`source_title`) and keep
  what describes the drawing: shots, events, bins, the notes and ⚠ warnings. v2's Plotly and Matplotlib titles keep
  the folder name, since those figures leave HeLab (Open in browser, saved figures) (`Q~8`). v1's plots draw
  exactly what they draw now.
- **v1's settings panel gets the section too** (`Q~9`, proposed yes): the panel, the dock lines and the TXY row are
  shared Qt panels, not the plot itself. v1's in-plot titles stay as they are, so a v1 plot shows its folder in the
  dock line and in its title, as today.
- **LR-3, long texts:** every line in a plot's settings page and dock source either wraps (the Plot info body),
  elides with its full text in the tooltip (the Plot info header, the status line, the dock line, the TXY button
  as now), or is short by construction. Long tooltips become rich text, which Qt wraps (`plot_info.wrapped_tip`:
  escaped, line breaks kept, a zero-width break after each `/` or `\` of a path). The settings' summary in the
  floating strip is already elided.

### The audit (LR-3's automatic check)

- A copy of `layout_audit.py` in this floor's session folder, extended with a `test_plot_settings` case. It makes
  a synthetic run folder with a long name (nested folders, about 160 characters of path, a 60-character last
  part), opens v2's Counts per shot, T, X, Y histograms, XY histogram and Transfer fractions plus v1's Counts per
  shot, and audits the window at panel widths 250 (the minimum), 320 and 480 px and window sizes 1100×700,
  1440×860 and 1920×1080. Plot info is audited both open and closed.
- **New checks:** a *line too long* is a non-wrapping, non-eliding label whose text is wider than its widget; a
  *tooltip too wide* is a plain-text tooltip with a line over 100 characters; plus the existing checks.
- It runs before step 4b (the baseline) and after, on a real display (`HELAB_SHOW_GUI=1`, as its README says).
  Findings and screenshots go in `.ai/temp/ui-audit/`, summarised in the handoff.
- **Suite test, proposed** (cheap and stable offscreen): `tests/test_basic_plots_v2_layout.py` opens a plot on the
  long-named folder in a 250 px Settings panel and asserts that every visible `QLabel` in the page and the dock
  source either wraps, is an `ElidedLabel`, or fits its width, and that no tooltip there is plain text with a line
  over 100 characters.

### Files (Addendum 1's list, and one more) **(CoCo)**

`instance.py` (makes the section; the input label moves into it), `txy_source.py` (the note moves out),
`dock.py` (the floating strip's tooltip wraps), `settings_panel.py` (nothing expected), plus a new
`plots/plot_info.py`. **The dock's source line and its tooltip are in `helab/views/plots/workspace.py`**
(`_wrap_plot`, `_update_plot_source_label`), not `dock.py`: I need CoCo's OK to edit those two functions there.

## 8. Tests

### New (owned)

- `tests/test_basic_plots_v2_v1_frozen.py`: v1's three files' SHA-256, ids, versions, parameter names, types and
  defaults, and its group name "Basic plots v1".
- `tests/test_basic_plots_v2_groups.py`: LR-12 (§1), the family and the tree (selector entries; v2 then v1; only v2
  expanded; expansion kept across group switches; user groups named like the family), and LR-2's button (§6).
- `tests/test_basic_plots_v2_shot_axis.py`: `analysis/shot_axis.py` (times, fallbacks, untimed, breaks at gaps,
  wording), and Counts per shot and Transfer fractions in both modes and all three libraries: axis type, triangles,
  notes, the dock line, Live appending in place (zoom kept), and a rerun on a mode switch.
- `tests/test_basic_plots_v2_hist2d.py`: `analysis/histogram2d.py` (sums against `np.histogram2d`, automatic and set
  bins, auto-crop leaving the flattened axis whole, manual bounds cutting it, a reversed range, empty input), and
  the three plots in each library (orientation, aspect, log scale with blank empty bins, update in place).
- `tests/test_basic_plots_v2_plot_info.py`: the section's contents and toggle, the dock line's short form, the TXY
  note's new place, wrapped tooltips, v2 titles without the folder (PyQtGraph) and with it (Plotly, Matplotlib),
  and v1's titles unchanged.
- `tests/test_basic_plots_v2_layout.py`: the long-name check (§7), if CoCo agrees.
- Every v2 plot is opened with `compute` checked on the worker and `render`/`update` on the GUI thread, as the
  existing bundled-analysis tests do. Input arrays are unchanged after a run (read-only views raise if written).

### Lists only

`tests/test_headless_imports.py` (`PURE`: `helab.analysis.shot_axis`, `helab.analysis.histogram2d`) and
`tests/test_accessible_names.py`'s covered-class lists (`PlotInfo`).

### Existing tests that see the change (no change expected unless noted)

- `tests/test_script_system.py::test_tree_panel_lists_only_working_scripts`: asserts the selector reads
  `["Basic plots v1", "DLD Front Panel Port"]` and the tree `{"Basic plots v1": [four plots]}`. **Must change:** now
  `["Basic Plots", "DLD Front Panel Port"]`, with the tree `{"v2": [...], "v1": [four plots]}`.
  `test_load_scripts_adds_a_working_group`'s sorted list also changes ("Basic plots v1" → "Basic Plots").
- `tests/test_accessible_names.py`: `script_button` and the walk over each group read only top-level item 0. With
  the family that's v2's node: the v2 plots are walked and v1's no longer are. **Proposed (CoCo):** walk every
  top-level node (a three-line change to the loop, beyond "lists only").
- `tests/test_debug_runner_menu.py`: `test_script_group_sets_the_group_selector` reads the selector's items and the
  first top-level item's text. It picks "DLD Front Panel Port" as "other", so it should pass. The "Plot Counts per
  shot" tests reach v2's button under §2's naming and should pass.
- The audit copy and the main-window tests that click "Counts per shot" now open v2's, so their screenshots differ.
- Tests that import v1's classes directly (`test_analysis.py`, `test_analysis_gui.py`, `test_plot_backends.py`,
  `test_transfer_fractions*.py`, `test_presets_window.py`, `test_live_plots.py`, `test_plot_ram_budget.py`,
  `test_preset_folder_live.py`, `test_display_units.py`, `test_density_images.py`, `test_dld_transfer_fractions.py`):
  unaffected, since v1 is untouched. `test_bundled_analyses.py` iterates `standard.MODULES` and `dld.MODULES`. It is
  unaffected, and I'd add v2's `MODULES` to it, which needs CoCo's OK as it's not an owned test.
- Any test asserting the source line's or TXY row's exact text (Plot info moves parts of them) will be found by the
  suite run in step 4b and listed with each change explained before I make it.

## 9. Order of work (the brief's steps)

2. LR-12: the popup width, the family and the tree, with tests.
3. v2's four plots and `shot_axis`, with tests.
4. XY, XT, YT and `histogram2d`, with tests. ◆ Full suite, five type checks, pushed branch, CI.
4b. Addendum 1: LR-2's button, then the audit baseline, then Plot info and the long texts, then the audit again.
5. The handoff, the docs proposals and the manual (`docs/`: a Basic Plots page with v2 and v1, its nav entry).

## 10. Questions for Tony (provisional)

- **Q~1 (LR-12):** what Tony saw (asked through CoCo): which machine, a screenshot, the script folders loaded, and
  whether it was the selector or the tree. *Proposed:* fix the Windows popup width now, and reproduce the real
  cause from his answer.
- **Q~2 (v2's scope):** the T, X, Y histograms and the 3D scatter have no shot axis. Should their v2 change
  anything beyond new ids and Plot info? Options: (a) the same as v1 for now; (b) the 3D scatter coloured by shot
  time; (c) something Tony names. *Proposed:* (a).
- **Q~3 (names):** the new plots as three entries, "XY histogram", "XT histogram", "YT histogram"; or one entry,
  "2D histograms", with a Plane choice; or "XY image" etc. *Proposed:* three entries, named as above.
- **Q~4 (Shot time's line):** across a long gap, (a) break the line at gaps over 10× the median interval; (b) draw
  points only in Shot time mode; (c) always connect. *Proposed:* (a).
- **Q~5 (the selector's choice):** remember the group chosen across restarts? *Proposed:* no; HeLab starts on
  "Basic Plots".
- **Q~6 (2D ranges and highlight):** manual T/X/Y bound the flattened axis too (so manual T images one cloud), while
  auto-crop leaves it whole, and there's no newest-shot highlight on the 2D plots. *Proposed:* yes to both.
- **Q~7 (Plot info's default):** closed (one header line) or open. *Proposed:* closed.
- **Q~8 (what stays inside a v2 plot):** v2's PyQtGraph titles drop the folder and revision (shown on the dock line
  just above), while Plotly and Matplotlib keep them. *Proposed:* yes.
- **Q~9 (v1 and Plot info):** v1's plots get the Plot info section, the shorter dock line and the TXY note's move
  (shared Qt panels), with their in-plot drawing unchanged. *Proposed:* yes.
- **Q~10 (the axis words):** Tony's "Shot ID / Shot time", or the DLD port's "shot number / shot time" ("Against").
  *Proposed:* "X axis: Shot ID / Shot time", axis label "Shot ID". v1 says "Shot number" and stays as it is.

Q65.2 is settled (Tony, 2026-11-05): "New", tooltip "Open another Counts per shot plot (1 open)".
