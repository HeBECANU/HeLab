# Review: TXY priority lists, External label, manual convert (block 53)

Reviewer: Claude (Opus 5.5), floor TXY Priority, landing review of `agent/txy-priority`, `git diff dcc02d8..cca4649`
(16 commits, 38 files). Read: brief.md, design.md (with Tony's answers to Q~1–Q~4), handoff.md, and the whole diff.

## Checks rerun

- Full suite: `pytest -n 4 --reruns 5 --reruns-delay 1 --basetemp=.ai/temp/pytest-review` at `cca4649`:
  **9217 passed, 673 skipped, no RERUN** (154 s).
- Type checks, all clean: `mypy helab/ --strict`, `mypy tests --strict`, `pyright helab tests`,
  `mypy helab/ --strict --platform win32`, `pyright --pythonplatform Windows helab tests`.
- CI: I did not re-read run 41583803573's logs; the handoff says it read all 12 jobs' logs and found no RERUN.

## Verdict

**One blocker (TP-1, High)**: a folder row that names a user profile loads the wrong profile's TXY in the helper.
TP-2 (Medium, an I/O-rule breach) and TP-3 (Medium, a test gap on Live) should be fixed before landing too. The
rest are Low or Nit and can go to AI_TODO or known-issues.

What holds up, checked against the code:

- **The identity rule.** A list equal to a mode goes through `with_list` as exactly that mode. Its payload, `choice_text`,
  `identity_source`, view key and result key are unchanged, and `Conversion` behaves the same as the explicit tag it
  resolves to (`test_the_four_modes_keep_their_identities_exactly`, and the session test's `strip` comparison). Any other
  list's text contains `>`, so it can never collide with a mode or a legacy value. Settings, the folder row and
  presets keep their old forms for modes.
- **Q~2's chain** (`chain_of`, `find_list`, `compose_list`): own list → `fallback` (folder's, then Settings') →
  External → any-HeLab. Each stage looks only at shots no earlier stage has. A one-entry list has no chain. The
  fallback shots are recorded (`fallback`, `fallback_entries`), and `wanted_key` includes them, so a changed
  Settings list is never taken as unchanged.
- **Convert on read (Q~1, Q~2.3).** `on_read` gets every stage's texts and External's shots (External is always in a
  multi-entry chain). So a shot is converted only when no stage has a file of it, and with the first convertible
  own HeLab entry. A one-entry list converts as HeLab only did. No stage's TXY is ever lost to a conversion.
- **store-v3 / v0.0.7a1 with list texts.** `test_txy_priority_v007.py`'s copies match `e03c32a`'s `normal_source`
  and `read_txy_source` (I diffed them). List texts never read as a 0.0.7 source, and result keys never match.
  TP-6 covers the one case the analysis predates: the modes' fallback.
- **Convert this folder… (Q~4).** It runs in the helper through `FolderCache.convert(profile_used=)`, and
  `convert_lists` is keyed by profile, so another profile's `done` list doesn't skip shots. The helper's convert
  rules are unchanged (temporary name and rename, never over an existing TXY). Beside on a share asks first
  (`confirm_beside_on_share`). The beside flag is turned on and left on, as Folder details' offer does (Q~7, open
  for Tony).
- **UI.** Every new control is `identify`d: the editor (`txy_list*`), the Converter tab's `tabs_txy_list`, the plot's
  `txy_source` button and the convert dialog's `convert_folder_*`. Both new dialogs are in
  `test_accessible_names.py`'s walk. No lambda captures a Qt-made sender.

## Findings (most severe first)

### TP-1 — High — the helper's folder-row step rewrites a user-profile entry to the conversion profile

`helab/io_ops/loading.py:313` and `helab/utils/txy_sources.py:410` (`with_list`).

Under store-v4, `load` reads the folder's row again and calls `with_choices(txy, row, txy_cache.builtin_for_tag)`
over the options FolderCache already resolved. FolderCache now resolves user profiles (`_profile_for_tag`), and the
editor offers them (`known_names()`). The helper only knows the built-ins, and `with_list` first overwrites `txy`'s
profile with `conversion`'s. The result:

- **Mode row** (`helab-only` or `helab-priority`, tag a user profile `u3f`): when `profiles("u3f")` is None, the
  "keep the profile asked for" fallback keeps the *conversion* profile, not the user profile FolderCache sent.
  Reproduced:
  ```
  app   : helab-only HUSER u3f
  helper: helab-only H19 m19v1
  ```
  So the tab loads m19v1's TXY, records the choice `helab-only@m19v1`, and Folder details says the folder reads `u3f`.
  Live (`live_check`, which has no row step) reads `u3f`. The load and Live then disagree about the same folder.
- **List row** (`u3f>m23v1>External`): the helper rebuilds `entries` with `u3f`'s `profile_hash` "". Its beside TXY
  are skipped (`find` needs a hash beside), and HeLab-folder TXY of an older version of `u3f` count as current.

Before this branch both sides fell back to the conversion profile for a user tag, so they agreed. This is a
regression of the new user-profile support. The session test uses built-ins only, so it passes.

Fix: have the helper's `profiles` callable also look in `txy["known"]` (FolderCache already sends user profiles by
tag), and/or keep the entries and profile already in `txy` for a tag the helper can't resolve. Add a test: a
store-v4 tab load (`loading.load`) of a folder row naming a user profile, as a mode and as a list.

