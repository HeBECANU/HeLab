# Versioning, building and CI

Reference detail for agents working in this area. It moved here verbatim from `AGENTS.md` on
2026-10-28, when AGENTS.md was cut to rules and a map ([index](README.md)). AGENTS.md keeps the
rules every task must follow; this file keeps the mechanics, names and behaviour. Keep it true:
on Ground, update it in the same commit as the code; on a floor, propose the change in your handoff. Settled decisions and Tony's wording live in
`.ai/memory/results/`; feature plans in `roadmaps/`.

## Building

The `.spec` file produces `HeLab.app` on macOS (bundle ID `au.edu.anu.he-bec-lab`).

`helab/main.py` dispatches in this order, each before anything that starts GUI services, caches
or Dash: `multiprocessing.freeze_support()` (frozen only, so the converter's worker pool can spawn,
A12.1), the I/O helper (`--helab-io-helper`), the headless converter (`convert`, [converter](converter.md)),
`--version`, then the GUI.

**The bundled manual** (Q54.3; Docs floor, landed `b0e3aac`): the Python 3.13 Build jobs build the user
manual offline (`HELAB_DOCS_OFFLINE=true`, Material's offline plugin) into `build/manual`, in their own
`build/docs-venv` (both ignored by Git, so the build stamp stays clean; never the app's venv). `HeLab.spec`'s
`user_manual()` bundles it as `helab/manual` (from `HELAB_MANUAL_DIR`, else `build/manual`), appended to
`a.datas` after `Analysis` so `datas=` stays the plain list `test_spec_datas.py` reads; without it the spec says
so and builds without it. "Check the packaged app has the user manual" fails a build that lacks it, so a
strict-build warning in the manual fails the release builds too. A commit from before the manual (a recovery
build of an older tag) builds without it. Compatibility builds ship without it. The source package never holds
`helab/manual` (`test_source_package_has_no_bundled_manual`).

## Versioning

**Versioning:** `helab/_version.py` is the only editable version source (PEP 440,
no `v` prefix). Branch names need not match it. `helab/build_info.py` writes
`_build_info.json` into PyInstaller/wheel build output; never generate it in the
source package. Runtime uses that stamp, or Git explicitly rooted in the package's
own checkout, never the launch directory. Help → About HeLab shows provenance.
CI stamps record the explicit source branch/build ref (`HELAB_BUILD_BRANCH`,
`HELAB_BUILD_REF`, set by `ci-build.yml`; else GitHub's own ref variables) without
replacing Git HEAD.
`BuildInfo.repository` ("owner/name") is stamped by `write_build_info` at build time only: from
`HELAB_BUILD_REPOSITORY`, else `GITHUB_REPOSITORY` in Actions, else the checkout's GitHub `origin`
(`build_repository`). It is never read from Git at runtime, so a source run has "unknown", and an older or
malformed stamp reads as "unknown". About shows it; Help › User manual uses it to find the build's site
([app-runtime-and-ui](app-runtime-and-ui.md#ui)).
Put a release-version bump on the PR branch before final approval. A squash merge
to `main` with a new version triggers CI tagging and a draft release after required
checks pass; publication remains manual. An existing tag with an incomplete draft
is recoverable: rebuild/test that tagged SHA, validate clean archive stamps before
tagging/uploading, preserve manifest-verified assets and never modify a published
release or force-move a tag. See `roadmaps/app-versioning.md`.

## CI

`.github/workflows/dev-cicd.yml` runs required Python 3.13 test/build matrices on
macOS, Windows and Ubuntu for every branch push and PR to `main`. A push to a
branch with an open PR to `main` runs only the detection job, since the PR's own
run tests the same commit (if the PR lookup fails, everything runs). Separate
Python 3.11, 3.12 and 3.14 compatibility matrices run only on PRs to `main`,
with soft failures. `ci-test.yml` has two independent jobs per OS and Python (converter stage 4,
2026-10-29): "Converter backends" (20 min) builds and requires cython (`native/build.py --ci`,
`HELAB_REQUIRE_BACKENDS=cython`) and runs the converter tests that use a backend, listed by hand
(`tests/test_convert_backend_*.py`, `test_convert_required_backends.py`, `test_convert_helab.py`,
`test_convert_split.py`, `test_convert_testdata.py`, and since caching v2's checkpoint 2 `test_raw_layer.py`,
the raw layer's layer-equals-file proof, so cython is proved there only; a new test that runs every
available backend joins the list); "Tests" runs the
whole suite in three groups for the required 3.13 jobs, each a job of its own ("Tests (1/3)", "Tests
(2/3)", "Tests (3/3)"; Quick Fixes 9, `9787e35`; two groups before, Q16.2, A17.2, and still for PRs'
compatibility jobs): `pytest --test-group N/3` (see [testing](testing.md)); the caller's result, which the
release gate needs, fails if any group does, and each macOS group uploads coverage for Codecov to merge.
A Tests job's limit is 30 min on Windows and 20 elsewhere, and pytest runs with `--session-timeout`
1200 s and 720 s (`457debc`), so it stops itself between tests, with its summary, rerun reasons and
junit.xml, before the runner would cancel the job. The
Tests jobs install the lock without Cython, nothing built (a `pip list` guard fails the job if a
backend package is present). The build job builds them (`build.py --ci`) before PyInstaller and checks the
app after (`check_build.py --frozen`); its timeout is 25 min. `HELAB_REQUIRE_BACKENDS` reaches later
steps through `$GITHUB_ENV`, so in the build job it also applies to "Test the older tagged commit
before rebuilding recovery assets" (skipped, and the variable unset, for a tag from before
`native/build.py`). Runners need a C compiler (MSVC on `windows-latest`). Group times on the first
run (40803552596, pytest step): Windows 11:02 and 10:02, macOS 4:09 and 4:52, Ubuntu 2:56 and 5:09; with
three groups (41481668334): Windows 8.9, 10.0 and 9.8 min, macOS 1.6, 6.1 and 4.7, Ubuntu 3.0, 3.5 and 3.4. Shared steps live in `ci-test.yml` and `ci-build.yml`, with
Codecov uploads. Builds are uploaded (`upload`) only in a run that releases, for the release job; test
results go to Codecov, and each Tests job keeps its `junit.xml` as an artifact for 7 days whatever its
outcome (`5324a7f`, `if: always()`; `junit-<os>-py3<minor>-group-index-<N>`, index 0 being group 1). Compatibility matrices expand on pushes, but pass `enabled: false`
to the called jobs, recording individual skips without starting runners. All
matrices disable fail-fast; required failures do not cancel
other OS tests/builds. All four matrices depend on branch/version selection;
release waits for all four, but only required matrices and version selection
must succeed (compatibility skips/failures are non-blocking). A new package
version on `main` creates an explicit tag and a draft
release; tag pushes do not
trigger releases. `python -m helab.release` validates/selects the version in CI.
`python -m helab.release_draft` validates archives and resumes draft uploads; GitHub lists
a draft under tag `untagged-<hash>`, so `get_release` also matches a draft by its name
(`release_name`: "Automated Release <tag>"), and two such matches raise. Each archive needs a regular
`helab/_build_info.json` with the release's version and commit, built clean; a stamp stored as a
symlink is followed and must lead to another stamp (the macOS zip keeps HeLab.app's links, and since
the cython kernel ships, `Contents/Frameworks/helab/` links its data files to `Contents/Resources/`;
0.0.7a1's release job stopped on one, run 41110274554). API
errors fail selection; they never mean "no release". Only authenticated main runs
query release state. Every Python 3.13 build also checks its own archive (`release_draft --check ARCHIVE
--commit SHA`, the stamps against `inputs.build-sha`, no tag or draft; A39.1, `c201c01`): the macOS zip with
`ditto`, Windows and Ubuntu `dist/HeLab` zipped with `python -m zipfile -c`, which follows links as the
artifact's copies do; skipped when `build-sha` isn't `github.sha` (a recovery build of an older tag, which
the release job still validates). Build jobs may target an older tagged SHA during recovery;
the normal test jobs still check the current workflow commit, and recovery builds
add Python 3.13 tests of the tagged commit on each OS.

**The Docs job** (A54.1, A54.2; landed `b0e3aac`): one Ubuntu job in `dev-cicd.yml` (10 min), beside the
tests; it needs only `get-version`, nothing needs it, and it is not in the release gate (it does block a
floor's landing, which needs every job green). It installs `requirements-docs.lock` (developer tools only:
ruff, mkdocs-material, mkdocstrings[python], mike; compiled with `-c requirements.lock`, never in the app's
requirements or its PyInstaller build), runs `ruff check` (D1 on the modules `ruff.toml` lists), then
`mkdocs build --strict` into `$RUNNER_TEMP/site`, and checks the install page links the building repo's
releases. It publishes nothing.

## The manual's site

`.github/workflows/docs-site.yml` (Q54.2; DM-1 (a), Tony 2026-11-03) is the only workflow that runs mike or
touches `gh-pages` (`tests/test_docs_workflows.py`). It runs only on `release: published`: the release job makes
a draft, which stays private until it is published by hand, so the site follows publishing and an abandoned draft
never deploys. It checks out `refs/tags/<tag>`, and mike deploys `<version>` (the tag without `v`, so
`BuildInfo.version`) with the alias `latest`, set as the default, to the running repo's `gh-pages`
(`github.repository`, so `HeBECANU/HeLab` publishes its own site). A commit without `mkdocs.yml` or
`requirements-docs.lock` skips with a notice and stays green. Concurrency group `helab-docs-site`, not
cancelling; 15 min; `contents: write`. A `release` event runs the workflow file of the released tag's commit, so
the first release whose tag contains `docs-site.yml` is the first to deploy. GitHub Pages must be turned on in
the repo's settings, source `gh-pages` (M56.2).

The pages link their own repository: `{repo_url}` in a page becomes `repo_url` (`HELAB_DOCS_REPO_URL`, set to the
building repo in CI; `mkdocs.yml`'s fallback for local builds), through `docs/hooks/repo_links.py`, which
`exclude_docs` keeps out of the site.

## Dependency graph

`.github/workflows/dependency-graph.yml` (weekly, by hand, and on pushes to `main` that
change `requirements.lock`, `helab/dependency_snapshot.py` or the workflow) runs
`python -m helab.dependency_snapshot --submit`, which sends `requirements.lock`'s exact
versions to GitHub's dependency graph through the dependency submission API (standard
library and `gh`; packages the lock marks `via -r requirements.txt` are direct, the rest
indirect), so Dependabot alerts cover what HeLab installs: Dependabot itself reads only the
unpinned `requirements.txt` (Q6.4). Without `--submit` it prints the snapshot.
