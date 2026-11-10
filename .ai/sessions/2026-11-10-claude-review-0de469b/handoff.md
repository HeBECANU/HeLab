# Handoff: fixes for the review of dev/v0.0.9 f844c0f..0de469b (`review/v0.0.9-0de469b`)

Worker (Claude, Mender), 2026-11-10. Base `a151050` (`0de469b` + the brief, review and known-issues entries).
Findings from `review.md`; one commit each, each with a test that fails before its fix. **Not pushed yet**: the push
comes after Probe re-reads the fix diff (brief, steps 3 and 4); the full suite and five type checks already pass at
`3751ca8` (below) and run again before the push.

| ID | Commit | Status | What changed |
|---|---|---|---|
| RV-1 | `07cde46`, `22bd1b3`, `3751ca8` | fixed as Tony decided | No cap: `9bbc62d`'s cap reverted (`07cde46`); `histogram2d.MAX_BINS` 20,000 an axis (`22bd1b3`); a memory warning at half the RAM budget, on the settings page as the settings change (Undo, Cancel) and in the plane titles and Plot info (`3751ca8`) |
| RV-2 | `14ef3f7` | fixed | `image_filters.levels` gives the σ step directly (in place); the factor computed in place; `apply(…, check)` called before each step and each adaptive σ step; `plane_counts` passes the run's `check` |
| RV-3 | `0f19fdf` | fixed | `planes_layout` includes each colour group's side (`left_colour_bar`), so a side change draws the plot anew |
| RV-4 | `b446775` | fixed | `docs/how-to/basic-plots.md`: the colour bars (counts one bar right; rates XY left, XT/YT right, each over its own planes) and the rate units (events / mm² / shot, events / (mm·ms) / shot) |
| RV-5 | `633c6ed` | fixed | `_Terminal._run` passes console output through an incremental UTF-8 decoder; `_Terminal(fd, console=None)` (tests give a stand-in), `_console(fd)` |
| RV-6 | `f931243` | fixed | `_swap_handler_streams` lists loggers and handlers under `logging._lock` (at most `LOGGING_LOCK_SECONDS` 2 s, then without it), swaps after releasing it; docstring's reason corrected |
| RV-7 | `bfe4009` | fixed | `tests/test_quit_confirms.py`: `join(5)` → `join(30)` |

## Notes on the fixes

