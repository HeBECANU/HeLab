# Audit: what can make HeLab's GUI thread hang or stall (step 1 of the brief)

Auditor (Reviewer role), 2026-11-10, branch `agent/gui-threads-audit` at `23730f6`. Read-only on code: nothing in
`helab/` or `tests/` changed. The brief is `brief.md` in this folder.

## Re-review 2 (round 2 of the fixes)

Auditor, 2026-11-10. Only the fix diff was read: `git diff 9a7d16c..8a9f32e`, my own `c06e3fc` skipped. That is
Bolt's ten commits (Tony's Q~1 – Q~5, and GT-24 – GT-28) and `handoff.md`'s "Round 2".

- **Open findings: none.**
- **No new hang or bug found.**
- Every round-1 re-review finding is closed, apart from GT-29 (Info), which is left by agreement. GT-30 is in the
  handoff's doc proposals.

### Checks, rerun here at `8a9f32e`

- **Full suite:** `pytest -n 4 --reruns 5 --reruns-delay 1 --basetemp=.ai/temp/pytest-review` gave **9907 passed,
  674 skipped, no RERUN** (207 s; `.ai/temp/rereview2/suite.txt`).
- **Type checks:** all five clean: mypy strict (244 files), mypy tests (242), pyright, and both win32 runs
  (`.ai/temp/rereview2/types.txt`).
- **Without the fix, the new tests fail** (`mutants.py`, now with `gt24`, `gt25` and `gt26`; the baseline passes):

  | Mutant | Fix undone | What fails |
  |---|---|---|
  | `gt24` | CacheTab sees no delivery | `test_the_budget_question_waits_for_the_delivery_with_the_real_box` |
  | `gt25` | `FolderCache._on_event` unmarked | `test_every_helper_event_through_folder_cache_is_a_delivery` |
  | `gt26` | the old iteration over the dict | `test_forgetting_a_folders_digests_survives_a_digest_added_meanwhile` |

