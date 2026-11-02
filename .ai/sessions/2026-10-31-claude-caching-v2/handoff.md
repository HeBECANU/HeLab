# Handoff: caching v2 (`agent/caching-v2`), Vault

Worker: Vault (Claude Opus 5.5). Brief: [brief.md](brief.md). Updated at each checkpoint.

## Stage 0 (checkpoint 1): A19.2, cache-5, cache-4, cache-6

Commits on `agent/caching-v2` (base `92fc597`, `dev/v0.0.8` at `d9d647f` merged):

| Commit | What |
|---|---|
| `b4ab6f6` | cache-5: a save whose guard names a re-keyed folder is `SaveRejected("cleared", REKEYED)`, its file retired at once |
| `46f481f` | cache-4: tests close the `sqlite3` connections they open (29 blocks in 11 files) |
| `cd6edca` | cache-6: `admin.py`'s comment on `prefs` and volume hints |
| `ce8eae7` | A19.2: the Clear fence between Clear converted TXY and a running conversion |

Checks at `ce8eae7` (macOS, M4 Max): `pytest -n 4 --reruns 5 --reruns-delay 1 --basetemp=.ai/temp/pytest`:
**8522 passed, 672 skipped, 2 warnings in 251.95s; no RERUN** (the warnings: pyqtgraph's NumPy 2.5
`arr.shape` DeprecationWarning in `test_t_spectrum.py`, known); `mypy helab/ --strict`, `mypy tests --strict`,
`mypy helab/ --strict --platform win32`: no issues; `pyright helab tests` and `--pythonplatform Windows`:
0 errors. Log: `.ai/temp/stage0/suite.log`.

