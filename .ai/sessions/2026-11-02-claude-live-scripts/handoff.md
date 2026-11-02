# Handoff: Live Scripts and the saved TXY choice (`agent/live-scripts`)

Worker Lumen (claude, Opus 5.5), 2026-11-02, base `a0bc26d`. Design: [design.md](design.md) (`95515e8`), answered
by CoCo the same night: D1 (b), D2 leaves the choice, D3 yes, D4 yes, D5 yes; D6 wording for Tony (Q~1 below);
plus "the watcher only while the toggle is on" and "a reload never runs while a compute of that script is on
the worker thread", both built.

## Commits

| Commit | What |
|---|---|
| `95515e8` | Design note |
| `5eb4225` | `ScriptsManager`: user folders recorded, helper modules reloaded, load errors kept, D1 hash, source-only imports; `runner.in_flight()` |
| `63b0baf` | Scripts panel (Reload, folders menu, auto-reload, error lines) and plots adopting new code |
| `63817b5` | A47.5: the TXY choice in records, the Keep box, reopen (D4) and script presets (D2) |

## Review fixes (Prismo, `review.md`; CoCo 2026-11-03: fix all, each with a test that fails before it)

Commit `a18e4c9`. Every finding fixed; tests in `tests/test_live_scripts.py`, `test_plot_txy_saved.py`,
`test_scripts_reload.py`.

