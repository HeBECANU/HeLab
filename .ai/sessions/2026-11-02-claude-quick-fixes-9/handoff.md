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

### Run 41455114540 (`b0da084`): success, all 12 job logs read

- **No RERUN and no crashed worker.**
  - Tests: windows 1/2 4443, 2/2 4456; macos 4460, 4475; ubuntu 4456, 4476.
  - Converter backends: 847 / 849 / 849.
  - A39.1 passed on all three builds.
- **The guard test passed on every OS, in both cases.**
- **Stall lines, Windows only, again each made in and still in the running test** (no leaked window):
  - `test_accessible_names::test_every_script_and_each_library` ×2;
  - `test_preset_folder_live::test_live_waits_for_the_folders_first_load_to_show`;
  - `test_debug_runner_menu::test_the_screenshot_target_is_the_window_in_front_as_the_menu_opens`;
  - `test_helabMainWindow::test_file_menu_places_a_root_in_the_current_tabs_selected_folder`;
  - plus my own test's deliberate stall.

## test_io_trace's GUI-never-touches-source test: its waits (caching-v2 CI 41456480233)

- **The RERUN.** `waitUntil timed out in 20000 milliseconds` at :259, inside `wait_idle`, not the invariant
  assertion. The test takes 9–18.5 s on Windows CI, 3.4 s here.
- **Fix.** Its five waits on helpers share `HELPERS_MS = 60_000`: the listing, the expand, the load, and
  both waits for idle. CI only shows `wait_idle`'s own frame, so it can't say which of the two failed.
  - The assertions are unchanged.
  - CI's per-test 120 s still bounds the whole test.
  - Other tests' `wait_idle` keep 20 s.
- **Checks.** Full suite 8946 passed, no RERUN; the five type checks pass.
- **Known-issues proposal:** add it as Fixed. "`test_io_trace.py::test_the_gui_process_never_touches_source_folders`:
  a 20 s wait for idle helpers on Windows CI (41456480233, Tests 2/2); its helper waits are 60 s now."

### Run 41460607344 (`daed254`): success, all 12 job logs read

- **No RERUN and no crashed worker.**
  - Tests: windows 1/2 4448, 2/2 4462; macos 4465, 4481; ubuntu 4461, 4482.
  - Converter backends: 847 / 849 / 849.
  - A39.1 passed on all three builds.
