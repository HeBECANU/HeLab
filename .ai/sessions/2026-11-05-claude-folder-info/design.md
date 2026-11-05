# Design: the Folder info window (`agent/folder-info`)

Worker (Claude, Opus 5.5), 2026-11-05. Step 1 of the [brief](brief.md); no code yet. The spec is
`roadmaps/folder-info.md`'s two Decided sections (Q64.1–Q64.10). Everything below that isn't Tony's is a
proposal; questions for Tony are `Q~n` at the end, questions for CoCo (files outside the owned paths) `C~n`.

Checked against the code at `6140924`: the readers named in the brief exist where it says
(`cache_store.py` :1478, :1531, :1609, :2806, :2835, :3104, :3488, :3530, :3830, :3937, :3952, :3994),
`ADMIN_ACTIONS` and `folder_choice` (`admin.py` :23, :275), `AdminResultFields` (`events.py` :93),
`FolderCache.cache_admin` (:3546) and `_on_admin_event` (:3954), `show_context_menu` (`FolderExplorer.py`
:2269), Folder details' Disk cache row (`FolderDetailsPanel.py` :350) and the File menu (`HelabMainWindow.py`
:423–466).

## 1. The helper job

### The action

One new `cache_admin` action, **`folder_info`**, in `ADMIN_ACTIONS` (`helab/io_ops/admin.py`). `cache_admin` is
already a local-lane operation and in `IOService.OFFLINE_OPERATIONS`, so the read never waits behind a slow share
and works while offline. `FolderCache.cache_admin` submits it with `priority=True`, like every admin job.

- **Params:** `path` (the folder), `verified_volumes` (`FolderCache.verified_volumes()`, as `constants` and
  `convert_prefs` send: the local lane then trusts only hints verified this session, so a swapped disk at the
  same mount never shows another disk's cache), and `temps` (the temp folder, as `inventory` sends, for the
  converted-TXY index there).
- **Opens the store once** through `stores._cache_store(root, local_lane=True, verified_volumes=…, offline=…)`,
  as every admin action does, and reads everything in **one read transaction** (`store.transaction(write=False)`),
  so the sections agree with each other.
- **Reads only the store and HeLab's converted-TXY index** (`<cache|temp>/converted-txy/index.sqlite`), never
  the source folder: no `stat`, `scandir` or open of `path` or anything under it. (The index's own folder is
  HeLab's, but the job doesn't list it either: sizes come from the index rows. "As recorded" in the tooltip.)
- **No data root:** `store._path_key(path)` raises `NoDataRoot` → the answer is a normal `folder_info` event with
  `root_state: "no_root"` and no store parts (the model says RAM only). `VolumeUnverified` →
  `root_state: "unverified"` ("This drive isn't verified yet this session; Refresh once it is"). Neither is
  an error and neither says "nothing saved".