Files outside the brief's owned paths, approved by CoCo (2026-10-31): `helab/convert/provenance.py` (the
fence) and `helab/convert/txy.py` (`write_atomic`'s optional `after_rename`). Both stay Qt-free and in `PURE`.

### A19.2: how the fence works

- `converted-txy/index.sqlite` gains a `fence` table (one row: a random token, `cleared_at`), added
  **within schema 1**: `CREATE TABLE IF NOT EXISTS` by the first Clear (and in `_TABLES` for a new index);
  `user_version` stays 1, so 0.0.7a1 reads and writes the index unchanged (convert-3's constraint).
- `clear_converted` first sets a new token (`TxyIndex.set_fence`, one `BEGIN IMMEDIATE`), then lists the
  folders and removes, as before.
- A conversion into the cache or temp base reads the token when it starts (`provenance.fence_of`, right
  after `_places`, before the listing). For each TXY: the row is written only while the token is unchanged
  (`record(fence=…)`, checked inside the row's transaction), then `hold(fence)` takes `BEGIN IMMEDIATE` and
  checks again, `write_atomic` renames, and `after_rename=index.release` lets go at once (a `finally` lets
  go too if anything failed before the rename). The row is still committed before the rename.
- So a Clear's `set_fence` lands either before the hold (the write is refused: `provenance.Cleared`, the
  temporary removed by `write_atomic`, the row forgotten) or after the rename (it waits on the lock, then
  lists and finds the TXY and removes it with its row). Each refused shot, and every later shot of that
  conversion (unread: `read` checks `index.fence()` first), is `shot_waiting` with reason `cleared`
  (`convert.CLEARED`); the next check converts them. A `FileNotFoundError` from the write while the fence
  has moved (a Clear removed the in-flight temporary, which `_OWN_FILE` matches) counts the same.
- Beside writes aren't fenced (`fence` is None): Clear never removes them.

CoCo's three points and the `after_rename` question:

1. **An older HeLab's Clear is unfenced.** 0.0.7a1's `clear_converted` never sets the token, so its Clear
   against this build's running conversion behaves as before (may leave TXY). Likewise 0.0.7a1's
   conversions never check it, so this build's Clear vs an old conversion is unfenced too.
2. **The held lock spans the rename alone.** `hold` is the last thing in `before_rename`; `after_rename`
   runs right after `os.replace`/`_rename_new` and before `_fsync_folder`. **Busy past `BUSY_SECONDS`**
   (10 s): `hold` raises `IndexUnavailable` with nothing held; `write_atomic` removes the temporary; the
   row is forgotten (or, if that is busy too, left matching no TXY on disk, so the shot is converted
   again); the exception fails the conversion as any index write it can't make does today. A manual run or
   `--once` is then simply run again; **in Live, a failed conversion stops auto-convert until the user
   presses Retry** (`explorer_live.py`'s `convert.error`), as any conversion error does today. The TXY
   already there is untouched (no rename happened): never a lost TXY. Test:
   `test_a_busy_lock_for_the_rename_fails_the_conversion_and_loses_no_txy`.
3. **Clear between pin and rename, both orders**: `test_a_clear_between_the_row_and_the_rename`
   (`before the lock`: refused, no TXY, no row, shot 2 waits unread; `while the rename holds it`: the
   Clear is shown blocked with the token unchanged, then removes the TXY and its row after the rename).
   Also `test_a_clear_after_a_conversion_started_refuses_its_rows_and_its_shots_wait` (fence moved before
   the row) and `test_the_fence_table_is_added_within_schema_1`.
4. **`after_rename` raising after the rename**: the TXY is in place and its row committed; `write_atomic`'s
   handler only removes the temporary name (already gone) and re-raises, skipping the folder fsync. In
   the converter the callback is `TxyIndex.release`, which suppresses `sqlite3.Error`, so it doesn't raise
   in practice; if it did, the `finally` calls `release` again (idempotent: `_held` is cleared first, and
   SQLite drops the lock with the connection at `index.close()` anyway). The converter's `except` would then
   forget the row of a TXY that exists, so that shot converts again next time (no loss). Test:
   `test_write_atomic_calls_after_rename_between_the_rename_and_the_folders_fsync` (default path unchanged;
   order rename → callback → fsync; raising leaves the file).

Gaps left (documented in `clear_converted`'s docstring):
- A base with **no index yet** isn't fenced: Clear makes no index (it would show as kept bytes in Settings ›
  Cache). Only the base's first conversion since the index (Q26.2), between its start and its first
  `open_index(write=True)` (the listing), can still write after such a Clear.
- A **damaged or busy** index isn't fenced (Clear can't write it); a **newer** HeLab's isn't ours.
- ~~Clear removes in-flight temporaries~~ **Fixed (S0-1, A~1, commit after `64280e0`):** Clear used to remove
  every `_OWN_FILE` partial of any age, so a conversion that started *after* the Clear's token, while the
  Clear was still removing, could lose its temporary: the rename raised `FileNotFoundError`, the conversion
  ended in an error, and in Live that stopped auto-convert until Retry (Assay's S0-1). Clear now leaves
  temporaries under `convert.PARTIAL_MAX_AGE` (1 h), as housekeeping does, and Settings › Cache's clearable
  count skips them too (`helab_txy._young_partial`). A conversion that started *before* the Clear never
  renames anyway (the fence). Tests: `test_a_clear_still_running_leaves_a_later_conversions_temporary_alone`
  (fails without the fix with that `FileNotFoundError`) and `test_the_helper_measures_and_clears_converted_txy`
  (a young temporary kept, an old one removed).

### cache-5

`_guard_holds` and `_check_result_guard` raise `SaveRejected("cleared", cache_store.REKEYED)` ("The
folder's data root changed before saving completed") instead of `ValueError`. Every save path already
handles `SaveRejected`: `save_dataset`/`add_pending` retire the file (`_reject_file`), `save_result`
retires it (`_reject_result_file`), `result_save` sends `result_not_saved` (reason `cleared`), listings and
summaries swallow it as before, and `confirm_dataset`'s caller (which caught only `StoreError`/
`SaveRejected`) no longer lets a raw `ValueError` escape. `adopt_pending_result`'s `except ValueError` is gone.

### cache-4

All 29 `with sqlite3.connect(…) as c:` blocks in tests are `with contextlib.closing(sqlite3.connect(…)) as
c, c:` (commit on exit kept, connection closed). The other direct connections in tests already close in
`finally`. Checked with a `gc.collect()` after every test and `-W always::ResourceWarning` on the 11 files:
no `unclosed database`; the same on the old `test_cache_switch.py` shows the leak
(`.ai/temp/cache-4/gc_plugin.py`, not committed).

## Steps 2–4 (checkpoint 2): the addendum, `.hlb` and the raw layer, store-v4's core (switch off)

| Commit | What |
|---|---|
| `9767d15` | step 2: [design-stage1.md](design-stage1.md), read by CoCo; T~1–T~3 sent to Tony |
| `b3945f1` | step 3: `helab/utils/hlb.py`, `helab/convert/raw_layer.py`, `check.convert_via_layer`, `check_samples.py --via-layer` |
| `9cbaa0a` | CI: the Converter backends job runs `tests/test_raw_layer.py` (CoCo's OK) |
| `cbf6e16` | step 4: the switch, store-v4 in `CacheStore` (`helab/utils/store_v4.py`), `LegacyStore`, the import, Keep, cache-2, makers, cache moves |
| `627d1ab` | step 4: the inventory measures store-v3 (`meta.legacy_bytes`, gap 8) |

Outside the brief's owned paths, approved by CoCo: `helab/convert/raw_layer.py` (new), `helab/convert/check.py`,
`dev/txy/check_samples.py`, `.github/workflows/ci-test.yml` (one line). New modules in `PURE`: `helab.utils.hlb`,
`helab.convert.raw_layer`.

### Step 3

- **`.hlb`** as the addendum §5: magic `\x89HLB\r\n\x1a\n`, `<u4` header length (≤ 16 MiB), JSON header (`format` 1,
  `kind`, `maker`, `meta`, `arrays` with explicit dtypes `|i1 |u1 <i8 <f8`, codec, chunks with offset, length,
  size, CRC32), Blosc chunks ≤ 64 MiB at element boundaries. Unknown header fields ignored; a newer `format`, an
  unknown dtype or codec, any damage: `HlbError`, never data. Bytes only (the store writes files, step 5).
- **Raw layer** as §6: compact `i8-i64d-1` when the strict path read the file, channels ≤ 127 and times < 2^62
  (looser than the design's 2^53 and still exact: every strict value is an integer float64, so its int64 and the
  deltas are exact); row 0 first, then stable time order. `f64-1` otherwise, in file order. `Facts` give
  `not_done` the same answer as the bytes. zstd 9 + byte shuffle.
- **Proof:** `tests/test_raw_layer.py` (every case, every textscan probe (1,381 inputs in 8 folders),
  `tests_sample_data/`, a seeded fuzz set of 57): byte-identical TXY from the layer with every available backend
  and the split path. **Here only `reference` and `numpy` are built: the cython backend is proved by CI's
  Converter backends job only** (rust, numba, mlx only wherever they are installed; the test skips a backend that
  can't run). Storing all
  rows in plain sorted order (row 0 not first) fails 54 of the tests.
- **Sample set** (`check_samples.py --positions all --via-layer --backend numpy`, read only, in memory; nothing in
  `~/HeLab-samples` changed, checked with `find -newer`): **303 identical, 1 cut, 2 variant, 3 empty (the 6
  proved exceptions), 0 differ**, the same table as the file path. 9.4 s for 309 shots.

### Step 4

- **The switch:** `store_v4` row (bool, off, no control); `cache_store.store_root()` reads it once per process
  (`live_layout`, lazily through `cache_setting.store_v4_enabled(app_settings())`); `store_root_for(dir, layout)`
  and `layout_of(root)` (the folder's name decides: `store-v4` is layout 4). Helpers never read it. Off: v3 as
  today, and `test_with_the_switch_off_store_v3_is_live_and_no_store_v4_is_ever_made`.
- **store-v4** = every v3 table (datasets included, T~3) + `makers` + `raw_layers` (empty until step 5) + `maker`
  columns on `datasets` and `results`; `meta.format` 1 (newer: read only), `gen_raw`, `imported_v3`,
  `legacy_bytes`; `store_v4.migrate` for tables added within layout 4 (none yet; called on every writable open).
  Not yet in v4: `legacy_v3` is written by step 6's question (unset = not answered = Keep).
- **cache-2:** in v4 a record kind's removal bumps `<kind>:<key>` (`store_v4.epoch_key`), datasets keep the
  folder's own row; v3 unchanged. A nested root's re-key moves only the folder rows (as today); a per-kind row
  left under the old key is harmless (a guard naming the old key is `REKEYED` anyway).
- **makers (Q28.4):** the session's maker is `HELAB_STORE_MAKER` in the environment, made at the GUI's (or
  `helab convert`'s) first `store_root()` under v4 and inherited by its helpers (`IOService` starts them with a copy
  of `os.environ`), so `store_options()` needs no change; a store without one (tests) makes its own. The row is
  written in the same transaction as the first data row. **Privacy (CoCo's note, block 29): the record holds the
  machine's hostname, and every `.hlb` header will carry the maker's record: fine on this machine, but a `.hlb` or a
  saved result shared off it carries the hostname.** The machine id is a random UUID in `app_folder()/machine-id`.
- **store-v3:** `LegacyStore` (`mode=ro`, else `mode=rw` + `query_only`; `NO_CKPT_ON_CLOSE`); the import once at
  v4's creation (retried while v3 can't be read; a v3 appearing later isn't imported); Keep's read-through of
  records and results (v4 exact, v3 exact, v4 outdated, v3 outdated; `ResultFound.legacy`; counts include v3's);
  Ignore/Clear never open v3. **Not built: copy-on-use** of v3 results into v4 (the addendum said "by the next save
  of that folder's results"); read-through only, while v3 is kept (A~3).
- **Cache moves:** the primary store (newest layout present) keeps `store_id`'s role; the record adds
  `store_ids`; `verify` checks each store; `checkpoint` writes the primary only; a v3 beside a v4 is read through
  `LegacyStore`. Older records (no `store_ids`) recover as before.
- **The guard test** (`test_only_legacy_store_ever_opens_store_v3_once_store_v4_is_live`): with v4 live, a session
  of opens, saves, results, records, purges, removals, the sweep, inventories and a copy move opens v3's database
  only from `legacy_store.py` (every `sqlite3.connect` and `CacheStore` open watched) and v3's files (all but
  `-wal`/`-shm`) are byte-identical, in place and in the copy. It fails if `cache_move` opens v3 itself.

Checks at `627d1ab` (macOS, M4 Max): `pytest -n 4 --reruns 5 --reruns-delay 1 --basetemp=.ai/temp/pytest`:
**8699 passed, 672 skipped, 2 warnings in 136.77s; no RERUN** (the known pyqtgraph warnings); `mypy helab/
--strict` (199 files), `mypy tests --strict` (178), `--platform win32`: no issues; `pyright helab tests` and
`--pythonplatform Windows`: 0 errors. Logs: `.ai/temp/step4/`.

### Checkpoint 2 review fixes (Assay, `review-checkpoint2.md`)

All six fixed, each with a test that fails before it; fix range `bdbd2bc..` this push.

| Finding | Commit | Fix |
|---|---|---|
| C2-2 Low | `471a980` | `.hlb`: the header's CRC32 after its length (header at offset 16); chunks must tile the body in order, no gap, overlap or trailing bytes. Format 1 still unwritten, so no bump |
| C2-3 Low | `6d53159` | `machine_id`: an invalid or empty file is replaced atomically, once; a missing one made with `os.link` so two first starts agree; never recursion |
| C2-1 Medium | `9d5889c` | Keep reads store-v3 for a key only while v4 never removed that kind for it (its generation, the key's epoch, its root's; a `None` save's tombstone `legacy-hidden:<kind>:<key>`, read by no guard; purges by age recorded in `meta.legacy_purged`) |
| C2-4 Nit | `9d5889c` | the result count adds only v3 lookups v4 lacks, none for a removed key; the step-4 test's 4 corrected to 3 |
| C2-5 Nit | `47a6723` | a root forgotten in v4 before a retried import stays forgotten (`meta.forgotten_before_import`); only roots are ever deleted of the imported state |
| C2-6 Nit | `0551343`, `630bf8e` | `cache_move.start(..., layout=)` makes the live store the primary (record `primary`); `CacheMover` sends `cache_store.live_layout()` as every move request's `layout` (CoCo's OK to edit it); without one (an old record), the newest as before |
| C2-7 Nit (re-check) | `f28f9ff` | purges by age keep two cutoffs per kind (the latest, and the latest that took scan histories with failures) |
| C2-8 Nit (re-check) | `4270080` | a retried import brings v3's flags set before v4's `prefs_cleared_at` in off, dated at the Clear |

Checks at `0551343`: **8723 passed, 672 skipped, 2 warnings in 154.35s; no RERUN**; mypy (also win32) and pyright
(also Windows) clean. Log: `.ai/temp/step4/suite-fixes.log`.

After the re-check (`ff1fe1a`): C2-7, C2-8 and C2-6's app half, each with a test that fails first. Checkpoint 2 now
lands with step 5's store side (`d207b61`, inert: store-v4 only, switch off) under them. Checks at `630bf8e`:
**8743 passed, 672 skipped, 2 warnings in 138.67s; no RERUN**; mypy (also win32) and pyright (also Windows) clean.
Log: `.ai/temp/step4/suite-c2b.log`. For Assay: the fix diff `ff1fe1a..630bf8e` and `d207b61`.

### Step 5, store side (`d207b61`, inert)

Raw layers in store-v4 (no `folder_cache.py`, no `raw_fill` helper yet: they wait for I/O Fixes):
`write_raw_file`, `start_raw_job` (`gen_raw`, `raw:<key>`, root epoch, the folder's `job_seq`), `save_raw_batch`
(one transaction and fit check per batch; same file kept, a later job's version replaces, changes in place named in
`overwritten` for Q28.6; over budget: nothing saved, never pending, as T~1 proposes), `mark_raw_seen` (`gone_at`),
`raw_rows`, `read_raw`, `remove_raw`; raw bytes and v3's counted bytes in `_live`; `inventory()["raw"]` and
`["older_stores"]` (Q28.5's list); Make room's order (datasets, raw seen, only copies; plan `raw_paths`,
`only_copy_paths`, `items`); a root's Clear takes its raw layers; the sweep's existing orphan rule over `raw/`;
the admin's `clear_raw` and `removed` kind `raw`. 16 tests in `tests/test_raw_layers_store.py`.

Assay's pass 3 (`99f7fd1`) on it, both fixed with a test that fails first:
- **C2-10 Low** (`0c08c5c`): the only-copy mark goes by when its evidence was taken: a sighting (a listing's
  time; a batch's `RawEntry.read_at`) clears `gone_at` only if newer than it, and a listing marks a shot gone only
  if newer than its last sighting.
- **C2-9 Low** (`6603b4b`): Don't cache with remove cached data also takes the folder's raw layers whose files
  were seen, and keeps only copies. **For Tony to confirm** (CoCo's decision per Q22.6: an only copy is never
  removed without being named; step 6's dialog may name and offer them).

Assay's notes for later steps:
- **Step 6:** Settings › Cache's Clear all passes `kinds=list(KINDS)` (`CacheTab.py:538`), so it doesn't take raw
  layers although it says "Removes everything in the disk cache"; with the raw row, Clear all includes `raw`. Make
  room's dialog names `only_copy_paths`.
- **Step 5's `raw_fill`:** publish each `.hlb` just before its batch's save (an unsaved file is an orphan the sweep
  deletes after an hour; a paused job could pass that).
- **Step 5's `raw_fill` passes `RawEntry.read_at`** (when it read each file), or C2-10/C2-11's ordering falls back to
  the save's time (Assay, pass 4).

Assay's pass 4 (`3c239a9`), both fixed with a test that fails first:
- **C2-11 Nit** (`0579fa1`): a replacing raw batch carries `gone_at` when a listing at or after its `read_at` found
  the shot gone.
- **C2-12 Nit** (`3f98958`, test-only): the via-layer test refuses file opens on its own thread only.

Not changed: `trim` (a lowered budget) still removes datasets only (A~4: give it Make room's order).

Checks at `3f98958`: **8746 passed, 672 skipped, 2 warnings in 134.48s; no RERUN**; mypy (also win32) and pyright
(also Windows) clean. Log: `.ai/temp/step4/suite-c2d.log`.

### Tony's answers (2026-10-31, via CoCo) and what's next

- **T~1 yes**: a raw batch over the budget is never saved and never asks. **T~2**: keep zstd 9. **T~3 yes**: store-v4
  carries `datasets` through stage 1. **C2-9 confirmed**: Don't cache with remove cached data keeps only copies.
- Checkpoint 2 lands at `a7b7257` (Assay pass 5: no open findings), after I/O Fixes (`471966b`) and Plot Identity.
- **New item (Tony), after step 5 and before step 7: export cache options and the file format with sample code.**
  Drafts: [hlb-format.md](hlb-format.md) (the format page, its "without HeLab" reader checked against a file
  HeLab wrote) and [design-export.md](design-export.md) (`hlb.read`, `raw_layer.columns`, `helab cache dump` and
  `export` to npz/mat/csv, read-only; one dispatch line in `helab/main.py`, to ask CoCo).
- Next: CoCo's word to merge `dev/v0.0.8`, then step 5's `folder_cache.py` part.

## Step 5 (after checkpoint 2 landed; `dev/v0.0.8` merged at `f5fe405`)

| Commit | What |
|---|---|
| `34ec22c` | cache-1: a data root's change of identity drops its folder flags and `write_beside` in RAM (`_root_prefs_gone`, beside `_root_constants_gone`'s three callers) |
| `fc25864` | `raw_fill` (helper operation), raw rows from conversions, Q28.6's notice, the Folder details line |

Files outside the owned paths, each approved by CoCo: `helab/io_helper.py` (dispatch, `SOURCE_OPERATIONS`,
`CACHE_ONLY`), `helab/utils/io_service.py` (`PAUSABLE`, `CACHE_OPERATIONS`, `LABELS`, `NOUNS`), `helab/utils/events.py`
(`RAW_OVERWRITTEN`), `helab/views/FolderDetailsPanel.py` (the amber Problems line; **Rivet's A39.4 edits that area
on Ground: merge `dev/v0.0.8` after Rivet pushes, before the next checkpoint push**).

- **raw_fill** runs on the background lane: pausable, refused offline, held during a cache move, and labelled
  "Cache raw pulses". It holds its slot until its exit is confirmed (`IOService`'s rule, unchanged). Its timeout is
  `NO_PROGRESS_TIMEOUT`, fed by heartbeats while it lists, reads and encodes. At most one per folder is queued or
  running (owner `raw_fill:<path>`, `IOService`'s dedup); a folder asked again, or one that yielded (`more`), is
  queued again when its run ends, at the back of the lane. It is never retried after an error until the next save
  asks.
- It is **triggered** by a valid `cache_saved`: Load, auto-load, presets' and reopened plots' loads, and Live's
  saves. Conversions save their own raw rows instead (`convert._RawRows`: cache or beside output, a data root,
  store-v4, online). Never for listings or scans, a Don't cache folder, without a data root, or in store-v3.
- **Q28.6:** a desktop notification once per shot per session, a log warning naming the folder, and Folder details'
  Problems line in amber ("N raw file(s) overwritten since cached", the files in its tooltip).
- Not built: the Folder details line comes from `FolderCache.raw_overwrites`, which lasts the session only (as
  Tony asked: once per shot per session).

**CI** for `fc25864` (pushed by CoCo): run 41182176328 was green on all three OSes. I read every Tests and
Converter job's log and found **no RERUN**. Windows Tests 1/2 took 13.5 min, 2/2 took 11.5 min. Windows 1/2's
long stack is `test_quit_confirms`'s own thread dump, not a failure.

Proposed docs (CoCo's request): **`io-and-browsing.md`**, lanes: "`raw_fill` (caching v2, store-v4 only) runs on a
background lane, pausable and refused offline, one per folder (`FolderCache.schedule_raw_fill` after a valid
`cache_saved`); it yields after about 30 s of work and is queued again at the back, so scans and Live's saves never
wait behind a large folder." **`cache-store.md`**: `raw_fill`, its batches and `read_at`, conversions' raw rows,
Q28.6's notice. **`converter.md`**: a conversion in store-v4 saves its shots' raw layers.

## Step 6: the store-v3 question and Settings › Cache's rows (`fe7957b`)

- **The question** (Q19.4, Q22.3; `CacheDialogs`): with store-v4 live and a store-v3 not answered yet, asked once a
  session: "Keep using it" / "Ignore it" / "Clear it…". Keep and Ignore are the admin's `legacy_choice`, and the
  choice is recorded in v4's `meta.legacy_v3` with v3's `store_id`. Clear asks first, then sends `clear_legacy`.
- **Clear old stores…** (Q28.5) is refused while `cache_locks.other_instances` names another HeLab ("Another HeLab
  is running…"). `CacheStore.clear_legacy()` renames store-v3 aside, then deletes it; it never follows a link
  ("isn't a folder here"), and store-v3 itself refuses it. It sends `removed` with kind `legacy`.
- **Make room** names raw pulses and only copies ("raw pulses of N folders", "only copy: their raw files are gone
  from …"). While store-v3 counts in the budget it also offers "Clear old stores…". `room_paths` is exactly what
  it named (`room_items`).
- **Settings › Cache** (store-v4 only): a Raw pulses row (shots, folders, size, only copies; Clear, which warns
  about only copies) and an Older cache row (size and choice; Ignore it / Keep using it; Clear…). Clear all takes
  raw pulses too. IDs: `cache_clear_raw`, `cache_legacy_choice`, `cache_clear_legacy`.
- Tests: `tests/test_store_v3_question.py` (9).

## Tony's export item (`8627566`)

- `helab.utils.hlb.read(path)` (no alias). `raw_layer.columns(layer, bin_time=25e-12)` gives `channel`,
  `time_bins` (absolute, int64) and `time_s`, in stored order.
- **`helab cache dump FILE`** prints the header as JSON (arrays without chunk lists, with `compressed_bytes`); the
  whole file is checked.
- **`helab cache export FILE|--folder FOLDER [--cache DIR] [--to npz|mat|csv] [--out] [--bin-time] [--force]`**:
  - npz: `savez_compressed`, with `header` as JSON text. mat: `scipy.io.savemat`, compressed. csv: one row per pulse.
  - A file goes to `./<stem>.<ext>`, a folder to `./helab-export-<name>/d<N>.<ext>`.
  - Never replaces a file without `--force`; refuses an `--out` inside a `store-v*` folder.
  - `--folder` keys the folder by its nearest `.helab-root`, as the app does. It reads store-v4 through a
    `mode=ro`, `NO_CKPT_ON_CLOSE`, `query_only` connection, so the store's files stay byte-identical (tested by
    hash).
  - Exit codes: 0 done, 1 nothing to export, 2 an error.
- `helab/main.py`: one dispatch line beside convert's, after the frozen helper entry point. `helab cache` loads
  no PyQt6 module at all (subprocess test). **Note:** `--folder` without `--cache` imports
  `helab.utils.constants` for `cache_dir()`, which loads QtCore (not widgets, no GUI); `--cache DIR` avoids it.
- No new dependency: scipy is already one.
- The format page: [hlb-format.md](hlb-format.md). It covers the byte layout, header fields, codecs, raw layers'
  encodings and row order, the format rule, Python with and without HeLab, the CLI, and MATLAB via `.mat`. Its
  "without HeLab" reader runs as a test. **Where it goes is CoCo's call** (proposed: `docs/hlb-format.md`, linked
  from the README's usage section and `cache-store.md`).
- Tests: `tests/test_cache_cli.py` (8).

## Step 7: the integration check (`393f999`)

`tests/test_caching_v2_session.py` runs one session with the switch on, through the app's own `store_options()`
(the test's private cache folder), beside an older HeLab's store-v3:

1. Load, then `raw_fill` (saves 3, then 0).
2. Each layer equals its file: the same SHA-256, size and facts, and the TXY made from the layer
   byte-identical to the file's.
3. Clear all, raw pulses included.
4. Make room through a real `cache_full`: X's dataset, then Y's raw layers, with Z's only copy kept even
   though it alone would do; a lower budget puts `raw-only:Z` last. The adopt removes exactly what was named.
5. store-v3's files hashed unchanged (`-wal`/`-shm` aside), with `sqlite3.connect` and `CacheStore.__init__`
   watched: nothing but `LegacyStore` opens it.
6. A COPY cache move with both stores, both verified, store-v3 carried unchanged.
7. `helab cache export --folder` on the moved store gives back Z's pulses after its raw files are gone.

A mutation (Clear's default leaving out raw) fails it.

**Checkpoint 3** (`45a7aa5`, pushed): CI 41184198967 was green on all three OSes. I read every Tests and Converter
job's log (9 jobs) and found **no RERUN**. Windows Tests 1/2 took 14.0 min, 2/2 took 11.8 min. The local full suite
gave 8851 passed, 672 skipped, no RERUN; strict mypy (also win32) and pyright (also Windows) are clean.

### Checkpoint 3 review fixes (Assay, `review-checkpoint3.md`, `1af8796`)

| Finding | Commit | Fix | Test (fails before the fix) |
|---|---|---|---|
| C3-1 Medium | `c1489ae` | `_RawRows` also saves at `BATCH_BYTES`; `save_batch` encodes each shot under the converter's `_Ticker` (`compute_budget` of its size), for `raw_fill` and conversions | `test_a_conversions_raw_rows_are_saved_by_bytes_too`, `test_encoding_a_large_raw_file_keeps_heartbeats_going` |
| C3-2 Low | `c1489ae` | `raw_fill` leaves a blank file, or one without a final newline, waiting (`raw.not_done`'s checks that need no profile) | `test_a_fill_leaves_a_raw_file_that_isnt_finished_waiting` |
| C3-3 Nit | `3938938` | The choice holds for the store-v3 it was made for (`_legacy_choice`). After Clear, a store-v3 there again is unanswered; under Keep, one with another `store_id` is. Ignore holds for whatever is there (an ignored store-v3 is never opened to tell) | `test_a_store_v3_made_again_is_asked_about_again_unless_ignored` |
| C3-4 Nit | `3938938` | `measure_legacy` lists `store-v3.clearing-<8 hex>` (`leftover`, `leftover_bytes`). Settings › Cache's Older cache row shows them with Clear… (asked). Clear old stores… removes them; housekeeping never does. `clear_legacy` returns the bytes actually removed | `test_what_a_clear_cut_short_leaves_is_shown_and_removed_only_when_asked` |
| C3-5 Nit (docs) | this handoff | Added to step 8's AGENTS.md proposal below | — |
| C3-6 Nit | `877a24f` | `_read_only` inside a `try`: "can't be opened read only (…)", exit 2 | `test_a_store_that_cant_be_opened_is_an_error_not_a_traceback` |

- **C3-3, which of Assay's two:** the comparison, kept to what can be told without opening an ignored store-v3.
  The docstring's promise now holds for Clear and Keep; for Ignore it is reworded.
- `test_store_v4.py::test_after_ignore_or_clear_store_v3_is_never_opened[clear]` set `clear` with store-v3 still
  present: under C3-3 that is a store-v3 made since. Its `clear` case now runs a real Clear.
- **Not done:** C3-2's optional half, not sending `raw_overwritten` when the replaced row wasn't finished. With
  the fix, `raw_fill` no longer saves unfinished rows, and conversions check `not_done` first. Only a row saved
  before this fix, with the switch on (no users), could still trigger it.
- **Checks:** the full suite (-n 4) gives **8857 passed**, 672 skipped, **no RERUN**. mypy --strict (helab, tests,
  win32) and pyright (also Windows) are clean.
- **CI 41186805673** (`9abdb58`): macOS Tests 1/2 **failed**. My own new test,
  `test_encoding_a_large_raw_file_keeps_heartbeats_going`, needed **5 RERUNs** and still failed: it got 2–4
  heartbeats where it asked for ≥ 5. The cause is the test itself: it counted heartbeats in a fixed 0.3 s
  window at a 0.02 s interval, and the loaded runner's ticker thread got fewer turns. The code was fine. The fix
  (the next commit) makes the slow encode last until three heartbeats have come, with a 10 s deadline. It passes
  25 of 25 runs under a 12-process CPU load with reruns off, and fails without C3-1's ticker.
  - **Corrected (CoCo):** that run's other jobs passed, but not all without RERUNs. I had read only the failed job's
    log; I have now read all nine. **Windows Tests 2/2 (job 124495315262) had 2 RERUNs** of
    `tests/test_io_service_run.py::test_writing_held_data_out_counts_as_progress`, in both cases `assert 2 == 1`
    (marks 0.72/1.36 ms and 0.73/1.36 ms). It is the known Windows timing flake in known-issues (also seen in
    CI 41164715526); IOService is untouched by this floor. The other seven Tests and Converter logs had no RERUN.
- **CI 41188263711** (`375562e`, the fixes with the test fix): green on all three OSes. I read every Tests and
  Converter job's log (9 jobs): **no RERUN**. Windows Tests 1/2 took 12.9 min, 2/2 took 10.9 min.

## Step 8: doc proposals for checkpoint 3 (steps 5–7, the export, cache-1)

The list below ("Proposed doc changes") was applied at checkpoint 2's docs commit (`7180751`); these are what
came after it. The switch stays off, so none of this is user-visible yet.

- **AGENTS.md** (wording only):
  - Code map, the `helab/convert_cli.py` row becomes: "`helab/convert_cli.py`, `helab/cache_cli.py` |
    `helab convert --watch` (headless converter); `helab cache dump|export` (caching v2's `.hlb` files, read
    only)".
  - Setup and commands, under `helab convert …`: "`helab cache dump FILE.hlb | export FILE.hlb|--folder FOLDER
    --to npz|mat|csv   # read only`".
  - The "frozen helper entry point … (after `freeze_support()`, before the `convert` dispatch)" rule stays
    true (`cache`'s dispatch follows convert's).
  - The disk-cache rule (C3-5, Assay's wording): "Only helpers, `helab convert` and, read only, `helab cache`
    open the store (…)".
  - Housekeeping: nothing new. `clear_legacy` is the user's choice, asked first, and sends `removed`
    (kind `legacy`). It also removes what an earlier Clear cut short left (`store-v3.clearing-<8 hex>`,
    C3-4). Those folders are shown in Settings › Cache and never removed without asking.
- **cache-store.md**, "store-v4":
  - The header line: "(stage 0 and checkpoints 2 and 3, landed …)".
  - **Raw layers**: drop "inert until `raw_fill`" and add: "`raw_fill` (`helab/io_ops/raw_fill.py`) fills
    them on the background lane after a valid `cache_saved`. Batches are at most 50 shots or 64 MB, each `.hlb`
    published just before its batch's save; `read_at` is the evidence; it yields after about 30 s (`more`).
    Over the budget it saves nothing and asks nothing (Q42.1). A file that is blank or doesn't end with a newline
    waits, as in the converter (C3-2). Each shot encodes under the converter's ticker (C3-1). A conversion in
    store-v4 saves its shots' raw rows through the same `save_batch`, by 50 shots or 64 MB. A raw file changed since it was cached is replaced, and Q28.6's
    notice says so (`raw_overwritten`: once per shot per session, a log warning, Folder details' amber
    Problems line)."
  - **store-v3 under v4**: replace "(until step 6's question is answered)" with: "The question (Keep using it /
    Ignore it / Clear it…) is asked once a session while unanswered (`CacheDialogs`); the choice goes in
    `meta.legacy_v3` (admin `legacy_choice`). **Clear** (`clear_legacy`, Settings › Cache or Make room's
    Clear old stores…, Q28.5) asks first, is refused while another HeLab runs (`cache_locks.other_instances`),
    renames store-v3 aside and deletes it, never through a link, and sends `removed` kind `legacy`. What a Clear
    cut short leaves (`store-v3.clearing-<8 hex>`) is listed in `measure_legacy` and shown in the Older cache
    row; only the next asked Clear removes it (C3-4). The choice holds for the store-v3 it was made for. After
    Clear, a store-v3 there again, or under Keep one with another `store_id`, is unanswered and asked about
    again. Ignore holds for whatever is there, never opened (C3-3)."
  - Removals: "`removed` kinds `raw` (rows in `raw`) and `legacy`; Clear all takes `raw` too."
  - A new bullet, **Reading `.hlb` outside HeLab**: "`helab.utils.hlb.read(path)`, `raw_layer.columns`, and
    `helab cache dump|export` (`helab/cache_cli.py`: read only; a folder through a `mode=ro`,
    `NO_CKPT_ON_CLOSE` connection; never into a `store-v*` folder, never replacing without `--force`). The
    format page: `docs/hlb-format.md`."
- **The format page**: [hlb-format.md](hlb-format.md) to `docs/hlb-format.md` (Q~2), linked from the README and
  `cache-store.md`.
- **data-roots.md** (cache-1): "When a data root's identity changes (re-marked, or its marker replaced), RAM drops
  its folders' flags and `write_beside` (`FolderCache._root_prefs_gone`, beside `_root_constants_gone`), so the
  old root's flags don't stick to the new one's folders."
- **io-and-browsing.md**: the lanes text in step 5's section above. Add `raw_fill` to the operations list
  (`SOURCE_OPERATIONS`, `CACHE_ONLY`, `PAUSABLE`), and `raw_overwritten` and `raw_fill_done` to the events.
- **app-runtime-and-ui.md**: Settings › Cache's Raw pulses and Older cache rows (store-v4 only; IDs
  `cache_clear_raw`, `cache_legacy_choice`, `cache_clear_legacy`); the store-v3 question in `CacheDialogs`; Make
  room naming raw pulses and only copies, with "Clear old stores…"; Folder details' amber raw-overwritten line.
- **converter.md**: "A conversion into the cache or beside, with a data root and store-v4 live and online, saves
  its shots' raw layers (`convert._RawRows`, through `raw_fill.save_batch`)." And `raw_layer.columns`,
  `BIN_TIME`.
- **testing.md**:
  - `tests/test_caching_v2_session.py` is stage 1's switch-on integration check. It watches
    `sqlite3.connect` and `CacheStore.__init__` for any open of store-v3 outside `LegacyStore`, and hashes v3.
  - `tests/test_cache_cli.py::test_helab_cache_starts_no_qt`: a subprocess, asserting no PyQt6 module loaded.
  - The `v4_live` fixture in `tests/test_raw_fill.py` (`cache_store._reset_live_layout(4)`).
- **The plan** (`roadmaps/caching-v2.md`, stage 1): tick step 5's rest (`fc25864`, `34ec22c`), step 6
  (`fe7957b`), step 7 (`393f999`) and the export (`8627566`). "Stage 1 built; the switch stays off until stage 2
  and Tony's go."
- **known-issues**: none new. The full suite's "Clean up disk cache failed … database is locked" warning (a
  test's private store-v3, switch off) is the SMB audit leftovers' "startup 'database is locked' on a fresh
  store"; it is a warning, not a failure or a RERUN.
- **README**: a short "Exporting cached raw pulses" section under usage (Q~2): `helab cache export --folder
  FOLDER --to mat`, with a link to the format page. Once the switch is on, that is.

### New items (provisional)

- **Q~1 The store-v3 question's and Settings › Cache's wording** (for Tony to confirm; user-visible once the switch
  is on):
  - The title is "An older disk cache".
  - The text: "The cache folder also holds an older HeLab's disk cache (store-v3, 6.0 MB)."
  - The detail: "Keep using it: HeLab reads its records and saved analysis where the new cache has none, and it
    counts toward the disk budget. Ignore it: it stays on disk, unused. Clear it: it is removed, after asking.
    Settings → Cache can change this later."
  - The buttons: Keep using it / Ignore it / Clear it….
  - Clear's question: "Remove the disk cache of an older HeLab (store-v3, …)? This HeLab no longer reads it; an
    older HeLab started later would begin an empty one. This can't be undone."
  - Settings › Cache rows: "Raw pulses", "Older cache (store-v3)".
  - Proposed: as built.
- **Q~2 Where the `.hlb` format page lives**:
  - (a) `docs/hlb-format.md`, linked from the README and `cache-store.md`;
  - (b) a README section;
  - (c) `.ai/architecture/` only.
  - Proposed: (a). Users read it, and its MATLAB part is for lab members. The README gets a two-line pointer
    once the switch is on.
- **M~2 On screen, switch on, test settings and a temp cache folder only** (`floor-env.sh`): see the store-v3
  question once, each Settings › Cache row and its buttons, Make room's text with raw pulses and only copies,
  and Folder details' amber line after overwriting a raw file in a temp folder.
- **M~3 MATLAB**: run `helab cache export d1.hlb --to mat` on a layer from the sample set's via-layer run (or a
  temp store) and the format page's MATLAB lines (`load`, `jsondecode(s.header)`).
- **A~5** `helab cache export` of stage 2's TXY layers (`kind` `txy`): same CLI, the layer's columns.
- **A~6** `helab cache export --folder` without `--cache` imports `helab.utils.constants` (QtCore) for
  `cache_dir()`. A Qt-free reader of the cache-folder setting would make all of `helab cache` Qt-free. Minor:
  no widgets and no GUI start either way.

## Proposed doc changes (for the Coordinator; checkpoint 2's, applied at `7180751`)

- **known-issues** (cache-4): replace the `test_cache_switch.py` leak entry with: "Fixed on
  `agent/caching-v2` (`46f481f`): the leaks were the tests' own `with sqlite3.connect(...)` blocks (29 in
  11 files; sqlite3's context manager commits but never closes), not the store's error paths; tests now use
  `contextlib.closing`." In the entry above it (`test_root_discovery.py::test_volume_check_alone_…`), the
  sentence "The collected object may be one of `test_cache_switch.py`'s leaked connections (next)" becomes
  "…may have been one of the tests' leaked connections (fixed, `46f481f`); the patch-the-name fix still stands."
- **cache-store.md**, "Tables added within store-v3" (cache-6): "…and its re-key of a nested root leaves the
  subtree's constants (0.0.5) and converter flags (0.0.6) behind, and a 0.0.6 HeLab's Clear folder
  preferences leaves `write_beside` on."
- **cache-store.md** and the converter's Clear (S0-1): Clear converted TXY "removes … their leftover temporaries
  once over an hour old" (a younger one may be a conversion's write in progress).
- **cache-store.md**, "Converted TXY in the cache folder" (A19.2): add "Clear fences conversions already
  running (A19.2): it first sets a new token in the index's `fence` table, and a conversion that started
  before writes no TXY after it (its shots wait as `cleared` and convert at the next check); a base with
  no index yet, a damaged or busy index and 0.0.7a1's Clear or conversions aren't fenced."
- **converter.md**: the same in the converter's index section, plus "`txy.write_atomic` takes
  `after_rename` (run after the rename, before the folder fsync)" and the `shot_waiting` reason `cleared`.
- **AI_TODO**: A19.2 done.
- **AGENTS.md** (for Tony to confirm, wording only):
  - Disk cache: "Only helpers (and `helab convert`) open the store (`DIR_CACHES/store-v3`, `CacheStore`; with the
    `store_v4` switch on, `store-v4`, and store-v3 then only through `LegacyStore`, read only)".
  - `_migrate`: "A table or column added within `store-v3` or `store-v4` is added to older stores by
    `cache_store._migrate` (store-v4: `store_v4.migrate`) on every writable open, never only in `SCHEMA`."
  - Housekeeping (CoCo's note b): "the sweep deletes retired dataset and layer files, and store files no row names
    once over an hour old": the same orphan rule over `raw/` too (step 5), **no new removal**.
  - Settings: the `store_v4` row stays off until stage 2 and Tony's go (Q28.3).
- **cache-store.md:** a "store-v4 (caching v2, behind the switch)" section: the switch and `layout_of`; v4's
  tables and meta; per-kind epochs; makers and `HELAB_STORE_MAKER`; `LegacyStore`, the import and Keep;
  `inventory()["legacy"]`; cache moves with two stores (primary, `store_ids`).
- **converter.md:** `raw_layer` (encodings, facts, `RAW_PARSER_VERSION`), `check.convert_via_layer` and
  `check_samples.py --via-layer`.
- **testing.md:** the `switch_on` fixture in `tests/test_store_v4.py` (the `store_v4` row in the test's ini plus
  `cache_store._reset_live_layout()`); `tests/test_raw_layer.py` in the Converter backends job.
- **The plan** (`roadmaps/caching-v2.md`): stage 1's store-v4 carries `datasets` (T~3, pending Tony); the raw
  layer's compact limit is 2^62; the sample set's via-layer result.

## Follow-ups (provisional)

- ~~A~1~~ done in stage 0 (S0-1, above).
- **known-issues** (the fixes' CI 41164715526): add to the `test_io_service_run.py::test_writing_held_data_out_counts_as_progress`
  entry "Again: `agent/caching-v2` CI 41164715526 (Windows Tests 2/2, job 124429733436, marks 1.4 ms and 5.2 ms) and
  CI 41186805673 (Windows Tests 2/2, job 124495315262, 2 RERUNs, marks 0.72/1.36 ms and 0.73/1.36 ms)".
  Its only RERUN; IOService untouched by this floor.
- (Merged at `7180751`: A~3 → A42.1, A~4 → A42.2, M~1 → M42.1; A~2 is in known-issues' pickle entry.)
- **A~2** `pack_dataset`'s 2.1 GB limit stays for v4's `datasets` in stage 1 (blosc-pickle); stage 2's `.hlb`
  segments end it.
- **A~4** `trim` (the user lowers the budget) in Make room's order in store-v4 (today datasets only).
- **A~3** copy-on-use of store-v3's saved results into v4 (or decide read-through is enough while v3 is kept).
- **M~1** time the raw codec on the lab PC (`check_samples.py --via-layer`; zstd 9 measured 16 MB/s of raw text
  per M4 Max thread).
- ~~**Step 5 owes:**~~ done in step 5: `raw/` under the sweep's orphan rule; v3's `legacy_bytes` in v4's usage
  and fit checks (`_legacy_counted`); the maker in each `.hlb` header (`raw_fill.save_batch`, which
  conversions' raw rows use too); Make room's order.
- **known-issues** (S0-2, Assay; `explorer_live.py`, I/O Fixes' file, not fixed here): "Live's line counts
  shots waiting with reason `cleared` (A19.2: Clear converted TXY ran during that conversion) as stuck until
  the next check, and their tooltip ends 'A waiting file is checked again only when it changes', which is
  wrong for `cleared`: the next check converts them. Transient (one check interval). Fix: leave `cleared` out
  of `stuck()` (Assay's correction; not in `CONVERT_SETTLING`)."

## Stage 2: open questions with proposed answers (no code; after checkpoint 3 landed, `c2d0ece`)

Stage 2 waits for Tony's go. These are the readiness note's D7 and gap 10, plus what building stage 1 showed.
Sources: the readiness note §1 and §3, the store-v4 design note §1–§6, the plan's "TXY layers and the policy",
and the decided Q18.2, Q19.3, Q22.1–Q22.11 and Q42.x. Numbered provisionally after Q~1 and Q~2 above (`Q~3`…),
to be merged by CoCo.

**Q~3 (readiness D7): the default policy.**
- *The conflict.* Q19.3 says every TXY source a plot uses is cached as its own layer. The design's `raw`
  policy writes no HeLab layer, and the plan calls raw + tag "the default once the converter is robust".
  Q22.11 (decided) settles most of it: "cache the raw layer and the selected TXY versions at the same
  time; a global default caches raw files; a per-folder override picks the source priority".
- *Proposed:* the default is **raw + used**. Raw rows where there are raw files, plus every TXY layer a
  load composes: the `matlab` layer for MATLAB shots, and the HeLab layer of the tag the load used,
  including a plot's other tag (Q19.3, "should be rare").
  - **raw** (convert on load: no HeLab layer; the `matlab` layer still, since it can't be derived) and
    **txy** (no raw rows: archives, or raw not wanted) are explicit choices, global or per folder.
  - "raw + tag" stops being a separate policy: the selected tag is the tag the load uses (Q~4).
  - As decided, a policy only decides what new saves write. Every layer is read, switching migrates
    nothing and removes nothing.

**Q~4 (gap 10b): one setting or two for "which TXY".**
- *The question.* Q22.11's per-folder "source priority" overlaps two things: Q18.2's source mode plus
  profile tag (global for tabs and Live; plots pick their own), and the design's `cache_policy.tag`.
- *Proposed:* one choice. **What a load reads** is Q18.2's source mode and tag, with a per-folder override
  (a row like `convert_prefs`: `source`, `tag`, `set_at`). **What is cached** is `cache_policy`
  (`path`, `policy` ∈ raw+used / raw / txy, `set_at`), with no `tag` column. So "cache this folder's
  p22v1" means "this folder loads p22v1", and Q~3's default caches what is loaded.
  - The override is the user's own state, imported like `convert_prefs`.
  - Clear all never removes it; Clear folder preferences does.

**Q~5 (gap 10a): a HeLab layer read from beside TXY, keyed per shot or per layer.**
- *The question.* Under `txy` (or with no raw file), a HeLab shot read from a beside `d_txy_helab_<tag>_<N>.txt`
  has no raw fingerprint. The design puts `by_txy` "in `info`", but one `(path, layer)` row can mix shots
  converted from raw with shots read from text.
- *Proposed:* **per shot.** Each fingerprint entry gains its kind, `[shot, size, mtime_ns, "raw"|"txy"]`, and
  `by_txy` goes. The loading order prefers raw: once the raw layer holds the shot, a TXY-keyed entry is
  replaced by the raw-keyed one at the layer's next save, so it is converted once.
  - Saved results made on a TXY-keyed shot then show as outdated once; that is the same rule as v3's
    HeLab shots, §4.
  - Make room counts a TXY-keyed shot whose text is gone as an only copy (not rebuildable).

**Q~6: store-v4's `datasets` table once `txy_layers` exist.** Q42.3 carried `datasets` through stage 1. Only
switch-on users (testers) have v4 rows.
- *Proposed:* stage 2 never writes `datasets`. It reads them like Keep reads store-v3: a dataset whose
  shots' fingerprints still match fills the `matlab` or `helab:<hash>` layer at the load's save. Make room
  and Clear remove `datasets` rows as today.
- No conversion code, and nothing removed without asking. A later layout (`_migrate`) may drop the empty
  table.

**Q~7: store-v3's MATLAB shots under Keep (the "v3 seed").**
- *Proposed:* **copy on use.** A load that finds a v3 dataset shot with the current fingerprint adds it to
  the `matlab` layer's save: it is read already, with no extra I/O, and v3 stays read only.
- Saved results stay read-through (A42.1 decides their copy separately).

**Q~8 (D8, stage 2's part): Make room's order with TXY layers.**
- *Proposed order:*
  1. HeLab layers whose raw layer is held (rebuildable locally);
  2. other folders' `matlab` layers and TXY-keyed HeLab shots whose source file the last listing saw;
  3. raw layers seen;
  4. only copies of any kind (raw layers whose raw file is gone, `matlab` and TXY-keyed shots whose file
     is gone), named.
- `trim` (A42.2) follows the same order.
- As in stage 1: exactly the named items, or nothing.

**Q~9: Live's segments (F8) and the budget.**
- *Proposed:* a save appends one segment of the new and changed shots, with one fit check for that
  segment.
- Compaction (over 8 segments, or over half superseded) runs in the same helper job only when the
  rewritten copy fits beside the old one. Otherwise it waits for the next save, and it is never a reason
  to ask Make room.
- The old segments are retired, then swept as today, so there is no new removal rule.

**Q~10: `pending_saves` with several units per folder (readiness gap 2).** Stage 1 never makes a pending raw
unit (Q42.1: over the budget it is not saved and never asks), so `UNIQUE (path)` held.
- *Proposed for stage 2:* keep one pending unit per folder. A TXY-layer save that doesn't fit merges its
  parts into that folder's pending row (`parts`, as the design says), so one question names everything it
  would save. Raw stays never-pending.

**Q~11: RAM while converting from the raw layer.**
- *Proposed:* no change to the RAM budget. A decoded raw layer lives only in the helper during a load's
  conversion. Its peak is bounded by the worker count times a shot, since each shot decodes, converts and
  is dropped. The GUI's RAM budget keeps counting the datasets it holds (`ram_buffers`) as today.

**Q~12 (readiness gap 11): identity across computers.** A raw fingerprint is `(size, mtime_ns)`, and SMB
clients on macOS and Windows may report different mtime resolution.
- *Proposed:* stage 2 keeps `(size, mtime_ns)` as the key on each computer. The stored `sha256` decides a
  match only for data made elsewhere (Q27.x's versioning, a later stage). There is no cross-computer
  matching in stage 2.

**Q~13: when the `store_v4` switch turns on (Q28.3).**
- *Proposed:*
  - not before stage 2 has landed and Tony has used it with the switch on, on his Mac and one lab PC
    (M~2, M42.1's codec timing);
  - then on by default in the release that ships stage 2, with store-v3 under Keep until the user answers;
  - the switch row stays for one release, so a lab PC can go back to store-v3 while v4 settles.

*Also for stage 2, no question:* `helab cache export` of TXY layers (A~5); `pack_dataset`'s 2.1 GB limit ends
with segments (A~2); the `.hlb` `kind` `txy` is additive within format 1.

# Stage 2 (Tony's go, 2026-11-02; brief-stage2.md)

## Step 1: the design addendum (`1eddfaf`)

[design-stage2.md](design-stage2.md). CoCo's answers:
- **S~1:** the files outside the owned paths, yes.
- **S~2:** raw-keyed wherever a raw file is listed, yes (CoCo tells Tony as an FYI).
- **S~3:** (b), with three conditions:
  - the file is written atomically, by the GUI only;
  - `helab cache` falls back to QtCore when it is missing, or names a folder that isn't there;
  - it is not part of housekeeping.
- **S~4:** share one view, yes.
- **S~5:** whole rows, yes.
- **S~6:** goes to Tony; build with the proposed labels.
- A40.2 and A44.2 joined stage 2 (CoCo).
- A44.2's two call lines (`helab/main.py`, `helab/views/CacheMover.py`) approved, with a test that
  `helab convert` doesn't write the file.

## Step 2: the store side, inert (`b691d26`, `a70d261`)

- **`b691d26`:**
  - store-v4's stage 2 tables (migrated into stage 1's stores) and `helab/convert/txy_layer.py` (PURE);
  - `CacheStore`'s TXY layers: save units, per-shot job order, views, `confirm_view` (A40.3), pending parts
    merged per folder (Q45.8), compaction only when it fits (Q45.7), `mark_txy_seen`;
  - one planner for Make room and `trim` (Q45.6, A42.2);
  - Clear `txy` everywhere it joins; the sweep, `_live`, inventory and cache move over `txy/`;
  - **S2-0:** `rekey_subtree` moves `raw_layers` and the TXY tables;
  - admin `clear_txy` and `folder_choice`.

  Tests: `tests/test_txy_layers_store.py` (19). Mutations of S2-0, the migration, the waiting parts' files
  and the policy each fail a test.
- **`a70d261`:**
  - A44.1: `helab cache export --folder F --kind txy [--layer]`, and a segment file;
  - A44.2: `cache-folder.json`, written by the GUI at startup and after a move, read by `helab cache` with
    CoCo's fallbacks.

  Tests: `test_cache_cli.py` (13), `test_cache_folder_record.py` (convert writes none; the GUI writes it).
- **Departures from the addendum, to note:**
  - **`save_dataset` is still allowed in store-v4.** The addendum's refusal moves to step 3, with the loads
    that replace it. Refusing it now would stop switch-on loads from caching anything until step 3.
  - **A merged waiting unit keeps the later job's view only.** One pending row per folder (Q45.8) can hold
    one view. Parts of every layer are kept; another source mode's view is made again at its next load.
  - **The GUI's Make room items** (`CacheDialogs.room_items` builds them from the room dict's keys) don't
    yet know `txy_*`. Step 5 adds them, after merging `dev/v0.0.8` (Rivet's strings in that file). Until
    then a switch-on Make room that names TXY layers finds its plan changed and removes nothing: safe.
  - **`gone_at` on a layer** is set and cleared by the latest listing (`mark_txy_seen`). Unlike raw rows'
    C2-10 ordering, a late older listing can flip it. Step 3's loads call it with the listing they took;
    say so if it needs raw's ordering.
- **Docs proposal:** `docs/hlb-format.md` gets a "TXY layers" section (§3's arrays and meta, the precision
  rule) and `helab cache export --kind txy`. AGENTS.md's code map row for `cache_cli.py` adds "TXY layers".
- **CI 41375836115** (`84ccaeb`, checkpoint 1): green on all three OSes. I read every Tests and Converter job's
  log (9 jobs). Windows Tests 2/2 (job 125055805809) had **2 RERUNs**, both known Windows flakes, both
  passed on retry:
  - `test_gui_responsiveness.py::test_timeout_retry_releases_dead_helper_slot_while_artifact_reader_is_blocked[1]`:
    `waitUntil timed out in 3000 milliseconds` at line 292, the known entry's line (listed as `[2]`);
  - `test_test_isolation.py::test_pytest_imports_the_checkout_it_runs_in_before_any_other`: the known pathlib
    `lstat` collection error.

  No other RERUN. Windows Tests 1/2 took 19.1 min (2/2: 13.7). The new store tests take under a second.
  **known-issues proposal:** add "Again: `agent/caching-v2` CI 41375836115 (Windows Tests 2/2, job
  125055805809)" to both entries, and "`[1]` too" to the first.
- **Windows Tests 1/2 timing** (CoCo asked; 17.4 min of pytest, 19.1 min job, against 11.1 and 13.4 in CI
  41188263711). Measured from the log's per-worker PASSED timestamps (CI prints no durations):
  - the stage 2 tests cost little: `test_txy_layers_store.py` 7–8 s of worker time, `test_cache_cli.py`
    3–4 s, `test_cache_folder_record.py` 0.9 s, `test_caching_v2_session.py` 5 s;
  - the growth (36.6 → 63.7 worker-min) is in files this floor didn't change: `test_convert_fastio.py`
    131 → 484 s, `test_convert_raw.py` 217 → 567 s, `test_store_identity.py` 227 → 380 s,
    `test_cache_move.py` 13 → 84 s;
  - group 1 ran about the same number of tests (4419 against 4409), and fastio's CPU-bound parsing was
    3.7× slower, so a slower runner this time, not new tests.

  Under the ~25 min stop line; watched at every run from here on.

### Checkpoint 1 review fixes (Assay, `review-s2-checkpoint1.md`, `7d5c567`)

| Finding | Commit | Fix | Test (fails before the fix) |
|---|---|---|---|
| S2-1 Medium | `6b0f998` | `trim` stops before only copies (`_free_space(only_copies=False)`) unless given the named plan (`expected`), which it removes exactly or not at all; `trim_plan(budget)` and the admin's `trim` with `plan_only`/`plan` give step 5's question what goes; `trim_estimate` is store-v3's | `test_trim_keeps_only_copies_unless_its_plan_names_them` |
| S2-2 Low | `6b0f998` | A layer keeps `seen_at` (`STAGE2_SCHEMA`, and a `migrate` addition for a store migrated before it); `mark_txy_seen` follows C2-10's rule | `test_an_older_listing_landing_late_undoes_no_mark`; the migration test, extended to a store without `seen_at` |

- **CI 41379212072** (`6b0f998`): green on all three OSes. I read every Tests and Converter job's log (9).
  Windows Tests 2/2 (job 125066159186) had **1 RERUN**, of
  `test_test_isolation.py::test_pytest_imports_the_checkout_it_runs_in_before_any_other`: the known pathlib
  `lstat` collection error, which passed on retry. **known-issues proposal:** add this run to that entry. No other
  RERUN. Windows Tests 1/2 took 9.1 min, 2/2 took 11.6.
- The step 3 work in progress was kept out of `6b0f998`: set aside as a patch, then reapplied after it.
- Assay's notes for later: `start_txy_job`'s guard also holds `gen_datasets` and the folder's epoch when step
  3d seeds layers from v4 `datasets` rows; Settings › Cache's Clear all sends `txy` (step 5).

## Step 3: loading (store-v4; the switch stays off, store-v3 unchanged)

| Commit | What |
|---|---|
| `7d185eb` | 3a: `helab/io_ops/txy_cache.py` `Access`: `_load` and `save_held` make the same calls (`row`, `full` with a loader, `touch`, `confirm`, `write`). In store-v3 these are the dataset methods; in store-v4 views and layers. Loads and Live's saves write append-only units, never a dataset. A40.3: a signature-only change only rewrites the view's info. A held shot already kept isn't read again for a save. `mark_txy_seen` at every v4 listing. Each job takes a TXY guard |
| `d8b6bae` | 3a: a cached read carries the tab's TXY source (FolderCache's `with_txy` for `cached`, and the `io_helper.py` line CoCo approved); an older request reads the folder's last used view |
| `3366640` | 3b (Q19.3): a plot's own TXY choice (a `no_cache` request) is cached under its own view in store-v4, quietly (no cache events, never waiting); Don't cache still keeps it RAM only |
| `d96c65f` | S2-3 (Assay re-check): a new layer is first seen at its job's listing time (`save_txy(seen_at=…)`, kept on waiting parts). Assay's note: the TXY guard also holds `gen_datasets` and the folder's epoch |
| `2f6c1f3` | 3c (Q45.2): the folder's own source and tag. A v4 load sends `folder_choices` and follows it for the tab. FolderCache remembers it and `with_txy` applies it to the tab's loads, Live and cached reads. `txy_sources.with_choices`; tags are resolved to the conversion profile or a built-in |
| `08895bc` | 3d: no view yet, so store-v4's own `datasets` row (Q45.4), else store-v3's under Keep (Q45.5, `LegacyStore.dataset_row`, `CacheStore.legacy_dataset`, never one store-v4 removed), seeds the layers on use. A42.1: a store-v3 result is copied into store-v4 as `result_find` returns it (`save_result(only_new=True)`) |
| `6f57918` | 3e: a HeLab shot from the raw layer (the loading order's second step), equal to its text, for built-in profiles |

- **Departures:**
  - `save_dataset` isn't made to raise in store-v4 (stage 1's tests and Q45.4's rows use it). Loads never call
    it there, and a test checks it.
  - Live checks don't open the store, so the folder's source reaches them through FolderCache, which learns it
    from a load's or the admin's `folder_choices`. A Live started with no load of that folder this session
    follows the global source until one runs.
  - 3e converts only for built-in profiles (the helper has no user profile library); others read the text.
- **Observed, not a failure or a RERUN:** one full local run printed `ERROR:root:GUI stalled for 62.74s; capturing
  thread stacks`. It comes from `gui_watchdog.py`, the main window's watchdog thread. Likely cause: a test leaves
  a main window's watchdog running after its event loop is gone. This floor's code touches neither. I saw it
  once, and it isn't in known-issues. **known-issues proposal:** "a main-window test may leave its `GUIWatchdog`
  running (a 'GUI stalled' log in a later test's worker)".
- Tests: `tests/test_txy_loading.py` (17), and additions to `test_txy_layers_store.py` (23), `test_store_v4.py`,
  `test_helper_dispatch.py`, `test_caching_v2_session.py`.
- Local full suite at `6f57918`: 8909 passed, 672 skipped, no RERUN. mypy --strict (helab, tests, win32) and
  pyright (also Windows) are clean.
- **CI 41383644340** (`e985e12`, step 3 with checkpoint 1's fixes): green on all three OSes. I read every Tests and
  Converter job's log (9): **no RERUN**. Windows Tests 1/2 took 14.2 min, 2/2 took 14.9 (pytest 12.4 and 13.0).

### Step 3 review fixes (Assay, `review-s2-step3.md`, `ad67f58`)

| Finding | Commit | Fix | Test (fails before the fix) |
|---|---|---|---|
| S3-1 Medium | `df17761` | `CacheStore.clear_folder_data`: a folder's Clear data cache (`invalidate`) takes in store-v4 its TXY layers, views and seen raw layers too, only copies kept (C2-9). `purge_datasets` takes layers and seen raw layers not used since the cutoff, only copies kept (Assay's call per Q22.6 and C2-9, **for Tony to confirm**). `_removal_events` sent | `tests/test_txy_fixes.py`: the Clear through the real `invalidate` request; the purge |
| S3-2 Low | `df17761` | The conversion from the raw layer runs before any `file_started`, under the converter's `_Ticker` (`compute_budget` of the raw size), in the load's read and the save's re-read | `tests/test_txy_fixes.py`: a slow decode keeps heartbeats going, with no `file_started` for the shot |

- **The handoff note Assay asked for:** while the HeLab text is on the share (stage 2's boundary), the raw step costs
  more CPU than parsing text on a local disk (0.48 s against 0.004 s for a 3.25 MB shot on an M4). Its gain is
  for slow shares, and offline.
- **CI 41386150963** (`df17761`): green on all three OSes. I read every Tests and Converter job's log (9). Ubuntu Tests
  2/2 (job 125087377900) had **1 RERUN**: `test_root_gui.py::test_the_gui_never_writes_the_saved_file_itself`,
  "worker 'gw3' crashed while running" it. It passed on retry. That is known-issues' entry for the same test
  ("xdist worker gw0 crashed"). **known-issues proposal:** add this run. No other RERUN. Windows Tests took 12.7
  and 10.8 min.
- The step 4 work in progress was kept out of `df17761` (a patch, reapplied after it). Step 4 is `8be1be6`, local.

### The "GUI stalled" log (CoCo asked for the test)

A full local run with its output kept (`.ai/temp/full-run.txt`) caught the faulthandler dump. The worker's main
thread was idle in execnet, waiting for more tests at the end of its run, while a `GUIWatchdog` thread
(`gui_watchdog.py:40`) was still alive.

`HelabMainWindow.closeEvent` stops the watchdog only on its full path. It returns early, leaving the watchdog
running, when a close waits for saves (`_wait_for_saves` opens `QuitSaveDialog`) or a quit dialog is open.
`qtbot.addWidget`'s close at teardown then doesn't stop it either. The likely tests are those whose window close
waits for saves: `tests/test_quit_confirms.py` and `tests/test_txy_last_used_quit.py`. Running each alone, then
a slow file in the same process, didn't reproduce it, so the exact test isn't pinned. Harmless: a log line, never
a failure.

**known-issues proposal:** "A main-window test whose close waits for saves (`QuitSaveDialog`) leaves its
`GUIWatchdog` running past the test; the worker, idle at the end of a run, then logs 'GUI stalled for ~63s'
(likely `test_quit_confirms.py` or `test_txy_last_used_quit.py`). Fix: the tests finish or cancel the dialog,
or the watchdog stops when the window is destroyed."

## Step 4: Live's segments and compaction (`8be1be6`)

Each Live autosave already writes one segment of what its layers lack (3a). Since `8be1be6`, after any unit is saved,
each layer it wrote that is due is compacted in the same job (`Access.compact` → `CacheStore.compact_txy`). A layer
is due at more than 8 segments, or with more than half its bytes superseded. The rewrite runs only if it fits beside
the old segments, else waits for a later save, never asking (Q45.7). It runs under the converter's ticker. Test:
nine autosaves give segments 2..8, the ninth compacts to one, and the next appends.

## Step 5: the UI (after merging `dev/v0.0.8` at `6679245`)

| Commit | What |
|---|---|
| `102c027` | Settings › Cache (store-v4 only): a TXY data row (shots, folders, size, tags, only copies; Clear… → `clear_txy`); Clear all sends and names `txy`; the global cache policy (a combo in S~6's proposed words, the `cache_policy` settings row, `FolderCache.cache_policy`, sent as `policy` with store-v4 requests only); policy `txy` keeps no raw pulses (`raw_fill` reason `policy`, conversions' raw rows skipped, `CacheStore.policy_of`); lowering the budget asks from `trim`'s plan (`plan_only`) and sends exactly its items (S2-1's step 5). Make room's `room_text` names TXY layers by group, and `room_items` is `cache_store.room_items` |
| `d849372` | The folder's own choices: right-click "TXY for this folder…" and "Cache policy for this folder…" (QInputDialog lists; "As Settings (every folder)"; disabled without a data root); `FolderCache.set_folder_choice` (kept now, then saved); Folder details' TXY line names them |

- **S~6** labels are as proposed, still waiting on Tony's answer (CoCo relays). In `CacheTab.POLICY_LABELS` and
  `FolderExplorer.FOLDER_CHOICE_GLOBAL`.
- The two menu dialogs are `QInputDialog.getItem`. Like the explorer's existing Custom depth… (`getInt`), they
  aren't named widgets; the menu actions are.

## Step 6: the integration check (`a39a94d`)

`test_caching_v2_session.py::test_a_stage_2_session_with_layers_leaves_store_v3_as_it_was`, with the switch on,
beside an older HeLab's store-v3:
1. a conversion saves raw layers;
2. the tab's load from the raw layer (no HeLab text read), then a plot's choice cached quietly, then the next load
   from the layers;
3. ten Live autosaves compacting;
4. Clear all;
5. Make room's order, through a real `cache_full`;
6. store-v3 hashed unchanged and opened only by `LegacyStore`;
7. a cache move, both stores verified, and `helab cache export --kind txy` on the moved store.

**Checkpoint 2** (stage 2 complete, switch still off): local full suite at `a39a94d` gives 8925 passed, 672 skipped,
no RERUN. mypy --strict (helab, tests, win32) and pyright (also Windows) are clean.

## Step 7: doc proposals for stage 2 (for the Coordinator)

- **AGENTS.md** (wording only):
  - The code map row for `helab/io_ops/` adds `txy_cache` ("a load's disk cache: store-v3's dataset, or store-v4's
    views and TXY layers").
  - The row for `helab/convert/` adds `txy_layer` ("TXY segments, `.hlb` kind `txy`").
  - The disk-cache bullets: no rule change. Compaction retires superseded segments, which the existing "the sweep
    deletes retired dataset and layer files…" line covers. Clear data cache and purges are the user's choices,
    as before.
  - The settings bullet's "The `store_v4` row stays off until caching v2's stage 2 and Tony's go" becomes "…until
    Tony has used stage 2 (Q45.11)".
- **cache-store.md**, a "TXY layers (stage 2)" part of the store-v4 section:
  - **The tables:** `txy_layers` (per-shot entries `[shot, size, mtime_ns, kind, seq, rows, problematic, job_seq]`,
    kinds per Q45.3, `gone_at` and `seen_at` per C2-10, S2-2/S2-3), `txy_segments` (append only), `txy_views`
    (source identity × profile asked for), `cache_policy`, `txy_source_prefs`, and `pending_saves.parts`.
  - **Save units** (`save_txy`): one fit check; the policy; `hold`; `seen_at`.
  - **One waiting unit per folder**, with parts merged (Q45.8).
  - **Compaction only when it fits** (Q45.7).
  - **The TXY guard:** `gen_txy`, `gen_datasets`, the `txy:` epoch, the folder's and the root's.
  - **Make room's and `trim`'s order:** five groups (Q45.6); `trim` keeps only copies unless given `trim_plan`'s
    items (S2-1).
  - **Clear:** `remove_txy`; `clear_folder_data` and `purge_datasets` take layers but keep only copies (S3-1,
    the purge for Tony to confirm).
  - **Seeds:** store-v4's `datasets` and store-v3's under Keep seed layers on use (Q45.4, Q45.5).
  - **A42.1:** `save_result(only_new=True)`.
  - **S2-0:** `rekey_subtree` moves raw and TXY layers.
  - **The sweep and moves:** they cover `txy/`.
- **io-and-browsing.md**, loads:
  - `txy_cache.Access` (the same calls for both layouts); the loading order (layer, then raw layer, then seeds,
    then the share; the raw step converts before any `file_started`, under the ticker, S3-2);
  - A40.3's confirm;
  - cached reads carry `txy`;
  - a plot's own choice is cached quietly (Q19.3);
  - the `folder_choices` event.
- **live.md:**
  - Live's saves append a segment and compact (Q45.7).
  - Live follows a folder's own source through FolderCache (`with_txy`), once a load or the admin told it.
- **converter.md:**
  - `txy_layer`;
  - a load converts a HeLab shot from the raw layer for built-in profiles, equal to its text;
  - policy `txy` keeps no raw rows from conversions.
- **app-runtime-and-ui.md:**
  - Settings › Cache's TXY data row and cache policy, and the lower-budget question from the plan;
  - Make room naming layers;
  - the folder menu's two items;
  - Folder details' TXY line.
- **settings.md:** the `cache_policy` row.
- **testing.md:** `tests/test_txy_layers_store.py`, `test_txy_loading.py`, `test_txy_fixes.py`, `test_txy_ui.py`, and
  the stage 2 session in `test_caching_v2_session.py`.
- **docs/hlb-format.md:** a "TXY layers" section, with `kind` `txy`, arrays `shots`, `offsets`, `hits` and
  `problematic`, the meta, `g8`/`f64`, and no shuffle; and `helab cache export --folder F --kind txy [--layer]`.
- **The plan** (`roadmaps/caching-v2.md`): stage 2's items ticked; "the switch stays off until Tony has used it
  (Q45.11)".
- **known-issues:**
  - the GUI-watchdog proposal above;
  - the RERUN sightings in the CI notes above (`test_gui_responsiveness` `[1]`, `test_test_isolation` twice,
    `test_root_gui`).

### New items (provisional)

- **Q~14 The purge by age in store-v4** takes TXY layers, views and seen raw layers not used since the cutoff,
  keeping only copies (S3-1: Assay's call per Q22.6 and C2-9). Proposed: as built. The alternative is that the
  purge row says "datasets only" and layers age out only through Make room.
- **Q~15 A Live started on a folder before any load of it this session** follows the global TXY source until a
  load or the admin tells FolderCache the folder's own (Live checks don't open the store). Proposed: accept for
  now, with A~8 as the fix.
- **A~7** Conversion from the raw layer (3e) for user profiles: the helper would need the app's profile library.
  Today only built-ins convert; others read their text.
- **A~8** FolderCache learns a folder's choices with its listing (`folder_choices` beside `folder_prefs` in
  `io_ops/metadata.py`), so Live and the first load follow it at once.
- **A~9** The GUI-watchdog test leak: finish or cancel the `QuitSaveDialog` in the quit tests, or stop the watchdog
  when the window is destroyed.
- **M~4** On screen, with the switch on in test settings and temp folders only:
  - Settings › Cache's TXY data row and cache policy, and the lower-budget question;
  - Make room naming layers;
  - the two folder menu items and Folder details' line.
- **M~5** On the lab share, a large shot's load from the raw layer against reading its HeLab text (S3-2's cost
  note: the raw step is slower than local text, faster than a slow share).
