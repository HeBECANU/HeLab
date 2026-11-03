# Handoff: docstrings for the script API and the user manual (`agent/docs-manual`)

Worker: Claude (Opus 5.5) on the Docs floor, 2026-11-03. Brief: `brief.md`; running notes and CoCo's
answers and addenda: `notes.md`. Base `c0daa9f`.

## What landed on the branch

| Commit | What |
|---|---|
| `4c47227` | **A54.1** docstrings for the script-facing API; `ruff.toml` (D1 on those modules only); `requirements-docs.txt`/`.lock`; the Docs CI job. CI run 41586073532: every job green, no RERUN in any of its 16 job logs. |
| `9631294` | A54.1 review fixes D-1..D-3 (Assay), made on `agent/docs-a54-1` from `4c47227`, fast-forwarded here. |
| `9507d02` | **A54.2** the manual: `mkdocs.yml`, `docs/` in Diátaxis sections, the API reference (mkdocstrings), eight first pages, `hlb-format.md` cleaned, README section, `/site/` ignored; public-safe module docstrings in `fits.py` and `profiles.py`. |
| `3462828` | CI: `mkdocs build --strict` in the Docs job; `docs-site` publishes with mike after the release job (moved to publish-only by `d0128ae`). |
| `0ab9c87` | `helab cache --help` names no one (explicit `DESCRIPTION`); `tests/test_cli_help.py`. |
| `662a287` | Help › User manual (Q54.4 (a)): site → bundled copy → GitHub page, async check; `BuildInfo.repository` stamped at build time; the manual bundled by `HeLab.spec` from `ci-build.yml`'s offline build (Q54.3). |
| `c8d400c` | Script loader: the module is in `sys.modules` only while its file runs, so `from __future__ import annotations` + `@dataclass` loads; the manual's warning replaced by the `get_type_hints` note. |
| `d0128ae`, `17239e0`, `ee6df99` | Assay's Docs review: DM-1 the site deploys from its own `docs-site.yml` on `release: published` only (option (a); Tony's call, CoCo asking); DM-2 that deploy skips a commit without the manual; DM-3 the pages link the building repo through `{repo_url}` (`docs/hooks/repo_links.py`). `tests/test_docs_workflows.py`. |
| `3b5a324`, `70a7248` | `HeLab.spec` fixes to `662a287`: the manual goes into `a.datas` after `Analysis` (a `Tree`), so `datas=` stays the plain list `test_spec_datas.py` reads; `Tree` imported, so `test_versioning.py`'s run of the spec works with `build/manual` present. |

**Still to do on this floor (CoCo):** `helab/analysis/results.py` docstrings (`AnalysisContext`,
`AnalysisResult`; 14 D1 gaps) and its entry in `ruff.toml` and the API reference, after TXY Priority
lands and this branch has merged `dev/v0.0.8`.

## Checks

- Full suite (`pytest -n 4 --reruns 5 --reruns-delay 1 --basetemp=.ai/temp/pytest`) at `70a7248`:
  **9206 passed, 673 skipped, 2 warnings (the known pyqtgraph ones), no RERUN.**
- **RERUNs on the way, all caused by this branch and fixed** (not flaky, nothing for known-issues):
  - at `c8d400c`: `test_spec_datas.py`'s three tests, 5 reruns each, failed ("isinstance(<ast.Starred>,
    ast.Tuple)": `662a287`'s `*manual_datas` in `datas=`); fixed by `3b5a324`;
  - at `3b5a324`: `test_versioning.py::test_spec_uses_same_metadata_and_numeric_bundle_fields`, 5 reruns,
    failed ("NameError: name 'Tree' is not defined", only with a local `build/manual`); fixed by `70a7248`.
- `mypy helab/ --strict` (205 files), `mypy tests --strict` (204), `mypy helab/ --strict --platform win32`,
  `pyright helab tests`, `pyright --pythonplatform Windows helab tests`: all clean. `ruff check`: passes.
- `mkdocs build --strict`: passes. The built HTML has no internal IDs, names or `.ai/`/`roadmaps/` paths
  (scanned); the only "TonyXTYan" is the header's repo link, which CI sets to the building repo.
