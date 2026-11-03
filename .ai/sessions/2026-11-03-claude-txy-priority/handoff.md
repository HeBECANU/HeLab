# Handoff: TXY priority lists, the External label, manual convert (block 53)

Worker: Claude (Opus 5.5), floor TXY Priority, branch `agent/txy-priority` from `dcc02d8`. Brief:
[brief.md](brief.md); design and Tony's answers: [design.md](design.md).

## Summary

- **Q53.1**: the UI calls MATLAB's `d_txy_forc` **"External (MATLAB converter)"** ("External" in short). Only the
  labels changed (`txy_sources.EXTERNAL_LABEL`/`EXTERNAL_SHORT`).
- **Q53.2**: a TXY choice is an **ordered list** of entries: `External`, a profile's tag, or `Conversion` (Q~3:
  the conversion profile, resolved when a load is asked for). Each shot takes the first entry with a usable TXY.
  It can be set at three levels with one editor (`helab/views/txy_list.py`):
  - Settings › TXY converter;
  - right-click › TXY for this folder…;
  - each plot's TXY row.
- **The identity rule**: a list that is one of the four modes is saved, sent and identified exactly as that
  mode, so existing caches, views, presets and results stay valid. Any other list is its own source, choice
  and identity: its text, e.g. `m23v1>m19v1>External`.
- **Q~2, Tony's fallback.** A list of several entries continues per shot: the folder's list (for a plot), then
  Settings' list, then External, then the newest current HeLab TXY of any profile. A one-entry list never falls
  back. Datasets record the shots taken from the fallback; Folder details and the plot's line say so.
- **Convert on read (Q~1, Q~2.3)** happens only when nothing in the chain has a file. It converts with the
  own list's first HeLab entry that can convert.
- **Live's offer (Q~2.2)**: a folder whose list is one profile that Auto-convert doesn't convert with offers
  "Convert with <tag>" for this session.
- **Q~4, manual convert**: right-click › Convert this folder… and File › Convert "<folder>"…. You pick any
  profile and HeLab's cache, its temp folder or beside the raw files. It runs through `explorer_convert`'s
  machinery.
- **v0.0.7a1** reads what this saves without mistaking it. This was checked against `e03c32a` and is pinned by
  a test (design.md §2).

## Commits (`dcc02d8..476f760`)

`3da409a`, `d2c735b` design · `ae4aafc` Q53.1 label · `284cc60` lists, helper side · `1ed3ae1` v0.0.7 pin ·
`8bdfd4b` lists, app side + Q~2 seam · `74168a4` UI · `99000a5` Q~2 fallback chain · `d310428` Q~2.2 Live offer ·
`1104f65` Q~4 manual convert · `ed183aa`, `a00295c` integration check · `476f760` the plot's TXY button elides.

## Checks

- **Full suite:** `pytest -n 4 --reruns 5 --reruns-delay 1 --basetemp=.ai/temp/pytest -rR`. Result at `476f760`: **9217 passed, 673 skipped, no RERUN** (146 s). The run before it (`a00295c`) had one failure, `tests/test_main_split.py::test_the_settings_panel_goes_no_narrower_than_its_controls_need` (6 tries). The plot row's new button was wider than the 250 px panel; it now elides its text (`476f760`).
- **Type checks, all clean at `476f760`:**
  - `mypy helab/ --strict`
  - `mypy tests --strict`
  - `pyright helab tests`
  - `mypy helab/ --strict --platform win32`
  - `pyright --pythonplatform Windows helab tests`
- **RERUNs and failures seen during the work:**
  - **`tests/test_converter_tab.py::test_the_cache_tab_shows_and_clears_converted_txy`** failed all 6 tries in
    one `-n 4` run of about 750 TXY/Live/plot tests, after `99000a5`'s FolderCache change. It passed alone, in
    its own file, and in two later runs of the same set. Cause not found. I don't see a link to this work (it
    measures and clears HeLab's converted-TXY folders). It belongs in known-issues unless the full suite or CI
    shows it again.
  - Every other rerun during the work was a real failure, retried 5 times and then fixed: asserts on old text
    or the old API, and one `both` junk value that a lone word read as a tag (which led to the `@` form, below).
- **New tests:**
  - `tests/test_txy_priority.py`: model, identities, loads, fallback, offer, editor, display.
  - `tests/test_txy_priority_v007.py`: v0.0.7a1's own functions run on our records.
  - `tests/test_txy_priority_session.py`: the integration check, store-v4 and `store_v3`.
  - `tests/test_convert_folder.py`: Q~4.
  - The two new dialogs are in `tests/test_accessible_names.py`'s walk.
