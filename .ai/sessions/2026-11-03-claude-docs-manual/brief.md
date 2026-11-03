# Brief: docstrings for the script API and the user manual's frame (`agent/docs-manual`)

Coordinator: CoCo, 2026-11-03. Tony (Chat, via Side, 2026-11-03): "do (a) and (b) now, before PR". The source is
block 54 (Ground `c0daa9f`):

- **Q54.1** is decided: do both before the v0.0.8 PR.
- **A54.1** (docstrings plus a check) and **A54.2** (the manual's frame) are in `.ai/AI_TODO.md`.
- **Q54.2** (GitHub Pages) and **Q54.3** (an offline copy in the app) are still open.

One Worker; one Reviewer at landing.

**Areas:** `docs` (the manual, its CI job and its dependencies) and `app` (Help › User manual). You also edit
**docstrings only** in the analysis and script modules below.

The TXY Priority floor (Prio) changes `helab/analysis/dataset_view.py` (`txy_choice`, identities),
`helab/analysis/presets.py` and a menu item in `helab/views/HelabMainWindow.py`. To keep merges clean:
- in those files, change docstrings only (and the Help menu's new item);
- **A54.1 lands first, as its own checkpoint**, so Prio can merge it early.

## Read first

- `AGENTS.md`;
- A54.1, A54.2 and Q54.1–Q54.3 in `.ai/AI_TODO.md` and `.ai/DECISIONS_TODO.md`;
- `helab/scripts/base.py` (the script contract);
- `.ai/architecture/plots-and-scripts.md` and `release-and-ci.md` (the CI layout: `.github/workflows/dev-cicd.yml`,
  `ci-test.yml`, `ci-build.yml`);
- the README's setup and dependency notes (`requirements.txt` direct, `requirements.lock` pinned);
- `docs/hlb-format.md`, which is already a public page.

## Base and branch

Base `c0daa9f` (`dev/v0.0.8`). Branch `agent/docs-manual`.

## Objective (in this order; commit each separately; stop and report to CoCo at each ◆)

1. **A54.1, docstrings:** every public name in:
   - `helab/scripts/base.py`;
   - `helab/analysis/dataset_view.py`: `DatasetView` itself, `name`, `short`, `key`, `shot_numbers`,
     `event_count`, `ViewIdentity`, `Provenance`, and the rest that is public;
   - `helab/analysis/parameters.py` and `selection.py`;
   - the fit helpers scripts use (`fits.py`; check what `helab/scripts/` imports).

   Use Google style, with `Args:`/`Returns:` only where they add to the types. Change **no code**: no signature,
   rename, reorder or behaviour change. A check keeps it: ruff's `D1` (pydocstyle) on those modules only, in CI
   and runnable locally, configured where ruff config fits this repo; say where in the commit.
   - ruff is a new developer dependency. Propose how it is installed (a docs/dev requirements file, or the lock)
     and keep the app's runtime requirements unchanged.

   Run the suite and the five type checks.

   ◆ **checkpoint 1: lands first.** `maestri ask "CoCo" "Docs: A54.1 at <hash>, suite <N>, RERUNs <…>"`.

2. **A54.2, the manual's frame:**
   - MkDocs with the Material theme: `mkdocs.yml` at the root, pages in `docs/`, keeping `docs/hlb-format.md` in
     place and linked.
   - Diátaxis sections: getting started, how-to, reference, explanations.
   - An **API reference for script writers**, built by mkdocstrings from A54.1's docstrings.
   - First pages, written for users from `.ai/architecture/`, the memory notes and the README: install and first
     folder; `.helab-root`; Live; converting TXY; writing a script; the cache; `helab convert` / `helab cache`;
     the settings. Keep them short and true to the code at your base. Where behaviour is changing on another
     floor (the TXY source lists: block 53, `roadmaps/txy-priority.md`), write a short placeholder that says so;
     don't describe the old four modes at length.
   - **Public text:** the repo is public. Name no person, no lab machine and no internal host or path. Nothing
     from `.ai/local/` or `.ai/sessions/`.
   - The docs dependencies (mkdocs-material, mkdocstrings[python]) are developer-only, pinned, outside the app's
     runtime requirements and its PyInstaller build.
3. **CI:** a job that builds the manual with warnings as errors (`mkdocs build --strict`) on one OS, plus the D1
   check. It must not slow the test jobs. **No deploy or publish step:** Q54.2 is open.
4. **Help › User manual:** opens the manual in the **system browser**, never a QtWebEngine view (the Side PC's
   can't draw). Until Q54.2/Q54.3 are answered, the target is a single constant: the manual's page on GitHub at
   this repo's default branch. Leave the seam where Q54.2's versioned site or Q54.3's bundled copy plugs in.
   It needs an accessible name and an ID, and a test.
5. **Docs proposals** in the handoff (`release-and-ci.md` for the CI job, `plots-and-scripts.md` for the API
   reference, AGENTS.md's one line for the docstring check, the README's docs build command), with provisional
   `Q~`/`A~`/`M~` items (M~ for Tony to read the first pages).

## Rules

**Owned paths:**
- `docs/**` and `mkdocs.yml`;
- the ruff config, and a new developer requirements file if you choose one;
- `.github/workflows/*` (the docs job and the D1 step only);
- docstrings in the step 1 modules;
- the Help menu's new item in `helab/views/HelabMainWindow.py`;
- the README's docs section;
- their tests.

Ask CoCo before any other file.

- Strict typing, including `--platform win32` and `pyright --pythonplatform Windows`.
- Tests never touch real data.
- Before each ◆ and the handoff: the full suite (`-n` with `--reruns 5 --reruns-delay 1`) and the five type
  checks, with every RERUN reported.
- Docs about this work go in `.ai/sessions/2026-11-03-claude-docs-manual/`.
- Push at checkpoints only. Before reporting a CI run, read every Tests and Converter backends job's log (and the
  new docs job's) for RERUN.
- No version bump, release, tag, PR or Pages deploy.

When done: `maestri ask "CoCo" "Docs: done at <hash>, suite <N> passed, RERUNs <…>, CI <run>"`.
