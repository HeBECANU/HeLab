# Review: Caching v2 stage 2, checkpoint 1 (store side, inert, switch off): `b691d26`, `a70d261`

Reviewer: Assay (Claude Opus 5.5), 2026-11-02. Read-only on code. Read:
- `brief-stage2.md` and `design-stage2.md`, with CoCo's answers to S~1–S~6;
- the handoff's "Step 2" and its departures;
- AGENTS.md (current: `helab cache` is now named as a read-only store opener).

**Verdict: no blocker while the switch is off. 2 findings: 0 High, 1 Medium, 1 Low.** Both are reachable only
with the `store_v4` switch on.
- **S2-1 (Medium):** `trim` (A42.2) removes only copies that its question never names. Fix it before anything
  can lower a v4 budget.
- **S2-2 (Low):** the answer to CoCo's question about layers' `gone_at`: yes, it reopens the C2-10 class for
  layers.

## Findings

### S2-1 · Medium · Lowering the budget (`trim`) now removes TXY and raw layers, only copies included, but its question counts datasets only

- `helab/utils/cache_store.py:3961-3972` (`trim` → `_free_space`, all five groups: `take_layers("only")` and
  `take_raw(True)` included).
- The question is `helab/views/CacheTab.py:853-864` (`_ask_trim`): "Removes cached data for up to N folders
  (…)", from `trim_estimate` (`cache_store.py`), which counts **datasets only**.
- **Scenario.** The switch is on, and a folder's MATLAB layer is the only copy (its `d_txy_forc` files are gone
  from the share, `gone_at` set).
  1. The user lowers the disk budget below current usage.
  2. The question says "Removes cached data for up to 0 folders (0 B)" (`trim_estimate` →
     `{datasets: 0, bytes: 0}`).
  3. The user agrees. `trim` goes through `_free_space` past datasets into layers, raw layers, and finally only
     copies, and removes the MATLAB layer, data that can't be read again.
- Before A42.2, `trim` removed datasets only, which is what the question says. Q22.6, and Tony's confirmation of
  C2-9, require that an only copy is never removed without being named. Make room names them (`txy-only:`,
  `raw-only:` items, exact plan); `trim` doesn't.
- **Fix.**
  - **Store side, now:** `trim` stops before group 5, so only copies stay (e.g. `_free_space(…,
    only_copies=False)` for `trim`), unless the caller passes a plan that names them, as `expected_room` does
    for Make room.
  - **Step 5:** the question is built from a helper's plan (as `room_plan`), not from `trim_estimate`, and names
    TXY and raw layers.
  - Add a test like the scratch one.
- **How verified.** Scratch test (`.ai/temp/assay/test_zz_s2a.py`, on an export of `a70d261`): a MATLAB layer
  marked gone; `trim_estimate(inventory, 1)` gives `{datasets: 0, bytes: 0}`; the admin's `trim` to budget 1
  removes the layer (`txy_layers(X) == {}`) and sends `removed` `["txy"]` for it.

### S2-2 · Low · A layer's only-copy mark follows whichever listing lands last: C2-10 reopened for TXY layers

- `helab/utils/cache_store.py:3506-3524` (`mark_txy_seen` sets `gone_at = seen_at` or `NULL` unconditionally);
  `:3615-3635` (`_txy_groups`: `gone_at IS NULL` puts a layer in group 2 or 3, "seen", ahead of only copies).
- **Scenario.** This is CoCo's question, answered yes.
  1. A listing at t=200 finds a folder's `d_txy_forc1.txt` gone, so its MATLAB layer gets `gone_at = 200`.
  2. A slower listing that started at t=100 lands afterwards, for example a background scan beside a tab load,
     or Live, once step 3's loads call it. It clears `gone_at`.
  3. Make room or `trim` then removes the layer in group 3, "sources seen", and names it `txy-seen:`, not
     `txy-only:`. The user loses the only copy without being told it is one.

  The same happens the other way: a late older listing that missed a file marks a layer gone after a newer one
  saw it (the safe direction). The handoff flags this departure and asks.
