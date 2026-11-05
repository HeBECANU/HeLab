# Brief: Basic plots v2 (`agent/basic-plots-v2`)

Coordinator: CoCo, 2026-11-05. Tony asked for this floor in Chat during a live run (relayed by Side): LR-10, LR-12
and LR-13 in `.ai/sessions/2026-11-05-claude-live-run/README.md`. One Worker; one Reviewer at landing.

## What Tony asked for

- **LR-10:** all four Basic plots get a v2. Every v2 plot with a shot axis gets an **X axis setting: Shot ID / Shot
  time**. Shot time is the clock time, from `DatasetView.shot_time` (the raw `d<N>.txt`'s mtime). Shots whose time
  is the TXY file's mtime (`DatasetView.fallback_times`) are marked, as `helab/scripts/dld/shot_times.py` does
  (its `fallback` points and `fallback_text` note).
- **LR-13:** v2 adds **XY, XT and YT plots**: 2D histograms with the third axis flattened (summed over the
  selection).
- **LR-12:** the Scripts panel's group menu shows "Basic plots v1" several times (Tony saw four entries reading the
  same). **Find why and fix it.** Then the menu entry reads **"Basic Plots"**, and the tree under it has the versions
  as nodes (v2, v1, …), newest first, only the newest expanded.
- **v1 stays exactly as it is**: its analysis ids, parameters, results and code, so saved results, presets and
  arrangements keep opening.

## Read first

- `AGENTS.md`, above all "Analysis and plots" (the script contract, `compute` on the worker, `render`/`update` on
  the GUI thread, read-only arrays, `Figure` not `pyplot`, PyQtGraph log axes, units: Basic plots keep s and m with
  SI prefixes) and the UI rules.
- `.ai/architecture/plots-and-scripts.md` (groups, `TreePanelWidget`, `ScriptsManager`, presets, arrangements,
  result caching and analysis ids/versions/hashes) and `testing.md`.
- The code: `helab/scripts/standard/` (v1: `basic_plots.py` with Counts per shot and TXY histograms, `scatter_3d.py`,
  `transfer_fractions.py`, `group.py`); `helab/scripts/dld/` (the DLD port's versions, and `shot_times.py`, the
  model for shot times and fallbacks); `helab/analysis/dataset_view.py` (`shot_time`, `shot_times`,
  `fallback_times`); `helab/views/plots/script_tree.py` (the group selector, `standard.MODULES` registered at
  :516); `helab/analysis/stats.py`, `selection.py`, `overlay.py` (shared helpers v1 uses).
- Memory: `.ai/memory/results/analysis-plots.md`.

## Base and branch

