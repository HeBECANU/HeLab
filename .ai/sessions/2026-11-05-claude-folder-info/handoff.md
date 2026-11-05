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
| `0f95d61` | Times Windows can't show read "unknown" (CI 41998150471's Windows failures) |
| `9da2bee` | Handoff notes the Windows fix |
| `8620de5` | Per-folder Clears: raw pulses, saved results, converted TXY (Q~6 and Q64.6 (b), Tony 2026-11-05) |
| `25bdbda` | Review (Tally): [review.md](review.md), 2 Major, 3 Minor, 3 Info |
| (next) | Review fixes FI-1, FI-2, FI-3, FI-4, FI-5, FI-7, FI-8 (FI-6 stays A~5) |

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
  the current tab); its own are the three per-folder Clears (below). Reads on open, Refresh, and after an action at the
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
- **Per-folder Clears** (Q~6 (a) and Q64.6 (b), Tony 2026-11-05: "implement now"): **Clear raw pulses…** (Disk
  cache), **Clear this folder's saved results…** (Saved plot results), **Clear this folder's converted TXY…**
  (HeLab's converted TXY). Each asks first from the current read (`folder_info.clear_question`: sizes, counts and
  the only copies; buttons "Remove …" / "Keep them", Keep the default, a warning icon when it names only copies),
  is offered only when that read found something to remove (never from a failed, stale read; greyed while it
  runs), and goes through `FolderCache.clear_folder(path, part)` → the existing admin actions scoped to the folder:
  - `clear_raw paths=[path]` → `CacheStore.remove_raw(paths)` (existing): the folder's `raw:` epoch bumped, so a
    `raw_fill` already running can't bring them back; only copies included, named in S4~1's paragraph.
  - `clear_results paths=[path]` (new parameter) → `remove_results(paths)` (existing scope): the folder's results
    epoch bumped; results waiting for an answer go with them, as before.
  - `clear_converted_txy path=path` (new parameter) → `helab_txy.clear_converted_folder` for each of
    `helab_txy.folders(path)` (cache folder by key, temp by key and by path): `clear_converted`'s rules for one
    folder (now shared: `_clear_folders`), fenced first, only the rows of the very files removed forgotten,
    beside TXY's rows and files never touched (the global Clear never touches them either: it only looks under
    `converted-txy/`), nothing else of the base. **The fence is the index's one token** (A19.2), so a conversion
    of another folder into the same base running at that moment stops writing and converts the rest at its next
    check, as after Settings' Clear (A~5).
  Each sends `removed` (Q3.3) with `paths: [path]`. The three trust only volume hints verified this session, as
  the read does (`admin.py`'s `verified_volumes` list; callers that send none, every global Clear and the
  S4~1 offer, trust every hint as before). An unverified drive refuses (`VolumeUnverified`, also for the converted
  Clear: it is a `NoDataRoot`, so it is re-raised before the RAM-only fallback to by-path folders). The header
  then says "Removed <this folder's …> · <time>" or "Couldn't remove <…>: <why>" (refused, failed or not queued),
  and the folder is read again. **Only copies of converted TXY:** the read now counts, per tag, HeLab's TXY of shots
  whose raw rows are marked gone (`folder_contents`' raw part has `gone_shots`, not sent; the event's
  `FolderConvertedTag` gains `only_copy`, `only_copy_bytes`); the question says how many, and that HeLab knows a d
  file is gone only for shots whose raw pulses it cached (no listing of the folder). The rows say "⚠ N only
  copies" in amber.
- **Links:** Disk cache's Settings › Cache… (every folder, by kind) and Saved plot results' Settings › Data
  roots… (the folder's root selected: `DataRootsTab.select_root(uuid)`, now or once its list is read;
  `show_settings_dialog(root=)`). Saved plot results' and converted TXY's own Settings › Cache… links went: they
  repeated Disk cache's, and with them those title lines needed 592 px (the window's default is 620). The sections
  now scroll sideways when the window is narrower than a title line (min 420; the widest line needs 475 px),
  instead of cutting buttons off.
- `LiveController.set_write_beside` (C~3): a public name over the existing asked path, for the Flags toggle.

## Review fixes (Tally's [review.md](review.md), CoCo's calls)

Each with a test that fails on `8620de5` (checked by running the new tests against the old sources):

- **FI-1 (Major) Live's save on stop:** `_save_ended` now reads after any `saved` / `superseded` save of the
  window's folder, Live on or not (`stop_live` turns Live off before its last save). A save of another folder, or
  one that saved nothing, doesn't read. Test: Live on, Live off, then the stop's `saveEnded` → one read; the old
  Live test's "Live off: a save alone doesn't read" now checks a rejected save and another folder's instead.
