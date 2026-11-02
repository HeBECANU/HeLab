# QF9 handoff (Rivet → CoCo)

Quick Fixes 9 on Ground (`dev/v0.0.8`), Tony's go 2026-11-02. One commit per item, each after the full suite
(`-n 12 --reruns 5 --reruns-delay 1`) and the five type checks, with HEAD the same before and after each run.
Vault's caching v2 paths were not touched.

| Item | Commit | Files | Test that fails before |
|---|---|---|---|
| A43.5 (Q43.5) the older cache's two refusal texts | 42855ab (with this brief) | `CacheTab.py`, `CacheDialogs.py` (strings only), `test_store_v3_question.py` | both refusal tests assert the whole text |
| A40.4 (Q40.1) Cancel all loads and scans' tip | 0f54c5e | `MissingShotsWindow.py`, `test_mismatched_folders.py` | the tip's text asserted (it was compared with the constant only) |
| A40.1 a helper still starting at quit | b34683e | `test_io_service_run.py` | none: no code change (below) |
| A41.1 an outdated saved result's view | — | — | skipped (CoCo, agreed) |
| A43.1 toolbar icons in every Qt test | e784834 | `tests/conftest.py`, `test_main_split.py` | `test_a_qt_test_has_the_apps_toolbar_icons` alone in a fresh process |
| A43.2 the presets re-reads' comments | e3faeb3 | `PresetsInspector.py`, `views/plots/presets.py` | none: comments only |
| `test_folder_icons` flake | eccb23c | `test_folder_icons.py` | its new "another thread stats a file meanwhile" case |

The full suite before each commit:

| Before | Passed | RERUN |
|---|---|---|
| A43.5 | 8861 | none |
| A40.4 | 8861 | none |
| A40.1 | 8862 | none |
| A43.1 | 8863 | none |
| A43.2 | 8863 | none |
| the icons flake | 8864 | none |

All 672 skipped each time, and the five type checks exit 0 each time.

## Notes per item

- **A40.1: done as a guard test (no code change; the cancel already covers it).**
  - `shutdown()` cancels every pending and active request before it sets `closed`, and `_run` kills a
    cancelled request's process as soon as `Popen` returns.
  - So the proposed `self.closed` check would add nothing: no request is closed without being cancelled.
  - `test_a_helper_still_starting_when_helab_quits_is_stopped` holds `_run` inside `Popen`, quits
    (`shutdown`), then lets it start a real helper: the helper is killed. The test fails when `_run`'s
    cancelled check after `Popen` is removed.
  - A scratch run, closing the service without cancelling, showed the only case the check would cover,
    and nothing does that.
- **A41.1: skipped (CoCo).**
  - There's no defect: an outdated saved result shows while its rerun goes on, and the TXY row and Release
    fall back to the plot's current view (`_shown_view or self.view`), the data the rerun uses.
  - **Proposed:** A41.1 stays open as "when Release or the TXY row needs it".
- **A43.1.** Conftest's autouse `toolbar_icons` sets the icons up once per worker, for tests that use
  pytest-qt (`qtbot` or `qapp` among their fixtures), taking `qapp` first.
  - A test without Qt still gets no QApplication. Otherwise a pure test first in a worker would get one,
    and a lazy QtWebEngine import after it would fail.
  - `test_main_split`'s own fixture is removed.
  - The suite's time didn't change (61–94 s across runs).
- **A43.2.** The comments now say why the cheap re-reads stay: the last read may have failed, or the cache
  folder moved since.
