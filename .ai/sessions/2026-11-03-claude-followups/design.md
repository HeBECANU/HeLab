# Design: Q49.3 (b), the try-import of a script folder

Worker: Mend (Claude Opus 5.5), Follow-ups floor, 2026-11-03. For CoCo's ◆ before code.

## What it is

Before HeLab imports a user script folder on the GUI thread, a **probe process** imports the same folder
the same way (`ScriptsManager().add_folder(folder)`, so the same `sys.path`, helper modules, source-only
loader and per-file error handling) and says it finished. Only then does the GUI import it for real.
A folder whose probe doesn't finish within the time limit, or whose probe dies, isn't imported: it is
listed in the Scripts panel's errors with the reason, its scripts leave the panel, its open plots keep the
code they have (`keep_script`), and it stays remembered (Reload tries it again).

A file that **raises** at import (or calls `sys.exit`) isn't a probe failure: the manager catches it per
file in the probe as in the GUI, so the probe finishes and the real import lists that file's error as
today. Only a hang or a crash (segfault, `os._exit`, a killed interpreter) skips the folder.

## The probe's entry (`helab/scripts/probe.py`, new; owned)

- `main(argv)`: `probe.py FOLDER RESPONSE_FILE`. Imports `helab.scripts.scripts_manager` (Qt-free, ~90 ms,
  no `helab.utils.constants`), writes `{"kind": "ready"}` as one JSON line to the response file, runs
  `ScriptsManager().add_folder(folder)`, writes `{"kind": "done", "loaded": bool, "seconds": float}`, flushes
  and exits 0 through `os._exit(0)` (so a script's atexit hook or a non-daemon thread it started can't
  hold the probe open after the answer).
- **Source runs:** `[sys.executable, "-m", "helab.scripts.probe", FOLDER, RESPONSE]`, `PYTHONPATH` as
  `IOService` sets it (the package root first).
- **The frozen app:** `[sys.executable, "--helab-script-probe", FOLDER, RESPONSE]`, dispatched in
  `helab/main.py` right after the `--helab-io-helper` block (after `freeze_support()`, before the `convert`
  dispatch and every GUI, cache or Dash import), as AGENTS.md requires. `HeLab.spec` would need
  `"helab.scripts.probe"` in `hiddenimports` only if PyInstaller can't see the import from `main.py`'s
  dispatch; it's a plain `from helab.scripts.probe import main`, so it can. (`HeLab.spec` is owned only
  for the manual's build: I won't touch it for this unless CoCo says so.)
- **Its streams:** stdin a pipe the GUI never writes nor closes, so `input()` at import blocks in the probe
  as it would in a terminal-launched HeLab and hits the time limit, instead of passing on EOF.
  stdout/stderr go to files in the probe's private temp folder (a script's prints don't fill a pipe; the
  stderr tail goes in the log and the error's details when it crashes). The answer travels in the
  response file, never stdout, because windowed frozen executables may have no standard streams (as the
  frozen I/O helper does).
- **No QApplication in the probe.** Scripts define Qt and PyQtGraph classes at import, which needs no
  application object; a script that *makes a widget* at import would abort the probe ("Must construct a
  QApplication") and be skipped though the GUI could load it. I propose accepting that (rare, bad practice,
  and the message says what happened); the alternative, an offscreen `QApplication` in the probe, costs
  ~0.2 s per folder and relies on the `offscreen` platform plugin being bundled in the frozen app. See P3.
- Environment: the GUI's, plus nothing new; the `HELAB_*_OVERRIDE` variables pass through, so a probe
  in a test or on a floor uses its private folders. The probe opens no settings, store or cache.

## The protocol and the GUI side (`helab/views/plots/script_tree.py`; owned)

- One probe per folder, a `QProcess` owned by the panel (asynchronous: `finished` / `errorOccurred`
  signals and a `QTimer`, no thread, no waiting). At most `PROBES_AT_ONCE = 2` at a time; the rest queue.
- A 100 ms `QTimer` reads the response file's new lines while a probe runs (a small local temp file, not a
  source folder; the timer runs only while probes do).
- **The time limit** counts from the probe's `ready` line, so the probe's own start (Python, NumPy,
  SciPy; seconds in a cold frozen app on a lab PC) doesn't count against the folder. A probe that isn't
  ready within `PROBE_START_SECONDS = 60` is a failure too ("HeLab's test import didn't start").
- **Outcomes:**
  - `done` → the GUI imports the folder now (`_load_folder`, unchanged, marker and all).
  - no `done` within the limit → `QProcess.kill()`; the folder is skipped: "didn't load: its import didn't
    finish within 10 s".
  - the probe exits without `done` → skipped: "didn't load: its import stopped HeLab's test import (exit
    code N)" (a signal: "(killed by signal N)"); the stderr tail in the error's details.
  - the probe can't start (`FailedToStart`) → **imported anyway**, logged: a missing interpreter must not
    stop every script folder from loading (the marker is still the backstop). See P4.
