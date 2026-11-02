# Review: Live Scripts and the saved TXY choice (`agent/live-scripts`)

Reviewer Prismo (claude, Opus 5.5), 2026-11-03, for CoCo. Range `a0bc26d..2617cfa` (the code), plus the handoff
commit `2825ddb`. I read the brief, design, handoff, `AGENTS.md`, `plots-and-scripts.md`, `settings.md` and the
whole diff (`git diff a0bc26d...2617cfa`), and reran the checks myself.

**Verdict: 11 findings: 0 blockers, 3 medium, 5 low, 3 nits.** M1 and M2 should be fixed before landing. M3 is a
startup risk that should at least go into known-issues (and probably a Q~ for Tony). The lows are small fixes or
records.

## Checks rerun

- Full suite, `pytest -n 4 --reruns 5 --reruns-delay 1 --basetemp=.ai/temp/pytest-prismo`: **8963 passed, 672
  skipped**, 2 warnings (pyqtgraph NumPy 2.5 deprecation), 139.9 s. **No RERUN** (no "rerun reasons" in the
  summary).
- `mypy helab/ --strict` (203 files), `mypy tests --strict` (194), `pyright helab tests`, `mypy helab/ --strict
  --platform win32`, `pyright --pythonplatform Windows helab tests`: all clean.
- **Do the tests fail without their change?** I ran 23 mutations on a copy of the tree (each one change, run
  against the three new test files plus `test_scripts_folder.py` and `test_script_system.py`, serially). 21 were
  caught: the in-flight wait (`_busy` returns 0; `in_flight` not recorded), unloading helpers, the source-only
  loader and its path hook, the protected roots, the D1 fold, the watcher being dropped when the toggle is off, the
  stamp comparison, the error lines, restoring remembered folders, un-holding in `keep_script`, re-applying the
  settings on adopt, the file-hash swap ("another copy"), `_folder_read`, `_own_folder_changed`, D2, Keep ignored,
  the old-record `txy_keep` default, the waiting plot taking its choice, a renamed profile found by its tag, and a
  script preset saving the choice. **2 survived** (M2, L1).
- **Scope.** Files outside the brief's named paths: `helab/analysis/runner.py` and `runner_core.py`
  (`in_flight()`, needed for CoCo's added rule that a reload never runs under a `compute`), and
  `helab/analysis/presets.py` (the `TxyChoice` format). The brief allows `helab/analysis/` "where a rerun or the
  TXY choice needs it", so both are justified. `presets.py` now imports `helab.utils.txy_sources` (standard library
  only); `test_headless_imports` passes.
