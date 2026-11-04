# Review: the Activity window (`agent/activity-window`)

Gauge (Reviewer), 2026-11-04. Diff reviewed: `63b9a15..b2e996a`, without `cab0f3b`'s merge of `c0860ec` (its
`CacheTab.py` hunk is identical to `c0860ec`'s and was left out). Read against the brief, `design.md` (with CoCo's
answers), `handoff.md`, `roadmaps/activity-window.md` (Q62.1–Q62.5) and `AGENTS.md`.

## Checks rerun

- Full suite at `b2e996a`, `pytest -n 4 --reruns 5 --reruns-delay 1 --basetemp=.ai/temp/pytest-gauge`:
  **9382 passed, 673 skipped, no RERUN** (output kept whole in `.ai/temp/gauge-suite.log`).
- `mypy helab/ --strict`, `mypy tests --strict`, `pyright helab tests`, `mypy helab/ --strict --platform win32`,
  `pyright --pythonplatform Windows helab tests`: all clean (`.ai/temp/gauge-types.log`).
- Reproductions of AW-1 (offscreen, scratchpad scripts, not committed): with the real `IOService` and
  `FolderCache`, and with a fake snapshot source.

## Summary

1 Blocker, 1 Major, 9 Minor, 2 Info. **AW-1 must be fixed before landing**: the window stops working the
first time a task changes group while its old group empties, which happens on every load that writes the disk
cache. The rest of the diff holds up. Rendering reads memory only. The GUI never waits. A cancelled helper's row
says "stopping" until its exit flag, and Retry is refused until `unexited` clears. The user hold leaves the
foreground and local lanes, saves and Live checks running, and quitting lifts it. History is added to on the GUI
thread only, and each IOService request's end is reported once. The hot paths add only cheap memory work while the
window is closed. Windows paths are compared as folders, every new control has an `identify` ID, no lambda captures
a Qt-made sender, and nothing is connected to `destroyed`.

## Findings (most severe first)

### AW-1 · Blocker · `helab/views/ActivityWindow.py:977-1001` (`_render_now`, `_sync`)

**A row whose group or parent changes, while its old group or parent row leaves the list, breaks the window.**
`_sync(tree.invisibleRootItem(), groups)` calls `takeChildren()` and drops the returned list. A group item that
is no longer wanted is then deleted by sip, and the C++ side deletes its child items with it. Those children
include the task's own `QTreeWidgetItem`, which `wanted` / `self._items` still hold. The next
`_sync(group, tops[name])` passes that deleted item to `addChildren` and raises
`TypeError: index 0 has type 'QTreeWidgetItem' but 'QTreeWidgetItem' is expected`.

- `tree.blockSignals(False)` is never reached, so the Now tree's signals stay blocked: selection no longer updates
  the details pane or the buttons.
- `self._items` keeps the deleted item, so **every later refresh** (the 1 s tick) raises
  `RuntimeError: wrapped C/C++ object of type QTreeWidgetItem has been deleted` from `_fill`/`setData`.
  `app_log`'s excepthook then logs a traceback and posts a status notice each second, until that task's id
  leaves the snapshot.

**Scenario (reproduced):** the Activity window is open and one folder loads. When its helper delivers the data
(`loaded`, `completed`), it goes on writing the disk cache. `about()` now gives the same task id the group
"saves" (`finishing`), and "Loads and scans" empties. The refresh raises at once, the next one raises
`RuntimeError`, and `now.signalsBlocked()` is still True. With the real `IOService` and `FolderCache`:
`cache.submit("tab", 0, "/data/run_1", "load", {})`, refresh, set `service.active[0].completed = True`, then
refresh twice.

The same thing happens when a child loses its parent row: a GUI conversion finishes (`tab_tasks` skips it) while
its pass's I/O row (`_conversion_parent`) is still listed, or a Live session's row goes while its save or
convert child stays. A row moving between two groups that both stay listed can also go missing for a tick: if the
new group is synced first, `addChildren` ignores an item that still has a parent.

