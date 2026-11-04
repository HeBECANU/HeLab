# Design: the Activity window (Q62.1–Q62.5)

Beacon (Worker), 2026-11-04, on `agent/activity-window` from `63b9a15`. Step 1 of the brief: no code
until CoCo's go. The spec is the plan's "Decided" section; this replaces its "Design notes" where they
differ. Open points for CoCo are marked **(CoCo?)**; questions only Tony can answer are `Q~` items at
the end.

## 1. Shape in one paragraph

One Qt-free module, **`helab/utils/activity.py`** (listed in `PURE`), holds the plain data (`Task`,
`Snapshot`, `Finished`), the pure rules (state, group, history filter, counts) and the session history
(a 200-entry ring, module-global). One Qt module, **`helab/views/ActivityWindow.py`**, holds
`ActivitySources` (reads each owner's memory through read-only accessors and calls the pure builders),
the window, and the action dispatch (each action calls its owner's existing method). Owners report
their own finishes into the history with one call each. While the window is closed, nothing but those
history appends runs: no timer, no signal connection, no snapshot.

Why `helab/utils/` and not `helab/analysis/`: most of what it describes is I/O (`IOService`,
`FolderCache`); `analysis/` is the analysis core. It must not import `io_service.py` at run time
(that imports Qt): it reads requests through a `Protocol` (`RequestLike`, the `IORequest` fields it
needs), with `IORequest` imported only under `TYPE_CHECKING`.

## 2. The snapshot

### 2.1 Data (Qt-free, `activity.py`)

```python
Group = Literal["loads", "saves", "live", "convert", "upkeep", "analysis", "scripts", "other"]
State = Literal["running", "queued", "paused", "stopping", "settling", "stalled", "waiting", "failed"]
Action = Literal["cancel", "retry", "show", "stop_live", "log", "answer"]

@dataclass(frozen=True)
class Task:
    id: str                 # stable across refreshes (selection survives), e.g. "io:<owner>:<op>:<path>:<gen>"
    group: Group
    title: str              # "Load data", "Live check", "Save data cache", "Convert raw files to TXY", …
    folder: str             # full path ("" for none: presets, a script folder is a path too)
    tab: str                # "" if none; resolved by the glue from owners (tab text, or the plot's title)
    state: State
    state_text: str         # "running", "queued", "paused while the current tab browses",
                            # "stopping (0:04)", "waiting for 3 files to settle", "no progress for 0:12",
                            # "failed: <message>", "waiting for your answer"
    progress: Progress | None   # files done/total, bytes read/total, fraction (None: unknown)
    elapsed: float | None   # seconds (a load: its LoadClock, queued and paused time left out)
    left: float | None      # LoadClock.remaining(); None while stalled or unknown
    details: tuple[str, ...]    # the details pane's lines (2.4)
    actions: frozenset[Action]
    route: Route            # opaque, plain: what the glue needs to call the owner (5)
    parent: str = ""        # a Live session's checks, saves and conversions sit under it

@dataclass(frozen=True)
class Snapshot:
    tasks: tuple[Task, ...]     # in group order, then the owner's order (IOService: dispatch order)
    counts: Counts              # running, paused, queued, stopping: as IOService.activity_counts counts them
    user_paused: bool           # Pause background I/O is on
    taken_at: float             # monotonic
```

### 2.2 Builders and what each source exposes

Every accessor reads memory only, returns plain data or the owner's own objects, and never submits
I/O. New code in owners' files is limited to these accessors, the finish reports (3) and the pause
hold (5.3).

| Source | Builder (in `activity.py` unless noted) | What the owner exposes (new = added) |
|---|---|---|
| **IOService** (all helpers: loads, scans, listings, cached reads, saves, conversions, `raw_fill`, `cache_admin`, `cache_move`, results, icons…) | `io_tasks(active, pending, retired, now, describe)` | existing public `pending`, `active`, `retired`, `blocker`, `waiting_for`, `held_by_mismatch`, `label`, `owners_of`, `running_requests`; new `IORequest.last_event` (kind of the last event, set in `_tick`), `IORequest.queued_at` (monotonic, set in `IORequest`'s default), `IOService.user_hold` (5.3), `IOService.unexited(operation, path)` (the Retry guard, 5.2) |
| **FolderCache** (what each producer is for) | the glue's `describe(request)` | new `FolderCache.job_of(owner) -> SharedJob \| None` (`_producers`), `FolderCache.admin_action(owner) -> str` (`_admin`: "sweep", "trim", "mark_used"…), `FolderCache.raw_filling(owner) -> bool`; existing `quit_entries()` (saves not yet a helper: "waiting" deferred saves, "held" writes), `load_clock`, `SharedJob.progress/current_file/clock/subscribers/saves()/live` |
| **Live** (`LiveController`, per tab) | `live_tasks(sessions, now)` | new `LiveController.sessions() -> list[LiveSession]` (`_live_sessions` values, watched first); `LiveSession` fields are public already (`on`, `error`, `request`, `next_at`, `unsettled`, `unsaved`, `saving`, `convert`, `started_at`); `live_line(session)` for the text |
| **Conversions from the GUI** (`ExplorerConverter`, per tab) and **the converter's questions** | `conversion_tasks(conversions)`, `question_task(box, path)` | existing public `ExplorerConverter.conversions` (`FolderConversion`), `row(path)`; `ExplorerConverter.box` and `LiveController.box` (an open question; its window title and text) |
| **AnalysisRunner** | `analysis_tasks(jobs, now)` | new `AnalysisQueue.jobs() -> tuple[RunInfo, ...]` (job id, owner, analysis short name, action, live, queued/running/stopping, queued_at, started_at; under its lock) and `AnalysisRunner.jobs()` passing it on; the queue records `started_at` in `_run` |
| **Script probes and reloads** (`FolderProbes`, `TreePanelWidget`) | `script_tasks(probes, reload)` | new `FolderProbes.activity() -> list[tuple[str, str, float]]` (folder, "queued"/"importing"/"stopping", started); new `TreePanelWidget.reload_waiting() -> tuple[set[str], int]` (folders pending, runs it waits for) |
| **Cache-folder move** (`CacheMover`) | `move_task(mover)` in the glue | existing public `running`, `moving`, `switched_folder`, `method`, `source`, `target`, `busy`; its helper steps are IOService rows under it (`parent`) |
| **Cache upkeep** | from `io_tasks`: `raw_fill`, `cache_admin` (sweep, trim, Make room's `adopt_result`, last-used marks, clears and purges), `cache_move`, `invalidate`, `volumes_verify`, `roots_verify` | `admin_action` names the job |

**Grouping** (`group_of(operation, payload, finishing, admin_action)`, pure): Loads and scans (`load`,
`cached`, `list`, `resolve`, `details`, `scan`, `saved_list`, `icons`); Saves (a load with `save`, a
finished load writing its cache, `result_save`, `scan_history`, `subtree_save`, marker writes, flags,
constants, presets, last uses at quit); Live (a session, with its checks, autosaves and auto-convert
passes as children: owners `<tab>:live`, `<tab>:live-save`); Conversions (Folder details' and Convert
this folder…'s passes under their `FolderConversion`; open converter questions); Cache upkeep
(`raw_fill`, `cache_admin`, `cache_move`, `invalidate`, volume and root verification); Analysis
(runner jobs; `result_find`); Scripts (probes, a reload waiting). Anything else: Other (so nothing
running is ever missing from the list).

**One row per helper task, merged across attempts.** A retry held until the old helper exits has the
same `(owner, generation, path, operation)` key: one row, state "stopping", its detail "attempt 2 of 3
starts when it exits" (`IOService._stopping_row`'s wording). A shared job with several tabs is one
row; Tab names each tab.

### 2.3 States (pure: `state_of`)

In this order:
1. **stopping**: the request is in `retired` (cancelled, timed out, requeued) — until its exit flag
   (`_forget`). Text "stopping (M:SS)", plus why ("cancelled", "timed out after 60 s without progress").
   An analysis job whose cancel is set while it computes is stopping too, until `finished`.
2. **paused**: `request.paused` (the helper confirmed). Why: "paused by you" (user hold), "paused:
   cached data doesn't match several folders" (mismatch hold), else "paused while the current tab
   browses or loads".
3. **queued**: in `pending`. "queued (3rd)"; a held one "waits for the previous attempt to stop"; one
   the mismatch hold or a cache move holds, says so.
4. **stalled**: running and `now - last_activity >= LoadClock.STALL_SECONDS` (5 s): "no progress for
   M:SS" (a load's own `clock.stalled_for` when it has one, so it matches Folder details).
5. **settling** ("waiting for N files to settle"): a Live session with `unsettled`, a GUI conversion
   between passes with `waiting`.
6. **waiting**: Live between checks ("next check in 2 s"), a converter question ("waiting for your
   answer"), a reload waiting for runs.
7. **failed**: Live stopped by an error (Retry), auto-convert stopped, a GUI conversion stopped. Failed
   helper requests leave the list (they are in the history, 3).
8. otherwise **running**.

**Counts** (`Counts`): running = `running_requests()`, paused = paused and not completed, queued =
pending minus held, stopping = `retired`: exactly `activity_counts`' numbers, so the status bar and the
list agree (a test compares them).

### 2.4 Details pane (from the same `Task.details`)

What it is (title, operation, owner kind), folder (full path), tab(s), lane (`current tab`,
`background`, `local disk cache`), helper process (pid while running; "not started", "exited"),
attempt, started (wall clock, from `started`/`queued_at`), last heartbeat ("2 s ago"), last event
(`last_event`), the file it's on (`current_file` / the job's), progress and estimate, for a stopping
one why and how long, for a load the `load_note` text. For a failure (history or a failed Live /
conversion): its error message and the session's log lines about it (4.2).

## 3. History (Q62.4)

- `activity.HISTORY = History(200)`: a `deque(maxlen=200)` of `Finished` (id, group, title, folder,
  owners, started, ended (wall), outcome `ok` / `failed` / `cancelled`, message, attempts, a retry
  route). `entries()` newest first. Session only (AGENTS.md: "session-only lists drop their oldest
  entries"). Thread-safe append (the analysis worker reports from its thread): a lock.
- **Who reports a finish** (one call each, `activity.record(...)`, memory only):
  - **IOService**, for every helper: at its first terminal event (`done`, `error`, `cancelled`, the
    final `timed out`) in one private `_report_end(request, outcome, message)` called where those are
    emitted (`_tick`, `cancel`, `cancel_held`, `set_offline`, `hold_cache`, `_start`'s offline refusal),
    once per request (`IORequest.reported`). A timeout that is retried isn't an end (the retry continues
    the task); a requeue isn't either. Owners come from `owners_of(request)` (FolderCache's
    subscribers, while the job is still filed: the hook runs before `resultReady.emit`).
  - **AnalysisRunner** in `_finished` (beside its milestone): completed / failed / cancelled.
  - **LiveController**: a session's end (Live off, an error stop, the tab closed) as one entry
    "Live: <folder>", with new shots and checks.
  - **ExplorerConverter**: a GUI conversion finished or stopped (one entry; its passes are I/O entries
    too, kept only when they fail — below).
  - **FolderProbes** in `_ended`: a failed test import (a passed one: kept, outcome ok).
  - **CacheMover** in `_finish`: moved / cancelled / failed.
- **Kept or not** (`kept_in_history`, pure): every failure and cancellation is kept. Successes are kept
  except the frequent ones that would push everything else out of 200: Live checks (their session
  is the entry), folder listings (`list`, `resolve`, `saved_list`), icons, `subtree_save`,
  `volumes_verify`, a GUI conversion's single passes. **(CoCo?)** whether that filter is right.
- Failures are marked (✕ and amber text in the State column; "failed" in the accessible text).
- A Retry from the history goes through the owner's path (5.2).

### 3.1 Log lines (memory)

`activity.LogLines`: a `logging.Handler` keeping the session's last 500 WARNING-and-up records (time,
logger, message), added to the root logger by the main window at start and removed when it closes.
The details pane shows the lines naming the task's folder within its run time; "Open log" opens this
session's log file (`<app folder>/logs/helab-<pid>.log`, `QDesktopServices.openUrl`), never read by
HeLab.

## 4. Refresh

- **Window hidden: nothing runs.** No timer, no connections, no snapshot (the history and the log
  handler only append). `showEvent` connects and builds once; `hideEvent` disconnects and stops the
  timers.
- **Shown:** a refresh is requested by `IOService.activityChanged`, `IOService.resultReady` (kinds
  `started`, `paused`, `resumed`, `done`, `error`, `cancelled` only), `FolderCache.quitSavesChanged`,
  `AnalysisRunner.finished`, each tab's `liveChanged` and `loadStateChanged`, and a history append (a
  plain callback list in `History`, called on the GUI thread; the worker's append is posted by
  `AnalysisRunner.finished` already). Requests coalesce into one single-shot 200 ms timer (at most 5
  refreshes a second, whatever the event rate). A 1 s timer refreshes elapsed times, progress and
  "no progress" (progress events aren't signalled separately).
- **Bounded:** a snapshot is O(tasks): IOService holds at most `MAX_PENDING` (128) requests plus 2
  retired per lane; tabs, plots and probes are few. Rendering updates the tree in place by task id
  (rows added, changed or removed; no rebuild), so selection and scroll stay.

## 5. Actions (Q62.3)

Each button is enabled only for a selected task whose `actions` include it, with the reason in its
tooltip otherwise. The list shows the owner's own state afterwards (no optimistic state of its own):
a cancelled helper shows "stopping" until its exit flag, then leaves.

### 5.1 Cancel (through each owner's path)

| Task | Path | Meanwhile |
|---|---|---|
| The tab's selected load or cached read | `FolderExplorer.cancel_loading()` (the toolbar's Cancel) | "stopping" until exit; the tab says "Cancelled — Retry" |
| A tab's background load | `FolderCache.cancel(bg_owner, "load", path)` | as above |
| A listing, scan or details | `FolderCache.cancel(<tab owner>, op, path)` (as `cancel_basic_scan` and `cancel_loading`'s listing retry do) | "stopping" |
| A shared job of several tabs | each tab's own cancel; the job stops when no subscriber is left (FolderCache's rule) | it stays "running" while another tab still wants it, detail says which |
| A plot's own TXY load (`plot-txy:<id>:…`) | `FolderCache.cancel(owner, "load", path)` | "stopping" |
| A GUI conversion | `FolderCache.cancel(converter.owner, "convert", path)` (as `ExplorerConverter.close`) | "stopping", then the Convert row's "Conversion stopped: cancelled" (click to try again) |
| Auto-convert | `LiveController.set_auto_convert(False)` (its own toggle: cancelling one pass only starts the next) | the pass stops; Live goes on |
| `raw_fill` | new `FolderCache.cancel_raw_fill(path)` → `service.cancel(RAW_FILL_OWNER + path)` (`_on_raw_fill_event` already ends it on `cancelled`; the next save asks again) | "stopping" |
| The cache-folder move | `CacheMover.cancel()` (until verified; a rename can't) | its own progress dialog and the row agree |
| An analysis job | `AnalysisRunner.cancel(job_id)` | "stopping" until `finished` |

**Not cancellable in v1** (no Cancel; the tooltip says why): Live checks (Stop Live instead); saves of
data and choices (Live's autosaves and stop-saves, a load's cache write, flags, constants, presets,
results, last-used marks, scan history, subfolder status) — cancelling loses what the user asked to
keep, and the quit window's Quit now is the existing stop; `cache_admin` (clears and purges the user
confirmed, Make room, the sweep, trims); icons, volume and root checks; script probes (their own 10 s /
20 s limits end them). **Q~1** asks Tony whether any of these should be cancellable.

### 5.2 Retry (a failed task)

| Task | Path |
|---|---|
| Live stopped by an error, auto-convert stopped | `FolderExplorer.resume_live()` (the Live line's Retry) |
| A failed load or listing of the tab's selected folder | the tab's Retry (`FolderExplorer._retry`, made reachable as `retry()`: a one-line public alias, **(CoCo?)** FolderExplorer.py isn't in my allowed list) |
| A failed listing of another folder | `FolderExplorer.refresh_folder(path)` (right-click Retry) |
| A failed load of a folder no longer selected | disabled: "Select the folder in its tab to load it again" (Show in tab does that) |
| A stopped GUI conversion | `ExplorerConverter.clicked(path)` (the Convert row's click: restarts, or asks again after a refused beside write) |
| A failed plot run | `AnalysisInstance.run()` (the plot's Run) |
| A failed script test import | `TreePanelWidget.reload_scripts([folder])` |
| Cache move, `raw_fill`, saves, upkeep | no Retry (the move: start it again in Settings; `raw_fill`: the next save asks; saves: their owners retry or say so) |

**Refused while the attempt it replaces holds its slot:** Retry is disabled, tooltip "The previous
attempt is still stopping", while `IOService.unexited(operation, path)` is true (any request in
`active` or `retired` of that operation and folder whose exit flag isn't set), or, for a plot, while
its job is in the runner. The owners' own paths start new owners/generations, so IOService's own
`blocker` wouldn't hold them: this check is what keeps a retry from running beside its predecessor.

### 5.3 The others

- **Show in tab:** a tab's task: `tab_widget.setCurrentIndex` and `FolderExplorer.reveal(path)` (as
  `reveal_load`); a plot's: `settings.show_plot(dock, raise_dock=True)` (Debug › Show Plot Tab's
  path); a converter question: raise and activate its box (`answer`).
- **Stop Live:** `FolderExplorer.stop_live()` (the toolbar's Live off; its new shots saved as always).
- **Open log:** this session's log file (3.1).
- **Pause / Resume background I/O** (one toggle): new `IOService.set_user_hold(on)`, the mismatch
  hold's twin: background-lane requests in `PAUSABLE` pause cooperatively (`_apply_pauses`) and none
  start (`_dispatch`), except what `mismatch_spared` spares (saves, Live checks); the foreground lane
  (the current tab) and the local lane go on. Session only; quitting lifts it
  (`FolderCache.cancel_for_quit`); a paused helper keeps its slot and its no-progress timer is frozen,
  as today. The queue tooltip says "Paused by you (Activity)". **(CoCo?)** the status bar's counts add
  "paused by you" while it is on (a new state, so no pinned text changes), else a forgotten pause looks
  like a stuck queue.
- **Cancel all queued:** every queued task with a Cancel route, each through its own path (5.1);
  saves and non-cancellable ones stay queued. No question (only reads are cancelled).

## 6. Window, columns, details pane, status bar click (Q62.1)

- `ActivityWindow(QWidget)`, one per main window, a top-level `Qt.WindowType.Window` child of the main
  window (non-modal, stays open beside it, closes with it). Title "Activity".
- **Opened by** Window › Activity (a new **Window** menu before Help; action ID `window_activity`) and by
  a click on the status bar's left message (`status_activity`, which ends with the app-wide counts):
  an event filter on that label (mouse release). Text unchanged; **(CoCo?)** add "Click for Activity"
  to its tooltip's end — or split the counts into their own flat button (`status_io_counts`), which
  would change the label's text, so I'd rather not.
- **Layout** (no vertical padding around blocks; gaps from `gaps.py`):
  - one button row: Cancel · Retry · Show in tab · Stop Live · Open log │ Pause background I/O
    (checkable) · Cancel all queued; then a one-line summary label (`ElidedLabel`: the counts,
    "paused by you"), detail in its tooltip;
  - a `QTabWidget`: **Now** (a `QTreeWidget`: group rows "Loads and scans (3)" with tasks under them,
    Live sessions with their children) and **History** (a `QTreeWidget`, newest first: Ended, Task, Tab,
    Folder, Outcome, Took);
  - a `QSplitter` with the details pane below (`QPlainTextEdit`, read only), for the selected row of
    either tab.
- **Columns (Now):** Task · Tab · Folder (name; full path in tooltip) · State · Progress ("123 of 579
  files · 21 %", a bar is not needed in v1) · Elapsed · Left. One-line rows, the rest in tooltips and
  the details pane. `CELL_PADDING_STYLE`.
- **IDs** (`identify`): `activity_window`, `activity_now`, `activity_history`, `activity_tabs`,
  `activity_details`, `activity_cancel`, `activity_retry`, `activity_show`, `activity_stop_live`,
  `activity_open_log`, `activity_pause`, `activity_cancel_queued`, `activity_summary`. Bound slots only
  (no lambda capturing a Qt-made sender; nothing on `destroyed`).
- **Size remembered:** new settings row `activity_window_size` ("W,H", logical pixels; default
  "760,420"; clamped to the screen), read when it first opens, saved when it hides. Position: Qt's
  default placement (Q62.1 asks for size only).

## 7. Tests

New, from fakes, no helpers (an `IOService` whose `_run` is patched to a no-op, so requests become
active without a process, and whose fields the test sets; a `FolderCache` on it; fake explorers where a
real tab isn't needed):

- `tests/test_activity.py` (Qt-free parts): `state_of` for each state and its text; `group_of` for
  every `IOService.LABELS` operation (none falls to Other by accident); `kept_in_history`; `History`'s
  200 cap and newest-first order, failures marked; `Counts` equal to `activity_counts` for a mix of
  running, paused, queued, held and stopping requests; `LogLines` matching by folder; the module in
  `PURE`.
- `tests/test_activity_sources.py`: each source's tasks (IOService loads with a job's progress and
  clock, a retry held behind a retired attempt as one "stopping" row, a mismatch-held and a user-held
  pause, cache_admin named by its action, `quit_entries`' deferred saves; a Live session with its check,
  save and auto-convert children; a GUI conversion between passes ("settling") and stopped ("failed");
  an open converter question; runner jobs queued, running, stopping; probes; a cache move); and the
  history reports from IOService (done, error, cancelled, final timeout; not a retried timeout, not a
  requeue), AnalysisRunner, Live, conversions, probes and the mover.
- `tests/test_activity_window.py` (Qt, `qtbot`): Window › Activity and a click on the status message
  open it; groups and columns render; the details pane; each action calls its owner's path (spies on
  `cancel_loading`, `FolderCache.cancel`, `AnalysisRunner.cancel`, `stop_live`, `resume_live`,
  `CacheMover.cancel`, `set_user_hold`); **stopping until the exit flag** (cancel, the row says
  stopping, `exited.set()` and a tick, the row goes); **Retry refused while the old attempt is
  unexited**, allowed after; Cancel all queued leaves saves; **rendering reads memory only** (a refresh
  with `IOService.submit`/`_start` failing the test, and `os.scandir`/`os.stat`/`open` of a source
  folder denied, as `test_offline_browsing`'s `no_source_io` / `deny_source`); **closed: nothing runs**
  (no active timer, signals disconnected); bounded refreshes (100 `activityChanged` in a burst → one
  refresh); the size saved and restored through `app_settings()`.
- **Existing tests touched:** `tests/test_headless_imports.py` (`PURE` gains `helab.utils.activity`);
  `tests/test_accessible_names.py` (the window added to `DIALOGS`, shown with a task in each group so
  every control is walked); `tests/test_settings_defaults.py` should pass unchanged with the new row
  (it checks the reads a real window makes); `tests/test_io_service.py` and the status-bar / Folder
  details / quit-window tests must pass unchanged (no pinned text changes, unless CoCo agrees to the
  "paused by you" part, which only appears with the hold on).

## 8. Edits outside my new files (all within the brief's allowed list, except one)

- `io_service.py`: `IORequest.last_event`, `queued_at`, `reported`; `_report_end` at the terminal
  emits; `user_hold` + `set_user_hold` in `_dispatch` / `_apply_pauses` / `queue_tooltip`; `unexited`.
- `folder_cache.py`: `job_of`, `admin_action`, `raw_filling`, `cancel_raw_fill`; lift the user hold in
  `cancel_for_quit`.
- `runner_core.py` / `runner.py`: `RunInfo`, `jobs()`, `started_at`; the history report in `_finished`.
- `explorer_live.py`: `sessions()`; the session-end report. `explorer_convert.py`: the conversion-end
  report. `script_tree.py`: `FolderProbes.activity()`, `reload_waiting()`, the probe-end report.
  `CacheMover.py`: the move-end report.
- `HelabMainWindow.py`: the Window menu, the status-bar event filter, the window instance, the
  `LogLines` handler.
- `settings_defaults.py`: the `activity_window_size` row.
- **Not in the list:** `FolderExplorer.py`, only if CoCo wants Retry of the selected folder through a
  public `retry()` alias of `_retry` (else I call `_retry` from the window, as the tab's button does).

## 9. Provisional questions for Tony (to go in the handoff)

- **Q~1** Cancel for saves, cache upkeep and probes: v1 lists them without Cancel (5.1). Proposed: keep
  it so; Quit now stays the only stop for saves.
- **Q~2** The history leaves out successful Live checks, listings, icons and other frequent small jobs
  (3). Proposed: yes; failures and cancellations of anything are always kept.
- **Q~3** "Paused by you" on the status bar while Pause background I/O is on (5.3). Proposed: yes.
- **Q~4** Retry of a failed load whose folder is no longer selected: disabled with "Select the folder
  in its tab" (5.2). Proposed: yes for v1.
