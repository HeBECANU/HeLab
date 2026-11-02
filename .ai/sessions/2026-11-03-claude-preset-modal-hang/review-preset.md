# Review: the arrangement preset hang (`agent/preset-modal-hang`)

Reviewer Prismo (claude, Opus 5.5), 2026-11-03. Diff: `git diff db6b32e..142e192 -- helab tests`. The handoff is `178bd90`.

**Verdict: no blocker. One low finding is open (L1), and there are three optional notes.**
- **The cause fits the evidence and the app is safe.** A real quit waits for the owed write.
- **A crash mid-probe can lose an owed change, but that is not a new risk.** It has existed since v0.0.6a1 (see below).
- **The seam follows the patched-names rule.**
- **Both tests prove their change.**

## The cause

- **The hang.** CI job 125410633098 (Ubuntu Tests 2/3) timed out at 100 s with the main thread in
  `helab/views/plots/presets.py`, line 602, in `_warn`. The test was at `tests/test_presets_plots.py:1062` on `db6b32e`:
  the `apply("all plots")` right after `restart_presets`.
- **The owed write.** While an identity probe is out, `_write_presets` (`folder_cache.py:2118-2121`) writes nothing.
  It marks the change owed (`presets_unsaved[key] = ""`, `_presets_again = True`) and starts no job. The old `stored()`
  waited only for `presets_read and not _preset_jobs`, so it passed at once. The restart then shut the helpers down with
  the write still owed.
- **Inferred, not seen.** The killed worker's log shows no probe line and no captured log, so the probe at that moment
  is inferred, not observed. The handoff says so ("plausible"). Whatever the cause was, the next occurrence will fail
  fast with its reason:
  - an owed write fails at `restart_presets`' new `assert not presets_saving()`;
  - a write that failed (unsaved with a reason, so not "saving") fails at `warning_box` with the warning's text instead
    of hanging.

## A real user can't lose it

- **Quit waits.** `presets_saving()` (`folder_cache.py:2054-2059`) counts `_presets_again` with an owed change, and
  `quit_saves` lists it (`:3012`, "Presets … waiting").
- **The write still happens during the quit wait.** While quitting (`quitting`, `:3118`), the probe's answer still runs.
  `_probe_answered` (`:1884-1941`) then runs `_read_presets` and `_write_presets`; the public `read_presets` is the only
  one gated by `quitting`. It stops only at `_closing` (`:3194`), which is set after the waits, or when the user chooses
  Quit now.
- **A test already proves it.** `tests/test_store_identity.py:281`, `test_writes_wait_for_the_probe_and_then_go`,
  asserts `"Presets" in cache.quit_saves()` while a probe holds a write, and that the write goes once the folder answers.
- **A crash mid-probe can lose it, but this isn't a new risk.**
  - During the probe the owed change exists only in RAM, so a crash, a kill or Quit now loses it.
  - The same is true of a change waiting for the store's names (`PRESETS_WAIT_READ`), or of one whose helper hasn't
    committed yet.
  - The window lasts as long as the identity helper takes, which the 60 s no-progress timeout bounds.
  - This code is unchanged since `9c477c21` (HeLab 0.0.6a1), and this diff doesn't touch it.
  - Not a finding.

## The seam follows AGENTS.md

- **Called bare in its own module, never imported by value.** `_warn` calls `warning_box` (`presets.py:609`), a lookup
  in the module's globals at call time, so the fixture's
  `monkeypatch.setattr("helab.views.plots.presets.warning_box", …)` takes effect. That matches the rule's "names patched
  and read only in their own module stay bare there" (like `ExplorerConverter` with `confirm_beside_on_share`). No other
  module imports it.
- **The arrangement presets' only static modal.** The plots area's other modals are `replace_or_add`, `confirm` and
  `ask_name` (`presets.py:148-171`, `box.exec()` / `QInputDialog`). Those are per-instance attributes that tests set,
  and `arrangement.py:432`'s question is non-modal (`show()`).
- **Expected warnings still work.** A test that expects a warning sets `presets.warn`, which takes precedence: `warn`
  defaults to `_warn`, which calls `warning_box`.

## The tests

On scratch copies: `db6b32e`'s code with `142e192`'s tests, `142e192`'s code, and four mutations of it, with
`--timeout=60`.

