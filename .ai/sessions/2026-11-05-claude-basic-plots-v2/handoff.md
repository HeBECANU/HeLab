# Handoff: Basic plots v2 (`agent/basic-plots-v2`)

Worker (Claude, Opus 5.5), floor "Basic Plots v2", 2026-11-05. Brief: `brief.md` (with Addendum 1); design:
`design.md` (CoCo's go after step 1, Tony's answers relayed by CoCo afterwards, below). Base `a1d3c2c`, with
`dev/v0.0.9` merged at `7ea6622` (Addendum 1). Live-run items: LR-2, LR-3 (plot settings), LR-4, LR-10, LR-12, LR-13.

## What was done (commits on the branch, oldest first)

| Commit | Step | What |
|---|---|---|
| `e958b69` | 1 | The design |
| `1c2d81c` | 2 | LR-12: "Basic Plots" as one selector entry with version nodes (v2, v1; newest open); the Windows popup fits its longest entry, never elided |
| `c08a284` | 3 | v2's four plots (`helab/scripts/standard_v2/`, ids `helab.v2.*`); Shot ID / Shot time on Counts per shot and Transfer fractions; `helab/analysis/shot_axis.py`; v1 pinned |
| `cae3d26`, `94c659b` | 4 | XY, XT, YT histograms; `helab/analysis/histogram2d.py`; a typing fix in the 2D tests |
| `08b1e80` | 4b | LR-2: the Plot button reads "New" while a plot of it is open (Q65.2) |
| `f30312e` | 4b | Tony's Q~3/Q~6: the DLD port's image options on XY/XT/YT; "Sum the whole summed axis" |
| `be5db5a`, `2b84b1a`, `4f1a49e` | 4b | LR-4 Plot info; LR-3 one-line rows, the dock's one source line (CoCo's (A)); the audit |
| `624a34f` | — | The long-name layout test leaves the Presets row out (a CI failure on Windows, Checks) |
| `485a39d` and after | — | `dev/v0.0.9` merged (5c21094, Mendy's LR-3 text-length work); the floor's own tooltip wrapping dropped for the app's |
| `9c8fcb4` | 5 | The manual page; the plotting-library comparison |

Checkpoint ◆ after step 4: `94c659b`, CI run 41974019806 green on every job of the three OSes, 0 RERUN in all 12
Tests and Converter backends logs (read, and confirmed by CoCo). The final suite, type checks and CI run are in
**Checks** below.

## What it does

- **The Scripts panel (LR-12).** The group selector lists each entry once. Basic plots v2 and v1 (group strings
  "Basic plots v2" and "Basic plots v1", unchanged in the manager) are one entry, **Basic Plots**
  (`standard.FAMILY`, `FAMILY_GROUPS`). Its tree has a top-level node per version, "v2" then "v1", with only the
  newest expanded; a node the user opens or closes keeps that for the session. Other groups look as before. A
  user group named like the family or one of its groups joins it. An older version's run buttons name it in
  their accessible name ("Plot Counts per shot (v1)"); IDs still come from the analysis id. Under the Windows
  styles, Qt makes a combo's popup as wide as the combo and cut the names in the middle ("Basic…ts v1"): the
  popup now fits its longest entry and never elides (`script_tree.fit_popup`).
- **LR-12: no duplicate entries existed (Q~1, answered).** Tony's screenshot showed the drop-down reading "Basic
  plots v1" once, and the tree's one node of that name holding the four scripts: the "four entries" were the
  scripts. So there was no cause to find; what he wants is what this floor built (the drop-down reads "Basic Plots",
  the tree has a v2 node above v1, only v2 expanded), which the nodes match as labelled ("v2", "v1"). **The Windows
  popup-width fix stays:** it is a real defect on the lab's Windows PCs, independent of LR-12. Under the Windows
  styles the popup is the combo's width (at least 4 characters, Q33.2) and elides in the middle, so with a narrow
  panel or long user group names entries read alike or cut. It is cheap, tested (`test_the_popup_fits_its_longest_entry_uncut`
  fails without it) and changes nothing on macOS or Fusion, where Qt already widens the popup.
- **v2's plots** (`helab/scripts/standard_v2/`, group "Basic plots v2", version 1 each): 3D scatter, Counts per
  shot, T, X, Y histograms, XY histogram, XT histogram, YT histogram, Transfer fractions. v2's 3D scatter and T, X, Y
  histograms are v1's under v2's ids (Tony, Q~2: he'll tweak them later). Transfer fractions reuses v1's compute.
  v2 imports v1's pure helpers (CoCo's call), and v1's files are never edited.
- **Shot ID / Shot time** (LR-10; `helab/analysis/shot_axis.py`, Qt-free): an "X axis" setting (Shot ID default)
  on Counts per shot and Transfer fractions. Shot time is a date axis on the local clock in all three libraries.
  TXY-time fallbacks are amber down-triangles, counted in the title and the dock's first line. Shots with no time
  are left out and counted. A gap over 10× the median interval breaks the line (Q~4). Live updates in place in
  either mode.
- **XY, XT, YT** (LR-13; `helab/analysis/histogram2d.py`): the third axis summed over the selection. The options
  follow the DLD port's Density images (Q~3): automatic or set bins per axis, a Gaussian blur (σ in bins, the total
  kept, capped at a quarter of the image), counts per bin or a rate per shot, and the colour range compressed
  (linear, sqrt, log with decades, power γ) in the colour map only. In s and m. Auto-crop leaves the summed axis
  whole; manual bounds on it limit the events summed unless "Sum the whole summed axis" is on (Q~6). There is no
  newest-shot highlight. Three entries, as LR-13 names them.
