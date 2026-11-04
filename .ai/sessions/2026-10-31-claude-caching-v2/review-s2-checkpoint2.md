# Review: Caching v2 stage 2, checkpoint 2 (stage 2 complete, switch off)

Reviewer: Assay (Claude Opus 5.5), 2026-11-02. Read-only on code. The code commits after `df17761`:

| Commit | What |
|---|---|
| `8be1be6` | step 4, Live's compaction |
| `102c027`, `d849372` | step 5, the UI |
| `a39a94d` | step 6, the integration session |

The `dev/v0.0.8` merge `6679245` and docs-only commits are skipped. I read the handoff's steps 4–6 and AGENTS.md's
cache and UI rules.

**Verdict: no blocker while the switch is off. 3 findings: 0 High, 0 Medium, 2 Low, 1 Nit.** All are question texts
in Settings › Cache, reachable only with the `store_v4` switch on.
- **C2S2-1 (Low):** Clear all's question doesn't name the only copies it removes.
- **C2S2-2 (Low):** the purge question still counts datasets only. My step 3 note, which CoCo's message counts as
  done, isn't built yet.

## Findings

### C2S2-1 · Low · Clear all removes TXY and raw only copies without naming them

- `helab/views/CacheTab.py:597-612` (`clear`, the Clear all branch).
- **Scenario.** The switch is on. Some folders' TXY layers or raw pulses are only copies: their files are gone
  from the share (`inventory["txy"]["only_copy"]`, `inventory["raw"]["only_copy"]` > 0).
  - Clear all's question says "Removes everything in the disk cache: cached data …, TXY data for N folders (…),
    raw pulses for M folders (…), …" and sends `kinds` with `raw` and `txy`.
  - `remove_txy(None)` and `remove_raw(None)` take the only copies too. The question never says that some of it
    can't be read again.
  - The rows' own Clear… questions do say it (`clear_raw` at `:627-636`, `clear_txy` at `:640-652`), and so do
    Make room and the plan-based trim.

  CoCo's check is "only copies named in every question" (Q22.6, Tony's confirmation of C2-9). Clear all is the one
  question that doesn't. (I missed the raw half of this at stage 1 step 6, checkpoint 3.)
- **Fix.** Add the rows' sentence when either count is above zero, e.g. "N shots' raw pulses and M folders' TXY
  data are the only copy: their files are gone from their folders, so they can't be read again."
- **How verified.** By reading the branch: its text uses only the `folders` and `bytes` of `raw` and `txy`.

### C2S2-2 · Low · The purge question still counts datasets only, while the store-v4 purge takes layers

