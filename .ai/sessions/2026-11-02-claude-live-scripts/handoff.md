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

- Full suite, `pytest -n 4 --reruns 5 --reruns-delay 1 --basetemp=.ai/temp/pytest`: 8963 passed, 672 skipped (private test data absent), 2 warnings (pyqtgraph NumPy 2.5 deprecation), 160.7 s; **no RERUN** (no "rerun reasons" in the summary).
- `mypy helab/ --strict`, `mypy tests --strict`, `pyright helab tests`, `mypy helab/ --strict --platform
  win32`, `pyright --pythonplatform Windows helab tests`: all clean (203 / 194 files, 0 errors).
- New tests: `tests/test_scripts_reload.py` (10), `tests/test_live_scripts.py` (8),
  `tests/test_plot_txy_saved.py` (16), all with temporary script folders and in-memory datasets.
- CI: CI_PLACEHOLDER

## Proposed doc changes (for the Coordinator)

**`.ai/architecture/plots-and-scripts.md`**, Script system paragraph, after "and any folder loaded with
Load Scripts…":

> Live scripts (v0.0.8): the folders loaded with Load Scripts… are remembered (`script_folders`) and loaded
> again at start, before plots reopen; Load Scripts…'s menu lists them (Reload, Remove from the list) and
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
never reads a folder by itself (D4). A script preset without a choice leaves a plot's choice as it is (D2);
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
> - Later: A~1 to A~5.

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
- **A~5** Remembered folders load on the GUI thread at start, as Load Scripts… always has; a folder on an
  unreachable share could stall startup. Check it off the GUI thread first (a stat with a timeout), or
  load script folders after the window shows.

## Not done

Reloading HeLab's bundled analyses (out of scope by the brief); no version bump, release, tag or PR.
