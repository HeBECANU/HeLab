# Brief: audit of the GUI thread, so that HeLab's GUI never hangs (`agent/gui-threads-audit`)

Coordinator: CoCo, 2026-11-10. Tony in Chat: "run a new floor to audit GUI threads, to make sure GUI should never
hang". One Auditor (Reviewer role) finds and verifies; one Worker fixes; the Auditor then reads only the fix diff;
the floor lands on `dev/v0.0.9` with Tony's OK.

## Why now

- **The TDC PC froze overnight** (2026-11-09, Live idle) until force quit. `96df3ed` fixed the freeze's likely
  mechanism (the watchdog's stack dump into the console tee's full pipe), but **the first 5.68 s stall's cause is
  unknown** (`roadmaps/known-issues.md`, "## App", first entry).
- The rule exists (AGENTS.md: "Never let the GUI thread wait on cancellation, deadlines or a helper"; the GUI never
  touches source folders or the store; rendering reads memory only), but nothing checks it as a whole, and the
  code has grown (plots v2, Folder info, App updates, the Activity window, the console tee, the memory row).
- CI logs keep showing "GUI stalled for 2.30s"-type lines in tests (known-issues), which may be test load or real.

## Read first

- `AGENTS.md`: "I/O and threads", "Analysis and plots" (`compute` on the worker; `render`/`update` on the GUI
  thread), the UI rules.
- `.ai/architecture/app-runtime-and-ui.md` (Threading, logging, the watchdog, the console tee, the quit window),
  `io-and-browsing.md` (IOService, lanes, slots, the reaper, heartbeats), `plots-and-scripts.md` (the runner, the
  memory estimates), `live.md`, `cache-store.md` (only to confirm the GUI never opens the store), `testing.md`.
- Earlier work: `.ai/sessions/2026-10-06-gui-responsiveness/`, `.ai/sessions/2026-11-03-claude-preset-modal-hang/`,
  `.ai/sessions/2026-10-19-claude-smb-io-audit/`; known-issues entries naming stalls, hangs or heartbeats.
- Code: `helab/utils/gui_watchdog.py`, `helab/utils/console_tee.py`, `helab/utils/app_log.py`,
  `helab/utils/io_service.py`, `helab/utils/folder_cache.py`, `helab/analysis/runner.py` / `runner_core.py`,
  `helab/views/` (the main window, `FolderExplorer`, `explorer_live.py`, `explorer_convert.py`, dialogs, Settings
  tabs, `ActivityWindow.py`, `FolderInfoWindow.py`, the quit path and `quit_watch.py`), `helab/views/plots/`,
  `helab/updates/` (what runs in the GUI process), `helab/utils/dash_server.py`, `helab/main.py`.

## The question

**Can anything that runs on the GUI thread take more than a moment, or wait on something that may not come?**
Look for, on every path the GUI thread runs (slots, timers, event handlers, `render`/`update`, model `data()`,
startup and quit):

1. **Waits:** `join`, `wait`, `Event.wait`, `queue.get`/`put` on a bounded queue, `Lock.acquire`/`with lock` where
   the holder can be slow (another thread, a helper's reader, logging's lock, the GIL held by C code),
   `subprocess.run`/`communicate`/`wait`, `time.sleep`, `QThread.wait`, `concurrent.futures` results, `select`.
2. **I/O:** file reads/writes/stats (any path: source folders, the app folder, logs, settings `.ini`/`QSettings`
   sync, the console file, temp files), sockets/HTTP (the update check, Dash), `sqlite3`, `os.listdir`/`scandir`,
   `Path.exists`/`resolve`/`realpath` (on a mount these can block for minutes), `shutil`, `importlib` of user code.
3. **CPU:** work that scales with data on the GUI thread (colouring images, building large Plotly figures and their
   JSON, sorting/formatting many rows, tooltips over thousands of items, model resets), and its bound.
4. **Nested event loops:** `exec()` of dialogs/menus, `QEventLoop`, `processEvents`, `waitUntil`-like loops in
   app code; re-entrancy they allow (a slot running inside another), and deadlocks with helpers or the runner.
5. **Signals across threads:** `BlockingQueuedConnection`, direct connections from worker threads that run GUI
   code on the wrong thread, Python callbacks from C threads, `faulthandler`/`signal` handlers.