Base: `dev/v0.0.9` at the commit that adds this brief (named in CoCo's message to you). Branch:
`agent/basic-plots-v2`.

Ground has uncommitted live-run work by the Assistant (LR-1, LR-6, LR-7, LR-9: the TXY list, the Activity window,
the Live status bar). It may also take LR-2 (the Scripts panel's Plot button reading "Add" once a plot is open,
in `script_tree.py`), which is waiting on Tony. CoCo merges those into your branch when they are committed. Keep
your `script_tree.py` changes to the group selector and the tree.

## Objective (commit each step separately; stop and report to CoCo at each ◆)

1. **◆ Design first (`design.md` in this folder), before any code.** It covers:
   - **LR-12's cause**, with a reproducing test, and the fix.
   - **The group and the tree:** how "Basic Plots" holds v1 and v2 (a group with version nodes, or two groups shown
     as one), what the other groups (the DLD port, user scripts) look like after it, and the selector's saved choice.
   - **v2's layout:** a new package (proposed: `helab/scripts/standard_v2/`, or modules beside v1), its analysis
     ids (proposed: new ids, e.g. `helab.v2.counts_per_shot`, so no v1 result or preset is reused by mistake), and
     what v2 shares with v1 (shared helpers moved to `helab/analysis/`, not v1's code changed in behaviour).
   - **Which plots have a shot axis** and how Shot time looks: the axis (a date-time axis with the clock time), the
     gaps between runs, the fallback mark and its note, Live (new shots appended), and a shot with no time at all.
   - **XY, XT, YT:** bins (automatic, as v1's histograms, or settable), ranges (the selection's, v1's 99 % crop),
     the colour scale (linear/log), the library (PyQtGraph `ImageItem` proposed), and the parameters.
   - **The tests**, and which existing tests you expect to touch (many tests name v1's group: list them; prefer not
     to change them).
   - Questions for Tony as provisional `Q~1`, `Q~2`… with options and a proposed answer.

   Send CoCo the design with `maestri ask "CoCo" …` and wait for the go.
2. **LR-12:** the cause's fix and the group/tree, with tests.
3. **v2's four plots** with the X axis setting and fallback marks, with tests.
4. **XY, XT, YT**, with tests. ◆ Report after this step, with the suite, the type checks and a pushed branch with
   its CI run.
5. **Docs proposals** in your handoff (`handoff.md`): the architecture section (`plots-and-scripts.md`), AGENTS.md's
   line if any (at most one), the manual (you write `docs/` yourself), and provisional `Q~`/`A~`/`M~` items,
   including an M~ for Tony to try v2 on a real screen and with Live.

## Acceptance

- v1 unchanged: its analysis ids, parameters and output; its existing tests pass untouched (or each change is
  explained).
- The group menu lists each group once; "Basic Plots" holds v2 and v1, newest first, only the newest expanded.
- Every v2 plot with a shot axis has the Shot ID / Shot time setting; fallback times are marked and counted in a
  note, as Shot times does; Live adds shots in either mode.
- XY, XT, YT histogram the selection with the third axis summed.
- **The invariants hold:** `compute` on the worker, `render`/`update` on the GUI thread; no array changed in place
  without `.copy()`; Qt-free analysis code in `helab/analysis/` listed in `PURE`; `Figure`, never `pyplot`;
  saved results NumPy plus JSON; a hook that raises is logged and HeLab goes on.
- **The UI rules hold:** every control has an accessible name and an `identify` ID (`tests/test_accessible_names.py`);
  one-line rows, detail in tooltips; no vertical padding around blocks; gaps from `helab/views/gaps.py`; no lambda
  that captures a Qt-made sender; no Python callable on `destroyed`.

## Rules

**Owned paths:** the v2 package (new files); `tests/test_basic_plots_v2*.py` (new); `docs/` (the manual's pages
for Basic Plots, and `mkdocs.yml`'s nav).

**Edits allowed, kept small:**
- `helab/scripts/standard/__init__.py` and `group.py` (the group's naming and v1/v2 registration only; v1's plots
  untouched);
- `helab/views/plots/script_tree.py` (the group selector and tree, LR-12);
- `helab/analysis/` (shared helpers moved out of v1, behaviour unchanged; a new Qt-free module listed in `PURE`);
- `helab/analysis/dataset_view.py` (read-only accessors only, if needed);
- `tests/test_headless_imports.py`, `tests/test_accessible_names.py` (lists only);
- existing tests that name v1's group, if LR-12 changes the name they see (list them in the design).

**Ask CoCo before any other file**, before changing anything v1 shows or saves, and before changing behaviour an
existing test pins.

**Checks and process:**
- Strict typing, including `mypy --platform win32` and `pyright --pythonplatform Windows`.
- Tests never touch real data. `~/HeLab-samples` is read-only.
- Run `source .ai/local/floor-env.sh` before tests or a manual run. The GUI may run from the floor once
  `$HELAB_TEST_SETTINGS_FILE` is set.
- Before each ◆ and the handoff, run the full suite (`pytest -n 8 --reruns 5 --reruns-delay 1
  --basetemp=.ai/temp/pytest`) and the five type checks, keeping their output whole and reporting every RERUN with
  its reason.
- Docs go in `.ai/sessions/2026-11-05-claude-basic-plots-v2/` only. Don't edit `AGENTS.md`, `.ai/architecture/`,
  `roadmaps/`, `.ai/memory/` or the three `.ai/*_TODO.md` lists; propose those changes in the handoff.
- Public text (the manual, docstrings, plot labels and tooltips) names no person except Tony, and no lab machine,
  internal ID or `.ai/` path.
- Commit freely on your branch. Push only at checkpoints (step 4's ◆ and the handoff). Before you report a CI run,
  read every Tests and Converter backends job's log for RERUN.
- Never delete a branch. No version bump, release, tag, PR or merge.

When done: `maestri floor status "<summary>" --state review`, then
`maestri ask "CoCo" "Basic plots v2: done at <hash>, suite <N> passed, RERUNs <…>, CI <run>"`.
