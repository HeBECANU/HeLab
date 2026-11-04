# Caching v2, stage 2: design addendum

Vault (Claude Opus 5.5), 2026-11-02, on `agent/caching-v2` after stage 1 landed (`c2d0ece`) and `dev/v0.0.8`
merged (`19084f7`). It builds on:
- the [store-v4 design note](../2026-10-29-claude-caching-audit/store-v4-design.md) ("design");
- the [readiness review](../2026-10-29-claude-caching-v2-readiness/readiness.md);
- [stage 1's addendum](design-stage1.md) ("stage 1");
- the plan [`roadmaps/caching-v2.md`](../../../roadmaps/caching-v2.md);
- Tony's go with **Q45.1–Q45.11**, plus A40.2, A40.3, A42.1, A42.2, A44.1 and A44.2 ([brief](brief-stage2.md)).

**No stage 2 code until CoCo has read this.** Where it differs from the design note, it says so and why.
Questions are marked **S~n** (for CoCo; Tony where noted). Everything else follows a decided answer.

## 0. Summary

- **Data lives in layers.** A folder has a `matlab` layer (MATLAB's TXY) and one `helab:<profile hash>` layer
  per HeLab profile. Each is a row in `txy_layers` plus append-only **segments** (`.hlb` `kind` `txy`).
  - Each shot is stored once, whatever the source mode.
  - A **view** row (`txy_views`, one per folder × source mode × tag) records which layer each shot of that
    composition comes from, plus the folder-level facts today's `datasets.info` holds (listing, signature,
    TXY record).
  - So every source mode and every plot's own choice is disk cached (Q19.3) without storing data twice.
- **The loading order**, per shot of the composition:
  1. the layer;
  2. HeLab shots only: convert from the raw layer;
  3. the share (HeLab TXY text, or the raw file converted; MATLAB's `d_txy_forc`).
  - Store-v4's own `datasets` rows (Q45.4) and store-v3's under Keep (Q45.5) are read for MATLAB shots before
    the share, and copied into the `matlab` layer on use.
- **Saves append.** A load, Live's autosave or a plot's load writes one save unit: a segment per layer for the
  shots that are new or changed, the layer rows, and the view. That is one transaction and one fit check;
  over the budget it becomes one pending unit per folder with parts (Q45.8).
  - Nothing unchanged is rewritten, which ends A40.3's rewrite and Live's whole-dataset rewrite, and
    `pack_dataset`'s 2.1 GB limit with them.
  - Compaction runs only when it fits (Q45.7).
- **Policy** (Q45.1): `raw+used` by default, or `raw`, or `txy`. It is a per-folder row and a global settings
  row, and decides only what new saves write.
  - **The source override** (Q45.2): a per-folder `source` + `tag` on top of Q18.2's global mode. It is one
    choice: what a folder loads is what gets cached.
- **Make room and `trim`** (Q45.6, A42.2) follow one order:
  1. store-v4 `datasets` rows (stage 1's, superseded);
  2. HeLab layers whose raw is held;
  3. `matlab` and TXY-keyed layers whose files were seen;
  4. raw layers seen;
  5. only copies of any kind, named.
- **Small items:**
  - A42.1: store-v3 results are copied into v4 when returned.
  - A44.1: `helab cache export --kind txy`.
  - A44.2: a Qt-free cache-folder file (S~3).
  - A40.2: Live keeps held data when a new HeLab TXY is unreadable.
  - **S2-0, a stage 1 gap found while designing:** `rekey_subtree` doesn't move `raw_layers`.
- **The switch stays off.** Store-v3 behaves exactly as today; none of this runs under it.
- **Stage 3's boundary is kept.** Stage 2 makes no HeLab shot that has no current HeLab TXY on the share. The
  composition is today's (`helab_txy.find` decides availability). Only how a chosen shot's data is fetched
  and kept changes. "Convert on read" for shots without HeLab TXY is stage 3.

## 1. Where the code goes

| Module | What | Area |
|---|---|---|
| `helab/utils/store_v4.py` | the schema of the new tables, `migrate` additions for stage 1's v4 stores | cache |
| `helab/utils/cache_store.py` (or a new `helab/utils/txy_layers.py` mixin past ~600 lines; same owner) | layer, segment and view read/write with guards, `start_txy_job`, pending parts, Make room's and `trim`'s order, Clear `txy`, the sweep over `txy/`, `rekey_subtree` (S2-0), the policy and override tables, A42.1's copy | cache |
| `helab/convert/txy_layer.py` (new, Qt-free, `PURE`) | a segment's arrays ↔ `.hlb` `kind` `txy`, precision per profile | convert |
| `helab/io_ops/loading.py`, `helab_txy.py` | the loading order, views, saving units, A40.3, the v4 `datasets` and v3 seed | io |
| `helab/io_ops/save_held.py`, `live.py` | Live's segments (Q45.7); A40.2 | io |
| `helab/io_ops/results.py` | A42.1's copy on return | cache |
| `helab/io_ops/admin.py`, `stores.py`, `events.py` | `clear_txy`, `txy` in `clear`/`removed`, `trim`'s events, the policy and override actions | cache |
| `helab/utils/folder_cache.py` | `tab_source(path)` with the override, policy reads, the `removed` kind `txy` | io |
| `helab/cache_cli.py`, `helab/utils/constants.py` (A44.2, S~3) | `--kind txy`; the cache-folder file | cache |
| `helab/views/…` (step 5; merge `dev/v0.0.8` first) | Folder details' TXY and policy lines; the override and policy controls; Settings › Cache's TXY row; Make room naming layers | app |
| `helab/utils/cache_move.py` | `txy_segments` in `_verify_store`'s blob tables | cache |
| `helab/utils/settings_defaults.py` | the global `cache_policy` row (default `raw+used`) | app |

Outside the brief's owned paths, to confirm (**S~1**):
- `helab/io_ops/results.py` and `admin.py`/`stores.py`/`events.py`, as in stage 1;
- `helab/convert/txy_layer.py` (new);
- `helab/utils/constants.py` (A44.2) and `settings_defaults.py` (one row);
- `cache_move.py` (one table name).

## 2. Schema (store-v4 only; additive within layout 4, `store_v4.migrate`)

```sql
CREATE TABLE txy_layers (            -- one per folder and layer
  path TEXT NOT NULL,                -- root:// key, as datasets.path
  layer TEXT NOT NULL,               -- 'matlab' | 'helab:<profile content hash>'
  tags TEXT NOT NULL,                -- JSON [tag]: names seen for this hash (m19v1, p22v1, …), display only (Q22.2)
  entries TEXT NOT NULL,             -- JSON [[shot, size, mtime_ns, kind, seq, rows, problematic]]
  shots INTEGER NOT NULL, rows INTEGER NOT NULL, ram_bytes INTEGER NOT NULL, bytes INTEGER NOT NULL,
  precision TEXT NOT NULL,           -- 'g8' (m19v1, MATLAB's text values) | 'f64' (Q19.6)
  maker TEXT, job_seq INTEGER NOT NULL, saved_at REAL NOT NULL, last_used REAL NOT NULL,
  PRIMARY KEY (path, layer));
CREATE INDEX txy_layers_last_used ON txy_layers (last_used);

CREATE TABLE txy_segments (          -- a layer's files; the highest seq holding a shot wins
  path TEXT NOT NULL, layer TEXT NOT NULL, seq INTEGER NOT NULL,
  file TEXT NOT NULL, bytes INTEGER NOT NULL, live_shots INTEGER NOT NULL, all_shots INTEGER NOT NULL,
  PRIMARY KEY (path, layer, seq));
CREATE INDEX txy_segments_file ON txy_segments (file);

CREATE TABLE txy_views (             -- a composition: what one source mode and tag loads for the folder
  path TEXT NOT NULL, source TEXT NOT NULL, tag TEXT NOT NULL,   -- Q18.2 mode; the HeLab tag asked for
  fingerprint TEXT NOT NULL,         -- JSON [[shot, size, mtime_ns, kind, layer]]
  problematic TEXT NOT NULL, raw_times TEXT NOT NULL DEFAULT '[]',
  info TEXT NOT NULL,                -- today's datasets.info: saved_at, snapshot_at, signature, names,
                                     --   folder_mtime_ns, unsettled, counts, txy (TXY_FIELD), kind, format
  maker TEXT, job_seq INTEGER NOT NULL, last_used REAL NOT NULL,
  PRIMARY KEY (path, source, tag));

CREATE TABLE cache_policy (path TEXT PRIMARY KEY, policy TEXT NOT NULL CHECK (policy IN ('raw+used','raw','txy')),
                           set_at REAL NOT NULL);                              -- Q45.1, no tag (Q45.2)
CREATE TABLE txy_source_prefs (path TEXT PRIMARY KEY, source TEXT NOT NULL, tag TEXT NOT NULL,
                               set_at REAL NOT NULL);                          -- Q45.2's override
```

Each entry's fingerprint has a **kind** (Q45.3):
- `raw`: the raw file's (size, mtime_ns). Used for a HeLab shot whose raw file is listed. That covers one
  converted from the raw layer or the raw file, and one read from a current HeLab TXY: `find` already proved
  it current against that raw file.
- `txy`: the TXY file's. Used for every `matlab` shot, and for a HeLab shot only where no raw file is listed
  (an archive without raw, under `txy`).
- **S~2:** this reads Q45.3 as "TXY-keyed only when there is no raw file". The decided answer said
  "under `txy` (or with no raw file)". Keying a current HeLab TXY by its raw file is what makes a
  re-conversion, a Clear of `converted-txy/` or a convert-from-raw-layer the same data (design §2, audit
  K2). Proposed: as read here.

Other schema notes:
- `entries[i].seq` names the segment holding the shot. `rows` and `problematic` let a view be served without
  opening every segment.
- **Views** hold no data. A view whose layer entry is gone (removed, Make room) or doesn't match its
  fingerprint is incomplete, and those shots come from the next step of the loading order. Removing a layer
  deletes its folder's views in the same transaction: they are derived, so this is an update, not a removal
  of the user's data.
- **`pending_saves`** gains `parts TEXT NOT NULL DEFAULT '[]'` in v4 (§6); v3 is untouched.
- **Epochs:** `txy:<key>` beside `raw:<key>` (per kind, cache-2), and `gen_txy` in `meta`.
- Store-v3 gets none of this. An older HeLab opening store-v4 refuses it as today (a newer layout opens
  read only).

## 3. The `.hlb` `kind` `txy` (format 1, additive)

- **Arrays:**
  - `shots` `<i8` [k];
  - `offsets` `<i8` [k+1];
  - `hits` `<f8` [N, 3] (T s, X m, Y m in rows, as today's arrays);
  - `problematic` `|u1` [k].
- **Meta:** `layer`, `profile_hash`, `tags`, `precision`.
- **Codec:** zstd 9 with **no shuffle** (`shuffle: "none"`, already written by `hlb.pack(shuffle=False)`;
  design measured 0.32× the TXY text against 0.58 with shuffle).
- **`helab/convert/txy_layer.py`:** `pack_segment(arrays_by_shot, …)` and `unpack_segment(data) → {shot:
  ndarray}`, checked like `unpack_dataset` (2-D, 3 columns, offsets monotone, k shots).
- **Precision** (Q19.6): `g8` layers hold the values the 8-significant-figure text parses to. A `matlab` shot
  is what `_read_txy_file` parsed; a `m19v1` shot converted from raw is `parse(format_txy(hits))`, which the
  byte-identical converter makes equal to the text. `f64` layers hold full float64.
- **The format page** (`docs/hlb-format.md`, Ground's) gains a "TXY layers" section and a sample. A docs
  change, proposed in the handoff.

## 4. Identity and the loading order

**Composition** is today's `helab_txy.compose`/`txy_sources.choose`, unchanged in rule:
- the listing decides which shots exist and which TXY each takes;
- offline (`read_cached`), the view's stored fingerprint decides.

The view key is `(path, identity_source(source), tag)`. The two priority modes share identity `""` today,
which keeps saved results valid, and they differ only on shots both kinds have, which their origins tell
apart. So they share one view, as they share one dataset row today.
- **S~4:** or one view per exact mode. Proposed: share, as today. Results keyed on `""` stay valid.

**Per shot of the composition, its layer L:**
1. **Layer L** holds the shot with the current fingerprint (kind included): take it from its segment.
2. **HeLab layers:** the raw layer holds the raw file's current fingerprint and parser. Decode and convert
   with L's profile (`reconstruct`), in the load's worker pool, under the converter's ticker
   (`compute_budget`, as C3-1), and add the shot to L's save.
3. **MATLAB shots:**
   - store-v4's own `datasets` row (Q45.4);
   - then store-v3's dataset under Keep (Q45.5, `LegacyStore`, read only);
   - in each case only a shot whose fingerprint equals the TXY file's now.

   The dataset is unpacked once per load (it is one pickle) and copied into the `matlab` layer's save.
   Offline, these are the cached sources.
4. **The share:**
   - HeLab: the current HeLab TXY text (parsed, as today); if it is unreadable, the shot is problematic, as
     today.
   - MATLAB: `d_txy_forc` (as today).
   - Converting a raw file here is stage 3's (§0).

**Quick checks** keep today's rules. They read the view instead of the `datasets` row:
- `_unchanged_since_cache` compares `info.signature`, `snapshot_at`, `folder_mtime_ns`, the sample stats and
  `_helab_unchanged` against the view;
- `memory_shots` and `cache_base` work on the view's fingerprint;
- the `cached` read (`read_cached`) serves the view's shots from layers.

**A40.3** has two parts:
- Shots whose (fingerprint, kind, layer) are unchanged are never rewritten: a save appends only new or
  changed shots.
- A load whose shots are all unchanged writes only the view's `info`: signature, listing, `unsettled`, and
  the current TXY record, **including `txy.folders`**. The probe's finding: today's `confirm_dataset` never
  refreshes it, so `_helab_unchanged` keeps failing after a conversion the source doesn't take. That write is
  `confirm_view(path, source, tag, fingerprint, info, guard)`, under the guard, only if the view's
  fingerprint is still that.

**Saved results** keep today's keys (Q45.10: per computer).
- A HeLab shot's coverage fingerprint becomes the entry's (raw-keyed) fingerprint. A result saved on a TXY
  fingerprint before stage 2 shows as outdated once, then matches (design §2).
- Store-v3's results under Keep are matched as they are, and copied (A42.1, §9).

## 5. Saving: units, guards, policy

- **`start_txy_job(path)`** is taken first, as `start_dataset_job`, and gives the same `job_seq`. The guard
  holds `gen_txy` and `gen_datasets` (a Clear of datasets also fences, while v4 `datasets` rows are read),
  the `txy:<key>` epoch, the folder's epoch and the root's epoch.
- **One save unit per job:**
  - one new segment per layer touched (its new and changed shots only);
  - each touched layer row (`entries` updated: the new shots point at the new `seq`; replaced shots' old
    segment `live_shots` decremented);
  - the view row.
  - One transaction, one `_live()` fit check (TXY segment bytes join `_live`), and the 80 % approval rule
    applied to the unit's growth, as today's dataset.
- **Ordering:**
  - a layer **entry** for a shot is replaced only by a job with `job_seq` ≥ the entry's (it is per shot now,
    so a Live save and a load of one folder never undo each other's shots);
  - a view row is replaced only by a job with `job_seq` ≥ its own.
- **Policy, read in the save's transaction** (`cache_policy` row, else the global default):
  - `raw+used`: everything above, and `raw_fill` as today.
  - `raw`: HeLab layers aren't written (a HeLab shot is converted from raw on each load); the `matlab` layer
    and the view are.
  - `txy`: layers and views as `raw+used`, but no raw rows: `schedule_raw_fill` skips the folder, and
    conversions' `_RawRows` doesn't start.
  - Switching writes nothing and removes nothing (decided).
  - Don't cache (`_check_cacheable`) still refuses everything, and no data root still means RAM only.
- **Store-v4's `datasets` table** is never written in stage 2 (Q45.4): `save_dataset` raises for layout 4
  (a test).

## 6. Pending units (Q45.8)

- `pending_saves` keeps `UNIQUE (path)`. In v4 its `parts` lists `[{layer, file, bytes, shots, job_seq,
  record}]`: each a segment file written but not adopted, plus the view record in the unit's `record`.
- **A newer unit for a folder merges** with the pending one: its part for a layer replaces that layer's part
  (newer `job_seq`), and other layers' parts stay. The view record is the newer one. The replaced part's file
  is retired.
- So a tab load's pending `matlab` part and a plot's later pending `helab:<hash>` part both wait under one
  question that names both.
- `adopt_pending` applies the parts in one transaction under each part's guard (`job_seq` per entry,
  `txy:<key>` epoch). A part fenced since is dropped with its file, and the rest still apply.
- Make room for the unit is planned over its total bytes.
- Raw stays never-pending (Q42.1). The 1 h expiry (`PENDING_MAX_AGE`) is unchanged.

## 7. Live's segments (Q45.7)

- **`save_held`:**
  - writes one unit holding only the held shots that are new or changed since the layer's entries (it
    already lists and checks them);
  - its view's signature stays `folder_print`;
  - it now passes `folder_mtime_ns` when the listing allows, so the next quick check needn't list (today
    None).
- **Compaction:**
  - when a layer has more than 8 segments, or more than half its stored bytes belong to superseded shots
    (`live_shots` vs `all_shots`), the same job writes one segment of the layer's current shots and retires
    the others;
  - only if that fits beside them in the budget (the fit check counts the new file before the old ones are
    retired);
  - otherwise it waits for a later save, and never asks (decided).
- **A40.2** (`live_check`): when a held shot is read again because HeLab's TXY of it is new (a switch or a
  re-conversion) and that TXY can't be read:
  - the held data stays (the held fingerprint and origin are kept, as for a file changed while read);
  - the HeLab file's (size, mtime) is sent back as known-unreadable for that shot, so it isn't read again
    until it changes;
  - a test: before, the held shot is dropped and marked unreadable.

## 8. Make room and `trim` (Q45.6, A42.2)

One planner, `_free_space(budget, exclude=path)`, used by `adopt_pending`'s Make room, `room_plan`, and `trim`.
It works least recently used first within each group, a whole row at a time, never the folder being saved,
exact and rolled back as today:
1. store-v4 `datasets` rows (stage 1's; superseded by layers once the folder is loaded);
2. HeLab layers whose every entry is raw-keyed with its raw row held (rebuildable locally);
3. `matlab` layers, and HeLab layers with TXY-keyed entries, whose TXY files the last listing saw;
4. raw layers seen (as stage 1);
5. only copies, named: raw layers gone (as stage 1), and layers of groups 3's kinds whose files are gone.

**Room items:**
- the path for a dataset (as today);
- `txy:<layer>:<path>`, `txy-seen:<layer>:<path>`, `raw:`, `raw-only:`, and `txy-only:<layer>:<path>`.

The dialog names layers by tag (`m19v1`, "MATLAB's TXY"). `trim` sends the same `removed` events (it removes
datasets only today).
- **S~5:** Make room's whole-row granularity for groups 2–3 (one folder's layer at a time). Proposed: yes; a
  per-shot plan would make the dialog unreadable.

## 9. Clear, Settings › Cache, results (A42.1), export (A44.1)

- **Clear `txy`** removes TXY layers, their segments and views:
  - it joins Clear all (beside `raw`), `clear_root`, and Don't cache with "remove cached data" (layers that
    aren't only copies, as C2-9);
  - `removed` kind `txy` (with `layers` rows and `bytes`);
  - an admin `clear_txy`;
  - Settings › Cache gets a "TXY data" row with the tags named.
- **Clear folder preferences** turns off `cache_policy` and `txy_source_prefs` too, by `set_at` and
  `prefs_cleared_at` as `convert_prefs`.
- **`rekey_subtree`** moves the new tables.
- **S2-0:** it also moves `raw_layers`, which stage 1 missed. A nested marker found below a folder with raw
  rows today leaves them under the old key: unused, but counted in the budget until Clear. A test fails
  before the fix.
- **A42.1:**
  - In `result_find`, a hit with `legacy=True` (exact or family: both are shown), with a guard and a
    writable store, is copied into v4 by a new `adopt_legacy_result`. It writes the bytes already read under
    the result guard, checks `_legacy_hidden` again under the lock, skips if v4 now has the key, then upserts
    under one fit check. If it doesn't fit, nothing is copied and nothing waits.
  - The event's `result_id` becomes v4's.
  - v3's own bytes still count while it is kept (both files exist): correct, not double counting.
- **A44.1:** `helab cache export --folder F --kind txy [--layer matlab|<tag>|helab:<hash>]` writes `t_s,
  x_m, y_m` per shot (`d_txy<N>.<ext>`). A single segment file exports as `FILE.hlb`, per shot.

## 10. A44.2: a Qt-free `helab cache` (S~3)

The cache folder is a `QSettings` value (a plist on macOS, the registry on Windows, an ini on Linux), resolved
by `constants.resolve_cache_dir` with the unsafe-location fallback. The options:
- **(a)** A Qt-free reader per OS (`plistlib` or `defaults read`, `winreg`, Qt's ini escaping), duplicating
  the fallback.
- **(b)** The GUI writes the resolved folder to `<app folder>/cache-folder.json` at start and after every
  cache move. `helab cache` reads that file and falls back to QtCore only when it is missing.
- **(c)** Leave it (QtCore only, no GUI).

Proposed: **(b)**. It is small, records the resolved answer rather than re-deriving it, and works on every OS.
It is written by the GUI only and never read by the GUI.

## 11. The per-folder override and policy in the app (Q45.1, Q45.2)

- **`FolderCache`:**
  - `tab_source(path)` returns the override, else the global `txy_source` (and the tag likewise);
  - `with_txy`, `payload_source` and `tab_choice` take the path;
  - plots' "As the folder's tab" follows the folder's override;
  - memory and events as `convert_prefs`;
  - the helpers get the source and tag in the request, as today.
- **UI** (step 5):
  - Folder details' TXY line names an override ("this folder: HeLab p22v1 first") and the policy when it
    isn't the default;
  - the explorer's right-click menu gets "TXY for this folder…" and "Cache policy…" items (a small dialog,
    IDs);
  - Settings › Cache gets the global policy.
- **S~6** (Tony, wording): those labels. Proposed as written. "Cache policy: raw + what you load (default) /
  raw only, convert on load / TXY only (no raw)".

## 12. Tests (by step; each fix or rule with a test that fails before it)

- **Store (◆ 1):**
  - segments round trip;
  - per-shot `job_seq`;
  - views incomplete after a layer's removal;
  - compaction only when it fits;
  - the pending merge (two layers, one question; a fenced part dropped);
  - the five-group order for Make room and `trim`, exact or nothing;
  - Clear `txy` everywhere it joins;
  - the sweep keeps segments named by a row or a pending part, and deletes unnamed ones over an hour old;
  - S2-0;
  - `save_dataset` refused in v4;
  - the migrate on a stage 1 v4 store;
  - A44.1 export;
  - the cache move verifying `txy_segments`.
- **Loading:**
  - the loading order (layer, then raw layer, then share; offline from layers);
  - every source mode cached once (helab-only and matlab-only share the layers of a priority view; data
    bytes counted once);
  - the override;
  - A40.3 (an all-unchanged load writes no segment, and the next quick check passes after a conversion the
    source doesn't take);
  - the v4 `datasets` and v3 seeds (copied on use; v3 hashed unchanged);
  - A42.1;
  - a HeLab shot from the raw layer equals its text TXY's parse (`g8`).
- **Live:** one segment per autosave of the new shots only, compaction, and A40.2.
- **UI:** the controls, IDs (`test_accessible_names`) and Folder details' line.
- **Integration (◆ 2):** extend `test_caching_v2_session.py` as the brief lists, with the switch on and temp
  stores only.
- **Off is unchanged:** the whole existing suite runs with the switch off, as today.

## 13. Questions (S~n), for CoCo; Tony where marked

- **S~1** The files outside the owned paths (§1).
- **S~2** Q45.3 read as "TXY-keyed only where no raw file is listed" (§2).
- **S~3** (Tony, if CoCo prefers) A44.2's option (b), a `cache-folder.json` in the app folder (§10).
- **S~4** The two priority modes share one view, as they share a dataset today (§4).
- **S~5** Make room's whole-row granularity for layers (§8).
- **S~6** (Tony) The policy and override wording (§11).