**Fix:** detach each wanted item from its current parent before re-parenting it, e.g. `old = item.parent();
if old is not None and old is not target: old.removeChild(item)` (for top-level items,
`tree.takeTopLevelItem`). Or, when any wanted item's parent changes, rebuild with `tree.clear()` while holding no
stale items. Keep the taken lists alive until the end of the render. Wrap the render in `try/finally` so
`blockSignals(False)` always runs, and drop `self._items` entries that fail. Add tests for a load becoming a cache
write as the only load, for a conversion finishing while its pass row stays, and for a Live session ending before
its save.

### AW-2 · Major · `helab/utils/activity.py:57` (`NOT_KEPT_WHEN_OK`), `helab/utils/io_service.py:1028-1048`

**Successful conversion passes and browse step 2 fill the 200-entry history within minutes**, pushing out the
failures it is meant to keep (Q62.4, and Q~2's "frequent small work left out"). `kept_in_history` keeps every
successful `convert` request:

- **Live's auto-convert** submits one pass with each Live check, at least a check interval after the last
  one ended (`LiveController._convert_tick`, `explorer_live.py:861-884`), whether or not new raw files came. At the
  default 3 s interval, that is one "Convert raw files to TXY · done" entry every few seconds, about 200 in 10 to
  15 minutes.
- **A GUI conversion's passes**: each is an extra entry beside the conversion's own `_report`. The handoff says
  "its passes are I/O entries too, kept only when they fail", but the code keeps them when they succeed too.
- **`details`** (browse step 2, `SnapshotFileSystemModel._request_details`) runs for every folder the user
  browses into, and each success is kept. So is every `cached` read.

**Fix:** leave out successful `convert` requests whose owner is a tab's Live or converter owner (their Live
session or conversion is the entry), or every successful `convert` pass, since the GUI conversions report their
own end. Add `details`, and probably `cached`, to `NOT_KEPT_WHEN_OK`. Then a test: auto-convert passes every few
seconds add no `ok` entries. Update the handoff's proposed architecture text and Q~2's wording to match.

### AW-3 · Minor · `helab/views/ActivityWindow.py:615-616`, `:637-643`; `docs/how-to/activity.md:62-63, 79`

**Cancel on a tab's selected load, and Cancel all queued, also stop the tab's other background loads,
including running ones.** The "select" role calls `FolderExplorer.cancel_loading()`, which calls
`_cancel_background()` (`FolderExplorer.py:2652-2657, 2672`) and cancels every `bg_owner` load. Scenario: the
user selects folder B while A's helper is still stopping, so B's load is queued. Cancel all queued cancels B, and
with it the tab's running background loads, though the page says it "cancels every queued task". On a single
row, Cancel also removes other rows the user didn't pick. This matches the toolbar's Cancel, as designed, but
nothing in the window or the manual says so.
**Fix:** for Cancel all queued (and perhaps Cancel), use `FolderCache.cancel(model.owner, op, path)` plus the
tab's own state update for that folder rather than `cancel_loading()`; or keep it and say so in Cancel's tooltip
and the manual. If the behaviour stays, it is CoCo's or Tony's call.

### AW-4 · Minor · `helab/views/plots/script_tree.py:819-830`

**The new methods were inserted between `@pyqtSlot()` and `_reload_clicked`.** The decorator now marks
`probe_activity`, a value-returning accessor called from Python, and `_reload_clicked` lost it. I checked that
`clicked` still reaches an undecorated no-argument method in PyQt6, so nothing breaks. But the decorator was
there on purpose (its comment: `clicked` must not pass `checked` as the folders), and a slot decorated with no
return type on a method that returns a list is wrong.
**Fix:** move `@pyqtSlot()` back onto `_reload_clicked` and drop it from `probe_activity`.

### AW-5 · Minor · `helab/views/explorer_convert.py:527-529, 559-563`; `helab/views/explorer_live.py:881-884`

**Some conversion failures never reach the history**, though "every failure is kept" (the manual's line 56,
Q~2). These set `conversion.error` or `convert.error` and show "failed" in Now, but never call `_report` /
`activity.record`:
- `start` when the beside flag can't be queued;
- `_pass` when the conversion can't be queued (or another profile's conversion of the folder runs), on the
  first pass or on a later one through `_next_passes`;