- A local `pyinstaller HeLab.spec` with `build/manual` built: `helab/manual/index.html` is in `HeLab.app`
  (`Contents/Frameworks/helab/manual`, where `PACKAGE_DIR` points) and `dist/HeLab/_internal`; the stamp
  records `"repository": "TonyXTYan/HeLab"`; the source tree has no `helab/manual`.
- The script page's example was loaded through `ScriptsManager` and run under the test conftest (load,
  compute, empty view, cancel, read-only arrays, render/update offscreen, live policy: 5 passed).
- Not run: the `docs-site` deploy (only after a release) and the Windows/Ubuntu bundle (CI's Build jobs
  check it on the next push: "Check the packaged app has the user manual").

## Proposed doc changes (for the Coordinator to apply)

**AGENTS.md** (one line under "Analysis and plots", and the commands block):
- "The script-facing API's public names have docstrings (Google style): ruff's D1 on the modules
  `ruff.toml` lists (`ruff check`, CI's Docs job); a module the manual's API reference documents is added
  there. Docstrings are public text (the manual renders them): no names, internal IDs or `.ai/`/`roadmaps/`
  paths."
- Commands: `uv pip install -r requirements-docs.lock` (docs tools, developer-only), `mkdocs serve`,
  `mkdocs build --strict -d .ai/temp/site`, `ruff check`.
- Code map: `docs/`, `mkdocs.yml`: the user manual (MkDocs Material; API reference by mkdocstrings);
  `helab/utils/user_manual.py`: Help › User manual's targets.

**`.ai/architecture/release-and-ci.md`:**
- CI: the "Docs" job (Ubuntu, 10 min, beside the tests, not in the release gate): `ruff check` then
  `mkdocs build --strict`, with `requirements-docs.lock` (compiled `-c requirements.lock`; never the app's).
- `docs-site.yml` (its own workflow): on `release: published` only (the release job's draft is private
  until published by hand; an abandoned draft never deploys), mike deploys `<version>` (the tag without
  `v`) with alias `latest` (set as default) to the running repo's `gh-pages`; a commit without
  `mkdocs.yml`/`requirements-docs.lock` skips with a notice; concurrency `helab-docs-site`. GitHub Pages
  must be enabled with source `gh-pages` (repo setting). `tests/test_docs_workflows.py` keeps it the only
  workflow that runs mike.
- The pages link their own repository: `{repo_url}` in a page is `repo_url`
  (`HELAB_DOCS_REPO_URL`, the building repo in CI), by `docs/hooks/repo_links.py`; the Docs job checks the
  install page links the building repo's releases.
- Building: the 3.13 Build jobs build the manual offline (`HELAB_DOCS_OFFLINE=true`, Material's offline
  plugin) into `build/manual` in `build/docs-venv` (ignored, so the stamp stays clean); `HeLab.spec`
  bundles it as `helab/manual` (`HELAB_MANUAL_DIR`, else `build/manual`; says so when missing); "Check the
  packaged app has the user manual" fails a build without it. Compatibility builds ship without it.
- Versioning: `BuildInfo.repository` ("owner/name") is stamped by `write_build_info` from
  `HELAB_BUILD_REPOSITORY`, else `GITHUB_REPOSITORY` in Actions, else the checkout's GitHub `origin`;
  never read at runtime; older stamps read as "unknown". About shows it.

**`.ai/architecture/plots-and-scripts.md`:**
- The API reference for script writers (`docs/reference/api/`) renders the modules `ruff.toml` lists;
  `dataset-view.md` names its classes one by one (the module docstring stays out until it is public-safe).
- The loader: a user script's module is in `sys.modules` (`helab.scripts.dynamic.<file name>`) only while
  its file runs (`scripts_manager._importing`), then whatever held the name is put back; an overlapping
  load of one name is refused, not waited for. `typing.get_type_hints` can't resolve a script class's
  string annotations afterwards.

**`.ai/architecture/app-runtime-and-ui.md`:** Help › User manual (`help_user_manual`): always the system
browser; the running version's site on the build's repo's Pages (HEAD check through
`QNetworkAccessManager`, 3 s transfer timeout, no thread; a click during a check adds none), else the
bundled copy, else `github.com/<repo>/blob/HEAD/docs/index.md` (`DEFAULT_REPOSITORY` for a source run).

**Corrections found while writing the manual** (the code is right, the docs are stale):
- `data-roots.md` (Fresh store) says the store is store-v3; from v0.0.8 it is store-v4.
- `cache-store.md` (Caching) "describes store-v3 as built", while Settings › Cache has store-v4's rows.
- `live.md`: the re-read note is "(writer paused past the settle time?)", not "> 5 s"; Live disables "Up
  Dir" (the button's label), not "Up".
- The comment above `STORE_V4_SETTING` in `settings_defaults.py` still says "off until stage 2"; its row
  says on from v0.0.8.

## Provisional items

**Questions for Tony**
- **Q~1 Material for MkDocs reaches end of life on 2027-05-05** (it says so at every build); Zensical, by
  the same team, reads `mkdocs.yml`. **Proposed:** stay on Material for v0.0.8 and try Zensical in 2027
  (CoCo: stay, and ask).
- **Q~2 Which GitHub page a source run opens** when it can't know its repo (no stamp; never Git at
  runtime): `DEFAULT_REPOSITORY` is `TonyXTYan/HeLab`, while the lab's PCs run clones of `HeBECANU/HeLab`.
  **Proposed:** keep TonyXTYan (the site's home); or stamp source runs via an env variable later.
- **Q~3 `latest` follows every published release, pre-releases too** (every release so far is an alpha, so
  otherwise the site would have no front page). **Proposed:** yes until the first final release, then
  only finals.

**Work agents may do (AI_TODO)**
- **A~1** `results.py`'s docstrings and its API page (assigned to this floor, after TXY Priority lands).
- **A~2** `dataset_view.py`'s module docstring public-safe (it names Q6.6, plots-1, plots-3; `root_key`'s
  docstring a person and "codebase review 2, C-15"), after TXY Priority lands; then its API page may render
  the module.
