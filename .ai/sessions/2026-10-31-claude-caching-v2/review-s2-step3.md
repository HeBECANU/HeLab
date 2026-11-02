# Review: Caching v2 stage 2, step 3 (loading): `6b0f998..e985e12`

Reviewer: Assay (Claude Opus 5.5), 2026-11-02. Read-only on code. The commits:

| Commit | What |
|---|---|
| `7d185eb` | 3a, `txy_cache.Access` |
| `d8b6bae` | 3a, cached reads carry the tab source |
| `3366640` | 3b, a plot's own choice cached under its own view |
| `d96c65f` | S2-3, and the TXY guard with `gen_datasets` and the folder epoch |
| `2f6c1f3` | 3c, `folder_choices` |
| `08895bc` | 3d, the v4/v3 dataset seeds and A42.1 |
| `6f57918` | 3e, a HeLab shot from the raw layer |

I read the handoff's "Step 3" with its departures, design §4–§7, and AGENTS.md's I/O and cache rules.

**Verdict: no blocker while the switch is off. 2 findings: 0 High, 1 Medium, 1 Low.** Both are reachable only with
the `store_v4` switch on.
- **S3-1 (Medium):** a folder's Clear data cache, and a purge of cached data by age, no longer reach the data
  store-v4 loads now keep (TXY layers and views). Fix before the switch goes on.
- **S3-2 (Low):** converting a HeLab shot from the raw layer runs inside the load's per-file timeout window with no
  heartbeat, against design §4. It fails large shots on a slow PC.

## Findings

### S3-1 · Medium · In store-v4 a folder's "Clear data cache" and a purge by age leave its TXY layers and view, so the next load serves the cleared data

- `helab/io_helper.py:144-150`: `invalidate`, which is `FolderExplorer.clear_data_cache`, removes
  `("datasets",)` only.
- `helab/io_ops/admin.py`'s `purge` with `what="datasets"` → `CacheStore.purge_datasets` (`cache_store.py`):
  datasets only.
- **Scenario.** Since `7d185eb`, store-v4 loads and Live's saves write TXY layers and a view, never a dataset.
  1. The user chooses Clear data cache for a folder. The helper removes its (absent) dataset row and bumps its
     epoch, and the app marks the folder not disk-cached.
  2. The folder's layers and view are untouched, so the next load's `Access.row` finds the view and serves the
     "cleared" data from the layers (shown as cached again).
  3. Likewise, purging cached data not used for N days removes no layer or view, so layers never age out.

  The new TXY guard (the folder's epoch, `d96c65f`) stops a load *already running* from saving back. But the data
  saved before the Clear simply stays. In store-v3 both actions remove the folder's cached data. This is what the
  user asked for and gets in v3, and doesn't get in v4.
- **Fix.**
  - `invalidate` in store-v4 also removes the folder's TXY layers and views (`remove_txy([path])`), and its raw
    layers seen. Only copies stay unless a question names them, as Don't cache does (C2-9, Tony's
    confirmation). Send `_removal_events`.
  - The purge by age takes layers and views not used since the cutoff, only copies kept. Or, for CoCo or Tony to
    decide: the purge row says it is datasets only.
  - Add a test for each.
- **How verified.** Scratch tests (`.ai/temp/assay/test_zz_s3.py`, on an export of `e985e12`):
  - after `store.remove(("datasets",), [X])` (exactly what `invalidate` runs), `read_view(X, "", "")` is found and
    `txy_layers(X)` still holds `matlab`;
  - after the admin's `purge` (`what="datasets"`, cutoff an hour ahead), `txy_layers(X)` still holds `matlab`.

### S3-2 · Low · A HeLab shot from the raw layer is converted inside the load's per-file window: no heartbeat, a 15 s limit

- `helab/io_ops/txy_cache.py:188-221` (`Access.from_raw`: decode, `reconstruct`, `format_txy`, `pandas.read_csv`).
- It is called from `read_txy` (`helab/io_ops/loading.py:673-677`), after the load's `file_started` for that shot.
- **Scenario.**
  - While a load reads a file (between `file_started` and `file_finished`), `IOService` counts only file events as
    progress, and its limit is `TIMEOUTS` = 15 s, then 20 s and 30 s on retry. Heartbeats wouldn't count even if
    sent.
  - `from_raw` runs all its work in that window. Design §4 said it runs "under the converter's ticker
    (`compute_budget`, as C3-1)" in the load's pool. It has neither.
  - **Measured here:** the testdata's largest raw shot (3.25 MB, `testdata/data/eras/2023-02-new-plates/d6.txt`)
    takes 0.48 s through this path on an M4 (6.8 MB/s of raw). Parsing its 1.42 MB TXY text takes 0.004 s.
  - At the lab PC's estimated 3–4× slower rate, a shot of about 30 MB or more passes 15 s. It then fails each
    attempt and the load fails, where reading the text (always on the share in stage 2) would have taken well
    under a second.