- **A probe holds its folder until its exit is confirmed** (`finished`), as a helper holds its slot: a
  reload asked meanwhile waits for it, and a second probe of a folder never runs beside the one it replaces
  (a killed probe's `finished` comes asynchronously; nothing on the GUI thread waits for it).
- **The skip** goes through `ScriptsManager` (owned): a new `skip_folder(directory, message, details)` that
  records the folder (as `add_folder` does for "folder not found"), clears its scripts and errors and puts
  one `LoadError(folder, message, details)`, so the panel's existing error list shows it at the tree's end
  ("⚠ 1 script file didn't load" → the row "<folder>: didn't load: its import didn't finish within 10 s").
- **On quit:** the panel's close kills running probes (`kill()`, no wait); their temp folders are removed
  when each `finished` arrives, or left for the OS temp cleaner if HeLab quits first.

## Start, reload and Load Scripts…

- **Start** (`restore_folders`): unchanged choice of folders (not on a share; none after a marker). The
  chosen folders are probed; those that pass load in the remembered order once every probe has answered
  (not each as it answers), then `_refresh`, the note and
  `foldersRestored` as now. So `PlotReopen.restore` still runs once, after every folder is settled, and
  the order of folders on `sys.path` stays the remembered order. Skipped ones join `_skipped` and the start
  note ("⚠ 1 script folder not loaded at start (its import didn't finish within 10 s): Reload to load it").
- **Reload** (button, folder menu, auto-reload on save): `reload_scripts` holds the plots and waits for
  runs as now; `_try_reload` then probes the pending folders instead of loading at once; the Reload
  button reads "Reload (checking)" with the tooltip "Test-importing N script folders in a separate
  process first". When every probe has answered: the folders that passed load, the skipped ones are
  recorded, then `_adopt` (the skipped folders' plots keep their code with the reason), `plotsChanged`
  and the notice as now ("Reloaded 2 script folders · ⚠ 1 didn't load: its import didn't finish within
  10 s"). Folders asked for while probes run join `_pending` and get their own round after.
- **Load Scripts…** of a new folder: probed too (it is an import of a script folder; the brief's "every
  reload" plus this keeps one path). See P2.
- Plots stay held through the probe: no run of the folder's scripts starts while it is tested.

## The time limit

`PROBE_SECONDS = 10.0` as a module constant in `script_tree.py`, measured from `ready`. A settings row
(`script_probe_seconds`, 2–120 s, Settings › General) needs `helab/utils/settings_defaults.py` and the
settings tab, both outside the brief's owned paths: see P1.

## The double import

The manual's script page (`docs/how-to/write-a-script.md`) gets one line: "HeLab first imports a
script folder in a separate test process (to catch a script that hangs or crashes at import), then
imports it for real: code at a script's top level runs twice, so keep it to definitions." The probe's
side effects are the script's own (a file it writes at import is written twice).

## The loading marker: kept

The probe can't catch everything: a file changed between the probe and the import (an editor saving
mid-reload), code that behaves differently in the GUI process (it checks `QApplication.instance()`,
touches a widget, or deadlocks only against the GUI thread's import lock), or a probe that couldn't start.
The marker costs one small file write per folder load and remains the way out of a start that freezes;
nothing about it changes.

## Tests (new `tests/test_script_probe.py`; existing `tests/test_scripts_folder.py` / live-scripts tests kept)

1. The probe module run as `python -m helab.scripts.probe` on a temp folder: a good folder answers
   `ready` then `done` (`loaded: true`); a file that raises answers `done` (the error isn't the probe's);
   a missing folder answers `done`, `loaded: false`.
2. The panel with a short limit (`PROBE_SECONDS` patched to ~1 s): a folder whose script sleeps at import
   is skipped with "didn't finish within 1 s", a good folder beside it loads, `foldersRestored` fires once
   after both, the start note names it; its probe was killed and its `finished` arrived (no zombie).
3. A folder whose script calls `os._exit(3)` at import: skipped, "exit code 3".
4. A script calling `input()` at import: skipped by the limit (the probe's stdin stays open).
5. Reload: a plot of a folder whose file is edited to hang keeps its old code and says why; fixing the
   file and reloading adopts the new code. A reload asked while a probe runs waits for it (one probe per
   folder at a time), then runs its own round.
6. `FailedToStart` (the command patched to a missing program): the folder imports anyway, logged.
7. The frozen dispatch: `helab/main.py` run with `--helab-script-probe FOLDER RESPONSE` in a subprocess
   (source tree, `sys.frozen` unset; the dispatch doesn't depend on it) answers and imports no PyQt6
   (checked from the probe: `"PyQt6" not in sys.modules` at `ready`, written in the `ready` line).
8. The probe imports no Qt (`helab.scripts.probe` added to `PURE` in `tests/test_headless_imports.py`,
   outside the owned paths: P5).

Existing tests that load folders through the panel (restore, reload, auto-reload) will see the probe:
they get a real probe (a subprocess per folder, ~0.3 s), or a conftest-free fixture that patches the
probe to answer at once for tests not about it. I'd use the real probe where cheap and the patch
elsewhere, to keep the suite's time.

## Questions for CoCo

- **P1** The time limit as a constant (10 s, from `ready`) for now, a settings row later? A row needs
  `settings_defaults.py` and Settings › General (not owned).
- **P2** Probe Load Scripts… of a new folder too? Proposed yes.
- **P3** No QApplication in the probe (a script making a widget at import is skipped), or an offscreen one?
  Proposed: none.
- **P4** A probe that can't start: import anyway (logged), as proposed, or skip?
- **P5** May I add `helab.scripts.probe` to `PURE` in `tests/test_headless_imports.py`, and is
  `HeLab.spec` left alone (no hiddenimport needed)?
