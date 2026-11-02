# Handoff: the arrangement preset hang (`agent/preset-modal-hang`)

Worker Lumen (claude, Opus 5.5), 2026-11-03, on the Live Scripts floor. Branch from `dev/v0.0.8` `db6b32e`. Brief
(CoCo, in Chat):
- **The hang:** on the switch-on branch (store-v4 the default), CI 41484277419, Ubuntu Tests 2/3, job 125410633098.
  `tests/test_presets_plots.py::test_an_arrangement_preset_round_trips_every_bundled_script` hung on a modal
  `QMessageBox.warning` ("Preset can't be read", from `read_arrangement`'s `RecordError`), raised right after the
  test's simulated restart had re-read the presets. The worker was killed at 100 s.
- **The asks:** find why `read_arrangement` raised and fix it, and add a `_warn` seam, so a test fails instead of
  hanging.

## Cause

**The test's restart lost a preset write that was still owed. A47.5's format isn't at fault, and the app handles
it.**

- **Which error it was.** The job's log has no "Preset … can't be read" warning, which `read_arrangement` logs for a
  record that can't be parsed. So the `RecordError` was "it isn't saved now": "all plots" wasn't in the store's
  memory after the re-read.
- **How a save can wait.** While the cache folder is being asked which store it holds (an identity probe, which
  `FolderCache` starts when a helper's answer names another store than the one in use), `_write_presets` doesn't
  write a change. It marks the change owed (`presets_unsaved[key] = ""`, `_presets_again = True`), starts no job,
  and writes it once the probe answers.
- **How the test lost it.** The test's `stored()` waited only for `presets_read and not _preset_jobs`. A save made
  during a probe therefore passed `stored()` at once, the simulated restart (`get_io_service().shutdown()`) dropped
  the owed write, and the re-read didn't find it. On CI, with store-v4 on and other tests' jobs answering late, a
  probe at that moment is plausible. Locally the test passed 72 runs on `e4967ec` under load (24 copies, `-n 8`,
  4 CPU hogs, 3 times).
- **The app is fine.** A real quit waits for an owed write: `presets_saving()` covers `_presets_again`, and the quit
  window holds it.

## Fix (tests, plus a seam in the app)

- **`stored()`** (in `tests/test_presets_plots.py`) also waits for `not _presets_again and not _probe_owner`.
- **`restart_presets`** asserts `not presets_saving()` before it shuts the helpers down, so a lost write fails the
  test there.
- **The seam:** `helab/views/plots/presets.py` gains `warning_box(parent, title, text)`, a module function that
  `ArrangementPresets._warn` calls by its module name. That is the plots area's only static modal. An autouse
  fixture in `test_presets_plots.py`, `no_modal_warnings`, replaces it with one that raises
  `AssertionError("a modal warning would wait here: …")`. A test that expects a warning still sets
  `presets.warn`, as before.

## Tests (each run on `db6b32e`'s code too)

| Test | Before | Now |
|---|---|---|
| `test_an_arrangement_saved_while_the_store_is_probed_survives_a_restart`: save while a probe is out (owed, no job); the probe answers 0.5 s later; restart; apply | fails with CI's message: "The preset “probed” can't be read (it isn't saved now)" | passes |
| `test_an_unexpected_preset_warning_fails_the_test_instead_of_waiting`: `apply` of a preset never saved | **hangs on the modal**, until a 20 s timeout | raises with the warning's text |

## Checks

- **Full suite** (`-n 4 --reruns 5 --reruns-delay 1`): 9159 passed, 673 skipped, **no RERUN**.
- **Type checks:** the five are clean.
- **CI:** CI_PLACEHOLDER

## Proposals (provisional)

- **A~1:** other tests that make a real "restart" (shut the helpers down) should wait for owed writes the same way.
  A shared helper in `tests/` would do it (`testing.md`).
- **A~2:** a suite-wide guard against a modal that no test closes (in `tests/conftest.py`, not this floor's): make
  `QMessageBox.exec` and the static helpers fail in tests unless a test allows them.
