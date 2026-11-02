# Design: live scripts, and a plot's TXY choice saved

Worker (claude, Opus 5.5), floor `agent/live-scripts`, base `a0bc26d`, 2026-11-02. For CoCo before code.
Questions are numbered **D1–D6** at the end, each with a proposed answer; I build the proposals unless told
otherwise.

## 1. Reloading a folder's scripts (`ScriptsManager`)

Today `load_directory` imports each `*.py` of a folder as `helab.scripts.dynamic.<file>` (not put in
`sys.modules`), with the folder **not** on `sys.path`, so `import helpers` from a script fails unless
the user arranged it. Changes (all in `helab/scripts/scripts_manager.py`, Qt-free; `base.py` unchanged):

- **User folders are recorded** (`folders()`, in the order added). `load_directory(folder)` loads or
  reloads one; `reload()` reloads every recorded folder; `remove_directory(folder)` drops its scripts,
  errors and helper modules. HeLab's bundled modules (`load_module`) are never reloaded or purged.
- **Helper modules.** While a folder's files run, the folder is at the front of `sys.path`, and it stays
  there while the folder is loaded, so a lazy `import helpers` inside `compute` (worker thread) works
  too. A **helper module** of a folder is any `sys.modules` entry whose `__file__` is inside that folder,
  found by scanning `sys.modules` at reload time (so lazy imports count), **except**: names `helab` or
  `helab.*`, anything under HeLab's package folder, and anything under the interpreter's stdlib or
  site-packages (`sysconfig` paths), so a script folder that happens to contain a venv or HeLab's own
  checkout never unloads them. A reload pops those entries (and their submodules), calls
  `importlib.invalidate_caches()`, then runs the folder's files again: the helpers import fresh from
  disk. Removing a folder also takes it off `sys.path`.
- **Errors are kept, not only logged:** `errors()` maps each failing file (or a missing folder) to a
  `LoadError(path, message, traceback)`: syntax errors, exceptions and `SystemExit` at import, no
  script class, abstract-only classes, bad metadata. A reload clears a folder's errors first.
- **Script ids stay** `<file>::<qualname>`, so a reloaded class has the id it had.

## 2. The Scripts panel (`helab/views/plots/script_tree.py`)

One row, as today, that shrinks with the panel (Q33.2):
`Group: [▾]  [Load Scripts… ▾]  [Reload]`

- **Load Scripts…** opens the folder chooser as today. Its menu arrow (a `QToolButton`,
  `MenuButtonPopup`) lists the remembered folders, each with **Remove from the list** (asks nothing: the
  folder and its files are untouched; its plots keep their last result, see §3), then
  **Reload when a script is saved** (checkable: auto-reload).