- `helab/views/CacheTab.py:700-710` (`purge_datasets`: `purge_estimate(…, datasets=True)`, "Removes cached data
  for N folders (…)"); `:748` (the row's estimate, the same).
- **Scenario.** Since `df17761` (S3-1), store-v4's `purge_datasets` also takes TXY layers and seen raw layers not
  used since the cutoff (only copies stay). Loads in store-v4 write layers, not datasets. So the question says
  "Removes cached data for 0 folders (0 B) not used in the last 90 days", then the purge removes those folders'
  layers. No only copy is at risk, but the user is told nothing goes.
- CoCo's message says this note ("the purge question built from a plan") is done. No commit in
  `df17761..a39a94d` touches the purge question (`git log -S purge_estimate` shows none).
- **Fix.** As for `trim`: in store-v4 ask from the helper's plan, or count the layers from the inventory's ages,
  so the question says what goes.
- **How verified.** By reading, and the `git log -S` search above.

### C2S2-3 · Nit · The TXY Clear question calls layers folders, and its singular reads "1 folder' TXY data"

- `helab/views/CacheTab.py:640-652` (`clear_txy`) and the row's "N only copies";
  `cache_store.py:3686` (`_txy_summary` counts `only_copy` per **layer**).
- **Scenario.** `plural(only, 'folder') + "' TXY data is the only copy"` gives "2 folders' TXY data" for 2 *layers*
  (one folder's MATLAB and HeLab layers count twice), and "1 folder' TXY data" for one.
- **Fix.** Count only-copy folders in `_txy_summary` (or say "layers"), and phrase it like the raw row's ("N
  folders' TXY data are the only copy" / "1 folder's …").
- **How verified.** By reading.

## Checked, no finding

- **Compaction never removes data before the new segment is saved.** `Access.compact` → `compact_txy`
  (reviewed at checkpoint 1):
  - the rewrite's segment row goes in first;
  - the old segments are retired only once the fit check passes, in the same transaction;
  - their files go later, through the sweep's grace period;
  - otherwise it rolls back and retires only the new file, and never asks.

  It runs under `_Ticker(compute_budget(4 × layer bytes))` and is best effort.
  `test_lives_autosaves_append_a_segment_each_and_compact_when_they_pile_up` fails with `txy_cache.py` as it was
  before `8be1be6`, and passes with it.
- **Make room and trim name only copies:**
  - `room_text` names TXY only copies by folder (`txy_only`), as for raw, in the five-group order, and
    `room_items` (= `cache_store.room_items`) sends exactly what was named;
  - lowering the budget in store-v4 asks from `trim`'s `plan_only` (`room_text(room, "Lowering the budget")`)
    and sends exactly its `items` as `plan` (S2-1's step 5).
- **Nothing removed without asking:**
  - Clear TXY data asks and names only copies (C2S2-3 is wording only);
  - the policy combo and the folder's policy say "Changing it removes nothing", and nothing is removed (only
    `cache_policy` rows and the setting change);
  - policy `txy` stops `raw_fill` (`reason="policy"`) and a conversion's raw rows (`policy_of`); nothing existing
    goes.
- **UI rules:**
  - the new Settings controls have IDs and names (`cache_clear_txy`, `cache_policy`);
  - the folder menu items are named QActions, disabled without a data root (`NEEDS_ROOT_TOOLTIP`);
  - the two `QInputDialog.getItem` lists are unnamed, like the explorer's existing Custom depth…, as the handoff
    says;
  - the TXY row is one line, its detail in a tooltip;
  - Folder details adds the folder's choices to its one TXY line, explained in the tooltip;
  - the menu's lambdas capture the slot and path, not a Qt-made sender;
  - `test_accessible_names` passes.
- **Switch off changes nothing:**
  - the TXY row and policy are shown only when the inventory has `txy` (store-v4);
  - `store_options()` adds `policy` only for `store-v4`;
  - the folder menu items appear only when the store is `store-v4`;
  - Clear all adds `raw` and `txy` only when present;
  - `trim` without `txy` in the inventory asks as before.
- **Step 6's session** covers conversion → load from the raw layer → plot choice → Live compaction → Clear all →
  Make room through a real `cache_full` → store-v3 hashed unchanged and opened only by `LegacyStore` → a cache move
  → export, with the switch on in temp stores.

## Checks (run by the reviewer)

On an export of `a39a94d`, whose `helab/` and `tests/` equal the floor's `HEAD` `2fc942a`:
- `pytest -n 4 --reruns 5 --reruns-delay 1 --basetemp=.ai/temp/pytest-assay` (the full suite, `test_txy_ui.py`,
  `test_txy_loading.py` and `test_caching_v2_session.py` included): **8921 passed, 673 skipped, 2 warnings,
  3 failed, 15 rerun in 174.33 s.**
  - All 3 failures and all 15 RERUNs are the three git-provenance tests (the export has no `.git`; 5 reruns each).
  - In the floor checkout: **3 passed, no RERUN**.
  - No other RERUN.
  - The 2 warnings are the known pyqtgraph ones.
  - The totals match Vault's 8925 passed and 672 skipped, once the export's 3 and 1 are added back.
- `mypy helab/ --strict` (203 files), `mypy tests --strict` (191), `--platform win32`: no issues.
- `pyright helab tests` and `--pythonplatform Windows`: 0 errors.
- `8be1be6`'s fails-without-its-change claim, as above.

On fix diffs I re-check only the fixes, their tests and the touched files' type checks.

## Re-check of the fixes (`c627027..28d5844`)

**Open findings: none.** C2S2-1, C2S2-2 and C2S2-3 are fixed.

| Test | At `c627027`'s code | With `28d5844` |
|---|---|---|
| `test_the_clear_questions_name_only_copies_by_folder` | failed | passed |
| `test_the_purge_question_counts_txy_and_raw_folders_in_store_v4` | failed | passed |
| `test_a_purge_by_age_takes_old_layers_but_not_only_copies` (extended) | failed | passed |
| `test_the_tab_shows_txy_data_and_the_policy_only_with_store_v4` (edited only) | passed | passed |

(On an export of `28d5844`, with `cache_store.py` and `CacheTab.py` as they were at `c627027`, then restored and
compared with git.)

- **C2S2-1: fixed.** `_only_copies` gives Clear all, and the TXY row's Clear, one sentence naming the only copies:
  "TXY data of N folders" from `txy.only_copy_folders`, and "raw pulses of M shots" from `raw.only_copy`.
  `_txy_summary` now counts only-copy folders separately from layers.
- **C2S2-2: fixed.**
  - In store-v4 the inventory's `ages` gains `txy` and `raw`: rows `gone_at IS NULL` with `last_used`, `bytes`
    and `path`.
  - `purge_estimate(…, datasets=True)` adds `txy_folders`, `txy_bytes`, `raw_folders` and `raw_bytes` with the
    purge's own condition (`last_used < cutoff`, only copies left out), and `bytes` covers all of it.
  - The question names datasets, TXY data and raw pulses with their folders, and adds "Only copies stay (Make
    room names them)". The row's estimate and the button follow it.
  - **The estimate equals what the store-v4 purge removes.** Scratch test (`.ai/temp/assay/test_zz_s2c.py`, on
    the export):
    - the setup: an old folder with two layers, a recent one, an old only-copy layer, old and recent raw rows,
      and an old raw only copy;
    - `purge_estimate` gave 17,143 bytes (1 TXY folder, 15,665 B; 1 raw folder, 1,478 B);
    - the admin's purge freed exactly 17,143 bytes of usage, and its `removed` events carried 15,665 B (`txy`) and
      1,478 B (`raw`);
    - recent data and both only copies stayed.

    The match holds because `txy_layers.bytes` is kept equal to the layer's segment bytes, which is what
    `_remove_txy_rows` sums. Views (records) aren't counted, as datasets' records never were.
- **C2S2-3: fixed.** The TXY Clear question uses the same sentence, counting folders.

### Checks (re-check)

On an export of `28d5844`:
- `pytest -n 4 --reruns 5 --reruns-delay 1 --basetemp=.ai/temp/pytest-assay` (the full suite, `test_txy_ui.py` and
  `test_txy_fixes.py` included): **8923 passed, 673 skipped, 2 warnings, 3 failed, 15 rerun in 154.85 s.**
  - All 3 failures and all 15 RERUNs are the three git-provenance tests (the export has no `.git`; 5 reruns each).
    They passed in the floor checkout with no RERUN at this review, and neither they nor `build_info.py` changed
    since.
  - No other RERUN.
  - The 2 warnings are the known pyqtgraph ones.
  - The totals match Vault's 8927 passed and 672 skipped, once the export's 3 and 1 are added back.
- `mypy helab/ --strict` (203 files), `mypy tests --strict` (191), `--platform win32`: no issues.
- `pyright helab tests` and `--pythonplatform Windows`: 0 errors.

Stage 2 has no open review findings.
