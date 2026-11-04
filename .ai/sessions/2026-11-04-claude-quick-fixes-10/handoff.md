# Handoff: Quick Fixes 10 (`agent/quick-fixes-10`)

Worker: Rivet (Quick Fixer), own worktree `.ai/temp/quick-fixes-10`, from `bd349ec` (dev/v0.0.9). Brief:
[brief.md](brief.md), and its addendum (A56.4, `fdbd962` on dev/v0.0.9; not merged into this branch).

| Item | Commit | Files |
|---|---|---|
| A59.1 Release notes that link their tags | `ca0bd61` | `helab/release_draft.py`, `.github/workflows/dev-cicd.yml` (release job), `tests/test_release_recovery.py` |
| A59.2 (b) The no-stable front page | `bfa2b78` | `docs/publish/no-stable.html`, `docs/publish/site_versions.py`, `tests/test_docs_workflows.py` |
| A56.7 `helab --help` | `5a4d863` | `helab/main.py`, `tests/test_versioning.py` |
| A58.2 Folder details' conversion and a read stopped early | `6b22d8d` | `helab/views/explorer_convert.py`, `helab/views/explorer_live.py`, `tests/test_explorer_convert.py` |
| A56.4 The built-in profiles' descriptions | `0dc4f90` | `helab/convert/profile.py`, `helab/convert/builtin_profiles/*.json`, `tests/test_convert_profile.py`, `tests/test_profile_library.py` |

Earlier work: everything from QF9 (`b0eb914`, its handoff `d57814e`) and the fixed-mount seam (`ee4bbdf`…`e629969`)
is in dev/v0.0.9's history (checked with `git merge-base --is-ancestor` against `bd349ec`). Nothing of mine is
unlanded.

## A59.1 Release notes that link their tags (`ca0bd61`)

**Before:** the release job's "Prepare Release Body" step wrote a fixed bash template: no tag link, no comparison
with the previous release, and a Workflow Run link built from `github.event.repository.url`, which is the API's
URL (v0.0.8a1's draft, run 41746737106, linked `https://api.github.com/repos/TonyXTYan/HeLab/actions/runs/…`).

**Now:** `release_draft.main` builds a new draft's notes (`release_body`):
- `## Release [<tag>](<server>/<repo>/tree/<tag>)`, the date, the commit link, and the Workflow Run link from
  `${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}` (`--run-url`);
- GitHub's generated notes (`POST /repos/{repo}/releases/generate-notes` with `previous_tag_name`: it changes
  nothing). The notes come with their own "**Full Changelog**" line; ours replaces it, so there is exactly one;
- the build list and note, as before;
- `**Full Changelog**: <server>/<repo>/compare/<previous>...<tag>` at the end (`/commits/<tag>` when there is no
  previous tag), then the asset manifest (`manifest_body`, unchanged).

**The previous tag** (as first built in `ca0bd61`; Tony's rule replaced it in `9e06bcb`, below): the newest `v` +
PEP 440 tag of a lower version among the tags in the commit's history (`git tag --merged <commit>`,
`tags_in_history`). For v0.0.8a1 that is v0.0.6a1: v0.0.7a1 was never tagged. `v.0.0.1i`, `v0.0.1x`, `v0.0.2e`
(not PEP 440) and `CI-CD-everything-passed` are never chosen. A tag on a branch that never merged isn't in the
history, so it isn't chosen either. This rule is now the fallback, used when the releases can't be listed.

**Recovery:** `publish_draft` now takes the body as a string or a callable, and calls it only when it creates the
draft. A resumed draft, or a published release, keeps its notes and never asks GitHub for new ones. Bodies are
still written only while drafts (`_guard`). If GitHub's notes are unavailable (an API error), the draft is made
without them, with a `::warning::` line. The draft matters more than its notes.

**The job:** the bash template step is gone. The release step passes `--server-url` and `--run-url`, and a new
"Install packaging" step comes first, since `release_draft` now imports `packaging` (as `release.py` does). The
step is unpinned, like get-version's. ci-build.yml's `--check` runs where requirements.lock is installed, so it
already has packaging.