- **Fix.** Either:
  - use the raw step only when the shot's `compute_budget` fits well inside the first file timeout (else read
    the text);
  - or convert before `file_started`, under a `_Ticker`, as the design says.

  Also worth a word in the handoff: while the HeLab text is on the share (stage 2's boundary), the raw step is
  much slower than the text on a local disk. Its gain is for slow shares.
- **How verified.**
  - By reading `IOService`'s progress rule (`io_service.py`: "while a file is read only file events count";
    `TIMEOUTS = (15.0, 20.0, 30.0)`).
  - The timing script above (read-only on HeLab's own test data).
  - The lab-PC figure is an estimate (the addendum's 3–4×), not a run there.

## Notes (not findings)

- **Step 4: compaction.** Live's save (`save_held`) now writes one segment per save, but nothing calls
  `compact_txy` yet. Step 4 wires it.
- **The departures look safe as stated:**
  - `save_dataset` isn't refused in v4, and loads never call it there (tested);
  - Live follows a folder's source once FolderCache has learnt it (a load's or the admin's `folder_choices`);
  - 3e works for built-in profiles only: other profiles read the text.
- **The "GUI stalled" log line** the handoff saw once: not in my full run (`grep` 0). The proposed known-issues line
  is reasonable.

## Checked, no finding

- **Loading order:** the view (layers), then the raw layer (built-in profiles, the raw row's fingerprint and
  parser equal to the listing's raw file), then the share. With no view yet, the folder's own v4 `datasets` row,
  else store-v3's under Keep (Q45.4, Q45.5). Seeded data is used only for shots whose fingerprint matches, as a
  dataset's was, and the load then saves it into layers (`cached` → False).
- **Identity:** `entry_keys` keys HeLab shots by their listed raw file (S~2), else by the TXY file; MATLAB shots by
  the TXY file. A save writes only shots a layer lacks under that key (and problematic flag). A held shot already
  kept isn't read again for the save (`lacking`).
- **Guards and `job_seq`:**
  - every store-v4 load and Live save takes the dataset guard and then the TXY guard;
  - the TXY guard now covers `gen_txy`, `gen_datasets`, the `txy:` epoch, the folder's own and the root's
    (`d96c65f`);
  - `confirm` (A40.3) writes only the view's info under the TXY guard;
  - per-shot `job_seq` is `save_txy`'s (checkpoint 1).
- **S2-3 closed:** loads and `save_held` pass `seen_at=listed_at`, a waiting part keeps it, and adoption uses it.
  `test_a_new_layer_is_first_seen_when_its_job_listed` fails without `d96c65f` and passes with it.
- **Nothing removed without asking:**
  - seeding only reads: v4 `datasets` through the store, store-v3 through `LegacyStore.dataset_row` and
    `read_file`, with `mode=ro`;
  - `legacy_dataset` refuses a folder whose datasets v4 removed (`_legacy_hidden("datasets", …)`);
  - no new removal path. (S3-1 is the opposite: a removal that doesn't happen.)
- **A42.1:** the copy runs under the find's own result guard, `only_new`, `hold=False`, and falls back to the v3 row
  on any failure. It never overwrites a result saved since and never waits.
- **3b, 3c:**
  - a plot's own choice is cached under its own view, quietly (`QUIET_KINDS` filtered, `hold=False`). The folder's
    saved Don't cache still keeps it RAM only.
  - `with_choices` applies the folder's source and tag to the tab's loads only (`tab`); a plot's explicit choice
    keeps its own.
- **I/O rules:** all store and source work stays in the helper. `mark_seen` runs once per listing, best effort.
  Cached reads carry the tab's source (`with_txy` for `cached`). No GUI waits: FolderCache only remembers
  `folder_choices`.
- **Switch off changes nothing:** `Access` delegates to the dataset methods in store-v3 (`signature_matters`,
  `lacking` all shots, `confirm_dataset`, `_write_dataset`). `folder_choices`, `quiet`, `mark_seen` and `from_raw`
  are v4 only. The full suite passes with the switch off.
- **Fails without its change, where claimed** (each on an export of its commit, with its `helab/` files as they
  were before it):
  - `d96c65f`: 2 failed, 2 passed with it;
  - `6f57918`: 1 failed, 1 passed with it.

## Checks (run by the reviewer)

On an export of `e985e12`:
- `pytest -n 4 --reruns 5 --reruns-delay 1 --basetemp=.ai/temp/pytest-assay` (the full suite, every touched test
  file included: `test_txy_loading.py`, `test_txy_layers_store.py`, `test_store_v4.py`,
  `test_helper_dispatch.py`, `test_caching_v2_session.py`): **8905 passed, 673 skipped, 2 warnings, 3 failed,
  15 rerun in 153.77 s.**
  - All 3 failures and all 15 RERUNs are the three git-provenance tests (the export has no `.git`; 5 reruns each).
  - In the floor checkout: **3 passed, no RERUN**. Vault's uncommitted `txy_cache.py` edit there doesn't touch
    them.
  - No other RERUN.
  - The 2 warnings are the known pyqtgraph ones.
  - The totals match Vault's 8909 passed and 672 skipped, once the export's 3 and 1 are added back.
- `mypy helab/ --strict` (203 files), `mypy tests --strict` (189), `--platform win32`: no issues.
- `pyright helab tests` and `--pythonplatform Windows`: 0 errors.
- Scratch checks, not committed: S3-1 (`.ai/temp/assay/test_zz_s3.py`), S3-2's timing (an inline script).

On fix diffs I re-check only the fixes, their tests and the touched files' type checks.