| Copy | `…fails_the_test_instead_of_waiting` | `…probed_survives_a_restart` |
|---|---|---|
| `db6b32e` code | error: `AttributeError: … has no attribute 'warning_box'` (the autouse fixture) | the same error |
| `142e192` | passes | passes |
| m1: old `stored()`, the new assert kept | passes | fails at the new assert: `assert not True` (`presets_saving()`) |
| m2: new `stored()`, the assert removed | passes | passes (the assert is a second guard) |
| m3: both reverted, as on `db6b32e` | passes | fails with CI's message: `["Preset can't be read: …"] == []` |
| m4: `_warn` calls `QMessageBox.warning` directly | **hangs** in `_warn` (the dump at 1:40 points there; `--timeout` can't break a Qt modal), killed | — |

So each test proves its change: the probe test fails exactly as CI did, and the seam test hangs as CI did.

## Findings

- **L1 (low; open, cheap).** The guard covers only `test_presets_plots.py`. Other tests apply arrangement presets
  through the real window's `ArrangementPresets` without `no_modal_warnings`:
  - `tests/test_presets_window.py:101`, `:123` and `:125`;
  - `tests/test_preset_folder_live.py:60` and `:90`.

  A preset missing there still hangs the worker on the real modal, the CI hang again. Fix: move the fixture to
  `tests/conftest.py` (autouse, and harmless where presets aren't used), or fold it into A~2 if CoCo prefers. Either
  way, A~2's list should name `replace_or_add` and `confirm`, whose defaults are real modals: an instance whose test
  forgets to set them would hang the same way.

## Optional notes

- **N1 (a doc proposal).** The handoff doesn't propose recording the new seam. A line in
  `.ai/architecture/plots-and-scripts.md`, or the patched-names list in `io-and-browsing.md`, would say that
  `presets.warning_box` is patched by `test_presets_plots` and called bare in its own module.
- **N2 (the handoff's "before" column).** On `db6b32e`'s code the two tests don't reach their behavior: they error in
  the fixture, because `warning_box` doesn't exist yet. The behaviors the table describes are what m3 and m4 show, so
  the table is right in substance.
- **N3 (A~1).** I agree with A~1: a shared "wait for owed writes, then restart" helper in `tests/`. `stored()` reads
  private fields (`_presets_again`, `_probe_owner`). A public `FolderCache.presets_idle()` (no job, nothing owed, no
  probe) would be cleaner for tests, but that is an app change, so it's for later.

## Checks

- **Full suite** on an isolated copy of `178bd90` (`git archive`, with the floor's `testdata`,
  `legacy/tdc_autoconverter` and `venv` linked in), `pytest -n 4 --reruns 5 --reruns-delay 1`:
  - The result was 3 failed, 9155 passed, 674 skipped, 15 rerun.
  - All 3 failures and all 15 RERUNs are the three git-provenance tests, which need a `.git` (`BuildInfo.commit ==
    'unknown'`): `test_release_recovery.py::test_detached_pr_stamp_records_source_branch_and_merge_ref_without_replacing_commit`,
    `test_versioning.py::test_source_provenance_ignores_launch_directory` and
    `test_versioning.py::test_frozen_metadata_survives_no_git_and_unrelated_cwd`.
  - Run in the floor's checkout (clean at `178bd90`), those three pass.
  - There was no other RERUN.
- **Type checks** on the same copy: `mypy helab/ --strict`, `mypy tests --strict`, `pyright helab tests`,
  `mypy helab/ --strict --platform win32` and `pyright --pythonplatform Windows helab tests` are all clean.
- **Under load** (16 busy loops, a load average of 34): `test_presets_plots`, `test_presets_window`,
  `test_preset_folder_live`, `test_store_identity` and `test_presets_store`, `-n 12 --reruns 5 --reruns-delay 1`, three
  rounds: 1677 passed each time, no RERUN.
- **CI 41490372206:** not reread. The handoff reports two Windows RERUNs:
  - the detached-stamp test (QF9's open proposal);
  - the Plotly worker crash, which `dev/v0.0.8`'s `b0eb914` fixes.

## Re-check: L1 (`git diff 498c584..767418c -- helab tests`)

Prismo, 2026-11-03. **L1 is closed. No finding is open.**

- **The fix.** `no_modal_warnings` moved from `test_presets_plots.py` to `tests/conftest.py`, autouse for every test.
  - It imports `helab.views.plots.presets` inside the fixture, at test time, after conftest has loaded, so the
    "never import helab before conftest" rule holds.
  - It patches the module attribute that `_warn` looks up when called (the seam as reviewed above), so
    `test_presets_window.py` and `test_preset_folder_live.py` are covered now, and so is every other file.
  - A test that expects a warning still sets `presets.warn` (`test_presets_plots.py`), and nothing in the suite
    patches `warning_box` itself.
  - The importing doesn't hurt the import-purity tests: `tests/test_headless_imports.py` checks in subprocesses, and
    it passed in the full suite.
- **The new test** is `test_presets_window.py::test_applying_a_missing_preset_in_the_window_fails_fast_instead_of_waiting`.
  It applies a preset that was never saved through a real `HelabMainWindow`'s `arrangement_presets`.
  - With the fix (the copy of `69add78`) it passes in 1.2 s.
  - With `498c584`'s conftest (the fixture lived only in `test_presets_plots.py`) it **hangs**. The dump at 1:40 shows
    `presets.py`'s `warning_box` (line 461), `_warn` (609) and `apply` (707). I killed it.
  - So it proves the move.
  - Its `waitUntil(presets_read and not _preset_jobs)` doesn't wait for owed writes (the `stored()` of the main fix).
    That doesn't matter here: no preset is saved, and the test wants "isn't saved".
- **The old seam test** still passes, now with conftest's fixture: `test_presets_plots.py::…fails_the_test_instead_of_waiting`.
- **Checks:**
  - **Full suite** on an isolated copy of `69add78`, `pytest -n 4 --reruns 5 --reruns-delay 1`: 3 failed, 9156 passed,
    674 skipped, 15 rerun.
    - All 3 failures and all 15 RERUNs are the three git-provenance tests (no `.git` in the copy), as in the first
      round. All three pass in the floor's checkout, which is clean at `69add78`.
    - No test hit "a modal warning would wait here", and there was no other RERUN.
  - **Type checks:** `mypy tests --strict`, `pyright tests` and `pyright --pythonplatform Windows tests` are clean.
    `helab/` is unchanged by this diff.
- **CI's two-writers failure.** CoCo says it is `dev/v0.0.8`'s, fixed in `28d8973` ("test_convert_helab: a writer
  tries a busy-index shot again until it lands"). I checked that `28d8973` is on `dev/v0.0.8` and not on this branch,
  so a merge with dev brings it in. I didn't read that CI run's logs.
- **The optional notes stand as they were.** N1, the seam doc line: `testing.md` could now name conftest's
  `no_modal_warnings`.
