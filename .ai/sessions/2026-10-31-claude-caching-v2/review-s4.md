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