- **`test_the_gui_process_never_touches_source_folders` took 12 s on Windows 2/2.**
- **That job took 24 min 40 s (usually 10–13).** No single test explains it.
  - The longest test was 94 s (`test_analysis_gui`'s other-library one), then the type checks (43–71 s).
  - The longest gap between two results was 18 s.
  - So it was a slow runner, not a hang.

## The cancelled Ubuntu job (CI 41468043383 attempt 1, agent/live-scripts 74b79b3): hunted, not pinned

- **What happened** (job 125354149828, `Tests (1/2)`, cancelled at 20 min):
  - **gw0:** `test_cache_admin.py::test_failed_listing_history_write_keeps_the_listing_guard` failed 6
    times, from 15:08:18 to 15:08:45, about 5 s an attempt and the last 0.2 s. In the green attempt 2 it
    took 0.4 s. gw0 then passed 457 tests normally.
  - **gw1, from 15:08:52:** every remaining test failed 6 times at about 35 s an attempt, with teardown
    ERRORs too. Those tests were `test_result_cache_badge`'s save test and `test_result_cache_plots`'
    outdated `[script]`/`[data]`, `ends_unshown[cancelled]` and `live_reruns_are_never_saved`.
    - Each attempt is their `WAIT = 30_000` for a save that never completed. In attempt 2 each takes
      0.3–1.4 s.
    - gw2 and gw3 had finished by about 15:10, so gw1's tail ran the job into its limit.
  - **43 RERUN lines and no reason.** The summary (`rerun reasons`), tracebacks and junit.xml come only
    when pytest ends.
- **Tried:**
  - the guard test alone, 15 of 15 passed;
  - gw0's exact order (110 tests) and gw1's (915 tests, from the log, mapped to Ground's IDs), replayed in
    one process with `pytest.main` and no xdist: both pass;
  - the log searched for disk-full, memory, OOM and file-limit messages: none.
- **What it looks like:** helper subprocesses on that runner getting nothing done from about 15:08. Both
  workers turned within 34 s; gw0's one test recovered, while every test left on gw1 needed a helper's
  save. Not proven: the run kept no reason.
- **Diagnostic so the next one names itself (`1ca5baa`).** conftest writes `RERUN REASON <test>
  (<phase>):` or `FAILED REASON …` live, on the controller's terminal, with the same lines as the
  summary. A cancelled job now keeps them.
- **Known-issues proposal (open):** "Ubuntu CI 41468043383 attempt 1: from 15:08, helper-dependent tests
  timed out on gw0 (`test_failed_listing_history_write_keeps_the_listing_guard`, ×6, ~5 s each) and gw1
  (`test_result_cache_*` saves, 30 s waits, ×6 each) until the job's 20-min cancel. No reason kept;
  neither worker's order reproduces it. Live reasons since `1ca5baa`."
- **A~ proposals.**
  - **A~4: `--session-timeout` in CI.** pytest-timeout 2.4 has it. Set it a little under each job's limit
    (e.g. 17 min for a 20-min job) so pytest ends itself and still prints its summary and writes
    junit.xml, instead of being killed.
  - **A~5: upload junit.xml `if: always()`.** Only useful with A~4: on a killed job the file doesn't exist,
    since pytest writes it at the end.

## test_live_convert's offline test: fixed (d03c0c6; Vault's reading)

- **The RERUN** (caching-v2 CI 41472779247, macOS Tests 2/2):
  `test_a_conversion_refused_offline_stops_auto_convert_and_says_so`, "assert 'auto-convert stopped: not
  while working offline' in 'Live stopped: Cancelled'" at :575.
- **Cause.** Live checks every 20 ms here. With no check in flight, its tick submits one; while the test
  is offline that check is refused, and its "cancelled" halts Live first.
- **Fix, in the test.** Live's next check is queued before going offline (`next_request`). With dispatch
  frozen it stays in flight, so Live asks for none while offline.
- **Repro case kept** ("a Live check comes due while offline": Live's tick runs while offline). With the old
  flow it fails with CI's exact message; now it passes.
- **Checks.** Full suite 9133 passed, no RERUN; the five type checks pass.
- **Known-issues proposal:** add it as Fixed. "A Live check asked for while the test was offline was
  refused and halted Live (CI 41472779247); the test queues Live's next check before going offline
  (d03c0c6)."
- **Test file touched:** `tests/test_live_convert.py`.

## CoCo's three Windows items (Ground CI 41476107464), priority (3) first

### (3) Three test groups (9787e35)

- **Change.** `ci-test.yml`'s matrix is three groups ("Tests (1/3)", "(2/3)", "(3/3)") for the required 3.13
  jobs on every OS.
  - One expression, the same job names everywhere, so "read every job" stays one pattern.
  - The compatibility jobs (PRs only, non-blocking) keep two, so a PR's run gains three jobs, not twelve.
  - conftest's `--test-group` already took N/M; its comments say three now.
- **Tests:** `test_test_groups` checks the even split for 2 and 3 groups (on the full suite) and reads the
  workflow's matrix; it fails on the old workflow.
- **Times from the first run, 41481668334** (all green; pytest time per group, from each job's summary
  line; job wall time in brackets):

  | OS | 1/3 | 2/3 | 3/3 |
  |---|---|---|---|
  | Windows | 8.9 min (10.9) | 10.0 (12.0) | 9.8 (13.2) |
  | macOS | 1.6 (4.2) | 6.1 (7.9) | 4.7 (6.2) |
  | Ubuntu | 3.0 (4.6) | 3.5 (4.9) | 3.4 (4.5) |

  - With two groups, Windows took 12.6/12.3 min (41478538998), and 20.3/21.1 on a slow runner
    (41476107464). Now about 10 min, against the stop line of ~25 and the job limit of 30.
  - The macOS jobs started 2–6 min after the others (macOS runner concurrency), so the run's end is set
    by macOS (16:42), not Windows (16:41).
- **That run's RERUNs:**
  - **Windows 3/3:** `test_release_recovery.py::test_detached_pr_stamp_records_source_branch_and_merge_ref_without_replacing_commit`,
    `assert 'unknown' == 'detached'` at :337. New; see "Filed" below.
  - **macOS 2/3:** `test_plot_backends.py::test_2d_plots_draw_with_every_library[values0-Plotly-TxyHistograms]`.
    Its worker died ("node down"; the live line says "(worker crashed or was killed)" since 57761e2). It's
    the known Plotly/QtWebEngine abort class (known-issues lines 139 and 162); another sighting.

### (1) test_cache_first's "(???)" (filed; the phase fixed in 57761e2)

- **The `(???)`.** It is xdist's phase for a dead worker's report. The live line now says "(worker
  crashed or was killed)".
- **The RERUN** `test_cache_first.py::test_a_server_clock_ahead_of_ours_keeps_the_quick_check[cached]`
  (Windows Tests 1/2, job 125382190106) was a hang, not a crash.
  - faulthandler's dump at 100 s ("Timeout (0:01:40)!") shows the main thread in `cache_store.transaction`'s
    `COMMIT`, under `start_dataset_job` (`loading.py:289`, the test's in-process `load` via
    `first_load`/`run_load`).
  - Then CI's `--timeout=120` killed the worker.
  - Not reproduced. The store is the test's own, and SQLite's busy timeout is 30 s, so a `COMMIT` held over
    100 s suggests a file-system stall on the runner, or a long wait behind another process.
  - **Known-issues proposal (open):** "`test_cache_first.py::test_a_server_clock_ahead_of_ours_keeps_the_quick_check[cached]`:
    the test's in-process load sat in SQLite's COMMIT (`start_dataset_job`) for over 100 s on Windows CI
    41476107464, Tests 1/2. The worker was killed at --timeout=120 and xdist reported it as crashed. Once;
    cause not found."

### (2) test_two_writers_side_by_side_lose_nothing (fixed, 324ad79)

- **The RERUN** (×2, Windows Tests 2/2, job 125382190899): `IndexUnavailable … database is locked … SQLITE_BUSY`
  after 27.30 s and 26.33 s.
- **Cause.** The test's two writer processes open the index per shot, and on a slow runner one missed its
  window past `BUSY_SECONDS`. The app takes that as harmless: the conversion fails and is tried again
  later.
- **Fix.** The writers try such a shot again, up to 4 times. The test still checks every row landed and
  the file is sound.
- **Repro case kept:** writers waiting only 1 ms. The old writer fails it 7 of 10 runs, the new one 0 of
  10.
- **Known-issues proposal:** add it as Fixed.

### Filed: test_release_recovery's detached stamp (new, from the three-group run)

- **The RERUN:** `assert 'unknown' == 'detached'` at :337, the test's first assertion,
  `checkout_build_info(checkout).branch` on a fresh `--no-checkout` clone just checked out.
- **Cause.** `build_info._git` gives each git call 2 s (`timeout=2`). On a slow Windows runner, `git status
  --porcelain` on that fresh checkout (it refreshes the whole index) can take longer, and
  `checkout_build_info` then returns an all-"unknown" `BuildInfo`.
- **App code** in the release area (`helab/build_info.py`), so not changed here.
- **Options** (Q~ for CoCo/Tony):
  - (a) a longer timeout where it can't slow the app's start (the build's stamp in `HeLab.spec`, and the
    tests), keeping 2 s at the app's start;
  - (b) the test runs `git status` once on its clone before asking (the index refreshed), which fixes the
    test only.
  - Proposed: (b) now, (a) if a real build ever stamps "unknown".
- **Known-issues proposal (open):** "`test_release_recovery.py::test_detached_pr_stamp_…`: 'unknown' ==
  'detached' on Windows CI 41481668334, because `build_info._git`'s 2 s timeout ran out for `git status` on a
  fresh checkout."

### Test files touched for these

`tests/conftest.py`, `tests/test_test_groups.py`, `tests/test_convert_helab.py`, `tests/test_test_isolation.py`;
CI: `.github/workflows/ci-test.yml`.

## (b), A~4, A~5 and the repro case's RERUN (CoCo's yes)

- **(b) a599ac6: the detached-stamp test.** Its fresh clone gets one untimed `git status` before
  `checkout_build_info`; the app's 2 s per git call stays.
  - The failure mode is shown here: with git calls given 1 ms, the branch is "unknown".
  - The slow first status itself doesn't happen on this Mac (0.14 s, then 0.13), so CI is the check.
- **A~4 457debc: `--session-timeout`.** It's 20 min of the 30-min job on Windows and 12 of 20 elsewhere.
  - pytest then stops between tests and fails the run with its summary, rerun reasons and junit.xml. This
    was checked under -n 2 here: "xdist.dsession.Interrupted: session-timeout", exit 2, junit written.
  - A test reads the job limits and the session timeouts, and keeps 8 min of each job for the rest.
- **A~5 5324a7f: junit.xml upload.** A step keeps junit.xml as an artifact for 7 days, `if: always()`.
  - Named `junit-<os>-py3<minor>-group-index-<N>`, where index 0 is group 1.
  - A test reads the step.
- **The repro case's RERUN** (Ground CI 41483647539, Windows Tests 3/3):
  `test_two_writers_side_by_side_lose_nothing[a writer missing its window]`, "IndexUnavailable … after
  0.04 s, attempt 4" at shot 0, with both writers making the index at once.
  - Fixed in 28d8973: a busy shot is tried again until `RETRY_SECONDS` (30 s), as a conversion is retried
    for as long as it takes, not 4 times.
  - New writer: 0 of 10 runs failed. The old writer (no retry) still fails the 1 ms case 7 of 10 here.
- **Each commit:** full suite (9157–9159 passed, no RERUN) and the five type checks before it.
- **Test files and CI touched:** `tests/test_release_recovery.py`, `tests/test_test_groups.py`,
  `tests/test_convert_helab.py`, `.github/workflows/ci-test.yml`.

### Run 41488725971 (`745bb46`: (b), A~4, A~5, the writers' retry): success, all 16 job logs read

- **A~4 works:** every test job's header says "session timeout: 1200.0s" (Windows) or "720.0s" (macOS,
  Ubuntu).
- **A~5 works:** nine artifacts `junit-<os>-py313-group-index-{0,1,2}`, 56–65 kB each.
- **Times.**
  - Windows pytest per group: 8.7, 9.0, 11.4 min.
  - macOS: 2.5, 5.1, 1.8. Ubuntu: 3.8, 5.2, 2.9.
- **All green; one RERUN:** `test_plot_backends.py::test_2d_plots_draw_with_every_library[values0-Plotly-TxyHistograms]`,
  macOS 2/3. Its worker died ("worker crashed or was killed").
  - That's the known Plotly/QtWebEngine abort class (known-issues lines 139, 162).
  - Its fourth sighting today: 41481668334 macOS 2/3; 41484513530 Ubuntu 2/3 and macOS 2/3; this run.
  - **Proposed:** a priority to hunt it. The worker dies in the Plotly case each time, now on Ubuntu too.
- `test_two_writers_side_by_side_lose_nothing`, both cases, and the detached-stamp test passed on every OS.