- **What the brief asked me to check.** Reloads re-import only the user's folders: yes. `helper_modules` skips
  `helab.*` and anything under HeLab's package, the stdlib and site-packages (but see L3 on the import hook). Helper
  modules reload, including packages and lazy imports: yes. The D1 hash fold: yes, except lazy helpers (L4). A reload
  never swaps code under a running compute: yes. `_try_reload` waits on `in_flight()` for every runner the plots
  use, and the check and the reload both run on the GUI thread, so a submit can't slip in between. Plots keep the
  settings that still fit, or keep their old code in amber (D3): yes. The watcher exists only while the toggle is
  on, and it watches only the script folders and the helper files and folders inside them: yes. Load errors are
  shown and never crash: yes. A47.5 (`SavedPlot`/`ScriptPreset.txy`, the Keep box, D2, old records restore as the
  folder's tab): yes, apart from M1 (a D4 hole) and M2 (a test gap).

## Medium

**M1. A reload makes a reopened plot that is waiting with its own TXY choice read its folder, which breaks D4.**
`helab/views/plots/instance.py:994-997` (`adopt_script`). When `run_reopened` finds the folder's data but the
folder wasn't read this session, it calls `_end_wait()` and sets `_own_waits = True`. From then on `waiting()` is
False, because `_wait` is None. So `adopt_script` skips its `if self.waiting(): … return True` branch and calls
`self.run()`. `run()` sees `_own_waits` and calls `_load_own_choice()`, which loads the folder. With "Reload when a
script is saved" on, this happens when the user saves a script, with no select of the folder and no Rerun. I
confirmed it with a throwaway test (a reopened `TxyChoice("helab-only")` plot on a dataset from the disk cache
only, then `hold_for_reload()` and `adopt_script(...)`): `loads(cache)` went from `[]` to one load request.
`keep_script` is fine; the same probe with it made no request. **Fix:** in `adopt_script`, treat `_own_waits`
like waiting (`if self.waiting() or self._own_waits:` show the follow line and return without running), and add
that test to `tests/test_plot_txy_saved.py` or `tests/test_live_scripts.py`.

**M2. No test checks that a plot's record holds its TXY choice, the centre of A47.5 (Q14.2/Q23.4).** I changed
`saved_plot()` to `txy=None` (`instance.py:854`), so arrangements, arrangement presets and the plots reopened at
start would save no choice, and every test passed. The tests build `SavedPlot(..., txy=...)` by hand for the
restore side, and they check `saved_plot().txy is None` only with Keep off. **Fix:** add a test that switches a
plot to a choice with Keep on (for example `set_txy_source("helab-only", "plates-2022")`), then asserts
`saved_plot().txy == TxyChoice("helab-only", "plates-2022", "p22v1")` and that it survives `Arrangement`
dumps/loads and a reopen (`reopened(...)` with the captured record).

**M3. At start, HeLab now runs the user's script code and lists their folders on the GUI thread, before the window
shows.** `helab/views/plots/script_tree.py:209` (`_restore_folders` in `TreePanelWidget.__init__`). Load Scripts…
always ran on the GUI thread, but only when the user chose it. Now every start does it. If a remembered folder is
on an unreachable share (A~5 names this case), or a saved script blocks at module level (`input()`, a network
call, a long loop), HeLab can't start, and every later start blocks the same way. The only way out is editing the
settings ini by hand. A~5 is filed as optional work, but this is a gap that users would hit, so it belongs in
`roadmaps/known-issues.md`, covering both cases. **Proposed:** record it before landing, and add a Q~ for Tony on
the remedy. Options: load the remembered folders after the window shows (and before `PlotReopen.restore`), skip
them with a modifier key or a `--no-scripts` flag, or check each folder off the GUI thread first. I don't think it
blocks landing if CoCo records it.

## Low

**L1. No test checks the hold.** I removed `self._held = True` from `hold_for_reload` (`instance.py:947`) and every
test passed. Without the hold, a Live revision or Rerun that arrives while the button reads "Reload (waiting)"
submits again on the old code, and that run keeps delaying the reload. **Fix:** in
`test_a_reload_waits_for_a_run_of_its_scripts_on_the_worker_thread`, assert that while the reload waits,
`instance.run()` (or a revision) enqueues nothing and the status reads "Waiting for its script to reload…".

**L2. "Reload (waiting)" can get stuck.** `script_tree.py:331-333, 369-372`. Suppose a reload is waiting and the
user removes that folder with "Remove from the list". `remove_folder` empties `_pending`, but `_stop_waiting()` is
never called: `_run_ended` and `_try_reload` both return early when `_pending` is empty. The button keeps "Reload
(waiting)" and its waiting tooltip, and the runners stay connected, until the next reload. **Fix:** in
`_try_reload`, `if not self._pending: self._stop_waiting(); return`. Alternatively, call it in `remove_folder`
once nothing is pending.

**L3. The source-only import hook also applies to installed packages under a script folder.**
`helab/scripts/scripts_manager.py:104-120` (`_source_only_finder`, `_source_only`). `helper_modules` skips
`_protected_roots()`, but the path hook doesn't. I loaded the venv's `lib/python3.13` as a script folder, and then
`import pyparsing` came through `_SourceOnlyLoader`. `_source_only` also deletes the cached finders under the
folder, so this applies to any path inside a script folder, including site-packages. The effect is that, after
someone loads a home folder or the HeLab checkout as a script folder, installed packages imported later skip
`.pyc` (slower imports). The code is still correct. **Fix:** make `_source_only_finder` refuse paths inside the
protected roots (the same rule as `helper_modules`).

**L4. The D1 fold leaves out helpers that are only imported in `compute`.** `scripts_manager.py:344-355`.
`_fold_helper_hashes` reads `helper_modules()` just after `_unload_helpers`, so a helper imported lazily is never
in `sys.modules` at that point. Editing such a helper doesn't change the script's `file_hash`, so R2's
saved-result reuse (off by default) and the "another copy" note can't see the change. **Fix:** fold the folder's
known helper files that still exist (`self._helper_files`, which already collects lazy ones), or note the limit
in the docs.

**L5. Auto-reload can reload once when nothing changed.** `script_tree.py:483`. `_stamp_of` stamps
`watched_files()`, which includes helper files found in `sys.modules`. Suppose a helper in a subpackage is first
imported lazily during a run. The folder's stamp now differs from the one saved at load, without any edit. The
next unrelated watcher event, such as vim's `.swp` or a non-`.py` file saved in the folder, then reloads the folder
and reruns its plots. **Fix:** stamp the known helper files at load (see L4), or refresh `_stamps` after a run
when only the file list grew. Alternatively, record it in known-issues.

## Nits

**N1. Missing IDs.** The details window's Close button has no ID (`show_error_details`, `script_tree.py:543`; most
of HeLab's message boxes call `identify_buttons(box, prefix)`). The new menu actions (`auto_reload_action`, and
each folder's Reload and Remove) have no `objectName`. `test_accessible_names` doesn't reach either, so nothing
fails, but the rule asks for a stable ID on every interactive control.

**N2. Submenus leak.** `_fill_folders_menu` (`script_tree.py:260`) makes one submenu per folder each time the menu
opens. `QMenu.clear()` deletes their actions, but the submenus themselves stay children of `folders_menu` until the
panel closes. **Fix:** `deleteLater` the old submenus in `_fill_folders_menu`.

**N3. A test fixture doesn't restore the import hook.** `tests/test_scripts_reload.py`'s `restored_imports`
restores `sys.path` and `sys.modules`, but not `sys.path_hooks`, `scripts_manager._SOURCE_ONLY` or
`sys.path_importer_cache`. The hook therefore stays installed for every later test in that xdist worker. It is
harmless today.

## Doc proposals in the handoff

They match the code: the folder is appended to `sys.path` (not put first, as the design said; the handoff says
why), `in_flight`, `adopt_script`/`keep_script`, `TxyChoice`, the Keep box, D2 and D4. Additions I'd make when
landing:

- `roadmaps/known-issues.md`: M3, and L4/L5 if they aren't fixed.
- The D4 sentence in `plots-and-scripts.md` should say that a reload doesn't count as a read either (once M1 is
  fixed).

