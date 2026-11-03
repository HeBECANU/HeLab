# Review: the Docs floor's rest (A54.2, CLI help, script loader): `git diff 9631294..9acc055` (agent/docs-manual)

Reviewer: Assay (Claude Opus 5.5), 2026-11-03. Read-only on code. This is a landing review of another floor's branch.

- **Base:** `9631294` (A54.1 with its fixes, reviewed in `review-a54-1.md`).
- **Head:** `9acc055`.
- **Read first:** the brief and the handoff in `.ai/sessions/2026-11-03-claude-docs-manual/`.
- **Tony's decisions applied:**
  - Q54.2: Pages per release, from whichever repo it runs in;
  - Q54.3: a bundled copy;
  - Q54.4 (a): Help opens the build's repo site, else the bundled copy.

**Verdict: no blocker. 3 findings: 0 High, 1 Medium, 2 Low, all open.**
- DM-1 is a timing question for Tony: the site goes public when the release *draft* is made, not when it is
  published.
- DM-2 and DM-3 are small.
- The rest holds:
  - the bundle;
  - `BuildInfo.repository`;
  - Help › User manual;
  - the loader fix;
  - the CLI help;
  - the public text;
  - the branch's CI.

## Findings

### DM-1 · Medium · The site is published when the release job makes the *draft*, before Tony publishes the release

- **Where:** `.github/workflows/dev-cicd.yml` `docs-site` (`needs: [get-version, release]`, `if: … needs.release.result
  == 'success' && … should_release == 'true'`).
