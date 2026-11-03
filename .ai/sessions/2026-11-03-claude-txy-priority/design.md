# Design: TXY priority lists (block 53)

Worker: Claude (Opus 5.5), floor TXY Priority, `agent/txy-priority` from `dcc02d8`. Step 1 of the brief. Proposals
are numbered provisionally (`Q~n`); where this differs from the plan's design notes it says so.

## 1. The list

### Entries

A **TXY list** is an ordered tuple of distinct entries, at least one. An entry is one of:

| Entry | Token in text | Means |
|---|---|---|
| External | `External` | MATLAB's `d_txy_forc<N>.txt` (label "External (MATLAB converter)", Q53.1) |
| A HeLab profile | its file tag, e.g. `m23v1`, `u3f…` | HeLab's `d_txy_helab_<tag>_<N>.txt` of that profile |
| The conversion profile | `Conversion` | the profile Settings › TXY converter converts with, resolved to its tag when a load is asked for |

Tokens are case sensitive. A tag is `[a-z][a-z0-9]{1,32}` (`profile.NAME_TAG`, lowercase only), so the two
capitalised words can never be a tag: the text needs no escaping and no prefix.

**`Conversion` is new (differs from the plan).** The plan writes HeLab priority as `[HeLab <conversion tag>,
External]`. Today the `txy_source` setting, a folder row with tag "" and a plot's `TxyChoice` with profile ""
all *follow* the conversion profile: change it in Settings and tabs read the new profile's TXY. A list naming a
fixed tag can't express that, so migrating `helab-priority` to `[m19v1, External]` would change behaviour
the first time someone changes the conversion profile, and Live would then convert with a profile the tab
doesn't read (Q~2). With `Conversion`, the default list is `[Conversion, External]`, exactly today's default,
and the UI shows it as "Conversion profile (m19v1)". The user can still pin `m19v1` explicitly. **Q~3**
(below) asks Tony whether to keep this entry.

### Text form

Entries joined by `>`: `m23v1>m19v1>External`, `Conversion>External`. Summaries in the UI use ` › ` and short
names: "m23v1 › m19v1 › External", "Conversion (m19v1) › External".

### Where it is stored: old form when it fits, list text otherwise

Every place that saves a choice today keeps its exact old value for the four modes, so nothing already saved
changes, and an older v0.0.8 dev build reads what it can:

| Place | Today | A list equal to an old mode | Any other list |
|---|---|---|---|
| `txy_source` setting (no tag; follows the conversion profile) | `helab-priority` … | the mode, when its HeLab entry is `Conversion`; else the mode and its tag, `helab-priority@m23v1` (`choice_text`'s form) | the list text (`m23v1>m19v1>External`) |
| store-v4 `txy_source_prefs` (`source`, `tag`; tag "" follows) | mode + tag | mode + tag (`Conversion` ↔ tag "") | `source` = list text, `tag` = "" |
| `TxyChoice` in presets, arrangements, reopened plots (`source`, `profile`, `tag`) | mode + profile name + tag | as today | `source` = list text, plus a new `entries` field: `[{"tag", "profile"}…]`, External as `{"external": true}` (each HeLab entry keeps its profile name, so `check_txy` can find a renamed profile by tag as it does now) |

The mode ↔ list map (`txy_sources.mode_of` / `list_of`), with `T` a tag or `Conversion`:

| Mode | List |
|---|---|
| `helab-priority` @T | `[T, External]` |
| `matlab-priority` @T | `[External, T]` |
| `helab-only` @T | `[T]` |
| `matlab-only` | `[External]` |

Every list of one or two entries with at most one HeLab entry is a mode, so **a list text that isn't a mode
always contains `>`**: it never collides with a mode name or the legacy `matlab`/`helab` values. Parsing:
legacy name → mode; `mode@tag` → that mode with that tag; else split on `>`, **at least two entries**, each
token checked; a text that parses to nothing is "none" (falls back to the default, as an unknown mode does
today). *(Changed while building, `@`-form added:* a lone word such as an old junk value `both` matches the tag
pattern, so a one-entry list text would have read it as "HeLab only, tag both"; a one-entry list is always a
mode, and the setting writes a pinned one as `helab-only@m23v1`.)

**No schema change.** `txy_source_prefs.source` is `TEXT`; the list text fits it. So `store_v4.migrate` gains
nothing, and the "added column through `migrate`" rule isn't triggered. (If CoCo prefers a dedicated column,
it goes through `migrate`; I see no need.) An older dev build reading a list text sees no valid source and
follows Settings; it never misreads it as another mode.