- **A~3** `docs/.ai-generated/` holds three old planning files in the public `docs/` folder (MkDocs skips
  dot-folders, so the site doesn't show them): move them to `.ai/sessions/` or delete.
- **A~4** The built-in profiles' notes, shown in Settings › TXY converter, carry internal IDs ("stage 3",
  "Q6.11"): user-facing text.
- **A~5** The stale docs listed under "Corrections" above.
- **A~7 `helab --help` starts the GUI** (Assay): `helab/main.py` handles `--version`, `convert` and
  `cache` before the GUI, but not `--help`/`-h`. Proposed: print a short usage (the app, `--version`,
  `--geometry`, `convert`, `cache`, each with `--help`) and exit 0, before anything starts.
- **A~6** Grow `ruff.toml`'s scope to the rest of what scripts import (`results.py` first, then
  `follow.py`, `backends.py`'s panes, `stats.py`), each with an API page.

**Manual checks (MANUAL_TODO)**
- **M~1 Read the manual's first pages** (`mkdocs serve`, or the CI artifact): install, data root, Live,
  converting TXY, writing a script, command line, settings, cache. Their labels and numbers were checked
  against the code; the wording, the order and what is left out are yours.
- **M~2 Turn on GitHub Pages** on TonyXTYan/HeLab (Settings › Pages › Deploy from a branch: `gh-pages`,
  `/`) once the first published release's `docs-site` run has made the branch; the same on HeBECANU/HeLab when
  releases are made there.
- **M~3 Help › User manual in a release build**: on a networked computer (the site's version page opens
  in the browser), offline or on the lab PC (the bundled copy opens, search works), and from a source run
  (the GitHub page).

## Notes for the reviewer

- In `dataset_view.py` (also changed by TXY Priority) every change is a docstring; no comment or field
  line moved, so its field comments now repeat part of the class docstrings.
- `ruff.toml` lives at the root because the repo has no `pyproject.toml`.
- The loader keeps `test_scripts_folder.py:88-89`'s invariant (nothing left in `sys.modules`).
