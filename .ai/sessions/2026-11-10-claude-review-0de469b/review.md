# Review: dev/v0.0.9 f844c0f..0de469b (`review/v0.0.9-0de469b`)

Reviewer (Claude), 2026-11-10. Range `git diff f844c0f..0de469b` (six commits, 22 files). Read in full:
`histogram2d.py`, `image_filters.py`, `parameters.py`/`parameter_tree.py` (nested groups),
`standard_v2/histograms_2d.py`, `console_tee.py`, `gui_watchdog.py`, `dock.py` (floating windows), and the
tests, docs and architecture notes the commits changed.

**Summary: no High. 2 Medium, 3 Low, 2 Info.** Full suite and all five type checks pass here (below).

| ID | Severity | Where | What |
|---|---|---|---|
| RV-1 | Medium | `helab/analysis/histogram2d.py:27`, `standard_v2/histograms_2d.py:60` | Nothing limits a plane's total bins: 10,000 × 10,000 is 1.6 GB held per plane, 4.8 GB for three, plus 3.2 GB more per plane on the GUI thread while it draws |
| RV-2 | Medium | `helab/analysis/image_filters.py:84` | Adaptive KDE allocates H × W × 9 float64 values to pick each bin's σ step: 2.7 GB at 4,000², about 17 GB at 10,000², per plane, and it can't be cancelled |
| RV-3 | Low | `standard_v2/histograms_2d.py:884` | PyQtGraph's in-place update leaves XY's rate bar on the wrong side when Show changes and only XY is on |
| RV-4 | Low | `docs/how-to/basic-plots.md:62`, `:101` | The manual still says one colour bar on the right and rates per m² and m·s |
| RV-5 | Low | `helab/utils/console_tee.py:67-73` | On a Windows console, a UTF-8 character split across two pump reads is lost or garbled |
| RV-6 | Info | `helab/utils/console_tee.py:198-206` | `_swap_handler_streams` loops over `loggerDict` in Python code without logging's lock |
| RV-7 | Info | `tests/test_quit_confirms.py:36` | The CI RERUN in run 42621021439 (outside this range): `join(5)` is too short on a loaded Windows runner |

---

## RV-1 (Medium): nothing limits a plane's total bins at the new 10,000 per axis

**Where:** `helab/analysis/histogram2d.py:27` (`MAX_BINS = 10_000`) and `:80-84` (`_bins`), and
`helab/scripts/standard_v2/histograms_2d.py:60-63` (the T/X/Y bins spin boxes, limit `(0, MAX_BINS)`). The
image also passes through `plane_counts` (`:501-524`), `colour_positions` (`:478`, GUI thread), `fill`
(`:917`) and `planes_plotly` (`:993-997`).

**Failure scenario:** the user sets X, Y and T bins to 10,000 (the spin boxes allow it, and the manual says
"up to 10,000"). Each plane becomes 10⁸ bins. `histogram2d` makes float64 counts and then an int64 copy;
`image_filters.apply` makes a float64 copy; the rate per shot makes another. The result keeps
`Histogram2D.counts` (int64) and `PlaneCounts.image` (float64), 1.6 GB per plane and 4.8 GB with all three
planes on. On the GUI thread, `colour_positions` → `compress` allocates temporaries of the same size for
every plane, and PyQtGraph then builds its own RGBA image. Plotly turns `z` and `customdata` (2 × 10⁸
numbers per plane) into JSON. A lab PC with 8 to 16 GB swaps or runs out of memory, and the process can be
killed. Nothing counts this memory against HeLab's RAM budget. A Live rerun allocates it all again.

**How confirmed:** measured with `tracemalloc` (1M events, `PER_SHOT`, Gaussian σ 1):

| | held | peak | time |
|---|---|---|---|
| `plane_counts` XY 10,000 × 10,000 | 1.60 GB | 2.40 GB | 1.3 s |
| `colour_positions` (GUI thread, log scale) | | +3.20 GB | 0.5 s |
| `histogram2d` 4,000 × 4,000 | 0.13 GB | 0.31 GB | 0.2 s |

Script: `/private/tmp/claude-501/-Users-tonyyan-GitHub-Local--maestri-floors-HeLab--reviewv009-0de469b--maestri-roles-ad0cf91f-a0be-4ee9-8846-f3dca8f70a29/297012a1-51ed-431f-a335-de3310452b67/scratchpad/mem10k.py`
(not committed). Before this range, `stats.MAX_BINS` = 2,000 kept a plane at 4 × 10⁶ bins at most, so the
same steps cost 25 times less.

