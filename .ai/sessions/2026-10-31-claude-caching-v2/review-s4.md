# Review: Caching v2 stage 4, the policy UI (switch off): `f285f1d..beffbff`

Reviewer: Assay (Claude Opus 5.5), 2026-11-03. Read-only on code. The commits:

| Commit | What |
|---|---|
| `1ad31a9` | S4~1: TXY only offers to remove HeLab's cached raw pulses (a folder; Settings) |
| `beffbff` | the stage 4 session in `test_caching_v2_session.py` |

`1ad31a9` lies before `f285f1d` (my stage 3 re-check), so I reviewed it as `git show 1ad31a9` against `fa7884f`. I read
the handoff's "Stages 3 and 4" (Tony's S4~1 wording) and "Stage 4", and AGENTS.md's removal rules.

**Verdict: no blocker. 4 findings: 0 High, 0 Medium, 2 Low, 2 Nit.** Nothing is removed without asking, the d files
are never touched, and every only copy that a yes removes is named first. All four are reachable only with the
`store_v4` switch on.
- **S4-1 (Low):** Settings' question gives the whole store's size and only copies, not those of the folders it removes.
- **S4-2 (Low):** the folder's question opens a modal inside FolderCache's helper-event handler.
- **S4-3 (Nit):** Settings skips the offer silently when busy or before the inventory is in, and never asks again.
- **S4-4 (Nit):** a comment is split from its constant.

## Findings

### S4-1 · Low · Settings' TXY only question asks about the whole store's raw pulses, but removes only the following folders'

