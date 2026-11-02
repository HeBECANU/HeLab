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
