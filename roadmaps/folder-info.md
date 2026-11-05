# Folder info window

Horizon: v0.0.9 (proposed, Q64.10). Added: 2026-11-05, from Tony in Chat during a live run (LR-5,
`.ai/sessions/2026-11-05-claude-live-run/`, relayed by Side; block 64). **Status:** planned; Q64.1–Q64.10 open.
Priority and completion: [overview](_readme.md). Related: [cache-store](../.ai/architecture/cache-store.md),
[data-roots](../.ai/architecture/data-roots.md), [converter](../.ai/architecture/converter.md),
[app-runtime-and-ui](../.ai/architecture/app-runtime-and-ui.md), the [Activity window](activity-window.md) (the
nearest precedent).

## Purpose

One place that says everything HeLab holds and knows about one folder. Today it is spread over the folder row's
tooltip, Folder details, the right-click menu's dialogs and Settings › Cache and Data roots, and some of it
(which plot results are saved, which TXY layers by tag, which data is the only copy) isn't shown anywhere for a
single folder.

## Decided (Tony, 2026-11-05, LR-5)

- **Opened from** right-click › Folder info…, a button in Folder details, and the File menu (for when the folder
  explorer is hidden).
- **Read only**, filled by **one store helper job**.
- **Sections:**
  1. the store's contents for the folder: raw pulses, TXY layers by tag, sizes, ages, and which are the only copy;
  2. saved plot results by script, with their settings, dates and sizes;
  3. the folder's flags: Don't cache, Don't auto-load, Convert beside;
  4. its TXY list and cache policy;
  5. its constants;
  6. its scan history and failures;
  7. HeLab's converted TXY;
  8. the data root.
- **Each section sits next to the folder's existing actions.**

## Questions for Tony (block 64; also in [DECISIONS_TODO](../.ai/DECISIONS_TODO.md))

- **Q64.1 The Folder details button.** Folder details has no buttons today: it is a grid of one-line rows, and
  its I/O, cache and offer rows are links. Proposed: **a "Folder info…" link at the end of the Disk cache row**
  (no new row; the no-vertical-padding rule). Or: (b) a small ⓘ button beside the folder's name; (c) a row of
  its own.
- **Q64.2 The File menu's folder, and a shortcut.** Proposed: **File › Folder info… acts on the current tab's
  selected folder**, also while the explorer is hidden, and is disabled with none (as Place .helab-root and
  Convert this folder already are, from `aboutToShow`); **⌘I / Ctrl+I** (free today; Finder's Get Info).
- **Q64.3 One window or several.** Proposed: **(a) one window, which shows the folder it was last opened for**
  (its path in the title) and doesn't follow the selection. Or: (b) one window per folder, several open at once
  (to compare folders); (c) one window that follows the selected folder.
- **Q64.4 When it reads.** Proposed: **on open, on Refresh, and after an action started from the window
  finishes**, with "As of HH:MM:SS" in its header; no automatic refresh while Live saves into the folder (Refresh
  says so). A failed read shows the error, never "nothing saved".
- **Q64.5 The actions beside each section.** "Read only" means the window itself never changes anything; its
  buttons **call the folder's existing actions, which ask as they do today**:
  - store: Clear loaded data cache…, Clear raw pulses…;
  - flags: Don't cache and Don't auto-load as the same toggles as the right-click menu; Write TXY beside as in the
    auto-convert menu;
  - TXY list: TXY for this folder…, Cache policy for this folder…;
  - constants: Folder constants…;
  - scan: Retry / Refresh scan;
  - converted TXY: Convert this folder…;
  - data root: Place .helab-root here… (RAM only), or Settings › Data roots selected on the root.

  Proposed: as listed. Or: (b) no buttons in v1, each section naming where its actions are.
- **Q64.6 Clear for saved results and converted TXY.** Today saved results clear per data root (Settings › Data
  roots) or everywhere (Settings › Cache), and converted TXY only everywhere. Proposed: **not in v1**; the two
  sections link to those places, and "Clear this folder's saved results…" / "…converted TXY…" (asking first)
  come later. Or: (b) add both in v1.
- **Q64.7 What a saved result shows.** Proposed: grouped by script (name and version), one line per result: the
  action, its settings in short (all of them in the tooltip), computed and last used dates, size. **Store-v4
  only**: store-v3's results are left out, since v0.0.9 ends store-v3 reads (V-3).
- **Q64.8 "The only copy".** Proposed: raw pulses whose `d*.txt` HeLab last saw gone, and TXY layers whose
  source TXY is gone and that no raw layer can rebuild; shown as counts and sizes with a warning mark and "Only
  copy: the source files are gone" in the tooltip. HeLab learns a file is gone only when it lists the folder,
  so the window says when it last looked.
- **Q64.9 This folder only, and this session.** Proposed: **this folder only** (never recursive, as the status
  rules are), with one line for its subfolders from memory (their derived status); and **a "This session"
  section** from memory: loaded in RAM and its size, Live on or off, plots open on it.
- **Q64.10 When.** Proposed: **v0.0.9, a floor on this Mac**, now (one floor open; the Activity Window floor is
  done and kept).

## Design notes (for the floor; propose, Ground decides)

- **One helper job.** A new `cache_admin` action, `folder_info`, in `helab/io_ops/admin.py` (local lane:
  `cache_admin` is in `LOCAL_OPERATIONS`, so it doesn't wait behind a slow share). It opens the store once and
  reads only the store and HeLab's converted-TXY index, never the source folder, and answers one new event kind
  in `helab/io_ops/events.py` (with `tests/test_helper_events.py`). Existing readers it can use:
  `CacheStore.folder_raw`, `raw_rows`, `txy_layers`, `folder_views`, `read_prefs`, `read_convert_prefs`,
  `read_folder_choices`, `read_constants`, `scan_history.read_history`, `root_usage`, and for converted TXY
  `helab_txy.folders` with `TxyIndex.shots`. New: a per-folder results reader (only `result_counts` exists) and a
  per-folder form of `_txy_groups`' rebuildable / only-copy logic.
- **Memory parts** (no helper): the inherited TXY list and constants (`FolderCache.folder_list`,
  `effective_folder_constants`), the data root (`root_of`, `no_root`), the session's state, and the subfolders'
  derived status.
- **A Qt-free model** (`helab/utils/folder_info.py`, listed in `PURE`) turns the event plus memory into sections
  of one-line rows; the window renders it only (`no_source_io`).
- **The window** (`helab/views/FolderInfoWindow.py`): non-modal, like the Activity window; a header line (path,
  data root, "As of", Refresh, Copy as text), then the sections, each with its actions on its title line;
  one-line rows with detail in tooltips; gaps from `helab/views/gaps.py`; `identify` IDs and accessible names;
  its size remembered (a `settings_defaults` row). The read shows in the Activity window like other admin jobs.
- **Tests:** the action on a temp store seeded with each kind of row (raw layers, TXY layers by tag, gone
  sources, results, flags, a TXY list, constants, a failed scan's history, a converted-TXY index), its error
  answer, the model from fake events, the window from the model, each button through its existing path (fakes),
  `no_source_io`, and the accessible-names walk.

## Not in scope (v1)

- Changing anything from the window except through the folder's existing actions (Q64.5).
- Per-folder Clear of saved results and converted TXY (Q64.6, later).
- Totals over subfolders (Q64.9).