- **RV-1, Tony's decisions (relayed by CoCo, 2026-11-10).** No cap on a plane's total ("I want to keep [the] bin
  limit as it runs just fine on my computer"), then "20k upper limit, and warning also offers an cancel/undo
  button", and a warning once a plot's estimated memory reaches 50 % of HeLab's RAM budget, the plot still running.
  So `9bbc62d` is reverted by `07cde46` (`test_bins_are_capped` back to no cap; the manual's cap sentence gone).
  The revert's message was reworded with `--amend` seconds after `git revert` made it (my own unpushed commit, never
  reviewed, to give it a body and the attribution line); no other commit was amended. Q~1 and Q~2 (the cap's value
  and per-plane scaling) are moot and gone.
- **RV-1, the limit:** `histogram2d.MAX_BINS` 20,000 (the spin boxes, their tooltip and the manual follow it);
  `stats.MAX_BINS` (1D, v1, the DLD port) stays 2,000. `test_bins_are_capped` checks the clamp one axis at a time,
  `(30,000, 1)` → `(20,000, 1)`, so that it never allocates a 20,000² plane.
- **RV-1, the estimate** (`histogram2d.estimated_bytes`, from the code): 16 B a bin held for every plane (int64
  `Histogram2D.counts` + float64 `PlaneCounts.image`), plus the largest plane's moment, as planes are computed and
  coloured one at a time: 32 B a bin while colouring on the GUI thread (`colour_positions`: the image over its peak,
  held through `compress`, its clip and the log path's two temporaries, four float64 arrays at once; that also covers
  the Gaussian, box, median and denoise filters), or 64 B a bin with the adaptive KDE on (about eight images,
  RV-2's measurement). These match Probe's 16 B held + 32 B transient. On the settings page an automatic axis counts
  as its most, 1,000 bins (an upper bound); the run's own note uses the bins it made.
- **RV-1, the contract (CoCo's OK, design (A) plus the hook):** `AnalysisContext.ram_budget: int = 0` (bytes, 0
  unknown), set by `AnalysisRunner.prepare(…, ram_budget=)` from the plot's `RamBudget.cache.max_data_bytes`
  (what `usage.budget` copies at each check, current between checks too); `AnalysisResult.of` doesn't copy it, so it
  is in no result, reuse key, lookup key, family key or digest (test). `DatasetAnalysis.estimated_bytes(action,
  values) -> int`, default 0. `budget_core.ESTIMATE_WARN_SHARE = 0.50`, `estimate_over`, `estimate_text`,
  `ESTIMATE_PREFIX`. The manual's API page (`docs/reference/api/results.md`) says what both mean; the hook's
  docstring renders on the script API page.
- **RV-1, the row** (`helab/views/plots/memory_row.py`, `MemoryRow`; logic in `AnalysisInstance._memory_check`):
  one line between the settings tree and **Rerun with these settings**, zero margins, IDs `plot_memory`,
  `plot_memory_warning`, `plot_memory_undo`, `plot_memory_cancel` with accessible names (covered by the
  accessible-names walk's main-window case). It is checked on a 0 ms timer after every settings-tree change and on
  `RamBudget.changed` (the main window calls `budget.check()` after a new budget). It is hidden with the budget unknown
  (0), for a script whose estimate is 0 (v1, the DLD port, user scripts), and for a hook that raises or returns a
  non-int (logged by `_hook`). **Undo** puts back every analysis setting changed since the settings were last under
  the warning (its tooltip lists them, "Scale 2 (now 7)"), disabled when there were none (a plot opened over it).
  **Cancel** calls `_cancel_run()`, enabled only while a run of this plot is in flight: `job_id` is now a property
  whose setter keeps Cancel in step, rather than touching every place that sets it. One `logging.warning` per plot
  per change of the analysis settings or the budget ("…; it still runs"); a rerun, a Live rerun or a budget check
  with the same settings doesn't log again. The run's note goes in `Planes.notes` (each plot's title, Plotly's and
  Matplotlib's titles) and `describe_result`'s "⚠", which the dock's settings line and Plot info show.
- **RV-1, int32 counts or a float32 image: not done.** float32 would change the numbers users see (colour bar
  ticks, Plotly hover, the totals the filters keep to ~7 digits). Left as they are.
- **RV-2:** `levels` rounds half to even (`np.rint`) where the old `argmin` took the lower step on an exact tie. On
  60,000 random factors and on the ladder itself they agree (test). Peak memory of `apply` with the adaptive KDE is
  now about 8 images (scipy's `gaussian_filter` alone peaks at about 4), down from about 20 (tracemalloc, 600²; the
  test's bound is 12). scipy's filters themselves can't be interrupted: a cancel waits for the current Gaussian.
- **RV-5:** the old loop was also run, outside the suite, with the same stand-in console: it garbled 8 of the 16
  split points of "σ → · é 𝛼" (every split inside a character). The suite's tests fail before the fix only
  because the old `_Terminal` takes no console argument. Not run on a real Windows console (M~2).
- **RV-6:** cheap and safe. The lock is logging's own RLock (`logging._lock`, 3.11–3.14; typeshed doesn't declare
  it, so `getattr`), held only while two lists are built, never while a stream is flushed. The timeout is there so
  a thread stuck holding it can't hang the exit. Note that `threading.RLock` is a function at run time, so the
  `cast` takes the type as a string (unquoted, it would raise at run time on every Python).

## Questions for Tony

None open: RV-1's were decided (above). CoCo asked Tony whether "20k" meant 20,000 an axis (built) or more.

## For an agent later

- **A~1:** the estimate hook is only the 2D histograms' so far. Other plots with large set grids (the DLD port's
  density images, Correlations) could declare `estimated_bytes` too.
- **A~2:** the 2D histograms' arrays count toward the RAM budget only once drawn (`RamBudget`, plots' buffers); the
  warning is the only check before.
- **A~3 (Probe's re-review, Info):** the estimate assumes PyQtGraph's colouring. With Plotly, Plotly 7 also
  base64-encodes `z` and `customdata` (about 2 × 8 B a bin, plus a third for the encoding) and QtWebEngine holds its
  own copy, so a 20,000² plane takes several GB more than the warning says (still the right order to warn about). If
  Plotly is used with fine bins, `PlaneHistograms.estimated_bytes` could add a per-library term (Drawing › Library is
  not among the analysis values today, so it would need the backend passed in).
- **A~4 (Probe's re-review, Info):** `blur_brief` defaults a missing Order to 0, while `blur_steps` defaults it to
  the filter's place + 1. Harmless (a run's values always hold every parameter); align the two defaults when
  `histograms_2d.py` is next touched.

## Checks on a real screen

- **M~1 (RV-1):** in the XY, XT, YT histograms with the RAM budget at its default, raise X, Y and T bins until
  the amber line above **Rerun with these settings** appears ("⚠ Estimated memory … % of the RAM budget …"), as you
  type, before any run. **Undo** puts the bins back and the line goes; set them again, press Rerun, then **Cancel**:
  the run stops ("Cancelled"). Leave it running: the plot draws, and its title says the same. The log has one warning
  for each change. With Show › rate per shot and only XY on, switching Show between counts and rate per shot moves
  XY's colour bar between the right and the left (RV-3).
- **M~2 (RV-5):** on a Windows PC, run HeLab from a console (PowerShell or cmd) and trigger a long log line with
  "σ", "→" or "·" (e.g. a blur note on the XY, XT, YT histograms at DEBUG): the console shows the characters, and
  the console keeps printing afterwards.

## Proposed doc changes (for the Coordinator)

- `.ai/architecture/plots-and-scripts.md`, Basic plots v2's 2D histograms: "`histogram2d.MAX_BINS` 10,000 set by
  hand (2026-11-09, Tony; …)" → "`histogram2d.MAX_BINS` 20,000 set by hand (2026-11-10, Tony; …), with no cap on a
  plane's total". For the filters: "`apply` takes the run's `check`, called before each step and each of the
  adaptive KDE's σ steps; the σ step comes from `levels` (log-spaced ladder, one image's memory)". And:
  "`planes_layout` includes each colour group's side, so a change of side (XY alone, counts ↔ rate) draws anew".
- `.ai/architecture/plots-and-scripts.md`, a new line near the RAM budget's (proposed wording): "**Memory
  estimates** (2026-11-10, Tony): a script may declare `DatasetAnalysis.estimated_bytes(action, values)` (bytes,
  from the settings alone; default 0, none). While it reaches `budget_core.ESTIMATE_WARN_SHARE` (50 %) of the RAM
  budget, the plot's settings page shows `MemoryRow` (`helab/views/plots/memory_row.py`) as the settings change: one
  amber line with Undo (every analysis setting back to the last settings under it) and Cancel (the run in flight,
  `_cancel_run`); hidden with the budget unknown or no estimate; one log warning per plot per change of settings; the
  run goes on either way. A run gets the budget as `AnalysisContext.ram_budget` (bytes, 0 unknown; set by
  `AnalysisRunner.prepare` from the plot's `RamBudget`), never copied into its result, so neither the budget nor the
  estimate enters a reuse key or digest. Basic plots v2's 2D histograms: `histogram2d.estimated_bytes` (16 B a bin
  held for every plane, plus the largest plane's 32 B a bin colouring or 64 B with the adaptive KDE; an automatic
  axis counted at 1,000 on the page), and the run's note in `Planes.notes` and `describe_result`."
- `.ai/architecture/app-runtime-and-ui.md`, the console tee: "a console terminal's output goes through an
  incremental UTF-8 decoder (`_Terminal._run`), so a character split across two pump reads is written whole;
  `_swap_handler_streams` lists the handlers under logging's lock (at most `LOGGING_LOCK_SECONDS`)".
- `roadmaps/known-issues.md`, the `test_the_watch_ends_a_process_left_running_with_its_exit_code` entry: "Fixed
  in `bfe4009` (`join(30)`), on `review/v0.0.9-0de469b`"; close it once that change has been through a few Windows
  CI runs without a rerun.

## Checks run here

RV-1's warning (`3751ca8`): `tests/test_plot_memory_warning.py` (row over / under / budget 0 / no estimate or one
that raises; follows the budget; Undo; Cancel in flight; one log per change), and in
`tests/test_basic_plots_v2_hist2d.py` the estimate from settings, the run's note against the budget, and the budget
never in a result's identity. Whole suite and five type checks at `3751ca8`: 9823 passed, 674 skipped, 2 warnings (PyQtGraph's NumPy deprecation in `test_t_spectrum.py`), no RERUN, in 174 s (`pytest -n 4 --reruns 5 --reruns-delay 1`, output `suite-3751ca8.txt` here); `mypy helab/ --strict` and `--platform win32` no issues (239 files), `mypy tests --strict` no issues (232), `pyright helab tests` and `--pythonplatform Windows` 0 errors (`types-3751ca8.txt` here); `ruff check` and `mkdocs build --strict` pass.

Earlier, per fix: the new tests fail before the fix and pass after; `tests/test_basic_plots_v2_hist2d.py` (121),
`test_density_images`, `test_headless_imports`, `test_basic_plots_v2_v1_frozen`, `test_accessible_names`,
`tests/test_crash_file.py` (36), `tests/test_quit_confirms.py` pass under `-n 4 --reruns 5 --reruns-delay 1`, no
RERUN; `ruff check` and `mkdocs build --strict` pass; mypy --strict, --platform win32 and pyright (both platforms) on
the touched files. The five whole-tree type checks at `f931243`: `mypy helab/ --strict` and `--platform win32` no issues (238
files), `mypy tests --strict` no issues (231), `pyright helab tests` and `--pythonplatform Windows` 0 errors
(output `.ai/temp/worker-types.txt`, gitignored; kept whole in this folder at step 4). The full suite runs after
Probe's re-read (brief, step 4).
