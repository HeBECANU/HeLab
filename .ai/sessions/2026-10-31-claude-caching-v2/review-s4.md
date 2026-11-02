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