- **The `test_folder_icons` flake.**
  - The I/O fakes (`os.stat`, `os.scandir`, the service's `submit`) now raise only on the GUI thread, where
    painting runs, and pass other threads' calls to the real ones.
  - With the old fakes, the repro case fails as on CI 41164525298. pytest's own failure report then trips
    over the still-patched `os.stat` too, which shows how wide that patch was.
  - **Known-issues proposal:** move it to Fixed with "the I/O check patched os.stat/os.scandir for the
    whole process and raised on another thread's call; it checks the GUI thread's only now (eccb23c,
    QF9)".

## Proposals

- **A~1.** Other tests patch `os.stat`/`os.scandir` or `subprocess.Popen` process-wide, the pattern behind
  both Windows flakes fixed in QF8 and QF9. A sweep could make them thread-aware too. Candidates: `grep -rn
  'setattr(os, "stat"\|setattr(os, "scandir"\|subprocess.Popen"' tests/`.
- **Known-issues: two flakes moved to Fixed.**
  - `test_folder_icons` (above).
  - QF8's `test_io_service_run` one, if not done at the docs pass.

## CI

The run's results follow, every Tests and Converter backends job's log read for RERUN.

### Run 41374704252 (`0406a1d`): success, all 12 job logs read

- **Tests passed.** windows Tests 1/2 4412, 2/2 4416; macos 4429, 4435; ubuntu 4425, 4436. Converter
  backends 847 / 849 / 849. No crashed worker.
- **1 RERUN**, windows Tests 2/2 (job 125052359778):
  `test_gui_responsiveness.py::test_timeout_retry_releases_dead_helper_slot_while_artifact_reader_is_blocked[1]`,
  `waitUntil timed out in 3000 milliseconds` at :292 (the killed fake helper's `poll()` still None).
  Known-issues line 137 lists both `[1]` and `[2]`; this is another sighting. Not QF9's code.
- **A39.1 passed on all three builds:** "built cleanly at 0406a1d2f6…".
- This record is committed locally only (doc-only).

## Follow-up: the type checks' timeout (e8a28a1; merged with Tony's Labcam cc82398 as 3c1720f)

- **The failure.** caching-v2 CI 41389534725, macOS (job 125097691928): `test_typing.py::test_pyright_helab`
  hit `--timeout=120` five times.
- **Measured from CI log timestamps** (a test's start line to its result line).

  `test_pyright_helab`:

  | Run | macOS | Windows | Ubuntu |
  |---|---|---|---|
  | the slow runner | 115–142 s | | |
  | QF9's 41374704252 | 58 s | 73 s | 40 s |
  | this push's 41392473183 | 81 s | 97 s | 42 s |

  mypy took 20–56 s.
- **Fix.** A module-level `pytest.mark.timeout(300)` on `test_typing.py`, with a guard test.
  - Why a mark and not a CI step: CI has no type-check step (`test_typing` is its only mypy and pyright
    run, on every OS), and a type error fails the suite locally too (AGENTS.md).
  - Shown: with `--timeout=2`, pyright (12.7 s here) times out without the mark and passes with it.
- **`test_accessible_names.py::test_every_script_and_each_library` is near 120 s too.**

  | Run | macOS | Windows | Ubuntu |
  |---|---|---|---|
  | the slow runner | 123 s (timed out), 109 s on its rerun | | |
  | QF9's run | 66 s | 94 s | 29 s |
  | this push's run | 85 s | 99 s | 27 s |

  **Proposed (A~2):** give it its own `pytest.mark.timeout(300)`, or split it per library. It isn't
  changed here, since that wasn't asked.
- **Local suite before the commit:** 8865 passed, 2 new RERUNs, under a load average of ~37 (other agents).
  Both passed 5 of 5 alone, and the suite after the merge (load lower) had none.
  - **Proposed known-issues lines:**
    - `test_live_io.py::test_a_live_check_pauses_background_work_only_while_it_reads`: `waitUntil` 10 s
      at :136.
    - `test_result_lifecycle.py::test_save_x_eviction_of_the_same_key_before_its_transaction_saves_the_newer_copy`:
      `waitUntil` 30 s at :71.

    Both are local, under heavy load, and passed on retry; the cause hasn't been looked into.
- **Merged tree (3c1720f):** 8865 passed, no RERUN; the five type checks pass.
- **CI 41392473183: success.** All 12 job logs read: no RERUN, no crashed worker; A39.1 passed on all three
  builds.

## A~2 done: the walk's own timeout (5f52068; CoCo's yes)

- **Change.** `test_every_script_and_each_library` gets `pytest.mark.timeout(300)`, with a guard test.
- **Not split per library:** one walk keeps the IDs check as one check, with the window and folder set up
  once.
- **Shown:** with `--timeout=5`, the walk (8 s here) times out without the mark and passes with it.
- **Full suite:** 8866 passed, no RERUN; the five type checks pass.
- **CI 41394539355 (`5f52068`): success.** All 12 job logs read, no RERUN, no crashed worker.
  - Tests: windows 1/2 4414, 2/2 4416; macos 4431, 4435; ubuntu 4427, 4435.
  - Converter backends: 847 / 849 / 849.
  - A39.1 passed on all three builds.

## Tonight: A47.3 and A46.1 (QF9 continued)

### A47.3: the GUI watchdog left running (36b2224)

- **Fix, in `helab/utils/gui_watchdog.py`, not the two quit tests.** `_watch` ends once its QObject is
  deleted (`sip.isdeleted`, checked each 0.5 s; a flag read, safe from its thread), so any window deleted
  without its full close takes the thread with it.
  - Before: `closeEvent` returns early while the quit window waits for saves. A test ending there had the
    window deleted at teardown, and the thread logged "GUI stalled… capturing thread stacks" every 30 s
    for the rest of the worker.
  - Not a Python callable on `destroyed` (AGENTS.md rules it out), and `weakref.finalize` can't run while
    the thread holds the wrapper.
- **The quit test isn't pinned.** `test_quit_confirms.py` and `test_txy_last_used_quit.py` leave no
  watchdog alone, even on the old code, as known-issues says.
- **Tests:** the new `tests/test_gui_watchdog.py`.
  - Cases: deleted unstopped (it ends), `stop()` (it ends), and a real `HelabMainWindow` whose close waits
    for saves, then deleted (its watchdog ends).
  - The two deleted cases fail on the old code: the thread is still alive after 3 s.
- **Suite:** 8932 passed, no RERUN, and no "GUI stalled" in its log; the five type checks pass.
- **Known-issues proposal:** move "A quit test leaves its `GUIWatchdog` running" to Fixed (36b2224).

### A46.1: process-wide fakes in tests (6fa8cd9)

- **The helper:** `conftest.this_tests(fake, real)`.
  - "This test's" threads are the test's own thread plus every thread started after the patch. Its
    IOService's `_run` threads start helpers, so the test thread alone wouldn't do.
  - Threads alive before the patch get the real function. It compares thread objects, since idents are
    reused.
- **Used where a fake refuses or records every call, or replaces `Popen`:**
  - `test_folder_cache`, `test_folder_summary` (3 blocks);
  - `test_gui_responsiveness` (the rendering block, including `CacheStore` and `sqlite3.connect`; 3 Popen
    fakes);
  - `test_settle_setting`, `test_root_discovery` (an lstat refusing all), `test_scan_history`,
    `test_two_step_browse`, `test_live_check` (2).
- **Left as they are:**
  - fakes that act only on the test's own paths (`test_cache_first`, `test_offline_browsing`,
    `test_io_trace`, three in `test_root_discovery`, one in `test_two_step_browse`);
  - `test_folder_summary`'s two already thread-aware ones.
- **Test:** `test_a_process_wide_fake_acts_on_this_tests_threads_only` in `test_test_isolation.py`. It
  fails with the plain fake the sites used.
- **Suite:** 8933 passed, no RERUN; the five type checks pass.
- **A guess, not checked:**
  `test_gui_responsiveness.py::test_timeout_retry_releases_dead_helper_slot_while_artifact_reader_is_blocked`'s
  known flake (line 137: a killed fake helper's `poll()` still None at :292) may be this pattern. An
  earlier test's thread starting a helper hit its Popen fake and added a stray process to `processes`. If
  so, it stops; keep the entry until CI says.

### Test files touched tonight (all outside the floors' app code)

`tests/test_gui_watchdog.py` (new), `tests/conftest.py`, `tests/test_test_isolation.py`,
`tests/test_folder_cache.py`, `tests/test_folder_summary.py`, `tests/test_gui_responsiveness.py`,
`tests/test_settle_setting.py`, `tests/test_root_discovery.py`, `tests/test_scan_history.py`,
`tests/test_two_step_browse.py`, `tests/test_live_check.py`. App code: `helab/utils/gui_watchdog.py` only.

### Run 41446664564 (`910e59f`: A47.3, A46.1): success, all 12 job logs read

- **No RERUN and no crashed worker.**
  - Tests: windows 1/2 4441, 2/2 4456; macos 4458, 4475; ubuntu 4454, 4475.
  - Converter backends: 847 / 849 / 849.
  - A39.1 passed on all three builds.
- **"GUI stalled" lines remain on Windows only:** 3 in Tests 1/2, 2 in Tests 2/2.
  - Every Windows run I have shows 1–3, before and after tonight: QF8's 41165963510 had 3+1, QF9's runs
    3+3, 1+3 and 3+1.
  - **Not what A47.3 fixed.** That was a deleted window's watchdog running on (now it ends). These come
    from a watchdog whose window is still alive.
    - One (2.18 s, Windows 2/2) is a test busy on the main thread with its window open (a plot hook in
      `test_constant_layers`), which is the watchdog working as meant.
    - The others (2.30 s, 2.18 s and 28 s, Windows 1/2) fire during converter tests that open no window,
      so an earlier test's window is still alive in that worker.
  - The stack dumps go to the worker's raw stderr, which xdist doesn't put in CI's log, so the window
    can't be named from this run.
- **Proposed:**
  - Keep the known-issues entry open, retitled "a test leaves a window (and its GUIWatchdog) alive".
  - **A~3, a diagnostic:** under pytest, the stall line also names the running test
    (`PYTEST_CURRENT_TEST`) and the watchdog's window (`parent().objectName()` or its creation test), so
    the next CI sighting names the leak.
  - Or: conftest fails a test that leaves a `HelabMainWindow` alive, as it does for web views
    (`delete_left_widgets`).

### A~3 done: the stall line names its window and tests (CoCo's yes)

- **The line now reads:** `GUI stalled for Xs (<window class> ['<objectName>']; made in <test>; now in
  <test>); capturing thread stacks`.
- **Where the names come from:** the window is read on the GUI thread, at construction and each beat;
  the tests come from `PYTEST_CURRENT_TEST`.
- **Test:** `test_a_stall_line_names_its_window_and_the_tests` fails on the old line.
- **Full suite:** 8934 passed, no RERUN; the five type checks pass.
- What the next Windows run's lines name follows.

### Run 41449699791 (`a00e3f6`, A~3): success, all 12 job logs read; what the stall lines name

- **No RERUN and no crashed worker.**
  - Tests: windows 1/2 4441, 2/2 4457; macos 4458, 4476; ubuntu 4455, 4476.
  - Converter backends: 847 / 849 / 849.
  - A39.1 passed on all three builds.
- **The stall lines, Windows only, each naming the test that made its window and the test running now:**
  - Windows 1/2: three, all `HelabMainWindow` made in and still in
    `test_accessible_names.py::test_every_script_and_each_library` (2.24 s, 2.28 s, **27.77 s**).
  - Windows 2/2: `HelabMainWindow` made in and still in
    `test_debug_runner_menu.py::test_dump_state_saves_what_the_window_shows_from_memory` (2.22 s) and
    `::test_the_screenshot_target_is_the_window_in_front_as_the_menu_opens` (2.42 s). Plus my own test's
    deliberate stall (`QObject 'plots_window'`, 10.50 s).
- **Conclusion: no window outlives its test.**
  - Every line's window was made in the test running then, so these are tests keeping the GUI thread busy
    with their own window: real stalls of a test, not a leak.
  - **This corrects my earlier reading.** The lines that sat among converter-test lines were another
    worker's output interleaved in the log, not a leftover window in that worker.
  - The longest is the scripts-and-libraries walk on Windows: 27.8 s without the event loop running, on a
    test that takes 94–99 s there (its own 300 s timeout since 5f52068).
- **Proposed:**
  - Close the known-issues entry: A47.3 (36b2224) fixed the leak it described, and what remains is
    in-test stalls.
  - A line for testing.md: a "GUI stalled" line in a CI log whose "made in" and "now in" are the same test
    is that test blocking the GUI thread, not a leftover window.
  - My own test's deliberate stall line shows in CI's log too. It could be filtered (a logger level) if
    it misleads; left as it is.

## A40.1's guard test RERUN (caching-v2 CI 41451159277; Vault's reading): fixed

- **The RERUN.** `test_io_service_run.py::test_a_helper_still_starting_when_helab_quits_is_stopped`,
  `TimeoutExpired` after 10 s at :162.
- **Cause.** Its `Popen` fake took any `HeLab-*` thread, so another IOService's helper start meanwhile
  entered it too and could be `started[0]`, which this test never kills.
  - `this_tests` wouldn't help: that helper's thread starts after the patch.
- **Fix.** The fake takes only this request's start, known by its stderr file in the request's folder; the
  request is known through `IOService.before_start`.
- **Repro case kept:** another service's helper starts meanwhile. With the old check it enters the fake
  too (`assert (2 == 1)`, 3 of 3).
- **Checks.** Full suite 8935 passed, no RERUN; the five type checks pass.
- **Known-issues proposal:** add it as Fixed. "A40.1's guard test took another IOService's helper start
  as its own (caching-v2 CI 41451159277); fixed by matching its request's stderr path."