- **FI-2 (Major) an unverified drive read as RAM only:** `io_ops.folder_info.folder_key(store, path)` turns the
  admin opener's plain `NoDataRoot` on a mount in `store._unverified_mounts` into `VolumeUnverified` (as
  `constants` and the offline listing check). The read says "unverified"; all three Clears refuse with that reason
  (`admin._refuse_unverified` for `clear_raw` / `clear_results` with `paths`; `_converted_folders` for the
  converted one, never falling back to the temp folder by path); the model greys the Clears with "Not now: this
  drive isn't verified yet this session". The helper tests now use the real opener and resolver on a hinted mount
  (`verified_volumes=[]` against `[[mount, source]]`, `test_store_migration`'s setup), for the read and all three
  Clears; the `_path_key` fakes are gone.
- **FI-3 the pane moved the window:** `open_detail` takes the position from `frameGeometry()` and `move`s in frame
  coordinates, the size by `resize`. The test (open and close three times, the frame's top stays) fails on the old
  code even offscreen: the offscreen platform has 6 px frame margins, and the old `setGeometry(x(), y(), …)` moved
  the frame by them.
- **FI-4 (CoCo's wording):** the raw pulses question adds "They're cached again the next time this folder loads.",
  or "They aren't cached again: this folder is set to Don't cache." / "…: this folder's cache policy is TXY only."
  (`Memory.policy_id`, the policy in effect). The manual's table says so.
- **FI-5 minimised:** a hide by the system (`isMinimized()` or a spontaneous hide) keeps the window hooked up; a
  read that falls due waits (`_missed`), and the restore reads once and refreshes This session. Closing unhooks
  as before. Test: minimised, two saves → no read; restored → one read; closed → unhooked.
- **FI-7:** Flags, TXY list and cache policy, and Constants show "Couldn't read the saved <…>: <why>" in amber when
  their part failed (`_saved_errors`), as the other sections do.
- **FI-8:** `fit_screen` on every show (and so every retarget that shows it), not only the first. Test: resized
  past its screen while hidden, reopened → fits.
- **FI-6:** stays A~5.

## Checks

- **After the review fixes:** full suite **9507 passed, 673 skipped, no reruns**; the five type checks, `ruff
  check` and `mkdocs build --strict` clean. (The first run had 4 failures with 20 reruns, all `tests/test_typing.py`'s
  four mypy checks on one annotation in `_choices`, fixed before this run.) Ten new tests: helper (FI-2's read and
  the three Clears on the real opener), model (FI-2, FI-4, FI-7), window (FI-1, FI-3, FI-5, FI-8). All eight in the
  model and window files fail on the `8620de5` sources, and FI-2's two fail without its helper fix.

- **After the per-folder Clears:** full suite (`pytest -n 4 --reruns 5 --reruns-delay 1
  --basetemp=.ai/temp/pytest`) **9500 passed, 673 skipped, no reruns**; the five type checks, `ruff check` and
  `mkdocs build --strict` clean. (A first run had 3 failures with 15 reruns, all `tests/test_typing.py`'s three
  checks on type errors in the new code and tests, fixed before this run.) New tests: helper 5
  (`test_folder_info_helper.py`: raw pulses, saved results and converted TXY of one folder on a seeded store with
  a second folder untouched, beside TXY's row and the source folder untouched, the running save's or conversion's
  fence, only copies named; a refused (unverified drive) and a failed (`StoreError`) Clear removing nothing; the
  app's three requests with verified volumes), model 4, window 1 (asks, no removes nothing, yes clears this folder
  and says "Removed …", a failure says "Couldn't remove …: why", read again, retargeted window ignores the end).
  Rendered at 620 and 420 px: fits at 620; at 420 the sections scroll sideways.

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
> change (armed 10 min), and after every `saveEnded` (saved, superseded) of its folder, Live on or not (Live's last
> save comes after Live is off); while Live watches the folder, `datasetChanged` re-renders This session.
> Minimised, it stays hooked up and reads once on the restore if one fell due; it fits its screen on every show. Memory parts (`FolderInfoSources.memory`): the data root, flags, the TXY list
> and policy in effect, inherited constants, the session's scan history, the subfolders' derived status, This
> session (RAM, Live, plots on it, newest shot). Its buttons call the tab's existing actions, and links to Settings
> › Cache and Data roots (the latter with the root selected, `DataRootsTab.select_root`); its own are the
> per-folder Clears (Q~6, Q64.6 b: raw pulses, saved results, converted TXY; `FolderCache.clear_folder`), each
> asked first from the current read (`folder_info.clear_question`, only copies named), the header saying
> "Removed …" or "Couldn't remove …: why", then a read. Long sections
> open a detail pane to the right, widening the window; the sections scroll; the window is clamped to its screen;
> size `folder_info_window_size`. "Nothing cached" only from a part the read found empty; a failed read keeps the
> last good lines greyed and names the error.

**`.ai/architecture/cache-store.md`**, at the end of store-v4's TXY layers bullets:

> - **Folder info's read** (`CacheStore.folder_contents`, `helab/io_ops/folder_info.py`, admin `folder_info`): one
>   folder's rows in one read transaction (raw totals and only copies, layers with `layer_group`, views, seed,
>   store-v4's own results, flags, choices, constants, history, summary, listing) and the converted-TXY indexes
>   read only; event `folder_info` (bounded: no per-shot data, 200 results, 32 layers and views). Make room's
>   per-layer rule is `cache_store.layer_group`, shared by `_txy_groups`: [app-runtime-and-ui](app-runtime-and-ui.md).
> - **One folder's Clears** (Folder info, Q~6 and Q64.6 b): `clear_raw paths=[path]` (`remove_raw(paths)`, the
>   folder's `raw:` epoch), `clear_results paths=[path]` (`remove_results(paths)`, its results epoch) and
>   `clear_converted_txy path=path` (`helab_txy.clear_converted_folder`: `clear_converted`'s rules for one of
>   HeLab's folders, `_clear_folders`; the index's one fence token, so other folders' conversions into that base
>   wait for their next check). Each sends `removed` with the folder's path and trusts only verified volume hints.
>   A converted TXY is counted as an only copy when its shot's raw row has `gone_at` (`folder_contents`' raw
>   `gone_shots`).

**`.ai/architecture/settings.md`**: the row `folder_info_window_size` (str, "620,560"; as Activity's).

**`.ai/architecture/io-and-browsing.md`**, where `ADMIN_ACTIONS` is named: add `folder_info` (read only; trusts
only verified volume hints, as `constants`), and that `clear_raw`, `clear_results` (new `paths`) and
`clear_converted_txy` (new `path`) do too when the app sends them (Folder info's per-folder Clears): a folder on a
mount in `store._unverified_mounts` is refused as `VolumeUnverified` (`io_ops.folder_info.folder_key`), as
`constants` does.

**`AGENTS.md`** (one line, the code map's `helab/views/` row): after `ActivityWindow.py (…)`, add
"`FolderInfoWindow.py` (File › Folder info…: one folder's cache, results, flags and choices; model
`helab/utils/folder_info.py`)". No new invariant.

**`roadmaps/folder-info.md`**: status → built on `agent/folder-info` (commits above); the Decided sections stand;
CoCo's Q~ answers (below) under them; Q64.6 → (b), built (Tony, 2026-11-05: "implement now"), with Q~6 (a); the
"Later" item "Per-folder Clear of saved results and converted TXY" is done; A~5 goes to Later.

**`roadmaps/known-issues.md`**, a new entry:

> - **`tests/test_convert_helab.py::test_a_killed_helpers_workers_exit` RERUN** (`AssertionError: the pool
>   started`): under `-n 8` the converting helper's pool workers weren't yet visible to `psutil` when its first
>   `shot_converted` arrived (2 reruns, `agent/folder-info` at `4dd31db`, 2026-11-05; passed on rerun). Unrelated
>   to that branch. Likely fix: wait briefly (bounded) for the children before asserting, or have the helper report
>   its pool's pids.

## Questions and follow-ups (provisional IDs)

Decided by CoCo with Tony in Chat (record them): **Q~1** title "Folder info — <path>"; **Q~2** (c) no per-folder
Clear raw pulses in v1, links to Settings (superseded by Q~6); **Q~3** the data root in the header; **Q~4** Folder
details' link hidden with the Disk cache row; **Q~5** section order as built.

- **Q~6 Per-folder "Clear raw pulses…"** (from Q~2). **Decided by Tony, 2026-11-05 ("implement now"): (a)**, a
  question naming the size and S4~1's only-copy paragraph, buttons "Remove cached raw pulses" / "Keep them",
  with Q64.6 (b)'s two per-folder Clears, on this floor before review. Built as above.
- **A~5 A per-folder fence for HeLab's converted TXY.** A per-folder Clear of converted TXY sets the index's one
  fence token (A19.2), so a conversion of *another* folder into the same base, running at that moment, stops
  writing (its shots wait, "HeLab's converted TXY were cleared while this conversion ran: converted again at the
  next check") and converts them at its next check. Safe (nothing comes back, nothing is lost), but that folder's
  wait message is misleading. Fix: a per-folder token (a `folder_fences` table, additive within schema 1, as
  `fence` was), read by `fence_of(root, folder)` and checked beside the base's; it touches
  `helab/convert/provenance.py` and `helab/io_ops/convert.py`, so not on this floor.
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
  following each shot and a read after each save (every N shots and on stop). The three Clears on a copy of a
  real folder: each question's sizes against Settings › Cache's, the only-copy paragraph (a raw file moved away,
  Retry / Refresh, then Clear raw pulses…), "Removed …" and the lines read again, and another folder's cache
  untouched. On macOS and Windows: open and close the detail pane several times (the window stays put: FI-3);
  move the main window to the laptop screen and reopen Folder info (it fits: FI-8); minimise it during Live and
  restore it after a save (FI-5).
- **M~2 Windows:** Ctrl+I, the fonts (the title lines' buttons on Windows' wider fonts), and the detail pane at
  1366-pixel-wide screens.