**Checked against GitHub:** I called `generate-notes` once for `v0.0.8a1` against `v0.0.6a1` to see its format.
It changes nothing. Its body lists PRs #10 (0.0.7a1) and #11 (0.0.8a1) and ends with the Full Changelog line
that `release_body` replaces. The job's first real run will be v0.0.9's release.

**Tests:** 15 new tests in `tests/test_release_recovery.py`; 14 fail on the old code, and the resume guard
already held.
- The previous-tag choice, over the real tag list's shapes.
- A real git history (`tmp_path`) with a tag on an unmerged branch.
- The body, with GitHub's sample notes and without any.
- `main` end to end, with and without GitHub's notes. The fake is a `MemoryReleases` with `generated_notes`.
- A resumed or published release keeps its notes, and the body callable is never called for it.
- The job's step: no `github.event.repository.url`, no `--body`, packaging installed before the first
  `release_draft` call, and `fetch-depth: 0`.

## A59.2 (b) The no-stable front page (`bfa2b78`)

mike's `set-default --template` renders only `{{href}}` (mike 2.2.0, `commands._add_redirect_to_commit`:
`template.render(href=href)`). So `site_versions.py` fills in the newest pre-release first:
- `no-stable.html` gains `{{latest}}`;
- `no_stable_page(newest)` replaces it with `latest_label(newest)`: "0.0.8a1 (alpha)", "(beta)",
  "(release candidate)", or "(development version)" for a `.dev` release;
- `main` writes that page into a temporary folder and hands mike its path (`plan(…, page)`).

`newest_pre_release` is the newest of every deployed version plus the new one while none is stable. So an older
pre-release published late still names the newest. The page is written exactly when the plan sets it as the
front page (tested). With a stable release the front page is `latest`, as before.

The page now reads:

> **HeLab manual**
> Latest: [0.0.8a1 (alpha)](pre-release/)
> No stable release yet: HeLab has only pre-releases (alpha and beta versions) so far, and the newest is the
> latest download. Its manual's version menu lists every release.
> *HeLab's Help › User manual opens the manual of the version you run.*

**Checks:** 3 new tests in `tests/test_docs_workflows.py`, all failing on the old code.
- The label.
- The page as mike's jinja2 renders it.
- Which version is named.
- `main` handing mike the filled-in page.

`ruff check` passes, and `mkdocs build --strict` passes (a docs venv from requirements-docs.lock, in my scratch
folder). I didn't run real mike against a gh-pages branch: its `--push` would push to the shared repository.

## A56.7 `helab --help` (`5a4d863`)

`helab/main.py` answers `--help`/`-h` with a short usage and exits 0. The check sits after the frozen helper and
probe dispatch and the `convert`/`cache` commands, so `helab convert --help` is still convert's own. It comes
before `--version`, Qt, settings, caches, Dash and `running.lock`:

```
usage: helab [--geometry WxH+X+Y]   start HeLab (the app)
       helab --version              print HeLab's version and build, and exit
       helab --help                 print this help, and exit
       helab convert --watch FOLDER [options]
                                    the headless TXY converter (helab convert --help)
       helab cache dump|export ...  look into the disk cache's .hlb files, read only
                                    (helab cache --help)

  --geometry WxH+X+Y  this run's main window: W x H points, its top-left at X,Y
                      (a sign each; "-" for a screen left of or above the main one)
```

**Tests** (`tests/test_versioning.py`): the help runs in a subprocess for `--help`, `-h` and with `--geometry`. It
imports `helab.main` as the `helab` script does, with the app folder override pointed at an empty folder.
- It exits 0.
- Neither PyQt6, `helab.utils.constants`, `dash_server` nor `cache_locks` is loaded.
- The app folder stays empty: no `running.lock`.

These 3 fail on the old code ("HeLab would start"). Two more check that convert's and cache's own help are
unchanged.

