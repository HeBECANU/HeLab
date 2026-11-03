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
- **CI:** not pushed yet. I push at this checkpoint after CoCo's word.

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
- **`live.md`:** Live reads with its folder's list; Auto-convert converts with `auto_convert_profile` (Settings',
  or the one-entry list's after the offer, Q~2.2).
- **`io-and-browsing.md`:** loads, Live checks and saves compose with `find_list`/`compose_list` (the chain; the
  held-shot rule).
- **`app-runtime-and-ui.md`:** right-click › Convert this folder… and File › Convert "<folder>"…, and the TXY
  list editor.
- **`roadmaps/txy-priority.md`:** status built (Q53.1, Q53.2, Q~1–Q~4), with the open Q~5–Q~8.
- **AGENTS.md (one line, under Analysis and plots or Converter):** "A TXY choice is a priority list
  (`txy_sources`); a list that is one of the four modes keeps that mode's saved form and identity exactly."
