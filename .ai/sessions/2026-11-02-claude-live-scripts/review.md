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
