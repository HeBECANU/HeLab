# Review: A54.1, docstrings for the script API: `git diff c0daa9f..4c47227` (agent/docs-manual)

Reviewer: Assay (Claude Opus 5.5), 2026-11-03. Read-only on code. This is a landing review of another floor's branch.

- **Base:** `c0daa9f` (Record block 54).
- **Head:** `4c47227` (A54.1), which is `origin/agent/docs-manual`'s tip. `f14bd2f` (the brief) is session files only.

**Verdict: no blocker. 3 findings: 0 High, 0 Medium, 3 Low, all open.**
- All three are docstrings that are true as far as they go but leave out a case a script writer can hit.
- The change is docstrings only: proved on the syntax trees, below.
- The ruff scope, the docs requirements and the CI job are as claimed.

## Findings

### D-1 · Low · `ScriptMetadata.file_hash` is not always "SHA-256 of the script file"

- **Where:** `helab/scripts/base.py:54` ("SHA-256 of the script file as loaded (set by HeLab; "" if unreadable)").
- **Scenario.** A user's script folder has a helper module its scripts import (D1, L4).
  - `ScriptsManager._fold_helper_hashes` (`helab/scripts/scripts_manager.py:359-369`) replaces every script's
    `file_hash` in that folder: it becomes the SHA-256 of the file's hash and each helper's path and hash.
  - A script writer who checks a result's recorded hash against `sha256sum my_script.py` finds a mismatch. The
    reason is not in the API reference.
- **Fix.** Add one line: "…; with helper modules in the folder, a hash of this and every helper's hash
  (``ScriptsManager._fold_helper_hashes``), so a helper's change counts too".