- **Scenario.** A version bump lands on main.
  - `release` runs "Tag tested main commit and create draft release" (`helab.release_draft`). The release stays an
    unpublished draft until Tony publishes it by hand (`release_complete`: "Published releases are immutable to
    this workflow").
  - `docs-site` then runs at once. It deploys `<version>/` to the public Pages site, moves `latest` (the front
    page) to it, and sets it as the default.
  - **Until Tony publishes,** the public site's front page documents a version nobody can download yet. The
    install page's "releases page" still offers the previous release.
  - **If the draft is abandoned** (a bad build; the version bumped again instead), its `<version>/` stays on
    Pages, and `latest` points at it until the next release.
- The brief's ask was "only after a release". In this workflow a release is only a draft until Tony acts.
- **Fix options** (Tony's choice, as Q54.2's detail):
  - (a) publish on GitHub's `release: published` event, in a small workflow that checks out the tag and deploys
    with mike;
  - (b) keep it as it is, and say in Q54.2 that the site goes public with the draft;
  - (c) deploy `<version>/` with the draft, but move `latest` only at publish.
- **How verified:** by reading `dev-cicd.yml`'s `release` and `docs-site` jobs, `helab/release.py`
  (`should_release` only on `refs/heads/main`) and `helab/release_draft.py` (drafts only).

### DM-2 · Low · `docs-site` fails on a recovery run of a tag from before the manual

- **Where:** `dev-cicd.yml` `docs-site`: "Install the docs tools" (`pip install -r requirements-docs.lock`) at
  `ref: release_sha`.
- **Scenario.** The release job resumes an unfinished draft of an older tag (`plan_release`: `recovering`, the
  tag's own commit).
  - `docs-site` checks out that commit. If it predates the manual, it has no `requirements-docs.lock` or
    `mkdocs.yml`, so the job fails red after a successful recovery.
  - `ci-build.yml`'s manual steps guard exactly this ("No user manual at this commit: building without it").
    `docs-site` doesn't.
- **Fix:** the same guard (skip with a notice when `mkdocs.yml` or the lock is missing), or an `if:` on a
  `hashFiles('mkdocs.yml')` check.
- **How verified:** by reading the job and `plan_release`. Not run: the job runs only after a release.

### DM-3 · Low · The install page hard-codes TonyXTYan's releases, though each repo's site is its own (Q54.2)

- **Where:** `docs/getting-started/install.md:56` ("the [releases
  page](https://github.com/TonyXTYan/HeLab/releases)").
- **Scenario.**
  - `HeBECANU/HeLab` publishes its own site (Q54.2: "from whichever repo it runs in"; M~2). Its header's repo
    link is its own (`HELAB_DOCS_REPO_URL`).
  - But its install page sends readers to TonyXTYan's releases, a different repo's builds.
  - The same page clones `HeBECANU/HeLab`, so the page names two repos for one install.
- **Fix:**
  - point at "the releases of this site's repository (the GitHub link at the top of the page)";
  - or render the link from `config.repo_url` (a macros plugin or a small hook);
  - or accept TonyXTYan as the one release source, and say so in Q54.2.
- **How verified:** by grepping `docs/` and `mkdocs.yml` for hard-coded repositories. These are the only two:
  this link, and `mkdocs.yml`'s fallback `repo_url` for local builds.

## Checked, no finding

### Pages deploy

- **Never on dev pushes or PRs:**
  - `docs-site` runs only after `release` succeeds with `should_release`, which `decide_release` gives only for
    `refs/heads/main`;
  - the `docs` job builds into `$RUNNER_TEMP/site` and publishes nothing.
- **Never hard-coded:**
  - mike pushes to the checkout's own `origin` (the running repo);
  - the site's links take `HELAB_DOCS_REPO_URL: ${{ github.server_url }}/${{ github.repository }}`;
  - only `mkdocs.yml`'s local fallback names TonyXTYan.
- **The deploy job's settings:**
  - `permissions: contents: write` at the workflow level;
  - `concurrency: helab-docs-site`, without cancelling;
  - a 15-minute timeout;
  - `fetch-depth: 0`.
- **mike's versions:**
  - `<version>` is the tag without `v`, which is `helab._version.__version__` (`tag = f"v{version}"`);
  - `deploy --push --update-aliases "$version" latest`, then `set-default --push latest`.
  - The version matches what Help builds (`BuildInfo.version`). `latest` on pre-releases is Q~3.
- **No CI loop:** mike's push with the `GITHUB_TOKEN` starts no workflow run (GitHub's rule), so a `gh-pages`
  push doesn't run CI on an HTML-only branch.

### Bundle

- `HeLab.spec`'s `user_manual()` adds `build/manual` (or `HELAB_MANUAL_DIR`) as a `Tree` with the prefix
  `helab/manual`. It is appended to `a.datas` after `Analysis`, so `datas=` stays plain for `test_spec_datas.py`.
  Without the manual it says so and ships without it.
- **Kept out of the source package:**
  - `build/` is ignored;
  - nothing writes under `helab/`;
  - `test_source_package_has_no_bundled_manual`;
  - the export's `helab/` has no `manual/`.
- **CI's Build jobs at the head** (run 41589115583) found it:
  - `dist/HeLab.app/Contents/Resources/helab/manual/index.html` (macOS);
  - `dist/HeLab/_internal/helab/manual/index.html` (Windows, Ubuntu).
- **The manual's own build in CI:**
  - built offline (`HELAB_DOCS_OFFLINE`), in `build/docs-venv`, so neither the app's venv nor the stamp is
    touched;
  - 3.13 builds only. Compatibility builds ship without it, as the handoff says.

### BuildInfo.repository

- **Written only by `write_build_info`,** at build time:
  - from `HELAB_BUILD_REPOSITORY`, else `GITHUB_REPOSITORY` in Actions, else the checkout's GitHub `origin`;
  - each checked against `REPOSITORY` / `GITHUB_REMOTE`.
- **Never read from Git at runtime:** `checkout_build_info` (a source run) leaves it "unknown".
- **Old stamps still read:** a stamp without the field, or with a malformed value, reads as "unknown".
  `test_repository_is_stamped_at_build_time_and_old_stamps_still_read` and `test_github_remotes` cover this.
- About shows it.

### user_manual.py and Help › User manual

- **Asynchronous; the GUI never waits:**
  - a `QNetworkAccessManager.head` with a 3 s transfer timeout, no thread;
  - its `finished` decides;
  - a click during a check adds nothing.
- **The system browser only:** `QDesktopServices.openUrl`, never a web view.
- **The fallback order:**
  1. the site, checked: 2xx/3xx with no error;
  2. else the bundled copy (`file://`);
  3. else `github.com/<repo>/blob/HEAD/docs/index.md`;
  4. with no site at all (a source run, an old stamp), the fallback at once.

  This is Q54.4 (a).
- **Its ID and name:** `setObjectName("help_user_manual")`, the way this window's other menu actions get their
  IDs. QAction's accessible name is its text, "User manual", plus a tooltip.
  `test_menu_item_has_a_name_and_an_id` covers it.
- **The tests are local only:**
  - an `http.server` on 127.0.0.1 answering 200 or 404;
  - the discard port for unreachable.
  - They reach no real host.
- **A note:** no test covers the slow-site timeout path. That path is Qt's own `setTransferTimeout`.

### Loader fix (c8d400c)

- **`_importing` holds `sys.modules[name]` only around `exec_module`:**
  - the `finally` puts back what held the name, or pops it, on success and on failure alike;
  - `_IMPORTING` refuses an overlapping load of one name instead of waiting.
- **Same-named scripts in two folders** each run under the name only while their own file runs, and nothing is
  left after.
- **A reload runs the new file.**
- **Loads run on the GUI thread only:** `_load_script_file`'s one caller is the folder load.
- **`_register_module`** still finds the classes: they have `__module__ == module.__name__`, on the module object
  it holds.
- **Tests:** `test_script_modules.py`'s five tests cover each case. With `test_scripts_folder.py`'s invariant
  (nothing left in `sys.modules`), all passed in a real clone (below).
- **Nit, not a finding:** a name held by `None` in `sys.modules` (a negative entry) is popped rather than put back.
  No script name is ever one.

### CLI help (0ab9c87)

I rendered every help on the export. None names a person or carries an item ID:
- `helab cache --help`, `dump --help` and `export --help`;
- `helab convert --help`;
- the CI tools' `--help` (`helab.release`, `helab.release_draft`, `helab.dependency_snapshot`).

`test_cli_help.py` keeps this for the user commands.
- **My mistake while checking:** `helab --help` has no help handling, so it starts the app. I ran it, and it
  started the GUI for 60 s. It used scratch cache, temp and app folders (`HELAB_*_OVERRIDE` under `.ai/temp/`),
  wrote nothing outside them, and was stopped by the timeout. This is old behaviour, outside this diff;
  `helab --version` exists and is documented.

### The pages: public text, true to the code

- **The built site** (`mkdocs build --strict`, the lock's tools, 17 pages) passes.
- **Scanned for names and internal references:** its rendered text has no person's name, lab machine, internal
  host, `/Users/` or `C:\Users` path, `.ai/` or `roadmaps/` path, or item ID (`Q1.2`, `S3~6`, `plots-3`, "codebase
  review"). The scan covered the API pages rendered from docstrings.
  - The only repository named in the text is the public `HeBECANU/HeLab` clone URL.
  - The only `TonyXTYan` links are the header's repo link and DM-3's.
  - The sources have no HTML comments.
- **Spot-checked against the code** (every bold or quoted UI label on the pages was searched for in `helab/`; the
  misses were headings, not labels):
  - "Large folder · ~X in RAM" with Load anyway… and No auto-load;
  - "N still being written";
  - "⚓ N to confirm";
  - File › Place .helab-root in “<folder>”… (`HelabMainWindow.py:292`);
  - the Settings page's defaults and ranges: settle 5 s (2–60), Live 3 s, background I/O 1, Live autosave 10, log
    files 300, RAM 1/8, the backend labels (`ConverterTab.BACKEND_NOTES`), g = 9.79602;
  - the command-line page's options against the real `--help`;
  - `--once`'s one-minute settle (`convert_cli.py:361`);
  - `helab --version`;
  - the script page's API names: `view.events`, `MatplotlibPane.redraw`, `matplotlib_pane`,
    `LivePolicy(every_shots, min_delay)`, and `covered_shots` recording `select_shots`.
- **The clone instruction** uses `--recurse-submodules`. That is safe, because the private `testdata` submodule
  is `update = none`.
- **`9507d02`'s edits to `fits.py` and `profiles.py`** are docstrings only: their syntax trees are identical once
  bare strings are removed.

### CI: the Docs job's cost and gates

- **`docs`:** 19 s at the head (ruff, then the strict build). It needs only `get-version`, nothing needs it, and
  it is not in `release`'s gate.
- **The manual in the 3.13 Build jobs:** 10–24 s each. It *is* in the release gate, through `required-builds`,
  since "Check the packaged app has the user manual" fails a build without it.
  - **Observation, not a finding:** this follows from Q54.3 (the bundled copy ships). A strict-build warning
    (such as a broken link) now fails the three release builds, not only the Docs job. The tools are pinned by
    the lock.
- **Run 41589115583 at `9acc055`:** every job green. I read every job's log through the API:
  - 9 Tests, 3 Converter backends, 3 Build, and Docs;
  - **no RERUN in any**.

## Checks (run by the reviewer)

**On an export of `9acc055`**, with testdata linked:
- `pytest -n 4 --reruns 5 --reruns-delay 1 --basetemp=.ai/temp/pytest-assay`: **9202 passed, 674 skipped, 2
  warnings, 3 failed, 15 rerun in 191.23 s.**
  - All 3 failures and all 15 RERUNs are the three git-provenance tests, 5 reruns each. The export has no
    `.git`.
  - `build_info.py` changed, so I ran them again in a real clone (`git clone --shared`, checked out at
    `9acc055`):
    - the whole of `test_versioning.py` and `test_release_recovery.py`;
    - `test_user_manual.py`, `test_spec_datas.py`, `test_cli_help.py`, `test_script_modules.py` and
      `test_scripts_folder.py`.

    **108 passed, no RERUN.**
  - No other RERUN.
  - The 2 warnings are the known pyqtgraph ones.
  - The totals match the handoff's 9206/673, once the export's 3 and 1 are added back.
- **Type checks:**
  - `mypy helab/ --strict` (205 files), `mypy tests --strict` (204), `--platform win32`: no issues;
  - `pyright helab tests` and `--pythonplatform Windows`: 0 errors.
- **`ruff check` (0.17.3):** passes.
- **`mkdocs build --strict`:** passes. It ran in a scratch venv from `requirements-docs.lock`, with
  `HELAB_DOCS_REPO_URL` set as CI sets it.
- **CI run 41589115583:** all jobs green, no RERUN in any log (above).

Scratch, not committed: the site scan, the help renderings and the job logs, in `.ai/temp/assay/`.