The settings rows' descriptions and `settings.md`'s paragraph are fine.

## Re-check of the fixes (2026-11-03)

I re-checked only the fix diff, `git diff 2825ddb..944fbd6 -- helab tests` (code commit `a18e4c9`).

**Verdict: all 11 findings are closed. The fix adds one new finding, R1 (medium), which is open.**

**Checks:**

- The touched tests and their neighbours pass: `test_scripts_reload`, `test_live_scripts`, `test_plot_txy_saved`,
  `test_scripts_folder`, `test_script_system`, `test_presets_plots`, `test_accessible_names`,
  `test_destroyed_connections` and `test_headless_imports`. Run with `-n 4 --reruns 5 --reruns-delay 1
  --basetemp=.ai/temp/pytest-prismo`: **167 passed, no RERUN**.
- The five type checks are clean.
- **Mutation check of the fixes.** I reverted each fix in turn on a copy of the tree. All of them made a new test
  fail except one of L2's two guards: the stop in `_try_reload` can be removed with no test failing, but the
  `remove_folder` guard is caught. That is enough. The two earlier survivors are caught now: M2 by
  `test_a_plots_record_holds_the_choice_made_in_its_row`, and L1 by the waiting test's new assertions.

| Finding | Status | How it was fixed |
|---|---|---|
| M1 | closed | `adopt_script` keeps waiting while `_own_waits` is set. |
| M2 | closed | The record test chooses in the row, then checks `saved_plot()` and a reopen. |
| M3 | closed for landing, see below | Remembered folders load after the window shows; network shares are skipped; the loading marker. |
| L1 | closed | Asserts nothing is submitted while held, and the status line. |
| L2 | closed | `_stop_waiting` runs when nothing is pending, in `_try_reload` and `remove_folder`. |
| L3 | closed | The hook refuses `_PROTECTED` paths, with a test using a fake site-packages. |
| L4 | closed | `_know_helpers` runs before unloading; the fold uses the known helpers. |
| L5 | closed | `_folder_changed`: a helper newly found but not modified since the load is absorbed. |
| N1 | closed | `identify_buttons` on the details window; object names on the actions. |
| N2 | closed | The submenus are `deleteLater`'d. |
| N3 | closed | The fixture restores `path_hooks`, `_SOURCE_ONLY` and `path_importer_cache`. |

