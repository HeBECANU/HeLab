# Brief: the Folder info window (`agent/folder-info`)

Coordinator: CoCo, 2026-11-05. Tony asked for it in the live run (LR-5) and decided Q64.1–Q64.10 in Chat (relayed by
Side; block 64): v0.0.9, a floor on this Mac. One Worker; one Reviewer at landing.

## Read first

- `AGENTS.md`, above all the I/O and threads rules (the GUI never opens the store or touches source folders; helpers
  do; rendering reads memory only; a read answers found / missing / error, and an error is never "nothing saved"),
  the disk-cache rules and the UI rules.
- **The plan: `roadmaps/folder-info.md`.** Its two "Decided" sections are Tony's and are the spec (Q64.1–Q64.10;
  the questions as asked are kept below them with the reasons). Its "Design notes" are proposals you may change in
  your design. "Later" and "Not in scope (v1)" are out of this floor (Q64.6 (b), Q64.9's N-level summary, Q64.11).
- The decisions: block 64 in `.ai/DECISIONS_TODO.md`.
- `.ai/architecture/cache-store.md` (store-v4: raw and TXY layers, views, results, prefs, the only-copy logic),
  `data-roots.md`, `converter.md` (the converted-TXY index), `io-and-browsing.md` (IOService, the local lane,
  `cache_admin`), `live.md` (Live's checks and saves), `app-runtime-and-ui.md` (Folder details, the File menu,
  the Activity window), `settings.md`, `testing.md`.
- Starting points in the code (from a map made for the plan; check them):
  - store readers in `helab/utils/cache_store.py`: `folder_raw` (:3937), `raw_rows` (:3104), `txy_layers` (:3488),
    `folder_views` (:3530), `read_prefs` / `read_convert_prefs` (:1478, :1531), `read_folder_choices` (:3952),
    `read_constants` (:1609), `root_usage` (:3994), `_folder_results` / `result_counts` (:2806, :2835; counts
    only: a per-folder list is new), `_txy_groups` (:3830; the rebuildable / only-copy logic, store-wide and
    private);
  - `helab/io_ops/admin.py` (`ADMIN_ACTIONS`, `folder_choice` :275), `helab/io_ops/events.py`
    (`AdminResultFields` :93), `helab/utils/scan_history.py` (`read_history`, `history_tooltip`),
    `helab/convert/provenance.py` (`TxyIndex.shots`), `helab/io_ops/helab_txy.py` (`folders`);
  - `FolderCache.cache_admin` (:3546) and `_on_admin_event` / `cacheAdminResult` (one round trip, end to end);
  - the GUI's memory: `FolderCache.folder_prefs`, `folder_list`, `effective_folder_constants`, `root_of`,
    `scan_history`, `result_counts`;
  - the ways in: `FolderExplorer.show_context_menu` (:2269), `FolderDetailsPanel` (its Disk cache row, :350;
    link rows through `eventFilter`, :176), `HelabMainWindow.create_menus` (File menu, :413–466; `aboutToShow`
    enabling as for Place .helab-root and Convert this folder);
  - the existing actions each section calls (the plan's Q64.5 list): `FolderExplorer.clear_data_cache`, the
    `clear_raw` admin, `set_folder_flag`, `explorer_live.fill_convert_menu`, `choose_folder_txy`,
    `choose_folder_policy`, Folder constants…, Retry / Refresh scan, Convert this folder…, Place .helab-root…,
    Settings › Data roots;
  - the nearest precedent: `helab/views/ActivityWindow.py` (non-modal, a Qt-free model in `helab/utils/activity.py`).

## Base and branch

Base: `dev/v0.0.9` at the commit that adds this brief (named in CoCo's message to you). Branch:
`agent/folder-info`. Two other floors run beside you: Basic Plots v2 (plots, the Scripts panel) and App Updates
(Help menu, About, Settings › General). Keep `HelabMainWindow.py` changes to the File menu and opening the window.

## Objective (commit each step separately; stop and report to CoCo at each ◆)

1. **◆ Design first (`design.md` in this folder), before any code.** It covers:
   - **The helper job:** one `cache_admin` action (proposed `folder_info`) on the local lane that opens the store
     once and reads only the store and HeLab's converted-TXY index, never the source folder; its event kind in
     `events.py` (fields, sizes bounded: a folder with thousands of shots or results must not make a huge event);
     the new readers (per-folder results; a per-folder form of the only-copy logic) and where they live.
   - **The model:** a Qt-free `helab/utils/folder_info.py` (in `PURE`) that turns the event plus memory into
     sections of one-line rows; which parts come from memory (the inherited TXY list and constants, the data root,
     This session, the subfolders line, the newest shot).
   - **Refresh (Q64.4):** on open, on Refresh and after an action started from the window; **while Live watches
     the folder**, the memory parts on each Live check that brings shots and the store read after each Live save
     (every 10 shots and on stop), never more than one read in flight (a newer request replaces a queued one);
     "As of HH:MM:SS"; the error state.
   - **The window (Q64.3, Q64.7):** one window, retargeted on each open, path in the title; the header (path, data
     root, As of, Refresh, Copy as text if you keep it); each section with its actions on its title line (Q64.5);
     **it grows sideways, not tall**: long sections show a few lines and open their full list in a detail pane to
     the right, widening the window; never taller than its screen; remembered size (a `settings_defaults` row).
   - **The ways in (Q64.1, Q64.2):** right-click › Folder info…; the "Folder info…" link at the end of Folder
     details' Disk cache row (no new row); File › Folder info… on the current tab's selected folder, with the
     explorer hidden too, disabled with none; ⌘I / Ctrl+I.
   - **Each section's content** (the plan's eight, plus This session and the subfolders line, Q64.9): what each row
     says, its tooltip, and the store-v4-only rule (Q64.7); Q64.8's only-copy wording with when HeLab last looked;
     without a data root, the window says RAM only and offers Place .helab-root here….
   - **The tests**, and which existing tests you expect to touch.
   - Questions for Tony as provisional `Q~1`, `Q~2`… with options and a proposed answer.

   Send CoCo the design with `maestri ask "CoCo" …` and wait for the go.
2. **The helper action, its readers and its event**, with tests on a temporary store seeded with each kind of row
   (raw layers, TXY layers by tag, gone sources, results, flags, a TXY list, constants, a failed scan's history, a
   converted-TXY index) and its error answer.
3. **The model and the window**, with the ways in and the actions; tests from fake events.
4. **Live's refresh** and the remembered size. ◆ Report after this step, with the suite, the type checks and a
   pushed branch with its CI run.
5. **Docs proposals** in your handoff (`handoff.md`): the architecture section (probably `app-runtime-and-ui.md`,
   with a pointer from `cache-store.md`), AGENTS.md's line if any (at most one), the manual's page (you write
   `docs/` yourself), and provisional `Q~`/`A~`/`M~` items, including an M~ for Tony to try the window on a real
   screen with a real folder and with Live.

## Acceptance

- Every decided section shows the folder's real state from one helper read plus memory; the only copies are named
  with when HeLab last looked; a failed read says so and never shows "nothing saved".
- Each section's buttons go through the folder's existing actions, which ask as they do today; the window itself
  changes nothing.
- While Live watches the folder the window keeps up by itself, with at most one read in flight; otherwise it reads
  only when asked.
- The window opens no taller than its screen; long lists open to the side.
- **The invariants hold:** the GUI never opens the store or touches the source folder (a `no_source_io` test for
  rendering and opening); the GUI never waits on the helper; requests bounded and deduplicated; byte sizes through
  `number_format.byte_size(n, "disk")`; every read through `read_setting`; the new event kind in `events.py` with
  `tests/test_helper_events.py`; `helab/io_ops/` doesn't import `helab.io_helper`.
- **The UI rules hold:** accessible names and `identify` IDs (`tests/test_accessible_names.py`, the window in its
  walk); one-line rows, detail in tooltips and the detail pane; no vertical padding around blocks; gaps from
  `helab/views/gaps.py`; no lambda that captures a Qt-made sender; no Python callable on `destroyed`; tooltips are
  wrapped app-wide already (`helab/views/tooltips.py`), so don't wrap them yourself.

## Rules

**Owned paths** (new files): `helab/utils/folder_info.py`, `helab/views/FolderInfoWindow.py`, new reader modules if
the design puts them apart, `tests/test_folder_info*.py`, `docs/` (the manual's page and `mkdocs.yml`'s nav).

**Edits allowed, kept small:** `helab/io_ops/admin.py`, `helab/io_ops/events.py`, `helab/utils/cache_store.py`
(read-only readers), `helab/utils/store_v4.py` (read-only readers), `helab/convert/provenance.py` and
`helab/io_ops/helab_txy.py` (read-only), `helab/utils/folder_cache.py` (the request and its signal, memory
accessors), `helab/views/FolderExplorer.py` (the menu item), `helab/views/FolderDetailsPanel.py` (the link),
`helab/views/HelabMainWindow.py` (File menu, the window), `helab/views/explorer_live.py` (Live's refresh hook,
read-only), `helab/utils/settings_defaults.py` (new rows only), `tests/test_headless_imports.py`,
`tests/test_accessible_names.py`, `tests/test_helper_events.py` (lists only).

**Ask CoCo before any other file**, before changing a store write path, and before changing behaviour an existing
test pins (Folder details' rows, the right-click menu's order, the status bar).

**Checks and process:**
- Strict typing, including `mypy --platform win32` and `pyright --pythonplatform Windows`.
- Tests never touch real data; `~/HeLab-samples` is read-only.
- Run `source .ai/local/floor-env.sh` before tests or a manual run. The GUI may run from the floor once
  `$HELAB_TEST_SETTINGS_FILE` is set.
- Before each ◆ and the handoff, run the full suite (`pytest -n 8 --reruns 5 --reruns-delay 1
  --basetemp=.ai/temp/pytest`) and the five type checks, keeping their output whole and reporting every RERUN with
  its reason. Layout tests take their sizes from the fonts, not constants (Windows CI's fonts are wider).
- Docs go in `.ai/sessions/2026-11-05-claude-folder-info/` only. Don't edit `AGENTS.md`, `.ai/architecture/`,
  `roadmaps/`, `.ai/memory/` or the three `.ai/*_TODO.md` lists; propose those changes in the handoff.
- Public text (the manual, docstrings, labels and tooltips) names no person except Tony, and no lab machine,
  internal ID or `.ai/` path.
- Commit freely on your branch. Push only at checkpoints (step 4's ◆ and the handoff). Before you report a CI run,
  read every Tests and Converter backends job's log for RERUN.
- Never delete a branch. No version bump, release, tag, PR or merge.

When done: `maestri floor status "<summary>" --state review`, then
`maestri ask "CoCo" "Folder info: done at <hash>, suite <N> passed, RERUNs <…>, CI <run>"`.
