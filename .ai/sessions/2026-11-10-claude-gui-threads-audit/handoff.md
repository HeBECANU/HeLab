# Handoff: fixes for the GUI-thread audit (steps 2 of the brief)

Worker (Bolt), 2026-11-10, branch `agent/gui-threads-audit`, from `74d29f9` (the audit). Not pushed (step 4 merges
`dev/v0.0.9` first). The findings are Sentinel's, in `audit.md` beside this file.

## Round 2 (after `9a7d16c`): Tony's answers and the re-review's findings

Tony answered Q~1 – Q~5 in Chat (via CoCo, 2026-11-10: "Q~1 yes add that as an option too in addition to custom
bin size; Q~2 ok; Q~3 ok; Q~4 ok; Q~5 ok"); Sentinel's re-review of `74d29f9..9a7d16c` (`audit.md`, "Re-review of the
fixes (step 3)") found GT-24 – GT-30. New commits after `9a7d16c` (nothing before it rewritten), for Sentinel to
re-read as `9a7d16c..<head>`:

| Item | Commit | What changed (what users see in bold) |
|---|---|---|
| Q~5 (GT-1 a) | `ce78608` | **A conversion's end shows "Load anyway…" for a large folder instead of asking**; Live and presets at launch still ask; the user's own click asks. `queue_load`/`load_to_ram_cache(ask_large=False)`, `_quiet_large`, also covering the helper's too-large stop. |
| Q~4 (GT-9) | `5d58875` | **Load Scripts…, Settings' temp Browse… and the cache's Change… use Qt's own folder dialog, opening in the home folder** (`helab/views/folder_dialog.py`); the converter's profile import/export stay native. Save to folder… (.helab-root) and Debug's save are unchanged (not among Q~4's; a candidate if Tony wants it). |
| Q~3 (GT-8) | `121577c` | **Quit on both startup boxes** ("Quit ends this HeLab; start it again once the move has finished." / "Quit ends HeLab now; the move is finished at the next start."); the recovery's helper is cancelled and its record stays. A~8 (the recovery's no-progress timeout) is **not done**: the recovery's deletes report no progress, and a heartbeat thread would beat through a hung delete; it needs progress callbacks through `cache_move.recover`/`cleanup`/`_remove_tree`. Kept as A~8. |
| Q~2 (GT-6) | `2eadccc` | **At start, a script folder whose test import took over 2 s waits for Reload: "takes N s to import"** in the start note (`SLOW_START_SECONDS`); Reload imports it. |
| Q~1 (GT-4) | `684b027` | **Image › Draw at: screen resolution (default) \| every bin.** At screen resolution an image over 2,048 bins a side is drawn from block means made on the worker (Plotly ≤ 1,000); PyQtGraph `autoDownsample`, Matplotlib `imshow`; ≤ 500,000 dots a plane in PyQtGraph and Matplotlib; the plane's title says how it is drawn; the estimate follows the setting. Every bin draws exactly as before. 8,000²: the means 0.33 s on the worker, colouring 0.003 s on the GUI thread instead of 0.088 s. |
| GT-24 (Medium) | `012b52a` | Settings › Cache's "Lower the disk cache budget?" (the two budget-job ends that ask) waits for the delivery to return. |
| GT-25 (Low) | `0cf3c32` | `FolderCache._on_event` is a delivery too (`_event` its body), so guard 2 sees boxes from tests that emit `resultReady` themselves; `test_cache_tab.finish` and one `test_root_gui` test let the event loop turn. |
| GT-26 (Low) | `385dd97` | `_forget_digests` iterates `list(_READ_DIGESTS)`. |
| GT-27 (Low) | `b827da4` | The probe says `done`, then `{"kind": "reads"}`; `ci-build.yml`'s packaged-app probe check expects the three lines (a CI file outside this floor's areas, changed because its exact assertion would fail). |
| GT-28 (Low) | `c1399fb` | `file_manager.show("")` opens nothing. |
| GT-29 (Info) | none | Left: the lost-bytes count can be off by a racing pump and its note may sit before the backlog; the note already says "around here". An exact count needs a lock on the pump's path, for a cosmetic gain. |
| GT-30 (Info) | none (doc) | In the doc proposals below. |