**M3: is it closed by what was built?** Yes, for landing.

- **The share stall is gone at start.** A remembered folder on a share is never listed or loaded at start, and
  never watched. `on_network` reads only the mount table: `GetDriveTypeW` and the UNC check on Windows, which
  covers the lab's mapped drives; psutil's `getfsstat` elsewhere.
- **A blocking or crashing script can now be recovered from inside the app.** Its first start still freezes, now
  just after the window shows. The next start skips the remembered folders and shows an amber line with Reload,
  so the settings file no longer has to be edited by hand.
- **PlotReopen's deferral is sound.** `restore()` returns early while `folders_pending` is set and runs again on
  `foldersRestored`. `record()` doesn't overwrite last session's record in the meantime.

**What stays open:**

- (a) Q~3, Tony's decision on importing off the GUI thread. Until then, a script that blocks at import still
  freezes HeLab once, whether it comes from Load Scripts…, Reload or the first start.
- (b) R1, below.

### R1 (medium, new): a loading marker that names an unlisted folder makes every later start skip the folders

`helab/views/plots/script_tree.py:326-334` (`_load_folder`), and `add_folder` (`:373-376`). `add_folder` appends
the new folder to `_remembered` and loads it. It saves the list (`_save_folders()`) only after the load. So if
HeLab hangs or crashes while Load Scripts… loads a **new** folder X, the marker names X but the saved list
doesn't. At the next start every remembered folder is skipped, as designed. But nothing ever removes the marker:

- Reload runs `_load_folder(F)` with `stuck == X`, which is neither `own` nor `== F`.
- "Remove from the list" can't reach X, because X isn't in the list.