- Live's auto-convert "couldn't be queued".

**Fix:** report there too, or in one place where `error` is set.

### AW-6 · Minor · `helab/utils/activity.py:173-178` (`History.add`)

**An error in a history listener, or the thread assert, propagates into the owner's own end path.** Only
IOService wraps `record` in `try/except`. `CacheMover._end` records before `self.finished.emit(moved)`, and
`stop_live` before `logging.info` and `_live_changed()`; so do the probe, conversion and runner reports. A raising
listener, such as a window whose wrapper has gone while it is still listed, would skip those calls. Today the
listener is removed in `hideEvent` and the main window closes the window first, so this is only a robustness gap.
**Fix:** call each listener in `History.add` under `try/except Exception: logging.exception(...)`, so a view
can never break an owner.

### AW-7 · Minor · `docs/how-to/activity.md:41-42, 45-46, 76-78`

Accuracy:
- Lines 41-42: "**stopping** … It keeps its place in the queue until it has" exited. It keeps its **slot**
  (nothing new starts in it, and its retry waits), not a place in the queue.
- Lines 45-46: "HeLab stops it after a minute without progress". A load's file reads time out after 15, 20 and
  30 s, with retries, and a finishing cache write has its own limit. Say "after a while without progress (a
  minute for most work)" or similar.
- Lines 76-78: "The current tab, saves, **Live** and reading the local disk cache carry on". Live's checks
  and autosaves do, but its **auto-convert passes pause**: `convert` is in `PAUSABLE` and they run in the
  background lane. Say so, as the Pause button's own tooltip does ("conversions").
- If AW-3 stays as it is, line 62-63 should say that Cancel on a tab's load also stops that tab's other
  background loads.

Public-text rules: no person's name, internal ID or `.ai/` path on the page.

### AW-8 · Minor · `helab/views/ActivityWindow.py:383`

**An internal ID in user-visible text.** A test import's details line reads "Its own time limits end it
(Q49.3 (b))" (details pane and tooltip).
**Fix:** "Its own time limits end it (10 s to start, 20 s to import)" or just drop the parenthesis.

### AW-9 · Minor · `helab/views/ActivityWindow.py:466-474, 844`; `helab/utils/settings_defaults.py:180-182`

**The saved size isn't clamped to the screen**, though the settings row says "at most the screen's" and the
design said "clamped to the screen". A size saved on a large external monitor reopens larger than a laptop's
screen.
**Fix:** bound it by `self.screen().availableGeometry()` (or the main window's screen) when it first shows, or
correct the description.

### AW-10 · Minor · `helab/views/ActivityWindow.py:1017-1047`

**The History tab is rebuilt from scratch on every history change.** `tree.clear()` resets its scroll
position, and for each failed entry `_history_details` scans `LogLines` (up to 500 lines × 200 entries) for its
tooltip. With AW-2's rate, that is a full rebuild every few seconds while the user scrolls. Selection is restored
by entry id, but ids repeat: every Live session of a folder is `live:<owner>:<path>`, and repeated requests of one
owner and generation share `io:…`. So the selection jumps to the newest entry with the same id.
**Fix:** prepend only the new entries (the deque's `version` tells how many), build tooltips lazily (on
selection or hover), and give entries unique ids (a counter, or the start time as conversions and probes
already have).

### AW-11 · Minor · `tests/test_activity_window.py:169-205`, and the missing regroup test

**The tests miss AW-1, and the memory-only test covers only IOService rows.** `test_rendering_reads_memory_only`
has no tabs, so `_live_task`, `_auto_convert_task`, `_conversion_task`, `_question_task` and the history's
rendering (with entries and `LogLines`) never run under the source guard. No test changes a row's group or parent
between refreshes, which would have caught AW-1.
**Fix:** run the memory-only test with a fake tab that has a Live session with auto-convert, a conversion, a
question and a failed history entry. Add the regroup and reparent tests from AW-1.

### AW-12 · Info · `helab/utils/activity.py:219-228` (`LogLines.about`)

Lines are matched by substring, so a failure in `/data/run1` also shows warnings about `/data/run10`. Matching
the folder followed by a separator or the end of the path, or with the path quoted, would avoid it.

### AW-13 · Info · `helab/views/ActivityWindow.py:970`

A group heading counts every task of that group, including children shown under another group's parent: a Live
session's auto-convert pass (group "convert") or its save (group "saves"). So "Conversions (2)" can sit above one
visible row. Count `tops[group]` plus their descendants instead, or count by where rows are shown.

## Doc proposals the handoff should change

- The proposed `app-runtime-and-ui.md` paragraph's list of what the history leaves out must match AW-2's fix.
- `testing.md`: the proposed note on `fresh_activity` is right. It could add that `IOService` now records into
  the global `HISTORY` in **every** test (bounded, and harmless with no listeners), and that a test shown window
  must be hidden or closed so its listener goes.

## Re-check (Gauge, fixes `3afddf4..16ff65c`)

I read only the fix diffs: `c906528`, `41de473`, `3798dea`, `7682d6c`, `384f93f`, `33b1489`, `a429d15`,
`df13e56`, `a3eb1c7`, `de386d2`, `a69c9d4`, `0c653c1` and `d4593c8`, plus the handoff commits `99c74c4` and `16ff65c`.

**Checks rerun at `16ff65c`:**
- Full suite, `pytest -n 4 --reruns 5 --reruns-delay 1 --basetemp=.ai/temp/pytest-gauge`: **9390 passed, 673
  skipped, no RERUN**. Output is kept whole in `.ai/temp/gauge-recheck-suite.log`.
- The five type checks are clean (`.ai/temp/gauge-recheck-types.log`).
- AW-1's reproduction, with the real IOService and FolderCache (a folder's only load starts writing its cache),
  is now clean. The tree goes from `Loads and scans (1)` to `Saves (1)`, with no exception, and its signals are
  not blocked.