**Store-v3 fallback:** the global setting and plot choices work unchanged (they aren't in the store);
per-folder rows stay store-v4 only, as now (`set_txy_source_pref` needs v4; the right-click item stays hidden
or disabled as today).

## 2. Identity rule

Identities are always computed on the **resolved** list: `Conversion` replaced by the conversion profile's tag,
then duplicates dropped (first kept). For a plot "As the tab", the tab's list resolved the same way.

- A resolved list that is a mode gets **that mode's identity, unchanged**: `identity_source` "" for both
  priority modes, `helab-only`, `matlab-only`; `choice_text` `helab-priority@m19v1` etc.; view key
  `(identity, profile hash)` (`txy_cache.view_key`); saved-result key `txy_source` absent for "" as now. So
  existing caches, store-v4 views and layers, presets and saved results stay valid. Tested exhaustively for
  every mode × `Conversion`/explicit tag (explicit `m19v1` and `Conversion` resolving to `m19v1` must give
  byte-identical identities, choices and keys).
- **Any other list** gets its own identity: its resolved text, e.g. `m23v1>m19v1>External`. That text is the
  `identity_source` (`ViewIdentity.source`, results' `txy_source`), the `choice_text` (`DatasetView.txy_choice`,
  dataset keys `|txy=…`), and the view key `(text, ">"-joined profile hashes of its HeLab entries)` so a view is
  bound to profile contents as the mode views are.
- `same_choice` keeps its rule ("" ↔ a priority mode's); a list never matches another list's text but its own.
- `source_of_choice` / `source_of` learn list texts (today any unknown text reads as MATLAB priority).
- Shots' origins stay `""` (External) and `helab:<hash>`. Two HeLab entries with one hash (`m19v1` and
  `p22v1` today) give the same origin; their TXY are byte-identical by contract, so that's correct.

The dataset's `txy` record keeps `source` (the mode, or the list text), `profile_tag` (the mode's tag; "" for a
list) and gains `entries` (the resolved list with each HeLab entry's hash), so a list dataset says what it was
asked for and the old fields mean what they meant.

### What v0.0.7a1 makes of a list (CoCo's gap; checked against `e03c32a`, main's 0.0.7a1 commit)

The store-v3 fallback saves datasets and results where v0.0.7a1 reads them, and both share the native
settings. Its `txy_sources` is today's minus stage 3 (diffed), so:

- **The `txy_source` setting holding `m23v1>External`:** `read_txy_source` → `normal_source` gives None →
  the default, HeLab priority; its Settings combo shows "HeLab's where made, MATLAB's for the rest". No data is
  misread: 0.0.7 loads what it shows. Pressing Save in 0.0.7's Settings writes its mode over the list (an old
  app rewriting a value it doesn't know; the list is then gone, nothing else). A single-entry or mode-shaped
  list is stored as its mode, which 0.0.7 reads exactly.
- **A store-v3 dataset saved under a list:** its record's `source` is the list text, which 0.0.7's
  `normal_source` doesn't know.
  - Both quick paths (`_unchanged_since_cache`, `_unchanged_since_memory`) go through `_helab_unchanged`, which
    returns False when `normal_source(saved.source) != source`: 0.0.7 never takes the list data as current
    without a full check.
  - The cache-first read (`read_cached`) sends the row as it is, and `FolderCache._with_choice` relabels a
    record whose source it doesn't know with the tab's source. So for the moment before the check, 0.0.7 shows
    the list's data as its tab's, marked not yet checked, the same as it already shows a tab dataset saved under
    another of the four modes after a Settings change.
  - The check-load then counts a held shot as held only when its origin equals what 0.0.7 composes
    (`held_origins == origins`, unchanged): every shot the list took from another entry (another HeLab hash, or
    External where 0.0.7 wants HeLab's) is read again; shots a list without External left out come in as new.
    The data 0.0.7 ends with is its own choice's. Only MATLAB's TXY feed its mismatch rule, as here.
  - Per-shot origins keep their format (`""` absent, `helab:<hash>`), which is all those checks read.
- **A store-v3 result saved under a list:** its key carries `txy_source: "m23v1>External"`; 0.0.7 reuses a
  result only on an exact key match (`result_cache.lookup_key`), and its own keys carry "" (absent),
  `helab-only` or `matlab-only`: never a match. Its record text would read "TXY source: HeLab or MATLAB
  priority" (`SHORT.get` default), with the HeLab shot count from the origins; display only. A result made in
  0.0.7 from the brief relabelled data is keyed by those shots' true origins, so it is reused only on the same
  data.

So lists can be saved into store-v3 like the modes; no need to keep them out. **Pinned by
`tests/test_txy_priority_v007.py`:** a verbatim copy of 0.0.7a1's `normal_source`, `_helab_unchanged`'s
source check, `_with_choice`'s relabel and `read_txy_source`, run on records, settings values and result keys
the new code makes for several lists: no list text is a 0.0.7 source, the quick check says "changed", the
relabel lands on the tab's source, origins are in the old format, the setting reads as the default, and no
list's result key equals an old mode's.

## 3. Migration

- **Setting `txy_source`:** read as a list (`read_txy_source` → `txy_sources.read_list`): a mode or legacy
  value maps as above; a list text parses; anything else is the default `[Conversion, External]`. Written
  in old form when it fits (a mode whose HeLab entry is `Conversion`). The `settings_defaults.py` row keeps
  its key and default (`helab-priority`) and its description says it may hold a list.
- **Folder rows:** `read_folder_choices` returns the row as now; `FolderCache` and `with_choices` read
  `source` + `tag` as a list (mode + tag "" → `Conversion`; mode + tag → that tag; list text → list).
- **Presets, arrangements, reopened plots:** `TxyChoice.from_json` reads old records as before; a record with
  `entries` reads the list. `check_txy` checks each HeLab entry's profile by name then tag as today; one entry
  unknown → the choice isn't applied (the plot is as the tab), with the problem naming that entry, never
  dropped silently.
- **Saved results, views, layers:** nothing to migrate (identity rule).

## 4. The per-shot choice

For each shot, walk the resolved list and take the **first entry with a usable TXY**:

- External: the listed `d_txy_forc<N>.txt`.
- HeLab tag T: a current HeLab TXY of T (`helab_txy.find`, per tag: HeLab's folders by provenance, beside by
  name and date). Inside the entry, the order is Q50.5's: its TXY layer entry, the raw layer, the text,
  converting the raw file.

As today, a chosen file that is still being written (settle time, future date, changing while read) leaves the
shot out of this load, to come in whole at the next; it **never falls through to a later entry** (that would
make a shot flip between entries from one load to the next). A damaged text is never used (Q50.5): its rows are
problematic as today.

Mechanics: `find` runs once per HeLab entry (each with its tag, hash, profile), narrowed by `only` to shots no
earlier entry has (the generalisation of `could_take`: MATLAB priority's narrowing becomes "after External,
only shots External lacks"), so a check reads no record of a shot an earlier entry wins. Beside entries are
kept per wanted tag (`beside_wanted` takes the list's tags). `compose` becomes one function over the list.

Unchanged: only MATLAB's TXY feed the folder-mismatch rule and the folder's signature; a list without External
leaves out shots that only External has (not missing; counted as removed, as HeLab only does, Q38.3); Live's
held-kind rule generalises to "a held shot keeps its entry while that entry is in the list and its TXY is
there" (for the four modes this is exactly today's `choose(held=…)`).

## 5. Convert on read under a general list — **Q~1**

Today (Q50.1 (a)): HeLab priority converts on read only shots MATLAB lacks; HeLab only converts every raw shot
without HeLab text; MATLAB's modes convert only shots MATLAB lacks (MATLAB priority) or none (MATLAB only).

**Proposed rule (generalises (a) exactly):** a shot is converted on read **only when no entry of the list has a
usable TXY file for it**, and then with the **first HeLab entry that can convert** (a built-in, or a profile
sent whole: the conversion profile today). A layer entry an earlier on-read conversion left counts as that
conversion's cache, not as a file. So a raw file that can't be converted now (settling, damaged) never costs a
shot a TXY any entry has, earlier or later.

Check against the four modes: `[T, External]` converts shots External lacks; `[External, T]` the same;
`[T]` every raw shot without T's text; `[External]` none: today's behaviour in all four. `CONVERT_OVER_MATLAB`
keeps its meaning (on: External no longer blocks conversion for the HeLab entry before it).

Not proposed (Q50.1 (b) generalised, "only if Tony asks"): convert for an entry ahead of later entries that have
files, falling back to them when conversion fails.

Example, `[m23v1, m19v1, External]`, a shot with an m19v1 text and a raw file: m19v1's text (no conversion
with m23v1). A raw-only shot: converted with m23v1 (a built-in), saved as m23v1's layer entry.

## 6. Live and Auto-convert — **Q~2**

Live reads with its folder's list (folder row, else Settings). Auto-convert writes text with the conversion
profile (Settings), unchanged; Q50.6's on-read conversion during Live follows §5 (the list's first convertible
HeLab entry).

When the **resolved list doesn't contain the conversion profile's tag**, converted text is never read by this
folder's tab. Options:

- (a) **proposed:** convert as now; the Live line's Auto-convert part adds "(not read here)", amber-free, and
  its tooltip says "Converts with m19v1, which this folder's TXY list (m23v1 › External) doesn't read; the
  TXY are kept for other lists and plots." Nothing is blocked.
- (b) Auto-convert converts with the list's first HeLab entry instead (a second "conversion profile" per
  folder: more surprising, and provenance/beside rules assume Settings' profile).
- (c) Refuse Auto-convert on such a folder, with that message.

With `Conversion` in the list (the default), this never happens.

## 7. UI

**One control, `TxyListEditor`** (new module, see paths), used in three places:

- A list of rows, each a checkbox and a name: "Conversion profile (m19v1)", "External (MATLAB converter)",
  then every built-in and user profile as "matlab-2023-lab-edit (m23v1)". Ticked rows are the list, in their
  order; drag to reorder (and Move up / Move down buttons, for keyboard use and tests). At least one ticked
  (OK disabled otherwise, with a one-line hint).
- At the top, the follow choice: "As Settings" (folder dialog), "As the folder's tab" (plot), absent in
  Settings. Choosing it greys the list and shows what it follows.
- A one-line summary under it ("m23v1 › m19v1 › External"), detail in the tooltip.
- Every control `identify`d: `txy_list`, `txy_list_follow`, `txy_list_up`, `txy_list_down`, per-row names.

Places:

1. **Settings › TXY converter:** "Tabs and Live read" becomes "TXY priority" with the summary and an
   "Edit…" button opening the editor in a small dialog (the tab's grid stays one line high).
2. **Right-click › TXY for this folder…:** the editor in a dialog, "As Settings" at the top (store-v4 only,
   the folder only, not its subfolders, Q50.11). Replaces the two `QInputDialog` picks.
3. **Each plot's TXY row:** the source and profile combos become one button showing the summary ("As the tab
   (Conversion › External)" or "m23v1 › External") that opens the editor with "As the folder's tab"; Keep
   stays and still decides whether the choice is saved. The conversion-profile/plate note line stays.

Summaries elsewhere (Folder details' choice line, the folder row tooltip's choice, a plot's record
"TXY source: …", `describe`'s "TXY: …"): the short list form; "MATLAB's" becomes "External's"/"External"
per Q53.1 (step 2), e.g. "TXY: HeLab's (m23v1 v1) for 3 of 10 shots, External for the rest".

## 8. Tests

- `test_txy_sources.py` (unit, pure): parse/text round trips; legacy and mode values; every mode × tag form
  ↔ list; the identity table (old modes byte-identical choices, identities, view keys, result-key fields;
  `Conversion` ≡ the explicit tag it resolves to); dedupe; invalid texts; per-shot choice over 3+ entries
  with held origins; §5's rule against the four modes and two general lists.
- Settings: `read_txy_source` for old values, list texts, junk; writing old form when it fits.
- Store-v4: `set_txy_source_pref` with a list text round trips; an old (source, tag) row reads as its list;
  store-v3 unaffected.
- Loads (`test_txy_loading.py`, `test_load_sources.py` style, temp folders only): a folder with External, two
  HeLab profiles' TXY and raw-only shots under `[m23v1, m19v1, External]` (each shot from the right entry,
  origins right, raw-only converted with m23v1 under store-v4, none under store-v3); the four modes give the
  same identities and data as before; a settling first-entry file leaves the shot out.
- Live: a held shot keeps its entry; a list without the conversion profile and Auto-convert's line (Q~2).
- Presets/arrangements: an old record opens unchanged; a list record round trips; an unknown entry is a
  problem, not a silent drop.
- Plots: a plot's own list beside the tab's (own dataset, own key); "As the tab" follows the folder's list.
- UI: the editor (tick, order, follow, OK disabled when empty), accessible names (`test_accessible_names.py`).
- Integration (step 5) as the brief lists, store-v4 on, plus one run with `store_v4=false`.

## 9. Paths beyond the brief's owned list (asking CoCo)

- `helab/utils/constants.py`: `read_txy_source` (reads the setting as a list; one function).
- `helab/views/txy_list.py` (**new**): the shared `TxyListEditor` and its dialog.
- `helab/analysis/budget_core.py`: only if `same_choice`'s signature changes (I aim to keep it, then no edit).
- `helab/views/HelabMainWindow.py:931` calls `set_tab_source(read_txy_source(...))`; unchanged if
  `set_tab_source` takes the text, which is my plan.
- Step 2's label may touch strings in `helab/views/CacheTab.py`/`FolderSummary`/tooltip builders if they say
  "MATLAB's"; I'll list them before editing.

## Tony's answers (via CoCo, 2026-11-03)

- **Q~1:** yes, as proposed (built).
- **Q~3:** yes, keep the `Conversion` entry (built).
- **Q~2:** not (a). Direction (exact rule being confirmed): if Auto-convert wrote m19v1 and the folder's list
  is `m23v1 › External`, the folder still reads the m19v1; only a one-entry list (m23v1 only) offers to
  convert with m23v1. Not built yet; the seam is `FolderCache.auto_convert_profile(path)` (today Settings'
  conversion profile) and `FolderCache.convert(…, profile_used=)`, which Live's Auto-convert goes through
  and the coming "Convert this folder…" can use.

## Questions (provisional)

- **Q~1** Convert on read under a general list: only shots no entry has a file for, with the first convertible
  HeLab entry (§5). Proposed: yes.
- **Q~2** Live and Auto-convert when the conversion profile isn't in the folder's list: convert as now and say
  "(not read here)" on the Live line with a tooltip (§6 (a)). Proposed: (a).
- **Q~3** Keep a `Conversion` entry that follows Settings' conversion profile (§1), so the default and every
  saved mode keep following it as they do today. Proposed: yes; the alternative pins tags at migration and
  changes behaviour on the next profile change.