- **LR-2:** while a plot of a script is open, its Plot button reads "New" (`NEW_PLOT_TEXT`), with the tooltip "Open
  another Counts per shot plot (1 open)". It's counted by script; the accessible name is unchanged.
- **LR-4, Plot info** (`helab/views/plots/plot_info.py`): the top of every plot's settings page, the DLD port's and
  loaded scripts' too (the page is shared; v1 too, Q~9). It's closed by default (Q~7). Closed, it's one line: the
  input, elided, with the folder's path in its tooltip. Open, it lists the dock's line, the shots, analysis
  and saved-result mark, the settings in short, the data's TXY and the record. Long names wrap (after "_" too), and
  it's at most 12 lines high, scrolling beyond. The **dock keeps one line**, "Data source: run · rev N · following
  Live" (or "Showing previously loaded data: …"), elided, with the record in its tooltip (CoCo's (A)). v2's
  PyQtGraph titles leave out the folder and revision; their Plotly and Matplotlib titles keep them (Q~8). v1's plots
  draw exactly what they did.
- **LR-3:** the status and input rows are one line each (`ElidedLabel`, whose tooltip, since `dev/v0.0.9`, starts
  with its full text while elided). Tooltips are plain text, which the app wraps at 600 px
  (`helab/views/tooltips.py`, Mendy's LR-3 work, merged at `485a39d`). The floor first wrapped its own tooltips as
  rich text (`wrapped_tip`, `TipLabel`), which the merge made redundant, so they're gone, together with the test
  changes they needed.
- **The audit** (`layout_audit.py` here, a copy of 2026-11-04's with a plot settings case and a plain-tooltip
  check; results in `audit-results.txt`). Over 45 cases (3 window sizes × 3 panel widths × 5 plots, a long folder
  name, on a real display), findings went from 1,408 to 828. Every plot-settings finding of LR-3 is gone. What
  stays belongs to the parameter tree (compact by design), the toolbar (Ground's), and "Preset:" at 250 px (left as
  it is by the 2026-11-04 audit).
- **Other plotting libraries** (Tony's question, `plotting-libraries.md`, trial `library_trial.py`): no new
  library now. Datashader is the only good fit; it bins 1 M events in 1.3 ms against `np.histogram2d`'s 84 ms.
  `np.bincount` gives identical counts in 4.8 ms with NumPy alone (A~1).

## Existing tests changed (each with why)

- `test_script_system.py`, 2 asserts (CoCo's (e)): the selector reads "Basic Plots" where it read "Basic plots
  v1", and the tree's v1 scripts are under the "v1" node.
- `test_accessible_names.py`, CoCo's (b): the walk over each group covers every top-level node, not only the
  first, since v1's plots are now a collapsed node. `PlotInfo` was added to the main window case's
  `@covers` (a list only).
- `test_bundled_analyses.py`, CoCo's (c): it also loads `standard_v2.MODULES`.
- `test_headless_imports.py` (lists only): `shot_axis` and `histogram2d` added to `PURE`.
- `test_debug_runner_menu.py::test_dump_state_saves_what_the_window_shows_from_memory` (CoCo's (d)): the plot that
  "Plot Counts per shot" opens is now v2's, so the expected id is `helab.v2.counts_per_shot`.
- **LR-4's dock line (CoCo's (A))**: each changed assert reads the same content where it now lives. The dock line
  holds the folder, revision and Live; the detail and settings come from the `plotSourceDetail` and
  `plotSourceSettings` properties that Plot info shows. The tooltip (the record) is unchanged.
  - `test_analysis_gui.py`: a `source_text(dock)` helper (the line plus detail and settings) in 9 asserts of 7
    tests: `test_selection_change_mid_run_keeps_the_input` (it also asserts the line itself is one line),
    `test_rerun_uses_the_same_input_and_close_cleans_up` (2),
    `test_reversed_manual_bounds_are_reported_in_the_dock_and_settings_tab`,
    `test_a_mask_from_the_settings_tab_and_its_errors`, `test_find_hot_spots_from_the_panel`,
    `test_histogram_fits_go_in_the_docks_record` (2), and `test_scatter_from_the_panel` (also its comment).
  - `test_constant_layers.py`: its `label()` helper adds the detail and settings for `plot_data_source` (asserts
    unchanged).
  - `test_result_cache_plots.py`: its `label()` helper adds the detail and settings for `plot_data_source`, and
    `source_line()` adds the detail (asserts unchanged).
  - `test_live_plots.py`: a `source_text(instance)` helper in 6 asserts of
    `test_shots_arriving_faster_than_a_run_give_one_rerun_on_the_newest`,
    `test_a_plot_follows_live_from_an_empty_folder_to_its_first_shots` and
    `test_transfer_fractions_highlight_follows_lives_newest_shot`.
  - (`test_folder_summary.py` and `test_plot_settings_panel.py` had changed for the floor's own wrapped tooltips;
    with those gone after the merge, both are as on `dev/v0.0.9`.)
- No other existing test changed. `test_live_scripts.py`'s dropped-panel test runs `test_live_plots` in a
  subprocess, so it failed with those asserts and passes again unchanged.

## New tests

`test_basic_plots_v2_groups.py` (LR-12, the family, the popup under the Windows style: it fails without the fix),
`_v1_frozen.py` (v1's SHA-256 with line endings normalised, ids, versions, parameters, and the helpers v2 imports),
`_shot_axis.py`, `_hist2d.py`, `_buttons.py` (LR-2), and `_plot_info.py` (Plot info, the dock line,
and LR-3's long-name check at 250 px, offscreen).

## Notes for CoCo and Ground

1. **v1 is pinned.** Ground's `7ea6622` (LR-11) had edited v1's `scatter_3d.py`. Its hashes are pinned after that
   edit. Any later edit to v1's three files fails `test_basic_plots_v2_v1_frozen.py` until the test is updated,
   and it marks every saved v1 result outdated (the file hash is in the reuse key). CoCo has told Ground.
2. **The Plot info section and the one-line dock apply to every plot** (DLD port and user scripts too), since the
   settings page and the dock are shared. In-plot drawing changed only in v2.
3. **The TXY note stays in its row**, one line with its tooltip, as 23 test references read it. Plot info
   lists the data's TXY instead.
4. The floor's venv had datashader and mpl-scatter-density, with their dependencies numba, llvmlite, xarray and the
   rest, only for the trial; they were uninstalled, so the venv is back to the lock plus pip.

## Proposed doc changes (for CoCo to apply)

**`.ai/architecture/plots-and-scripts.md`:**

- *Script system* paragraph: replace "lists HeLab's bundled analyses in two groups, both imported (`MODULES`):
  **"Basic plots v1"** (`helab/scripts/standard/`…)" with: "lists HeLab's bundled analyses in two entries:
  **"Basic Plots"**, the family of "Basic plots v2" (`helab/scripts/standard_v2/`, ids `helab.v2.*`) and "Basic
  plots v1" (`helab/scripts/standard/`, unchanged and pinned: `tests/test_basic_plots_v2_v1_frozen.py`), shown as one
  selector entry whose tree has a version node each, newest first and only the newest expanded (`script_tree.FAMILIES`,
  from `standard.FAMILY`/`FAMILY_GROUPS`; LR-12); and **"DLD Front Panel Port"** …". Add: "The selector lists each
  entry once; its popup fits its longest entry and never elides (`fit_popup`: the Windows styles don't widen a combo's
  popup). An older version's run buttons name it (`Plot Counts per shot (v1)`). While a plot of a script is open, its
  Plot button reads `NEW_PLOT_TEXT` ("New", Q65.2), the tooltip counting them; the accessible name stays."
- A new section, **"Basic plots v2"**: the package and ids; v2 imports v1's pure helpers and v1's files are never
  edited (their SHA-256 is in each result's reuse key); 3D scatter and T, X, Y histograms as v1's under v2's ids
  (Q~2); Transfer fractions reuses v1's compute (`TimedFractions`). The shot axis: `helab/analysis/shot_axis.py`
  (Shot ID / Shot time, fallbacks as amber down-triangles, untimed shots counted, a break at gaps over
  `GAP_FACTOR` 10× the median interval; `standard_v2/common.py` draws it in each library). The 2D histograms:
  `helab/analysis/histogram2d.py` (planes, auto-crop leaving the summed axis whole, manual bounds limiting it unless
  `include_outside`, bins at most 1,000 automatic, blur, rate per shot, `compress` in the colour map only);
  `standard_v2/histograms_2d.py` (shared) with one module per plane, so the tree lists XY, XT, YT in that order (the
  manager registers a module's classes alphabetically). v2's PyQtGraph titles leave out the input; Plotly and
  Matplotlib keep it (Q~8).
- *Following Live, coverage and plot display*: replace "Each plot dock's source is two lines, the input and the
  settings in short form (…)" with: "Each plot dock's source is one line, elided: `Data source: <run> · rev N ·
  <Live state>` (or "Showing previously loaded data"), the record in its tooltip. The rest (shots, `<id> vX`,
  the saved-result mark, the settings in short) is in the plot's **Plot info** (`plots/plot_info.py`, LR-4): the top
  of its settings page, closed by default to one line (the input, an `ElidedLabel`), open with wrapped lines at most 12
  high (scrolling), from the dock's properties (`plotSourceText`, `plotSourceDetail`, `plotSourceSettings`,
  `plotSourceRecord`; long names broken by `explorer_text.breakable`)."

**`AGENTS.md`**, one line under "Analysis and plots": "Basic plots v1's plot files (`helab/scripts/standard/`)
stay byte for byte: their SHA-256 keys saved results (`tests/test_basic_plots_v2_v1_frozen.py`); changes go to v2
(`helab/scripts/standard_v2/`)." Also, in the Code map's `helab/scripts/standard/` row: "`helab/scripts/standard/`,
`standard_v2/`, `helab/scripts/dld/` | Basic Plots v1 (pinned) and v2; the DLD Front Panel Port".

**`.ai/memory/results/analysis-plots.md`**: add "Basic plots v2 (2026-11-05)", with Tony's choices: "Basic Plots"
with version nodes, newest first (LR-12); new ids, so v1's results and presets stay v1's; Shot ID / Shot time, its
fallbacks marked as Shot times does (LR-10); XY/XT/YT with the DLD port's image options, in s and m (LR-13, Q~3);
"Sum the whole summed axis", default off, and no newest-shot highlight (Q~6); Plot info, closed by default, v1's
panel too, and v2's PyQtGraph titles without the input (LR-4, Q~7–Q~9); "New" for the second Plot (Q65.2).

**The manual**, done here: `docs/how-to/basic-plots.md` (in the nav) and `install.md`'s first plot.

## Provisional items

- **Q~1 (LR-12): answered** (Tony's screenshot, via CoCo, 2026-11-05): there was no repeated entry; the four lines
  were the four scripts under the one "Basic plots v1" node. What he asked for is what was built; the Windows
  popup-width fix stays (above).
- **Q~11 (Datashader):** add it later, only if Live on very large folders (over about 10 M events per image) makes
  the 2D plots lag after A~1? *Proposed:* not now; ask again with numbers from a real run.
- **Q~12 (wording):** v2 says "Shot ID" (Tony's word), while the DLD port's Shot trends say "shot number"
  ("Against"). Align the DLD port's wording? *Proposed:* yes, on a DLD floor, keeping its parameter values (or as an
  alias), since presets save them.
- **A~1:** bin `histogram2d.py` with `np.bincount` on computed indices (about 17× faster, the same counts, NumPy only;
  the last bin's right-edge rule must match). The DLD port's Density images could follow on its own floor.
- **A~2:** PyQtGraph labels Transfer fractions' Y axis "(x0.001)" with ticks up to 600 (v1 and v2): set the axis's
  units or turn off its SI prefix scaling, in v2 only.
- **A~3:** at the panel's 250 px minimum, "Preset:" is cut and touching (left by the 2026-11-04 audit); the TXY
  row's "HeLab converts with …" elides early. A one-line layout pass on the Presets row.
- **M~1:** Tony tries Basic Plots v2 on a real screen and with Live: the tree (v2 open, v1 closed), New, Shot time
  on a real run with gaps (and a folder converted later, for the triangles), the XY/XT/YT options, and Plot info and
  the one-line dock with long folder names. **On the lab's Windows PC**, open the group menu at a narrow panel (the
  popup fix: every entry in full).

## Checks

At `9c8fcb4` (the handoff's own commit adds only this file), the full output is in `.ai/temp/suite-final.txt` and
`types-final.txt` (not committed):

- Full suite (`pytest -n 8 --reruns 5 --reruns-delay 1 --basetemp=.ai/temp/pytest`): **9,501 passed, 673 skipped,
  0 RERUN**.
- Type checks: `mypy helab/ --strict` (224 files), `mypy tests --strict` (219), `pyright helab tests`,
  `mypy helab/ --strict --platform win32` and `pyright --pythonplatform Windows helab tests`: **all clean**.
- Manual: `ruff check` and `mkdocs build --strict` pass (in a separate docs venv).
- CI run 41979487365 (`b01dcce`) **failed one job**: Windows Tests (1/3). My new
  `test_basic_plots_v2_plot_info.py::test_a_long_folder_name_fits_the_narrowest_panel` failed on its first try and on
  all 5 reruns. The reason was `'Preset:' is cut`: at 250 px, Windows' fonts cut the Presets row's label. That's the
  known issue the 2026-11-04 audit left (A~3), not one of the lines LR-3 is about, so the test was too broad. The
  test now leaves the Presets row out (as it does the parameter tree), saying why. Every other job was green, and
  the other 11 Tests and Converter backends logs have 0 RERUN. That RERUN was a real failure, not a flake: nothing
  goes to known-issues.
- After the fix: CI run 41981789709 (`624a34f`) green on every job, with 0 RERUN in all 12 logs.
- **After merging `dev/v0.0.9` (5c21094)** and dropping the floor's own tooltip wrapping: full suite **9,527
  passed, 673 skipped, 0 RERUN**; all five type checks clean (226 and 220 files). The audit's merged run (above,
  `audit-results.txt`) shows no plot-settings label cut. The CI run for this head goes to CoCo with its ID.
