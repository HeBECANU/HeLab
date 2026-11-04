# Handoff: the Activity window (`agent/activity-window`)

Beacon (Worker), 2026-11-04. Base `63b9a15` (dev/v0.0.9), `origin/dev/v0.0.9` (`c0860ec`, Side's Windows fix
for `test_cache_tab`) merged in as `cab0f3b` before any code. Design: [design.md](design.md) (CoCo's go,
with answers (1)–(4) and (a)–(d)).

## Commits

| Commit | Step |
|---|---|
| `9252fe3` | 1 · design |
| `cab0f3b` | merge of `origin/dev/v0.0.9` (`c0860ec`) |
| `3c07a66` | 2 · the snapshot and its sources |
| `0c45c27`, `1fd54b6` | 3 · the window (and a test's typing) |
| `33b913f` | 4 · the actions through their owners, and the history |
| `f76f7e2` | 5 · the manual's page |
| `a141e60` | Windows CI fix: owners' paths compared as folders; wider default size |
| `d0e203a` | Windows CI fix: a raw fill cancelled under the owner it was queued with |
| `b2e996a` | 5 · handoff |
| `3afddf4` | Gauge's review |
| `c906528` | AW-1, AW-13 · the Now tree survives rows changing group or parent; headings count shown rows |
| `41de473` | AW-2 · successful conversion passes, details scans and cached reads stay out of the history |
| `3798dea` | AW-3 · Cancel all queued never stops a running task; Cancel says it stops a tab's other loads |
| `7682d6c` | AW-4 · `@pyqtSlot()` back on `_reload_clicked` |
| `384f93f` | AW-5 · conversion failures that start no helper go in the history |
| `33b1489` | AW-6 · a history listener's error is logged, never raised into the reporter |
| `a429d15`, `df13e56` | AW-7, AW-8 · the manual's lines; no internal ID in a details line |
| `a3eb1c7` | AW-9 · the saved size fitted to the screen |
| `a69c9d4` | AW-10 · unique history keys; the History tab updated in place |
| `0c653c1` | AW-12 · log lines name the folder itself |
| `d4593c8` | AW-11 · the memory-only test covers a tab's rows and the history |
| (this commit) | the handoff, after the review |

## What is built

- **`helab/utils/activity.py`** (Qt-free, in `PURE`): `Task`, `Snapshot`, `Counts`, `Finished`, `Route`,
  `Progress`; the pure rules (`request_state`, `group_of`, `kept_in_history`, `io_tasks` with a held
  retry merged into its stopping attempt, `analysis_tasks`); `HISTORY` (200, newest first, added to on
  the GUI thread only: `History.add` asserts it); `LogLines` (the session's last 500 warnings, in
  memory) with `install_log_lines` / `remove_log_lines`.
- **`helab/views/ActivityWindow.py`**: `ActivitySources` (the snapshot from IOService and FolderCache,
  each tab's Live sessions, auto-convert, GUI conversions and converter questions, the analysis runner,
  probes and reloads, the cache move; memory only), `ActivityActions` (each action through its
  owner), `ClickOpens` (the status bar's click), `ActivityWindow` (Now and History tabs, details pane,
  buttons; nothing runs while hidden; size in `activity_window_size`).
- **The main window**: Window › Activity (`window_activity`), a click on `status_activity` opens it,
  its tooltip's last line is "Click for Activity" (`ACTIVITY_HINT`); `LogLines` installed at start and
  removed in `closeEvent`.
- **Owners' additions** (read-only accessors, finish reports, the hold): see "Files changed".

## Deviations from the design (for the Reviewer)

1. **Builders' homes.** Live, conversion, question, probe and move rows are built in
   `ActivitySources` (Qt side), since `LiveSession`, `FolderConversion` and the boxes live in Qt
   modules; `activity.py` keeps the pure rules, the I/O rows (through `RequestLike`) and the analysis
   rows (through `RunInfo`, a `TYPE_CHECKING` import).
2. **History titles.** A finished request is named by its operation (`IOService.LABELS`, or "Live
   check"), not `IOService.label`, which says "Save data cache" for any completed load.
3. **Live's successful plot reruns** aren't kept in the history either (`AnalysisRunner._live_jobs`):
   with Live, every plot reruns on each new shot and would fill the 200 within minutes. Failures and
   cancellations are kept. Part of Q~2.
4. **A cancelled shared job's owners.** FolderCache forgets a job before cancelling its helper
   (`_forget_job`, then `service.cancel`), so its history entry records the producer's owner, not its
   tabs: Show in tab and Retry from History aren't offered for it (failures keep their tabs: the report
   runs before FolderCache hears of the error). A~1.
5. **Step 3's commit** had placeholder action methods; step 4 replaced them (each step commits on its
   own, as briefed).
