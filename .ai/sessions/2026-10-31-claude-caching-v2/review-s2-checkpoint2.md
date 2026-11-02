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