- **The new tests fail on the old code.** I ran HEAD's tests against `3afddf4`'s `helab/`, in a scratch copy
  with `PYTHONPATH` pointing at it. All 13 new or changed tests failed there, covering AW-1, 2, 3, 5, 6, 8, 9, 10,
  12 and 13. The 40 others passed.
- **AW-11's memory-only test catches a regression.** `test_rendering_reads_memory_only` passes on both, as it
  only adds coverage. In a scratch copy I made `_live_task` call `os.path.isdir(session.path)`, and the test then
  failed with `touched == ['stat …/source/live']`.

| AW | Re-check |
|---|---|
| AW-1 | **Resolved.** When the shape changes or an item is replaced, every item is detached before any is placed again. The items taken out stay in `held` until the render ends, so sip never deletes a row that is still wanted. A stale wrapper is replaced (`_item` catches `RuntimeError`), and `try/finally` always unblocks the signals. If a render fails part-way, `_shape` isn't updated, so the next render detaches everything again. Three regroup/reparent tests cover it. It brings one regression in scroll position: AW-14. |
| AW-2 | **Resolved.** `NOT_KEPT_WHEN_OK` now includes `convert`, `details` and `cached`. Failures and cancellations are still kept. The 20-pass test fails on the old code. |
| AW-3 | **Resolved as CoCo decided.** `queued_only` skips only the `select` subscriber of a `load`/`cached` request; any other subscriber of the same request is still cancelled. Both tooltips and the manual say so. The test checks that the running background load survives and that `cancel_loading` isn't called. |
| AW-4 | **Resolved.** |
| AW-5 | **Resolved.** Each failure is reported once. `_next_passes` skips a conversion with `error` set. `_convert_tick` returns while `convert.error` is set, so a pass that couldn't be queued adds one entry, not one per check. A Live `offline` answer is FolderCache's, with no IOService request (`folder_cache.py:2816`), so it isn't counted twice. |
| AW-6 | **Resolved.** |
| AW-7 | **Resolved.** The manual's three lines are now accurate. The page has no person's name, internal ID or `.ai/` path. |
| AW-8 | **Resolved.** `probe_limits()` keeps `script_tree` (and QtWebEngine) out of the builder's imports. |
| AW-9 | **Resolved.** The window is fitted once, in `showEvent`, before it is mapped. `de386d2`'s bound (the window's own `minimumSizeHint`) is right for the 800 px offscreen screen. |
| AW-10 | **Resolved.** `key` is `id#seq`, and `seq` is never reset (`clear` keeps `_serial`), so keys stay unique across a clear. New entries are inserted on top and dropped ones removed from the bottom. The history rebuilds only when its newest shown key has gone (the first render, a clear, or more than 200 new entries while the window was hidden). When the selected oldest row drops, the selection moves to the next row and the details pane follows it (checked by script). Retry and the details use the same entry. One small change: the Tab column is now set when a row is added and isn't updated if the tab is renamed later. This is harmless. |
| AW-11 | **Resolved** (see the mutation check above). |
| AW-12 | **Resolved.** |
| AW-13 | **Resolved.** |

