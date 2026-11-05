# Handoff: the Folder info window (`agent/folder-info`)

Worker (Claude, Opus 5.5), 2026-11-05. Brief: [brief.md](brief.md); design: [design.md](design.md) (CoCo's go:
C~1, C~2, C~3, C~5 yes; Q~2 (c); Q~1, Q~3, Q~4, Q~5 as proposed, with Tony in Chat). Base `6140924` on
`dev/v0.0.9`.

## Commits

| Commit | What |
|---|---|
| `e72c4a4` | Design (step 1) |
| `5c0a979` | The helper's read, its readers and its event (step 2) |
| `e14e380` | The model, the window and the ways in (step 3) |
| `4dd31db` | Live on/off reach the window; HelabMainWindow's partial-fake tests keep working (step 4) |
| `88b6656` | Settings › Data roots… selects the folder's root (`DataRootsTab.select_root`, CoCo's go) |
| `2d708e0` | The manual's page (`docs/how-to/folder-info.md`) |
| `0f09f06` | Handoff |
| (next) | Times Windows can't show read "unknown" (CI 41998150471's Windows failures) |

Not pushed by me: `github.com` doesn't resolve from this Mac (nor from Ground); CoCo pushes from Ground.

## What it does

- **The read** (`cache_admin` "folder_info", local lane, offline too): `helab/io_ops/folder_info.py` opens the
  store once (the admin job's opener, trusting only verified volume hints, as `constants` does) and reads
  `CacheStore.folder_contents(path)`, one read transaction: the raw layer's totals and only copies, each TXY layer
  with Make room's group, views, a stage 1 seed, store-v4's results (newest 200 by `last_used`, records decoded
  for the script and settings; a record that won't decode is kept as "record unreadable"), flags, converter
  flags, choices, constants, scan history, last basic scan and saved listing. Then each base's
  `converted-txy/index.sqlite`, read only (`open_index(write=False)`, `TxyIndex.shots`). Never the source folder
  (tests trace `os` calls). Each part is `found`, `missing`, `error` or `skipped`; no root → `no_root`, an
  unverified drive → `unverified`, store-v3 → its store-v4 parts skipped; the store failing to read fails the job.
  Bounds: no per-shot data, 200 results, 32 layers and views, settings texts 160 / 2,000 characters (a 240-result
  folder's event is under 600 kB; usually a few kB).
- **Make room's rule** is `cache_store.layer_group`, used by `_txy_groups` and the reader (C~1); a test checks
  `_txy_groups` against the rule as it was, inline, on a seeded store.
- **The model** (`helab/utils/folder_info.py`, `PURE`): `build(event, Memory, now, error=, reading=)` → header +
  This session, Disk cache, Saved plot results, Flags, TXY list and cache policy, Constants, Scan history, HeLab's
  converted TXY (Q~5), each with its actions by ID. The data root is in the header (Q~3). Only copies come first,
  amber, "HeLab last looked <time>" (the newest `gone_at` of those rows or the saved listing's time). "Nothing
  cached" only from parts the read found empty; a failed read keeps the last good lines, greyed ("stale"), and
  says why. Flags, choices and constants are memory's (what HeLab applies), the store's saved row in the tooltip,
  and "(not saved yet)" in amber when they differ. `Reads`: one read in flight, a newer ask replaces the queued
  one, a retarget drops the old answer.
- **The window** (`helab/views/FolderInfoWindow.py`): one, made at startup hidden (as Activity is: so
  `test_settings_defaults`' real-window test sees its size row read), retargeted by `show_folder(path, tab)`,
  title "Folder info — <path>" (Q~1) and `setWindowFilePath`. Actions go through the tab it was opened from (else
  the current tab); the window changes nothing itself. Reads on open, Refresh, and after an action at the
  folder's next change (`folderPrefsChanged`, `constantsChanged`, `dataRootsChanged`, `scanHistoryChanged`,
  `diskCacheChanged`, `cacheRemoved`, `saveEnded`, other admin jobs' `cacheAdminDone`; armed 10 min). While Live
  watches the folder (any tab): `datasetChanged` → This session only (500 ms coalesced), `saveEnded` saved or
  superseded → a read; each tab's `liveChanged` updates the header. Long sections show 3 lines and a link; the
  detail pane opens to the right and widens the window (clamped to the screen), × gives the width back. The
  sections scroll; the window is clamped to its screen at first show. Size: `folder_info_window_size`
  ("620,560"), saved on hide without the pane. Section buttons are flat tool buttons (push buttons padded every
  title line; CoCo: fine).
- **The ways in:** right-click › Folder info… after Copy Pathname (C~2; `FolderExplorer.folderInfoRequested`);
  Folder details' "Folder info…" link (`details_folder_info`) in a third grid column of the Disk cache row, the
  other rows spanning it, shown with the row (Q~4); File › Folder info… with `Ctrl+I` (⌘I), enabled on
  `aboutToShow`, tab changes and selection changes.
- **Q~2 (c):** no per-folder Clear raw pulses; the Disk cache and results sections link to Settings › Cache and
  Settings › Data roots (the folder's root selected: `DataRootsTab.select_root(uuid)`, now or once its list is
  read; `show_settings_dialog(root=)`).
- `LiveController.set_write_beside` (C~3): a public name over the existing asked path, for the Flags toggle.

## Checks

- **After the Windows fix:** full suite 9490 passed, 673 skipped, **no reruns**; five type checks clean. CI
  41998150471 (`4dd31db`) was red on Windows Tests (1/3) and (2/3) from `when()`'s `OSError: [Errno 22]` on the
  tests' small timestamps (fixed in the commit after `0f09f06`); its "RuntimeError: bad rev 1" is
  `test_live_plots`' deliberate fake failure (that test passed).

- Full suite (`pytest -n 8 --reruns 5 --reruns-delay 1 --basetemp=.ai/temp/pytest`) at `2d708e0`: **9489 passed,
  673 skipped, 1 rerun**: `tests/test_convert_helab.py::test_a_killed_helpers_workers_exit` ("AssertionError: the
  pool started"; also 2 reruns at `4dd31db`; unrelated, known-issues entry proposed below).
- The five type checks: clean (`.ai/temp/types-handoff.txt`).
- `ruff check` and `mkdocs build --strict -d .ai/temp/site`: clean (the docs lock installed in this floor's venv
  only).
- New tests: `tests/test_folder_info_helper.py` (11), `tests/test_folder_info_model.py` (16),
  `tests/test_folder_info_window.py` (12). Lists touched: `test_headless_imports.py` (PURE),
  `test_accessible_names.py` (a "folder info" case with its detail pane open). `test_helper_events.py` passes
  unchanged (the kind is in `events.KINDS` and the union; the app matches it in `FolderCache._on_admin_event`).
- Looked at: the window rendered to a PNG with a fake read (all sections fit at 640×640 with tool buttons; the
  detail pane widens it).

## Proposed doc changes (for CoCo)

**`.ai/architecture/app-runtime-and-ui.md`**, a new paragraph under UI:

> **Folder info** (Q64.1–Q64.10; `helab/views/FolderInfoWindow.py`, model `helab/utils/folder_info.py`, Qt-free in
> `PURE`): one window, made at startup hidden and retargeted on each open (`show_folder(path, tab)`; title
> "Folder info — <path>"), from right-click › Folder info…, Folder details' "Folder info…" link at the end of the
> Disk cache row (its own grid column; the other rows span it; shown with the row) and File › Folder info…
> (`Ctrl+I`, enabled on `aboutToShow`, tab and selection changes). One read fills it: `FolderCache.folder_info`
> → `cache_admin` "folder_info" (local lane) → `folderInfoRead(owner, event)`, the job's end on
> `cacheAdminDone`; `folder_info.Reads` keeps one read in flight (a newer ask replaces the queued one; a retarget
> drops the old answer). It reads on open, Refresh, and after an action started from it at the folder's next
> change (armed 10 min); while Live watches the folder, `datasetChanged` re-renders This session and `saveEnded`
> (saved, superseded) reads again. Memory parts (`FolderInfoSources.memory`): the data root, flags, the TXY list
> and policy in effect, inherited constants, the session's scan history, the subfolders' derived status, This
> session (RAM, Live, plots on it, newest shot). Its buttons call the tab's existing actions (no Clear of its own:
> Settings › Cache and Data roots, the latter with the root selected, `DataRootsTab.select_root`). Long sections
> open a detail pane to the right, widening the window; the sections scroll; the window is clamped to its screen;
> size `folder_info_window_size`. "Nothing cached" only from a part the read found empty; a failed read keeps the
> last good lines greyed and names the error.

**`.ai/architecture/cache-store.md`**, at the end of store-v4's TXY layers bullets:

> - **Folder info's read** (`CacheStore.folder_contents`, `helab/io_ops/folder_info.py`, admin `folder_info`): one
>   folder's rows in one read transaction (raw totals and only copies, layers with `layer_group`, views, seed,
>   store-v4's own results, flags, choices, constants, history, summary, listing) and the converted-TXY indexes
>   read only; event `folder_info` (bounded: no per-shot data, 200 results, 32 layers and views). Make room's
>   per-layer rule is `cache_store.layer_group`, shared by `_txy_groups`: [app-runtime-and-ui](app-runtime-and-ui.md).

**`.ai/architecture/settings.md`**: the row `folder_info_window_size` (str, "620,560"; as Activity's).

**`.ai/architecture/io-and-browsing.md`**, where `ADMIN_ACTIONS` is named: add `folder_info` (read only; trusts
only verified volume hints, as `constants`).

**`AGENTS.md`** (one line, the code map's `helab/views/` row): after `ActivityWindow.py (…)`, add
"`FolderInfoWindow.py` (File › Folder info…: one folder's cache, results, flags and choices; model
`helab/utils/folder_info.py`)". No new invariant.

**`roadmaps/folder-info.md`**: status → built on `agent/folder-info` (commits above); the Decided sections stand;
CoCo's Q~ answers (below) under them; Q~2 (c) means "Clear raw pulses…" per folder joins Later with Q64.6 (b).

**`roadmaps/known-issues.md`**, a new entry:

> - **`tests/test_convert_helab.py::test_a_killed_helpers_workers_exit` RERUN** (`AssertionError: the pool
>   started`): under `-n 8` the converting helper's pool workers weren't yet visible to `psutil` when its first
>   `shot_converted` arrived (2 reruns, `agent/folder-info` at `4dd31db`, 2026-11-05; passed on rerun). Unrelated
>   to that branch. Likely fix: wait briefly (bounded) for the children before asserting, or have the helper report
>   its pool's pids.

## Questions and follow-ups (provisional IDs)

Decided by CoCo with Tony in Chat (record them): **Q~1** title "Folder info — <path>"; **Q~2** (c) no per-folder
Clear raw pulses in v1, links to Settings; **Q~3** the data root in the header; **Q~4** Folder details' link
hidden with the Disk cache row; **Q~5** section order as built.

- **Q~6 Per-folder "Clear raw pulses…"** (from Q~2). `remove_raw(paths)` removes the folder's only copies too.
  Options: (a) a question naming the size and the only copies (S4~1's paragraph); (b) keep only copies (a new
  `remove_raw` option: a store write path); (c) leave it to Settings. **Proposed:** (a), with Q64.6 (b)'s
  per-folder Clears, in one follow-up.
- **A~1 Activity's name for the read.** A Folder info read shows in Activity's Cache upkeep under the admin
  action's name; give it a label ("Folder info read") and leave successful ones out of History
  (`activity.NOT_KEPT_WHEN_OK`: Live's saves make one each while the window is open).
- **A~2 Raw pulses after a Live save.** `raw_fill` runs after a save, so the window's raw pulses lag one save; read
  again on `raw_fill_done` of the watched folder too (bounded by `Reads`).
- **A~3 Opening the store.** The read uses the admin opener, which makes the store folder when it isn't there (as
  every admin job does). A read-only open for `folder_info` (as `helab cache --folder` does) would make the window
  never create a store; small, but it touches `stores._cache_store`.
- **A~4 Large raw folders.** `folder_contents` parses every TXY layer's entries (for the shot range and the
  rebuildable check): fine at thousands of shots; time it on the largest real folder (with M~1) and move the range
  into SQL if needed.
- **M~1 Try the window on a real screen** (Tony): a real data folder with cached data, saved results, a TXY list
  and constants; a folder with only copies (a raw file moved away, then Retry / Refresh: the mark and "last looked",
  then moved back); a RAM-only folder (Place .helab-root here…); the detail pane on a long results list; the
  window's height on the laptop screen; ⌘I with the folder panel hidden; and with Live on the folder: This session
  following each shot and a read after each save (every N shots and on stop).
- **M~2 Windows:** Ctrl+I, the fonts (the title lines' buttons on Windows' wider fonts), and the detail pane at
  1366-pixel-wide screens.