- **Reload** (ID `reload_scripts`, "Reload scripts", tooltip "Import the loaded folders' scripts and
  their helper modules again; open plots of them rerun on the new code") reloads every folder; disabled
  when no folder is loaded.
- **Load errors**: the tree ends with `⚠ N script files didn't load` (amber, expanded) whatever group is
  selected, one child per failing file: `name.py: SyntaxError: invalid syntax (line 12)`; the tooltip
  holds the traceback; double-click opens a read-only details window with the traceback (copyable). No
  error, no item. A reload with errors also says so on the status bar (`workspace.notice`), one line.
- **Remembered folders**: new settings row `script_folders` (str: a JSON list of paths, like
  `live_launch_folders`; default ""). A folder is added on Load Scripts… and removed only by Remove from
  the list. At start the panel loads them (in its `__init__`, so before `PlotReopen.restore`: plots of
  user scripts reopen at start once their folder is remembered). A remembered folder that isn't there
  is an error line ("folder not found"), kept in the list.
- **Auto-reload**: settings row `script_auto_reload` (bool, default **off**, as the brief says). On, a
  `QFileSystemWatcher` watches the remembered folders and their `.py` files (re-adding files after an
  editor's replace-on-save); any event starts a 0.75 s debounce, then the folder's `.py` files are statted
  (name, size, mtime_ns) and compared with the last load: only a real change reloads, and only that
  folder. Only the user's script folders are watched; nothing touches source folders, helpers or the
  store.

## 3. Open plots on a reload (`AnalysisInstance`, `instance.py`)

After a folder reloads, each open plot whose script came from it (its `script_id`'s file is in the
folder) is matched to the reloaded scripts by **analysis id and action** (as `find_script` does):

- **Found:** `adopt_script(metadata, script)`: cancel a run in flight (old code), drop what the old
  script kept for the plot (`plot_closed(action, owner, path)`), capture the plot as an arrangement
  records it (`saved_plot()`: parameters, library, Live group, TXY choice), rebuild its settings page
  from the new script's parameters in place (the page swaps in the Settings panel or the floating
  window; the dock, its place, number and title stay; the title follows a renamed script), apply the
  captured settings through `check_plot` (the existing preset/reopen check), and **rerun**, drawn anew
  (`render`, not the old widget's `update`). So a parameter whose name and type still fit keeps its
  value; a **removed** one is dropped, a **new** one starts at its default, a **retyped** one (or a
  value outside new limits, a removed choice) starts at its default; each is named in the Presets row's
  note, "Reloaded · ⚠ 2 settings at the script's defaults: Bins, Mode" (tooltip: every reason), as
  reopening does. A plot still waiting (reopened) keeps waiting; a released one reloads on the new code
  when shown, as today.
- **Gone or failing:** a file that now fails to load, or whose class or action vanished, leaves the plot
  **showing its last result and running its old code** (the old class object stays in memory), with an
  amber status line: "⚠ Script didn't reload (SyntaxError: … line 12): still running the code loaded at
  14:02" (tooltip: traceback). Live follows on with the old code: a typo saved during a run must not
  stop a Live plot (D3). The next successful reload adopts the new code. A folder removed from the list
  leaves its plots the same way ("its folder was removed from the Scripts list").
- Only plots of reloaded folders rerun; bundled analyses' plots never do.

## 4. A plot's TXY choice saved (Q14.2 = Q23.4, A47.5)

- **Format** (`helab/analysis/presets.py`, still `FORMAT = 1`: optional fields, old records read as
  before): `SavedPlot` and `ScriptPreset` gain `txy_source` ("" = as the folder's tab, or one of
  `txy_sources.SOURCES`), `txy_profile` (a profile's name, "" = the conversion profile's) and
  `txy_profile_tag` (its file tag, to find it again if renamed), and `SavedPlot` gains `txy_keep`
  (bool, default true). A record without them: as the folder's tab, keep on.
- **Check**: `check_plot` returns the TXY choice to apply, or a `Problem` ("TXY: saved “x” is no
  longer a source"; "TXY profile: “p22-edit” (tag p22e1) isn't known now"); not applied means as the
  tab, named in the note like any setting.
- **The toggle**: a checkbox in the plot's TXY row, **"Keep this plot's TXY choice"** (ID `txy_keep`),
  on by default. On: the plot's arrangement record (reopen at start, arrangement presets) and the script
  presets saved from it hold its TXY choice. Off: they hold none (a reopened plot starts as the tab) and
  the record holds `txy_keep: false`, so the plot reopens with the box still off. It only governs
  saving: choosing a source still works as today.
- **Restoring**: a reopened plot or one opened by an arrangement preset starts with its saved choice
  (its TXY row shows it). Applying a script preset with a TXY choice switches the plot to it (an edit
  like any other, which loads that choice's data as choosing it in the row does); one without the field
  leaves an open plot's choice as it is (D2).
- **A reopened plot with its own choice** must still never read its folder by itself (the
  `reopen_plots_at_start` row: "never reading the folder itself"), and its own choice's dataset is RAM
  only (`no_cache`), so the disk cache can't bring it. It waits as today (`FolderWait`); when its folder's
  data shows, it loads its own choice **only if the folder was read by a load this session** (the tab's
  load of it, or an arrangement preset's deliberate load), else it says "Select the folder, or Rerun, to
  load HeLab's only (p22v1)". Rerun always loads (deliberate). (D4)

## 5. What is remembered

QSettings: `script_folders` (JSON list) and `script_auto_reload` (bool), two new rows in
`settings_defaults.py`. Arrangement records and script presets: the TXY fields above. Nothing else
(the selected group, the error list and file stats are session only).

## 6. Tests (temporary script folders only; no real data)

- `tests/test_scripts_reload.py` (Qt-free): reload picks up an edited script and an edited helper (in a
  subpackage too); a deleted file's script goes; errors keep message and traceback (syntax, raise,
  `SystemExit`, none found); HeLab's and stdlib modules are never purged even from a folder holding a
  copy; two folders with same-named helpers; remove takes the folder off `sys.path`.
- Panel (qtbot): Reload button state and ID; error item lines, tooltip and details window; folders
  remembered, restored, a missing one shown and kept, removed; auto-reload toggle saved; the debounced
  check reloads only on a real `.py` change (called directly, not waiting on file events).
- Plots: a plot of a temp script reruns on the edited code keeping a still-valid value, with a removed,
  a retyped and a new parameter named; a vanished class and a syntax error keep the last result, the
  amber line and the old code (Rerun still works); the dock and number stay.
- TXY: record round trip with and without the fields; check problems; `saved_plot` with the toggle on
  and off; reopen restores the choice and the toggle; script preset with and without the field; the
  reopened plot's no-folder-read rule (a recorded submit spy, as the existing reopen tests do).
- Existing suites (`test_scripts_folder`, `test_script_system`, `test_presets_*`, the converter tab's
  TXY tests) stay green; `test_accessible_names` covers the new controls.

## Questions (proposed answers in bold)

- **D1 Helper changes and the result identity.** `ScriptMetadata.file_hash` is the script file's
  SHA-256; a change in a helper module doesn't change it, so saved-result reuse (R2, off by default) and
  "saved from another copy" notes can't see it. Options: (a) leave it and file it in known-issues; (b)
  for scripts of user folders whose folder imported helper modules, record
  sha256(file hash + each helper's path and hash) instead. **(b)**, set by the manager, `base.py`
  unchanged; bundled analyses keep the plain file hash. (It is conservative: any helper of the folder
  counts for every script of it.)
- **D2 A script preset without the TXY field, applied to an open plot:** **leaves the plot's choice as
  it is** (the preset says nothing about it); the brief's "restore As the folder's tab" applies to
  arrangements and reopened plots, which start fresh.
- **D3 A plot whose script fails to reload keeps running its old code** (Live included), amber, until a
  reload succeeds. **Yes** (alternative: disable Rerun and stop following Live).
- **D4 A reopened plot with its own TXY choice** loads it only once its folder was read by a load this
  session, else waits for a select or Rerun. **Yes** (alternative: load it from the folder at once,
  which breaks the reopen row's "never reading the folder itself").
- **D5 Auto-reload default off**, its control in the Scripts panel's Load Scripts… menu (not in the
  Settings dialog, which other floors are editing tonight). **Yes.**
- **D6 Wording**: "Reload", "Reload when a script is saved", "Remove from the list", "Keep this plot's
  TXY choice", "⚠ N script files didn't load". For Tony in the handoff (Q~).