- `helab/views/CacheTab.py:45-53` (`remove_raw_following_text(raw)`: `raw["bytes"]` and `raw["only_copy"]`).
- `:1127-1132` (`save`: `raw = self.inventory["raw"]`, the store's totals).
- `helab/utils/cache_store.py:3091-3110` (`remove_raw_following`: only the folders with no `cache_policy` of their own).
- **Scenario.** The switch is on. Folder A follows Settings and has 2 cached shots. Folder X has its own policy
  (Raw + what you load) and 1 shot. The user saves TXY only in Settings.
  - The question says "up to 2.2 kB" (3 shots), and names X's only copies if it has any.
  - A yes removes 1.5 kB (2 shots), and X keeps its pulses.
  - When a large folder keeps its own policy, the figure can be many times what goes. The only-copy sentence can
    name shots that stay, or appear when none of the removed folders has an only copy.
  - The error is always an overstatement. Nothing is removed beyond what is named, and no only copy goes unnamed.
    But it misses CoCo's criterion that the asked size matches what is removed. A47.4 held the purges to the same
    rule: the estimate uses the removal's own condition.
- **Fix.** Report what `remove_raw_following` would remove, using its own `WHERE`: count, bytes and only copies.
  - Either `inventory()["raw"]` gains a `following` part, or `CacheStore.raw_following()` is called beside it.
  - The question then says "N MB" without "up to".
  - Add a store test with an only copy (`gone_at` set) in a following folder and another in a folder with its own
    policy, and check that the estimate equals the removal.
  - Today's tests never set `gone_at` for `folder_raw` or `remove_raw_following`. The UI test injects
    `only_copy: 1`.
- **How verified.** Scratch test (`.ai/temp/assay/test_zz_s4.py`, using `test_raw_layers_store.py`'s helpers, on an
  export of `beffbff`). The store has RUN with 2 shots, and X with 1 shot and `set_cache_policy(X, "raw+used")`.
  - The question's text says "up to 2.2 kB", from `inventory()["raw"]`: 2216 B, 3 shots.
  - `remove_raw_following()` removed 1478 B, 2 shots.

### S4-2 · Low · The folder's question opens a modal dialog inside FolderCache's helper-event handler

- `helab/utils/folder_cache.py:3892-3896` (`_on_admin_event` emits `rawRemovalOffered` inline).
- `helab/views/FolderExplorer.py:2430-2445` (`_offer_raw_removal` then `_ask_remove_raw`: `box.exec()`, connected
  directly at `:456`).
- **Scenario.** The switch is on. The user sets a folder to TXY only, and it has cached raw pulses.
  - The `admin_result` event reaches `_on_admin_event`, which emits `rawRemovalOffered`. The explorer runs
    `QMessageBox.exec()` in that call, a nested event loop, while FolderCache's handler is still on the stack.
  - While the box is open, IOService's queued events are handled re-entrantly. That includes the same job's `done`,
    which pops `_admin`, `_choice_writes` and `_choice_owners`.
  - After the box closes, the outer handler goes on and emits `cacheAdminResult("folder_choice", …)` for the
    `admin_result`, after the job's own `done`. Listeners see a job's result after its end.
  - The other events handled meanwhile (loads, listings, Live) run inside a half-finished handler. No other
    FolderCache signal opens a modal synchronously: the Make room, root-copy and data-root questions start from a
    user action, or from a button that a signal updates.
  - Nothing breaks that I could show today. Each later change to `_on_admin_event`'s tail would have to allow for
    this.
- **Fix.** Ask after the handler returns. Either `QTimer.singleShot(0, …)` in `_offer_raw_removal`, keeping the
  `closed` and owner checks, or `box.open()` with a `finished` slot (a bound slot, per the UI rule on senders). Keep
  `ask_remove_raw` as the test seam.
- **How verified.** By reading `_on_admin_event` and `_offer_raw_removal`, and IOService's queued `resultReady`
  delivery. I grepped `helab/views` for other modals that cache signals start, and found none.

### S4-3 · Nit · Settings skips the offer silently when busy or before the inventory is in, and never asks again

- `helab/views/CacheTab.py:1127-1128` (`raw = (self.inventory or {}).get("raw")` … `and not self.busy`).
- **Scenario.** The user saves TXY only while Settings › Cache runs another job, or before its inventory has arrived.
  No question is asked and nothing is removed, which is safe. Next time `before` is already `"txy"`, so the offer
  never comes again. The pulses stay until the user finds Clear raw pulses.
- **Fix (optional).** Say so in the tab's status line ("Cached raw pulses kept: Clear raw pulses removes them"), or
  ask once the job ends. Otherwise note it in the handoff as accepted.
- **How verified.** By reading `save`.

### S4-4 · Nit · `remove_raw_text` splits a comment from its constant

- `helab/views/FolderExplorer.py:64-74`. The comment "A folder's own TXY source or cache policy (caching v2 stage 2):
  following the global one." now sits above `def remove_raw_text`. Its constant `FOLDER_CHOICE_GLOBAL` is 10 lines
  below.
- **Fix.** Move the function above the comment, or below `FOLDER_CHOICE_GLOBAL`.

## Checked, no finding

- **Nothing removed without asking.**
  - `folder_choice` with policy `txy` only reads `folder_raw`. The session test keeps both rows after it, and
    `raw_fill` then stops for "policy".
  - The folder's removal is `clear_raw paths=[path]`, sent only when `_ask_remove_raw` returns True ("Remove cached
    raw pulses"; "Keep them" is the reject role).
  - Settings' removal is `clear_raw following=True`, sent only on `confirm(…, "Remove")`.
  - Both send `removed` (`_raw_removed_event`, Q3.3).
- **Only the asking tab asks.** `_choice_owners` records `set_folder_choice`'s `owner`, and `_offer_raw_removal`
  checks `owner != self.model.owner` and `closed`. The entry is popped on `done`, `error` and `cancelled`.
- **Only copies named.**
  - The folder's text names `only_copy` shots ("their raw files are gone from the folder, so they can't be read
    again"). Settings' text names them as "up to" (see S4-1).
  - A yes removes them, as Clear does. This matches Q22.6 and C2-9: never removed unnamed. "Keep them" keeps
    everything. The purges still keep only copies (`gone_at IS NULL`).
- **The d files are never touched.**
  - `remove_raw_following` and `remove_raw` delete `raw_layers` rows and retire store files only.
  - The session test compares `d1`–`d3`'s bytes before and after, and the next load still converts all 3 on read.
- **Save guards.** `remove_raw_following` bumps each removed folder's `raw:` epoch inside the transaction, as
  `remove_raw` does, so a raw batch already on its way can't bring them back.
- **The folder's size matches its removal.** `folder_raw` sums every row of the folder, and `clear_raw paths=[path]`
  removes every row. Rows a `raw_fill` adds in between would also go. TXY only stops new fills, and the epoch fences
  saves still running.
- **Tony's wording.** "Also remove HeLab's cached copy of this folder's raw pulses (N MB)? Your d files aren't
  touched.", with "HeLab's cached raw pulses" on the button.
- **UI rules.**
  - `identify_buttons(box, "txy_only_raw_confirm")` gives the buttons names and IDs.
  - The signal is connected as a bound method and disconnected on close.
  - No lambda captures a Qt-made sender.
- **Switch off changes nothing.**
  - `folder_raw` and `remove_raw_following` return zeros in store-v3.
  - Policy rows and the folder's policy menu exist only with store-v4.
  - The new `AdminResultFields.folder_raw` is typed in `events.py`.
- **Fails without its change.** On an export of `1ad31a9`, with its six `helab/` files as they were at `fa7884f`:
  `test_txy_only_offer.py` + `test_txy_ui.py` give **4 failed, 14 passed**. Restored (compared with git):
  **18 passed**.
- **`beffbff`.** The session test runs the helpers' own `cache_admin`, `raw_fill` and `load` with the switch on,
  and checks what the handoff says.

## Checks (run by the reviewer)

On an export of `beffbff`, whose `helab/` and `tests/` equal the floor's `HEAD` `ba11e8a`:
- `pytest -n 4 --reruns 5 --reruns-delay 1 --basetemp=.ai/temp/pytest-assay` (the full suite,
  `test_txy_only_offer.py` and `test_caching_v2_session.py` included): **8957 passed, 673 skipped, 2 warnings,
  3 failed, 15 rerun in 159.11 s.**
  - All 3 failures and all 15 RERUNs are the three git-provenance tests. The export has no `.git`, and each ran
    with 5 reruns.
  - In the floor checkout: **3 passed, no RERUN**.
  - No other RERUN.
  - The 2 warnings are the known pyqtgraph ones.
  - The totals match Vault's 8961 passed and 672 skipped, once the export's 3 and 1 are added back.
- `mypy helab/ --strict` (203 files), `mypy tests --strict` (193), `--platform win32`: no issues.
- `pyright helab tests` and `--pythonplatform Windows`: 0 errors.
- Scratch, not committed: S4-1 (`.ai/temp/assay/test_zz_s4.py`).

On fix diffs I re-check only the fixes, their tests and the touched files' type checks.

## Re-check of the fixes (`cbba723..3085e53`)

**Open findings: 1 Nit (S4R-1).** S4-1, S4-2 and S4-4 are fixed. S4-3 is fixed in the tab, but its message can't be
seen (S4R-1). No blocker.

### S4R-1 · Nit · S4-3's status line is set on a Settings dialog that closes at once, so the user never sees it

- `helab/views/CacheTab.py:1138-1140` (`self.message = RAW_KEPT_MESSAGE`, in `save`).
- `helab/views/SettingsDialog.py:393-396` (`_write_settings`: `self.cache_tab.save(settings)`, then `self.accept()`).
- `helab/views/HelabMainWindow.py:912` (each opening makes a new `SettingsDialog`).
- **Scenario.** The user saves TXY only while Settings › Cache runs a job, or before its inventory is in.
  - `save` sets the tab's message, and the dialog then closes and is dropped.
  - The next Settings opening has a new tab with no message.
  - So nothing is offered and nothing is said, as before the fix. Nothing is removed, which is safe.
  - The test calls `tab.save` on a bare tab, so it can't show this.
- **Fix.** Say it where the user will see it after Settings closes:
  - a notification (`helab/utils/events.py`) or a QMessageBox information box;
  - or keep the dialog open on the Cache tab, as a declined budget does (`save_settings`' `else`).
  Or accept S4-3 as it stands, and note it in the handoff.
- **How verified.** By reading `_write_settings`, `save_settings` and `HelabMainWindow`'s opening of Settings.

### The fixes

- **S4-1: fixed.**
  - `inventory()["raw"]["following"]` (count, bytes, folders, only copies) uses `_FOLLOWING`, the same `WHERE`
    string `remove_raw_following` selects with.
  - The question names the folders and their size, without "up to", and names only those folders' only copies.
  - The new store test sets `gone_at` in a following folder and in one with its own policy. It checks that the
    estimate's rows and bytes equal the removal, and that the other folder's only copy is left out.
  - My S4-1 scratch figures now agree.
- **S4-2: fixed.**
  - `_offer_raw_removal` only checks the owner, `closed` and the path, then defers the question with
    `QTimer.singleShot(0, functools.partial(self._ask_raw_removal, …))`. The partial wraps a bound method, not a
    Qt-made sender.
  - `_ask_raw_removal` checks `closed` again before asking, so a tab closed in between asks nothing.
  - The test checks that nothing is asked synchronously, and then that it is asked.
  - Observation: the test's closed-tab case closes the tab before the offer, so it exercises the first check. The
    second check is a one-line guard, read.
- **S4-3: in the tab.** When busy, or with no inventory, `save` sets `RAW_KEPT_MESSAGE` and asks nothing. See S4R-1.
- **S4-4: fixed.** `remove_raw_text` now sits after the constants, and the comment is back on `FOLDER_CHOICE_GLOBAL`.
- **Fails without the fixes.** I exported `3085e53` and set its three `helab/` files back to `cbba723`.
  - `test_txy_only_offer.py` doesn't import: `RAW_KEPT_MESSAGE` is new.
  - With that import replaced by the constant's text: **3 failed, 2 passed**.
  - Restored (compared with git): **5 passed**.

### Checks (re-check)

On an export of `3085e53`, whose `helab/` and `tests/` equal the floor's `HEAD` `ee4df2b`:
- Touched and neighbouring tests, run with `pytest -n 4 --reruns 5 --reruns-delay 1 --basetemp=.ai/temp/pytest-assay`:
  `test_txy_only_offer`, `test_txy_ui`, `test_cache_tab`, `test_raw_layers_store`, `test_caching_v2_session`,
  `test_cache_store`, `test_accessible_names` and `test_destroyed_connections`.
  **135 passed, no RERUN.**
- `mypy helab/ --strict` (204 files), `mypy tests --strict` (199), `--platform win32`: no issues.
- `pyright helab tests` and `--pythonplatform Windows`: 0 errors.

## Re-check 2 (`eb38718`: S4R-1)

**Open findings: none.** S4R-1 is fixed.

- **The fix.**
  - `EventHub.notify` gains `status=True`. Without `desktop`, it hands the message to the main window's existing
    status sink, `show_status_notice`, which `HelabMainWindow` registers and which shows the message for 10 s.
  - It records the event as shown, with `desktop` False. It never shows a desktop notification.
  - A failing sink is logged, and HeLab goes on.
  - Settings' TXY only sends `RAW_KEPT` with `RAW_KEPT_MESSAGE` when it can't offer the removal (busy, or no
    inventory yet), beside the tab's own message.
  - The notice reaches the main window, which stays open after Settings closes.
- **Its test.** In both states, the test checks that the status sink got the message once, that the event's kind
  is `RAW_KEPT`, and that the event was shown and not desktop. A fake desktop notifier fails the test if it is
  called. Hooks get the event as for any other kind.
- **Fails without it.** On an export of `eb38718`, with `events.py` and `CacheTab.py` set back to `eb38718^`:
  `test_txy_only_offer.py` gives **1 failed** (`AssertionError: busy`) and **4 passed**. Restored (compared with
  git): **5 passed**.
- **Checks.** On that export, whose `helab/` and `tests/` equal the floor's `HEAD`:
  - Touched tests and every test file that uses `events`, run with `pytest -n 4 --reruns 5 --reruns-delay 1
    --basetemp=.ai/temp/pytest-assay`: `test_txy_only_offer`, `test_cache_tab`, `test_events_hub`,
    `test_headless_imports`, `test_clock_skew`, `test_live_convert` and `test_shot_trends`.
    **118 passed, no RERUN.**
  - `mypy helab/ --strict` (204 files), `mypy tests --strict` (199), `--platform win32`: no issues.
  - `pyright helab tests` and `--pythonplatform Windows`: 0 errors.

Stage 4 has no open review findings.

## The fresh-store race (`eb38718..c06f342`: `cache_store.py`, `test_store_v4.py`)

**Verdict: 1 open finding: 0 High, 1 Medium.** The fix for "duplicate column name: maker" is right, and every other
step of the schema that can't run twice is guarded the same way. But a second race on the same path is left: the
WAL pragma. It makes the new 6-thread test fail about 1 run in 4.

### SR-1 · Medium · Helpers opening a new store at once still fail: `PRAGMA journal_mode = WAL` says "database is locked" at once

- `helab/utils/cache_store.py:955` (`_open`: `conn.execute("PRAGMA journal_mode = WAL")`, before `BEGIN
  IMMEDIATE`, for a store with no layout yet).
- `:4573-4578` (`_transient_io_error`: only `SQLITE_IOERR` is retried, not `SQLITE_BUSY`).
- **Scenario.** Several helpers open a store-v4 that doesn't exist yet. This happens after the switch goes on, or
  after a cache-folder move.
  - Each one finds no layout and switches the new file to WAL.
  - Changing the journal mode needs the database to itself. While another connection is changing it, or holds the
    write lock, SQLite returns "database is locked" **at once**, without waiting out the 30 s `busy_timeout`. My
    40 rounds of 6 opens took 1.1 s in all.
  - The open is not retried, so the helper's request fails with "Disk cache could not be opened: database is
    locked".
  - It is the same "new store opened by helpers at once" case that `c06f342` fixes for the schema. The line is
    older than this commit, but the commit's own test hits it.
- **The new test is flaky because of it.** `test_a_new_store_opened_by_two_helpers_at_once_is_made_once[store-v4]`
  fails in its 6-thread part with `StoreError('Disk cache could not be opened: database is locked')`:
  - alone, without reruns: **4 of 15 runs failed**;
  - with `--reruns 5 --reruns-delay 1`: **4 of 12 runs needed a RERUN**.

  Under AGENTS.md this would be a RERUN in CI that blocks landing until it is explained.
- **Fix.** Make the switch to WAL wait like any other lock, for example:
  - read `PRAGMA journal_mode` and skip the switch when it is already `wal` (WAL persists in the file);
  - otherwise retry the pragma on `SQLITE_BUSY` (`sqlite_errorcode & 0xFF == SQLITE_BUSY`, or the "database is
    locked" text) until `busy_timeout` has passed;
  - or create the store under `BEGIN IMMEDIATE` in the default journal mode, then switch to WAL once, with that
    retry.

  Then run the 6-thread part over several rounds (my scratch uses 40 rounds of 6 opens), so it fails reliably
  without the fix rather than about one run in four.
- **How verified.**
  - Scratch test `.ai/temp/assay/test_zz_race.py`, on an export of `c06f342`: 40 rounds of 6 threads opening a
    fresh `store-v4`; **4 of 240 opens failed**.
  - The cause's traceback: `cache_store.py`, line 955, in `_open`: `conn.execute("PRAGMA journal_mode = WAL")`,
    `sqlite3.OperationalError: database is locked`.
  - The rerun counts above are from repeated runs of the commit's test.

### Checked, no finding

- **The fix.**
  - `_open` checks `_layout_version` again after `BEGIN IMMEDIATE`. Creation and its meta rows are one
    transaction, so a second helper sees either no `meta` table or a whole store.
  - When the store is there, the second helper commits without running the schema.
  - Either way it goes on to the usual layout check, `_migrate`, `store_v4.migrate` and `import_legacy`.
  - `_create` is the old body unchanged, moved.
- **Every other step that can't run twice is checked again under the write lock.**
  - `_migrate`: `missing()` again after `BEGIN IMMEDIATE`; its one `ALTER` (`datasets.raw_times`) runs only when
    still missing; meta rows go in with `INSERT OR IGNORE`.
  - `store_v4.migrate`: `no_layers()` and `no_seen_at()` again under the lock, for `STAGE2_SCHEMA`'s
    `ALTER pending_saves ADD parts` and the `txy_layers.seen_at` `ALTER`.
  - `import_legacy`: `_imported()` again under the lock; rows go in with `INSERT OR IGNORE`; `imported_v3` with
    `INSERT OR REPLACE`, written once.
  - `SCHEMA`, `ROOT_SCHEMA` and `store_v4.SCHEMA`'s tables and indexes are `IF NOT EXISTS`. `ALTER` appears nowhere
    else in `helab/`.
- **Store-v3 unchanged.**
  - The layout comes from the folder's name (`layout_of(root)`).
  - For store-v3 the only change is that a helper finding the store already made skips idempotent statements it
    used to repeat.
  - Store-v3's case of the deterministic test fails without the fix only through the test's stub, which hides the
    layout from the final check. It guards store-v3 against the change; it doesn't show a store-v3 bug.
- **Fails without it.** On an export of `c06f342`, with `cache_store.py` as it was at `eb38718`: the test fails
  for store-v4 with "duplicate column name: maker" (8 of 8 runs). With the fix, the deterministic part always
  passes.
- **Checks.** On that export, whose `helab/` and `tests/` equal the floor's `HEAD`:
  - `pytest -n 4 --reruns 5 --reruns-delay 1 --basetemp=.ai/temp/pytest-assay` on `test_store_v4`,
    `test_cache_store`, `test_cache_store_open`, `test_result_cache_store` and `test_caching_v2_session`:
    **123 passed, no RERUN in that run.** The repeated runs above did RERUN (SR-1).
  - `mypy helab/ --strict` (204 files), `mypy tests --strict` (199), `--platform win32`: no issues.
  - `pyright helab tests` and `--pythonplatform Windows`: 0 errors.

## Re-check of SR-1 (`872b679..768ac40`)

**Open findings: none.** SR-1 is fixed, and the test doesn't flake.

- **The fix.** `_wal(conn, busy_timeout)` replaces the bare pragma on a store with no layout.
  - It reads `PRAGMA journal_mode` and switches only when the mode isn't `wal`. When another helper made the store,
    it is WAL already, so there is nothing to switch.
  - Otherwise it retries on `SQLITE_BUSY` or `SQLITE_LOCKED` (by code, else by text) every 5 ms until
    `busy_timeout`, then raises. Other errors raise at once.
  - It runs only in the processes that open the store (helpers, `helab convert`, `helab cache`), never on the GUI
    thread.
  - It also covers store-v3's creation, which had the same WAL race. Without the fix the test's store-v3 case
    failed too, and nothing else changes for store-v3.
- **Observation, not a finding:** the pragma's answer isn't checked. SQLite returns the old mode, without an error,
  when it can't switch for reasons other than a lock, such as inside a transaction, which can't happen here. The old
  code didn't check it either.
- **The test** now runs 8 rounds of 6 threads, each on a fresh store, for store-v4 and store-v3.
- **Fails without the fix.** On an export of `768ac40`, with `cache_store.py` as it was at `872b679`, in 20 runs:
  - 9 failed: 5 with both cases failing, 4 with one;
  - 11 passed.

  The test catches the race about half the time, where it used to catch it about a quarter of the time. It can't
  be deterministic, since the race is SQLite's. The fix, which is the part that matters, never failed in what
  follows.
- **Doesn't flake with the fix.** Restored and compared with git:
  - **100 of 100** sequential runs passed;
  - another **100 of 100** passed as 4 loops of 25 at once, under load;
  - my scratch test (`.ai/temp/assay/test_zz_race.py`, 40 rounds of 6 fresh opens) had **0 of 240** opens fail,
    against 4 before.
- **Checks.** On the export, whose `helab/` and `tests/` equal the floor's `HEAD`:
  - `pytest -n 4 --reruns 5 --reruns-delay 1 --basetemp=.ai/temp/pytest-assay` on `test_store_v4`,
    `test_cache_store`, `test_cache_store_open`, `test_result_cache_store` and `test_caching_v2_session`:
    **123 passed, no RERUN.**
  - `mypy helab/ --strict` (204 files), `mypy tests --strict` (199), `--platform win32`: no issues.
  - `pyright helab tests` and `--pythonplatform Windows`: 0 errors.

Stage 4, its race fix included, has no open review findings.

## The views fix (`768ac40..4afa96a`: store-v4's listings, scans and adopt read the folder's view)

**Verdict: no blocker. 1 finding: 0 High, 0 Medium, 1 Low.** With the switch on, cached badges, cache-first and
offline browsing after a restart now find store-v4's cached folders. The handoff's sweep holds. Store-v3 is
unchanged.

### SV-1 · Low · One damaged view record makes the whole listing fail, where store-v3 reports an error for that folder

- `helab/utils/cache_store.py:2209-2215` (`_view_infos`: `json.loads(fingerprint)`, then `entry[4]` and
  `entry[1]` for each entry, unguarded).
- `:2277-2279` (`read_dataset_infos` catches only `sqlite3.Error` and `StoreError`).
- **Scenario.** The switch is on. One folder's `txy_views.fingerprint` is unreadable: damaged, or written by a
  HeLab whose entries have another shape.
  - `json.loads` raises `JSONDecodeError`, a `ValueError`; a short entry would raise `IndexError`, a non-list
    `TypeError`.
  - The exception leaves `read_dataset_infos`, then `_read_saved`, then `list_folder`. The listing of the parent
    folder fails outright, so every sibling's listing, badges and saved status are lost with it.
  - Store-v3 doesn't do this. A malformed fingerprint fails inside SQLite's `json_each`, as a `sqlite3.Error`, which
    is caught. A malformed `info` is `_error`'d per folder. Either way it becomes a `cache_warning`, and the listing
    goes on: "a read answers found / missing / error".
- **Fix.** In `_view_infos`, parse each folder's view in its own `try` for `ValueError`, `IndexError` and
  `TypeError`. Let `read_dataset_infos` answer `_error("Saved dataset record is unreadable: …")` for that folder
  only, for example by returning the failures beside the rows. Add a case to `test_v4_listings.py` with one damaged
  view among two folders.
- **How verified.** Scratch test (`.ai/temp/assay/test_zz_views.py`, using `test_txy_loading.py`'s helpers, on an
  export of `4afa96a`):
  - after a store-v4 load, set the folder's `txy_views.fingerprint` to `'not json'`;
  - `read_dataset_infos` raised `JSONDecodeError: Expecting value: line 1 column 1 (char 0)`;
  - `list_folder` of its parent raised the same.

### Checked, no finding

- **Listings find store-v4's cached folders.**
  - `read_dataset_infos` still reads `datasets` first, which in store-v4 holds stage 1's seeds only. It then
    overlays `_view_infos` for folders that have views, so a view wins over a seed, and a folder with only a seed
    still answers from it.
  - Which view: the one `wanted` names, else the most recently used. The `ORDER BY last_used` loop keeps a wanted
    view once found.
  - What it gives:
    - bytes: those of the layers the view names;
    - RAM: each layer's `rows` times the share of its shots the view names, times `TXY_ROW_BYTES`;
    - TXY bytes: the fingerprint's sizes (entries are `[shot, size, mtime, "txy", layer]`, as `txy_cache` writes
      them);
    - info: the view's own, which `_cache_info` accepts with its `saved_at` and `signature`.
  - So `disk_cached` and `cache_info` in the listing are the view's: the badges, cache-first's local lane and
    offline browsing see the folder as cached after a restart.
- **Observation, not a finding:** no caller passes `wanted` yet, so listings show the most recently used view,
  whatever the tab's TXY source. That is usually the source the tab last loaded with. A folder whose only view is
  of another source shows as cached, and its load then reads the source. Wiring the tab's (source, tag) is for
  later, if Tony wants the badge per source.
- **Nothing is read from source folders.** `_view_infos`, `cached_matlab_shots`, `folder_views` and `read_view`
  read store tables only. A scan's mismatch rule still compares against the shots the listing found.
- **The scan's mismatch rule.**
  - store-v3: `cached_matlab_shots` reads the dataset row's fingerprint shots, as `_saved_fingerprint` did.
  - store-v4: the most recently used view's MATLAB-layer shots. A HeLab-only latest view gives none, so no
    mismatch, which is never a false one. Before this commit store-v4 found nothing at all.
  - Unreadable is no answer: `folder_views` gives `[]` on an error, and `read_view`'s error returns `_error`.
- **Adopt's `cache_info`:** `read_dataset_infos([path])`, the same answer a listing gives, the view's in store-v4.
- **The handoff's "left as is" list holds.** I checked every remaining reader of `datasets` in `helab/`:
  - the inventory's "Cached data" row (`inventory`) and the purge (`purge_cached`): store-v4's datasets are seeds,
    and its layers have their own rows and purges;
  - Make room and trim (`_room_plan`, `_free_space`): they have their layer groups;
  - file accounting (`_dataset_bytes`, the known-files union);
  - `cache_move`'s verify: it covers `txy_segments`;
  - `txy_cache.Access`: `row`, `confirm` and `touch` go to `datasets` only when `not self.layered`, or for a seed
    (`_seed_row`); `confirm_dataset` is called only when not layered.
- **Store-v3 unchanged.**
  - `read_dataset_infos`' SQL is the same, and `_view_infos` runs only for `layout >= store_v4.LAYOUT`.
  - `cached_matlab_shots` gives the dataset's fingerprint shots.
  - Adopt reads the same dataset through `read_dataset_infos`.
  - `test_offline_browsing.py` runs its restart with both stores.
- **Fails without it.** On an export of `4afa96a`, with `admin.py`, `scanning.py` and `cache_store.py` as they were
  at `768ac40`: `test_v4_listings.py` and `test_offline_browsing.py` give **6 failed** (the 4 new tests and 2
  offline-restart tests) and **54 passed**. Restored (compared with git): all pass.

### Checks (views)

On an export of `4afa96a`, whose `helab/` and `tests/` equal the floor's `HEAD` `1cffaba`:
- `pytest -n 4 --reruns 5 --reruns-delay 1 --basetemp=.ai/temp/pytest-assay` (the full suite, since stage 4 lands
  after this): **9144 passed, 674 skipped, 2 warnings, 3 failed, 15 rerun in 210.06 s.**
  - All 3 failures and all 15 RERUNs are the three git-provenance tests. The export has no `.git`, and each ran
    with 5 reruns.
  - In the floor checkout: **3 passed, no RERUN**.
  - No other RERUN.
  - The 2 warnings are the known pyqtgraph ones.
  - The totals match Vault's 9148 passed and 673 skipped, once the export's 3 and 1 are added back.
  - My first run had the test data linked inside an empty `testdata/` folder, so 17 test-data tests skipped. I
    fixed the link and reran; the figures above are from the second run.
- Touched tests: `test_v4_listings`, `test_offline_browsing`, `test_store_v4`, `test_cache_store`,
  `test_txy_loading` and `test_caching_v2_session`, with the same options: **164 passed, no RERUN**.
- `mypy helab/ --strict` (204 files), `mypy tests --strict` (200), `--platform win32`: no issues.
- `pyright helab tests` and `--pythonplatform Windows`: 0 errors.
- Scratch, not committed: SV-1 (`.ai/temp/assay/test_zz_views.py`).

## SV-1's fix (`48e3656`) and Q50.1 (a) (`ced04aa`)

**Open findings: 1 Medium (SQ-1).** SV-1 is fixed. (a) does what it says for loads, but it undoes Live's held-shot
rule for shots Live converted on read.

### SQ-1 · Medium · Under (a), Live reads a shot it converted on read again, and switches it to MATLAB's, once MATLAB's TXY appears

- `helab/io_ops/helab_txy.py:275` (`on_read`: `not over_matlab and shot in (matlab or {})` leaves the shot out,
  held or not).
- `helab/io_ops/live.py:199` (Live passes `matlab`, but not its held origins).
- `helab/utils/txy_sources.py:109-118` (`choose` keeps a held HeLab shot only while HeLab's TXY of it is there).
- **Scenario.** The switch is on, with HeLab priority and Live in the lab. MATLAB's autoconverter runs beside
  HeLab, its usual setup.
  1. A raw file settles. MATLAB's TXY isn't there yet, so Live converts the shot on read and holds it with origin
     `helab:<hash>`.
  2. Seconds later MATLAB's autoconverter writes `d_txy_forc<N>.txt`.
  3. On the next check, (a) leaves the shot out of `on_read`, so `choose`'s held rule finds no HeLab TXY to keep.
     MATLAB's wins.
  4. Live reads the shot again (`file_started`, a `shot` event) and its origin becomes MATLAB's.
  - So every shot is read twice, and the plots replace each one.
  - With a profile other than MATLAB's (a calibration, a user profile), the shot's data change, a few seconds after
    it appeared, from the HeLab conversion the user asked for to MATLAB's.
  - `choose`'s own docstring says the held rule is there so "a MATLAB TXY appearing for a shot HeLab filled doesn't
    stop Live". As built (and with `CONVERT_OVER_MATLAB = True`) the shot stays as it was held.
- **Fix.** Make `on_read` spare shots held from HeLab, as `could_take` does for MATLAB priority (`| set(held)`).
  - Live passes its `held_origins`, and the new filter skips a shot whose held origin is HeLab's.
  - A load has nothing held, so (a)'s rule stands for loads. A reload then takes MATLAB's for those shots, which is
    (a)'s rule; that is worth a line in Q50.1 for Tony.
  - Add a Live test: a held on-read shot, then MATLAB's TXY appears, then nothing is read again.
  - Or, if CoCo and Tony prefer Live to follow the load, record the switch as (a)'s known consequence in Q50.1.
- **How verified.** Scratch test (`.ai/temp/assay/test_zz_q50.py`, using `test_convert_on_read.py`'s `live`
  helpers). Live holds shot 1 from an on-read conversion (`origins={"1": helab:<hash>}`), and MATLAB's
  `d_txy_forc1.txt` is there, two checks apart.

  | Run | Shots read again | `file_started` | Origin after |
  |---|---|---|---|
  | export of `ced04aa` | [1] | 1 | MATLAB's (`{}`) |
  | `ced04aa`, `CONVERT_OVER_MATLAB = True` | none | 0 | held |
  | export of `ced04aa^` | none | 0 | held |

### Checked, no finding

- **SV-1: fixed.**
  - `_view_infos` parses each folder's view in its own `try` (`ValueError`, `IndexError`, `TypeError`,
    `KeyError`). A failure goes into `damaged`, and `read_dataset_infos` answers that folder alone with
    `_error("Saved view record is unreadable: …")`, even when it also has a seed.
  - My SV-1 scratch now gives a per-folder error. The listing goes on, with a `cache_warning` and its `entries`.
  - Without the fix, `test_v4_listings.py` has **1 failed**, the new test, which damages the view three ways.
- **(a) for loads.**
  - `on_read` leaves out a shot MATLAB's TXY has unless `converts_over_matlab(source)`: HeLab only always; HeLab
    priority only with the flag; MATLAB's sources never.
  - The source is normalised before (`requested_source` in loading and in Live).
  - **A settling or damaged raw file no longer hides a shot whose MATLAB TXY exists.** The new test keeps MATLAB's
    TXY of a fresh raw file and of an invalid one, and converts the raw-only shot. Under HeLab only the raw file
    still decides, by design.
- **The count matches the load.** `on_read_shots` is `raw` when the source converts over MATLAB's, else
  `raw - txy`, the shots with no TXY file. After a load it is the load's own `helab_on_read`.
  - MATLAB only now gives `raw - txy` instead of `raw`, but `converts_on_read` is False for it, so it stays 0.
  - The wording is unchanged, and it names the count.
- **Flipping `CONVERT_OVER_MATLAB` restores the as-built behaviour.**
  - `converts_over_matlab(HELAB_PRIORITY)` becomes True. The filter then never applies, and the count is `raw`, as
    before.
  - The commit's test checks this for loads with the flag on (all three converted). My Live scratch with the flag
    on behaves as `ced04aa^`.
- **Fails without it.** With `ced04aa`'s five `helab/` files as they were at its parent, `test_convert_on_read.py`
  gives **3 failed, 13 passed**: the sources' rule, the count, and the new settling or damaged test.

### Checks (SV-1 and (a))

On an export of `48e3656`, whose `helab/` and `tests/` equal the floor's `HEAD` `6b00cb0`:
- `pytest -n 4 --reruns 5 --reruns-delay 1 --basetemp=.ai/temp/pytest-assay` on the touched tests and Live's and
  loading's neighbours: **296 passed, no RERUN** (179 + 117). The files:
  - `test_convert_on_read`, `test_v4_listings`, `test_offline_browsing`, `test_txy_loading`, `test_txy_sources`,
    `test_live_convert` and `test_caching_v2_session`;
  - `test_live_check`, `test_live`, `test_live_io`, `test_live_testdata` and `test_folder_cache*`.
- `mypy helab/ --strict` (204 files), `mypy tests --strict` (200), `--platform win32`: no issues.
- `pyright helab tests` and `--pythonplatform Windows`: 0 errors.
- Scratch, not committed: SQ-1 (`.ai/temp/assay/test_zz_q50.py`).

## Re-check of SQ-1 (`9be3e12`)

**Open findings: none.** SQ-1 is fixed.

- **The fix.**
  - `helab_txy.on_read` takes `held` (shot → origin), and leaves out a shot MATLAB's TXY has only when it isn't
    held from HeLab's: a non-empty origin. Live holds MATLAB's shots with origin `""`, so those keep (a)'s rule.
  - Live passes `held_origins`, the same mapping it gives `could_take` and `compose`.
  - Loads pass nothing held, so (a) stands for loads.
  - A shot held from another HeLab profile is spared too, then converted with the current one. That is the
    as-built behaviour.
- **Its test**, `test_a_shot_live_converted_on_read_stays_helabs_when_matlabs_txy_of_it_appears`, is parametrized
  over the flag. With `helab_txy.py` and `live.py` as they were at `9be3e12^` (that is, `ced04aa`'s rule):
  - **flag off: failed**;
  - **flag on: passed**.

  Restored (compared with git): **2 passed**.
- My SQ-1 scratch (`.ai/temp/assay/test_zz_q50.py`) now reads nothing again, sends no `file_started`, and the
  shot stays held, as at `ced04aa^`.
- **Checks.** On an export of `9be3e12`, whose `helab/` and `tests/` equal the floor's `HEAD` `cca4691`:
  - `pytest -n 4 --reruns 5 --reruns-delay 1 --basetemp=.ai/temp/pytest-assay` on `test_convert_on_read`,
    `test_txy_loading`, `test_txy_sources`, `test_live_convert`, `test_live_check`, `test_live`, `test_live_io`,
    `test_live_testdata` and `test_caching_v2_session`: **193 passed, no RERUN.**
  - `mypy helab/ --strict` (204 files), `mypy tests --strict` (200), `--platform win32`: no issues.
  - `pyright helab tests` and `--pythonplatform Windows`: 0 errors.

Stage 4, through `9be3e12`, has no open review findings.

## `65ee050`: a load of another TXY choice says the folder is disk cached

**Open findings: none.**

- **The change** (`helab/io_ops/loading.py:813-818`). A store-v4 load whose own view was read and found absent
  (`had_dataset` False, not None) also says `disk_cached` when the folder has any view (`store.folder_views`).
  That matches what listings say (`read_dataset_infos` → `_view_infos`). `had_dataset`, and so the dataset info's
  "created" or "updated", is unchanged.
- **It can't claim "cached" for a folder with no usable data.**
  - A view outlives no layer. `_remove_txy_rows`, the only `DELETE FROM txy_layers`, deletes every view of each
    folder losing a layer, in the same transaction, and bumps its `txy:` epoch. Clear TXY data, the purges, Make
    room, trim and Clear root all go through it or delete views themselves.
  - `folder_views` answers `[]` on a read error, so an error never says "cached".
  - The read runs at the end of the load, in the helper, on a fresh snapshot, so a Clear that landed meanwhile is
    seen.
  - When the cache is unknown (`had_dataset` None: unreadable, no store, Don't cache) the field is still left out,
    as before. Quiet loads still say nothing.
  - Scratch test (`.ai/temp/assay/test_zz_dc.py`, on an export of `65ee050`): load, then `clear_txy` of the
    folder, then a load of another choice. **Views `[]`, `disk_cached: False`.**
- **The switch-off path is unchanged.** `other_view` needs `access.layered`, which is False in store-v3, so
  `disk_cached` there is `cached or bool(had_dataset)` as before. `folder_views` also returns `[]` below layout 4.
- **Fails without it.** With `loading.py` as it was at `65ee050^`, the new test
  `test_a_load_of_another_txy_choice_says_the_folder_is_disk_cached` **failed**. Restored (compared with git), it
  passes.
- **Checks.** On an export of `65ee050`, whose `helab/` equals the floor's `HEAD` `1485e6f` (the later merge
  changed only tests and CI):
  - `pytest -n 4 --reruns 5 --reruns-delay 1 --basetemp=.ai/temp/pytest-assay` on `test_v4_listings`,
    `test_txy_loading`, `test_folder_cache` (the CI's badge test), `test_offline_browsing`,
    `test_caching_v2_session` and `test_convert_on_read`: **144 passed, no RERUN.**
  - `mypy helab/ --strict` (204 files), `mypy tests --strict` (200), `--platform win32`: no issues.
  - `pyright helab tests` and `--pythonplatform Windows`: 0 errors.