- **CI:** run **41583803573** on `64d08c8`, green on macOS, Windows and Ubuntu: all 9 Tests jobs and 3 Converter backends jobs. I read every job's whole log (downloaded through the API): **no RERUN** in any.

## Review fixes (Sieve's [review.md](review.md), 10 findings)

One commit each, every one with a test. TP-1 and TP-3 were checked to fail without their fix.

After the fixes, dev/v0.0.8 was merged (`b959de1`: record-only commits and labcam). Full suite at `b959de1`:
**9228 passed, 673 skipped, no RERUN**. The five type checks are clean. After TP-11 and the test fix (`f944a5a`):
**9229 passed, 673 skipped, no RERUN**; the type checks are clean. CI run **41590741400** on `d58cfa4`: green on all three OSes, all 12 Tests and Converter
backends logs read, **no RERUN**. CI: run **41587970080** on `bf3fb85`, green on all three OSes. I read every Tests and Converter backends job's
log: **one RERUN**, Windows Tests (1/3) (job 125757887948):
`tests/test_test_isolation.py::test_pytest_imports_the_checkout_it_runs_in_before_any_other`, the known
collection error in pathlib `lstat` on Windows. It passed on retry. It is the same signature as the open
known-issues entry; add this sighting there (CI 41587970080, job 125757887948, `bf3fb85`). It is unrelated
to this branch. The other 11 job logs have no RERUN.

| Finding | Commit | Fix |
|---|---|---|
| TP-1 (High) | `35a7007` | The helper's folder-row step resolves tags from what the app resolved and sent (`helab_txy.tag_lookup`: the mode's profile, the entries, `known`, `conversion`, then the built-ins). A user-profile row stays that profile, as a mode and as a list. |
| TP-2 (Medium) | `93ecebd` | `FolderCache._profile_for_tag` is memory only. The user's profiles are read once on a request's path (`with_txy` → `read_user_profiles`), or handed over by Settings' Save (`set_user_profiles`, no read). A tooltip never reads the profile folder. |
| TP-3 (Medium) | `8f250df` | Tests of `live_check` and `save_held` under `m23v1 › m19v1`. They **found a bug**: a shot held from a fallback External, which an own entry then had, stopped Live and the save with "changed". Live now reads it again (as A39.2's switch); `save_held` composes with `reclaim=False`. |
| TP-4 (Low) | `b6b2a84` | `converts_over_matlab` for a list matches `find_list`: External blocks, except with `CONVERT_OVER_MATLAB`. |
| TP-5 (Low) | `b0c8741` | A conversion of another profile is never joined. `FolderCache.converting_with` and `convert` refuse; Live's tick waits; Convert this folder… says which profile is converting. |
| TP-6 (Low) | `f9d0f28` | design.md §2: the modes' fallback across versions (v0.0.7a1's quick check, pre-Q~2 data). A test pins both. No code change; for Tony under Q~6. |
| TP-7 (Low) | `aa39796` | Live's "Convert with <tag>" holds only while the folder reads that one profile (`taken_convert_with`); `set_folder_list` drops it. |
| TP-8 (Low) | `66cde23` | A list that resolves to fewer entries says so: "Conversion (m19v1) › m19v1 (reads as m19v1 only)". The behaviour choice is **Q~9**. |
| TP-9 (Low) | `962838c` | No silent refusals. While a converter question is open, the items are disabled with the reason; beside becoming unavailable while the dialog is open gets a message. |
| TP-11 (Low, re-check) | `4bdfa14` | Live's tick compares the running conversion's whole profile (`converting_with(path, profile)`), as `convert` does. A same-name profile edited meanwhile now waits instead of stopping Auto-convert. The test fails without the fix. Also TP-8's nit: Folder details' line says "(reads as m19v1 only)" (`9de5e4c`). |
| TP-10 (Nit) | `70b6f27` | The summaries follow the conversion profile picked in Settings, show Folder details' "Conversion (tag)", and refresh the plot row when its folder's list changes. |

## What changed, by area (for the Reviewer)

### Model (`helab/utils/txy_sources.py`)

- **Entries and parsing:**
  - Entries are `External`, `Conversion` or a tag. A tag is lowercase, so the two words can never be one.
  - `list_of`, `parse_list` and `mode_of` convert between lists and the four modes.
  - `parse_list` reads a mode, `mode@tag`, or a list text of **at least two** entries. A lone word reads as
    "none": an old junk value such as `both` would otherwise read as "HeLab only, tag both".