- **GT-27 and the packaged app:**
  - `.github/workflows/ci-build.yml` changes by one line: the probe check's expected kinds, now
    `["ready", "done", "reads"]`. Nothing else in the workflow changed.
  - I built the app (`pyinstaller HeLab.spec --clean -y`, macOS) and ran that step's script on it. Exit 0; events
    `ready` (offscreen), `done` (`loaded: true`), and `reads` (the folder's one file); `seen: {"frozen": true, "gui": false}`.
  - The build and dist folders were removed afterwards.
  - Windows and Linux runs are CI's.
- **Q~1: "every bin draws exactly as before", checked.** `experiments/rereview2/test_every_bin_same.py` draws six
  cases with `9a7d16c`'s code (before Draw at) and with the new code at Draw at = every bin, and
  `compare_every_bin.py` compares them:
  - the cases: wide 5,000 × 10 XY, automatic bins on all planes, 3,000 × 2,500 XT, log-scale YT, density dots, and
    one-colour dots;
  - in each library: PyQtGraph's image arrays, autoDownsample, labels, dot positions and brushes; Plotly's whole
    figure JSON; Matplotlib's collection arrays, coordinates, offsets, titles and kinds;
  - result: **101 arrays compared, 0 differ**. A control against the new default (screen resolution) differs in
    50, so the comparison would see a change.

### Status of each item

| Item | Status | What I checked |
|---|---|---|
| Q~5 (GT-1 (a)), `ce78608` | **Closed**: a conversion's end opens no box at all | `_quiet_large` is set only by `ask_large=False` (`_passed`) and cleared by the user's next explicit load. It also covers the helper's too-large stop. Live and presets still ask, outside the delivery (round 1). |
| Q~4 (GT-9's dialogs), `5d58875` | **Closed** for Load Scripts…, the temp folder's Browse… and the cache's Change… | Each uses `folder_dialog.choose_folder` (`DontUseNativeDialog`, from home). The converter's import/export, Save to folder… and Debug's save stay native, and the allow-list names each as still open. Whether Qt's own dialog stays quick beside a dead mapped drive is M~2's to confirm on a lab PC. |
| Q~3 (GT-8), `121577c` | **Closed** (Quit on both boxes); A~8's timeout rightly deferred, as reasoned | See the first table below. |
| Q~2 (GT-6, at start), `2eadccc` | **Closed** | A passed probe's `seconds` over 2 s leaves the folder for Reload, and its reads are dropped. The rest of GT-6 (the import's own reads at Reload) stays A~1. |
| Q~1 (GT-4), `684b027` | **Closed** at the default; "every bin" is unchanged, by design and as checked above | See the first table below. |
| GT-24 (Medium), `012b52a` | **Closed** | See the second table below. |
| GT-25 (Low), `0cf3c32` | **Closed** | See the second table below. |
| GT-26 (Low), `385dd97` | **Closed** | `list(_READ_DIGESTS)` is one C call. |
| GT-27 (Low), `b827da4` | **Closed** | See the second table below. |
| GT-28 (Low), `c1399fb` | **Closed** | An empty or blank path launches nothing. |
| GT-29 (Info) | Left, agreed | Cosmetic. |
| GT-30 (Info) | In the handoff's doc proposals | Keeping exit code 1 and the "previous run crashed" line is reasonable. |

The two largest items in detail:

| Item | What I checked |
|---|---|
| Q~3 | **The wait:** `cache_locks.startup` holds nothing while it waits, so `SystemExit` there is safe. |
| Q~3 | **Quit during the recovery:** it cancels the helper and leaves the record. If the reaper's kill lost the race with the exit, the orphaned helper still holds `move.lock`, so the next start waits, now with Quit. |
| Q~3 | **A box closed because its wait ended:** it blocks its signals first, so it isn't taken for a Quit. |
| Q~1 | **The drawn image:** `block_mean` and `block_edges` are right for a last block smaller than the rest. The bins are regular (`np.histogram2d` with a count and a range), so `imshow` places cells as `pcolormesh` did. The colour bar's top follows the drawn image. |
| Q~1 | **The disk cache:** 2D histograms aren't saved there (`cache_supported` is the default False), so `display` needs no codec type. |

The round-1 re-review's findings in detail:

| Item | What I checked |
|---|---|
| GT-24 | `asks` matches exactly the two `_on_done` branches that ask; every other end stays synchronous. The deferred re-call re-checks the tab and its cache, and the job has ended, so nothing waits. |
| GT-25 | The mark also covers IOService's synchronous `queued` and `cancelled` emits from clicks. That only defers there, and only makes guard 2 stricter. The two harness changes (`processEvents`, `waitUntil`) take the turn the app now takes; nothing is weakened. |
| GT-27 | `done` comes first, then `reads`. FolderProbes takes `reads` only after `done`, and again at the probe's exit (`_finished` → `_read`). A slow `reads` only delays the exit (PROBE_EXIT_SECONDS) and passes without reads. |

### Info (new)

- **GT-31** (GT-27): on a slow share, the probe's stats after `done` can take longer than `PROBE_EXIT_SECONDS`.
  The probe is then ended with the warning "finished but its process didn't exit within N s". That is true but
  misleading now that the process is busy with the reads. It still passes, so this is cosmetic. Rewording that
  warning when `done` came but `reads` didn't would make it exact.

## Re-review of the fixes (step 3)

Auditor, 2026-11-10. Only the fix diff was read: `git diff 74d29f9..9a7d16c` (Bolt's 13 commits, `handoff.md`).

- **Open: GT-24 (Medium, new).** A modal question still opens inside a helper's delivery, on a path neither the
  audit nor the fix listed.
- **Open, Low (new):** GT-25 (guard 2 sees less than it seems to), GT-26 and GT-27 (from GT-6 (B)'s fix), GT-28
  (from GT-9's fix).
- **Info (new):** GT-29, GT-30.
- **Everything else** in the fix diff is closed, or rightly deferred to a question for Tony or a later item.
- **No fix adds a hang.**

### Checks, rerun here at `9a7d16c`

- **Full suite:** `pytest -n 4 --reruns 5 --reruns-delay 1 --basetemp=.ai/temp/pytest-review` gave **9878 passed,
  674 skipped, no RERUN** (197 s; output in `.ai/temp/rereview/suite.txt`).
- **Type checks:** all five clean: `mypy helab/ --strict` (244 files), `mypy tests --strict` (240),
  `pyright helab tests`, and the two win32 runs (`.ai/temp/rereview/types.txt`).
- **"Fails without the fix", checked by undoing each fix in memory** (`mutants.py`, a pytest plugin; the checkout
  is untouched):

  | Mutant | Fix undone | Result |
  |---|---|---|
  | `gt1` | `outside()` runs its function at once | 8 of 10 in `test_modal_outside_delivery.py` fail, as claimed |
  | `gt5` | the old per-child re-derive | both tests in `test_cache_removed_derive.py` fail |
  | `gt6` | a probe's reads never fresh | `test_fresh_reads_spare_the_gui_threads_reads…` fails |
  | `gt10` | the old walk per tab | `test_a_fit_finds_the_areas_docks_once…` fails |
  | none | (baseline) | 56 passed |

- **GT-2 and GT-3 against the pre-fix `helab/`** (`git archive 74d29f9`):
  - GT-2: the new test's blocked-stderr child timed out at 30 s on the old code, and exits 7 in 1.3 s on the new.
  - GT-3: the held-write child crashes on the old tee (it has no file queue); my step-1 run measured 3.008 s there.
    It takes 0.000 s on the new code.
- **A sweep with FolderCache's dispatcher marked as a delivery** (`GT_MUTANT=fcmark`, full suite). Guard 2 then also
  sees helper events that tests emit themselves:
  - result: 2 failed, 9883 passed;
  - both failures are `test_root_gui.py::test_a_save_that_fails_says_why_and_can_be_tried_again`, whose warning is
    now rightly deferred (it asserts it at once);
  - no other box was found, but tests stub most confirm hooks (GT-25).
- **Existing tests:** only adapted, none weakened.
  - `test_cache_switch`'s Windows half moved to a new test that runs on every OS.
  - `test_accessible_names`' walk runs a pending dock fit first, as the debounced design means.
  - The others take the new arguments, or check through `file_manager` instead of `openUrl`.

### Status of each finding

| Finding | Status | Note |
|---|---|---|
| GT-1 (High) | **Closed** for (a)–(e) (`41c4b39`); the class stays open through GT-24 | See the first table below |
| GT-2 (High) | **Closed** (`531d35e`) | See the first table below |
| GT-3 (Medium) | **Closed** (`e5aaa9a`) | See the first table below; cosmetic leftovers in GT-29 |
| GT-4 (Medium) | Rightly deferred (Q~1) | Every remedy changes the picture |
| GT-5 (Medium) | **Closed** (`63d1d5f`) | See the second table below |
| GT-6 (Medium) | **Partly closed** (`c2b1d5b`, option (B)); the rest deferred (A~1, Q~2) | See the second table below |
| GT-7 (Medium) | (a) **closed** (`8db0b2a`); (b) rightly deferred (A~2, M~1) | See the second table below |
| GT-8 (Medium) | Rightly deferred (Q~3, A~8) | A Quit button is visible to users |
| GT-9 (Medium) | `openUrl` **closed** (`542376d`); dialogs deferred (Q~4) | See the second table below |
| GT-10 (Low) | **Closed** (`762d56c`) | See the second table below |
| GT-11, GT-12, GT-13, GT-15 (Low) | Deferred (A~3 – A~6) | Fine for Low |
| GT-14 (Low) | **Closed** (`bbc2eea`) | See the second table below |
| GT-17 (Info) / guard 4 | **Closed** (`bf490d1`, `13cc77c`) | See the second table below |
| GT-16, GT-18 – GT-23 (Info) | Unchanged | |
| Guard 1 (`e8121a1`) | Done, honest | See the second table below |
| Guard 2 (`41c4b39`) | Done; narrower than the audit said | GT-25 |
| Guard 3 | Deferred (A~7) | |

The three High and Medium closures, and what I checked in each:

| Finding | What I checked |
|---|---|
| GT-1 | **Deferral:** `delivering("io")` wraps all of `_tick`, so `_dispatch`, `_apply_pauses` and every emit are inside. `outside()` uses `singleShot(0)`, never inside the tick, and each deferred function re-checks its object (closed window, `sip.isdeleted`, CacheMover's `running`/`moving`/`_cancelled`). |
| GT-1 | **Order:** the cache move's `move_check` now runs after that tick's later events. The check's `done` doesn't end the mover, and `_checked` returns if the move ended, so nothing is lost. |
| GT-1 | **The large-folder question:** asked once per folder. It is dropped after a Cancel or a change of selection, and re-asked through `queue_load` outside any delivery. |
| GT-2 | **(a):** the note thread is joined at most `NOTE_SECONDS`, then `os._exit`. |
| GT-2 | **(b):** `crash_file.exit_after` arms faulthandler's C timer at GRACE + NOTE + 2 = 4 s. Only `main` calls it; its tests run in child processes, so pytest's own `faulthandler_timeout` timer is never replaced. `end()` keeps the armed file open. |
| GT-3 | **The tee:** the pump only `put_nowait`s, so it never waits on the file. The writer keeps chunk order. `stop` waits at most 2 s each for the queue, the writer and the lock. |
| GT-3 | **The log:** the file's handler is now first. The watchdog's lines go through `log_within`, joined 1 s; at most 3 lingering threads per 30 s while a handler stays blocked. |

The rest:

| Finding | What I checked |
|---|---|
| GT-5 | `_rederive` is equivalent to the old walk: deepest first, so each folder is derived after all its descendants, each once. Only touched folders, and ancestors whose status changed, are marked changed. `one_activity` nests and emits once, even on an exception. |
| GT-6 | Option (B) spares the listing, `isdir`, the stats and the hash reads. A script's hash is now the hash of the very bytes its import ran (`_READ_DIGESTS`), which is better. **Still on the GUI thread:** the import's own open and read of each script and helper file (A~1), and `isfile` of helpers known only from earlier sessions. New issues in GT-26 and GT-27. |
| GT-7 | (a): only the cache folder's own drive is asked, with `GetDriveTypeW`; a UNC path counts as remote. |
| GT-9 | No local `openUrl` is left (the bundled manual's `file://` and web pages stay). Edge case in GT-28. |
| GT-10 | The direct-children lookup is safe: HeLab never sets `GroupedDragging`, so docks stay children of the area. |
| GT-14 | The deferred SIGTERM close, and the checks after Settings' and Restore's `exec()`. |
| GT-17 / guard 4 | `timed_hook` wraps render, update, draw and every `_hook`, and logs even when the hook raises. |
| Guard 1 | Scope: `helab/views` and `helab/models`, direct calls only, as its docstring says. Each of the 15 entries names its finding and whether that is still open. Stale entries fail. |

### GT-24 · Medium · new · Settings › Cache's "Lower the disk cache budget?" opens inside a helper's delivery

- **Where:** `helab/views/CacheTab.py:640-690` `_on_done` is connected to `FolderCache.cacheAdminDone`. That signal
  is emitted in `FolderCache._on_admin_event` (`folder_cache.py:4170`), inside `IOService._tick` → `resultReady` →
  `_on_event`. From `_on_done`:
  - `:659`: store-v4's trim plan has arrived;
  - `:675`: the helper found more cached than the tab saw (`recorded: False`).
  - Both call `_ask_trim` → `self.confirm` → `_confirm` → `box.exec()` (`:611`).
- **Effect:** GT-1's, for as long as the box is open. The user started it (Save in Settings, which closes as it
  saves), so the box appears a moment later, on its own. While it is open no helper's events flow, then there is a
  burst of false timeouts.
- **Confirmed** by `experiments/rereview/test_gt24_budget_box.py`. It keeps CacheTab's real `_confirm` and delivers
  the budget job's answer inside `gui_delivery.delivering("io")`, as `_tick` does. Guard 2 then records
  `QMessageBox.exec while delivering 'io'` with `_ask_trim` on the stack.
- **Why it was missed:** the tests stub `tab.confirm` and emit `resultReady` themselves (GT-25).
- **Fix:** run `_on_done`'s two questions through `gui_delivery.outside`. The budget job is already done, so nothing
  waits on the answer. Add a test that keeps the real `_confirm`.

### GT-25 · Low · new · Guard 2 sees only deliveries that go through `IOService._tick`, and tests mostly don't

- **Delivery:** most GUI tests deliver helper events by emitting `service.resultReady` themselves (for example
  `test_cache_tab.finish`), not through `_tick`, so `gui_delivery.current()` is None and guard 2 checks nothing.
- **Stubs:** many tests also replace the hook that would open the box: `CacheTab.confirm`,
  `FolderExplorer.confirm_large`, `report_flag_failure`, `FolderInfoWindow.ask_clear`, `RootDuplicatesWindow.choose_keep`.
- **Effect:** the audit's claim that guard 2 "would have caught GT-1 (b)–(e) in their existing tests" was too
  strong. It catches a box only in the tests written for it (`test_modal_outside_delivery.py`). GT-24 passed the
  whole suite.
- **Fix, cheap:**
  - Mark `FolderCache._on_event` as a delivery too, beside `_tick`. Every helper event goes through it, so tests
    that emit directly are covered. The `fcmark` sweep shows it costs 2 tests a `waitUntil`.
  - Keep the real confirm in one test per result-driven question.

### GT-26 · Low · new (GT-6 (B)) · `_READ_DIGESTS` is iterated on the GUI thread while the worker may write it

- **Where:** `scripts_manager.load_directory`'s
  `for path in [path for path in _READ_DIGESTS if _inside(...)]`.
- **The race:** `_SourceOnlyLoader.get_code` adds to the dict on whichever thread imports. A Reload waits only for
  runs of the reloaded folders' scripts (`script_tree._busy`), so another folder's `compute` importing a helper
  lazily can add a key mid-iteration.
- **Effect:** `RuntimeError: dictionary changed size during iteration`. That folder's Reload then fails ("Error
  loading scripts", logged).
- **Likelihood:** rare (it needs a lazy import of a helper during the Reload).
- **Confirmed** by reading.
- **Fix:** iterate a snapshot (`list(_READ_DIGESTS)`, one C call under the GIL) or take a lock.

### GT-27 · Low · new (GT-6 (B)) · The probe's reads count against its 10 s import limit

- **Where:** `helab/scripts/probe.py` takes `manager.folder_reads(folder)` (a listing, a stat per file, a hash for
  any file without a digest) *before* it says `done`. `FolderProbes` kills a probe whose `done` is not in by
  `PROBE_SECONDS` after `ready` (`script_tree.py:340`).
- **Effect:** a folder on a slow share whose import took close to 10 s can now fail its test import, with the
  message "its import didn't finish within 10 s", though the import did finish. The extra cost is about one stat
  per file, nothing on a local disk.
- **Confirmed** by reading.
- **Fix:** say `done` first and the reads in a following line, used if they come within a short wait. Or skip the
  reads when the limit is near.

### GT-28 · Low · new (GT-9, Windows) · `file_manager.show("")` opens Explorer at HeLab's working folder

- **Where:** `open_command` passes `os.path.normpath(path)`, and `normpath("")` is `"."`.
- **Effect:** Settings › Cache's Open, with the disk cache off (`store_options()` is `{}`, so the path is `""`), and
  Settings' temp and cache Open buttons with an empty field, open the current folder instead of nothing.
  `openUrl("")` did nothing.
- **Fix:** `show` returns False for an empty path.

### Info

- **GT-29** (GT-3): the console tee's `lost` counter is added to by both pumps without a lock, so a count can be off.
  The note "N bytes … lost around here" is written before the queued backlog, though the lost bytes came after it.
  Both cosmetic.
- **GT-30** (GT-2): a teardown ended by `exit_after` exits with code 1 and writes the stacks to the crash file. The
  next start then says "The previous run crashed: see crash-<pid>.txt". That is truthful, and the doc change
  should say so.

## Summary

| Severity | Count | Findings |
|---|---|---|
| High | 2 | GT-1 (a modal box inside a helper result stops all helper I/O), GT-2 (quit's last resort can't end the process) |
| Medium | 7 | GT-3 logging, GT-4 2D histogram drawing, GT-5 cache-removed slot, GT-6 script folder reloads, GT-7 mount tables (Windows), GT-8 startup waits, GT-9 native dialogs and `openUrl` |
| Low | 6 | GT-10 – GT-15 |
| Info | 8 | GT-16 – GT-23 |

Nothing found makes the GUI thread wait on a lock, a thread or a helper. The rule ("never let the GUI thread
wait on cancellation, deadlines or a helper") holds where it's checked: no `join`, `wait`, `communicate`, future or
`BlockingQueuedConnection` on a GUI path, and all helper work goes through IOService's reader threads.

What does go wrong:

- **Nested event loops opened inside result handlers.** A box opened that way blocks IOService's own timer, so
  every helper's events stop while the GUI stays responsive (GT-1).
- **Output to a console or pipe** that may not drain (GT-2, GT-3).
- **CPU work that grows with data and has no display cap** (GT-4, GT-5, GT-10 – GT-12).
- **File-system and shell calls on the GUI thread** for things the user chose: script folders, file dialogs, and
  on Windows the mount table (GT-6, GT-7, GT-9).

**The overnight 5.68 s stall** (TDC PC, 2026-11-09) is still unexplained. This audit narrows its candidates for an
idle Live on Windows (GT-23).

### How it was checked

- **Static inventory.** `inventory.py` is an AST scan of `helab/` for calls that can block, with the function that
  holds each. It found 597 hits outside helper-only modules (`inventory.tsv`). Reachability from the GUI thread was
  traced by hand and with grep.
- **Four readers.** I took the runtime core: logging, the console tee, the watchdog, IOService, FolderCache's
  dispatch, startup and quit. Three helpers each read one area: plots/analysis/scripts, the explorer/model/Live,
  and the main window/settings/updates. Every High and Medium finding below was re-checked by me in the code. GT-1
  and GT-2 were also re-run by me.
- **Dynamic checks.**
  - `stall_probe.py` is a pytest plugin. It samples the GUI thread's stack whenever the event loop misses beats for
    0.3 s *while HeLab code runs under it*; `test_probe_sanity.py` shows it catches a 0.8 s slot. The full suite ran
    under it: `pytest -p stall_probe -n 4 --reruns 5 --reruns-delay 1` gave **9838 passed, 674 skipped, no RERUN**
    in 196 s, output in `.ai/temp/gt-suite-probe.txt`, summarised by `aggregate.py`.
  - Targeted scripts confirmed the mechanisms: `modal_in_result_check.py`, `quit_watch_check.py`,
    `tee_block_check.py` and `dock_fit_scaling.py`, plus the helpers' timing scripts in `experiments/`.
  - Synthetic data only, offscreen, on this Mac (Apple Silicon). No Windows run was possible: GT-7 and GT-9 need
    one (proposed checks at the end).
- **What the suite shows, and what it can't.** The test data is small, so the suite finds only structural stalls.
  It found one over 0.4 s (GT-10). The rest were about 0.3 s first shows of a plot's widget under `-n 4` load
  (GT-20). Data-sized costs come from the timing scripts.

## Findings

### GT-1 · High · A modal box opened inside a helper's result stops every helper's I/O until it is answered

- **Where:** `helab/utils/io_service.py:1091` `_tick` (the 20 ms timer) → `:1138` `resultReady.emit` → a slot →
  `exec()`.
  - Qt never delivers a timer's next timeout while its slot is still running. So while the box's nested loop
    runs, `_tick` doesn't. Nothing drains `messages`, no slot frees, nothing dispatches and no timeout is checked,
    for every helper.
  - The GUI itself keeps painting and taking input.
- **Reachable boxes:**
  - **(a) Unattended.** A finished folder conversion leads to the large-folder question:
    - `FolderExplorer._io_event` (`FolderExplorer.py:1377`) → `explorer_convert.ExplorerConverter.event` → `_passed`
      (`explorer_convert.py:623`) → `explorer.queue_load` (`:635`)
    - → `load_to_ram_cache(explicit=True)` (`FolderExplorer.py:1323`) → `_large_blocked` (`:930`, `:1068`) →
      `_confirm_large` (`:1105`) → `LargeFolderDialog.confirm_large` → `.exec()` (`LargeFolderDialog.py:46`).
    - So a "Convert this folder…" that ends minutes later on a large folder opens the box with nobody there. Live,
      loads, saves and the quit window's pending saves then all stop until someone clicks.
  - **(b)** A flag or constants save that failed: `FolderCache._on_admin_event` → `_prefs_not_saved` /
    `_constants_not_saved` (`folder_cache.py:4151-4163`) → `QMessageBox.warning` (`FolderExplorer.py:2593`,
    `:2662`). `report_flag_failure` is set only by tests, so in the app this always opens the box.
  - **(c) Help › Record I/O trace:** `_on_trace_check` (`HelabMainWindow.py:1195`) →
    `QMessageBox.information` (`:1212`), `_refuse_io_trace` → `QMessageBox.warning` (`:1225`),
    `_ask_delete_old_traces` → `box.exec()` (`:1236`).
  - **(d) The cache move:** `CacheMover._event` (`CacheMover.py:148`) → `_confirm` → `QMessageBox.question`
    (`:375`), and `report` → `box.exec()` (`:388`, from `:187` and `:371`).
  - **(e) Save to folder… for a `.helab-root`:** `ManualMarkerDialog._result` → `QMessageBox.warning`
    (`DataRootDialogs.py:233`, `:235`).
- **Afterwards:**
  - Reader threads stop at the queue's 256 messages (`_put` retries every 0.1 s).
  - Each `_tick` then handles at most 64 events or 8 ms before it checks timeouts. A helper whose heartbeats are
    still queued looks silent for as long as the box was open, so it is retired as timed out and retried: the
    file limits are 15/20/30 s, 60 s otherwise.
  - Expect a burst of false I/O timeouts after a box left open longer than about 15 s. This follows from the
    reading; it wasn't run.
- **Confirmed:**
  - The chains by reading.
  - The stop by `modal_in_result_check.py`, on a real `IOService`: another request's heartbeats delivered during a
    1 s nested loop were **0** when the loop ran inside the `resultReady` slot, and **42** when it was opened with
    `QTimer.singleShot(0)`. The helper's `experiments/main/timer_reentry.py` shows the Qt rule itself.
- **Fix:**
  - Never `exec()` from an I/O event. Use `box.open()` with `finished`, or defer the question with
    `QTimer.singleShot(0, …)`. `ManualMarkerDialog._ask_replace`, `CacheDialogs`, `RootDuplicatesWindow`,
    DataRootsTab's alerts and `_offer_raw_removal` already do this.
  - For (a), the large-folder question after a conversion should also not be modal at all: show the existing
    "Load anyway…" state.
  - Guard: see "A guard that keeps it so", (2).

### GT-2 · High · quit's last resort (`quit_watch.exit_soon`) can fail, leaving a windowless HeLab that holds `running.lock`

- **Where:** `helab/views/quit_watch.py:38-47`. The watch thread logs a warning and flushes every handler, and only
  then calls `os._exit`.
- **(a) A stderr that takes nothing.**
  - `main` registers `console.stop` with `atexit`. After the event loop ends it points fd 2 back at the real
    terminal (`console_tee.py:194-196`).
  - If that terminal takes nothing (a PowerShell window paused by a selection, the TDC case), the watch thread's
    `logging.warning` blocks in coloredlogs' stream handler and `exit` is never reached.
  - **Confirmed** by `quit_watch_check.py`: a child whose fd 2 is a full pipe was still running 20 s after
    `exit_soon(7, 0.2)`, and was killed. The control run with the pipe drained ended in 0.26 s with exit code 7.
    The first, untimed run hung until killed by hand.
- **(b) Interpreter finalization.**
  - After `sys.exit` and atexit, Python's finalization stops daemon threads at their next GIL take. A destructor
    that blocks in the final collection or module teardown (a PyQt or QtWebEngine object) outlives the watch.
  - **Confirmed** by the helper's `experiments/main/fin2.py`: a 3 s `__del__` kept the process 3.03 s with a 1 s
    watch. With `faulthandler.dump_traceback_later(1.0, exit=True)` (`fin3.py`) it ended at 1.02 s.
- **Effect:** the process never ends. It holds `running.lock`, so the next start says "HeLab is already running".
  This is the known issue quit_watch was written to close.
- **Fix:**
  - Arm `faulthandler.dump_traceback_later(GRACE + 1, exit=True, file=<the crash file>)` just before `sys.exit`.
    Its C thread survives finalization.
  - In the watch, `os._exit` first, or write the note with `os.write` to the log file's descriptor (never through
    logging's handlers), then exit.

### GT-3 · Medium · Every log line goes first to the console pipe, whose pump writes the console file synchronously; a held write makes every thread's logging wait, and hides the stall from the log

- **Where:**
  - `main.py:65` `coloredlogs.install(level=DEBUG)` adds the root logger's first handler, a stderr stream handler.
    The log file's handler is added after it (`app_log.py:102`).
  - With the console tee on, stderr is a pipe: 64 KiB on macOS, a few KiB by default on Windows (`os.pipe` →
    `CreatePipe(…, 0)`).
  - Its pump (`console_tee.py:151-163`) writes each chunk to `console-<pid>.txt` before reading the next.
- **Scenario:** that file write is held: a busy disk, an antivirus scan of the 20 MB file at rotation, a full
  disk's slow path. The pipe fills, and every `logging` call on every thread then waits in its `write`:
  - the GUI thread's;
  - the analysis worker's milestones (helper's GP-10);
  - **the watchdog's own stall line and stacks** (`gui_watchdog.py:80-82`).
  - Because the stream handler comes first, the record doesn't reach the log file either until the pipe drains.
    A stall caused this way leaves no line at all.
- **Confirmed** by `tee_block_check.py`: with the pump's file write held 3 s once, the slowest of 2,000 log calls
  on the main thread took **3.008 s**, after 65,600 bytes. The same run without the hold took 0.000 s.
- **Not a deadlock:** blocked `write`s release the GIL, and since `96df3ed` the terminal never holds the pump. But
  the wait has no bound.
- **Fix:**
  - Put the file handler first, or give the watchdog a handler of its own on the log file.
  - Send the console handler through a `QueueHandler`/`QueueListener` that drops when full.
  - In the tee, write the file from its own thread with a bounded queue, as `_Terminal` already does for the
    terminal.
  - Separately, the root logger at DEBUG formats every debug record for the console. That costs little today: the
    debug calls found are not in hot paths.

### GT-4 · Medium · Basic plots v2's 2D histograms draw data-sized images, dots and figures on the GUI thread with no display cap

- **Where:**
  - `helab/scripts/standard_v2/histograms_2d.py:925-945` `fill`, run by `update`/`draw` on the GUI thread:
    `AnalysisRunner.finished` → `AnalysisInstance._finished` (`views/plots/instance.py:703`) → `_updated`/`_draw`.
  - Bins can be set to 20,000 a side (Q72.1), which is 400M cells a plane, and up to 3 planes; dots up to
    `MAX_DOTS` (5M).
  - It runs again on every Live update, rerun, library switch and, for Matplotlib, every resize, pan or zoom.
- **Measured** by the helper, `experiments/plots/` (offscreen, this Mac):

  | Part | Where | Measured | Extrapolated |
  |---|---|---|---|
  | (a) PyQtGraph image: `colour_positions` and `setImage`, coloured at the next paint | `:479`, `:939` | 0.64 s a plane at 8000² | about 4 s a plane at 20000² (about 12 s for XY+XT+YT), with GBs of float64 temporaries on the GUI thread |
  | (b) PyQtGraph dots: `ScatterPlotItem.setData` with one `QBrush` per dot (`dot_brushes`) | `:920`, `:937` | 0.26 s for 200k (the default); 1.2 s for 1M; 6.0 s for 5M, per plane | |
  | (c) Matplotlib `pcolormesh` and dots, drawn by `MatplotlibPane.redraw` | `:1128-1135` | `pcolormesh` 2000²: 0.47 s a draw; 4000²: 1.86 s a draw; 5M dots: 6.1 s a draw | the mesh alone is about 6.4 GB at 20000² |
  | (d) Plotly `go.Heatmap(z=…, customdata=…)` | `:1015` | figure built on the GUI thread: 0.12 s at 4000²; serialised on Dash's thread with `json` (no orjson): 1.6 s, 431 MB, holding the GIL up to 477 ms at a time | at 20000², GBs of JSON |

- `estimated_bytes` warns about memory only, not this time.
- **Fix:**
  - Decimate in `compute` (the worker) to display resolution: for example ≤ 2048 a side for images, ≤ 1000–2000
    for Plotly. Move the colour indices to the worker. Turn on `ImageItem(autoDownsample=True)`.
  - Group dots by colour (≤ 64 items, one brush each) and cap PyQtGraph and Matplotlib dots lower.
  - Use `imshow` rather than `pcolormesh` for the regular bins.
  - What the user sees changes, so this is a question for Tony (`Q~1` below).

### GT-5 · Medium · Removing saved status re-derives the parent once per child: O(n²) in one slot (17.5 s at 8,000 subfolders)

- **Where:** `helab/models/SnapshotFileSystemModel.py:1017-1036` `_cache_removed`.
  - For each node, `_update_ancestors` (`:319`) → `_derive(parent)` iterates all of the parent's children.
  - Each node's `changed()` (`:623`) emits `activityChanged`, which rebuilds the tab's whole summary
    (`FolderExplorer._update_activity`).
- **Path:** a `removed` helper event → `FolderCache.removed` (`folder_cache.py:4031`, `:4256`; `:4214` for deleting
  or reassigning a `.helab-root`) → `cacheRemoved` → `_cache_removed`, one slot. Settings › Cache's Clear passes
  `paths=None`: every node.
- **Measured** by the helper (`experiments/explorer/test_gt_derive.py`, with a frozen IOService): 0.68 s at 2,000
  subfolders and 17.5 s at 8,000, so about 2 min at 20,000. Re-checked by me by reading.
- **Fix:** collect the touched parents, derive each once after the loop, and emit `activityChanged` once.

### GT-6 · Medium (High while a share drops) · Reloading a script folder reads it and imports it on the GUI thread

- **Where:**
  - `views/plots/script_tree.py` `_load_folder` → `ScriptsManager.add_folder` (`scripts_manager.py:354`, `:375`,
    `:459`): `isdir`, `listdir`, `analysis/identity.py:30` `file_hash`, and `exec_module` (stat/open/read of each
    script and helper).
  - Then `_stamp_of` (`script_tree.py:751`, `:763`, `:1013`): a `listdir` and a `stat` per file.
- **Scenarios:**
  - Only the start skips network folders (`restore_folders`, `:647`). Reload, Load Scripts… and the folder menu's
    Reload of a share do all of the above on the GUI thread.
  - The test import in its own process (Q49.3 (b)) only shows the share answered moments earlier. A slow share at
    50–200 ms an operation makes about 15 s for 30 files. One that drops between the test and the import blocks
    for the redirector's timeout: 30–60 s, unbounded on a hard mount.
  - **(GP-6)** A local folder whose import legitimately takes up to `PROBE_SECONDS` (10 s, `script_tree.py:63`)
    passes the test and then blocks the GUI thread about as long, at every start and Reload.
- **Confirmed** by reading (helper and me). The remaining part is already in known-issues ("A user script that
  blocks only in HeLab's own process…").
- **Fix:**
  - Have the probe process return each file's bytes, hash and stat, and compile and exec from memory on the GUI
    thread.
  - Record the probe's import time; above 1–2 s, don't import at start and say why (`Q~2`).

### GT-7 · Medium (Windows, unconfirmed there) · Mount tables are read on the GUI thread: at import, and every 100 ms while a folder with raw files is shown

- **(a) At import.**
  - `cache_location._filesystem` (`cache_location.py:48`) calls `psutil.disk_partitions(all=True)`, from
    `constants.refuse_unsafe_cache_dir` (`constants.py:420`, `:468`) at import (`resolve_cache_dir`, `:486`), and
    again in `main._start_cache` → `recover` → `start_cache_dir`.
  - On Windows, `all=True` calls `GetVolumeInformationW` on every drive, remote ones too, before the window exists.
- **(b) While browsing.**
  - The Folder details refresh (`central_placeholder_timer` → `_update_folder_details`, `HelabMainWindow.py:1748-1749`) and every `loadStateChanged` →
    `FolderDetailsPanel.show_explorer` → `converter.row` (`FolderDetailsPanel.py:236`) →
    `ExplorerConverter.offered` → `share_of` (`explorer_convert.py:373`) → `mount_table` → `current_mounts` →
    `_windows_mounts` (`cache_paths.py:53-70`: `GetDriveTypeW` per letter, `WNetGetConnectionW` per remote one).
  - The table is cached 10 s, so it is read again every 10 s.
  - Reached whenever the selected folder has raw files and no TXY: the usual state on the TDC share. Also from Live's
    `_convert_tick` → `share_to_confirm` (`explorer_convert.py:118`) when TXY go beside the raw files.
- **Scenario:** a mapped drive whose server is gone (a lab PC's `O:\`). Those calls may wait for the redirector,
  tens of seconds each.
- **On macOS and Linux:** psutil reads the kernel's table without waiting (0.015 ms for 30 mounts here).
- **Confirmed** by reading only; the Windows behaviour is not tested (`M~1`).
- **Fix:**
  - (a) Classify only the cache folder's own drive with `GetDriveTypeW`, never `all=True`.
  - (b) Have helpers report mount source, type and remoteness (extend `mounts_seen`; FolderCache keeps
    `_mounts_observed`) and let `share_of` read that.

### GT-8 · Medium (rare) · Two startup waits have no limit and no way out

- **(a)** `main.py:113-120` `wait()`: `processEvents` plus `time.sleep(0.2)` inside `cache_locks.startup`'s loop.
  It runs until `cache.lock` frees and `move.lock` isn't held; a cache-move helper can hold `move.lock` past the
  HeLab that started it (a stalled disk).
- **(b)** `main.py:168-172` `_recover_in_helper`: `submit(…, timeout=math.inf)` and then `QEventLoop.exec()`.
- **Both boxes** use `StandardButton.NoButton`: no Quit, no Cancel. The watchdog isn't running yet, so nothing is
  logged.
- **Confirmed** by reading.
- **Fix:** a Quit button on both. Give the recovery a no-progress timeout (heartbeats) instead of `inf`.

### GT-9 · Medium (OS behaviour, unconfirmed) · Native file dialogs and `QDesktopServices.openUrl` run in HeLab's GUI thread and can stall on a dead share

- **File dialogs:**
  - `SettingsDialog.py:319` (temp folder Browse), `:331` (cache folder Change…)
  - `ConverterTab.py:461`, `:481` (profile import and export)
  - `DataRootDialogs.py:207` (Save to folder…)
  - `HelabMainWindow.py:990` (Debug › Save screenshot / Dump State)
  - `script_tree.py:612` (Load Scripts…)
  - Windows' shell dialog lists mapped drives in its side pane and can freeze ("Working on it…") on a
    disconnected one. macOS's sidebar can do the same with a dead SMB mount. File › Open already avoids the
    native dialog (`HelabMainWindow.py:1429`).
- **`openUrl`:**
  - `FolderExplorer.py:2357` Open in File Manager: a source folder, possibly a share that went away.
  - Settings' Open Path for the temp and cache folders.
  - `_show_io_trace_folder`, `_show_log_folder`, `ConverterTab.py:492`, `CacheTab.py:272`, `CacheMover.py:392`.
  - `ShellExecuteW` and `NSWorkspace` run synchronously.
- **Confirmed** by reading; the stalls are platform behaviour (`M~2`).
- **Fix:** `DontUseNativeDialog` with a local start folder (as File › Open). `QProcess.startDetached` of
  `explorer`/`open` instead of `openUrl` (as `DataRootsTab.show_selected`).

### GT-10 · Low · The plot dock area's tab fit is quadratic and runs on every dock signal

- **Where:** `views/plots/dock.py:432-483`. `fit` → `identify_tabs` → `dock_at` for each tab, and each `dock_at`
  is a recursive `findChildren(QDockWidget)` over the whole area.
- **Triggers:** every `dockLocationChanged`, `topLevelChanged`, `visibilityChanged` (each tab switch) and
  `windowTitleChanged`.
- **Measured:**
  - The suite's only stall over 0.4 s: **0.59 s** in `test_accessible_names.py::test_every_script_and_each_library`,
    stack in `dock_at`.
  - `dock_fit_scaling.py`, with 300 widgets a dock: 10 docks 2.2 ms, 40 docks 32 ms, 80 docks 137 ms on this Mac.
  - Windows CI logged "GUI stalled for 2.30s" in the same test, and its tab-bar ID flake is this walk racing the
    debounce timer (known-issues).
- **Fix:** one `findChildren(QDockWidget, FindDirectChildrenOnly)` per fit into an `{address: dock}` map.

### GT-11 · Low · The RAM budget's check is O(plots² × shots) when over 80 %

- **Where:** `analysis/budget.py:123-138`, `:154-163` (`RamBudget.check`/`frees`). Each candidate's `frees` rebuilds
  every other plot's `ram_buffers` (`views/plots/instance.py:1617`).
- **Triggers:** after every run's end (`budget.schedule`, `instance.py:745`), every `datasetChanged` and every budget
  change.
- **Measured** by the helper (`experiments/plots/t_budget.py`): 0.19 s at 20 plots × 5,000 shots, 0.68 s at 40.
  Each released plot's first snapshot (grab and PNG) adds 0.09–0.2 s.
- **Fix:** take each plot's buffers once per check and keep holder counts.

### GT-12 · Low · The folder browser repeats data-sized work per row and per tick

- **(a) One full summary rebuild per changed row.** `changed()` emits `activityChanged` per row
  (`SnapshotFileSystemModel.py:623`), and each emit rebuilds the whole summary; a details batch is up to 128 rows
  (`:861`). This is 43 µs a row when idle. With Live and auto-convert on a 100,000-shot dataset a rebuild costs
  11 ms, so a 128-row batch is about **1.4 s**.
- **(b) Status checks re-derive per child.** Each child's status → `_update_ancestors` → `_derive(parent)`, O(n) per
  event: 10.4 ms an event at 20,000 siblings, about 200 s of GUI time over a full check, in small slices.
- **(c) Recomputed every 100 ms.** `txy_sources.empty_helab_shots` (`txy_sources.py:274-292`) and `origins_of` run
  every 100 ms (`FolderDetailsPanel.py:389`, `:462`) and on every summary tick (`explorer_live.py:1114`, `:1126`).
  That is 11 ms at 100,000 shots, about 25–30 % of the GUI thread, steadily.
- **(d) A settings read per animation tick.** `explorer_live.low_hits_threshold()` (`:123`) opens a QSettings on
  every 80 ms animation tick (`:1159` in `convert_line`, via `FolderExplorer._animate` `:2186`) while auto-convert
  is on. That costs 8 µs here, but it is where the 2026-11-06 field stalls' stacks were.
- `_animate` refreshes every tab, hidden ones too.
- **Measured** by the helper (`experiments/explorer/`).
- **Fix:**
  - Coalesce `activityChanged` (a dirty flag plus `singleShot(0)`).
  - Keep running tallies on parents.
  - Cache (c) per dataset object and (d) until Settings changes it.
  - Refresh only the shown tab's summary.

### GT-13 · Low · Small local-disk and registry work on the GUI thread

- **Profile library:**
  - `txy_source.known_profiles` / `profile_by_tag` (`views/plots/txy_source.py:31-44`) and `txy_list.known_names`
    (`:26`) list the profiles folder and parse every JSON on each call.
  - They are called for every plot on each plot open or close (`instance.py:939` via `PlotReopen.record`), and at
    `:1281`, `:1288` and `txy_source.py:152`.
  - A few ms locally.
- **Settings sync:** `QSettings.sync()` (`RegFlushKey` on Windows, which can take seconds on a busy disk) at
  `main.py:125` and in `CacheMover._cutover` → `write_cache_setting` (`CacheMover.py:290`).
- **I/O trace:** `delete_io_traces` (`io_service.py:97`) deletes every earlier trace file on the GUI thread, inside
  GT-1 (c)'s handler.
- **Cache move:** `CacheMover` runs `undo_rename` (an `os.rename` of the cache folder, `:326`) and
  `cache_move.cleanup` (`:314`) on the GUI thread, at the edge of "the GUI never touches the cache".
- **At import:** `usable_directory` (`isdir` + `TemporaryFile`, `constants.py:342-345`) runs on the saved temp
  folder, which can be set to a share.
- **IOService pauses:** `IOService._apply_pauses` touches or removes a pause flag in a helper's temp folder per pause
  change (`io_service.py:601-613`), under `request.control`, which `_run` holds across `tempfile.mkdtemp`.
- **Fix:**
  - Keep the profile library in memory, refreshed on change.
  - Move trace deletion into `trace_check`'s helper, and the cache-folder rename and cleanup into a helper.
  - The rest can stay.

### GT-14 · Low · Re-entrancy after nested loops

- **Settings:** `show_settings_dialog` carries on after `exec()` (`HelabMainWindow.py:1284-1318`) even if the
  window closed meanwhile (the updater's `ready`, or SIGTERM ending nested loops). `get_io_service()` then makes a
  new IOService after shutdown (`io_service.py:1231-1235`) and may submit.
- **Updates:** `_update_planned` (`:1052`) starts the updater after its box without a check.
- **SIGTERM:** `handle_exit` (`:2530`) calls `close()` from a Python signal handler, which can run in the middle of
  `_tick`.
- **Fix:** return when closing after each `exec()`. Use `QTimer.singleShot(0, self.close)` in `handle_exit`.

### GT-15 · Low · `git` at import and in window construction

- **Where:** `build_info.py:50` `_git`, 2 s timeout each:
  - `APP_BUILD_INFO` runs 4 calls, `git status --porcelain` among them (up to 8 s);
  - `updates/settings._upstream` runs 2 more in `UpdateCheck.__init__`.
- **Measured:** under 10 ms each warm.
- **Side effect:** a timeout makes `checkout_build_info` all-unknown, so `is_source` is False and updates are quietly
  off for the session.
- **Fix:** keep commit and branch when only `status` times out, and log it.

### Info

- **GT-16** · Debug › Show Memory Usage: pympler over every object, on the GUI thread (`MemoryUsageWindow.py:30`):
  0.2 s for 246k objects, seconds in a loaded HeLab. Debug menu only.
- **GT-17** · User scripts' `render`, `update`, `describe_*`, `parameters` and `estimated_bytes` run on the GUI
  thread unbounded and unmeasured (`instance.py:786-800`, `:862`). A cheap guard: time each hook, and warn with the
  script's name above 0.5 s.
- **GT-18** · The first `QWebEngineView` (Chromium's start) is made on the GUI thread when the first Plotly plot
  opens (`analysis/panes.py:49`): a one-off, not measured offscreen.
- **GT-19** · Notifications run synchronously:
  - `events.DesktopNotifier.deliver` → `QSystemTrayIcon.showMessage` (`events.py:127`), once per low-count shot,
    damaged file or read stop;
  - `events.notify`'s user hooks;
  - a hung Explorer taskbar on Windows could hold each call.
- **GT-20** · A newly computed plot's first show (`AnalysisDock.setWidget` → `widget.show()`, layout and polish) took
  about 0.3 s under `-n 4` load: the probe's 64 near-threshold stalls in `test_result_lifecycle.py` and
  `test_result_cache_review.py`. Expected, but it adds up when many plots finish together.
- **GT-21** · Without the console tee (`HELAB_NO_CONSOLE_FILE`, or the logs folder unwritable: `console_tee.start`
  returns None), logging writes to the console directly, and a paused PowerShell window blocks the GUI thread on its
  next line indefinitely: the pre-`96df3ed` situation.
- **GT-22** · macOS App Nap: nothing opts HeLab out (no `beginActivity`). A hidden or occluded HeLab's timers are
  throttled, so Live checks slow down and the watchdog can report stalls that are App Nap.
- **GT-23** · **The 5.68 s stall's candidates** for an idle Live on the TDC PC (Windows, unattended), from this
  audit:
  - GT-7 (b): the mount table every 10 s while a raw-only share folder is shown;
  - GT-3: a held console-file write, made worse because that stall's own stacks would wait behind it;
  - GT-12 (d): the field stalls' known site;
  - a display or monitor power change re-laying-out every window (Qt screen events; speculative).
  - The next stall's stacks will tell, if GT-3 is fixed first so the watchdog's line reaches the log.

## Checked and clean

- **IOService:**
  - helper start, pipe reads, JSON parsing and artifact reads are on daemon reader threads; the GUI only `kill`s
    and `poll`s;
  - `_tick` is bounded (64 events or 8 ms a pass);
  - the queues are bounded (`messages` 256, `MAX_PENDING` 128) and requests deduplicated;
  - slots are freed only on confirmed exit;
  - `store_options()` is memory only (cached layout and policy).
- **FolderCache:** dispatch and load assembly are memory only and O(shots) (`folder_cache.py:4330-4785`);
  `shutdown` clears memory only; `activity.record` and `LogLines` are memory only.
- **The watchdog:** its stacks go to a regular temp file (`thread_stacks`), not through the console. It never calls
  Qt from its thread (apart from `sip.isdeleted`).
- **The console tee's terminal path:** `_Terminal.put` never waits, and a stuck terminal only drops output. (Its
  file path is GT-3.)
- **AnalysisRunner and `runner_core.AnalysisQueue`:**
  - `_lock` guards dict operations only, and the queue is unbounded, so `put` never blocks;
  - `stop()`'s `join(5)` is called in tests only, and the worker is a daemon;
  - `finished` is queued to the GUI;
  - `compute`s use no Qt and release the GIL: `histogram2d` with 10M events holds it at most 11 ms.
- **Locks shared with other threads:** `RamResults`, `trends.ShotCache`, `KeptRuns`, correlations' `_LOCK`, Dash's
  `_plots_lock`/`_lock` guard dict operations only.
- **No `BlockingQueuedConnection`** anywhere, and no widget is touched off the GUI thread (OldLogs' queued signal,
  quit_watch's logging).
- **The quit path:**
  - `closeEvent` and `_wait_for_saves` join nothing and wait on no helper;
  - `QuitSaveDialog` is `open()`ed and polls memory every 250 ms, with Quit now always there;
  - `IOService.shutdown` only kills and polls.
- **Rendering:**
  - model `data()`, paint and tooltips read memory only, per visible row
    (`test_rendering_never_reads_filesystem_or_disk_cache` covers this);
  - `FolderTabWidget`, `path_index` and `FolderCache.key` are lexical;
  - `data_roots`' file-system functions (`_volume_id` with `diskutil`, `read_marker`) run only in helpers and
    `helab cache`.
- **Timers:**
  - status bar (1 s): psutil 0.2 ms;
  - status-bar left and Folder details (100 ms): memory, bounded by the queue (apart from GT-7 (b), GT-12 (c));
  - `log_memory` (a minute): memory sums;
  - the Activity window: no timers while hidden, at most 5 refreshes a second, bounded rows (128 requests, 200
    history entries, 500 log lines);
  - Folder info: reads go through a helper.
- **Updates:**
  - the check is asynchronous `QNetworkAccessManager` with a 10 s timeout, and the ETag cache is a small local JSON;
  - the dry run is an asynchronous `QProcess` with a 180 s kill;
  - the updater starts with `startDetached`;
  - the ready poll is a local file every 100 ms with a 15 s deadline;
  - `launch.tidy` handles small local files;
  - Help › User manual is an asynchronous HEAD with a 3 s timeout.
- **Already non-modal or deferred:** ClockSkewWarning, CacheDialogs, RootDuplicatesWindow, DataRootsTab's alerts,
  `_ask_raw_removal`/`_offer_raw_removal`, explorer_convert's questions, the RAM report.
- **Script folders:**
  - `FolderProbes` runs the test import in a separate process (QProcess, a 100 ms poll of a local file, `kill`
    without waiting);
  - auto-reload stats only local folders (1.2 ms with 2,000 modules);
  - start skips shares.
- **Size caps that hold:** DLD density images 1000², 1D histograms 2000 bins, 3D scatter 2M (0.34 s a draw).
- **Locks and settings:** `cache_locks` are non-blocking (`LOCK_NB`/`LK_NBLCK`). Lab parameters, folder constants
  and `live_launch` are settings only, at launch or on user actions.

## A guard that keeps it so (proposal; CoCo to approve)

1. **A static lint test**, `tests/test_gui_thread_calls.py`, with `inventory.py`'s AST finder moved into `tests/`.
   - **What it does:** it scans the GUI-process modules (`helab/views`, `helab/models`, `helab/analysis` Qt-side,
     GUI-side `helab/utils`, `helab/scripts/scripts_manager.py`, `helab/updates` except `updater.py`). It fails on
     any call it classes as a wait, file-system, network, subprocess, import-of-user-code, `QSettings.sync`,
     `QFileDialog.get*`, `QDesktopServices.openUrl` or `psutil` call that isn't in an allow-list
     (`tests/data/gui_thread_allowed.txt`: `module:function:call  # reason`).
   - **Cost:** about 1 s a run, and an allow-list of roughly 60 entries to write once (most are local app-folder
     files or user-chosen actions). It catches direct calls only, not a utility that stats a path two calls down;
     for those, a deny-list of known I/O utilities (`cache_location.*`, `cache_paths.current_mounts`,
     `user_profiles.*`) adds a few lines.
2. **No modal loop inside a helper or runner result** (GT-1's class). IOService's `_tick` and AnalysisRunner's
   delivery set a flag while they emit.
   - An autouse conftest fixture patches `QDialog.exec`, `QMessageBox.exec` and its static helpers, and
     `QMenu.exec`, so they fail the test when called with the flag set.
   - The app logs a warning with the stack instead.
   - **Cost:** about 30 lines and a boolean. It is precise; it would have caught GT-1 (b)–(e) in their existing
     tests, and (a) with one new test.
3. **A suite-wide stall report.** `stall_probe.py` moves into conftest, report-only like RERUN reporting.
   - The terminal summary lists HeLab code that held the event loop over 1 s, with stacks. A test fails only above
     5 s (CI load makes lower limits flaky).
   - **Cost:** one thread per worker sampling every 25 ms. The probed full suite took 196 s at `-n 4`, with no
     baseline measured. It finds only what the tests' small data exercises, so it backs (1) and (2) and doesn't
     replace them.
4. **In the app:** fix GT-3 so the watchdog's lines reach the log whatever the console does, and time user scripts'
   GUI-thread hooks (GT-17).

Recommended: (2) and (4) with the High/Medium fixes, (1) next, (3) when convenient.

## Proposed for the handoff (the Worker or CoCo files them)

- **Q~1 (Tony):** for GT-4, should Basic plots v2 draw its 2D histograms at display resolution (decimated on the
  worker; the saved result and the bins stay as chosen), and cap dots lower (for example 500k for PyQtGraph and
  Matplotlib)? Proposed: yes, images ≤ 2048 a side (Plotly ≤ 1000), with a note on the plot when decimated.
- **Q~2 (Tony):** for GT-6, should a script folder whose test import takes over about 2 s be left for Reload at start
  (like a share), with "takes N s to import"? Proposed: yes.
- **M~1 (lab PC, Windows):** with a mapped drive whose server is off, time HeLab's start (GT-7 (a)) and select a
  raw-only folder (GT-7 (b)). Does the GUI stall, and for how long?
- **M~2 (lab PC, Windows):** with the same dead drive, open Settings › General › Browse… and Open in File Manager on
  a folder of it (GT-9).
- **Known-issues:**
  - GT-10 is the cause of the `test_accessible_names` tab-bar flake (its fix closes that entry);
  - GT-23's candidates go under the 5.68 s entry;
  - GT-2 reopens "File › Quit sometimes left the process running" until fixed.

## Files in this folder

- `inventory.py`, `inventory.tsv`: the static inventory.
- `stall_probe.py`, `aggregate.py`, `test_probe_sanity.py`: the suite-wide stall probe.
- `modal_in_result_check.py` (GT-1), `quit_watch_check.py` (GT-2), `tee_block_check.py` (GT-3),
  `dock_fit_scaling.py` (GT-10): run from the checkout's root. The Qt ones need `QT_QPA_PLATFORM=offscreen`.
- `experiments/{main,plots,explorer}/`: the area readers' timing scripts (synthetic data). The `test_gt_*.py` ones
  run as `PYTHONPATH=tests python -m pytest -p conftest <file> -s`.
- Re-review (step 3): `mutants.py`, a pytest plugin that undoes one fix in memory (`GT_MUTANT=gt1|gt5|gt6|gt10`) or
  marks FolderCache's dispatcher as a delivery (`fcmark`). Run it as
  `GT_MUTANT=<name> PYTHONPATH=.ai/sessions/2026-11-10-claude-gui-threads-audit pytest -p mutants <tests>`.
  `experiments/rereview/test_gt24_budget_box.py` shows GT-24; run it as
  `PYTHONPATH=tests python -m pytest -p conftest <file>`.
- Re-review 2: `experiments/rereview2/test_every_bin_same.py` and `compare_every_bin.py` show that Q~1's "every bin"
  draws as before. Copy the test into a checkout's `tests/` (or run it with `-p conftest` from this one), with
  `GT_OUT` set, and `GT_EVERY=1` for the new code; then run `python compare_every_bin.py BEFORE.npz AFTER.npz`.