## A58.2 Folder details' conversion and a read stopped early (`6b22d8d`)

**Cause:** the read-stop handling (A37.1, Q48.1, Q48.2) lived in `explorer_live.LiveControl._converted` and
`_notify_read_stopped`. `ExplorerConverter.event` only counted a `shot_converted`.

**Fix:** the handling now lives in `explorer_convert`, shared by both conversions:
- `note_read_stop(path, event, by)` logs the file and sends the "raw file read stopped early" notification. Its
  key is unchanged (`READ_STOPPED_RAW`, folder, name, size, mtime), so a file notifies once per session
  whichever conversion made it;
- `read_stops_text(stopped)` gives the line's part (one file by name, several counted) and the tooltip line;
- `READ_STOPPED` moved there too; `explorer_live` re-exports it for `FolderDetailsPanel`.

`FolderConversion.stopped` keeps the stopped files by name. The Convert row names them, while converting and when
done, with the detail in its tooltip, and drops a file converted again to its end. Live's line, tooltip and
notification are unchanged; Live's A37.1 test passes unchanged.

**Not done:** Live's Auto-convert row turns amber for a read stopped early; Folder details' Convert ("offer") row
doesn't. That colour is set in `FolderDetailsPanel.py`, outside this brief's files, so it is A~1.

**Test** (`tests/test_explorer_convert.py`), failing on the old code: a real conversion (in-process helper) of a
folder with a raw file stopped at line 10, then:
- the row "3 converted to HeLab's cache folder · d3.txt read stopped at line 10" and its tooltip;
- the notification's text and event, once;
- the same file again isn't notified again;
- several are counted ("2 reads stopped early");
- read to its end, a file is no longer named.

## A56.4 The built-in profiles' descriptions (`0dc4f90`): for Tony's approval

`notes` is DESCRIPTIVE (outside the content hash), so no tag, hash or file name changed. A test pins each
built-in's hash to its value before the change: `fbaf4728…14d0` for matlab-2019 and the three plate profiles,
`a228f236…183e` for matlab-2023-lab-edit. That test also held on the old code. Another test checks that each
description is user-facing: no internal ID or "content hash", it says whether the profile is calibrated, and
"Marked uncalibrated" appears exactly for `UNCALIBRATED`. That one fails on the old notes.
- **Sources:** the profiles' fields, `converter.md`, `roadmaps/txy-converter.md` and `profile.py`.
- **The JSON files:** rewritten from the definitions (`to_json`), so they stay equal.
- **On screen:** Settings › TXY converter shows the text above "Plates in since…", "Content hash…" and "TXY
  files…". Offscreen at 720×640 it wraps and fits; the profile list gives up a few lines.

The five texts (wording is Tony's to approve):

1. **matlab-2019:** "HeLab's default. The lab's MATLAB converter (tdc_autoconverter), unchanged since 2017,
   which made the d_txy_forc files in the data folders: the same constants and the same quirks, so its TXY match
   those files byte for byte. Choose it for hits that agree with the lab's existing TXY, on data of any date.
   Not calibrated: it keeps MATLAB's fixed constants (time sums of 3200 bins on X and Y) for every plate."
2. **matlab-2023-lab-edit:** "The DLD front panel's copy of the MATLAB converter, as the lab had edited it by
   2023-08-29. It differs from matlab-2019 in three ways: a 0.5 µs dead time on x1 (an x1 pulse within 0.5 µs
   after a kept one is dropped), time sums of 3390 bins on X and 3275 on Y for T only, and X and Y worked out
   from the raw corner times. It finds about 12–14 % fewer hits than matlab-2019 on the lab's sample shots.
   Choose it to match TXY made with the front panel's edited copy. Not calibrated."
3. **plates-2017:** "For data taken on the MCP plates fitted on 2017-03-17, until the 2022 swap. For now it holds
   matlab-2019's constants, so its hits are matlab-2019's, written under its own file names; it changes only
   when these plates are calibrated. A plot's settings suggest it for a folder dated while its plates were in,
   but never pick it for you. Not calibrated yet: the 2019–2021 halo runs are to calibrate it."
4. **plates-2022:** "For data taken on the MCP plates fitted in 2022 (between 2022-08-22 and 2022-11-03; HeLab
   dates the swap 2022-11-03 for now), until the 2025 swap. For now it holds matlab-2019's constants, so its hits
   are matlab-2019's, written under its own file names; it changes only when these plates are calibrated. A
   plot's settings suggest it for a folder dated while its plates were in, but never pick it for you. Not
   calibrated yet: a run with MCP pulses in November 2022 measured time sums of 3367 bins on X and 3294 on Y on
   these plates, which it doesn't use yet."