- **store-v3** (the hidden `store_v4=false` fallback): `layout: 3`; flags, constants, scan history and the
  converted TXY are read as in v4 (those tables exist in v3); the store and results parts are
  `status: "skipped"` and the model says "Shown for store-v4 only" (Q64.7: store-v3's results are left out).
- **Errors:** the store failing to open or its read transaction failing raises `StoreError` → the helper's
  usual `error` event (the job fails as a whole). A part that fails on its own (a damaged results record, a
  layer row that won't parse, an index that's damaged or busy) is that part's `{"status": "error", "error": …}`;
  the other parts still arrive. Every part is `found`, `missing` (nothing of that kind is saved: only said when
  the read succeeded), `error` or `skipped`.
- The event ends with the usual `admin_result` (store id, next deadline, usage) so `_on_admin_event`'s
  housekeeping (sweep deadline, usage) runs as for every admin job.

### The new readers (read only)

In `helab/utils/cache_store.py` (allowed: read-only readers):

- **`CacheStore.folder_contents(path, *, max_results) -> FolderContents`**: one `transaction(write=False)` that
  reads the folder's store-v4 rows by its key and returns a frozen dataclass of `Read`s:
  - `raw`: count, bytes, the shot range, earliest and latest `saved_at`, latest `last_used`, the newest
    `seen_at`, and the only copies (`gone_at IS NOT NULL`): count, bytes, earliest and latest `gone_at`.
    One `SELECT … GROUP BY` (no per-shot rows), like `folder_raw` but with the dates.
  - `layers`: one entry per TXY layer (`txy_layers` + `txy_segments` bytes): layer, tags, shots, rows,
    bytes, precision, `saved_at`, `last_used`, `seen_at`, `gone_at`, and its **group** (below).
  - `views`: `(source, tag, last_used)` per view (`folder_views`' query).
  - `seed`: store-v4's own `datasets` row's bytes, if any (stage 1's seed).
  - `results`: the folder's count and bytes (`_folder_results`' query, store-v4 rows only: no store-v3
    read-through, Q64.7, and Keep's read-through ends in v0.0.9 anyway), and the newest `max_results` rows by
    `last_used` (`result_id`, `analysis_id`, `action`, `record`, `bytes`, `computed_at`, `saved_at`,
    `last_used`). The record's JSON is returned as text; decoding is the job's (below).
  - `prefs`, `convert_prefs`, `choices`, `constants`, `history`, `summary` (the last basic scan's record),
    `listing_at` (the saved listing's `listed_at`) through the existing readers' queries (`read_prefs`,
    `read_convert_prefs`, `read_folder_choices`, `read_constants`, `read_records("histories" | "summaries" |
    "listings")`), called inside the same transaction (they nest: `transaction` counts depth).
- **The per-folder form of the only-copy logic.** `_txy_groups` (Make room's planner, store-wide) classifies each
  layer as `rebuildable` (a HeLab layer whose every entry is raw-keyed and whose raw row is held with the same
  fingerprint), `seen` or `only` (`gone_at` set). I'd move that classification into one private function,
  `_layer_group(layer, entries, gone_at, held) -> "rebuildable" | "seen" | "only"`, which both `_txy_groups` and
  `folder_contents` call, so the window can never disagree with what Make room would do. Behaviour of
  `_txy_groups` unchanged (Make room's tests pin it). **C~1** asks CoCo whether that refactor is in bounds, or
  whether I should duplicate the rule in the reader with a test that pins the two together.

In the job (a new module **`helab/io_ops/folder_info.py`**, standard library + the store and index readers,
never imports `helab.io_helper`; `admin.py` calls `folder_info.read(store, path, params, send)` from its new
branch):

- **Results:** each record is decoded with `result_cache.result_from(record, None)` (no arrays: the record holds
  none) for the script's identity (`analysis_id`, `version`, `file_name`) and its parameters. A record that
  won't decode keeps its row with `settings: ""` and `damaged: true` (shown as "record unreadable", never left
  out). Parameters become a **short text** (`name=value` pairs, values through `repr`, at most 160 characters,
  "…" after) and a **full text** for the tooltip (one per line, at most 2,000 characters).
- **Converted TXY:** `helab_txy.folders(path, options, key)` names the candidate folders (the cache base by key,
  the temp base by key and by path). For each base with an index (`open_index(root, write=False)`, read only;
  missing → that base is `missing`; unreadable, busy or of a newer schema → `error` with SQLite's words):
  `TxyIndex.shots(folder)` grouped by `(profile_tag, output)` into count, bytes (`txy_size`), the profile's
  name and version, the newest `converted_at`, plus the folder row's `last_used`. A new read-only
  `TxyIndex.folder_summary(folder)` (`provenance.py`, allowed: read only) can do the grouping in SQL so no
  per-shot rows cross into Python for a big folder; I'll use `shots()` first and add it only if a timing test on
  10,000 rows says so.

### The event: `folder_info` (`events.py`, `FolderInfoEvent`)

Kind `folder_info`, then `admin_result` as usual. Fields (all JSON; per-shot data never sent: only counts,
ranges and dates):

```
kind: "folder_info"
path: str                  # as asked (the GUI matches it with the window's target)
key: str                   # the folder's root:// key ("" without one)
root_state: "rooted" | "no_root" | "unverified"
layout: int                # 3 or 4
read_at: float             # when the read transaction ran (this computer's clock)
store: str                 # its store_id (FolderCache.store_answer)
parts: dict[str, FolderInfoPart]   # every part's status: found | missing | error | skipped, and error text
raw: FolderRawField        # shots, bytes, first, last, saved_first, saved_last, last_used, seen_at,
                           #   only_copy, only_copy_bytes, gone_first, gone_last
layers: list[FolderLayerField]     # layer, tags, shots, rows, bytes, precision, saved_at, last_used,
                                   #   seen_at, gone_at, group  (at most 32: more is "N more")
views: list[FolderViewField]       # source, tag, last_used (at most 32)
seed_bytes: int
results: FolderResultsInfo # count, bytes, rows (at most 200, newest used first), more (rows left out)
                           #   row: result_id, analysis_id, version, file_name, action, settings,
                           #        settings_full, bytes, computed_at, saved_at, last_used, damaged
prefs / convert_prefs / choices / constants: dict | None   # as their admin events carry them
history: dict | None       # the ScanHistory record (already bounded: HISTORY_LIMIT = 10 failures)
summary: dict | None       # the last basic scan's record: status, counts, scanned_at
listing_at: float | None   # when HeLab last listed the folder (its saved listing)
converted: list[FolderConvertedBase]  # per base (cache, temp): status, error, last_used,
                                      #   tags: [{tag, profile, version, output, shots, bytes, newest}]
```

**Size bound:** about 200 results × (160 + 2,000) characters plus 32 layers and 32 views is under 0.5 MB in the
worst case and a few kB usually; nothing grows with the number of shots. `tests/test_helper_events.py` gets the
kind through `KINDS` and the union, and a test sends a folder with 300 results and 20,000 raw rows and checks
the event's encoded size.

## 2. The model: `helab/utils/folder_info.py` (Qt-free, in `PURE`)

Pure functions and frozen dataclasses; imports `number_format`, `time_format`, `txy_sources` and
`scan_history`'s pure parts, no Qt, no `helab.utils.constants` (checked: `tests/test_headless_imports.py`).

- `Row(text, tooltip="", warn=False)`: one line. `Action(id, label, tooltip, enabled=True, checked=None)`:
  a button on a section's title line (`checked` for the flag toggles).
- `Section(id, title, rows, actions, detail=(), detail_title="")`: `rows` are the few lines shown in the
  window; `detail` the full list for the side pane (empty when everything fits in `rows`).
- `Info(path, title, header: tuple[Row, ...], sections, as_of, error, live)`.
- `Memory`: what the window gathers from memory (`FolderCache` and the tab, no disk), as plain values:
  the data root (`root_of`: folder, uuid, label), `no_root` and `pending_root`, the flags (`folder_prefs`),
  `write_beside`, the folder's own choices and the list a load reads (`folder_choices`, `folder_list`, with
  whether it's the folder's own or Settings'), the policy in effect, the constants in effect
  (`effective_folder_constants`, and for each value the folder that set it: `inherited_constants`), why
  they're session-only (`constants_session_only`), the session's scan history (`scan_history`), the
  subfolders' derived status (`subtree`), and **This session**: loaded (shots, RAM bytes, TXY source) or not,
  a pending save's question, Live on/off for this folder in any tab and Auto-convert, the plots open on it
  (titles), the newest shot (number and when its file was written, from the dataset's `raw_times` or
  fingerprint).
- `build(event: FolderInfoEvent | None, memory: Memory, now: float, *, error: str = "",
  script_names: Mapping[str, str] = {}) -> Info` and `as_text(info) -> str` (Copy as text).
  `script_names` maps `analysis_id` to the plot's name from the loaded scripts (memory), else the ID.

**What comes from where.** The store read is the truth for what HeLab *holds*; memory for what *applies now*:

| Part | Source |
|---|---|
| Header: path, data root, RAM only | memory (`root_of`, `no_root`, `pending_root`), with the read's key in the tooltip |
| This session, the subfolders line, the newest shot | memory only |
| Disk cache (raw pulses, TXY layers, only copies, saved loads) | the read |
| Saved plot results | the read (names from memory) |
| Flags | memory (what HeLab acts on), the read's saved row in the tooltip; if they differ, an amber "not saved yet" note |
| TXY list and cache policy | memory (`folder_list`: the folder's own or inherited from Settings), the read's saved choice in the tooltip |
| Constants | memory (in effect, each with where it was set), the read's own row in the tooltip; session-only says why |
| Scan history | the read (saved), and memory's session history when it is newer (its `revision`) |
| Converted TXY | the read (the index) |

Before the first answer the store parts say "Reading…"; a failed read keeps the last good parts, greyed, with
the error in the header (below). **No part ever says "nothing saved" unless its status is `missing` from a read
that succeeded.**

## 3. Refresh (Q64.4)

A small pure state machine in `folder_info.py`, `Reads`, so its rules are tested without Qt:
`ask(path) -> submit?`, `answered(owner, path) -> apply?`, `failed(owner)`. The window drives it.

- **At most one read in flight.** Asking while one runs marks one more as queued (a newer ask replaces the
  queued one, never a second queue); when the running one answers, the queued one is submitted.
- **Retargeting** (the window opened for another folder) sets the target at once; an answer for the old path is
  dropped, and the new path's read is queued behind the running one (or submitted if none runs).
- **When it reads:** on open (every `show_folder`, even for the same folder), on Refresh, and **after an action
  started from the window**: clicking an action arms "read after the folder's next change"; the first of
  `FolderCache`'s signals naming this folder (`folderPrefsChanged`, `constantsChanged`, `cacheRemoved`,
  `dataRootsChanged`, `scanHistoryChanged`, `diskCacheChanged`, `saveEnded`, `cacheAdminDone`) then asks for a
  read, coalesced 300 ms. The arm lasts 10 minutes (a dialog left open) and ends on retarget. Nothing else
  reads by itself, except during Live.
- **While Live watches the folder** (any tab's `live_control.live` on this path; `ActivityWindow.watching(explorer, path)`'s
  rule): `FolderCache.datasetChanged(path)` (a Live check that brought shots) rebuilds the memory parts only,
  coalesced 500 ms; `saveEnded(path, "saved" | "superseded")` (Live's autosave, every N shots and on stop) asks
  for a store read through `Reads`. The header says "Live: refreshes by itself". `raw_fill` runs after a save,
  so raw pulses show at the next save's read, or Refresh (said in Refresh's tooltip).
- **"As of HH:MM:SS"**: the read's `read_at`, local time. While a read runs, "Reading…" beside it; Refresh stays
  enabled (it queues one).
- **The error state:** an `error` or `cancelled` answer (or the job not queued: the queue full, the cache off)
  shows an amber header line, "Couldn't read the disk cache: <message>", and keeps the last good parts greyed
  with their own As of; with no earlier read, the store sections say "Not read: see above" rather than any count.
- **The GUI never waits:** submit, then return; answers arrive on a signal. `FolderCache.folder_info(path) ->
  str` (the owner, "" if not queued) submits the admin job; a new signal **`folderInfoRead = pyqtSignal(str,
  object)`** (owner, event) carries the `folder_info` event and the job's `error`/`cancelled`
  (`cacheAdminResult` has no owner, so it can't tell two windows' reads, or a stale one, apart). Requests are
  deduplicated by `IOService.submit`'s key and bounded by `Reads`.

## 4. The window (Q64.3, Q64.7): `helab/views/FolderInfoWindow.py`

- **One window**, created lazily by the main window, non-modal (`Qt.WindowType.Window`, parent the main window,
  like the Activity window), **retargeted on each open**: `show_folder(path, explorer)`. Title
  "Folder info — <path>" (Q~1), and on macOS `setWindowFilePath(path)` (the title bar's proxy icon). The tab it
  was opened from is kept as a weak reference: its actions go through that tab (a closed tab's actions fall
  back to the current tab; none → actions disabled, "Open the folder in a tab first").
- **Header** (one line each, no padding): the path (`ElidedLabel`, middle-elided, full in its tooltip); the data
  root ("⚓ <label> · <marker path>", or "RAM only: no .helab-root here or above" with **Place .helab-root
  here…**, or "Waiting for Same folder or Copy" with **Review…**); "As of 14:02:31" with **Refresh** and **Copy
  as text** on the same line, and "Live: refreshes by itself" when it does; the amber error line when the last
  read failed.
- **Sections**, top to bottom in a `QScrollArea`: each a bold title with its actions on the same line (small
  flat buttons, right of the title: `COLUMN_GAP` apart), then its one-line rows (`ElidedLabel`, tooltips carry
  the detail). Gaps from `helab/views/gaps.py` (`ROW_SPACING`, `LABEL_GAP`, `COLUMN_GAP`); no vertical margins
  around blocks.
- **It grows sideways, not tall.** A section shows at most 4 rows; a longer one (saved results; layers or the
  history when many) shows 3 and a link row "All 37 saved results ›". Clicking it opens the **detail pane** to
  the right (a `QTreeWidget`, one row per item, columns for the item's parts, tooltips with the rest; its
  title and a close ×), and the window widens by the pane's width, up to the screen's available width (with no
  room, the pane takes its width from the sections through a splitter). Closing the pane gives the width back.
  The sections column scrolls, so **the window never needs to be taller than its screen**; at open its size is
  the remembered one, clamped to the screen's available geometry (`fit_screen`, as the Activity window).
- **Remembered size:** a new `settings_defaults` row, `FOLDER_INFO_SIZE_SETTING = "folder_info_window_size"`,
  str, `"620,560"`, "The Folder info window's size in logical pixels, \"<width>,<height>\", saved when it closes,
  without its detail pane; at most the screen's, at least 420 by 240; otherwise the default (Q64.7)." Read
  through `read_setting`, parsed as the Activity window's `parse_size`.
- **Rendering reads memory only** (the model's rows): building and showing never stat anything
  (`no_source_io` test). It renders when a read arrives, on Refresh, and during Live as above; not on a timer.
- **Accessible names and IDs:** every button, link row and the detail pane through `identify`
  (`folder_info_refresh`, `folder_info_copy`, `folder_info_<section>_<action>`, `folder_info_<section>_more`,
  `folder_info_detail`), and the window added to `tests/test_accessible_names.py`'s walk.

## 5. The ways in (Q64.1, Q64.2)

- **Right-click › Folder info…** in `FolderExplorer.show_context_menu`, proposed right after "Copy Pathname" (the
  folder's own group, before Retry / Refresh), with "⌘I" shown as its shortcut text. **C~2**: the menu's order
  changes by one item (no test pins it: I checked `tests/` for the menu's labels).
- **Folder details' Disk cache row** (Q64.1): a "Folder info…" link at the row's end, as its own small `QLabel`
  in a third grid column of that row (so the row's text elides and the link never does), shown whenever the
  row is; the row itself is unchanged. The panel emits `folderInfoRequested(str)`; the main window opens the
  window for the current tab's selected folder. When the row is hidden (the data root not known yet: before a
  helper answers) the link hides with it (Q~4).
- **File › Folder info…** with **⌘I / Ctrl+I** (`QKeySequence("Ctrl+I")`, which Qt shows as ⌘I on macOS): acts on
  the current tab's selected folder, also with the explorer hidden. Disabled with none: enabled from
  `aboutToShow` as Place .helab-root and Convert this folder are, and **also** on tab change and selection
  change (`selectionPathChanged`), since a disabled action's shortcut never fires and a shortcut doesn't show
  the menu. Memory only.
- `HelabMainWindow` changes stay in `create_menus` (the action), opening the window (`show_folder_info`), and
  closing it at quit.

## 6. Each section's content

Times are local, "5 Nov 14:02" (today: "14:02:31"); ages through `time_format.relative_age` in tooltips. Sizes
through `byte_size(n, "disk")` (RAM: `"ram"`).

**This session** (memory). Rows: "Loaded: 1,234 shots · 2.1 GiB in RAM · HeLab priority" or "Not loaded";
"Live: on in tab 2 · Auto-convert on" (or off); "Plots: Correlations, Release time" (count when more than 3;
names in the tooltip); "Newest shot: 1234 · written 14:01:55"; a waiting save's question ("Waiting for your
answer: Make room…"). Then the **subfolders line**: "Subfolders: some have data (derived 14:00, saved)" from
`subtree()`, with its tooltip as the folder row's. No actions.

**Disk cache** (the read). Rows:
- "Raw pulses: 1,234 shots (d1–d1234) · 1.8 GB · saved 3 Nov–5 Nov" (tooltip: last used, last seen by a listing,
  the policy that keeps them).
- One row per TXY layer: "TXY External (MATLAB's): 1,200 shots · 900 MB · last used 5 Nov 13:00"; HeLab's:
  "TXY m23v1: 1,234 shots · 950 MB · rebuildable from raw pulses" (tooltip: the profile hash's first 12, the
  tags seen, precision, segments' bytes, saved and used dates, and the group in words).
- **Only copy** (Q64.8), amber with ⚠, only when there are any: "⚠ Only copy: 12 shots' raw pulses (18 MB) and 1
  TXY layer · HeLab last looked 5 Nov 13:58". Tooltip: "Only copy: the source files are gone. HeLab keeps these
  in its disk cache, but the folder's d*.txt (or TXY files) for them weren't there when HeLab last listed the
  folder (5 Nov 13:58, 2 hours ago). HeLab learns a file is gone only when it lists the folder; if the files are
  back, a listing (Retry / Refresh) clears this." "When it last looked" is the newest `seen_at`/`gone_at` of
  those rows (the listing's evidence time, C2-10's rule), else the saved listing's `listed_at`.
- "Loads saved: HeLab priority · m23v1; External" (views; tooltip: each with its last use).
- "Older dataset (stage 1): 120 MB" when a seed row remains (rare).
- With a successful read and none of the above: "Nothing cached for this folder". RAM only: "RAM only: nothing
  is cached for this folder" (and the header's Place .helab-root here…). store-v3: "Shown for store-v4 only".
- Actions (Q64.5): **Clear loaded data cache** (`FolderExplorer.clear_data_cache`, as the right-click: it doesn't
  ask today and keeps only copies) and **Clear raw pulses…** (Q~2: there is no per-folder one today).

**Saved plot results** (the read; store-v4 only, Q64.7). Grouped by script: a group line "Correlations v3
(4 results · 12 MB)", then one line per result: "<action> · <settings, short> · computed 3 Nov 14:00 · used
5 Nov · 3.1 MB" (tooltip: every setting, one per line; the script's file and hash; saved date). Shows the newest
3 lines; the rest in the detail pane ("All 37 saved results ›"), which lists every row the read sent and says
"and N more not shown" past 200. A damaged record: "<script> · record unreadable · 3.1 MB". Action (Q64.6 (a)):
**Settings › Data roots…** (selected on the folder's root: Clear cached analysis there) and **Settings ›
Cache…**; no per-folder Clear in v1.

**Flags** (memory; the read in the tooltip). One row each: "Don't cache: off", "Don't auto-load: off",
"Write TXY beside: off", with the actions as **checkable buttons** (the same toggles as the right-click, which
ask as they do: `set_folder_flag`; Write TXY beside through Auto-convert's `_set_write_beside`, which asks
before turning it on: C~3). RAM only: disabled with the right-click's `NEEDS_ROOT_TOOLTIP`.

**TXY list and cache policy** (memory). "TXY: HeLab priority · m23v1 (this folder's own)" or "(Settings' list)";
"Cache policy: raw pulses and used TXY (Settings')". Tooltip: the list as its editor shows it, and the saved
choice with its date. Actions: **TXY for this folder…** (`choose_folder_txy`), **Cache policy for this
folder…** (`choose_folder_policy`); both only under store-v4, as in the right-click.

**Constants** (memory). One row per value in effect: "Fall distance: 0.848 m (this folder)", "Trap ω: … (from
/…/run_12)"; "None set here or above (lab defaults)" otherwise; session-only: amber "This session only: <why>".
Action: **Folder constants…** (`show_folder_constants`).

**Scan history** (the read; the session's when newer). "Last folder status check: ok, 5 Nov 13:58" or "Failed
3 times · automatic checks skipped" (amber); the failures in the detail pane when more than 3 (newest first,
as `history_tooltip` words them); "Last basic scan: 1,234 TXY · 5 Nov 13:58" from the summary record. Action:
**Retry / Refresh** (`refresh_folder`, disabled offline as in the right-click).

**HeLab's converted TXY** (the read: the index). One row per base and tag: "Cache folder: m23v1 · 1,234 shots ·
950 MB · last used 5 Nov" ; "Beside the raw files: m23v1 · 1,234 shots (as recorded)". Tooltip: the profile's
name and version, the newest conversion, the base's folder. An index that can't be read: "Index can't be read
(<why>): shots only convert again" (its own part's error, never "none"). Action: **Convert this folder…**
(`converter.ask_convert`, disabled with `convert_unavailable`'s reason) and **Settings › Cache…** (its Clear,
Q64.6 (a)).

**Data root** (Q64's eighth) is in the **header** (Q~3), since every other section depends on it: "⚓ <label> ·
<marker path>" with **Settings › Data roots…** (selected on the root); RAM only with **Place .helab-root
here…** (`place_root`, its own checks and question); a pending location with **Review…**.

## 7. Tests

New (owned paths):

- **`tests/test_folder_info_helper.py`**: the action on a temporary store-v4 seeded with each kind of row: raw
  layers (some `gone_at`), TXY layers by tag (a rebuildable HeLab layer, a seen `matlab` one, an only-copy one),
  views, results (decodable, damaged, 300 of them for the bound), flags, converter flags, choices (a TXY list),
  constants, a failed scan's history, a summary and a listing, and a converted-TXY index in the cache base and the
  temp base. Checks each field; `group` agrees with `_txy_groups` for the same rows; a folder without a root
  (`no_root`), an unverified volume (`unverified`), a store-v3 store (`skipped` parts), a store that can't be
  opened (`error` event), a damaged index (that part `error`, the rest found), the event's encoded size; **no
  source I/O**: the source folder doesn't exist on disk in these tests, and an `os` trace (the testing doc's
  I/O traces) shows no call under it.
- **`tests/test_folder_info_model.py`**: `build` from fake events and `Memory`: every section's rows and
  tooltips, the only-copy wording and "last looked", "Nothing cached" only on `found`/`missing` parts, an error
  answer never saying nothing is saved, RAM only, store-v3, results grouped and truncated with the detail list,
  memory vs store differences ("not saved yet"), `as_text`, and `Reads` (one in flight, a newer ask replaces
  the queued one, retarget drops the old answer, a failure keeps the last good parts).
- **`tests/test_folder_info_window.py`** (pytest-qt): the window from a model; never taller than the screen
  (sizes from the fonts, not constants, for Windows CI); the detail pane widens the window and gives the width
  back; each action calls the tab's existing method (fakes record the calls); Refresh, the post-action arm,
  and Live's two triggers through fake `FolderCache` signals; the remembered size through `read_setting`;
  `no_source_io` for opening and rendering; the ways in: the right-click menu has the item, File › Folder info…
  follows the selection (disabled with none) and ⌘I opens it, Folder details' link emits its signal.

Existing tests I expect to touch (lists only, as the brief allows): `tests/test_helper_events.py` (the new kind
and its sender), `tests/test_headless_imports.py` (`helab.utils.folder_info` in `PURE`),
`tests/test_accessible_names.py` (the window in its walk), and `tests/test_settings_defaults.py` only if it
lists rows by hand. Folder details' and the File menu's existing tests should pass unchanged (the link is a new
widget; the Disk cache row's text and visibility don't change).

## 8. Questions

For Tony (provisional; CoCo files them):

- **Q~1 The window's title.** (a) "Folder info — <full path>" (the path in the title, as Q64.3 says; long paths
  are cut by the OS); (b) "<folder name> — Folder info" with the full path in the header and the macOS proxy
  icon. **Proposed:** (a).
- **Q~2 "Clear raw pulses…" for one folder.** Q64.5 lists it, but today it exists only as Settings › Cache's
  Clear raw pulses (every folder) and as S4~1's offer after "TXY only" (whose question says the folder keeps no
  raw pulses from now on). A per-folder clear also removes the folder's **only copies** (`remove_raw` takes
  every raw row of the folder). Options: (a) a new question, "Remove HeLab's cached raw pulses of <folder>
  (1.8 GB)? Your d files aren't touched." with S4~1's only-copy paragraph when there are any ("12 of them are the
  only copy: their raw files are gone from the folder, so they can't be read again."), buttons "Remove cached raw
  pulses" / "Keep them"; (b) the same, but keep the only copies (a new reader-side rule: `remove_raw` would need
  a `keep_only_copies` option, a store write path, which needs CoCo's go); (c) no button in v1, a link to
  Settings › Cache as for results (Q64.6). **Proposed:** (a).
- **Q~3 Where the data root goes.** Q64's list puts it eighth. **Proposed:** in the header, under the path, since
  every other section depends on it (RAM only means nothing else is cached); or (b) a section of its own, last.
- **Q~4 The Folder details link while the data root isn't known yet.** The Disk cache row is hidden until a
  helper says (a moment after selecting); the link hides with it. **Proposed:** (a) as described (File › Folder
  info… and ⌘I still work); (b) show the row with "Folder info…" alone meanwhile (changes the row's visibility,
  which existing tests pin).
- **Q~5 Section order.** **Proposed:** This session, Disk cache, Saved plot results, Flags, TXY list and policy,
  Constants, Scan history, Converted TXY (what's loaded now first, then what's kept, then the choices, then
  history); or (b) Tony's list's order with This session last.

For CoCo (files outside the owned paths, or a behaviour an existing test may pin):

- **C~1** `cache_store._txy_groups`: extract the per-layer classification into `_layer_group`, shared with the new
  reader (behaviour unchanged), or duplicate it with a test pinning the two together? I'd extract.
- **C~2** The right-click menu gains "Folder info…" after "Copy Pathname" (its order changes by one item).
- **C~3** Write TXY beside is `AutoConvert._set_write_beside` (private, in `explorer_live.py`, which the brief
  allows only for Live's refresh hook). May I add a one-line public `set_write_beside(path, on)` there that calls
  it, or should the window call the private method? (I'd add the public name.)
- **C~4** If Q~2 is (a), the question needs a small public `FolderExplorer.ask_clear_raw(path, size,
  only_copy)` beside `_ask_raw_removal` (same box, its own words and `identify_buttons` ID); in bounds?
- **C~5** A new module `helab/io_ops/folder_info.py` for the job (assembling and bounding the event), with
  `admin.py` dispatching to it; the brief allows "new reader modules if the design puts them apart". Is
  `helab/io_ops/` fine for it, and `tests/test_folder_info_helper.py` for its tests?