So **every later start skips all the remembered folders**, with no way out in the UI except loading X again
through Load Scripts…, which the user has no reason to guess. A marker that can't be read (`loading_marker() ==
""`) gets stuck the same way. I confirmed it with a throwaway test: list `[good]`, marker `{"folder": hung}`. After
`restore_folders()` and `reload_scripts()`, the marker still names `hung`, and a second `TreePanelWidget`'s
`restore_folders()` loads nothing.

**Fix:** any of these would do:

- a deliberate Reload or Load Scripts… removes a marker it didn't make once its loads end (the user's word,
  like Rerun);
- `restore_folders` keeps a marker only when it names a remembered folder, and drops one naming no listed
  folder or none;
- `add_folder` saves the list before loading.

Add a test for the unlisted-folder case.

## Re-check 2: R1 and R2 (2026-11-03)

I re-checked only the fix diff, `git diff f66a946..909c66d -- helab tests` (code commit `c79f210`).

**Verdict: R1 and R2 are closed, and no finding is open. Nothing here blocks landing.**

**Checks:**

- The touched tests pass: `test_live_scripts`, `test_scripts_reload`, `test_plot_txy_saved`,
  `test_accessible_names` and `test_destroyed_connections`, run with `-n 4 --reruns 5 --reruns-delay 1
  --basetemp=.ai/temp/pytest-prismo`: **81 passed, no RERUN**.
- The five type checks are clean.

**R1 (a stale loading marker) is closed.** A marker can no longer stick, in any of the cases:

- **At start, an unreadable marker:** that start still skips the folders, then the marker is dropped.
- **At start, a marker that names no remembered folder:** the marker is dropped and the folders load.
- **A deliberate load clears a marker it didn't make.** This covers Reload, a folder's Reload in the menu,
  Load Scripts… of a new folder, and Load Scripts… of a known folder (through `reload_scripts`).
- **Auto-reload leaves the marker alone** (`deliberate=False`).
- A marker that names a remembered folder still makes the next start skip the folders, as designed.

**R2 (Lumen found it) is closed.** `clicked` passed its `checked` bool as `folders`, so the Reload button raised
in its slot and never reloaded. It is now connected through the `_reload_clicked` slot, and the test clicks the
real button.

**Mutation check.** I reverted each fix in turn on a copy of the tree. Each of these makes a new test fail:

- the slot for the button (R2);
- dropping an unreadable marker;
- dropping a marker that names no remembered folder;
- clearing the marker in `add_folder`;
- clearing the marker on a deliberate reload.

**Two optional notes, not findings:**

1. **`deliberate=False` in `_check_changes` isn't tested end to end.** That is the one mutant that survived: the
   test calls `reload_scripts(..., deliberate=False)` directly. If it is ever lost, an auto-reload also clears a
   marker, which only removes the one-start safety skip.
2. **`_pending_deliberate` can outlive its reload.** Suppose a deliberate reload is waiting and its folder is then
   removed. `_pending_deliberate` stays True, so the next auto-reload counts as deliberate and clears a marker.
   The effect is the same harmless one. Resetting the flag in `_stop_waiting` when nothing is pending would tidy
   it.

## Follow-up: the reload-wait test race (2026-11-03)

This covers the test-only diff `git diff 8861de9..74b79b3 -- tests` and the repro
`repro_reload_wait_race.py`.

**Verdict: the fix is correct and the cause is right. No finding is open.**

**The cause is confirmed.** The Ground CI rerun (run 41463943327, job 125340069131) failed at
`tests/test_live_scripts.py:206`, `assert (0 == 1)`, which is `len(instance.runner.in_flight()) == 1`. The old
test waited for `in_flight()`, which counts a job from when it is queued. The failing sequence was:

1. The job was still queued when `reload_scripts()` cancelled it (`hold_for_reload`).
2. `_busy` still saw the queued job, so the button read "Reload (waiting)" and that assertion passed.
3. The worker then picked the job up and ended it as cancelled without computing, so `in_flight()` was empty at
   line 206.

That is correct product behaviour: no `compute` ran, so there was nothing to wait for. The flaw was in the test.

**The repro reproduces it.** I ran the repro in a copy of each tree:

- with the old tests (`8861de9`), `test_a_reload_waits…` fails with the same `assert (0 == 1)`;
- with the new tests (`74b79b3`), the module passes (22 passed).

Under the repro, the old L2 test (`test_removing_the_folder_a_reload_waits_for_ends_the_wait`) still passes,
because it has no `in_flight` count assertion. Its change is preventive, and right.

One small inaccuracy in the repro: its docstring names `'Reload' == 'Reload (waiting)'` as the failure, but the
failure observed both in CI and locally is line 206.

**The tests still prove that a reload waits for a running compute.** They now wait for the compute's own
`STARTED` event, so the compute is on the worker and blocked on `GATE`, ignoring cancellation, before
`reload_scripts()`. Rewriting the helper for the new code creates fresh events, but the running compute keeps the
old module's `GATE`, which the test holds.

I mutated the code and ran the two tests against each change:

| Mutation | Result |
|---|---|
| `_busy` returns 0 | caught by both tests |
| `in_flight` never records the job's script | caught by both tests |
| `in_flight` drops a job once its compute starts | caught by both tests |
| the hold removed | caught by the first test |

The third mutation is the case the old wait didn't distinguish, and the new tests catch it.

**Under load,** with 16 busy-loop processes (load average about 100) and `-n 12 --reruns 5 --reruns-delay 1`, I
ran each of the two tests 40 times:

| Tests | Result |
|---|---|
| New (`74b79b3`), two runs | 200 passed, **no RERUN** |
| Old (`8861de9`), the same harness | **1 RERUN** in one run |

So the old tests' flake reproduces under load, and the new tests don't flake.
