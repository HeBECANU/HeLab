# Activity window

Horizon: v0.0.9 (Tony, 2026-11-04, Q62.5). Added: 2026-11-04, from Tony in Chat (block 62: Q62.1–Q62.5,
decided). **Status:** planned; to be built as one floor on this Mac (the dev computer) from `dev/v0.0.9`.
Priority and completion: [overview](_readme.md). It covers the Near term item "Show the analysis worker
beside I/O" (Tony, 2026-10-19). Related: [io-and-browsing](../.ai/architecture/io-and-browsing.md),
[live](../.ai/architecture/live.md), [plots-and-scripts](../.ai/architecture/plots-and-scripts.md).

## Purpose

"now we have so much background stuff going on, in addition to the indicator line at bottom of the app, shall
we have a dedicated window showing all running tasks, show their details and status and manage them?" Today
only the status bar's counts (`IOService.activity_counts`) and Folder details' All I/O tooltip
(`IOService.request_note`) say what runs.

## Decided (Tony, 2026-11-04)

- **Q62.1:** it is called **Activity**, opened from Window › Activity and by clicking the status bar's counts.
  One window, not modal, that stays open beside the main window.
- **Q62.2:** v1 shows, grouped by kind:
  - loads and scans;
  - saves;
  - Live: each tab's session, its checks, autosaves and auto-convert;
  - **conversions launched from HeLab's GUI**: Folder details' Convert, auto-convert, the converter's share
    questions while they wait (Tony: "we should show conversion launched from within helab app gui");
  - cache upkeep: `raw_fill`, the sweep, budget trims, a cache-folder move;
  - analysis jobs (each plot's `compute`, `AnalysisRunner`);
  - scripts: folder probes and reloads.

  `helab convert` processes running beside the app come later: they need a channel to the app.
- **Q62.3:** actions: Cancel, Retry (a failed task), Show in tab, Stop Live, Open log; for all, Pause / Resume
  background I/O and Cancel all queued. Reordering the queue later.
- **Q62.4:** this session's history: finished and failed tasks, newest first, failures marked, the last 200
  (the oldest dropped: a session-only list, as AGENTS.md allows).
- **Q62.5:** in v0.0.9, a floor on this Mac.

## Design notes (for the floor; propose, Ground decides)

- **Columns:** task, tab / folder, state (running, queued, paused, stopping, waiting for files to settle, "no
  progress for M:SS", failed), progress (files, bytes, %), elapsed, time left (`LoadClock`'s estimate).
- **Details pane:** what the task is, its lane and helper process, when it started, its last heartbeat and
  event, the file it's on, and for a failure its error and log lines.
- **One source of truth:** a Qt-free snapshot of tasks (`helab/analysis/` or `helab/utils/`, plain data)
  built from IOService (active and pending requests, lanes, pause state, held slots), `AnalysisRunner`,
  the Live controllers and `ExplorerConverter`, refreshed on their signals plus a 1 s timer for elapsed
  times. The window renders that snapshot only.
- **Invariants it keeps (AGENTS.md):** rendering reads memory only, never disk, and submits no I/O; the GUI
  never waits on a cancel, a deadline or a helper; a cancelled helper holds its slot until its exit is
  confirmed (the list shows "stopping" until then); a retry never runs beside the attempt it replaces.
- **Cancel** goes through each owner's own path (`IOService.cancel(owner, operation)`, `AnalysisRunner.cancel`,
  Live's stop), never a new one, so the status bar, Folder details and the quit window agree with the list.
- **UI:** every control gets an accessible name and ID (`identify`); one-line rows with detail in tooltips and
  the details pane; the window remembers its size.
- **Tests:** the snapshot from each source (fakes, no helpers), cancel and retry through their owners, the 200
  cap, stopping until the exit flag, no disk reads while rendering (`no_source_io`), and the accessible-names walk.

## Not in scope (v1)

- `helab convert` processes beside the app (later, Q62.2); remote or CLI workers.
- Reordering the queue (later, Q62.3).