6. **Paths compared as folders.** Owners name a folder by different strings (`FolderCache.key`'s abspath
   on a request, a session's or a selection's own path; on Windows `/live` vs `D:\live`), so the
   window compares them with `FolderCache.key` (`same`, `session_of`, `watching`), and
   `IOService.unexited` compares both sides by `os.path.abspath`. The default size is 1080×440 (the
   button row needs about 1,070 px with Windows' fonts).
7. **No per-tab signals.** The window refreshes on IOService's `activityChanged` and terminal
   `resultReady` kinds, FolderCache's `quitSavesChanged`, each runner's `finished`, history appends,
   and the 1 s tick; Live's and conversions' own state changes show within a second. A~2 if that
   proves slow.

## Files changed outside the owned paths (all allowed by the brief or by CoCo)

- `helab/utils/io_service.py`: `IORequest.last_event`, `queued_at`, `reported`; `_ended` /
  `_report_end` at every terminal emit; `unexited`; the user hold (`user_hold`, `set_user_hold`,
  `user_held`, in `_dispatch`, `_apply_pauses`, `queue_tooltip`, and `activity_counts`' "paused by you",
  `USER_HOLD_NOTE`).
- `helab/utils/folder_cache.py`: `job_of`, `admin_action`, `finishing_of`, `raw_filling`,
  `cancel_raw_fill`; `cancel_for_quit` lifts the user hold.
- `helab/analysis/runner_core.py`, `runner.py`: `RunInfo`, `jobs()`; the runner's history report from a
  GUI-thread slot (`_record`).
- `helab/views/explorer_live.py`: `sessions()`; Live off's report; `_convert_stopped` (AW-5). `explorer_convert.py`: the
  conversion's end report (`_report`). `plots/script_tree.py`: `FolderProbes.activity()`,
  `TreePanelWidget.probe_activity()` / `reload_waiting()` / `probe_limits()`; the probe's end report. `CacheMover.py`: the
  move's end report (in `_end`).
- `helab/views/HelabMainWindow.py`: the Window menu, the window, the click, the tooltip line, the log
  handler.
- `helab/views/FolderExplorer.py`: one public `retry()` calling `_retry` (CoCo's go, answer (2)).
- `helab/utils/settings_defaults.py`: the `activity_window_size` row.
- `tests/test_headless_imports.py` (`PURE` gains `helab.utils.activity`), `tests/test_accessible_names.py`
  (`DIALOGS` gains the window), **`tests/test_folder_cache.py`: the two assertions that pin the status
  message's tooltip exactly (`:384`, `:436`) now expect "Click for Activity" as its last line (CoCo's
  go)**.
- `docs/how-to/activity.md` and `mkdocs.yml` (the manual's page, after "Follow a folder live").

## Checks

**After the review fixes** (`d4593c8` and this commit):
- Full suite, `pytest -n 8 --reruns 5 --reruns-delay 1 --basetemp=.ai/temp/pytest`: **9391 passed, 673
  skipped, 2 RERUN** (output kept whole in `.ai/temp/activity-suite-review.txt`), both of one existing test,
  `tests/test_gui_responsiveness.py::test_rendering_never_reads_filesystem_or_disk_cache`: reasons
  `(teardown) AssertionError: GUI rendering performed I/O / RuntimeError: Failed to process unraisable
  exception` and, on its rerun, `(setup) … Failed to process thread exception`; it passed on the next. The test
  starts no thread of its own and guards `os.scandir` / `os.stat` for every thread started after its patch
  (`conftest.this_tests`), so a thread another test left (a helper's reader finishing and starting its
  `HeLab-artifact-cleanup` `shutil.rmtree`, which scandirs) running then raises there. Not reproduced in three
  runs of the activity files followed by `test_gui_responsiveness.py` in one process. Proposed for
  known-issues below.
- The five type checks: clean (`.ai/temp/activity-types-review.txt`). `ruff check`; `mkdocs build --strict`.
- CI: CI_REVIEW

**Before the review** (`b2e996a`):

- Full suite, `pytest -n 8 --reruns 5 --reruns-delay 1 --basetemp=.ai/temp/pytest`, at `d0e203a`:
  **9382 passed, 673 skipped, no RERUN** (output kept whole in `.ai/temp/activity-suite-step4c.txt`; the
  same at `33b913f` and `a141e60`).
- `mypy helab/ --strict`, `mypy tests --strict`, `pyright helab tests`, `mypy helab/ --strict --platform
  win32`, `pyright --pythonplatform Windows helab tests`: all clean.
- `ruff check`; `mkdocs build --strict -d .ai/temp/site` (in a throwaway `.ai/temp/docs-venv` from
  `requirements-docs.lock`, so the floor's venv is unchanged); `tests/test_docs_workflows.py`,
  `tests/test_user_manual.py`.
- **CI: run `41796851699` on `d0e203a`: green, every job** (Tests 1/3, 2/3, 3/3 and Converter backends on
  macOS, Windows and Ubuntu, Build ×3, Docs); every Tests and Converter backends log read: **no RERUN**.
- Earlier runs: `41792160550` (`33b913f`) failed Windows Tests 1/3 and 3/3 (four new tests: Windows' keyed
  paths `D:\live`, and the button row's 1,074 px), fixed in `a141e60`; `41794579242` (`a141e60`) failed
  Windows Tests 1/3 (`cancel_raw_fill` keyed its path), fixed in `d0e203a`, and **Ubuntu Tests 1/3 had one
  RERUN**: `tests/test_load_queue.py::test_an_automatic_load_waits_for_the_selection_to_settle_only_while_loads_are_busy`,
  reason `assert (False) where False = FolderExplorer.settling` at `tests/test_load_queue.py:674` (passed on
  its rerun). That test drives `FolderExplorer` only (no Activity code), its settle wait runs on real
  timers (`SETTLE_MAX` 1.0): proposed for known-issues below.
- Windows paths are also checked locally with a simulation of Windows' `abspath` (made-up `/x` paths keyed
  to `/K/x`; a pytest plugin in the session's scratchpad, not committed), which fails on the old
  `cancel_raw_fill` and passes now on all three new test files.

New tests: `tests/test_activity.py` (19: rules, history, every source's rows), `test_activity_window.py`
(9: opening, groups and columns, details, in-place rows, nothing while hidden, bounded refreshes,
memory-only rendering with source access and I/O submits denied, the remembered size, the main window's
menu and click), `test_activity_actions.py` (17: each Cancel route, stopping until the exit flag, Cancel
all queued leaving saves, Retry refused until the old attempt exits, Retry/Stop Live/Show through
owners, the user hold never pausing the foreground or local lane, saves or Live checks, quitting lifting
it, the window's buttons, and each owner's history report). Each test file resets `HISTORY` and
`LogLines` and takes the handler off the root logger (an autouse `fresh_activity`, answer (b)).

## Review fixes (Gauge's AW-1 to AW-13, `3afddf4`)

All fixed as Gauge suggested, with CoCo's decisions on AW-3 (one row's Cancel stays the toolbar's Cancel,
said in its tooltip and the manual; Cancel all queued never stops a running task) and AW-10 (unique ids):
AW-1 (the Now tree's re-parenting, three regroup/reparent tests that fail on the old render), AW-2
(`NOT_KEPT_WHEN_OK` gains `convert`, `details`, `cached`), AW-3, AW-4, AW-5 (`ExplorerConverter.start`/
`_pass` and `LiveController._convert_stopped` report), AW-6, AW-7 (the manual), AW-8 (the probe limits
from `TreePanelWidget.probe_limits()`), AW-9 (`ActivityWindow.fit_screen`), AW-10 (also: the History tab
updated in place, log lines read for the details pane only), AW-11, AW-12, AW-13. The handoff's text
below follows them.

## Proposed doc changes (for the Coordinator)

### `.ai/architecture/app-runtime-and-ui.md`, a new paragraph under "UI"

> **The Activity window** (Q62.1–Q62.5; `agent/activity-window`, landed `<hash>`; manual: "See and manage
> what HeLab is doing"): Window › Activity (`window_activity`) and a click on the status bar's message
> (`status_activity`, its tooltip's last line "Click for Activity", `HelabMainWindow.ACTIVITY_HINT`;
> `ActivityWindow.ClickOpens`) open one non-modal `ActivityWindow` per main window, built hidden at start.
> Its model is Qt-free (`helab/utils/activity.py`, in `PURE`): `Task` rows in a `Snapshot`, built from memory
> only by `ActivitySources` (`helab/views/ActivityWindow.py`) from IOService's `active`, `pending` and
> `retired` (a retry held behind its stopping attempt is one row), FolderCache (`job_of`, `admin_action`,
> `finishing_of`, `raw_filling`, `quit_entries`' waiting and held saves), each tab's Live sessions
> (`LiveController.sessions`) with their checks, saves and auto-convert under them, GUI conversions and the
> converter's open questions, the analysis runners (`AnalysisQueue.jobs`, `RunInfo`), the Scripts panel's
> test imports and a waiting reload, and the cache move. Groups: Loads and scans, Saves, Live, Conversions,
> Cache upkeep, Analysis, Scripts (Other for anything new). States: running, queued (its place, or why
> held), paused (by the foreground, the mismatch hold or the user), stopping (until the exit flag), waiting
> for N files to settle, no progress for M:SS (`LoadClock.STALL_SECONDS`), failed. Its counts are
> `activity_counts`'. **Hidden, it does nothing** (no timer, no connection); shown, a 200 ms coalesced
> refresh on `activityChanged`, terminal `resultReady` kinds, `quitSavesChanged`, runners' `finished` and
> history appends, plus a 1 s tick; rows update in place. **Actions go through each owner's own path**
> (`ActivityActions`): Cancel (a tab's selected load through `cancel_loading`, the toolbar's Cancel, which
> also stops that tab's background loads, as its tooltip and the manual say (CoCo, AW-3); else
> `FolderCache.cancel`, auto-convert's toggle, `cancel_raw_fill`, `CacheMover.cancel`,
> `AnalysisRunner.cancel`; saves, cache upkeep and test imports have none), Retry (`resume_live`, the Convert row's `clicked`, `refresh_folder`, `FolderExplorer.retry`,
> a plot's `run`, `reload_scripts`; refused while `IOService.unexited(operation, path)`), Show in tab, Stop
> Live, Open log (this session's log file), Pause / Resume background I/O (`IOService.set_user_hold`) and
> Cancel all queued (never a running task: a tab's selected load is left to its tab's Cancel,
> `cancel(…, queued_only=True)`; saves stay). **The Now tree** fills rows in place; when any row's group or
> parent changes it detaches every item before placing it again, holding the taken items until the render
> ends, under `try/finally` (AW-1); a group's heading counts the rows shown under it. **The history**
> (`activity.HISTORY`, the last 200, newest first; added to on the GUI thread only; each entry's `key` is
> unique, `Finished.seq`): each owner reports its task's end once (`activity.record`): IOService at a
> request's first terminal event, before its owner hears (`_report_end`; a retried timeout or a requeue is
> no end), the runner from a GUI-thread slot, Live off, Live's auto-convert stopping without a helper's
> failure (`_convert_stopped`), a GUI conversion's end (including one whose pass couldn't be queued), a
> test import's end, the cache move's end. Every failure and cancellation is kept; successes are kept but
> Live's checks, Live's plot reruns, every conversion pass (the Live session or the GUI conversion is the
> entry), listings, details scans, cached reads, icons and other frequent small work (`kept_in_history`,
> `NOT_KEPT_WHEN_OK`; AW-2). A listener's error is logged, never raised into the reporter. The History tab
> adds new entries on top and drops the oldest at the bottom, leaving the rest. `activity.LogLines` keeps
> the session's last 500 warnings in memory for a failure's details (lines naming the folder itself, not a
> longer name; the main window adds it to the root logger at start and removes it on close). The window's
> size is `activity_window_size`, fitted to its screen when it first shows.

### `.ai/architecture/io-and-browsing.md`, in "The shared I/O queue"

> - **The user's hold** (the Activity window's Pause background I/O, Q62.3): `IOService.set_user_hold`,
>   the mismatch hold's twin: `PAUSABLE` requests in the background lane pause cooperatively and none
>   start (`user_held`), never the foreground or local lane, saves or Live checks (`mismatch_spared`);
>   `activity_counts` adds "paused by you" and the queue tooltip says so; session only, lifted by
>   `FolderCache.cancel_for_quit`. Every request's end is reported once to the Activity history
>   (`_report_end`, at each terminal emit through `_ended`), and `unexited(operation, path)` is the
>   Activity window's Retry guard ([app-runtime-and-ui](app-runtime-and-ui.md#ui)).

### `.ai/architecture/testing.md`

> Tests of the Activity window (`tests/test_activity*.py`) reset the module-global `activity.HISTORY` and
> `LOG_LINES_HANDLER` around each test and take the handler off the root logger (`fresh_activity`).
> `IOService` records into the global `HISTORY` in **every** test that ends a request (bounded at 200, and
> harmless with no listeners); a test that shows an `ActivityWindow` hides or closes it (pytest-qt's
> `addWidget` does), so its listener leaves `HISTORY.listeners`.

### `AGENTS.md` (one line, in the code map's `helab/views/` row)

> add "`ActivityWindow.py` (Window › Activity: every task, its history and actions; model
> `helab/utils/activity.py`)" to the `helab/views/` row's list.

### `roadmaps/activity-window.md` and `roadmaps/_readme.md`

Status to done (v0.0.9) at landing; "Reordering the queue" and `helab convert` beside the app stay in
"Not in scope (v1)".

## Provisional items

- **Q~1** Cancel for saves, cache upkeep and test imports: v1 lists them without Cancel. Proposed: keep it
  so; the quit window's Quit now stays the only stop for saves.
- **Q~2** The history leaves out successful Live checks, Live's plot reruns, every successful conversion
  pass (Live's auto-convert runs one with each check; the Live session or the GUI conversion is the entry),
  folder listings, details scans, cached reads, icons and other frequent small work. Proposed: yes; every
  failure and cancellation is kept.
- **Q~3** "paused by you" on the status bar while Pause background I/O is on (CoCo: yes). Proposed: keep.
- **Q~4** Retry of a failed load whose folder is no longer selected: disabled with "Select the folder in
  its tab to load it again (Show in tab)". Proposed: yes for v1.
- **A~1** A cancelled shared job's history entry loses its tabs (deviation 4): FolderCache could pass the
  subscribers to IOService before cancelling (e.g. `owners_of` reading a just-forgotten job), so Show in
  tab works from History for cancellations too.
- **A~2** Refresh on each tab's `liveChanged` / `loadStateChanged` too, if a second's delay on Live's own
  state shows (deviation 6).
- **Known issue (proposed)**: `tests/test_gui_responsiveness.py::test_rendering_never_reads_filesystem_or_disk_cache`
  RERAN twice in one local run after the review fixes (teardown, then its rerun's setup): `AssertionError: GUI
  rendering performed I/O` raised in a thread, pytest-qt's "Failed to process unraisable/thread exception".
  Probably a thread another test left behind (a helper's artifact cleanup, `shutil.rmtree`) started during the
  test, which `this_tests` counts as the test's own; a fix would be to count only threads the test's own
  service starts. Not touched here.
- **Known issue (proposed)**: `tests/test_load_queue.py::test_an_automatic_load_waits_for_the_selection_to_settle_only_while_loads_are_busy`
  RERAN once on Ubuntu CI (run `41794579242`, Tests 1/3): `assert (False) where False =
  FolderExplorer.settling` at `:674`, right after selecting a third folder while the second's load was
  busy; it passed on the rerun. Probably its settle wait (real timers, `SETTLE_MAX` 1.0) ending before the
  assertion on a slow runner. Not touched here.
- **M~1** Try the window on a real screen: open it from Window › Activity and from the status bar; follow
  a load, a Live session with auto-convert, a Folder details conversion and a plot run; Cancel a load,
  Retry a failed listing, Stop Live, Pause and Resume background I/O during a background scan; check the
  size is remembered and the History marks failures.
- **M~2** On the lab PC (or a share): Pause background I/O while a background load reads a slow share,
  and confirm it pauses and resumes, and that quitting while paused quits normally.
