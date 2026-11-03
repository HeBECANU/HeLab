# Notes: docstrings and the user manual's frame (`agent/docs-manual`)

## Brief changes from CoCo (2026-11-03, in the terminal)

Addendum for A54.2 (Tony's answers on Ground `736bba6`); steps 1 and 2 unchanged, steps 3 and 4 change:

- **Q54.2 yes:** GitHub Pages, one version per release (mike). The deploy job publishes from the repo
  it runs in (`github.repository`, the workflow's own token), never a hard-coded owner, so
  HeBECANU/HeLab gets its own site. Deploy only on a release (the release/tag event the release
  workflow uses), never on a dev push and never from this floor. `mkdocs build --strict` on every
  push stays (step 3). Enabling Pages in the repo settings is Tony's: an M~ item.
- **Q54.3 yes:** the built manual goes in the PyInstaller bundle (HeLab.app, the Windows build),
  and stays out of the source package (as `_build_info.json` does).
- **Q54.4 decided (a)** (Ground `64c506b`): Help › User manual opens the site of the repo the build
  came from, at the running version's page; the repo is recorded at build time with the build
  info, never read from git at runtime. It falls back to the bundled copy when the site can't be
  reached, straight away when running from source without a bundle, and then to the docs' GitHub
  page. Always the system browser.
- **New owned paths:** `HeLab.spec`, `.github/workflows/ci-build.yml`, and the release workflow file
  for the deploy step.

## Step 1 (A54.1)

- Modules: `helab/scripts/base.py`, `helab/analysis/dataset_view.py`, `parameters.py`,
  `selection.py`, `fits.py` (scripts import `FitResult`, `bin_centres`, `fit_histogram`) and
  `profiles.py` (the DLD basic plots import `AxisFit`, `fit_axis` and more from it: also a fit
  helper scripts use).
- Docstrings only. In `dataset_view.py` no existing comment or field line was touched (Prio edits
  them); its fields are described in the class docstrings' `Attributes:` sections, so the field
  comments there now repeat part of it. A clean-up after Prio lands could drop them.
- Module constants scripts read got attribute docstrings (a string under the assignment), which
  mkdocstrings shows.
- The check: `ruff.toml` at the root (no `pyproject.toml` in this repo), `select = ["D1"]`,
  ignoring D105 (magic methods) and D107 (`__init__`), with `include` listing the six modules, so a
  bare `ruff check` checks exactly those. `ruff` is in a new `requirements-docs.txt` (direct) /
  `requirements-docs.lock` (pinned, compiled with `-c requirements.lock`); the app's requirements
  and the PyInstaller build don't change.
- CI: a "Docs" job in `dev-cicd.yml` (Ubuntu, 10 min, beside the tests, not in the release gate)
  runs `ruff check`. Step 3 adds `mkdocs build --strict` to it.
- Not in scope, worth a follow-up: `helab/analysis/results.py` (`AnalysisContext`,
  `AnalysisResult`, which every script uses) has 14 D1 gaps; the API reference will want it.