### TP-2 — Medium — a tree tooltip can read the profile folder from disk (I/O rule: rendering reads memory only)

`helab/models/SnapshotFileSystemModel.py:516` → `FolderCache.on_read_shots` → `converts_on_read` →
`folder_source` → `resolved` → `with_list` → `_profile_for_tag` (`helab/utils/folder_cache.py:1170`).

`_profile_for_tag` reads `ProfileLibrary(profiles_folder()).profiles()` when `_user_profiles` is None. That is true
until the first load, and again after every Settings save (`set_convert_profile` resets it, line 1007). The tag must
be one that isn't a built-in or the conversion profile, which is exactly a folder list naming a user profile. The
folder row tooltip (`_on_read_text`) then reads and parses JSON files on the GUI thread while rendering. It is the
local app folder, not a source folder, but AGENTS.md says "models, badges, tooltips and summaries read memory only".
`instance.txy_choice()` (`resolved`) has the same path, outside rendering.

Fix: read the user profiles off the render path (when Settings saves, and at start), and make `_profile_for_tag`
memory only, as `profile_by_tag` already is.

### TP-3 — Medium — no test of Live's check or `save_held` under a general list or the fallback

`tests/test_txy_priority*.py` never call `live_check` or `save_held`. The existing Live tests exercise those
functions' new `find_list`/`compose_list` path only for the four modes. Untested:

- the list-specific held-shot rules in `compose_list`: a shot held from a fallback stage taken back when an own entry
  now has it; a held `helab:<hash>` found in a later stage;
- `live.py`'s rewritten `switching` (`helab_found.get(shot) is unheld_shots.get(shot)`);
- `record(..., fell_back, shots)` from Live and from `save_held`;
- on-read conversion in Live with a list (`listed_found.converting`).

The design's §8 promised "Live: a held shot keeps its entry; a list without the conversion profile". The handoff's
A~1 covers only the offer's widget. Add at least one `live_check` test under `m23v1 › m19v1 › External` with held
shots (including one from the fallback), and one `save_held` test checking the record's `fallback`.

### TP-4 — Low — `converts_over_matlab` disagrees with `find_list` for a multi-entry list without External

`helab/utils/txy_sources.py:244`, used by `FolderCache.on_read_shots` (`helab/utils/folder_cache.py:1122`).

For `m23v1>m19v1` it returns True ("External isn't in it"), but Q~2 puts External in the chain, and `find_list`
then blocks shots External has (`over_matlab` False unless `CONVERT_OVER_MATLAB`). So the folder tooltip's "N
converted when loaded" counts every raw file instead of `raw - txy`. That is display only, until the first load
counts. `tests/test_txy_priority.py:118` pins the wrong value. Fix: True only for a one-entry list without External
(or with the flag, as for HeLab priority), matching `find_list`.

### TP-5 — Low — Live's Auto-convert joins a running Convert this folder… of another profile

