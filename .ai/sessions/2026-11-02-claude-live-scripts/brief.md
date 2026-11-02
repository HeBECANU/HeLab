# Brief: live scripts, and a plot's TXY choice saved (`agent/live-scripts`)

Coordinator: CoCo, 2026-11-02. Tony (Chat, via Side, 2026-11-02): "yes I need live scripts build in v0.0.8", and
Q14.2/Q23.4 yes: save a plot's TXY source and profile with presets, arrangements and reopened plots, plus a
plot-settings toggle to turn that off. One Worker; one Reviewer at landing. The floor runs overnight.

**Areas:** `plots` (owner); `app` for the Scripts panel and settings rows.

## Read first

`AGENTS.md` (analysis and plots rules: the script contract `helab/scripts/base.py` imports no Qt; compute on the
worker thread, render on the GUI thread; a hook that raises is logged and HeLab goes on; UI rules, IDs);
`.ai/architecture/plots-and-scripts.md`, `settings.md`; `helab/scripts/scripts_manager.py`,
`helab/views/plots/script_tree.py`, `workspace.py`, `instance.py`, `arrangement.py`, `presets.py`, `txy_source.py`;
Q14.2 and Q23.4 in `.ai/DECISIONS_TODO.md`.

## Base and branch

Base `a0bc26d` (`dev/v0.0.8`). Branch `agent/live-scripts`. Beside you: Caching v2 (Vault; the store, loading,
Settings › Cache) and Converter UX (A39.5 + A37.1: share warnings, the parser's stop line, Live line, Folder
details). Neither owns your paths.

## Objective (in this order; commit each separately)

1. **A short design note** (`design.md` in your session folder) for live scripts: how a reload works
   (re-import the script's module and its helper modules from the user's folders, never HeLab's own packages),
   what happens to open plots (rerun on the new code, keeping settings; a script whose class vanished or fails
   to load leaves its plot showing the last result with the error), how errors are shown, what is remembered,
   and tests. Send it to CoCo before code (`maestri ask "CoCo" ...`); CoCo answers within the night.
2. **Live scripts:**
   - a **Reload** button in the Scripts panel, and an optional **auto-reload on save** (a settings row, off by
     default unless the design says otherwise; file watching must not read source folders or touch the data:
     only the user's script folders);
   - **open plots rerun on the new code, keeping their settings** (parameters whose names still exist; say what
     happens to removed or retyped parameters);
   - **remembered script folders** (a settings row: the folders added, restored at start, removable);
   - **load errors shown in the Scripts panel** (one line per failing file, the traceback in the tooltip or a
     details view), never a crash;
   - **helper modules re-imported** (modules a script imports from its own folder), so a change there reloads too.
3. **Q14.2 / Q23.4:** a plot's TXY source and profile are saved with presets, arrangements and reopened plots,
   and restored; a plot-settings toggle ("Keep this plot's TXY choice", on by default unless you propose
   otherwise) turns the saving off for tweaking or exploring; old presets without the field restore "As the
   folder's tab".
4. **Docs proposals** in the handoff (`plots-and-scripts.md`, `settings.md`, a roadmap plan text for live
   scripts), provisional `Q~`/`A~`/`M~` (wording, defaults for Tony).

## Rules

Owned paths: `helab/scripts/scripts_manager.py` (not `base.py`'s contract unless the design shows it must change:
ask), `helab/views/plots/**`, `helab/analysis/` where a rerun or the TXY choice needs it, the settings rows in
`helab/utils/settings_defaults.py`, their tests. Ask CoCo before any other file. Every control named with an ID;
strict typing (incl. `--platform win32`, `pyright --pythonplatform Windows`); tests never touch real data; script
tests use temporary script folders. The full suite (`-n` with `--reruns 5 --reruns-delay 1`) and the five type
checks before the handoff, every RERUN reported. Docs only in `.ai/sessions/2026-11-02-claude-live-scripts/`.
Push at checkpoints only; read every Tests and Converter backends job's log for RERUN before reporting a CI run.
No version bump, release, tag or PR.

When done: `maestri ask "CoCo" "Live Scripts: done at <hash>, suite <N> passed, RERUNs <…>, CI <run>"`.