- **How verified:** by reading `_register_module` (`metadata.file_hash = digest`, from `identity.file_hash`, the
  bytes' SHA-256) and `_fold_helper_hashes`.

### D-2 · Low · `ViewIdentity.source` doesn't say the two priority modes are both ""

- **Where:** `helab/analysis/dataset_view.py:89` ("source: Which TXY the data is made of
  (``txy_sources.identity_source``)").
- **Scenario.** A script reads `view.identity.source` to tell HeLab priority data from MATLAB priority data.
  - Both give "" (`txy_sources.identity_source`, `helab/utils/txy_sources.py:191-195`). Only HeLab only and MATLAB
    only are named.
  - The shots' `origins` are what tell priority data apart.
  - The field's own comment says so ("'' for the priority sources, else the source's name"); the new docstring
    dropped it.
- **Fix.** "Which TXY source the data is made of: "" for the two priority modes (``origins`` tells their shots
  apart), else the mode's name (``txy_sources.identity_source``)."
- **The class docstring holds:** "another TXY choice or another profile is another identity" is true. Every load
  gets its own `chain` token (`build_view`'s `uuid4`), and `revise` never revises across choices (`same_choice`).
  The module docstring already explains this.

### D-3 · Low · `DatasetView.revision` and `added_shots` leave out replaced shots

- **Where:** `helab/analysis/dataset_view.py:155` ("revision: … one more each time Live adds shots to it") and
  `:161` ("added_shots: The shots this revision added to the previous one").
- **Scenario.** A script keeps a running total across Live's revisions by adding the events of
  `view.added_shots`. Two kinds of revision break that:
  - **Replaced shots.** `revise` (`:431-459`) also makes a revision when a shot already shown has a new fingerprint
    (its TXY file was rewritten), or now comes from the other kind of TXY or another profile. Those shots are in
    `added` and so in `added_shots` (`with_shots`: "added (new or replaced shots)", `:258`). The running total
    counts them twice.
  - **Times only.** A revision may also add no shot at all, only shot times found for shots already shown
    (`filled`, `:453`).
- **Fix:**
  - revision: "one more each time a newer load (Live's) adds or replaces shots, or finds their raw files' times";
  - added_shots: "The shots this revision added or replaced (a replaced shot's array is new)".
- **How verified:** by reading `revise` and `with_shots`. The callers are `live_feed.py:41` and
  `views/plots/instance.py:1244`.

## Checked, no finding

### Docstrings only

For each of the 6 Python files, I compared the parent's and the head's syntax trees (`ast.dump`, without
attributes) with every bare string statement removed. These are module, class and function docstrings, and the new
attribute docstrings after a field or constant.
- All 6 are **identical**: no code, signature, default, decorator or import changed.
- The only removed lines in `helab/` are the 7 one-line docstrings that were expanded.
- `__doc__` of these modules is read nowhere in `helab/`. Only the CLI modules use their own `__doc__`, for argparse.
  So no UI text changes.

### The docstrings against the code

Everything else I checked holds. Highlights:

**`base.py`**
- The module's run order: `compute` on the worker thread with an `AnalysisContext`, then `render` on the GUI
  thread.
- `script_id`: `<file path>::<class qualname>` (`scripts_manager.py:452`).
- `name`: the panel item and the dock title (`script_tree.py:823`, `instance.py:183`).
- `description`: the panel tooltip (`script_tree.py:824`).
- `identity()`'s fallback order.
- `parameters`: the values reach `context.parameters` through `effective` → `ParameterSpec.coerce`
  (`runner_core.py:91`).
- `compute`'s return value is `AnalysisResult.data`.
- `execute_action`'s ValueError. It is also raised for a `context` of the wrong type: a nit.
- No Qt imported at run time: `QWidget` is under `TYPE_CHECKING`.

**`parameters.py`**
- `coerce`: clamping, and a choice outside `choices` becoming the default.
- `when` and `shown_with`, `unit_prefix`, `SI_FACTORS`.
- `Value` is a JSON scalar.

**`selection.py`**
- `SHOT_SPECS`, `newest_colour`'s red fallback.
- `HIGHLIGHT`/`NEWEST_COLOUR` are the `newest_specs` names.
- `BOUNDS` and `FIXED_BOUNDS` (`unit_prefix` None / "m").
- `SI_PREFIXES` largest first; `keep_fraction`.

**`fits.py`**
- `Role`'s four values and their scaling; `names` order; `__call__`.
- `reduced_chi2` is nan at dof 0.
- `thomas_fermi_area`: ∫₋₁¹(1−u²)ᵖ du = √π Γ(p+1)/Γ(p+3/2), which is 16/15 at p = 2.
- `thomas_fermi`'s powers: 2 for a full projection, 3/2 for a thin slice.
- `arrival_time`: `sigma` = σ_v/g, since the exponent is v/(g·σ), and only the offset where t ≤ 0.

**`profiles.py`**
- `Smoothing.apply`, `AxisFit.ok` and `.failure`.

**`dataset_view.py`**, besides D-2 and D-3:
- `Provenance`'s fields match their comments.
- `origins` leaves MATLAB's shots out.
- `txy_choice` "" means MATLAB's TXY alone.
- `chain` is not in the reuse key.
- `Held.of`.

### The ruff config's scope

`ruff check` (ruff 0.17.3, the lock's) was run from the export's root:
- **The scope is exactly the 6 files.** `--show-files` lists only them.
  - Neither nested `pyproject.toml` (`native/rust`, `side_projects/labcam`) has a `[tool.ruff]`, so no other
    config is picked up.
- **At the head it passes** (exit 0).
- **It has teeth:** on the parent's 6 files with the same config it fails with 29 errors (D100 ×1, D101 ×5,
  D102 ×15, D103 ×8).
- **What D1 doesn't check:** the module-level attribute docstrings (constants, aliases), which pydocstyle never
  checks. They are written but not enforced. D105 and D107 are ignored, as claimed.

### The docs requirements stay out of the app

- `requirements-docs.txt` holds only `ruff`. `requirements-docs.lock` pins `ruff==0.17.3`, compiled with
  `-c requirements.lock`.
- **No app or build file names either file or ruff:**
  - `requirements.txt` and `requirements.lock`;
  - `setup.py`'s `install_requires`;
  - `HeLab.spec`;
  - `dependency-graph.yml` and `dependency_snapshot.py`, which send only `requirements.lock`;
  - `test_shipped_backends`' requirement checks.
- Nothing in `helab/` imports ruff, so PyInstaller can't collect it.

### The CI job

- **It can't block or slow the test jobs:** `docs` needs only `get-version` and nothing needs `docs`. It runs on
  its own ubuntu runner, with a 10-minute timeout.
- **It has the same `covered_by_pr` skip** as the other jobs, and the same `checkout@v7` and `setup-python@v7`.
- **It is not in the release gate:**
  - `release` needs `get-version`, `required-tests`, `required-builds`, `compatibility-tests` and
    `compatibility-builds`;
  - its `if:` reads only `get-version`, `required-tests` and `required-builds`;
  - `helab/release*.py` queries no job results.
- **Process note, not a finding:** AGENTS.md's landing rule ("every job" green) makes a red Docs job block a
  floor's landing. That is presumably the intent ("a public name without one fails CI").

## Checks (run by the reviewer)

On an export of `4c47227`, with testdata linked:
- `pytest -n 4 --reruns 5 --reruns-delay 1 --basetemp=.ai/temp/pytest-assay`: **9179 passed, 674 skipped, 2
  warnings, 3 failed, 15 rerun in 184.86 s.**
  - All 3 failures and all 15 RERUNs are the three git-provenance tests, 5 reruns each. They fail only because the
    export has no `.git`:
    - `test_release_recovery.py::test_detached_pr_stamp_records_source_branch_and_merge_ref_without_replacing_commit`;
    - `test_versioning.py::test_frozen_metadata_survives_no_git_and_unrelated_cwd`;
    - `test_versioning.py::test_source_provenance_ignores_launch_directory`.

    They passed in this floor's checkout with no RERUN earlier today, and A54.1 doesn't touch them.
  - No other RERUN.
  - The 2 warnings are the known pyqtgraph ones.
- **Type checks:**
  - `mypy helab/ --strict` (204 files), `mypy tests --strict` (201), `--platform win32`: no issues;
  - `pyright helab tests` and `--pythonplatform Windows`: 0 errors.
- `ruff check` (0.17.3): passes at the head; 29 errors on the parent's files (above).
- The syntax-tree comparison script is scratch, not committed.

## Re-check of the fixes (`git diff 4c47227 9631294`, agent/docs-a54-1)

**Open findings: none.** D-1, D-2 and D-3 are closed, and nothing new. `9631294` descends from `4c47227` and changes
only `helab/scripts/base.py` and `helab/analysis/dataset_view.py`.

- **Still docstrings only:** with bare strings removed, both files' syntax trees are identical to `4c47227`'s.
- **D-1: closed.** `file_hash` now says that with helper modules in the folder it is a SHA-256 of the file's hash
  and every helper's path and hash, so it differs from the file's own SHA-256. This matches
  `_fold_helper_hashes`.
  - **Nit, not a finding:** the folded helpers are those imported now or seen imported before
    (`_know_helpers`), and an unreadable file's "" is folded too. Neither matters to a script writer.
- **D-2: closed.** `source` now says "" for the two priority modes (the shots' `origins` tell them apart), else the
  mode's name. This matches `txy_sources.identity_source`.
- **D-3: closed.**
  - `revision` now counts a newer load that adds or replaces shots, or only finds raw-file times.
  - `added_shots` now includes replaced shots (rewritten TXY, or from another TXY) and is empty for a times-only
    revision. Both match `revise` and `with_shots`: `added` is `{}` when only `filled`.
  - The running-total advice is right.

### Checks (re-check)

On an export of `9631294`:
- `ruff check` (0.17.3): all checks passed.
- `mypy --strict` and `pyright` of the two files: no issues, 0 errors.
- The full suite, `-n 4 --reruns 5 --reruns-delay 1`: **9179 passed, 674 skipped, 2 warnings, 3 failed, 15 rerun.**
  - All 3 failures and all 15 RERUNs are the three git-provenance tests, 5 reruns each, because the export has no
    `.git`.
  - No other RERUN.
  - The totals equal `4c47227`'s, as a docstring-only change should give.
