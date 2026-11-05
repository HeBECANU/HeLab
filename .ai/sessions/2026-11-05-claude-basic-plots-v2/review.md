# Review: Basic plots v2 (`agent/basic-plots-v2`)

Reviewer (Claude, Opus 5.5), floor "Basic Plots v2", 2026-11-05. Diff reviewed: `127b1e8..bd7176f` (the branch's own
work; `127b1e8` is the `dev/v0.0.9` tip merged at HEAD, so the merges' content is left out), against `brief.md`
(with Addendum 1), `design.md`, `handoff.md`, the live-run log's LR-2, LR-3, LR-4, LR-10, LR-12 and LR-13 rows, and
`AGENTS.md`.

## Checks rerun

At HEAD `bd7176f`, after `source .ai/local/floor-env.sh`; output kept whole in `.ai/temp/` (not committed):

- **Full suite** (`pytest -n 4 --reruns 5 --reruns-delay 1 --basetemp=.ai/temp/pytest-lens`,
  `.ai/temp/review-suite.txt`): **9,543 passed, 673 skipped, 2 warnings, 0 RERUN** (231 s). The 2 warnings are
  pyqtgraph's NumPy 2.5 `arr.shape` deprecation in `tests/test_t_spectrum.py`, not this branch's.
- **Type checks** (`.ai/temp/review-types.txt`): `mypy helab/ --strict` (228 files), `mypy tests --strict` (221),
  `pyright helab tests`, `mypy helab/ --strict --platform win32` (228) and `pyright --pythonplatform Windows helab
  tests`: **all clean** (0 errors, 0 warnings).
- **CI:** there is **no run for HEAD `bd7176f` yet**. The latest, 41986996975 (`ab2a7d7`), is green on every job;
  its 12 Tests and Converter backends logs (fetched per job, `.ai/temp/review-ci-job-*.log`) have **0 RERUN**.
- **v1 untouched:** `git diff 127b1e8..HEAD -- helab/scripts/standard/` changes only `__init__.py` (the family
  constants); `basic_plots.py`, `scatter_3d.py`, `transfer_fractions.py` and `group.py` have no commit on the branch
  since the base `a1d3c2c` other than Ground's merged LR-11, and `test_basic_plots_v2_v1_frozen.py` pins them.
- **Reproductions** (scratchpad scripts, not committed): BP-1, BP-2, BP-3 and BP-5 below were each reproduced.

## Summary

**No blocker.** One Major: the 2D histograms' manual View range crops unset and reversed axes to the auto-crop
share while their note says "using full extent" (BP-1). Four Minor and four Info.

What holds:

- **v1 byte for byte**, with the SHA-256, ids, versions and parameters pinned. The hash check normalises line
  endings, so it holds on Windows checkouts.
- **Threads.** Every v2 `compute` is NumPy, SciPy and `DatasetView` only, with no Qt and no drawing. `render` and
  `update` build widgets only, on the GUI thread through the instance, and the hooks go through `_hook`, so one
  that raises is logged.
- **No array is changed in place.** `events()` concatenates into a new array, the masks and fancy indexing make
  copies, `broken` and `blurred` return new arrays, and `test_*_leave_their_input_unchanged` covers it.
- **Shot time.** It is the raw file's mtime, else the fingerprint's (`fallback_times`), and shots with neither are
  left out and counted. Fallbacks are amber down-triangles in all three libraries. The gap rule is 10× the median
  positive interval, needs at least three shots, and draws breaks as NaN points. It is local time everywhere:
  PyQtGraph's `DateAxisItem` uses each timestamp's own offset, so DST is handled.
- **The 2D histograms.** They are never rotated, with equal aspect on XY. Automatic bins are Freedman–Diaconis
  capped at 1,000, and the colour compression is the same in all three libraries (the Matplotlib norms match
  `compress`). Blur is σ in bins, capped at a quarter of the longer side, with reflecting edges, so the total is
  kept. Rate per shot is counts ÷ shots ÷ bin area.
- **The Basic Plots family.** The selector and Debug › Script Group list each entry once. Debug › Run Plot walks
  every top-level node, so it lists "Plot Counts per shot" (v2) and "Plot Counts per shot (v1)". The IDs still come
  from the analysis id, and `find_script` looks over every group, so presets and arrangements reopen v1 by id.
- **The changed asserts** in `test_analysis_gui.py`, `test_live_plots.py`, `test_constant_layers.py` and
  `test_result_cache_plots.py` read the same strings from where LR-4 moved them (`plotSourceDetail`,
  `plotSourceSettings`). They are not weakened, apart from what the dock no longer shows (BP-6).
- **The layout tests** compare text advance with the widget's width (+2 px), not fixed pixels, and the long-name
  test leaves out the Presets row, with its reason given. Both were green on Windows CI.

## Findings

### BP-1 — Major — `helab/scripts/standard_v2/histograms_2d.py:224-229` (with `helab/analysis/histogram2d.py:70-76`)

**What's wrong.** In the manual View range, a shown axis that has no bounds (min = max, unset) or reversed bounds
(min > max) gets `None` from `manual_bounds`. `histogram2d` then crops that axis with
`shortest_range(values, keep_fraction(values))`, the auto-crop share (99 % by default, or whatever "Auto-crop:
keep" was last left at, a setting hidden in manual mode), instead of the full extent. That contradicts:

- `manual_bounds`' docstring ("None for that axis's full extent");
- v1, which uses `(column.min(), column.max())` for such an axis (`helab/scripts/standard/basic_plots.py:265-267`);
- the design (§5: "Unset axes (min = max) use their full extent");
- the plot's own note, "⚠ X: min > max, using full extent".

**Failure scenario** (reproduced with the test file's `view()`):

- XY with `range_mode=manual` and only `t_min=0, t_max=5` set. X then spans −0.0110…0.0101 instead of its full
  extent −0.0147…1.0099, and the title says "280 outside the range". v1 with the same settings shows X over the full
  extent with 0 outside.
- With `x_min=1, x_max=-1`, X is still cropped to 99 % while the title says "X: min > max, using full extent".

A user who sets T only, to image one cloud, silently loses the far events on X and Y.

**Fix.** In `compute`, when `manual(values)`, give `histogram2d` `keep=1.0`, or pass the full extent for shown axes
whose bound is `None`, as v1 does. Add a test: manual mode with only T set gives X and Y edges equal to the events'
min and max with 0 outside, and a reversed X gives the full extent.

### BP-2 — Minor — `helab/scripts/standard_v2/counts_per_shot.py:129-141`, `transfer_fractions.py:101-120`

**What's wrong.** An X-axis switch (Shot ID ↔ Shot time) redraws only in PyQtGraph. Matplotlib and Plotly update in
place and keep the user's zoom from the old axis:

- **Matplotlib** (`MatplotlibPane.redraw`, `helab/analysis/backends.py:116-137`) restores the old limits because a
  date axis's scale is still "linear".
- **Plotly** keeps a constant `uirevision` (`UI_REVISION`), so plotly.js keeps a range the user set. I didn't run
  this one in a browser, so it is plausible but unverified.

The design (§4) and the `update` docstrings say "Another X axis draws it anew". The test checks a redraw only for
PyQtGraph (`test_basic_plots_v2_shot_axis.py:178-180`).

**Failure scenario** (reproduced): Counts per shot drawn with Matplotlib in Shot ID mode, zoomed to x 2–6, then
switched to Shot time. `update` returns True, the axis keeps (2, 6), which reads as 1970-01-03…01-07, and the data
is at about 2025-11-05. The plot looks empty until Home is pressed. Transfer fractions behaves the same.

**Fix.** Return False from `update` when the mode differs, in every library: record `data.axis.mode` on the pane in
`draw` and compare it, as PyQtGraph's `axis_mode` and `layout()` already do. Alternatively, make the Plotly
`uirevision` include the mode. Then assert `not script.update(widget, switched)` for all three backends.

### BP-3 — Minor — `helab/scripts/standard_v2/histograms_2d.py:186-195`

**What's wrong.** `Histogram2DPlot.get_metadata` passes `file_path=__file__`, which is `histograms_2d.py`. But
`ScriptsManager.load_module` hashes the registered module, the 11-line `xy_histogram.py` (and its XT and YT twins).
The identity therefore names one file and carries another file's hash: it reads `helab.v2.xy_histogram v1 ·
histograms_2d.py (sha256 05c7bfdd42e6)`, where `05c7bfdd42e6` is `xy_histogram.py`'s hash and `histograms_2d.py`'s is
`fe546bcbf089`.

**Failure scenario.**

- A later change to `histograms_2d.py`, which holds all of XY, XT and YT's compute and drawing, never changes their
  hash. The presets' "script changed" note (`helab/analysis/presets.py:472`) and the reuse key
  (`helab/analysis/results.py:279`) don't see it unless `version` is bumped by hand.
- The tree tooltip, Plot info and the record show a file name and hash that don't belong together.

v2's `txy_histograms.py`, `scatter_3d.py` and `transfer_fractions.py` also inherit code their hash doesn't cover,
but that code is frozen v1 (design §0, CoCo's call). `histograms_2d.py` is not frozen.

**Fix.** Either:

- have each plane module's class report its own `__file__`, so the name matches the hash, and note in
  `plots-and-scripts.md` that a change to `histograms_2d.py` (and `common.py`) needs the three plots' `version`
  bumped; or
- register `histograms_2d.py` itself and order the three entries some other way than `inspect.getmembers`'
  alphabetical order.

### BP-4 — Minor — `helab/views/plots/instance.py:1464` (with `workspace.py:319`, `HelabMainWindow.py:1923`)

**What's wrong.** Plot info's first line copies the dock's line (`plotSourceText`) only when the instance runs
`_show_follow` → `_show_info`. The main window also relabels every dock when the tab's selection or folder changes
(`HelabMainWindow._update_folder_details` → `PlotWorkspace._update_plot_source_label`): that sets `plotSourceText`,
but Plot info isn't told. Found by reading the code; not run.

**Failure scenario.** A plot runs on `run_A`, then the user selects `run_B` in the tab. The dock now reads "Showing
previously loaded data: run_A · rev 1", while Plot info still reads "Data source: run_A · rev 1" until the next run
or Live change. The stale-data signal the design kept (§7) disagrees between the two places.

**Fix.** Leave the dock's line out of Plot info, since it is always on screen above the plot. Or have
`_update_plot_source_label` notify the dock's instance, for example through a signal or a callback on the dock, so
it refreshes `_show_info`. Then add a test that changes the tab's selection and compares the two.

### BP-5 — Minor — `docs/how-to/basic-plots.md:87`

**What's wrong.** The text `**Data source: <folder> · rev N · following Live**` puts a bare `<folder>` in the page.
Python-Markdown passes it through as an HTML element. I verified this: `markdown.markdown('**Data source: <folder> ·
rev N**')` gives `<p><strong>Data source: <folder> · rev N</strong></p>`. The browser then drops the unknown tag.
`mkdocs build --strict` doesn't catch it.

**Failure scenario.** The manual shows "Data source:  · rev N · following Live".

**Fix.** Use backticks, as `docs/how-to/live.md:30` does (`` `Data source: <folder> · rev N · following Live` ``),
or write `&lt;folder&gt;`.

### BP-6 — Info — `helab/views/plots/workspace.py:312-320`

**What's wrong.** The dock now shows only folder · rev · Live. Several things were on the dock's visible line and
now sit only in Plot info (closed by default), the line's tooltip and the status line:

- the saved-result mark, including "saved result of …, outdated";
- the ⚠ warnings in the settings ("⚠ X: min > max…", constants notes);
- v2's "⚠ N TXY times" count.

This follows CoCo's (A) and the design (§7). But "outdated" is a safety signal of the same kind as the "Showing
previously loaded data" prefix that was kept on the plot. It matters for the DLD port's disk-cached plots (Release
time, Correlations). Basic plots don't disk-cache.
`test_reversed_manual_bounds_are_reported_in_the_dock_and_settings_tab` now checks the dock's properties, not what
the line shows.

**Suggest.** Keep "outdated" and ⚠ warnings on the dock's line, or put the question to Tony as a provisional item
in the handoff.

### BP-7 — Info — provisional IDs in code

**What's wrong.** These `Q~`/`A~` IDs will dangle once CoCo numbers them:

- `helab/scripts/standard_v2/histograms_2d.py:3` ("Tony, Q~3");
- `helab/views/plots/instance.py:209` ("Q~7");
- `tests/test_basic_plots_v2_hist2d.py:4` ("Q~3");
- `tests/test_basic_plots_v2_plot_info.py:55` ("Q~7") and `:90` ("A~3").

The shipped module docstrings also carry live-run IDs: `histograms_2d.py:1` ("LR-13") and `plot_info.py:1`
("LR-4"). AGENTS.md's no-internal-ID rule binds the API-reference modules only, and other modules already do this,
so this is Info.

**Suggest.** The handoff lists these lines, so they are renamed with the final IDs at landing.

### BP-8 — Info — `helab/views/plots/instance.py:209, 1470-1472`

**What's wrong.** `AnalysisInstance.info_open` is written in `_info_toggled` but read only by tests. The section's
state already lives in `PlotInfo.toggle`, and `_empty_page` keeps the widget.

**Suggest.** Drop it, and have the tests use `plot_info.is_open()`.

### BP-9 — Info — design §8's thread checks

**What's wrong.** The design promised "Every v2 plot is opened with `compute` checked on the worker and
`render`/`update` on the GUI thread". No new test asserts a thread. The code is structurally right (see Summary),
and the window tests (`_buttons.py`, `_plot_info.py`) run `compute` through `AnalysisRunner`.

**Suggest.** Add one small test that records `threading.current_thread()` in `compute` and in `render`/`update` of
the v2 classes run through the runner, or drop the claim from the handoff.

## Doc changes the handoff should also propose

- **`plots-and-scripts.md`'s v2 section:** XY, XT and YT's identity and hash cover only the plane stubs, so a change
  to `histograms_2d.py` or `common.py` bumps the plots' `version` (BP-3).
- **`known-issues.md`:** nothing. No RERUN was seen in the suite or in CI.

## Re-check 1

Reviewer (Lens), 2026-11-05. Scope:

- the fix diff `git diff cb6a5bf ffb8ea4`, a commit per finding (`259e50a` … `ffb8ea4`);
- the handoff update `e837ead`.

`8bae2b1`, the `dev/v0.0.9` merge, is left out.

### Checks rerun

At HEAD `e837ead`, after `source .ai/local/floor-env.sh`; output in `.ai/temp/` (not committed):

- **Full suite.** The fixes reach shared code: every plot's dock line and its tooltip in `workspace.py`, and the
  dock's event filter and the warnings in `instance.py`. So I ran the whole suite (`pytest -n 4 --reruns 5
  --reruns-delay 1 --basetemp=.ai/temp/pytest-lens`, `.ai/temp/review-suite-2.txt`): **9,551 passed, 673 skipped,
  0 RERUN**. The 2 warnings are the same pyqtgraph deprecation as before.
- **Type checks** (`.ai/temp/review-types-2.txt`): `mypy helab/ --strict` (225 files), `mypy tests --strict` (224),
  `pyright helab tests`, `mypy helab/ --strict --platform win32` and `pyright --pythonplatform Windows helab
  tests`: **all clean**.
- **Reproductions.** I reran my scratch scripts for BP-1, BP-2 and BP-3 against the fixed code; results under each
  finding below.
- **CI** 42017707256 is as relayed (green, 0 RERUN in its 12 logs). I didn't refetch its logs.

### Findings

- **BP-1 (Major): fixed** (`259e50a`).
  - In manual mode, `compute` passes keep = 1.0, so an unset or reversed shown axis covers the full extent of the
    events summed.
  - My repro now matches v1: X −0.0147…1.0099 with 0 outside, for both the unset and the reversed axis, and the
    note is true.
  - The new test sets keep to 50 % per plane, which would have failed before. The manual's View range text says
    the same.
- **BP-2 (Minor): fixed** (`aebb27f`).
  - Every drawing, in each library, is marked with its axis (`common.drawn_on`), and `update` refuses another axis
    (`same_axis`) before any library branch.
  - The instance passes `update` the same widget `draw` returned (`_content`, `instance.py:687-698`), so the mark is
    read where it was set. Live updates stay in place.
  - My repro: `update` now returns False on the switch, so the plot is drawn anew. The every-library test asserts
    the refusal and an in-place update of the new drawing.
- **BP-3 (Minor): fixed** (`bb85a67`).
  - `histograms_2d.py` is registered itself, with `Histogram1XY`, `Histogram2XT` and `Histogram3YT`; the three stubs
    are removed.
  - My repro: `helab.v2.xy_histogram v1 · histograms_2d.py (sha256 68073806a168)`, which is that file's own hash.
  - Unchanged: the analysis ids, names, versions, run-button IDs (from the analysis id) and the tree order (XY, XT,
    YT, asserted). The abstract base is skipped, with a log line.
  - The class names change the script ids, but presets and arrangements find plots by analysis id, and v2 hasn't
    shipped.
  - The handoff now proposes the doc note on `common.py` and the hash.
- **BP-4 (Minor): fixed** (`5f9ca07`).
  - `AnalysisInstance.eventFilter` refreshes Plot info on the dock's `plotSourceText` `DynamicPropertyChange`, so the
    main window's relabel reaches it. The new test, where another tab loads another folder, covers it.
  - On close, the dock leaves `dock_widgets` before the page and dock are deleted, so nothing relabels it while
    Plot info is going.
  - A refresh can run twice when the instance relabels its own dock (`_show_follow`); this is harmless.
- **BP-5 (Minor): fixed** (`4bef5dc`). The dock line is in backticks, and the paragraph names the new marks. A test
  rejects bare `<tag>` placeholders outside code on this page.
- **BP-6 (Info): addressed** (`f92b103`).
  - The line ends ` · outdated` for an outdated saved result and ` · ⚠ N` for the run's warnings, and its tooltip
    lists the warnings in full before the record.
  - Each warning is counted once (`dict.fromkeys`). The warnings come from `describe_run`'s two strings,
    `parameter_warnings`, the constants' notes and `describe_result`; for example, v1's reversed-bounds warning
    shows as "⚠ 1".
  - The two extended asserts add checks and weaken none. `outdated` clears after the rerun (asserted).
  - It applies to every plot's dock, which fits the one-line dock.
- **BP-7 (Info): fixed** (`2d31d3b`). There is no `Q~`/`A~` ID left in the branch's own code, docstrings or tests.
  The remaining `git grep` hits are in files outside this branch (`dataset_view.py`, `helab_txy.py`, …).
- **BP-8 (Info): fixed** (`2788f4c`). `info_open`, its slot and `PlotInfo.toggled` are gone; the toggle's checked
  state is the section's state.
- **BP-9 (Info): fixed** (`ffb8ea4`). `test_basic_plots_v2_threads.py` opens and reruns each of the 7 v2 plots from
  the Scripts panel. It asserts `compute` runs off the GUI thread, and `render`, `draw` and `update` on it, with
  each plot updated in place.

### New

- **BP-10 (Info), `helab/views/plots/instance.py:90-92`.**
  - **What's wrong.** `flags()` finds warnings by splitting a description on " · " and keeping the parts that start
    with "⚠ ". A warning whose own text holds " · " is counted as two, the second without its mark, so the dock's
    "⚠ N" could be one low.
  - **Where it matters.** No warning in HeLab's scripts has " · " today; a user's script could.
  - **Suggest.** Nothing now, or have `describe_run` and `describe_result` warnings come as a list later.

**Open findings: none blocking. BP-10 (Info) is the only one open.**

## Re-check 2

Reviewer (Lens), 2026-11-05. Scope: the BP-10 fix, `git diff ffb8ea4 8b3e385` (the code is in `a5fc321`; `8b3e385`
updates the handoff). The `dev/v0.0.9` merge is left out.

### Checks rerun

At HEAD `8b3e385`; output in `.ai/temp/` (not committed):

- **Touched and dock-related tests** (`.ai/temp/review-tests-3.txt`): `test_analysis_gui.py`,
  `test_result_cache_plots.py`, `test_constant_layers.py` (constants' notes), `test_live_plots.py` and every
  `test_basic_plots_v2_*.py`, with `-n 4 --reruns 5 --reruns-delay 1`: **292 passed, 0 RERUN**.
- **Type checks** (`.ai/temp/review-types-3.txt`): all five are **clean**.
- **CI** 42021456513 is as relayed; I didn't refetch its logs.

### Findings

- **BP-10 (Info): fixed** (`a5fc321`).
  - Warnings that come as lists are counted as they come: `parameter_warnings` and the constants' notes.
  - Their `⚠ <warning>` text is taken out of `describe_run`'s and `describe_result`'s text first. Each remaining
    `⚠ ` mark then counts once and runs to the next ` · ⚠ ` or the end (`WARNING_MARK`).
  - `dict.fromkeys` still dedupes. The new GUI test (one listed warning holding " · ", repeated in the settings, and
    one in `describe_result`) reads "⚠ 2" with both warnings in full in the tooltip.
  - A probe confirms the cases: `'a · ⚠ one · ⚠ two'` gives 2, and a listed warning holding " · " repeated in text
    gives none extra.

### New

- **BP-11 (Info), `helab/views/plots/instance.py:91`.**
  - **What's wrong.** A warning that isn't listed and isn't last in its description takes the ordinary parts after
    it into its text. The count stays right, but the tooltip line reads more than the warning. For example,
    `'manual range · ⚠ X: min > max · bins auto'` gives the warning `'X: min > max · bins auto'`.
  - **Where it matters.** Every HeLab script puts its `⚠` parts last (checked by grep over `helab/scripts`), so
    only a user's script could show this.
  - **Suggest.** Nothing needed for landing. It is the trade-off for letting a warning hold " · "; a later contract
    could give descriptions their warnings as a list.

**Open findings: none blocking. BP-11 (Info) is the only one open.**
