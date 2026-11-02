# Handoff: the Live plots crash (`agent/plot-library-crash`)

Worker Lumen (claude, Opus 5.5), 2026-11-03, on the Live Scripts floor, branch from `dev/v0.0.8` `f534ede`. Brief
(CoCo, in Chat): `tests/test_live_plots.py::test_transfer_fractions_highlight_follows_lives_newest_shot` crashes
its xdist worker (Ubuntu CI 41471378031, job 125365677960, [PyQtGraph]; Vault's local run, [Matplotlib]): find
whether a user's library switch can crash the same way, fix it (app or test), with a repro under load.

## Cause

**A Python-owned widget, freed by the cyclic garbage collector while Qt polished it.** The widget was the test's
Scripts panel. My Live Scripts change (M3, `a18e4c9`) gave the panel the trigger.

- **Where it crashed.** The CI job's faulthandler trace shows the crash at line 1636. That is the test's first
  `waitUntil`, right after `plot()` and before the test switches any library. So the library switch isn't the
  cause.
- **The native stack** (macOS crash report `python3.13-2026-11-03-030617.ips`): a posted PolishRequest reaches a
  Python-made `QWidget` (`sipQWidget::event`). `QWidget::ensurePolished` then polishes its children. A
  `QLabel`'s polish sets its palette (`QWidget::setPalette`, `setPalette_helper`), and `updateIsOpaque` crashes:
  its `setDirtyOpaqueRegion` walks up a freed parent chain.
- **What frees it.** `test_live_plots.plot()` (and about 40 other test sites) builds `TreePanelWidget(window.plots)`
  with no Qt parent, so Python owns it. pytest-qt's `addWidget` holds it only weakly, and its run buttons'
  closures keep it in a reference cycle, so it is cyclic garbage from the moment `plot()` returns. A scratch
  plugin that keeps (`gc.DEBUG_SAVEALL`) what the collector finds during each test lists exactly this one
  Python-owned widget, `TreePanelWidget(labels=['ElidedLabel:ss', 'QLabel'])`, in both tests of the CI sequence.
- **What runs Python mid-polish.** M3 added `start_note`, an `ElidedLabel` with a style sheet
  (`color: AMBER`). Polishing a style sheet sets the palette, and that sends a PaletteChange to
  `ElidedLabel.changeEvent`, which is Python. Any Python code can start the collector. When it does there, it
  frees the panel in the middle of its own polish. Before M3, nothing in the panel ran Python while it was
  polished.
- **Can the app crash the same way? No.**
  - The app's Scripts panel is held by the main window (`panel_right_bottom_script_selector`), so it is never
    garbage.
  - A user's library switch (`PlotWorkspace.set_plot_result`, `replace_plot_content`) never makes the replaced
    widget Python's. `setParent(None)` leaves its C++ object alive, hidden and not Python-owned until its
    `deleteLater`; only its Python wrapper goes. A destroyed-signal trace showed the C++ object deleted only by
    the deferred delete.
  - I first changed `workspace.py` to keep replaced widgets under a hidden holder. That fixed nothing, so I
    reverted it, and kept a guard test of the guarantee instead.

## Fix

`helab/views/plots/script_tree.py`: `start_note` is amber through its palette, set once at construction, not
through a style sheet. Nothing in the panel runs Python while it is polished now, so no collection can happen
inside its polish, whoever drops the panel.

## Tests (each run on `f534ede` too)

| Test | On `f534ede` | Now |
|---|---|---|
| `test_live_scripts.py::test_a_dropped_scripts_panel_survives_a_collection_in_its_first_polish`: runs the CI test in a nested pytest, with a plugin forcing `gc.collect()` in every `ElidedLabel.changeEvent` | **SIGSEGV (−11) every time**, with the native stack identical to CI's (crash report `python3.13-2026-11-03-032504.ips`) | passes |
| `test_live_scripts.py::test_the_panels_polish_runs_no_python_code`: no PaletteChange or StyleChange reaches `ElidedLabel` while the panel is polished; the note is still amber | fails | passes |
| `test_live_plots.py::test_a_replaced_plot_stays_qts_until_its_delete_later`: a guard, by C++ address. The replaced widget is alive, hidden and not Python-owned after the switch, out of the dock, and gone after the deferred delete | passes (the guarantee already held) | passes |

`repro_gc_mid_polish.py` (this folder) is the plain-PyQt repro: a Python-owned top-level widget in a cycle,
collected while Qt polishes it (a collection forced in a style-sheet label's `changeEvent`). It segfaults with
the same native stack, and given a Qt parent it survives all 200 rounds.

Not reproduced by load alone. These all passed on `f534ede`:
- the test 120 times with `-n 8` and `gc.set_threshold(50, 1, 1)`;
- the CI pair of tests 12 times;
- `test_live_plots.py` 6 times under 4 CPU hogs.

The collection has to land inside the polish, which the nested test forces.

## Checks

- Full suite, `pytest -n 4 --reruns 5 --reruns-delay 1 --basetemp=.ai/temp/pytest`: **9135 passed, 673
  skipped, 1 rerun**. The rerun's reason was
  `tests/test_explorer_convert.py::test_auto_convert_beside_on_a_share_once_confirmed_or_turned_off[off]`:
  `pytestqt.exceptions.TimeoutError: waitUntil timed out in 5000 milliseconds` at `test_explorer_convert.py:114`.
  That is the Converter UX floor's test, not touched here, and it passed on its rerun. It is not in
  known-issues; A~1 below proposes the entry.
- `mypy helab/ --strict`, `mypy tests --strict`, `pyright helab tests`, `mypy helab/ --strict --platform win32`,
  `pyright --pythonplatform Windows helab tests`: all clean.
- CI: run 41483861898 on `34e6452`, success. I read all nine Tests and Converter backends logs. macOS
Tests (1/2) and (2/2) passed 4565 and 4570, Ubuntu 4561 and 4571, Windows 4549 and 4551, and the Converter
backends 866, 866 and 864. Eight logs had 0 RERUN and no crash. **Windows Tests (1/2)** (job 125409160738) had
**1 rerun**: `test_live_plots.py::test_each_plot_keeps_its_scripts_minimum_size[Scatter3D]`, "worker 'gw2'
crashed" ("node down: Not properly terminated"), with no faulthandler output (a native crash), and it passed on
retry. That is an existing known-issues entry (the same test, Windows CI 40808815122, "Likely the QtWebEngine
crash below"): the 3D scatter's Plotly web view, which this change doesn't touch. Add this run to that entry.

## Proposals (provisional)

- **A~1** known-issues: "[ ] `test_explorer_convert.py::test_auto_convert_beside_on_a_share_once_confirmed_or_turned_off[off]`
  reran once (the `waitUntil(control.box is not None)` at :114 timed out after 5 s; the plot-library-crash
  floor's full suite, 2026-11-03); passed on rerun."
- **A~2** A rule for `testing.md` (or AGENTS.md, for the Coordinator): a widget a test makes with no Qt parent
  and drops is freed by the garbage collector at any moment, even mid-polish (a SIGSEGV), whenever Python code
  runs inside Qt's handling of it. So give test-made panels a parent or keep them referenced, and keep Python
  code out of a widget's polish (no style sheets on Python widget subclasses whose `changeEvent` is overridden).
  Optionally, give the ~40 `TreePanelWidget(window.plots)` test sites a parent.
- **known-issues:** the entry Vault proposed ("Live plots' library switch: a main-thread SIGSEGV polishing a
  QLabel of a replaced plot widget") should instead say: a dropped test Scripts panel, garbage-collected
  mid-polish, fixed here.
