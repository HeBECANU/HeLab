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
