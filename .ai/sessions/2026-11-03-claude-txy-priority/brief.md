# Brief: TXY priority lists and the External label (`agent/txy-priority`)

Coordinator: CoCo, 2026-11-03. Tony (Chat, via Side, 2026-11-03): "shall we merge v4 to v0.0.8 and implement the
features described in aeed904?", and "you are the dev computer (M4M)". Block 53 is decided: **Q53.1** (MATLAB's TXY is labelled "External (MATLAB
converter)"), **Q53.2** (a TXY choice is any ordered list of HeLab profiles' TXY and External, set globally, per
folder and per plot), and **Q53.3** (in v0.0.8, before the PR to `main`). The plan is
[`roadmaps/txy-priority.md`](../../../roadmaps/txy-priority.md). One Worker; one Reviewer at landing.

**Areas:** this floor owns the TXY choice end to end: `convert` (the source model), `io` (loads, Live and convert
on read), `cache` (the folder rows and identities), `plots` (each plot's TXY row) and `app` (Settings, the
right-click dialog, Folder details). The only other floor is Caching v2, which is idle until the PR, so nothing
beside you owns these paths.

## Read first

- `AGENTS.md`, above all the I/O, cache and UI rules.
- `roadmaps/txy-priority.md`, every part of it; its design notes are proposals, so propose where you differ.
- `helab/utils/txy_sources.py`, the four modes and `identity_source`.
- `.ai/architecture/converter.md` (TXY sources), `cache-store.md` (the store-v4 section: `txy_source_prefs`,
  views, TXY layers, convert on read) and `plots-and-scripts.md` (`txy_source.py`, the Keep box from Q14.2).
- Q45.2, Q50.1 (a), Q50.5–Q50.8, Q50.11 and Q53.x in `.ai/DECISIONS_TODO.md`, under "Recently decided" and block 53.

## Base and branch

Branch `agent/txy-priority`, base `dcc02d8` (`dev/v0.0.8`: the switch-on landed `92f9d1a`, its docs `dcc02d8`).
**store-v4 is on by default.** store-v3 is still reachable through the hidden `store_v4=false` fallback (V-2): it has the global
`txy_source` setting and no per-folder TXY rows (`set_txy_source_pref` needs store-v4), so the list must work
under both stores.

## Objective (in this order; commit each separately; stop and report to CoCo at each ◆)

1. **Design note** (`design.md` in your session folder):
   - the list's type and its text form in settings, folder rows, presets and saved-result keys;
   - the **identity rule**: the four old modes' lists keep their identities exactly (the two priority modes
     share ""), so existing caches, store-v4 views and layers, presets and saved results stay valid; any other
     list gets its own identity;
   - migration: the `txy_source` settings row and store-v4's `txy_source_prefs` (source + tag) read as lists;
     an added column or table goes through `store_v4.migrate`, never only `SCHEMA`; old presets and
     arrangements still open;
   - the per-shot choice: the first entry with a usable TXY; a damaged or still-changing text is never used
     (Q50.5);
   - **convert on read under a general list**, extending Q50.1 (a), so that a HeLab entry never costs a shot an
     earlier entry's TXY. Propose the rule as **Q~1**;
   - Live and Auto-convert when the conversion profile isn't in the folder's list (what Live's line says), as
     **Q~2**;
   - the UI: one list control for all three levels, and short summaries such as "m23v1 › m19v1 › External";
   - the tests.

   ◆ **Send the design to CoCo before code:** `maestri ask "CoCo" "TXY priority: design at <hash>"`.
2. **Q53.1, the label:** "External (MATLAB converter)" wherever the UI names MATLAB's TXY (sources' labels and
   short names, Settings › TXY converter, right-click › TXY for this folder…, plots' TXY rows, Folder details,
   tooltips). Change labels only. File names, tags and HeLab's `matlab-2019`/`matlab-2023-lab-edit` profiles
   keep their names.
3. **The model:** lists in `txy_sources.py`, the identity rule, the per-shot choice in loads (`io_ops/loading.py`,
   `helab_txy.py`, `txy_cache.py`), Live (`io_ops/live.py`, `save_held.py`), convert on read, and the
   store-v4 folder rows with their migration. Then the global setting, folder rows and presets migrate.
4. **The UI at three levels:** Settings › TXY converter (in place of "Tabs and Live read"); right-click › TXY
   for this folder… (with "As Settings"; the folder only, not its subfolders, as Q50.11); each plot's TXY row
   (with "As the tab"; the Keep box still saves it). Every control has an accessible name and an ID.
   Folder details and tooltips name the list in short.
5. **Integration check**, in a temp store with store-v4 on, plus one run under the store-v3 fallback:
   - a folder with External, two HeLab profiles and raw-only shots, loaded under a three-entry list, where
     each shot comes from the right entry;
   - the four old modes giving the same identities and data as before;
   - a plot's own list beside the tab's;
   - a restart that keeps the folder's list;
   - an old preset that still opens.
6. **Docs proposals** in the handoff (`converter.md`, `cache-store.md`, `plots-and-scripts.md`, `settings.md`,
   the plan's status), with provisional `Q~` and `M~` items (M~ for Tony's look at the dialog).

## Rules

Owned paths:
- `helab/utils/txy_sources.py`;
- `helab/io_ops/{loading,helab_txy,txy_cache,live,save_held}.py`;
- `helab/utils/folder_cache.py` (the TXY choice only);
- `helab/utils/cache_store.py` and `store_v4.py` (`txy_source_prefs` and its migration only);
- `helab/views/{ConverterTab,FolderExplorer,FolderDetailsPanel,explorer_live}.py` (the TXY parts);
- `helab/views/plots/txy_source.py`, `instance.py`;
- `helab/analysis/{dataset_view,presets,results}.py` (the choice's identity);
- the settings row in `settings_defaults.py`;
- their tests.

Ask CoCo before any other file.

- Strict typing, including `--platform win32` and `pyright --pythonplatform Windows`.
- Tests never touch real data.
- Before the handoff: the full suite (`-n` with `--reruns 5 --reruns-delay 1`) and the five type checks, with
  every RERUN reported.
- Docs go only in `.ai/sessions/2026-11-03-claude-txy-priority/`.
- Push at checkpoints only. Before reporting a CI run, read every Tests and Converter backends job's log for
  RERUN.
- No version bump, release, tag or PR.
- Never turn the store-v4 switch off by default.

When done: `maestri ask "CoCo" "TXY priority: done at <hash>, suite <N> passed, RERUNs <…>, CI <run>"`.
