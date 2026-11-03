# Review: the store-v4 switch-on, at landing: `origin/dev/v0.0.8...origin/agent/v4-switch-on`

Reviewer: Assay (Claude Opus 5.5), 2026-11-03. Read-only on code.

- **Base:** the merge base `162342d`.
- **Head:** `aeed904`.
- **Under review:** the switch-on itself, `ca9c869`, and the dev merges after it (`e4967ec`, `d3b4931`, `23134c0`).
- **Tony's commits:** `040a294` and `aeed904` are in the diff, but dev already has them as `19aea45` and `5878bd2`.
  I compared the patches without their `index` lines and they are identical.
  - A trial merge (`git merge-tree --write-tree origin/dev/v0.0.8 origin/agent/v4-switch-on`) is clean.
  - At the merge they change nothing, so I did not review them again.

**Verdict: no blocker. 3 findings, all Low, all open.** None is reachable in v0.0.8's behaviour:
- SO-1 matters only from v0.0.9.
- SO-2 is wording in the release notes and code comments.
- SO-3 is test coverage of the hidden fallback.

## Findings

### SO-1 · Low · From v0.0.9, Settings › Cache's Older cache row still says store-v3 is kept and counted, and offers Ignore it / Keep using it

- **Where:**
  - `helab/views/CacheDialogs.py:111` (`legacy_text`: "kept, counted in the budget" / "not answered yet: kept");
  - `helab/views/CacheTab.py:354-356` (the row's tooltip: "Kept: HeLab reads its records … counts toward the
    budget");
  - `helab/views/CacheTab.py:1030-1036` (the Ignore it / Keep using it button, shown whenever store-v3 is there).
- **Scenario.** HeLab 0.0.9 starts with store-v3 in the cache folder, unanswered or under Keep.
  - V~3's gate works as intended: `_kept_legacy()` is None, `_legacy_counted()` is 0, and `_legacy_due()` asks
    nothing.
  - `measure_legacy` then gives `choice` None or `keep` with `counted: False`. But `legacy_text` ignores `counted`,
    so the row reads "N GB · not answered yet: kept" or "kept, counted in the budget".
  - The toggle still offers Ignore it and Keep using it. Both are now no-ops: nothing is read either way.
  - The row contradicts the release note ("From 0.0.9 it is no longer read or counted") and the commit's own
    "only Clear old stores… remains".
- **Also, smaller:** from v0.0.9, `set_legacy_choice` (`cache_store.py:4420-4424`) still opens store-v3 through
  `LegacyStore` to read its `store_id`. The once-only `store_v4.import_legacy` (Q22.4) does too, for a 0.0.7 → 0.0.9
  upgrade.
  - The import is a separate decision from Keep's read-through, and keeping it seems right: it brings over the
    user's flags and roots.
  - But the commit message's "store-v4 neither opens nor counts store-v3" is broader than the code.
- **Fix:**
  - When `not legacy_read_through()`: the row says "no longer read (an older HeLab's)", hides the choice button,
    and keeps Clear….
  - Or record this as a v0.0.9 roadmap item, since today's version is `0.0.7a1` and v0.0.8 reads through.
- **How verified:**
  - by reading `measure_legacy`, `legacy_text` and `CacheTab._show_v4_rows`'s legacy rows;
  - `test_from_v0_0_9_store_v3_is_neither_read_nor_counted_nor_asked_about` covers only the store and `_legacy_due`,
    not the row.

### SO-2 · Low · The release notes (and three comments) name "Settings › Cache › Clear old stores…", which isn't there

- **Where:**
  - `.ai/sessions/2026-10-31-claude-caching-v2/release-notes-v0.0.8-caching.md` ("only Settings › Cache › Clear old
    stores… removes it");
  - comments: `helab/utils/cache_store.py:775` and `:1032`, and `CacheDialogs._legacy_due`'s docstring ("Settings'
    Clear old stores…").
- **Scenario.** A user reads the note and looks in Settings › Cache.
  - The control there is the "Older cache (store-v3)" row's **Clear…** (`CacheTab.py:351,361`).
  - "Clear old stores…" is Make room's button (`CacheDialogs.py:132-146`; `older_stores`, Q28.5).
  - Also in the notes: "The first start shows a one-time question about the older cache". It is shown only when an
    older HeLab's store-v3 is in the cache folder (`_legacy_due`: `present`), so a fresh install never sees it.
- **Fix.**
  - Say "Settings › Cache › Older cache › Clear… (or Make room's Clear old stores…)".
  - Say "If an older HeLab's cache is there, the first start asks…".
  - The notes are Tony's to edit (V~5); the comments are Vault's.
- **How verified:** by grepping `helab/` for both labels.

### SO-3 · Low · The hidden fallback's (store-v3's) user-facing wording for raw-only folders is no longer tested anywhere

- **Where:**
  - `tests/test_folder_summary.py:84-91` (`test_non_data_folder_summary`'s raw case);
  - `tests/test_row_tooltip.py:95-98` ("fixable" and "raw only").
- **Scenario.**
  - On this branch these cases expect store-v4's wording only: "1 raw found · converted when loaded · Not loaded",
    "No cached data", and "· N converted when loaded".
  - Store-v3's wording ("1 raw shot found · No converted TXY files", "No data to cache", and the tooltips without
    the on-read suffix) appears in no test now (grep of `tests/`).
  - V~2 ships store-v3 as the fallback for v0.0.8. A regression in those lines with the row set off would go unseen.
- **Store-v3 elsewhere is still well covered:**
  - The store and helper layers: 103 explicit `store-v2`/`store-v3` directories in 25 test files. The layout comes
    from the folder name, so these run on store-v3 whatever the switch.
  - The 6 marked tests (below).
  - What lost coverage is only the GUI wording above, plus the tests the switch-on moved to the live store (now
    store-v4 only). Those read through layout-neutral helpers (`read_dataset_infos`, `txy_cache.Access`) and would
    pass on either store.
- **Fix:** add a `store_v3`-marked parameter (or a copy) for the raw case and the two tooltip cases, with
  store-v3's expected text.
- **How verified:** by reading the diff and grepping `tests/` for the old strings.

## Checked, no finding

### The default flip and V~2's fallback

- `settings_defaults`: `store_v4` defaults to True. `store_v4_enabled` reads it through `read_setting(…, typed=True)`.
- **Read once per process:** `live_layout()` caches it in `_live_layout`. Scratch: a change to the row after the
  first read is not seen.
- **The row as a person might set it**, read the way a new process reads it (scratch):
  - `"false"`, `"False"`, `"0"` and `False` give store-v3;
  - `"true"`, `True` and no row give store-v4.
- **Helpers don't read the setting.** They open the `directory` in `store_options()`, and its layout comes from the
  folder name.
  - Only `store_root` reads the setting: in the GUI process, and in headless `helab convert` (`convert_cli.py:117`),
    which reads the same settings file and so agrees.
  - `helab cache` reads store-v4 by name.
  - The cache move passes `live_layout()` (`CacheMover.py:118`).

### V~3's version gate

`legacy_read_through` takes the first three numbers.
- The test's cases hold: `0.0.7a1`, `0.0.8a1` and `0.0.8` read through; `0.0.9a1`, `0.0.9`, `0.1.0` and `1.0.0` don't.
- Scratch adds:
  - `0.0.9.dev0` → False;
  - `0.0.8.dev0`, `0.0.8rc1`, `0.0.8.post1` and `0.0.8+local` → True;
  - `0.0.10` → False, compared as numbers, not text;
  - a malformed version (`v0.0.8`, `" 0.0.8"`, `1!0.0.8`, `0.1`, `0.0`, `"not a version"`) → False.
- **The malformed fallback is the safe side:** store-v3 is left untouched and unread, and Clear… stays.
  - `_version.py` is PEP 440, checked by the versioning tests, so a malformed version can't ship.
  - `legacy_read_through("")` falls back to this HeLab's version (`version or __version__`), which is harmless.
- The branch's version is `0.0.7a1`, so read-through is on today. The PR's bump to `0.0.8` keeps it on.
- **The gate covers:** reads (`_kept_legacy`, used by every read-through), the budget (`_legacy_counted`, in usage
  and the fit), and the question (`_legacy_due`).
  - `measure_legacy` still reports store-v3 on disk with `counted: False`. That feeds SO-1.

### What the switch on by default now sends to store-v4

- **Production paths:** see V~2 above.
- **Startup's tidy** removes only the old diskcache folders (unchanged), never `store-v3`.
- **Tests:** a test reaches store-v4 only through the live store (`store_options()`, `store_root(private_store)`).
  - Every such test whose expectation changed is in the diff.
  - I checked every `read_dataset_row(…).missing` / `is None` assertion in `tests/` for one made vacuous by store-v4
    (which never writes a dataset row):
    - the live-store ones were moved to view-aware reads: `test_io_trace`'s `cached()` and `read_dataset_infos`;
    - the rest use explicit `store-v2`/`store-v3` folders, or are store-v4 tests asserting no dataset by design
      (Q45.4).

### The marker and the marked tests

- **There are 6 marked tests, not 7:**
  - `test_store_v4`'s switch-off test;
  - the three "store-v3 half" tests: two in `test_convert_on_read`, one in `test_txy_ui`;
  - the two HeLab-only tests in `test_txy_sources`.
- **Each runs on store-v3, and each depends on it.** With its marker removed (copies, on the export), all 6 fail on
  store-v4:
  - the store-v3 directory assertion;
  - `on_read` in the payload;
  - `policy` in `store_options()`;
  - `shots_missing` / the shot left out.
- **The fixture is sound:**
  - `store_layout` (autouse) runs after `private_settings` and before `private_store`;
  - it sets the row off in the test's own settings file and resets the layout before and after.
  - Scratch, in one process, in order:
    - a marked test sees layout 3, `store-v3`, no `policy`, and a real load writes a `datasets` row. No `store-v4`
      folder is made.
    - The unmarked test after it sees layout 4, `store-v4`, `policy`, a view, and no dataset row.
- **What the 6 cover:**
  - the switch itself;
  - the absence of `policy` and `on_read` under store-v3;
  - store-v3's HeLab-only source rule.

  Store-v3's store and helpers stay covered by the explicit-directory tests (SO-3).

### The rest of the diff

- **The new tests:** the default and the hidden row; the version cases; v0.0.9's store, budget and question.
- **The adjusted tests:** each change follows a documented store-v4 behaviour:
  - `raw_fill` after a load's save;
  - Clear all's `raw`/`txy` kinds;
  - the live store's name;
  - a raw file counts as data (S3~5);
  - "converted when loaded";
  - views instead of dataset rows.

## Checks (run by the reviewer)

On an export of `origin/agent/v4-switch-on` (`aeed904`), with testdata linked:
- `pytest -n 4 --reruns 5 --reruns-delay 1 --basetemp=.ai/temp/pytest-assay`: **9176 passed, 674 skipped, 2
  warnings, 3 failed, 15 rerun in 157.98 s.**
  - All 3 failures and all 15 RERUNs are the three git-provenance tests, 5 reruns each. They fail only because the
    export has no `.git`:
    - `test_release_recovery.py::test_detached_pr_stamp_records_source_branch_and_merge_ref_without_replacing_commit`;
    - `test_versioning.py::test_frozen_metadata_survives_no_git_and_unrelated_cwd`;
    - `test_versioning.py::test_source_provenance_ignores_launch_directory`.
  - In the floor checkout (same options): **3 passed, no RERUN**.
  - No other RERUN.
  - The 2 warnings are the known pyqtgraph ones.
- **Type checks:**
  - `mypy helab/ --strict` (204 files), `mypy tests --strict` (201), `mypy helab/ --strict --platform win32`: no
    issues.
  - `pyright helab tests` and `--pythonplatform Windows`: 0 errors.
- **Scratch, not committed** (`.ai/temp/assay/test_zz_so.py`, 23 passed):
  - the version cases;
  - the row set by hand, read once;
  - a marked test followed by an unmarked one, with real loads.
- **The marker-stripped copies** of the 6 marked tests: 6 failed, as expected. The copies were removed after.

## Re-check of the fixes (`git diff aeed904 669a2d9`: SO-2 `8754b41`, SO-3 `669a2d9`)

**Open findings: none in this diff.** SO-2 and SO-3 are closed. SO-1 is deferred to a v0.0.9 roadmap item (CoCo).

- **SO-2: closed.**
  - The release notes now say "Settings › Cache › Older cache (store-v3) › Clear… (or Make room's Clear old
    stores…)", which match the controls (`CacheTab.py:351,361`; `CacheDialogs.py:141-146`).
  - They also say the question comes only "if an older HeLab's cache (`store-v3`) is in the cache folder", as
    `_legacy_due` checks `present`.
  - The three comments and `CacheTab.clear_legacy`'s docstring say the same.
  - **Not a finding:** "the first start asks once" is a little loose. If the question is closed unanswered, it is
    asked again at the next start (`_legacy_asked` is per session; "Closing it answers nothing"). The old text had
    the same looseness, and the notes are Tony's to edit.
  - **Not a finding:** `CacheTab.clear_legacy`'s new docstring line is 159 characters. Nothing checks line length,
    and `helab/` already has 190 lines over 120.
- **SO-3: closed.**
  - `test_non_data_folder_summary[raw-store-v3]` (a `store_v3`-marked `pytest.param`) checks store-v3's "1 raw shot
    found · No converted TXY files" and "No data to cache".
  - `test_row_tooltip_on_store_v3[fixable, raw only]` checks the tooltips without the on-read count.
  - Both reuse the store-v4 cases' builders. The tooltip check moved into `check_tooltip` unchanged.
  - **The marker works on a `pytest.param`, and the new cases depend on store-v3:** they pass as written (3 passed).
    With the marker removed (copies, on the export), all 3 fail on store-v4.
  - The store-v4 cases still pass beside them.

### Checks (re-check)

On an export of `669a2d9`:
- The touched test files and their neighbours (`test_folder_summary`, `test_row_tooltip`, `test_cache_tab`,
  `test_store_v3_question`, `test_store_v4`, `test_cache_switch`), run with `-n 4 --reruns 5 --reruns-delay 1`:
  **221 passed, no RERUN.**
- **Type checks:**
  - `mypy --strict` of the touched files: no issues;
  - `mypy helab/ --strict --platform win32` (204 files): no issues;
  - `pyright` of the touched files, and `--pythonplatform Windows`: 0 errors.
