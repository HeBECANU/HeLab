# TXY priority lists

Horizon: v0.0.8 (Tony, 2026-11-03, Q53.3). Added: 2026-11-03, from Tony in the terminal (block 53:
Q53.1–Q53.3, decided). **Status:** planned; to be built on the dev computer as one floor from
`dev/v0.0.8`. Priority and completion: [overview](_readme.md). Related: [TXY converter](txy-converter.md),
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

## Design notes (for the floor; propose, Ground decides)

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
