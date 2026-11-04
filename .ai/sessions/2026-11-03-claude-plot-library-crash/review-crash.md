# Review: the Live plots crash (`agent/plot-library-crash`)

Reviewer Prismo (claude, Opus 5.5), 2026-11-03. Diff: `git diff f534ede..34e6452`. The handoff is `8c381e6`.

**Verdict: no blocker and no open finding.** There are two optional notes (N1, N2) and an assessment of A~2.
- **The cause is confirmed.** A test-made Scripts panel with no Qt parent was freed by the garbage collector while Qt
  polished it.
- **Users can't hit it.**
- **The fix closes it.** Coloring `start_note` amber through its palette, not a style sheet, means no Python code runs
  during the panel's polish.
- **The tests prove it.** Both new tests fail on `f534ede`, the nested one with a SIGSEGV.

## The cause

- **Where it crashed.** CI job 125365677960 (run 41471378031) shows `Fatal Python error: Segmentation fault`, with
  the main thread at `tests/test_live_plots.py`, line 1636, in `test_transfer_fractions_highlight_follows_lives_newest_shot`
  (the log's line 5969). On `f534ede` that line is the test's first `waitUntil`, after `plot()` and before any
  library switch. So the switch did not start it.
- **Why the panel is garbage.**
  - `plot()` (`tests/test_live_plots.py:164`) makes `TreePanelWidget(window.plots)`. Its first argument is the
    workspace, not a Qt parent, so Python owns the panel.
  - `qtbot.addWidget` keeps only a weak reference (`pytestqt/qtbot.py:793`).
  - So once `plot()` returns, nothing but reference cycles holds the panel.
- **Where Python runs mid-polish.**
  - `start_note` is an `ElidedLabel`, and `ElidedLabel` overrides `changeEvent` in Python (`helab/views/ElidedLabel.py:42`).
  - Polishing a style-sheeted label sets its palette, which sends a PaletteChange to that `changeEvent`.
  - Any allocation there can start a collection, and that frees the panel inside its own polish.
  - Before M3 (`a18e4c9`) nothing in the panel ran Python while it was polished.
- **I checked this independently.** I wrote a plugin that forces `gc.collect()` after every `ElidedLabel.changeEvent`
  and `resizeEvent`. I ran it on `test_live_plots`, `test_live_scripts`, `test_analysis_gui`, `test_folder_details_io`,
  `test_result_cache_badge`, `test_large_folder`, `test_cache_tab`, `test_constant_layers` and `test_script_system`,
  with `-n 8 --reruns 5 --reruns-delay 1`, leaving out the nested test:
  - **On `f534ede`:** 39 RERUNs, every one a crashed worker ("worker 'gwNN' crashed while running …"), across many
    `test_live_plots` and `test_live_scripts` tests.
  - **On `34e6452`:** 256 passed, no RERUN.

  So with the note's style sheet gone, these files have no other path where Python runs in Qt's handling of a dropped
  panel. The only Python virtual methods in the panel's widget tree are `ElidedLabel`'s `changeEvent` and `resizeEvent`.

## Users can't hit it

- **The app's Scripts panel.**
  - `HelabMainWindow.py:1233` makes it, and `:1247` adds it to `right_splitter`, so Qt owns it.
  - `self.panel_right_bottom_script_selector` also holds a reference.
  - No event loop runs between the two lines. It is never garbage.
- **The library switch.**
  - `set_plot_result` (`workspace.py:236-237`) and `replace_plot_content` (`:260-261`) call `old.setParent(None)` and
    then `old.deleteLater()`.
  - In PyQt6, `setParent(None)` makes the widget Python's. I checked: `sip.ispyowned` is True right after it.
  - `deleteLater()` hands it back to Qt (`ispyowned` False after it), so no collection can free it before its
    deferred delete. I checked this with the replaced widget held in a reference cycle and after a `gc.collect()`: it
    stayed alive until its deferred delete.
  - In between, the local `old` keeps it referenced. **The guarantee holds** (see N1 for the handoff's wording).
- **The amber note still shows amber.**
  - Qt warns that `setPalette` may not apply under an ancestor's style sheet. The app's main `splitter` has one
    (`QSPLITTER_STYLESHEET`, `HelabMainWindow.py:991`).
  - I rendered the panel under a `QSplitter` with that style sheet, on the offscreen platform. The note's
    `WindowText` was `#b26a00` (`AMBER`), and 154 of its pixels were `#b26a00`, the same as without a style sheet
    and as on `f534ede`.
  - The native macOS style isn't checked; the release smoke pass would show it.

## The tests

The three tests, on scratch copies of the two commits (`f534ede` with `34e6452`'s tests):

| Test | `f534ede` | `34e6452` |
|---|---|---|
| `test_a_dropped_scripts_panel_survives_a_collection_in_its_first_polish` | fails: `-11` (SIGSEGV) | passes (nested: "3 passed", all three libraries) |
| `test_the_panels_polish_runs_no_python_code` | fails: `PaletteChange` seen twice | passes |
| `test_a_replaced_plot_stays_qts_until_its_delete_later` | passes (a guard) | passes |

- **The guard test catches a broken guarantee.** I removed `old.deleteLater()` from `set_plot_result` and the guard
  failed (`assert (0 == 1)`): without it, the old widget is deleted as soon as its wrapper goes.
- **It does not cover `replace_plot_content`.** The same mutation there survives, because the library switch doesn't
  take that path (see N1).
- **The nested test caught the bug once more, by accident.** At 04:09:52, while my first full suite ran, this floor's
  working tree was switched to `agent/preset-modal-hang` (`db6b32e`). That branch doesn't contain the fix. The
  nested test then ran the CI test against the old `script_tree.py` and failed 6 times out of 6 with `-11`. That run
  is void for the branch (see Checks), but it shows the test catches the bug outside a scratch copy too.

## A~2 (the proposed testing rule)

**Adopt the first half, preferring a Qt parent.** A test-made widget with no Qt parent that the test drops can be
freed at any moment, and Qt crashes if that moment falls inside its own event handling.
- A kept reference is enough only if it lasts until pytest-qt's teardown. Teardown calls `close()` and
  `deleteLater()` (`pytestqt/qtbot.py:808-809`), and `deleteLater()` hands the widget to Qt.
- So give the panel a Qt parent: `TreePanelWidget(window.plots, window)`, since its second argument is the parent.
  This is the simpler rule.
- About 45 test sites make `TreePanelWidget(...)`: 17 in `test_analysis_gui`, 16 in `test_live_scripts`, 4 in
  `test_constant_layers`, and the rest in 6 other files. The first to change are the `plot()` helpers that drop it.
- I'd propose that change as an AI_TODO item rather than this floor's work. Under forced collections none of them
  crashes now (the 256-passed run above).

**Make the second half a note on the mechanism, not a ban.** "Keep Python code out of a widget's polish (no style
sheets on Python subclasses whose `changeEvent` is overridden)" covers less than the risk, and bans more than it needs to.
- **It covers less.** Polish isn't the only window. Any Python event handler that runs inside Qt's handling of a
  dropped widget is the same hazard: `ElidedLabel.resizeEvent` after a layout, or `AnalysisDock.event`
  (`dock.py:249`), which sees every event.
- **It bans more.** The app style-sheets `ElidedLabel`s under widgets Qt owns, and that is safe:
  - `FolderExplorer.py:1916` and `:1979`, the summary and freshness lines;
  - `FolderDetailsPanel.py:249`, `:253` and `:259`, its state, errors and convert values.

  As a ban, the rule would forbid those for no gain.
- **Proposed wording for testing.md:** "A widget a test makes with no Qt parent and then drops is freed by the
  garbage collector whenever any Python code runs, even while Qt is inside one of its own event handlers (a
  SIGSEGV). Give test-made widgets a Qt parent, or keep a reference until pytest-qt's teardown. In the app, every
  widget has a Qt parent or an owner that holds it."

## Optional notes

- **N1 (wording and coverage).** The handoff says "`setParent(None)` leaves its C++ object … not Python-owned until
  its `deleteLater`", and the guard's docstring says "is never Python's". In PyQt6, `setParent(None)` does make it
  Python's, and the `deleteLater()` right after hands it back to Qt. The guarantee rests on those two lines staying
  together. Suggested fixes:
  - Say this in the docstring, and in a comment at `workspace.py:236` and `:260`.
  - Optionally guard `replace_plot_content` too (the RAM budget's release picture). Removing its `deleteLater()`
    isn't caught today.
- **N2 (the nested test could pass with no tests run).** It asserts only `returncode == 0`.
  - If the CI test's parameters were all skipped some day, pytest would still exit 0, and the test would pass without
    running anything.
  - Pytest returns 5 if the CI test is renamed (nothing collected), so that case already fails.
  - Asserting `"3 passed" in done.stdout`, or checking for no "skipped", would close it.

## Checks

- **My first full suite is void.** The floor's checkout moved to `agent/preset-modal-hang` during it, as the reflog
  shows: `HEAD@{2026-11-03 04:09:52}: checkout: moving from agent/plot-library-crash to agent/preset-modal-hang`.
  Its pyright RERUNs came from the mixed tree (a missing attribute of `helab.utils.events`), and so did the nested
  test's failure. I didn't touch that working tree, which now holds someone's uncommitted
  `helab/views/plots/presets.py` and `tests/test_presets_plots.py`.
- **I reran the full suite on an isolated copy.** I took `git archive 8c381e6`, with the floor's `testdata`,
  `legacy/tdc_autoconverter` and `venv` linked in (submodule commits match), and ran it with `PYTHONPATH` set to the
  copy:
  - The command was `pytest -n 4 --reruns 5 --reruns-delay 1`.
  - The result was 3 failed, 9131 passed, 674 skipped, 15 rerun.
  - All 15 RERUNs and the 3 failures are the three git-provenance tests, which need a `.git`:
    - `test_release_recovery.py::test_detached_pr_stamp_records_source_branch_and_merge_ref_without_replacing_commit`
    - `test_versioning.py::test_source_provenance_ignores_launch_directory`
    - `test_versioning.py::test_frozen_metadata_survives_no_git_and_unrelated_cwd`
  - Their reasons: `assert 'unknown' == 'aaaa…'` and `assert ('unknown' != 'unknown')`, where `BuildInfo.commit` is
    `'unknown'`. They are an artifact of the copy, untouched by this diff, and green in CI 41483861898.
  - There was no other RERUN.
- **Type checks** on the same copy: `mypy helab/ --strict`, `mypy tests --strict`, `pyright helab tests`,
  `mypy helab/ --strict --platform win32` and `pyright --pythonplatform Windows helab tests` are all clean.
- **Under load,** with 16 busy loops and a load average of 30 to 55:
  - `test_live_scripts.py` and `test_live_plots.py` whole, with `-n 12 --reruns 5 --reruns-delay 1`: 163 passed.
  - The three new tests and the CI test, 10 rounds with `-n 3 --reruns 5 --reruns-delay 1`: 60 passed.
  - No RERUN in either.
- **CI 41483861898** (on `34e6452`) is a success on every job. I didn't reread its logs for RERUNs; the handoff
  reports Windows Tests (1/2)'s Scatter3D worker crash, which is in known-issues.