`helab/utils/folder_cache.py:2605` (`job_key("convert", path, …)` ignores the payload's profile).

`convert_unavailable` keeps the manual convert from starting while Live converts. The reverse isn't guarded: with a
manual conversion running with m23v1, Live's tick (`cache.convert(profile_used=m19v1)`) joins that job. Live then
reports m23v1's results (counts, low-hit notifications) as its own, and converts with m19v1 only on a later tick.
A~4 covers the other direction only. Fix: have Live skip the tick while `converter.conversions[path]` runs, or key
convert jobs by profile. Or extend A~4 and list it in known-issues.

### TP-6 — Low — the modes' fallback (Q~6) isn't in design §2's cross-version analysis

Under Q~2, HeLab priority and MATLAB priority datasets can hold fallback shots of other profiles (origins
`helab:<other hash>`) with `source` still the mode. Two effects, neither covered by `test_txy_priority_v007.py`:

- **v0.0.7a1 on a store-v3 dataset.** Its `_helab_unchanged` sees the same source and profile, so when HeLab's
  folders are unchanged it takes the dataset as current. It then shows shots its own composition would leave out.
  They are labelled correctly by origin, so no data is mislabelled, but it is a difference from the "0.0.7 ends with
  its own choice's data" conclusion.
- **This build on data saved before the branch.** Such data has no `fallback_entries`, and `wanted_key` matches it
  when there is no folder list. So the quick check can keep pre-Q~2 data, and the fallback shots appear only after a
  change or a full check.

Proposed: record both under Q~6 for Tony, and add a line to design §2 / converter.md. No code change needed if Tony
accepts.

### TP-7 — Low — Live's "Convert with <tag>" choice outlives the folder's list

`helab/views/explorer_live.py:758`, `FolderCache.convert_with`.

`convert_with` isn't cleared when the folder's list changes (`set_folder_list`). After the user changes the list to,
say, `m19v1 › External`, Auto-convert still converts with m23v1 for the session. The menu still shows the item ticked
with "(this folder reads m23v1 only)", which is now false. Fix: drop the entry in `set_folder_list`, or show the
item only while the list is still one entry of that tag.

### TP-8 — Low — `Conversion` plus the tag it resolves to collapses to a one-entry list

`helab/utils/txy_sources.py:140` (`resolve`), `helab/io_ops/helab_txy.py:385` (`chain_of`), the editor in
`helab/views/txy_list.py`.

The editor accepts `[Conversion, m19v1]` with conversion m19v1. That resolves to `(m19v1,)`: HeLab only, which never
falls back (Q~2.2), while the summary shows two entries ("Conversion (m19v1) › m19v1"). Similarly, a saved
`[Conversion, m23v1]` silently turns from a fallback list into a one-entry list when the conversion profile becomes
m23v1. Proposed: decide fallback on the list as saved (two entries or more), not as resolved, or have the editor
warn about the duplicate. This is Tony's call if it changes what users see; it could go with Q~6.

### TP-9 — Low — two silent refusals in Convert this folder…

`helab/views/explorer_convert.py:425`, `:445`.

`ask_convert` returns None without a word when another question box is open (`self.box is not None`). The menu
items are enabled, so the click does nothing. `_convert_answered` only logs when beside became unavailable while
the dialog was open. The module's rule is "never a silent refusal". Fix: show a one-line message (or disable the
items while a box is open), and answer the beside case like `ask_after_refusal`.

### TP-10 — Nit — stale summaries

- `ConverterTab.set_txy_entries` (`helab/views/ConverterTab.py:287`): "Conversion (m19v1)" isn't refreshed when the
  profile combo changes before Save.
- `FolderDetailsPanel._with_choices` calls `summary(entries)` without the conversion tag, so it shows a bare
  "Conversion", while the plot row and Settings show "Conversion (m19v1)".
- `TxySourceRow.set_entries` shows "As the folder's tab (…)" with the folder list as it was when last set. It
  doesn't follow a later change of the folder's list until the plot updates its row.

## Doc changes the handoff should also propose

- converter.md / io-and-browsing.md: the helper's folder-row step (`with_choices`) and how it treats user profiles
  (after TP-1's fix).
- known-issues: the `test_converter_tab.py::test_the_cache_tab_shows_and_clears_converted_txy` failure the handoff
  saw once (6 tries) should be listed. AGENTS.md lists every RERUN or repeated failure until its cause is found, and
  the handoff only proposes it conditionally.
- The Q~6/TP-6 and TP-8 points for DECISIONS_TODO, beside Q~5–Q~8.