- **Saved forms:**
  - `setting_text` gives the setting's form: the mode; `helab-only@m23v1` when the tag is pinned; or the list
    text.
  - `folder_row` gives the store row's form: mode + tag, or the list text with tag "".
- **Payloads:** `with_list` and `items_of` build a load's options; `payload_entries` reads them back.
- **Other helpers:** `valid_list`, `summary` ("m23v1 › m19v1 › External", "m23v1 only"), `fallback_of`,
  `origin_name`.
- **`describe`** adds the fallback ("; 3 shots from the fallback (matlab-2019 v1, External)").
- **List texts are accepted wherever a mode is**: `source_text`, `requested_source`, `source_of`,
  `source_of_choice`, `choice_tag`, `converts_over_matlab`.

### Helpers (`helab/io_ops/helab_txy.py`, `loading.py`, `live.py`, `save_held.py`, `txy_cache.py`)

- **The chain:**
  - `chain_of` builds it.
  - `find_list` runs `find` per stage, each narrowed to shots no earlier stage has a file of. This generalises
    `could_take`.
  - `_find_any` is the any-HeLab stage.
  - `compose_list` returns the chosen TXY per shot, the HeLab shots taken, and the fallback shots.
- **The held-shot rule:** exactly `choose(held=…)` for the four modes. A held shot keeps a fallback stage only
  while no entry of the own list has it.
- **Beside TXY** are kept by tag (`Beside`). A list of several entries keeps every tag.
- **Records:** for a list, `entries`, `fallback_entries` and `fallback`. `wanted_key`/`saved_wanted` include the
  fallback, so a change to Settings' list is never taken as "unchanged".
- **The view key** of a list is its text plus its entries' hashes.
- `find` gains `look_in_folders`. `on_read` gains `over_matlab`.

### App (`helab/utils/folder_cache.py`, `constants.py`, `cache_store.py`, `settings_defaults.py`)

- **FolderCache:**
  - `tab_list`, `folder_list`, `folder_own_list`, `resolved`, `set_folder_list`.
  - A plot sends `{"list": […]}`; `with_txy` resolves it.
  - `with_txy` sends `fallback`, `known` and `conversion`.
  - Profile lookups: `known_profiles` and `_profile_for_tag`; user profiles are read once and again after
    Settings saves. `profile_by_tag` is memory only.
  - Q~2.2: `auto_convert_profile` (the seam), `auto_convert_offer`, `set_convert_with`.
  - `convert(…, profile_used=)`.
- **`read_txy_source`** reads lists, through `parse_list`/`setting_text`.
- **The folder row:** `set_txy_source_pref` refuses what isn't a mode or a list. No new table or column, so
  `store_v4.migrate` is unchanged.

### UI

- **The editor** (`helab/views/txy_list.py`, new): `TxyListEditor`, `TxyListDialog`, `ask_txy_list`,
  `known_names`.
- **The three levels:**
  - `ConverterTab`: "TXY priority (tabs and Live)", its summary and Edit….
  - `FolderExplorer.choose_folder_txy`: the editor with "As Settings".
  - `plots/txy_source.TxySourceRow`: one button with the list in short; Keep unchanged.
- **The plot** (`plots/instance.py`) holds `txy_list`. `set_txy_source(mode, profile)` stays as a wrapper.
  `txy_source` and `txy_profile` are read-only properties.
- **Presets:** `TxyChoice.of_list`, `tokens` and `entries` (JSON `entries: [{entry, profile}]`). `check_txy`
  checks each entry by name, then by tag.
- **Display:**
  - `FolderDetailsPanel` names a folder's own list and adds "· N fallback".
  - `DatasetView.fallback` carries the fallback shots.
  - `results._source_text` names a list in a plot's record.
- **Live** (`explorer_live.py`): the Auto-convert part of the line says "not read here: convert with m23v1?",
  and the menu has "Convert with m23v1 (this folder reads m23v1 only)". Live's conversions go through
  `auto_convert_profile`.
- **Manual convert:**
  - `explorer_convert.py`: `ConvertFolderDialog`; `ExplorerConverter.ask_convert`, `convert_unavailable`;
    `start(…, profile)`.
  - The right-click item is in `FolderExplorer`.
  - File › Convert "<folder>"… is in `HelabMainWindow` (the menu item only).

### Paths beyond the brief's list

All were OK'd by CoCo:

