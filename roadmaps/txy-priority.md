# TXY priority lists

Horizon: v0.0.8 (Tony, 2026-11-03, Q53.3). Added: 2026-11-03, from Tony in the terminal (block 53:
Q53.1–Q53.3, decided). **Status:** built and landed (`9bf99ff`, the TXY Priority floor from `dcc02d8`; CI
41590741400 green), with Q55.1–Q55.8 decided (Tony, 2026-11-03) and Q55.9 open; see "As built" below. Priority and completion: [overview](_readme.md). Related: [TXY converter](txy-converter.md),
[caching v2](caching-v2.md); how sources work today: `helab/utils/txy_sources.py` and
[converter.md](../.ai/architecture/converter.md).

## Purpose

Today a load asks for one of four **sources** (HeLab priority, MATLAB priority, HeLab only, MATLAB only)
and, for HeLab's TXY, one profile tag. Tony wants any order of any profiles: "instead of helab priority or
matlab priority, we can select any profile priority too", chosen globally, per folder and per plot "for
maximum creative freedom" (Q53.2).

## Decided

- **Q53.1, the label:** MATLAB's `d_txy_forc<N>.txt` is called **"External (MATLAB converter)"** wherever
  the UI names it (sources' labels and short names, Settings › TXY converter, right-click › TXY for this
  folder…, plots' TXY rows, Folder details, tooltips). Only the label: the files keep their names (HeLab
  never renames or modifies an existing TXY, AGENTS.md), and HeLab's own profiles named `matlab-2019` /
  `matlab-2023-lab-edit` (HeLab's reproduction of MATLAB's converter) keep theirs.
- **Q53.2, priority lists at three levels:** a TXY choice is an **ordered list of entries**, each
  `External (MATLAB converter)` or HeLab's TXY of one profile (by tag: built-in or user profiles). Each shot
  takes the first entry that has a usable TXY for it; a one-entry list is the old "only". It can be set:
  - **globally** (Settings › TXY converter, replacing "Tabs and Live read", the `txy_source` row);
  - **per folder** (right-click › TXY for this folder…, replacing the source + tag picks; "As Settings"
    stays; the folder only, not its subfolders, as Q50.11);
  - **per plot** (each plot's TXY row, `helab/views/plots/txy_source.py`; "As the tab" stays).
- **Q53.3:** in v0.0.8, before the PR to `main` (0.0.8a1, Q47.5).

## As built (landed `9bf99ff`; block 55)

The floor's [handoff](../.ai/sessions/2026-11-03-claude-txy-priority/handoff.md) and
[design](../.ai/sessions/2026-11-03-claude-txy-priority/design.md); mechanics in
[converter.md](../.ai/architecture/converter.md#txy-priority-lists).

- **The label** (Q53.1): "External (MATLAB converter)", "External" in short; only the labels changed.
- **Lists** (Q53.2): entries `External`, a profile's tag, or `Conversion` (Settings' conversion profile, resolved
  when a load is asked for; Q55.3). Set in Settings › TXY converter, right-click › TXY for this folder… and each
  plot's TXY button, with one editor (`helab/views/txy_list.py`).
- **The identity rule:** a list that is one of the four modes is saved, sent and identified exactly as that
  mode; any other list is its own identity, its text (`m23v1>m19v1>External`). No schema change; v0.0.7a1 reads
  what this saves without mistaking it (`tests/test_txy_priority_v007.py`).
- **Fallback** (Q55.2, Q55.5, Q55.6): a list of several entries continues per shot with the folder's list (for a
  plot), Settings' list, External, then the most recently converted HeLab TXY of any profile; a one-entry list
  never falls back. Datasets record the fallback shots; Folder details and the plot's line say so.
- **Convert on read** (Q55.1): only when nothing in the chain has a file, with the own list's first HeLab entry
  that can convert.
- **Live's offer** (Q55.2): a folder whose list is one profile that Auto-convert doesn't convert with offers
  "Convert with <tag>" for the session.
- **Convert this folder…** (Q55.4, Q55.7): right-click and File › Convert "<folder>"…, any profile, to HeLab's
  cache, its temp folder or beside the raw files (beside turns the folder's beside setting on).
- **Open:** Q55.9 (a list that resolves to one entry reads as one and doesn't fall back). Follow-ups A55.1–A55.4;
  checks M55.1–M55.4.

## Design notes (as planned; the floor's answers are above)

- **The four modes are lists:** HeLab priority = [HeLab <conversion tag>, External]; MATLAB priority =
  [External, HeLab <tag>]; HeLab only = [HeLab <tag>]; MATLAB only = [External]. A list equal to one of
  them must keep that mode's **identity** (the two priority modes share identity "", `identity_source`), so
  existing caches, store-v4 TXY layers, presets and saved results stay valid; any other list gets an
  identity text of its own, carried by datasets, `DatasetView.txy_choice`, views and saved-result keys, so
  data of one list is never taken for another's.
- **Shots' origins** stay as now (`""` External, `helab:<profile hash>`), so a dataset made under a list
  says which entry each shot came from.
- **Migration:** the `txy_source` setting and store-v4's per-folder rows (`txy_source_prefs`: source + tag)
  read as lists; old values keep working (a `settings_defaults.py` row, and a column or table added through
  `store_v4.migrate`, never only in `SCHEMA`). Saved presets and arrangements that name a source still open.
- **Convert on read** (store-v4, Q50.1 (a)): under HeLab priority, loads and Live convert on read only the
  shots External lacks. The floor proposes the rule for a general list (e.g. convert on read only for the
  first HeLab entry, only shots no earlier entry has), as an open question.
- **Live and Auto-convert:** Live reads with its folder's list; Auto-convert still writes with the
  conversion profile (Settings). If that profile isn't in the list, the floor proposes what Live's line
  says.
- **UI:** a small dialog (entries ticked and dragged into order, "As Settings" / "As the tab" at the top),
  one control used in all three places; summaries and tooltips name the list short (e.g. "m23v1 › m19v1 ›
  External"). Every control gets an accessible name and ID.
- **Tests:** the identity rule (old modes' identities unchanged), migration of the setting and the folder
  rows, per-shot choice across three or more entries, a plot's own list beside the tab's, convert on read
  under a general list.

## Not in scope

- Renaming or rewriting any TXY file; changing HeLab's file names or tags (frozen, Q18.4).
- Mixing entries within one shot (a shot always comes whole from one TXY).
