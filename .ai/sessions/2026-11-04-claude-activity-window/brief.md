# Brief: the Activity window (`agent/activity-window`)

Coordinator: CoCo, 2026-11-04. Tony (Chat, 2026-11-04, relayed by Side) approved the feature and a floor on this
Mac: block 62, Q62.1–Q62.5, all decided. One Worker; one Reviewer at landing.

## Read first

- `AGENTS.md`, above all the I/O and threads invariants and the UI rules.
- **The plan: `roadmaps/activity-window.md`.** Its "Decided" section is Tony's and is the spec. Its "Design notes"
  are proposals that you may change in your design.
- The decisions: Q62.1–Q62.5 in `.ai/DECISIONS_TODO.md`, under "Recently decided".
- `.ai/architecture/io-and-browsing.md` (IOService, lanes, slots, pausing, the reaper's exit flag),
  `live.md`, `converter.md` (the GUI's conversions, `ExplorerConverter`), `plots-and-scripts.md`
  (`AnalysisRunner`, `FolderProbes`, reloads), `app-runtime-and-ui.md` (the status bar, windows, `identify`),
  `cache-store.md` (raw_fill, the sweep, budget trims, the cache-folder move) and `testing.md`.
- Starting points in the code:
  - `IOService.activity_counts` and `request_note` and `IOService.cancel(owner, operation)` in `helab/utils/io_service.py`;
  - `FolderCache.cancel` in `folder_cache.py`;
  - `AnalysisRunner` in `helab/analysis/runner.py` and `runner_core.py` (`cancel`, `in_flight`);
  - `LoadClock` in `helab/utils/load_clock.py`;
  - `ExplorerConverter` in `helab/views/explorer_convert.py`;
  - the Live controllers in `explorer_live.py`;
  - `FolderProbes` in `helab/views/plots/script_tree.py`;
  - `CacheMover` in `CacheMover.py`;
  - the status bar in `HelabMainWindow._create_status_bar`;
  - `MemoryUsageWindow.py`, the nearest existing non-modal window.

## Base and branch

Base: `dev/v0.0.9` at the commit that adds this brief (named in CoCo's message to you). Branch:
`agent/activity-window`. This is the only floor open.

## Objective (commit each step separately; stop and report to CoCo at each ◆)

1. **◆ Design first (`design.md` in this folder), before any code.** It covers:
   - **The snapshot.** The Qt-free task model: its fields, where it lives, and which module builds it from each
     source (IOService's active and pending requests, lanes, pause state and held slots; `AnalysisRunner`;
     Live; the GUI's conversions and share questions; cache upkeep; script probes and reloads). Also what each
     source must expose, kept to read-only accessors from memory.
   - **Refresh.** Which signals refresh the snapshot, and the 1 s timer for elapsed times. Keep the cost low with
     the window closed (ideally nothing runs then).
   - **History (Q62.4).** Where finished and failed tasks are recorded, the 200 cap, and which owner reports a
     finish.
   - **Actions (Q62.3).** For each: which owner's existing path it calls, and what the list shows meanwhile.
     "Stopping" lasts until the exit is confirmed. A Retry is refused while the attempt it replaces still holds
     its slot.
   - **Window, columns, details pane and the status bar click (Q62.1).**
   - **The tests**, and which existing tests you expect to touch.

   Send CoCo the design with `maestri ask "CoCo" …` and wait for the go.
2. **The snapshot and its sources**, with tests from fakes (no helpers).
3. **The window**: Window › Activity and a click on the status bar's counts open it; columns, grouping by kind,
   the details pane, the window's remembered size.
4. **The actions** through their owners, and the session history. ◆ Report after this step, with the suite,
   the type checks and a pushed branch with its CI run.
5. **Docs proposals** in your handoff (`handoff.md`):
   - the architecture section, probably in `app-runtime-and-ui.md` with pointers from `io-and-browsing.md`;
   - AGENTS.md's line, if any (at most one, an invariant or a pointer);
   - the manual's page (you write `docs/` yourself; see Owned paths);
   - provisional `Q~`/`A~`/`M~` items, including an M~ for Tony to try the window on a real screen.

## Acceptance

- Everything in Q62.2 is listed while it runs, with a correct state: running, queued, paused, stopping,
  "waiting for files to settle", "no progress for M:SS" or failed.
- Every Q62.3 action works through its owner's existing path. The status bar, Folder details, the quit window
  and the Activity list agree.
- The history holds this session's last 200 tasks, newest first, with failures marked.
- **The invariants hold:**
  - rendering reads memory only and submits no I/O (a `no_source_io` test);
  - the GUI never waits on a cancel, a deadline or a helper;
  - a cancelled helper's task shows "stopping" until its exit flag;
  - a retry never runs beside the attempt it replaces;
  - queues and refreshes stay bounded.
- **The UI rules hold:**
  - every control has an accessible name and an `identify` ID (`tests/test_accessible_names.py`, with the window
    added to its walk);
  - rows are one line, with detail in tooltips and the details pane;
  - no vertical padding around blocks;
  - gaps come from `helab/views/gaps.py`;
  - no lambda that captures a Qt-made sender, and no Python callable on `destroyed`.
- A new `helab/analysis` or `helab/utils` module that is meant to be Qt-free is listed in `PURE`
  (`tests/test_headless_imports.py`).

## Rules

**Owned paths** (new files):
- `helab/utils/activity.py`, or `helab/analysis/activity.py`, for the Qt-free snapshot (say which in the design);
- `helab/views/ActivityWindow.py`;
- `tests/test_activity*.py`;
- `docs/` (the manual's new page and its nav entry, which also edits `mkdocs.yml`).

**Edits allowed, kept small** (read-only accessors, a finish hook for the history, the menu entry and the status
bar's click):
- `helab/utils/io_service.py`;
- `helab/utils/folder_cache.py`;
- `helab/analysis/runner.py` and `runner_core.py`;
- `helab/views/explorer_live.py` and `explorer_convert.py`;
- `helab/views/plots/script_tree.py`;
- `helab/views/CacheMover.py`;
- `helab/views/HelabMainWindow.py`;
- `helab/utils/settings_defaults.py` (only for a new row, e.g. the window's size);
- `tests/test_headless_imports.py` and `tests/test_accessible_names.py` (lists only).

**Ask CoCo before any other file**, and before changing any behaviour an existing test pins (the status bar's
text, Folder details' activity, the quit window).

**Checks and process:**
- Strict typing, including `mypy --platform win32` and `pyright --pythonplatform Windows`.
- Tests never touch real data. `~/HeLab-samples` is read-only.
- Run `source .ai/local/floor-env.sh` before tests or a manual run. The GUI may run from the floor once
  `$HELAB_TEST_SETTINGS_FILE` is set.
- Before each ◆ and the handoff, run the full suite (`pytest -n 8 --reruns 5 --reruns-delay 1
  --basetemp=.ai/temp/pytest`) and the five type checks, keeping their output whole and reporting every RERUN
  with its reason.
- Docs go in `.ai/sessions/2026-11-04-claude-activity-window/` only. Don't edit `AGENTS.md`, `.ai/architecture/`,
  `roadmaps/`, `.ai/memory/` or the three `.ai/*_TODO.md` lists; propose those changes in the handoff.
- Commit freely on your branch. Push only at checkpoints (step 4's ◆ and the handoff). Before you report a CI
  run, read every Tests and Converter backends job's log for RERUN.
- Never delete a branch. No version bump, release, tag, PR or merge.

When done: `maestri floor status "<summary>" --state review`, then
`maestri ask "CoCo" "Activity window: done at <hash>, suite <N> passed, RERUNs <…>, CI <run>"`.