- `helab/utils/constants.py` (`read_txy_source` only);
- `helab/views/txy_list.py` (new);
- `helab/views/explorer_convert.py`;
- `helab/views/HelabMainWindow.py` (menu item);
- step 2's strings in `helab/views/CacheTab.py` and `helab/utils/cache_store.py` (the inventory's "External");
- tests: `test_helabMainWindow.py` (one line), `test_accessible_names.py` (two dialog cases).

`budget_core.py` is untouched: `same_choice` keeps its signature.

## Provisional decisions (Ground to file)

- **Q~1** (Tony: yes). Convert on read only when no entry has a TXY file. It converts with the own list's
  first HeLab entry that can convert. This generalises Q50.1 (a); the modes behave exactly as before.
- **Q~2** (Tony):
  1. A multi-entry list falls back to Settings' list, then any TXY (External, then other HeLab profiles,
     newest first). A plot's chain is its own list → the folder's list → Settings' → any.
  2. A one-entry list never falls back. Live offers "Convert with <tag>" when Auto-convert's profile isn't its
     entry.
  3. Convert on read only when nothing in the chain has a file.
  4. Origins record each shot's entry; the identity stays the list's.
- **Q~3** (Tony: yes). The `Conversion` entry follows Settings' conversion profile.
- **Q~4** (Tony: build it). Convert this folder… with any profile, to HeLab's cache, its temp folder or
  beside the raw files. Right-click and the menu bar; the folder only.

## Questions for Tony (provisional numbers)

- **Q~5** "Newest profile first" in Q~2's last stage. Built as *the most recently converted TXY of each shot
  first*. The alternative is a fixed profile order (say built-ins by version, then user profiles). Proposed:
  keep.
- **Q~6** HeLab priority and MATLAB priority are lists of two, so with Q~2 they **fall back too**. A folder with
  only m23v1's TXY under the default `[Conversion, External]` now loads them as fallback (before: those shots
  weren't loaded). Identities and saved results' keys don't change. Proposed: as built (Tony's rule says every
  multi-entry list). The alternative is to treat the four modes as "no fallback".
- **Q~7** Convert this folder… beside the raw files turns the folder's beside setting **on** and leaves it on.
  The helper writes beside only while the store's flag is on, and Folder details' offer already does this. So
  Live's Auto-convert in that folder then writes beside too. Proposed: keep, and say it in the dialog's tooltip
  (done). The alternative is a one-off beside write that the helper allows for that request only (a helper
  change).
- **Q~8** Settings stores a mode with a pinned tag as `helab-only@m23v1` (the `choice_text` form), since the
  `txy_source` setting has no tag of its own. v0.0.7a1 reads it as its default, HeLab priority. Proposed: keep.
- **Q~9** (review TP-8) `[Conversion, m19v1]` with conversion m19v1 resolves to `m19v1` alone: a one-entry list,
  which never falls back. A saved `[Conversion, m23v1]` turns into one entry if the conversion profile becomes
  m23v1. Built: the summaries say "(reads as m19v1 only)". The alternative is to decide fallback on the list as
  saved (two entries or more), which needs the payload to say so. Proposed: keep as built (identity follows what
  is read).
- **Q~6 addendum** (review TP-6, design §2): a HeLab or MATLAB priority dataset may now hold fallback shots of
  other profiles. v0.0.7a1 may keep such a store-v3 dataset on a quick check until HeLab's folders change or a
  full check. This build keeps data saved before Q~2 on a quick check until a change. Nothing is mislabelled.

## Known issues (for Ground to file)

- **Found and fixed (`f944a5a`):** `tests/test_converter_tab.py::test_the_cache_tab_shows_and_clears_converted_txy`
  failed all 6 tries twice on this floor (`-n 4` runs).
  - **The cause:** it counted converted TXY in the xdist worker's temp folder (conftest's `DIR_TEMPS`, one per
    session). Any test that converts to "temp" earlier on the same worker left files there: before this
    branch, `test_explorer_convert`'s `[temp]` case; this branch's `test_convert_folder`. Each retry then hit
    `FileExistsError` on its own folder. I reproduced it in one process with either test first.
  - **The fix:** both tests use their own temp folder.
  - For known-issues: listed as Fixed.
- **Windows CI** (41587970080, job 125757887948, `bf3fb85`): one RERUN of
  `test_test_isolation::test_pytest_imports_the_checkout_it_runs_in_before_any_other`, the open pathlib `lstat`
  entry. Add this sighting.

## Follow-ups (A~)