### AW-14 · Minor · `helab/views/ActivityWindow.py:1046` (`_place_rows`, AW-1's full detach)

**With no row selected, the Now tree jumps to the top whenever a task starts or leaves.** AW-1's fix runs
`root.takeChildren()` on every shape change. That takes every top-level row out, the vertical scroll bar's
maximum falls to 0, and its value is clamped there before the rows come back.

Measured with the real IOService: 80 queued scans, scrolled to the bottom (value 75), then one more scan
queued. The value is **0** after the refresh at `16ff65c`, and **75** with `b2e996a`'s render.

With a row selected, `setCurrentItem` scrolls to that row. The old render did this too, so it isn't a regression.
While loads queue and finish, the shape changes several times a second, so you can't read further down a long
list.

**Fix:** save `now.verticalScrollBar().value()` (and the horizontal one) before the detach and set them again
after the rows are placed, inside the `try`. Add a test that scrolls a long list, queues a task and checks the
value is kept.

### AW-15 · Minor · `helab/views/explorer_convert.py:612`, `helab/utils/io_service.py:1028-1037` (pre-existing; I missed it in the first review)

**A GUI conversion pass that fails or is cancelled goes into the history twice.** IOService's `_report_end` keeps
a `convert` that fails or is cancelled (AW-2 leaves out only successes). `ExplorerConverter.event` then reports
the same end again through `_report`, with its `conversion` route.

Checked by script: `cache.convert("tab:convert", "/raw", …)` and a helper `error` leave
`('Convert raw files to TXY', 'failed', 'io', ('tab:convert',))` in `HISTORY`. The tab's `_io_event` then calls
`converter.event`, which adds a second `('Convert raw files to TXY', 'failed', …, 'conversion')` row.

Closing a tab (or Cancel) during a conversion gives two `cancelled` rows the same way. Live's auto-convert isn't
affected, because `_convert_stopped` reports only ends where no helper ran. The rule that each owner's end is
reported once still holds, since these are two owners. But the user sees one failure as two rows, and the two
rows' Retry buttons use different routes.

**Fix:** follow AW-2's own reasoning: the GUI conversion is the entry. Either
- IOService doesn't report `convert` requests whose owner is an `ExplorerConverter`'s, the way Live's are
  handled; or
- `kept_in_history` leaves out every outcome of a `convert` request whose route is a GUI conversion.

Then add a test that runs a pass's `error` through FolderCache and the tab, and checks there is one entry.

**Summary of the re-check:**
- AW-1 to AW-13 are resolved, and I found no new Blocker or Major.
- There are 2 new findings, both Minor:
  - AW-14 is a regression from AW-1's fix.
  - AW-15 predates the fixes; I missed it in the first review.

## Re-check 2 (Gauge, fixes `12d4580..6f1b4f4`)

I read only `8cfd279` (AW-14), `5b9a270` (AW-15) and the handoff commit `6f1b4f4`.

**Checks rerun at `6f1b4f4`:**
- Full suite, `pytest -n 4 --reruns 5 --reruns-delay 1 --basetemp=.ai/temp/pytest-gauge`: **9392 passed, 673
  skipped, no RERUN**. Output is kept whole in `.ai/temp/gauge-recheck2-suite.log`.
