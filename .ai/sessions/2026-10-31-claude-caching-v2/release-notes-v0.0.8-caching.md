# v0.0.8: caching v2, release-note lines (V~5, for the v0.0.8 PR)

These are proposed lines for the release notes. Tony edits them; the release itself is his.

## The new disk cache (store-v4)

- **A new disk cache.** HeLab 0.0.8 keeps its disk cache in a new store, `store-v4`, in the same cache folder.
  - It caches each shot's TXY data once per TXY source and converter profile.
  - It also keeps HeLab's own copy of the raw pulses (the `d` files' contents), so another converter profile can
    make its TXY without reading the folder again.
  - The `d` files themselves are never changed or removed.
- **The older cache.** If an older HeLab's cache (`store-v3`) is in the cache folder, the first start asks once
  what to do with it:
  - **Keep using it:** HeLab reads its records and saved analysis where the new cache has none, and counts it in
    the disk budget.
  - **Ignore it:** it stays on disk, unused.
  - **Clear it…:** it is removed, after asking with its size.
  - HeLab 0.0.8 is the last version that reads the older cache. From 0.0.9 it is no longer read or counted, and
    only Settings › Cache › Older cache (store-v3) › Clear… (or Make room's Clear old stores…) removes it.
- **Going back to 0.0.7.** HeLab 0.0.7 still works with its own `store-v3`, which 0.0.8 never writes. What 0.0.8
  cached in `store-v4` isn't seen by 0.0.7, which loads those folders from their files again.

## Convert on read

- **HeLab TXY sources.** With a TXY source that reads HeLab's TXY (HeLab priority, the default, or HeLab only), a
  folder's raw files without a TXY are converted when the folder is loaded and kept in the disk cache. No TXY text
  file is written for them.
  - Under HeLab priority, MATLAB's TXY is still used where it exists.
  - Folder tooltips and Folder details say "N converted when loaded".
- **Live.** Live converts new shots when it reads them, with Auto-convert off too. Auto-convert also writes HeLab's
  TXY text files, to the folder Settings › TXY converter names.

## Settings › Cache

- **New rows:**
  - TXY data;
  - HeLab's cached raw pulses;
  - the cache policy: Raw + what you load (the default), Raw only (convert on load), or TXY only (no raw).
- **Per-folder choices:** right-click › "TXY for this folder…" and "Cache policy for this folder…".
- **TXY only** removes nothing by itself. HeLab offers to remove its cached copy of the raw pulses, with their size,
  and the `d` files are never touched.
- **Remove old entries** has a row per kind (cached data, TXY data, HeLab's cached raw pulses, folder records,
  cached analysis), plus "Everything not used, checked or shown in the last N days".
- Only copies (cached data whose files are gone from their folders) are never removed by age. Make room and Clear
  name them before removing them.

## For the curious

The cache's files (`.hlb`) are documented in `docs/hlb-format.md`. `helab cache dump` and `helab cache export`
read them without HeLab running.