- **A~1** Live's offer UI (the line's text, the menu item) has no widget test, only FolderCache-level ones
  (`test_a_one_entry_folder_offers_its_profile_to_auto_convert`). Add one in `test_live_convert.py`'s style.
- **A~2** `txy_sources.choose`, `helab_txy.compose` and `could_take` are kept for their tests and for MATLAB
  only (`compose(source, matlab, {})`). They could go once their tests move to `compose_list`.
- **A~3** The any-HeLab stage reads provenance records of every tag in HeLab's folders for the shots no
  earlier stage has. Only those shots are looked at, but a large folder converted with several profiles reads
  more rows than before. Time it on a lab folder (M~4).
- **A~4** File › Convert This Folder… and the right-click item are disabled while Live's Auto-convert converts
  that folder. A manual convert with another profile could instead queue after Live's conversion; that needs
  FolderCache's convert jobs keyed by profile.
- **A~5** design.md §6 (Q~2's options a/b/c) is superseded by Tony's answer, recorded under "Tony's answers"
  there.

## Manual checks (M~)

- **M~1** Tony looks at the TXY list editor in its three places: Settings › TXY converter's Edit…;
  right-click › TXY for this folder… ("As Settings"); a plot's TXY button ("As the folder's tab"). Check
  ticking, dragging and Move up/down, the summary, and OK off with nothing ticked.
- **M~2** right-click › Convert this folder… and File › Convert "<folder>"…: pick m23v1, then each destination.
  On a share, beside asks first. The Folder details row shows progress "with m23v1".
- **M~3** Live in a folder whose list is "m23v1 only" with Auto-convert on m19v1: check the line's "not read
  here: convert with m23v1?" and the menu item. Taking it converts with m23v1.
- **M~4** A real folder with External, m19v1 and m23v1 TXY under `m23v1 › m19v1 › External`. Check the
  shots' origins in a plot's record, and Folder details' "· N fallback" when a list misses some shots. Also
  check timing on a large folder (A~3).

## Proposed doc changes (for Ground)

- **`converter.md` › TXY sources:** rewrite around lists.
  - The tokens, the mode ↔ list map, the identity rule, and the saved forms (setting: mode, `mode@tag` or list
    text; folder row: mode + tag or list text; presets: `entries`).
  - Q~2's chain; Q~1/Q~2.3's convert on read; the External label (Q53.1).
  - Convert this folder… (Q~4) under "Profiles in the app" or a new subsection.
- **`cache-store.md`:**
  - `txy_source_prefs` holds a mode + tag or a list's text; no schema change, and the store refuses junk.
  - `txy_views`' key for a list is (its text, its entries' hashes joined by `>`).
  - The `txy` record's `entries`, `fallback_entries` and `fallback`.
  - "Convert on read (stage 3)": Q~1/Q~2.3 replace "Under HeLab priority only the shots MATLAB's TXY lacks".
- **`plots-and-scripts.md`:**
  - The TXY row is one button opening the list editor; the plot holds `txy_list`.
  - `TxyChoice`'s `entries`, and `check_txy` for lists.
  - `DatasetView.fallback`, and `describe`'s fallback text.
- **`settings.md`:** the `txy_source` row's values (mode, `mode@tag`, list text), and Settings › TXY converter's
  "TXY priority".
- **`live.md`:**
  - Live reads with its folder's list.
  - Auto-convert converts with `auto_convert_profile`: Settings' profile, or the one-entry list's after the offer
    while the list stays so (Q~2.2, TP-7).
  - It waits while a conversion of another profile runs (TP-5).
- **`io-and-browsing.md`:**
  - Loads, Live checks and saves compose with `find_list`/`compose_list` (the chain; the held-shot rule).
  - A shot held from a fallback stage is reclaimed by an own entry in loads and Live (read again, External
    feeding the mismatch rule meanwhile), never in Live's save (`reclaim=False`, TP-3).
  - The helper's store-v4 folder-row step resolves tags with `tag_lookup` (TP-1).
  - FolderCache's profile lookups are memory only (TP-2).
- **`app-runtime-and-ui.md`:** right-click › Convert this folder… and File › Convert "<folder>"…, and the TXY
  list editor.
- **`roadmaps/txy-priority.md`:** status built (Q53.1, Q53.2, Q~1–Q~4), with the open Q~5–Q~8.
- **AGENTS.md (one line, under Analysis and plots or Converter):** "A TXY choice is a priority list
  (`txy_sources`); a list that is one of the four modes keeps that mode's saved form and identity exactly."