6. **Logging and output:** handlers that can block (stream handlers to a console or pipe, file handlers on a slow
   disk, `flush`), `print` to a blocked stdout, the console tee's paths, the watchdog itself.
7. **Startup and quit:** what runs before the event loop (60 s grace in the watchdog) and during quit (the quit
   window, `running.lock`, helper shutdown, `quit_watch`).
8. **Platform:** Windows-only paths (console handles, `msvcrt`, file locks, antivirus-slow opens), macOS (App Nap,
   QtWebEngine, Spotlight on mounts).

For each hit: is it reachable on the GUI thread, how long can it take in the worst real case (a hung SMB mount, a
blocked console, a busy disk, a huge folder or plot), and is it already bounded (a timeout, a helper, a size limit)?

## Process

1. **Auditor** (read-only on code; writes only `audit.md` in this folder, and scripts or tests under this folder):
   - a **static inventory**: a script (AST or grep, kept here) that lists blocking calls in `helab/` with the
     function that holds them, then trace which are reachable from the GUI thread (CodeGraph misses calls made
     through attributes: confirm with grep);
   - **dynamic checks** where cheap: run touched scenarios offscreen with the watchdog's stall threshold lowered
     (e.g. 0.2 s) and collect the stacks; a fake slow helper / blocked console / huge plot; `sys.setswitchinterval`
     or `faulthandler.dump_traceback_later` as needed. Never real data; never Tony's mounts; `~/HeLab-samples` read
     only;
   - write `audit.md`: numbered findings `GT-1`, `GT-2`… with file:line, the GUI path that reaches it, severity
     (High: can hang indefinitely; Medium: can stall over 2 s in a real case; Low: under 2 s or only in an unlikely
     case; Info), the failure scenario, how confirmed (a test, a run, a stack, or reading), and a proposed fix. Also
     a short **"checked and clean"** list, and a proposal for **a guard that keeps it so** (e.g. a test or lint that
     fails on a new blocking call in `helab/views/` without an allow-list entry, or a suite-wide stall check), with
     its cost. Commit it; report to CoCo. Don't fix.
2. **Worker** (recruited after the audit): fixes the findings CoCo passes on (High and Medium first), one commit
   each with a test that fails before the fix where practical, and the guard if CoCo approves it. Questions for
   Tony as `Q~1`…, later work `A~1`…, checks on a real screen or the lab `M~1`… in `handoff.md`, with proposed
   doc changes. Ask CoCo before changing behaviour users see or an existing test pins.
3. **Auditor** re-reads only the fix diff; findings closed or reopened in `audit.md`.
4. **Worker** merges the latest `dev/v0.0.9` (fetch from origin; Tony also pushes from another computer), runs the
   full suite (`pytest -n 8 --reruns 5 --reruns-delay 1 --basetemp=.ai/temp/pytest`) and the five type checks
   (`mypy helab/ --strict`, `mypy tests --strict`, `pyright helab tests`, `mypy helab/ --strict --platform win32`,
   `pyright --pythonplatform Windows helab tests`), output kept whole here, every RERUN reported; pushes the branch
   once and reads every Tests and Converter backends job's log for RERUN.

## Rules

- Owned: this session folder; then the files the findings name and their tests. Never edit Basic plots v1's pinned
  files (`tests/test_basic_plots_v2_v1_frozen.py`). Ask CoCo before changing a store write path, the helper
  protocol (`helab/io_ops/events.py`), the script contract, or behaviour an existing test pins.
- Don't edit `AGENTS.md`, `.ai/architecture/`, `roadmaps/` (known-issues too), `.ai/memory/` or the three
  `.ai/*_TODO.md` lists: propose changes in the handoff.
- Strict typing (with `--platform win32` and `--pythonplatform Windows`). Tests never touch real data; `source
  .ai/local/floor-env.sh` before tests or a run.
- Public text names no person except Tony and no lab machine, internal ID or `.ai/` path.
- Commit freely on this branch; push only at step 4. Never push `dev/v0.0.9`; never delete a branch. No version
  bump, release, tag, PR or merge into `dev/v0.0.9`. Commit messages end with
  "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>".