| Finding | Fix | Its test fails before |
|---|---|---|
| M1 a reload reads the folder of a plot waiting on its own TXY choice | `adopt_script` returns without running while `_own_waits` | `test_a_reload_doesnt_count_as_reading_the_folder_for_a_waiting_choice`: fails on `e9fdd6c` |
| M2 no test of the record holding the choice | test only (the code was right) | `test_a_plots_record_holds_the_choice_made_in_its_row`: fails with Prismo's mutation (`txy=None`) |
| M3 user code on the GUI thread at every start | deferred `restore_folders` (200 ms into the event loop), `PlotReopen.restore` waits for `foldersRestored` (and `record` keeps last time's record meanwhile); shares not loaded at start nor watched (`on_network`, mount table only); loading marker `<app folder>/scripts-loading.json`; one-line `scripts_start_note`; skipped folders stay remembered and in the menu | four new tests (deferred plus reopen, marker, share, `on_network`) and the two updated restore tests: all fail on `e9fdd6c`. What is left: Q~3 |
| L1 no test of the hold | test only | the waiting test's new lines: fail with Prismo's mutation (no `_held = True`) |
| L2 "Reload (waiting)" stuck | `_try_reload` and `remove_folder` end the wait when nothing is pending | `test_removing_the_folder_a_reload_waits_for_ends_the_wait`: fails on `e9fdd6c` |
| L3 the source-only hook takes installed packages | `_source_only_finder` refuses `_PROTECTED` | `test_installed_packages_inside_a_script_folder_keep_their_usual_imports`: fails on `e9fdd6c` |
| L4 lazy helpers left out of the D1 hash | a helper seen imported is known (`_know_helpers`, recorded before unloading) and folded; it is watched too | `test_a_helper_imported_only_in_compute_counts_in_the_hash_once_seen`: fails on `e9fdd6c` |
| L5 a reload with nothing changed | stamps per file, plus the load's time: a new helper file not modified since the load is stamped, not a change | `test_a_helper_first_imported_in_a_run_isnt_a_change`: fails on `e9fdd6c` |
| N1 IDs | `identify_buttons(box, "script_error_details")`; `script_auto_reload`, `script_folder_reload`, `script_folder_remove` | in `test_the_menus_actions_and_the_details_window_have_ids_and_submenus_go`: fails on `e9fdd6c` |
| N2 submenus leak | old submenus `deleteLater` on each fill | the same test |
| N3 the fixture leaves the hook | `imports_restored()` also restores `sys.path_hooks`, the cached finders and `_SOURCE_ONLY` | `test_the_import_system_is_restored_after_a_test` checks the helper itself |

How "fails before" was checked: the new test files were copied into a worktree of `e9fdd6c` (with stubs for
the three new names `script_tree` exports): 12 failed, 34 passed. M2 and L1 were checked by putting Prismo's
mutations back: each test then fails.

## Re-check fix (Prismo, `f66a946`: R1)

Commit `c79f210`. **R1** a loading marker could stick (HeLab stopped while Load Scripts… loaded a new folder,
not yet remembered, or the marker unreadable): every later start skipped all remembered folders. Now a start
drops a marker naming no remembered folder (and loads them), skips one start for an unreadable marker and
drops it, and a deliberate Reload (button or a folder's menu) or Load Scripts… ends a marker it didn't make;
auto-reload doesn't (`reload_scripts(…, deliberate=False)`). **R2** (mine, found writing R1's test): the
Reload button was connected straight to `reload_scripts(folders)`, so `clicked`'s `checked=False` came in as
the folders and raised `TypeError`; the button never reloaded (the tests had called `reload_scripts()`
directly). It has its own slot now (`_reload_clicked`); the tests click it and trigger the menu's Reload.
Tests: `test_a_marker_naming_no_remembered_folder_is_dropped_at_start`,
`test_an_unreadable_marker_skips_one_start_only`, `test_a_deliberate_load_clears_a_marker_it_didnt_make`
[reload, menu, load another]: all five fail on `f66a946`. Full suite 8980 passed, 672 skipped, **no RERUN**;
the five type checks clean. CI: CI3_PLACEHOLDER

## What was built

**Reload core** (`helab/scripts/scripts_manager.py`, Qt-free):
- `folders()`, `add_folder`, `reload([folders])`, `remove_folder`, `errors()` (`LoadError(path, message,
  details)`: one line plus traceback), `helper_modules(folder)`, `watched_files`, `stamp`, `folder_of`,
  `class_folder` (weak, across reloads), `loaded_at`.
- A loaded folder is appended to `sys.path` (HeLab's and installed modules keep their names). Its helper
  modules are the `sys.modules` entries whose file is inside it, never `helab.*`, the stdlib or
  site-packages. A reload pops them and re-runs the folder's files, so helpers (packages and lazy imports
  in `compute` included) import fresh.
- **Source-only imports** (`_SourceOnlyLoader`, a `sys.path_hooks` entry limited to the user's folders):
  found while testing. Python checks a `.pyc` by the source's whole-second mtime and its size, so
  `VALUE = 1` → `VALUE = 2` saved within a second reloaded the old code. User folders now never read or
  write `__pycache__`, so HeLab also writes nothing into them.
- A file without scripts that the folder imports, now or before, is a helper, not a failure. A failure's
  warning is logged only once the folder's helpers are known.
- D1: when a folder's files imported helpers, each of its scripts' `file_hash` is
  sha256(file hash + each helper's `relpath:hash`). Bundled analyses keep the plain hash.
- `AnalysisQueue.in_flight()` / `AnalysisRunner.in_flight()`: the scripts of queued or computing jobs (a
  cancelled one until its `compute` returns).

**Scripts panel** (`helab/views/plots/script_tree.py`):
- Row: `Group [▾]  [Load Scripts… ▾]  [Reload]`. Load Scripts… is now a menu button (`QToolButton`,
  same ID `load_scripts`). Its menu: "Script folders", each folder → Reload / Remove from the list; then
  "Reload when a script is saved".
- **Reload** (`reload_scripts`, ID `reload_scripts`): holds the folders' plots (runs cancelled, nothing
  submitted, Live revisions wait), then waits until `in_flight()` has no script of those folders. The
  button reads "Reload (waiting)" until then. It then reloads, and each plot of them takes the new code or
  keeps its old code.
- Loading an already loaded folder again is a reload.
- **Remembered folders**: `script_folders` (JSON list), loaded in the panel's `__init__`, so before
  `PlotReopen.restore`: plots of user scripts reopen at start. A missing folder stays listed with
  "folder not found".
- **Auto-reload**: `script_auto_reload` (default off). A `QFileSystemWatcher` exists only while it is on.
  It watches the script folders, their `.py` files and their helper files and folders, and re-adds paths
  after each change. Events start a 0.75 s settle; then each folder's stamps (path, size, mtime_ns) are
  compared, and only a real change reloads that folder.
- **Load errors**: `⚠ N script files didn't load` (amber) at the tree's end whatever the group, one line
  per file (`live.py: SyntaxError: invalid syntax (live.py, line 1)`). The tooltip holds the path and
  traceback; a double-click opens a non-modal details window (`script_error_details`). Load Scripts… and
  Reload say so on the status bar.

**Open plots** (`helab/views/plots/instance.py`):
- `hold_for_reload`, `adopt_script(metadata, script)`, `keep_script(why)`.
- Adopt captures `saved_plot()`, swaps script, policy and constant keys, and rebuilds the settings page in
  place (`_fill_page` / `_empty_page`: the same page widget, so the Settings panel and a floating plot's
  window need no change). It re-applies the settings through `check_plot` with the new script's file
  hash, so there is no "another copy" note; a version bump still says so. It then reruns and draws anew,
  not through `update`.
- A removed, retyped or new parameter is named in the Presets row: "Reloaded · ⚠ 3 settings at the
  script's defaults: Mode, Extra, scale"; a removed one is named by its key, as presets do already.
- Failure (the file fails, the class or action is gone, the folder was removed, or the new script's
  hooks or parameters raise): the old code and last result stay, with an amber line on the dock and status
  line: "⚠ Script didn't reload (…): still running the code loaded at 14:02". Rerun and Live run the old
  code; the next good reload adopts.

**A47.5** (`helab/analysis/presets.py`, `txy_source.py`, `instance.py`, `presets.py`):
- `TxyChoice(source, profile, tag)`: `SavedPlot.txy` and `txy_keep` (default true), `ScriptPreset.txy`;
  optional JSON fields, `FORMAT` stays 1.
- `check_txy` / `check_plot(…, profiles=)`: a renamed profile is found by its tag, with a note. An unknown
  profile or source is a `Problem`, and the plot stays as the folder's tab. `PresetsInspector` calls
  `check_plot` without profiles, so profiles aren't checked there (A~3).
- The TXY row's second line ends with a **Keep** box (ID `txy_keep`, accessible name "Keep this plot's
  TXY choice", on). Off: records save no choice, and the plot reopens with the box off.
- Reopen: the plot takes its choice while waiting. When its folder's data is found, it loads that choice
  only if HeLab read the folder this session (a listing snapshot, or a dataset checked against it). Else
  it says "Select <folder>, or Rerun, to load HeLab's only (…)". A tab's later load of the folder, or
  Rerun, starts that load (D4).
- Script presets: Save holds the plot's choice (none while Keep is off). Apply switches to it; a preset
  without one leaves the plot's choice as it is (D2).

## Checks

After the review fixes (`a18e4c9`): full suite `pytest -n 4 --reruns 5 --reruns-delay 1
--basetemp=.ai/temp/pytest`: **8975 passed, 672 skipped, 2 warnings, 1 rerun**, 153.8 s. The rerun's reason:
`tests/test_dash_server.py::test_stop_frees_the_port`, `assert 56278 == 56276` (the free-port race, A~6;
unrelated to this change; passed on its rerun). The five type checks are clean. CI: run 41454753537 on `944fbd6`, success; every job read: Tests (1/2) and (2/2) on macOS (4485, 4490 passed), Ubuntu (4482, 4491) and Windows (4468, 4471), Converter backends on all three (849, 849, 847), **0 RERUN** in every log.

Before the review:

- Full suite, `pytest -n 4 --reruns 5 --reruns-delay 1 --basetemp=.ai/temp/pytest`: 8963 passed, 672 skipped (private test data absent), 2 warnings (pyqtgraph NumPy 2.5 deprecation), 160.7 s; **no RERUN** (no "rerun reasons" in the summary).
- `mypy helab/ --strict`, `mypy tests --strict`, `pyright helab tests`, `mypy helab/ --strict --platform
  win32`, `pyright --pythonplatform Windows helab tests`: all clean (203 / 194 files, 0 errors).
- New tests: `tests/test_scripts_reload.py` (10), `tests/test_live_scripts.py` (8),
  `tests/test_plot_txy_saved.py` (16), all with temporary script folders and in-memory datasets.
- CI: run 41448691912 on `2617cfa`, success; every job read: Tests (1/2) and (2/2) on macOS (4480, 4483 passed), Ubuntu (4477, 4483) and Windows (4463, 4464), Converter backends on all three (849, 849, 847 passed), **0 RERUN** in every log.

## Proposed doc changes (for the Coordinator)

**`.ai/architecture/plots-and-scripts.md`**, Script system paragraph, after "and any folder loaded with
Load Scripts…":

> Live scripts (v0.0.8): the folders loaded with Load Scripts… are remembered (`script_folders`) and loaded
> again at start (`TreePanelWidget.restore_folders`, `RESTORE_DELAY_MS` 200 after the event loop starts, so
> after the window shows; `PlotReopen.restore` waits for `foldersRestored`). Not at start: a folder on a
> network share (`on_network`, from the mount table only; never watched either), and none when
> `<app folder>/scripts-loading.json` is there (written before each folder load, removed after: a load
> that never ended). Those wait for Reload, said in one amber line (`scripts_start_note`), and stay
> remembered; Load Scripts…'s menu lists them (Reload, Remove from the list) and
> turns on "Reload when a script is saved" (`script_auto_reload`, off; only then a `QFileSystemWatcher`
> watches the script folders and their helper files, 0.75 s settle, reloads a folder only when a `.py`
> stamp changed). `ScriptsManager` keeps each user folder on `sys.path` (appended) while loaded; its
> **helper modules** are the `sys.modules` entries with a file inside it (never `helab.*`, the stdlib or
> site-packages), unloaded on each reload so they import fresh; user folders import from source only
> (`_SourceOnlyLoader`: no `__pycache__` read or written, since a `.pyc` is checked by whole-second mtime
> and size); a folder's scripts record their file's hash folded with its helpers' (D1). Failures are kept
> (`errors()`, with tracebacks) and listed at the Scripts tree's end. **Reload** holds the folders' plots,
> waits until no run of their scripts is queued or computing (`AnalysisRunner.in_flight`: a reload never
> runs under a `compute`), then each plot takes the new code in place (`AnalysisInstance.adopt_script`:
> settings page rebuilt, settings re-applied through `check_plot`, rerun drawn anew) or keeps its old code
> and last result with an amber line (`keep_script`: Rerun and Live go on with it). Bundled analyses are
> never reloaded.

**Presets and reopening** paragraph, after "holding every parameter and the library (not the Live group)":
"and the plot's TXY choice (`TxyChoice`: source, profile name and tag), unless the TXY row's Keep box
("Keep this plot's TXY choice", on by default) is off"; after the arrangement's "Live group and places":
"its TXY choice and Keep". Add: "A saved choice is checked like a setting (`check_txy`: a renamed profile
is found by its tag; an unknown one or an unknown source is named and the plot stays as the folder's tab).
A reopened plot with its own choice loads it once its data is found only if HeLab read the folder this
session (listed, or loaded or checked), else it waits for a select of the folder or Rerun, so reopening
never reads a folder by itself (D4); a reload of its script (auto-reload too) doesn't count as a read
either. A script preset without a choice leaves a plot's choice as it is (D2);
records without one restore as the folder's tab."

In the **Dataset analyses** paragraph, the TXY row: "each plot's settings have a TXY row (with Keep)".

**`.ai/architecture/settings.md`**, a new paragraph:

> **Script rows** (Live scripts): `script_folders` (a JSON list of the folders added with Load Scripts…,
> loaded at start; removed only by Remove from the list) and `script_auto_reload` (bool, default off:
> Reload when a script is saved, in Load Scripts…'s menu).

**`roadmaps/` plan text** (a new `roadmaps/live-scripts.md`, or a section of the overview):

> # Live scripts (v0.0.8; Tony 2026-11-02: "yes I need live scripts build in v0.0.8")
> Built on `agent/live-scripts` (design: `.ai/sessions/2026-11-02-claude-live-scripts/design.md`).
> - [x] Reload button; auto-reload on save (off by default, watches only the script folders, only while on)
> - [x] Open plots rerun on the new code keeping settings that still fit (removed, retyped and new ones
>   named); a script that fails to reload leaves its plot on the old code, amber
> - [x] Remembered script folders, restored at start before plots reopen, removable
> - [x] Load errors in the Scripts panel (one line per file, traceback in tooltip and details window)
> - [x] Helper modules re-imported (D1: their hashes in the scripts' identity)
> - [ ] Tony's manual check (M~1, M~2), wording (Q~1)
> - [x] At start: remembered folders load after the window shows; a share's waits for Reload; a load that
>   never ended (the loading marker) skips them at the next start (review M3)
> - Later: A~1 to A~4, A~6; Q~3.

`AGENTS.md`, optional one line under Analysis and plots: "A reload of the user's scripts never runs while
a `compute` of them is on the worker thread (`AnalysisRunner.in_flight`), and never touches HeLab's
bundled analyses or the interpreter's modules."

## For Tony and later (provisional IDs)

- **Q~1 Wording** (D6, proposed as built): "Reload" (waiting: "Reload (waiting)"), "Load Scripts…" with
  its menu "Script folders" / "Reload" / "Remove from the list" / "Reload when a script is saved", "⚠ N
  script files didn't load", "⚠ Script didn't reload (…): still running the code loaded at HH:MM",
  "Reloaded · ⚠ N settings at the script's defaults: …". The TXY row's box reads **"Keep"** (its
  accessible name and tooltip say "Keep this plot's TXY choice"), because the full text on that line
  would widen the Settings panel (Q33.2). Proposed: keep "Keep".
- **Q~2** A choice not applied on reopen is said as "⚠ 1 setting at the script's defaults: TXY profile";
  for TXY "at the script's defaults" means "as the folder's tab". Proposed: fine as is; else a TXY-specific
  wording.
- **M~1** Auto-reload with real editors (VS Code, PyCharm, vim's rename-on-save) on macOS and Windows: one
  reload per save, plots rerun, nothing reloads while auto-reload is off. On Windows, check that a watched
  script folder can still be renamed or deleted in Explorer while auto-reload is on (`QFileSystemWatcher`
  on Windows may hold directory handles).
- **M~2** A lab session: a Live plot of a user script, edited mid-run with a typo, then fixed. The plot
  keeps following on the old code with the amber line, then takes the fixed code.
- **A~1** The Presets row's "changed" dots and "Save N changes" don't count a TXY choice changed from the
  applied preset.
- **A~2** Two script folders with a same-named helper share the first one imported (Python's one module
  namespace). Detect it and name it in the error list.
- **A~3** `PresetsInspector` (`helab/views/PresetsInspector.py`, not owned) calls `check_plot` without
  `profiles`, so it doesn't name a preset's unknown TXY profile. Pass `{name: file_tag(p)}` from
  `txy_source.known_profiles()`.
- **A~4** The `reopen_plots_at_start` row's description could name the TXY rule ("a plot with its own TXY
  choice loads it only once HeLab read its folder this session").
- **A~5** (done in the review fixes, M3: remembered folders load after the window shows, never from a
  share, and a loading marker skips them after a load that never ended.)
- **A~6** `tests/test_dash_server.py::test_stop_frees_the_port` reran once in the review-fix suite
  (`assert 56278 == 56276`): `free_port()` picks a port and the server binds it later, and another process
  (other floors' suites ran on this Mac at the same time) took it in between, so the server fell back to
  the next free port. Not in `roadmaps/known-issues.md` now (earlier sessions noted it: 2026-10-20,
  2026-10-21, 2026-10-22). Proposed entry: "[ ] `test_dash_server.py::test_stop_frees_the_port`: the port
  `free_port()` returns can be taken before `DashServer.start()` binds it when suites run at once (rerun
  on the Live Scripts floor, 2026-11-03). Fix: bind and hand the open socket over, or retry with a new
  port when `start()` returns another." (`tests/test_dash_server.py` isn't this floor's to change.)
- **Q~3** (M3's rest) The remembered **local** folders still import their scripts on the GUI thread, now after
  the window shows. A script that blocks at import (`input()`, a network call) still freezes that session,
  as Load Scripts… always could, and the marker makes the next start skip the folders, so HeLab always gets
  a start that works. A folder the mount table calls local but that is slow (an iCloud, Dropbox or OneDrive
  folder whose files are placeholders) is loaded too. Importing scripts off the GUI thread would remove the
  freeze, but I don't think it is safe: scripts define Qt and PyQtGraph classes at import, and imports hold
  Python's import lock against the GUI thread's own imports. Proposed: keep it as built (the marker as the
  way out), and add the cloud-folder kinds to the "not at start" rule only if Tony sees it happen.

## Not done

Reloading HeLab's bundled analyses (out of scope by the brief); no version bump, release, tag or PR.