5. **plates-2025:** "For data taken on the MCP plates fitted on 2025-06-18, the plates in the detector now. For
   now it holds matlab-2019's constants, so its hits are matlab-2019's, written under its own file names; it
   changes only when these plates are calibrated. A plot's settings suggest it for a folder dated while its
   plates were in, but never pick it for you. Marked uncalibrated: there is no calibration data for these plates
   yet. It doesn't yet turn the image back after the corner cables were swapped (between 2026-06-27 and
   2026-07-21), which turned it by 180°."

Points for Tony to check:
- (3) names the planned calibration data (the roadmap's stage 3).
- (5)'s cable swap and 180° come from `converter.md`'s provisional finding (2026-10-29 session) and may be more
  than users need.
- (2) uses "DLD front panel" for the lab's MATLAB analysis.

## Checks (before the handoff)

All runs used `pytest -n 12 --reruns 5 --reruns-delay 1` on macOS, with the worktree's code first on
`PYTHONPATH`.

- **First run** (after all five commits): 1 failed, 9322 passed, 673 skipped, 5 reruns.
  `test_profile_library.py::test_the_plate_profiles_start_as_matlab_2019` failed on all 5 reruns. It isn't a
  flake: it checked plates-2025's notes for "Uncalibrated" with a capital U, and A56.4's text says "Marked
  uncalibrated". I fixed it in A56.4's commit (`0dc4f90`, amended before any push): it now matches
  "uncalibrated" in any case.
- **Second run** (`0dc4f90`): **9323 passed, 673 skipped, no RERUN.**
- **Types:** `mypy helab/ --strict`, `mypy tests --strict`, `mypy helab/ --strict --platform win32`,
  `pyright helab tests` and `pyright --pythonplatform Windows helab tests` were all clean. `mypy tests` and both
  pyright runs were repeated after the fix; `helab/` didn't change after the first run.
- **Docs:** `ruff check` and `mkdocs build --strict` passed (A59.2).

## Proposals (the Coordinator applies them)

**`release-and-ci.md`**:
- **The release job (A59.1):** `release_draft` writes a new draft's notes (`release_body`): the tag linked,
  GitHub's generated notes (`generate-notes` with `previous_tag_name`), the Workflow Run from
  `github.server_url`, and one "Full Changelog: <previous>...<tag>" link.
  - **The previous tag** (Tony, 2026-11-04): the previous **published full** GitHub release. Of the repository's
    releases that are published and not marked pre-release (`full_release_tags`), take those whose tag is in the
    commit's history (`git tag --merged`) and pick the highest PEP 440 version lower than the new one
    (`previous_release`). An alpha published as a full release counts, so v0.0.9 compares with v0.0.8a1. Drafts
    and GitHub pre-releases never do.
  - **Fallbacks:** if the releases can't be listed, the newest earlier `v` tag in the history, with a warning; if
    the history can't be read either, no previous tag, and the Full Changelog links the tag's commits.

  A resumed draft keeps its notes, and GitHub's notes failing leaves a draft without them (a warning). The job
  installs `packaging`.
- **The publishing step (A59.2 (b), the rule):** a pre-release version may be published as a full GitHub release
  (v0.0.8a1 is GitHub's "Latest"). The site goes by the version number: its `latest` stays the newest stable
  version. Until there is one, the front page (`no-stable.html`, filled in by `site_versions.no_stable_page`
  since mike renders only `{{href}}`) names the newest pre-release, "Latest: 0.0.8a1 (alpha)", linked to
  `pre-release/`.

**`converter.md`**:
- **Profiles in the app (A56.4):** each built-in's `notes` is user-facing text, shown in Settings › TXY
  converter: what it is, when to choose it, how it differs, whether it is calibrated. It carries no internal ID.
  Rewording it changes no hash (`tests/test_convert_profile.py` pins the five hashes).
- **Folder details' conversions (A58.2):** a read stopped early is named in the Convert row and notified once
  per file, through `explorer_convert.note_read_stop` and `read_stops_text`, which Live's auto-convert uses
  too.

**`app-runtime-and-ui.md`** (or `AGENTS.md`'s commands block, one line):
- `helab --help` (`-h`) prints a short usage and exits 0 before Qt, settings, caches, Dash and `running.lock`,
  after the frozen dispatch and the `convert`/`cache` commands (A56.7).

**Known issues:** nothing new from this batch (RERUNs, if any, are listed under the checks).

## Provisional items

- **A~1 Folder details' Convert row amber for a read stopped early** (`FolderDetailsPanel.py`). Live's
  Auto-convert row is amber when it names one (`READ_STOPPED`); the Convert ("offer") row, which now names them
  (A58.2), isn't. It is a two-line change beside the `convert` row's style, in a file outside this brief.
- **A~2 Pin `packaging` in the release jobs.** get-version and now the release job run `pip install packaging`
  unpinned; requirements.lock has `packaging==26.3`.

## CI

Run **41756514071** (`298b601`, push) succeeded. I read the logs of all 17 jobs: Detect, Docs, and on macOS,
Windows and Ubuntu, Build, Converter backends and Tests 1–3. No log has a RERUN. Each Tests and Converter job's
summary line is "N passed, M skipped", with nothing failed. The macOS build's ERROR lines are its expected check
of the optional backends (mlx, numba, rust not installed).

From the junit artifacts, every new or changed test passed on all three OSes:
- A59.1: 18 cases;
- A59.2: 3;
- A56.7: 5;
- A58.2: 1;
- A56.4: 2, plus test_profile_library's plate test.

## Review fix (`be2f0e5`) and its CI

The independent review had no High or Medium findings. It had one Low for me:
- **The finding:** `main`'s `body()` called `tags_in_history` (`git tag --merged`) outside the try that guards
  GitHub's notes. A failing git aborted `publish_draft` before `api.create`, after the tag was pushed, and every
  rerun would fail the same way.
- **The fix:** `subprocess.SubprocessError` and `OSError` are caught there. HeLab warns and builds the notes with
  no previous tag; GitHub's notes are still asked for, and the Full Changelog links the tag's commits.
- **The test:** a `CalledProcessError` and a `FileNotFoundError` from `tags_in_history`. The draft is made with
  all three assets and the manifest. Both cases fail on `298b601`'s `release_draft.py`.

The file's 47 tests pass. mypy --strict (also `--platform win32`) and pyright (also `--pythonplatform Windows`)
are clean on the files. As asked, I didn't run the full suite for this fix.

**CI 41758844145** (`be2f0e5`) succeeded. I read all 17 job logs. The new test passed on all three OSes (junit).
**Two RERUNs**, each passed on its rerun. Neither is in known-issues, and neither test's path is one this branch
changes. I haven't looked for their causes. Proposed known-issues lines:

- [ ] `test_live_convert.py::test_a_conversion_refused_offline_stops_auto_convert_and_says_so[as it comes]`:
  macOS CI 41758844145 (Tests 1/3, job 126341476955), one RERUN. The `waitUntil` (5 s) at line 626, for the
  conversion's "not while working offline" error after `_convert_tick` while offline, timed out once. Cause not
  yet found.
- [ ] `test_gui_responsiveness.py::test_real_helper_loads_data_and_refresh_replaces_changed_data`: Windows CI
  41758844145 (Tests 3/3, job 126341477058), one RERUN. The `waitUntil` (15 s) at line 788 timed out once, with
  real helper processes. That job took 12 min 43 s; the other Windows groups took about 7–10 min. Cause not yet
  found.

## RERUN (1) checked: not related to this branch

CoCo asked whether `test_live_convert.py::test_a_conversion_refused_offline_stops_auto_convert_and_says_so[as it
comes]` (macOS CI 41758844145) is related to `6b22d8d`, which changed `explorer_live.py`.

**(a) The code path.** The test goes `_convert_tick` → `FolderCache.convert` → `submit` → IOService's offline
refusal (`service.offline = True`). The `offline` event then reaches `_convert_event`, which sets
`convert.error`. Line 626 waits for that.
- None of that is in `6b22d8d`'s diff.
- The changed `_converted` branch runs only for a `shot_converted` with a `read_stop`. This test's raw files read
  to the end, so it takes the unchanged `else`.
- The only changed code it reaches is `read_stops_text({})` in each Live-line render, which returns `("", "")` at
  once. `READ_STOPPED` is the same tuple, now defined in `explorer_convert`.

**(b) Runs under load** on macOS (16 cores), with `--reruns 0`. Branch `04419ed` and base `bd349ec` (a clean
worktree) alternated pass by pass, so both met the same load. CPU burners (`yes`) ran beside each round.

| Round | What ran | Branch | Base |
|---|---|---|---|
| 1 | the whole of test_live_convert.py plus the target, `-n 12`, 8 burners, 30 passes (the target 4 times a pass) | 120 runs, 0 failed | 120 runs, 0 failed |
| 2 | the target only, `-n 12`, 16 burners, 30 passes (2 a pass) | 60 runs, 0 failed | 60 runs, 0 failed |
| 3 | 12 concurrent single-process runs, 8 burners, 10 rounds (2 each) | 240 runs, 0 failed | 240 runs, 0 failed |

In total, **420 runs on each side, no failure on either.** pytest dropped the repeated node IDs I passed for more
copies, so each pass ran the counts in brackets; the table counts what actually ran. In every other pass of the
whole file (round 1) the file's other 23 tests passed too.

**(c) Not related.** Neither the code path nor the numbers tie it to this branch, and it didn't reproduce on
either side. On CI the test ran 11 s on `gw3`, about 6 s of setup and then the 5 s wait. The known-issues line
proposed above stands, with its cause not found. One idea for the hunt: the refusal's `offline` answer may arrive
on a timer that a loaded runner's event loop is late to.

RERUN (2) (Windows, real-helper refresh): the known-issues line above, as CoCo asked.

**CI 41762330085** (`feb9985`, handoff only) succeeded. I read all 17 job logs.
- **One RERUN,** passed on rerun: Windows Tests 2/3 (job 126352703916),
  `test_quit_confirms.py::test_quitting_with_nothing_to_save_closes_within_a_second`, with
  `assert (692.18 - 691.02) < 1.0`: quitting took 1.15 s. It is already in known-issues (the Windows sightings
  of 41578243240 and 41597667363); this is one more for that entry.
- **The Build jobs:** each log's one "RERUN" match is only this commit's subject in the checkout line.

## Tony's A56.4 OK, and the profiles list's TXY tags in aligned columns (`6722408`)

Tony approved A56.4's five texts (via CoCo, 2026-11-04). He then asked for two more:
1. Show each profile's TXY file tag in Settings › TXY converter's profiles list, and align the list's columns
   ("each column in the profiles list should be aligned"). Done in `6722408`.
2. Change the Full Changelog's previous-tag rule (a stable release compares with the previous stable release).
   On hold until CoCo confirms which "stable" Tony means.

**The list:** a `QTreeWidget` with one header and a column per field: Profile, Version, TXY tag, Kind, Notes,
Hash.
- Each column is sized to its widest text (`ResizeToContents`); rows are uniform, one line each, and there's no
  root decoration.
- The TXY tag is the one the profile's files are named with (`file_tag`): a built-in's own (`m19v1`), or a user
  profile's `u` + 32 hex digits. Its tooltip gives the file pattern.
- An unreadable profile file's row spans the columns.
- `profile_label` (one " · "-joined string) became `profile_columns`. The ID and accessible name
  (`profiles_list`, "Profiles") are kept, and `test_accessible_names` passes.

A user profile's tag is long (33 characters), so its column is wide. It still fits at 720 px; a narrower window
scrolls sideways. I kept it whole, since it is exactly what the profile's files carry.

**Screenshots** (offscreen, 720×640, plates-2022 selected, with a user profile `halo-fit` v3; gitignored, on the
Mac):
- before: `/Users/tonyyan/GitHub-Local/HeLab/.ai/temp/quick-fixes-10/.ai/temp/qf10-shots/converter-profiles-before.png`
- after: `/Users/tonyyan/GitHub-Local/HeLab/.ai/temp/quick-fixes-10/.ai/temp/qf10-shots/converter-profiles-after.png`

**Checks:** a new test in `tests/test_converter_tab.py`. It fails on the old code, whose list has no header or
columns. It checks:
- the header's titles, every column `ResizeToContents`, and uniform rows;
- each row's six texts, for the built-ins and a user profile;
- the tag's tooltip, and selection;
- once shown, every column is at least as wide as its widest text, so nothing is cut.

The module's helpers now read the tree's rows. test_converter_tab, test_accessible_names, test_typing and the
Settings dialog tests: 324 passed, no RERUN. mypy --strict (also win32) and pyright (also Windows) are clean on
the files. As for the review fix, I didn't run the full suite for this one.

**Proposal (`converter.md`, Profiles in the app):** the profile manager's list has one aligned column per field:
Profile, Version, TXY tag (`file_tag`), Kind, Notes, Hash.

**CI 41767805544** (`133ccd8`, with `6722408`) succeeded. I read all 17 job logs; none has a RERUN. From the junit
artifacts, `test_the_profiles_list_shows_each_tag_in_aligned_columns`, and the two tests whose helpers changed
(`test_the_builtins_are_listed_read_only`, `test_unreadable_files_are_named`), passed on macOS, Windows and Ubuntu.
While the run went on, this Mac's DNS for api.github.com dropped in and out, so I fetched the logs with retries;
every log came down whole.

## The Full Changelog compares with the previous published full release (`9e06bcb`)

Tony chose (via CoCo, 2026-11-04) the previous **published full** GitHub release: not a draft, not marked
pre-release on GitHub, whatever its version string. Tony: "I think we include alpha full releases too, v0.0.3 was
a very long time ago". The rule (`release_draft.previous_release`):
- of the repository's releases that are published with `prerelease` false (`GitHubReleases.full_release_tags`,
  every page), keep those whose tag is in the commit's history;
- take the highest PEP 440 version lower than the new one. So v0.0.9 compares with v0.0.8a1.

**Fallbacks:**
- An API error listing the releases (`SubprocessError`, `ValueError` or `OSError`): the newest earlier `v` tag in
  the history (the A59.1 rule), with a `::warning::`.
- With the history unavailable too: no previous tag (as in `be2f0e5`).

**Tests** (`tests/test_release_recovery.py`): 9 new, all failing on the previous `release_draft.py`.
- The choice with fake release lists: an alpha full release chosen; releases that aren't full, aren't in the
  history, or are higher, all skipped.
- `full_release_tags` over two pages, skipping drafts and GitHub pre-releases.
- `main` comparing with the full release (v0.0.3b) over newer tags that aren't full releases (v0.0.3, v0.0.4a1).
- The API-failure fallback to v0.0.4a1, with its warning.
- Neither releases nor history: no previous tag.

The file's 56 tests pass and the five type checks are clean (whole `helab/` and `tests`). The release job's
comment says the new rule. The `release-and-ci.md` proposal above states it.