- The five type checks are clean (`.ai/temp/gauge-recheck2-types.log`).
- **Both new tests fail on the old code.** I ran HEAD's tests against `12d4580`'s `helab/`, in a scratch copy.
  - The scroll test fails with `assert 0 == 67`.
  - The one-entry test fails with "Left contains one more item: ('Convert raw files to TXY', 'failed', 'io')".

| AW | Re-check 2 |
|---|---|
| AW-14 | **Resolved.** Both scroll bars' values are read before the detach and set again inside the `try`, before `setCurrentItem`. My earlier probe (80 queued scans, scrolled to the bottom, one more queued) now keeps 75, as `b2e996a` did. With a row selected, the tree scrolls only as far as that row (76 → 41, where it used to be 36). |
| AW-15 | **Resolved** for the case it targets: a GUI conversion's failed or cancelled pass now gives one entry, with the conversion's route. Checked as CoCo asked: (1) **Bounded and cleared.** The marks are an `OrderedDict` capped at 1024, oldest dropped first, and `reports_end_itself` pops each mark at the request's first terminal event. A mark can be left behind (`service.submit` refusing after `_note_self_reported`, or a request that never reaches `_report_end`), but producer owners are `uuid4().hex`, so a leftover mark can never match a later request. (2) **No change when the window is closed.** The history is written whether or not the window is open, and the new cost on the hot path is one set lookup per subscribe and one dict pop per end. Owners outside `self_reporting` are unchanged. (3) **Live's own pass** is never marked, and a failed one keeps IOService's entry (the test's last case). (4) **A shared job** is where the mark goes wrong: AW-16, below. A load another tab also wants is never marked, because only the converter's owner is in `self_reporting`, and it subscribes only to `convert`. |

### AW-16 · Minor · `helab/utils/folder_cache.py:3352-3356` (`_note_self_reported`), `:3314-3319` (`cancel`)

**A mark set when the GUI conversion joins Live's pass stays after the GUI conversion leaves, so Live's failure
is lost.** The mark is set on the producer when a self-reporting owner subscribes, and it is only removed at
the request's end. FolderCache runs one conversion per folder, and a second asker with the same profile joins
it (`convert`, and `_convert_tick` checks `converting_with`). So a GUI conversion and Live's auto-convert of
one folder share the job, in either order.

When the GUI conversion's subscription is cancelled and Live's keeps the job running:
1. The conversion reports `cancelled`.
2. The mark stays.
3. When that pass then fails, IOService skips it.
4. Live reports no helper failure of its own (`_convert_stopped` covers only ends where no helper ran).

So nothing reaches the history, although Live's auto-convert stops on the error.

The GUI conversion's subscription can be cancelled by the Activity window's Cancel on the conversion row
(`cache.cancel(route.owner, "convert", path)`), or by `ExplorerConverter.close` when only its own tab closes.

Checked by script, with the real IOService and FolderCache and `"tab:convert"` in `self_reporting`:
- `convert("tab:live", p)`, then `convert("tab:convert", p)`: the job's subscribers are `['tab:live', 'tab:convert']`.
- `cancel("tab:convert", "convert", p)`: the job runs on for `['tab:live']`.
- The helper's `error`: `HISTORY` is `[]`. At `12d4580`, IOService recorded this failure.

A related but acceptable case: when both owners are still subscribed and the pass fails, the conversion's entry
is the only one. That is still one entry for one failure.

**Fix:** remove the mark when the last self-reporting subscriber leaves a job that runs on. In
`cancel`'s subscriber loop, after `del job.subscribers[key]`, if `job.subscribers` isn't empty and no remaining
subscriber's owner is in `self_reporting`, call `self._self_reported.pop(job.owner, None)`. If the job is
forgotten, keep the mark, so the cancelled request's end is still the conversion's alone. Add a test:
- Live's pass joined by a GUI conversion.
- The GUI conversion cancelled.
- The pass's `error`.
- Expect one `('Convert raw files to TXY', 'failed', 'io')` entry.

**Summary of Re-check 2:**
- AW-14 and AW-15 are resolved, and I found no Blocker or Major.
- There is 1 new finding, AW-16 (Minor), which comes from AW-15's mark.