**Proposed fix:** keep 10,000 per axis (Tony's limit) but cap each plane's total, for example
`MAX_PLANE_BINS = 16_000_000` (4,000²) or 25 M. When the product is over the cap, scale both axes down in
proportion and add a note to the plane ("bins capped at … for memory", like the σ cap's note). Optionally keep
`counts` as int32 and the image as float32. The cap's value is Tony's choice: propose it as `Q~1`. A test:
`histogram2d(events, "XY", 1.0, (10_000, 10_000)).counts.size <= MAX_PLANE_BINS`, with the note.

## RV-2 (Medium): Adaptive KDE uses 9 times the image's memory to pick σ steps, and can't be cancelled

**Where:** `helab/analysis/image_filters.py:84`:
`level = np.abs(np.log(factor)[..., None] - np.log(ladder)).argmin(axis=-1)`

**Failure scenario:** the broadcast makes an H × W × `LEVELS` (9) float64 array, plus its `abs`. With
Adaptive KDE on at large set bins, compute needs about 170 bytes per bin. That is 2.7 GB at 4,000 × 4,000 and
about 17 GB at 10,000 × 10,000, for each plane, in the GUI process's worker thread. `apply` and its steps never
call the runner's `check`, so a long filter chain (2 s at 4,000², about 13 s or more at 10,000²) can't be
cancelled, and Live queues behind it.

**How confirmed:** measured (`scratchpad/mem.py`, 1M events, σ 2, α 0.5): Gaussian peaked at 0.26 GB, adaptive
at 2.70 GB (2.1 s), denoise at 0.51 GB, all at 4,000²; at 2,000², adaptive peaked at 0.68 GB. The ratio fits the
broadcast.

**Proposed fix:** the ladder is log-spaced, so compute the step directly:
`step = 2 * log(ADAPTIVE_RANGE) / (LEVELS - 1)`, then
`level = np.clip(np.rint((np.log(factor) + np.log(ADAPTIVE_RANGE)) / step), 0, LEVELS - 1).astype(np.intp)`.
This allocates one H × W array. Exact ties may round to the other step (`rint` rounds half to even), which
`test_the_adaptive_kde_smooths_faint_regions_more_than_bright_ones` won't notice. Also pass `check` into
`image_filters.apply` and call it between steps and between adaptive levels. Fix together with RV-1.

## RV-3 (Low): in-place update leaves XY's rate bar on the wrong side

**Where:** `helab/scripts/standard_v2/histograms_2d.py:884-888` (`planes_layout`) and `:860-869` (`update`).
The bar's side is set only in `draw` (`:793`, `:826-836`).

**Failure scenario:** only XY is on. The plot shows counts, so its bar is on the right (column 1). The user
switches Show to "rate per shot". `colour_groups` gives `(("XY",),)` both times, so `planes_layout` is equal
and `update` fills the plot in place: XY's rate bar stays on the right. A fresh draw of the same result puts it
on the left (column 0), as the commit and the architecture note say ("XY's rate bar sits on the left … in every
backend"). Switching back leaves a counts bar on the left. Plotly and Matplotlib rebuild their figures, so only
PyQtGraph is affected.

**How confirmed:** a scratch test (`scratchpad/edge/test_side.py`, run with the suite's conftest).
`draw(counts)` then `update(widget, rate)` returned True, with `widget.plane_bar.inset_column == 1`, while
`draw(rate).plane_bar.inset_column == 0`.

**Proposed fix:** add each group's side to `planes_layout`, e.g.
`tuple(left_colour_bar(group) for group in colour_groups(data))`, so the change draws the plot again. Make the
scratch test a real test in `tests/test_basic_plots_v2_hist2d.py`.

## RV-4 (Low): the manual wasn't updated for 0de469b's units and colour bars

**Where:** `docs/how-to/basic-plots.md:62-63`: "The planes share one set of settings and one colour bar, right
of the last plane. Each image is coloured over the same range, from 0 to the highest bin of the planes shown".
And `:101-102`: "a rate per shot (counts per shot per bin area: per m² for XY, per m·s for XT and YT)".

**Failure scenario:** since 0de469b, a rate per shot is in events/(mm²·shot) and events/(mm·ms·shot). XY's bar
is on the left and XT/YT's on the right, each over its own range. The manual (public text, Help › User manual)
still describes the old behaviour, and its units are wrong by 10⁶. The commit says "Document the behaviour", but
it changed only `.ai/architecture/plots-and-scripts.md`, not the manual.

**How confirmed:** reading. `git diff ceb7419..0de469b --stat` shows no file under `docs/`. The code's units
are at `histograms_2d.py:206-207`, `:427` and `:517`.

**Proposed fix:** rewrite the two paragraphs. Counts share one bar on the right, over 0 to the highest bin. A
rate per shot is per mm² for XY and per mm·ms for XT and YT, with XY's bar on the left and XT/YT's on the
right, each over its own planes' highest bin. Run `mkdocs build --strict`.

## RV-5 (Low): a UTF-8 character split across two pump reads is lost or garbled on a Windows console

**Where:** `helab/utils/console_tee.py:67-73` (`_Terminal._run`):
`written = self.console.write(view) …; view = view[written or len(view):]`

**Failure scenario:** the pump reads up to 64 KiB at a time, wherever the pipe's contents end. Windows pipes are
small, so a large write (a stack dump, a long log line with "σ", "→" or "·") can be read in two parts. When a
part ends inside a multibyte character, `_WindowsConsoleIO.write` writes only up to the last whole character.
The loop then passes the 1 to 3 leftover bytes on their own, which the console can't write: they come back as 0
written, and `written or len(view)` drops them, or CPython raises `OSError`, and then `_run` returns and the
console shows nothing more for the rest of the run. Older CPython writes the partial bytes as U+FFFD. In every
case the character on the console is garbled or gone. The file always has the right bytes.

**How confirmed:** a scratch run (`scratchpad/term.py`) with a stand-in console whose `write` stops before an
incomplete UTF-8 tail, as `_WindowsConsoleIO.write` does since gh-82052. For "σ → ·" put as two chunks split
inside "σ", the console got `b'\x83 \xe2\x86\x92 \xc2\xb7'`: the lead byte was lost and a stray continuation
byte was written. CPython's behaviour for a lone partial tail comes from reading its source and wasn't run on
Windows here.

**Proposed fix:** in `_run`, keep what the console didn't take and put it in front of the next chunk
(`pending = view[written:].tobytes()` when `0 <= written < len(view)` and the rest is a partial character).
Drop bytes only on a real error, and don't end the thread on `OSError` from a partial character. A test with a
fake console like the one above, run on every OS.

## RV-6 (Info): `_swap_handler_streams` loops over `loggerDict` without logging's lock

**Where:** `helab/utils/console_tee.py:198-206`.

The generator steps through `logging.Logger.manager.loggerDict.values()` in Python code, so a thread switch can
happen between items. If another thread creates a logger then, the loop raises
`RuntimeError: dictionary changed size during iteration`. This runs only where a stream was rebound (a Windows
console). At `start` few threads exist, but `stop` runs at exit, and a raise there skips putting fds 1 and 2
back and closing the file. Fix: take a snapshot under logging's lock
(`with logging._lock: loggers = list(...)`, or `logging._acquireLock()` on older Pythons). The docstring's
reason is also wrong: coloredlogs' `StandardErrorHandler` reads `sys.stderr` on every record (checked with
`inspect`), so coloredlogs follows the rebind by itself. Only a handler built with an explicit
`StreamHandler(sys.stderr)` needs the swap. The swap is harmless either way. Confirmed by reading; a race isn't
practical to reproduce.

## RV-7 (Info): the CI RERUN in run 42621021439 (outside this range)

`windows + py3.13 / Tests (2/3)` (job 129172975176, head `0de469b`), the summary's rerun reasons:
`RERUN tests/test_quit_confirms.py::test_the_watch_ends_a_process_left_running_with_its_exit_code`,
`assert [] == [3]` at `tests\test_quit_confirms.py:37`. It passed on the rerun. The test started at 13:04:17. The
watch thread's "still running" warning, which comes after `still_running()` formats every thread's stack,
appeared at 13:04:25, but the test's `join(5)` gave up after 5 s. On a loaded Windows runner the stack
formatting (linecache reads) took over 5 s. `helab/views/quit_watch.py` and this test aren't in the range.

**Could 96df3ed's console tee have left a blocking handler behind (CoCo's question)? No.**
- conftest sets `HELAB_NO_CONSOLE_FILE` (`tests/conftest.py:50`), so `console_tee.start` returns None in every
  test process (`test_the_console_file_is_off_under_the_test_suite`).
- The two tests that start a tee do it in child processes (`test_crash_file.py:131` and `:165`, inside `-c`
  scripts).
- The one test that runs tee code in its own process
  (`test_a_terminal_that_takes_nothing_never_stops_the_pump`) builds a `ConsoleTee` but never calls `start()`,
  so it doesn't call `dup2` or rebind `sys.stderr` or any handler, and its `stop()` has nothing to restore. It
  closes its `_Terminal` in `finally` and checks that the thread has ended.
- The failing run's own thread dump, which `still_running()` logged from that worker, lists only `MainThread`,
  `DashServer`, `pytest_timeout …` and `HeLab-quit-watch`. No `console-tee-*` pump or
  `console-tee-terminal-*` thread was alive.
- In that dump the quit-watch thread is in `still_running()` → `traceback.format_stack`, before the warning and
  the handler flush, and the warning was then logged. The thread was slow, not blocked by a handler.

Proposed: `join(30)` in the test (it costs nothing when the test passes). CoCo's entry `834bdeb` in
`roadmaps/known-issues.md` covers it.

---

## Checked and found clean

- **Histogram numerics:** `PLANES`' new orientation agrees everywhere (counts are (horizontal, vertical), and
  `Step.sigma` and `gaussian_filter`'s axes follow it). Rates: `bin_area × 1e6` is m² → mm² and m·s → mm·ms,
  and the rate is applied after the filters, which run on counts. Bins over the limit are clamped. The single-
  value and empty ranges are unchanged from before the range.
- **Filters:** chain order (Order, then `FILTERS`' order); caps per axis; median and box sizes capped by the
  smaller side; Gaussian, units, box, denoise and adaptive keep the total; denoise on an all-zero image stays 0;
  adaptive with α 0 is a plain Gaussian; an empty image returns at once; the units σ becomes bins per axis.
- **Edge cases, all three backends** (scratch test `scratchpad/edge/test_edges.py`, 30 cases): one event; five
  identical events; counts; rate per shot with log scale; dots by summed axis; dots by local density with log
  scale and rate per shot; all six filters on. Every image is finite, every backend draws, and `update` works in
  place.
- **Threads:** all the numerics are in `compute`. `render`/`update` only map colours and set data. The input is
  never changed (`apply` copies, the events are read-only, `test_the_input_is_left_unchanged`). The dots sample
  is fixed (`display_sample`, seed 0) and bounded by Max dots (at most 5 M).
- **Watchdog (96df3ed):** the stacks go through a regular temp file into the log, never fds 0–2. 60 s before the
  first beat and 2 s after; `max_delay` leaves out the first beat. The watching thread never calls Qt, and the
  GUI thread never waits.
- **Console tee (96df3ed):** the pump writes the file first and never waits on the terminal; the terminal queue
  is bounded (256 × 64 KiB). Stop has timeouts, and a stuck terminal's descriptor is left open for its thread.
  With no console (pythonw, frozen), `os.dup` fails, so the file alone, and the rebind skips a `None` stream.
  The rebind is restored at stop.
- **Floating windows (61f5832):** the polling timer is the dock's child, so it goes with the dock.
  `_as_window` returns if the dock was docked during the drag. The hide and show from `setWindowFlags` are
  absorbed by the settings panel's next-pass check (`_shown_still_visible`). An arrangement's
  `setFloating(True)` goes through the same path. Not verifiable here: whether, on Windows, a parented
  `Qt.Window` can go behind the main window (an owned window can't), and native-title-bar drag-to-dock. Both
  are in M69.1.
- **Saved results, presets, arrangements:** `PlaneHistograms` declares no `cache_types`, so its results are never
  written to the disk cache (as at f844c0f); the mm² change can't show old numbers under new labels. The old ids
  `helab.v2.{xy,xt,yt}_histogram` aren't in the `v0.0.8a1` tag (the file isn't there). Presets and arrangements
  are checked against the installed script (`presets.check_plot`), which names each problem.
- **Nested settings groups:** every reader of `ParameterSpec.group` goes through `group_path`
  (`tree_children`, `parameter_of`, `settings_widget`).
- **Tests:** they test what the commits claim. In `test_a_terminal_that_takes_nothing_never_stops_the_pump`,
  296 × 64 KiB stays under `CAP`, so no rotation breaks its size check.

## Checks run here (head cb5cf8a = 0de469b + the brief)

- `pytest -n 4 --reruns 5 --reruns-delay 1 --basetemp=.ai/temp/pytest-review`: **9790 passed, 674 skipped, 2
  warnings in 233 s, no RERUN.** The 2 warnings are PyQtGraph's NumPy 2.5 `arr.shape` deprecation in
  `test_t_spectrum.py`. Output: `.ai/temp/review-suite.txt`.
- `mypy helab/ --strict`, `mypy tests --strict`, `mypy helab/ --strict --platform win32`: no issues (238, 231,
  238 files). `pyright helab tests` and `pyright --pythonplatform Windows helab tests`: 0 errors. Output:
  `.ai/temp/review-types.txt`.

---

## Re-review of the fix diff (`71ba4f7..49aa1a6`, Reviewer, 2026-11-10)

I read the code diff of the eleven commits and the handoff, reran my own reproductions against the fixes, and ran
the full suite and the type checks myself at `49aa1a6`. **Every finding is closed. No new blocker.**

| ID | Fix | Status | How checked |
|---|---|---|---|
| RV-1 | `07cde46`, `22bd1b3`, `3751ca8` | **closed (as Tony decided: no cap)** | No cap; `MAX_BINS` 20,000 an axis; a memory warning at 50 % of the RAM budget on the settings page (Undo, Cancel) and in the run's notes. Read `estimated_bytes` (16 B a bin held for each plane, plus the largest plane's 32 B, or 64 B with adaptive), which matches my measurements. `ram_budget` is on the context only, not in `AnalysisResult.of`, so it's in no key (tested). Cancel follows `job_id` through a property; the row has accessible names and IDs. The budget connection is undone at close, and the timer stops. Read `tests/test_plot_memory_warning.py` (6 tests). |
| RV-2 | `14ef3f7` | **closed** | `levels` works in place, and `check` is called before each step and each σ step. My `mem.py` at 4,000²: adaptive's peak is **0.67 GB, down from 2.70 GB** (1.5 s). |
| RV-3 | `0f19fdf` | **closed** | `planes_layout` now includes each group's side. My scratch run: `update(counts → rate, XY alone)` returns **False**, so the plot is drawn again (my old assertion checked the widget it had replaced). The new test `test_xy_alone_redraws_its_bar_on_its_side_when_show_changes` covers it. |
| RV-4 | `b446775` (+ `22bd1b3`, `3751ca8`) | **closed** | The manual now gives the colour bars, the units (events / mm² / shot, events / (mm·ms) / shot), 20,000 bins and the warning. `docs/reference/api/results.md` explains `ram_budget` and `estimated_bytes`. Public text names no person or internal ID. |
| RV-5 | `633c6ed` | **closed** | An incremental UTF-8 decoder on the console path only (pipes and files still get raw bytes). My stand-in console, every split point of "σ → · é 𝛼": **0 of 16 garbled**, against all 8 splits inside a character before. Still not run on a real Windows console (handoff M~2). |
| RV-6 | `f931243` | **closed** | Handlers are listed under `logging._lock` (an RLock; at most 2 s, then without it) and swapped after it is released. The docstring's reason is corrected. |
| RV-7 | `bfe4009` (+ `a151050`, CoCo's) | **closed** | `join(30)`; the known-issues entry gives the cause. |

**Notes (Info, no action needed):**

- The estimate assumes PyQtGraph's colouring. Plotly 7 also base64-encodes `z` and `customdata` (about 2 × 8 B a
  bin, plus a third more for the encoding) and QtWebEngine holds its own copy, so with Plotly a plane at 20,000²
  takes several GB more than the warning says. It's still the right order of magnitude to warn about. It could
  become an A~ item if Plotly is used with fine bins.
- `blur_brief` defaults a missing Order to 0 while `blur_steps` defaults it to the filter's place + 1. It's
  harmless, because the run's values always include every parameter.

**Rerun here at `49aa1a6`:** `pytest -n 4 --reruns 5 --reruns-delay 1 --basetemp=.ai/temp/pytest-review`:
**9823 passed, 674 skipped, 2 warnings (PyQtGraph's NumPy deprecation) in 188 s, no RERUN**. `mypy helab/ --strict`
and `--platform win32`: no issues (239 files); `mypy tests --strict`: no issues (232). `pyright helab tests` and
`--pythonplatform Windows`: 0 errors. `ruff check`: passed. My scratch edge cases (30, all three libraries) still
pass.