Round 2's checks at `c1399fb`, output kept whole here: `fixes2-suite.txt` (`pytest -n 8 --reruns 5 --reruns-delay 1`:
**9907 passed, 674 skipped, no RERUN, no failure**) and `fixes2-typecheck.txt` (the five type checks, all clean).

Existing tests changed in round 2 (all for the approved behaviour or the new seam): `test_basic_plots_v2_hist2d`
(the parameter order with `draw_at`; the estimate test at every bin; the legend test reads Matplotlib's raster),
`test_script_probe` (`done` then `reads`; the CI step's three lines), `test_script_reads`, `test_live_scripts`,
`test_cache_tab.finish`, `test_root_gui`'s failed-save test.

## What was fixed (round 1)

| Finding | Status | Commit | What changed |
|---|---|---|---|
| GT-1 (High) | fixed, all five paths | `41c4b39` | `helab/utils/gui_delivery.py`: `delivering()` marks `IOService._tick` ("io") and a plot's run end (`AnalysisInstance._finished`, "analysis"); `outside(fn)` runs `fn` now, or from the event loop once the delivery returns. (a) the large-folder question asked from a result, (b) flag/constants "not saved", (c) the I/O trace's answers, (d) the cache move's question and reports, (e) `.helab-root` Save to folder… warnings all go through it. Same boxes, same text. |
| GT-2 (High) | fixed | `531d35e` | The quit watch logs from a thread of its own, waited for 1 s (`NOTE_SECONDS`), then exits whatever. `crash_file.exit_after()` arms `faulthandler.dump_traceback_later(exit=True)` onto the crash file, a C thread that outlives teardown; `main` arms it at GRACE + 3 s. |
| GT-3 (Medium) | fixed | `e5aaa9a` | The console tee writes its file from a writer thread (bounded queue, `FILE_CHUNKS` = 1024; losses noted in the file); the log file's handler goes first; `app_log.log_within()` for the watchdog's lines (guard 4, first half). |
| GT-4 (Medium) | waits for Q~1 | none | Nothing invisible worth doing was found: building dots' brushes with NumPy instead of a list saves 0.03 s against 1.6 s inside pyqtgraph's own `setData` for 1M dots. `autoDownsample` averages bins and `imshow` resamples instead of drawing quads: both change the picture once bins exceed screen pixels (and `imshow` changes vector exports), so both belong to Q~1. Colour indices on the worker would add an array to every saved result and still be recomputed on the GUI thread when a display setting changes. |
| GT-5 (Medium) | fixed | `63d1d5f` | `_cache_removed` re-derives each folder once, deepest first (`_rederive`), and says `activityChanged` once (`one_activity()`). |
| GT-6 (Medium) | (B) fixed; (A) proposed (A~1) | `c2b1d5b` | Option (B), agreed with CoCo: the probe's `done` line carries `FolderReads` (names; size, mtime_ns, SHA-256 per file; no bytes; none past 2,000 files); the import right after uses them while fresh (same folder, ≤ 10 s) for listing, helper checks and hashes, and stamps; missing, stale, future or another folder's: read as before. With fresh reads a script's hash is that of the bytes its import read. |
| GT-7 (Medium, Windows) | (a) fixed; (b) deferred (A~2) | `8db0b2a` | (a) Windows classifies only the cache folder's own drive (`GetDriveTypeW`), never `disk_partitions(all=True)`. OK'd by CoCo. |
| GT-8 (Medium, rare) | proposed (Q~3) | none | Both fixes change what users see (a Quit button) or risk ending a slow legitimate recovery (a finite timeout on a helper that may not heartbeat while it copies). |
| GT-9 (Medium) | `openUrl` fixed; file dialogs proposed (Q~4) | `542376d` | `helab/utils/file_manager.show()` opens local folders and files with `open` / `explorer` / `xdg-open` detached (as Data roots' Show already did); `openUrl` stays for web addresses. |
| GT-10 (Low) | fixed, and the known flake | `762d56c` | `DockTabCloser.fit` maps the area's docks once. `test_accessible_names`' walk runs a pending fit first. Together they close known-issues' "`test_every_script_and_each_library` … QTabBar … no ID" entry (Windows CI 41086378298, 41465454700, 42765698387): its cause was the walk running before the debounced fit, which was late behind a stall in that same fit. |
| GT-11, GT-12, GT-13, GT-15 (Low) | proposed (A~3 – A~6) | none | Not small or not safe enough for this floor (below). |
| GT-14 (Low) | fixed | `bbc2eea` | SIGINT/SIGTERM close from the event loop; Settings and Restore previous version start nothing after their `exec()` if the window is closing. |
| GT-17 (Info) / guard 4 | fixed | `bf490d1`, `13cc77c` | `instance.timed_hook`: render, update, draw and every `_hook` (describe_*, estimated_bytes, …) timed; over 0.5 s a warning names the plot, the script's class and the hook. |
| Guard 2 | done | `41c4b39` | `tests/conftest.py` `no_modal_in_delivery`: `exec()` and the static helpers of QDialog, QMessageBox, QMenu, QInputDialog, QFileDialog, QColorDialog and QFontDialog raise while a delivery runs, and the test fails at teardown even if HeLab's code caught it. A test that patches one of those names itself replaces the check for that name. |
| Guard 1 | done | `e8121a1` | `tests/test_gui_thread_calls.py` + `tests/data/gui_thread_allowed.txt` (15 entries, each with a reason; stale entries fail too). |
| Guard 3 | not done (A~7) | | As agreed. |

### Seen by users

- **GT-7 (a), Windows only:** a cache folder on a mapped network drive is refused as "on a network drive", where it
  said "on a network drive (ntfs)" (the file system's name is no longer asked). CoCo OK'd it; Tony to be told.
- **GT-1 (a):** a large folder whose load is asked for from a helper's result (a conversion's end, Live or a preset
  at launch) shows "Load anyway…" for one event-loop turn before its question opens. The question, its text and its
  answers are unchanged.
- **GT-6 (B):** none expected. A folder's import is the same; its stamps may be up to 10 s older (taken in the
  probe), so a file saved in that gap triggers one more auto-reload.
- **GT-9:** none expected: the same file manager opens, through `open` / `explorer` / `xdg-open`. `explorer <file>`
  opens a file in its default app as ShellExecute did.

### Existing tests changed (all mechanical, behaviour kept)

- `test_cache_switch.py::test_synced_and_network_cache_folders_are_refused`: its psutil fake-mount part is skipped
  on Windows, with the reason in the test; `test_windows_asks_only_the_cache_folders_own_drive` covers that path on
  every OS. OK'd by CoCo.
- `test_script_probe.py`: the missing folder's `done` line now has `"reads": None`; the real folder's reads are
  checked.
- `test_live_scripts.py`: two `add_folder` spies take its new `reads` argument.
- `test_crash_file.py::test_a_terminal_that_takes_nothing_never_stops_the_pump`: starts the tee's file writer and
  waits for it before checking the file's size (it drove `_pump` alone).
- `test_helabMainWindow.py`: Show log folder is checked through `file_manager` (it patched `openUrl`);
  `test_handle_exit_main_window` waits for the deferred close.
- `test_accessible_names.py`: `Walk` runs pending dock fits first (GT-10).

## Checks

At `bbc2eea` (the last fix), output kept whole in this folder:

- `fixes-suite.txt`: `pytest -n 8 --reruns 5 --reruns-delay 1 --basetemp=.ai/temp/pytest`: **9878 passed, 674
  skipped, no RERUN, no failure** in 114 s.
- `fixes-typecheck.txt`: `mypy helab/ --strict` (243 files), `mypy tests --strict` (239), `pyright helab tests`,
  `mypy helab/ --strict --platform win32`, `pyright --pythonplatform Windows helab tests`: all clean.

Step 4 (merge the latest `dev/v0.0.9`, the suite and type checks again, one push, CI's logs read for RERUN) follows
Sentinel's re-read. Each fix commit says which tests fail
without it (GT-1: 8 of 10 with `outside()` made synchronous; GT-5: 300 derives vs 1; GT-10: 36 lookups vs 8;
GT-2, GT-3: the audit's own measurements, now tests).

## Questions for Tony (Q~1 – Q~5 answered "yes"/"ok", built in round 2 above)

- **Q~1 (from the audit, GT-4):** should Basic plots v2 draw its 2D histograms at display resolution (decimated on
  the worker; the saved result and the bins stay as chosen), and cap dots lower (e.g. 500k for PyQtGraph and
  Matplotlib)? Proposed: yes, images ≤ 2048 a side (Plotly ≤ 1000), with a note on the plot when decimated. That
  includes PyQtGraph's `autoDownsample` and Matplotlib's `imshow` for regular bins, which also change the picture
  past screen resolution (measured: no invisible change worth making).
- **Q~2 (from the audit, GT-6):** should a script folder whose test import takes over about 2 s be left for Reload
  at start (like a share), with "takes N s to import"? Proposed: yes. The probe already reports `seconds`.
- **Q~3 (GT-8):** the two startup boxes ("Another HeLab is moving the cache…", "Finishing an interrupted cache
  move…") have no button and no limit. Add a Quit button to both (ending HeLab; the move stays for the next
  start)? Proposed: yes. And should the startup recovery get a no-progress timeout, which needs the move helper to
  send heartbeats while it copies (today it may not)? Proposed: yes, as one change with the heartbeats (A~8).
- **Q~4 (GT-9):** the native file dialogs (Settings' Browse… and Change…, Load Scripts…, Converter's import and
  export, Save to folder…, Debug's save) can stall in Windows' or macOS's sidebar on a dead share. Use Qt's own
  dialog (`DontUseNativeDialog`, as File › Open does) with a local start folder? It looks different from the OS's.
  Proposed: yes for Load Scripts… and Settings' folders (the ones that may point at shares); keep the native one
  for the converter's profile import and export.
- **Q~5 (GT-1 (a)):** after a conversion that ends minutes later on a large folder, should HeLab ask at all, or
  only show "Load anyway…" (no box opening with nobody there)? Proposed: only "Load anyway…" when the load was
  asked for by a conversion's end; Live or a preset at launch still asks.

## Later work (A~)

- **A~1 (GT-6 (A)):** the folder's code from memory, so the GUI thread reads nothing of a share at Reload. The
  probe returns each `.py` file's and helper module's bytes (bounded, e.g. 8 MB in all) through a file in its temp
  folder, not the JSON line; during `load_directory` a temporary meta-path finder serves the folder's top-level
  modules (and `_SourceOnlyLoader.get_data` the scripts) from those bytes, with `__file__` the real path; a module
  not in the snapshot imports from disk as now; linecache gets the source too. Data files a script reads at import
  still come from disk. After Q~2.
- **A~2 (GT-7 (b)):** the mount table for `share_of` (Folder details' 100 ms refresh, Live's convert tick, the share
  question) is read on the GUI thread every 10 s on Windows (`GetDriveTypeW` per letter, `WNetGetConnectionW` per
  mapped drive). Options: (1) helpers report mounts (extend `mounts_seen` in `events.py`; FolderCache keeps
  `_mounts_observed`; `share_of` reads that); (2) a refresh thread in the GUI process (changes the AGENTS.md rule
  "no worker pools besides …"). Proposed (1), after M~1 shows whether those calls wait.
- **A~3 (GT-11):** `RamBudget.check` takes each plot's buffers once per check and keeps holder counts (O(plots ×
  shots) instead of O(plots² × shots)).
- **A~4 (GT-12):** (a) coalesce `activityChanged` everywhere with `one_activity()` (GT-5 added it) or a dirty flag
  and `singleShot(0)`; (b) running tallies on parents instead of `_derive` over all children per child event;
  (c) cache `txy_sources.empty_helab_shots`/`origins_of` per dataset object (11 ms per 100 ms at 100,000 shots);
  (d) `explorer_live.low_hits_threshold()` cached until the setting changes. (d) needs a per-test reset of the cache
  (tests each have their own settings file), so it wasn't done here for an 8 µs saving; refresh only the shown
  tab's summary.
- **A~5 (GT-13):** keep the profile library in memory (refreshed on change), move `delete_io_traces` into
  `trace_check`'s helper, and the cache move's `undo_rename` and `cache_move.cleanup` into a helper.
- **A~6 (GT-15):** keep commit and branch when only `git status` times out in `build_info`, and log it (a timeout
  today makes updates quietly off for the session).
- **A~7 (guard 3):** `stall_probe.py` into conftest, report-only like RERUNs (over 1 s listed with stacks; fail
  only over 5 s).
- **A~8 (GT-8):** heartbeats from the cache-move helper while it copies, then a no-progress timeout for the startup
  recovery (with Q~3).
- **A~9 (guard 1):** widen the lint's scope to the GUI-side `helab/utils` modules (IOService and the watchdog have
  legitimate waits on their own threads, so it needs per-function scoping) and to `open`/`os.stat` with a longer
  allow-list.
- **A~10 (GT-1):** an app-side warning (log with stack) when a modal opens during a delivery, as the audit
  proposed; today only the test suite catches it.

## Checks needing Tony or the lab (M~)

- **M~1 (from the audit, GT-7, Windows lab PC):** with a mapped drive whose server is off, time HeLab's start
  (GT-7 (a), now fixed: expect no wait) and select a raw-only folder (GT-7 (b): does the GUI stall, and for how
  long?).
- **M~2 (from the audit, GT-9, Windows lab PC):** with the same dead drive, Settings › General › Browse… (native
  dialog: Q~4) and Open in File Manager on a folder of it (now detached: HeLab should stay responsive even if
  Explorer hangs).
- **M~3 (GT-1, GT-3):** on the TDC PC, after a long Live session: no burst of "timed out" helper retries after a
  box was left open (GT-1), and any "GUI stalled" line now reaches the log file with its stacks (GT-3), for the
  5.68 s stall.

## Proposed doc changes (the Coordinator applies them)

- **AGENTS.md, "I/O and threads"**, one line: "A modal box, dialog or menu is never `exec()`ed inside IOService's
  `_tick` or a plot's run end: code reached from a helper's or a job's result opens it through
  `gui_delivery.outside` (conftest's `no_modal_in_delivery` fails one)."
- **AGENTS.md, "UI"** (or "I/O and threads"): "Local folders and files open with `file_manager.show` (detached),
  never `QDesktopServices.openUrl`, which runs the shell's open on the GUI thread (`tests/test_file_manager.py`)."
  And: "A call that can block in `helab/views` or `helab/models` is listed with its reason in
  `tests/data/gui_thread_allowed.txt` (`tests/test_gui_thread_calls.py`)."
- **`.ai/architecture/app-runtime-and-ui.md`:** the quit watch's note thread and `crash_file.exit_after`; the
  console tee's file writer (`FILE_CHUNKS`, the lost-bytes note); the log file's handler first; `log_within` and the
  watchdog's 1 s per line; `gui_delivery`; `file_manager`; SIGINT/SIGTERM closing from the event loop.
- **`.ai/architecture/io-and-browsing.md`:** `_tick` delivers inside `gui_delivery.delivering("io")`;
  `SnapshotFileSystemModel._rederive` and `one_activity`; Windows' cache-folder classification by drive type.
- **`.ai/architecture/plots-and-scripts.md`:** `FolderReads` (the probe's `reads`, `READS_SECONDS`, `READ_FILES`,
  the loader's digests), `timed_hook` and `SLOW_HOOK_SECONDS`, `DockTabCloser.docks()`.
- **`.ai/architecture/testing.md`:** `no_modal_in_delivery` (and that a test patching one of its names replaces
  it), `no_file_manager`, the GUI-thread lint and its allow-list.
- **GT-30 (the re-review), for the app-runtime doc:** a teardown ended by `crash_file.exit_after` exits with code 1
  and writes every thread's stack to `crash-<pid>.txt`; the next start then says "The previous run crashed: see
  crash-<pid>.txt". Proposed: keep it. A quit that needed the last resort *is* a hang worth reporting (its stacks are
  the evidence), and it is rare; the line could name it ("ended by HeLab after its quit hung") if Tony prefers, by
  writing a marker line into the crash file before arming (a later A~).
- **Round 2 for the docs:** `plots-and-scripts.md`: Draw at (`DRAW_AT`, `DISPLAY_SIDE`, `PLOTLY_SIDE`, `DRAWN_DOTS`,
  `PlaneCounts.display`, the estimate's drawn cells), `SLOW_START_SECONDS` and the probe's `reads` line after `done`;
  `app-runtime-and-ui.md`: the startup boxes' Quit, `folder_dialog.choose_folder`; `testing.md`: guard 2 also through
  `FolderCache._on_event`; `io-and-browsing.md`: `ask_large` / "Load anyway…" after a conversion. Memory
  (`results/analysis-plots.md`): Draw at, Tony 2026-11-10.
- **`roadmaps/known-issues.md`:** close the `test_every_script_and_each_library` "QTabBar … no ID" entry (GT-10,
  `762d56c`); under the 5.68 s stall entry, add GT-23's candidates and that GT-3 now lets the next stall's line
  and stacks reach the log; note GT-2 fixed against "File › Quit sometimes left the process running".
