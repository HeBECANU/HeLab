# Caching v2 stage 3: convert on read (design note, for CoCo before code)

This note builds on Tony's answers S3~1–S3~6 (2026-11-02), Q19.1 (text output unchanged), A40.2, A47.1 and A47.6.
The switch stays off.

**Scope.** Store-v4 only: with store-v3 (the switch off) loads, Live and counts stay exactly as today.

## 3a. Loads convert on read (A47.1 inside)

- **Candidates** (`loading._load`). When the source reads HeLab's TXY, a shot with a raw `d<N>.txt` but no current
  HeLab text of the profile asked for becomes an *on-read* candidate:
  - Its `HelabShot` names the raw file, with the raw file's size and mtime, and is marked `on_read`.
  - `compose` then picks between it and MATLAB's TXY by today's source rules (`could_take`, `choose`):
    MATLAB-priority still takes MATLAB's text first, and HeLab-first takes the conversion.
  - The order for a shot is S3~3's: its TXY layer, then the raw layer (`from_raw`), then a current text, then
    converting its raw file.
- **The per-shot step.** If nothing earlier serves the shot, it's converted from the raw file:
  - `convert_shot(bytes, profile, backend)` runs before `file_started`, under the converter's `_Ticker` with
    `compute_budget(size)`, as S3-2 does for the raw layer.
  - The result is parsed into the array exactly as `from_raw` does, so the data equals the text.
  - The shot is saved in the HeLab layer as kind `raw`, keyed by its raw file, as today.
  - No TXY text is written (Q19.1).
  - The raw layer itself isn't written here: `raw_fill` fills it after the load, as today.
- **Raw files still being written** are never read:
  - The settle time applies to the raw file's stat, since the candidate's listed stats are the raw file's.
  - An unfinished file (the converter's own checks: no final newline, no rows yet) counts as late: kept out, and
    the next load tries again.
  - A file with no hits gives an empty shot, as the converter's empty TXY does.
- **A47.1, profiles:** `FolderCache.with_txy` sends the whole profile (`to_dict()`) for the profile asked for: the
  conversion profile, or a folder's tag resolved through `_profile_for_tag`. `from_raw` and the on-read step use
  it, so user profiles convert too, with no built-in-only lookup.
- **Counts:** the load's `txy_helab` stays the count of HeLab *texts*. A new `helab_on_read` counts conversions.

## 3b. Live (S3~4) and A40.2

- **Live with a HeLab source.** `live_check` takes new shots by the same candidates and steps, converting on read
  whatever the auto-convert toggle says.
  - The toggle now means "also write TXY text". Its label and tooltip say so: "Also write TXY files", with the
    tooltip "Live converts new shots when it reads them; this also writes HeLab's TXY text to <destination>".
- **A40.2.** When a held shot's new HeLab TXY turns out unreadable, the held data is kept and the shot is marked
  for a retry, not dropped as known-unreadable.

## 3c. What users see

- **S3~5:** scans count raw shots as loadable for a HeLab source in store-v4. The folder tooltip and Folder
  details say "N converted when loaded"; no new badge.
- **S3~6:** a plot's TXY row and Folder details name an on-read shot "HeLab <tag>, converted from raw" in place
  of a file name.

## 3d. The integration check

The stage 2 session test gains a stage 3 part, in temp stores with the switch on:
- a load converts on read;
- Live converts a new shot;
- an unfinished raw file waits;
- a user profile converts.

## Checkpoints

- **◆ After 3a.**
- **◆ After 3b–3d,** with the doc proposals.

## Not changed

The text output setting and where text goes (Q19.1); the auto-convert toggle's existence; store-v3; the 8 GB
budget; housekeeping; the switch (off).

## For CoCo

- **R~1** On-read candidates and every stage 3 behaviour are store-v4 only, so the switch-off app is unchanged.
  Proposed: yes.
- **R~2** A load doesn't write raw layer rows itself; `raw_fill` keeps doing that after it. Proposed: yes; it's
  one less writer.