- **Fix.** C2-10's rule:
  - keep a last sighting per layer (a `seen_at` column);
  - clear `gone_at` only when the listing is newer than it (`gone_at < seen_at`);
  - set it only when the listing is newer than the last sighting.

  `save_txy` already keeps `gone_at` on an existing row (`keep_gone`), so only `mark_txy_seen` changes.
  Stage 2's tables haven't shipped, so the column can join `STAGE2_SCHEMA` now. A store some developer already
  migrated needs it as its own `migrate` addition (AGENTS.md's `_migrate` rule).
- **How verified.** Scratch test (same file): `mark_txy_seen(X, {"txy": {}}, 200.0)` → `gone_at == 200.0`;
  then `mark_txy_seen(X, {"txy": {1: …}}, 100.0)` → `gone_at is None`.

## Notes for later steps (not findings)

- **Step 3: the TXY guard.** Design §5 says `start_txy_job`'s guard also holds `gen_datasets` and the folder's
  epoch, because a load that seeds layers from v4 `datasets` rows mustn't copy data a Clear of datasets just
  removed. `start_txy_job` (`cache_store.py:3090`) takes only `gen_txy`, the `txy:` epoch and the root's. That's
  harmless until step 3 seeds layers from `datasets` rows: add them then, or fence the seed another way.
- **Step 5: Clear all.** Settings › Cache's Clear all sends `KINDS` plus `raw` (`CacheTab.py:559`), not `txy`.
  The admin's no-kinds Clear does take `txy`. With the TXY row, Clear all should send `txy` too, as with raw at
  stage 1.
- **The handoff's departures** look safe as they stand:
  - `save_dataset` is still allowed in v4 until step 3;
  - a merged waiting unit keeps the later view (another mode's view is rebuilt at its next load);
  - GUI Make room items for `txy_*` come in step 5: until then a plan naming layers doesn't match what the GUI
    agreed to, so nothing is removed.
- **Adopting a waiting unit doesn't re-read the folder's policy:** a HeLab part made under `raw+used` is adopted
  even if the folder is now `raw`. The user agreed to that save, so this is fine.

## Checked, no finding

- **The switch off changes nothing:**
  - every stage 2 path checks `layout >= 4` (`_txy_live`, `_txy_summary`, `_known_files` and `_listed_files`'
    `txy/`, `_rekey_sets`, admin `clear`'s `txy`, `remove_txy`), and `_retire_pending` reads no `parts` in v3;
  - `_free_space` under v3 is today's datasets loop (least recently used, until it fits), for Make room and
    `trim` alike;
  - the full suite passes with the switch off.
- **Format additive:**
  - stage 2's tables and `pending_saves.parts` (with a default) arrive through `store_v4.migrate`, in one
    `BEGIN IMMEDIATE`, re-checked under the lock (`no_layers`);
  - `.hlb` `kind` `txy` stays format 1;
  - `txy_layer.unpack_segment` checks the arrays agree (offsets monotone and covering the hits, shots strictly
    increasing, flags one per shot) on top of `hlb`'s CRCs.
- **Guards and `job_seq`:**
  - `save_txy` checks the TXY guard (`gen_txy`, `txy:` epoch, root epoch) and `_check_cacheable`, then applies
    the unit under a savepoint;
  - per-shot entries are replaced only by a job whose `job_seq` is at least the entry's (later ones are named in
    `refused`); views likewise;
  - over budget or at the 80 % rule, the unit is rolled back (its retirements too) and waits;
  - a rejected unit's files are retired unless a row or a waiting part names them;
  - compaction re-checks the guard and that the entries are unchanged, and keeps the new segment only if usage
    still fits, otherwise rolls back and retires it, never asking.
- **Pending parts (Q45.8):**
  - one row per folder; a later job's part replaces a layer's earlier one (the earlier one's file retired), and
    an earlier job's part arriving later is dropped;
  - adoption checks each part's guard, drops and retires a fenced part, applies the rest under their own
    `job_seq`, and rejects the unit only when none is left;
  - every pending removal (Discard, expiry, Clears, a dataset save replacing it) goes through `_retire_pending`,
    which retires the parts' files;
  - the sweep keeps files a waiting part names (`json_each(pending_saves.parts)`);
  - the app's waiting-saves list reads only generic columns.
- **Make room:**
  - `_free_space`'s five groups run in order, least recently used first, a whole row at a time, never the folder
    being saved;
  - only copies come last and are named (`txy-only:`, `raw-only:`), and adoption with `expected_room` takes
    exactly the named plan or nothing. (`trim`: S2-1.)
- **Clear:**
  - Clear all (admin, no kinds) takes `txy` (`gen_txy` bumped, all views and waiting layer parts);
  - `clear_root` takes its layers, views and waiting parts;
  - Don't cache with "remove cached data" takes layers that aren't only copies (as C2-9), with their views;
  - per-folder `remove_txy` fences each folder by its `txy:` epoch, rows or none.
- **S2-0:** `rekey_subtree` moves `raw_layers` per shot (newer wins), a folder's TXY set as one (newer wins), and
  the two choice tables. Waiting parts' guards then fail as `REKEYED`, so they are retired.
- **Helpers and the GUI:**
  - only helpers, and `helab cache` read only, open the store;
  - `record_cache_folder` (A44.2) writes to the app folder, not the store: atomic, by the GUI only (startup,
    after a move), never read by the GUI, logged on failure, not housekeeping;
  - `test_cache_folder_record` checks `helab convert` writes none.
- **The export (A44.1):** read only; never into a `store-v*` folder; `--layer` or the only layer; a segment file
  as one table with a `shot` column.
- **Mutation claims** (each on a copy of `a70d261`, then restored):
  - `_rekey_sets` returning early fails `…rekey_moves_raw_and_txy_layers`;
  - `migrate` without stage 2's addition fails `…stage_1_gets_stage_2s_tables`;
  - `_policy` ignoring the folder's row fails `…policy_raw_writes_no_helab_layer…`;
  - as committed, all 19 pass.

## Checks (run by the reviewer)

On an export of `a70d261`, whose `helab/` and `tests/` equal the floor's `HEAD` `e16bb4d` (the floor was clean):
- `pytest -n 4 --reruns 5 --reruns-delay 1 --basetemp=.ai/temp/pytest-assay` (the full suite, including
  `test_txy_layers_store.py`, `test_cache_cli.py`, `test_cache_folder_record.py`, `test_store_v4.py` and
  `test_caching_v2_session.py`): **8880 passed, 673 skipped, 2 warnings, 3 failed, 15 rerun in 189.33 s.**
  - All 3 failures and all 15 RERUNs are the three git-provenance tests (the export has no `.git`; 5 reruns each).
  - In the floor checkout (same code): **3 passed, no RERUN**.
  - No other RERUN.
  - The 2 warnings are the known pyqtgraph ones.
  - The totals match Vault's 8884 passed and 672 skipped, once the export's 3 and 1 are added back.
- `mypy helab/ --strict` (202 files), `mypy tests --strict` (188), `--platform win32`: no issues.
- `pyright helab tests` and `--pythonplatform Windows`: 0 errors.
- Scratch checks, not committed: S2-1 and S2-2 (`.ai/temp/assay/test_zz_s2a.py`), and the three mutations above.

On fix diffs I re-check only the fixes, their tests and the touched files' type checks.

## Re-check of the fixes (`7d5c567..6b0f998`; `7d185eb` not included)

**Open findings: 1 Nit (S2-3, new, C2-11's class for a new layer). S2-1 and S2-2 are fixed.**

| Finding | Commit | Without the fix | With it |
|---|---|---|---|
| S2-1, S2-2, migration | `6b0f998` (`cache_store.py`, `store_v4.py`, `admin.py`, `events.py`) | 3 failed | 3 passed |

(On an export of `6b0f998`, with those four files as they were at `7d5c567`, I ran
`test_trim_keeps_only_copies_unless_its_plan_names_them`, `test_an_older_listing_landing_late_undoes_no_mark` and
the extended `test_a_store_v4_from_stage_1_gets_stage_2s_tables`, then restored the files and compared them with
git.)

- **S2-1: fixed.**
  - `trim` without a plan runs `_free_space(…, only_copies=False)`, which stops before group 5.
  - `trim(…, expected)` runs the whole order under a savepoint and keeps it only if the items equal the plan the
    user was shown, so only copies go only when named.
  - `trim_plan` tries the whole order and rolls back (exact; `possible` when it would fit).
  - The admin's `trim` takes `plan_only` (answers `room` and `items`) or `plan` (removes exactly those).
  - `trim_estimate`'s docstring says it is store-v3's only.
  - **Step 5 note:** `CacheTab` still sends `trim` without a plan and asks from `trim_estimate`. In store-v4
    that can remove re-readable TXY and raw layers the question doesn't count (never only copies now). Build
    the question from `plan_only` and send its `items` as `plan`.
- **S2-2: fixed.**
  - `txy_layers.seen_at` (default 0) is in `STAGE2_SCHEMA`, and comes through `migrate`'s own addition for a
    store migrated before it (`no_seen_at`, checked after the stage 2 addition under the same lock).
  - `mark_txy_seen` follows C2-10's rule: a sighting clears `gone_at` only if newer than it (`>=` keeps it), and a
    gone mark needs a listing newer than the last sighting (`seen_at <`; `COALESCE` keeps the first).
  - `_write_layer_row` keeps an existing layer's marks.

### S2-3 · Nit · A new layer's `seen_at` is its save time, so a listing between the read and the save that found the files gone is ignored

- `helab/utils/cache_store.py` `_write_layer_row` (`seen = … if stored is not None else now`). This is C2-11's
  class (raw rows took the save time until `RawEntry.read_at`), here for a layer made by a save.
- **Scenario.**
  1. A load reads `d_txy_forc1.txt` at t=100.
  2. The file is deleted, and a listing at t=150 finds it gone.
  3. The load saves at t=200, making the MATLAB layer with `seen_at = 200` and `gone_at` NULL.
  4. The t=150 listing's `mark_txy_seen` lands, but `seen_at < 150` is false, so the layer isn't marked gone.

  Until a listing after t=200, Make room counts the only copy as group 3, "seen". If that listing landed before
  the save, the row didn't exist yet, and the gone evidence is lost the same way. Narrow, and healed by the
  next listing.
- **Fix.** `save_txy` takes the time the unit's data was read, or its listing's time (the load has it in step 3;
  default the save time), as a new layer's `seen_at`. It can land with step 3's loads.
- **How verified.** Scratch test (`.ai/temp/assay/test_zz_s2b.py`, on the export of `6b0f998`): a new layer
  saved 100 s after its read, then `mark_txy_seen(X, {"txy": {}}, read + 50)`, gives `seen_at - read = 100 s`
  and `gone_at` None.

### Checks (re-check)

On an export of `6b0f998`:
- `pytest -n 4 --reruns 5 --reruns-delay 1 --basetemp=.ai/temp/pytest-assay` (the full suite,
  `test_txy_layers_store.py` and the admin tests included): **8882 passed, 673 skipped, 2 warnings, 3 failed, 15
  rerun in 150.07 s.**
  - All 3 failures and all 15 RERUNs are the three git-provenance tests (the export has no `.git`; 5 reruns
    each). They passed in the floor checkout with no RERUN at this review, and neither they nor `build_info.py`
    changed since.
  - No other RERUN.
  - The 2 warnings are the known pyqtgraph ones.
- `mypy helab/ --strict` (202 files), `mypy tests --strict` (188), `--platform win32`: no issues.
- `pyright helab tests` and `--pythonplatform Windows`: 0 errors.
