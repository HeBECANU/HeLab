# Review: Caching v2 A47 items (switch off): `5cbf1d4` A47.4, `28d2112` A47.2, `9e8c576` A47.6

Reviewer: Assay (Claude Opus 5.5), 2026-11-03. Read-only on code. Read: `design-purge.md` (with P~1 and P~2 built as
proposed), the handoff's A47 sections, the three commits.

**Verdict: no blocker. 1 finding: 0 High, 0 Medium, 1 Low.** The finding is in FolderCache's memory of a folder's
stage 2 choices: cache-1's class, which I missed at step 3 and which A47.2's listings now rely on. The switch is off,
so nothing is reachable today.

## Finding

### A47-1 · Low · A data root's change of identity keeps the old root's folder choices (TXY source, policy) in RAM

- `helab/utils/folder_cache.py:1652-1670` (`_root_prefs_gone`: drops `prefs`, `_confirmed_prefs` and
  `convert_prefs`, not `folder_choices`).
- `:1018-1031` (`remember_choices`: a part absent from the event keeps what RAM has).
- `helab/io_ops/metadata.py` (A47.2: a listing sends a folder's `choices` only when set).
- **Scenario.** The switch is on. A folder under data root A has its own TXY source (say MATLAB's only) and policy.
  1. Its root changes identity: a replaced marker, It's a copy…, a removed marker, or another root found at it.
     cache-1's `_root_prefs_gone` drops the folder's flags in RAM, but `folder_choices` keeps root A's.
  2. The store under the new key has no choices for the folder, so the next listing sends none.
     `remember_choices` is never called, and RAM keeps root A's for the session.
  3. `with_txy` applies them, so the tab's loads, Live and cached reads keep following root A's TXY source.

  This is cache-1's class, which `34ec22c` fixed for flags and `write_beside`. The choices arrived later, in step
  3c (`2f6c1f3`), and I missed it there. A47.2 makes listings the way FolderCache learns choices, but a listing can
  only add; it never resets.
- **Fix.** `_root_prefs_gone` also drops `folder_choices` for the folders the old root held (not those of a nested
  root), keeping a folder whose `set_folder_choice` write is still running, and tells `folderPrefsChanged`. Add a
  case to `test_root_change_flags.py`.
- **How verified.** Scratch test (`.ai/temp/assay/test_zz_a47.py`, using `test_root_change_flags.py`'s harness, on
  an export of `9e8c576`):
  - `remember_choices(RUN, {source: matlab-only, policy: txy, …})`;
  - then a `root_changed` event with a new UUID;
  - `folder_choices[RUN]` still holds them, and `with_txy(RUN, {})` still gives `matlab-only`.

## Checked, no finding

- **A47.4: each purge kind takes only its kind.**
  - `purge_cached(cutoff, kinds)` takes datasets, and in store-v4 TXY layers (with their segments and their folders'
    views) and raw layers, only those asked, in one transaction.
  - Layers count as old only with `gone_at IS NULL`, so **only copies always stay**.
  - The epochs and generations move as for any removal, so a running save can't bring the data back.
  - store-v3: datasets only (`_with_layers_removed` returns early, even for `all`).
  - Unknown kinds are refused.
- **The admin's `purge`:**
  - `what` is datasets | txy | raw | records | results | all;
  - `all` takes results (`remove_results(cutoff)`), every cached kind and folder records, **scan failures only with
    `include_failures`** (the box, sent by `purge_all`);
  - empty removals send no event;
  - the result's bytes count layers too.
- **"Everything" names every part and its size** (`everything_text`): cached data, TXY data, HeLab's cached raw
  pulses ("your d files aren't touched"), folder records ("scan failures are kept" without the box) and cached
  analysis as the user's plots' results, with the total, "Only copies stay" and what stays open. Each part's figure
  comes from the same estimate as its own purge row.
- **The estimate equals what is removed:**
  - `purge_estimate` uses each purge's own condition (`last_used < cutoff`, `gone_at IS NULL` for layers);
  - `results_purge_estimate` uses `remove_results`' `last_used < cutoff`;
  - the commit's test checks admin bytes == estimate bytes for `txy`, `raw` and `all`;
  - my checkpoint 2 re-check showed the per-kind bytes match exactly.
- **Tony's wording:** every question that clears raw pulses (Clear, Clear all, the purges, Make room, lowering the
  budget) says "HeLab's cached raw pulses" and that the d files aren't touched.
- **UI:**
  - one-line purge rows with IDs `purge_txy`, `purge_raw`, `purge_all` (and their `_days`);
  - the TXY and raw rows are hidden in store-v3.
- **A47.2 ordering:**
  - `remember_choices` merges each part (the policy; the source with its tag) by its own `*_set_at` (`>=`), so an
    older listing's policy never beats a newer one, nor a source;
  - it emits only on a change;
  - listings read `read_folder_choices` beside prefs (none in store-v3), and report a read error as an error.
- **A47.6:**
  - `with_txy` adds Settings' `convert_backend` unless given;
  - `from_raw` runs it when it can run here, else the app's numpy (numba always numpy: it needs a conversion's
    compiled-code folder);
  - every backend's output is the reference's byte for byte by the converter's contract, proved per backend
    (cython in CI's Converter backends job) by `test_raw_layer.py`'s layer-equals-file tests;
  - the loading test, parametrized over none, numpy, reference, numba and an unknown backend, checks which ran and
    that the data equals the text.
- **Fails without its change** (each commit exported, with its `helab/` files as they were at its parent):

  | Commit | Without its change | With it |
  |---|---|---|
  | `5cbf1d4` | 6 failed | 6 passed |
  | `28d2112` | 2 failed (the new tests; 2 others matched by keyword pass either way) | 4 passed |
  | `9e8c576` | 5 failed (all but the reference case) | 6 passed |
- **Switch off changes nothing:**
  - store-v3 purges are datasets only;
  - the TXY and raw rows are hidden;
  - `read_folder_choices` gives none in store-v3;
  - `backend` in the TXY options is used only by store-v4's raw-layer step.

## Checks (run by the reviewer)

On an export of `9e8c576`, whose `helab/` and `tests/` equal the floor's `HEAD` `585ae26`:
- `pytest -n 4 --reruns 5 --reruns-delay 1 --basetemp=.ai/temp/pytest-assay` (the full suite, every touched test
  file included): **8936 passed, 673 skipped, 2 warnings, 3 failed, 15 rerun in 181.69 s.**
  - All 3 failures and all 15 RERUNs are the three git-provenance tests (the export has no `.git`; 5 reruns each).
  - In the floor checkout: **3 passed, no RERUN**.
  - No other RERUN.
  - The 2 warnings are the known pyqtgraph ones.
  - The totals match Vault's 8940 passed and 672 skipped, once the export's 3 and 1 are added back.
- `mypy helab/ --strict` (203 files), `mypy tests --strict` (191), `--platform win32`: no issues.
- `pyright helab tests` and `--pythonplatform Windows`: 0 errors.
- Scratch, not committed: A47-1 (`.ai/temp/assay/test_zz_a47.py`).

On the fix diff I re-check only the fix, its test and the touched files' type checks.
