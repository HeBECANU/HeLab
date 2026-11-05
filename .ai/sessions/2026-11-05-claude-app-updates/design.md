# App updates: design (step 1)

Worker, 2026-11-05, floor "App Updates", branch `agent/app-updates` from `127b1e8`. The spec is
`roadmaps/app-updates.md` (Shared rules, Stage 1, Stage 2's source path) as amended by Q65.1 (b) and Q65.3 and
the brief. Nothing here is code yet; the questions for Tony are at the end (`Q~1`…).

Facts checked while designing (read-only):

- CI's check runs are named `<os> + py3.13 / Tests (1/3)`, `… / Tests (2/3)`, `… / Tests (3/3)`,
  `… / Converter backends`, `… / Build` (macos, windows, ubuntu), app `github-actions`; the compatibility jobs
  (`py3.11`, `py3.12`, `py3.14`) are `skipped` on branch pushes. 45 check runs per commit: one page at
  `per_page=100`. (`gh api …/commits/<dev/v0.0.9>/check-runs`.)
- Release tags since v0.0.5a1 are lightweight (`git/matching-refs/tags/v` gives `object.type: commit`); older
  ones are annotated.
- The Python minor version a commit needs is in `requirements.lock`'s header
  (`uv pip compile … --python-version 3.13`). There is no `pyproject.toml`; `setup.py` holds the entry points.
- `io_service` starts helpers as `[sys.executable, -m, helab.io_helper]` (source), so their command line names
  the venv's Python. `IOService.shutdown` kills retired helpers; a cache move's helper can outlive HeLab and holds
  `move.lock`.
- Help › User manual already does an asynchronous `QNetworkAccessManager` request with a transfer timeout; the
  update check follows the same pattern.

## 1. Where the code goes

A new package **`helab/updates/`** (owned):

| Module | Qt? | What |
|---|---|---|
| `versions.py` | pure | Version status from `BuildInfo` and the repo's facts; channel filter; "newer than"; Skip this version |
| `github.py` | pure | The requests (URL, `If-None-Match`), parsing releases, tag refs, compare and check runs; the CI-green rule; the ETag cache record |
| `settings.py` | QtCore | Reading the new settings rows (through `read_setting`), the default mode and repo |
| `check.py` | Qt | `UpdateCheck`: the request sequence on `QNetworkAccessManager`, the daily startup check, results as a signal |
| `launch.py` | Qt | Copying the updater out, `--check` (dry run) as a `QProcess`, the detached start, the ready handshake, the started mark, the last outcome |
| `dialog.py` | Qt | The update window (§4) |
| `updater.py` | **standard library only** | The updater script (§6). Imported by nothing in HeLab; copied out and run |

`versions.py`, `github.py` and `updater.py` join `PURE` in `tests/test_headless_imports.py` (no Qt, no
`helab.utils.constants`). `updater.py` imports nothing from `helab` at all (a test checks its imports are standard
library only), since it runs as a lone copy.

Outside the package, only the brief's allowed edits: `HelabMainWindow.py` (Help items, the status-bar mark,
About's lines, the quit for an update, the last outcome shown once), `SettingsDialog.py` (Settings › General's
rows), `settings_defaults.py` (new rows), `main.py` (the started mark only; no updater entry is needed, since the
updater never runs from HeLab's own interpreter), and the two tests' lists. No change to `io_helper`, the quit
window, `running.lock` or the release job.

## 2. Version status

Computed in `versions.status(build, facts)`, from `BuildInfo` (version, commit, branch, dirty; the same for a
source and a frozen run of one commit) and the chosen repo's published releases and tag refs:

- **Release X**: the running commit is the commit of tag `vX`, `vX` has a published, non-pre-release GitHub
  release, and the tree is clean (`dirty` false or, frozen, unknown).
- **Pre-release X**: the same for a release GitHub marks pre-release, or a PEP 440 pre-release version.
- **Development version (based on X)**: anything else, X being `BuildInfo.version` (`_version.py`). A dirty tree
  is always Development. Before any check succeeds, the status is computed from `BuildInfo` alone: "Development
  version (based on X)" for a source run, "X" with "not checked yet" otherwise (no guess).
- **Update available: Y**, added to the above when the chosen mode has something newer (§3), not skipped.

Help › About gets three lines under today's provenance: *Version status*, *Updates* (the mode in words, §3) and
*Last check* (time and result, or "never" / "couldn't reach GitHub at HH:MM"). About reads memory only.

## 3. The check (stage 1)

**Transport.** `QNetworkAccessManager` on the GUI thread's event loop (no thread, no helper), as Help › User
manual does; `setTransferTimeout(10 s)` (time without progress); `User-Agent: HeLab/<version>`,
`Accept: application/vnd.github+json`, `X-GitHub-Api-Version`; GET only, to `https://api.github.com` only (the
host is a constant; tests inject a fake transport, never a different host through a setting or environment).
No token, no cookies (`setCookieJar` none, `CacheLoadControl` off). If Qt networking misbehaves on a lab PC the
fallback is a small `io_helper` request; not built unless needed.

**ETags.** Each URL's last `ETag` and its **trimmed, parsed** reply (not the raw body) live in
`<app folder>/updates/github-cache.json` (written by the GUI: a small file in the app folder, beside the logs and
locks; temp + rename). Every request sends `If-None-Match`; a 304 reuses the record and doesn't count against
GitHub's 60 requests an hour per address. A missing or malformed cache file is "no cache".

**Requests per check** (all with ETags):

| Mode | Requests |
|---|---|
| Releases (source and frozen) | `GET /repos/{r}/releases?per_page=100` (drafts never appear without a token; any with `draft: true` are dropped anyway); `GET /repos/{r}/git/matching-refs/tags/v` (tag → commit; an annotated tag is resolved once with `GET /repos/{r}/git/tags/{sha}`, cached by SHA); for the offered release, `GET /repos/{r}/compare/{tag commit}...main` (`ahead` or `identical`: on `main`; else not offered, logged) |
| Branch (source) | `GET /repos/{r}/compare/{running commit}...{branch}`: `identical` (up to date), `ahead` (candidates: its `commits`, newest first), `behind`/`diverged` (the checkout has commits the repo's branch doesn't: no update, "ahead of <repo>'s <branch>"), 404 (commit or branch not on that repo: no update, said why); then `GET /repos/{r}/commits/{sha}/check-runs?per_page=100` for candidates, newest first, stopping at the first green one, at most 5 |

The releases' two requests also run in branch mode (for the status line, "Release X", and to mention a newer
release), so a branch-mode check is 3–8 requests, most of them 304s.

**CI green on all three OSes** (`github.ci_green`), from one commit's check runs, only those whose
`app.slug == "github-actions"` (another app can't post a fake success):

- for each of `macos`, `windows`, `ubuntu`: at least one run named `<os> + py3.13 / Tests…` and one named
  `<os> + py3.13 / Build`;
- every job name `<os> + py3.13 / …` has succeeded: of its runs (a re-run, or a push's and a PR's run of one
  commit) the newest that isn't skipped counts, and a name that was only skipped, or whose newest run was
  cancelled, is **not green** (CoCo, 2026-11-05: the target commit's own runs, on all three OSes);
- anything else (`queued`, `in_progress`, `failure`, `cancelled`, `timed_out`, `action_required`, missing) is
  **not green**. Other jobs (Docs, compatibility, the release job) don't count.

The rule doesn't hard-code the number of test groups, so a CI that grows a fourth group still passes on an older
HeLab.

**When.** Help › Check for Updates… at any time (a click while one runs adds none). At startup, at most once a
day: 30 s after the window shows (startup is never delayed), when "Check for updates at start" is on and the last
**successful** check is over 24 h old (or in the future). A failed startup check is quiet (logged) and retried at
the next start; the manual check explains a failure in its window ("Couldn't reach GitHub: <Qt's error>", "GitHub's
limit of 60 requests an hour from this network is used up until HH:MM" from `X-RateLimit-Reset`).

**Repos.** Only `HeBECANU/HeLab` and `TonyXTYan/HeLab` (a constant list; the setting stores one of them, anything
else reads as the default). Stage 2 finds the repo among the checkout's remotes **by URL** (`remote.<n>.url`,
the raw config value, matched with `build_info.GITHUB_REMOTE`; never by remote name). Default: `Q~1`.

**Channels.** "Include pre-releases" off: only releases GitHub doesn't mark pre-release **and** whose version
isn't a PEP 440 pre-release. On: both. Compared with `packaging.version.Version` (tag without `v`; tags that
don't parse are ignored). A development version is offered only releases newer than its own version.

**Skip this version.** Stores the offered version (releases) or commit (branch). A skipped one never shows the
status-bar mark or the Help entry after a startup check; the manual check still shows it, marked "skipped", with
"Don't skip". A newer one is offered again.

**How it shows.** No banner, no vertical space:

- a status-bar `QToolButton` (auto-raise, hidden unless an update is available and not skipped), text
  "⬆ 0.0.9" (branch: "⬆ dev/v0.0.9 +3"), tooltip with the details; a click opens the update window;
- Help › **Check for Updates…** (always), and above it, only while an update is available, "HeLab 0.0.9 is
  available…" (branch: "dev/v0.0.9 has 3 newer commits…"), opening the same window;
- Help › **Restore previous version…**, enabled when a previous version is kept (§7).

Every control gets `identify` (IDs `update_available`, `help_check_updates`, `help_update_available`,
`help_restore_previous`, `update_*` in the window) and joins `tests/test_accessible_names.py`'s lists.

## 4. The update window and Settings › General

**The window** (`dialog.py`, modeless, one): status line; what was found (release: version, date, notes as
Markdown in a `QTextBrowser`; branch: the commits' subjects and dates, newest first, with each one's CI state);
links to the release page or GitHub's compare page; then per run:

- **Frozen:** "Download" (the platform asset `HeLab-<os>.zip`, else the release page, in the browser) and the
  steps in one line. No self-update (Q65.1 (b)).
- **Source:** "Update and restart". Clicking it runs the updater's dry run (§6, `--check`, a `QProcess`: the GUI
  never waits) and shows what it found: the refusals with their reasons (the button stays off), or what will
  happen ("Fetches dev/v0.0.9 from TonyXTYan/HeLab and fast-forwards 127b1e → 4f02aa; requirements.lock changed:
  a new venv is built first (a few minutes); Live is on in 1 tab and stops; HeLab quits and starts again"), with
  "Stash my changes first" when local changes are the only refusal. A second click on "Update and restart"
  (now "Quit and update") starts it.
- "Skip this version" / "Don't skip", "Close".

**Settings › General** (`SettingsDialog.py`, rows only, one line each, in one `QFormLayout` group "Updates"):

| Row | Control | Setting (new rows in `settings_defaults.py`) |
|---|---|---|
| Check for updates at start (once a day) | checkbox | `updates_check_at_start`, bool, True |
| Updates from: | combo `HeBECANU/HeLab`, `TonyXTYan/HeLab` · combo "The branch HeLab runs from (dev/v0.0.9)", "Releases" · checkbox "Include pre-releases" | `updates_repository`, str, "" (= the default, `Q~1`); `updates_mode`, str, "" (= the default for what the checkout is on), "branch", "releases"; `updates_prereleases`, bool, False |

A frozen build shows "Releases" only (the mode combo disabled, tooltip "A compiled HeLab only checks releases;
download them from the release page"). A detached checkout greys out "branch" (tooltip says why). Not shown, not
user-editable: `updates_skipped` (str), `updates_last_check` (ISO time of the last successful check),
`updates_last_result` (str, for About).

**Q65.3 in About** (*Updates* line): "the branch dev/v0.0.9 of TonyXTYan/HeLab, fast-forward only, to commits
whose CI passed on macOS, Windows and Ubuntu"; "releases of HeBECANU/HeLab (pre-releases included), tag to tag";
frozen: "releases of HeBECANU/HeLab (checked only: download them by hand)".

## 5. The two source modes (Q65.3)

The default comes from what the checkout is on (`BuildInfo.branch`): a branch → **branch**; `detached` →
**releases**. The setting overrides it; "branch" on a detached checkout is a refusal.

**(a) Releases**, tag to tag: the newest release on the channel newer than the running version. The updater
fetches `refs/tags/vY` (no `--force`: a local `vY` naming another commit is a refusal, "the tag moved") and the
repo's `main`; checks the tag's commit is the one the check saw and is an ancestor of the fetched `main`; then
`git checkout --detach vY`. Later updates go tag to tag; a branch the checkout was on is left as it was (the
window says "leaves dev/v0.0.9; to develop here again, check out a branch by hand").

**(b) Branch**, fast-forward only: the checkout must be on that branch (HEAD not detached). The target is the
newest candidate whose CI is green (§3; `Q~2`). The updater fetches the branch
(`refs/heads/B:refs/remotes/<remote>/B` from the matched remote), checks the target is an ancestor of the fetched
tip and a descendant of `HEAD`, then `git merge --ff-only <target>`. It never resets, rebases or force-updates a
ref; a branch that diverged is a refusal.

Both then `git submodule update` (initialized submodules only, no `--init`; a failure is a warning in the log,
not a failed update: they are references and test data, not HeLab's code).

## 6. The updater (stage 2, source path)

**The script.** `helab/updates/updater.py`, standard library only. HeLab copies it to
`<app folder>/updates/updater-<token>.py` (outside the checkout it replaces) and runs it with the base Python
(`sys._base_executable`; on Windows its `pythonw.exe`, so no console), refused if that path is inside the checkout
or its venv. `--check` is the dry run (refusals and the plan as JSON on stdout, changes nothing but a
`git fetch` of the target refs); without it, the real run. Every run takes one request file (JSON, written by
HeLab): checkout, venv, app folder, HeLab's pid, mode, repo, remote URL, target (tag or commit, as checked),
`stash` flag, the tools (`git`, `uv` as argument lists, found by HeLab: `PATH`, then the usual install places),
the relaunch command, a token. Nothing comes from the command line but the request's path and `--check`.

**Refusals**, each with its reason (checked by `--check`, and again by the real run once HeLab has exited; any
refusal there changes nothing and relaunches the old HeLab with the reason):

| Refusal | How it's found |
|---|---|
| SSH session | `SSH_CONNECTION`, `SSH_CLIENT` or `SSH_TTY` set (HeLab's and the updater's environment) |
| Elevated | POSIX `geteuid() == 0`; Windows `IsUserAnAdmin()` (an admin account's normal, unelevated session is fine) |
| `git` or `uv` missing | not found, or `--version` fails |
| Different Python minor | the target's `requirements.lock` header `--python-version X.Y` ≠ the base Python's |
| Local changes | `git status --porcelain --untracked-files=no --ignore-submodules=dirty` not empty; offered: `git stash push -m "HeLab update <from> → <to>"` (tracked changes; never dropped or popped; the log and the next start say `git stash list` / `git stash apply`) |
| Untracked files the update would overwrite | files added between `HEAD` and the target that exist untracked (`git ls-files --others --exclude-standard`); named in the reason |
| Detached HEAD or another branch in branch mode | `git symbolic-ref -q HEAD` ≠ `refs/heads/<B>` |
| No remote for the repo | no remote's URL matches (`Q~6`) |
| Not fast-forward / tag moved / tag not on `main` / target ≠ what was checked | as §5 |
| Other HeLabs or helpers | any `instances/*.lock` other than HeLab's own held (a `helab convert`), or `move.lock` held (a cache move's helper) |
| A cache move | the cache mover is running (checked in HeLab before starting; loads and checks are cancellable and saves are waited for, so they don't refuse) |
| HeLab's environment isn't the checkout's venv | `sys.prefix` isn't `<checkout>/venv` (resolved): refused only when the venv must be rebuilt |
| Test guard | with `HELAB_TEST_SOURCE_GUARD` set, any checkout or app folder outside the temp folder |

**The handshake.** HeLab starts the updater detached (`QProcess.startDetached`). The updater first opens a
handle on HeLab's process, safe against pid reuse (Windows `OpenProcess(SYNCHRONIZE)`; macOS a `kqueue`
`EVFILT_PROC`/`NOTE_EXIT`; Linux `os.pidfd_open`), then writes `updates/ready-<token>`. HeLab polls for it with a
`QTimer` (never waits), up to 15 s; seen, it closes through the normal path (§8); not seen, it says "The updater
didn't start" and stays.

**Waiting**, before changing any file (up to 30 min for HeLab itself, which may be in its quit window; then 2 min
for the rest; giving up changes nothing and logs why):

1. HeLab's handle signals exit;
2. `running.lock`, every `instances/*.lock` and `move.lock` in HeLab's app folder are free (the same OS locks as
   `cache_locks`, re-implemented in a few lines since the script imports nothing from HeLab);
3. no process runs from the checkout or its venv: POSIX `ps -A -o pid=,command=` naming the venv or checkout
   path; Windows the image paths of all processes (`CreateToolhelp32Snapshot` + `QueryFullProcessImageNameW`,
   ctypes) under the checkout, **and** a rename probe of the venv folder (`venv` → `venv.probe-<token>` and back),
   which fails while any process (the venv's Python redirects to the base `python.exe`) has a `.pyd` from it open.

**The update** (in this order; each step logged):

1. Fetch (§5), re-check every refusal, record the previous state in `updates/previous.json` (commit, branch or
   detached, mode, whether the venv was rebuilt, the stash's message if any).
2. Stash if asked.
3. Move the code: `git checkout --detach vY` or `git merge --ff-only <target>`, then `git submodule update`.
4. **The venv, only when `requirements.lock` changed** between the previous commit and the target (`Q~5`):
   resolve `venv` (a symlink to `venv.nosync/` stays a symlink: the real folder R is what's rebuilt), build
   `R.new` beside it with `uv venv --relocatable --seed --python <base python> R.new` and
   `uv pip install --python R.new -r requirements.lock -e .` (the target's files, now checked out). Check it
   with `R.new`'s Python importing `helab.build_info`, `helab.utils.settings_defaults` and `PyQt6.QtCore` and
   printing the version, which must be the target's. Then swap: R → `R.previous`, `R.new` → R (Windows: retried
   for a few seconds, for antivirus and the indexer). `--relocatable` keeps entry points and activation working
   after the rename. Else the venv is reused untouched. A failure here moves the code back (below).
5. Relaunch, detached, as the same user in the same desktop session (the updater is HeLab's child there): the
   venv's Python `-m helab` (Windows `pythonw.exe`), cwd the checkout, HeLab's environment plus
   `HELAB_UPDATE_TOKEN=<token>` (`Q~7`).
6. Wait for the started mark (§7); write `updates/last.json` (outcome, from, to, reason, log path) and exit.

**On failure** at any step after 1: undo in reverse (checkout back to the previous commit, the local branch's ref
back with `git reset --keep` only if the updater moved it, the venv swapped back), relaunch the old HeLab, and
record the reason. A failure before step 4's swap leaves the old venv untouched; `R.new` is removed (the
updater's own half-built folder). A failed update leaves the previous version working.

**The log**: `updates/update-<UTC>.log`, and `updates/last.json`, which the next start reads (a small app-folder
file) and shows once: a status-bar notice "Updated to 0.0.9 (4f02aa)" or a message box "The update didn't
finish: <reason>. HeLab is still 0.0.8a1." with Show log.

## 7. Started mark, roll back, Restore previous version

**Started mark.** `main.py`: when `HELAB_UPDATE_TOKEN` is set, once the main window has shown and the event loop
has turned once (a `QTimer.singleShot(0)` after `show()`), HeLab writes `updates/started-<token>`. The updater
waits for it up to 3 min. Without it: if the new HeLab has exited (crashed or refused), the updater rolls back
(§6, "On failure") and starts the old one with the reason; if it's still running, it is never killed (it may be
recovering a cache move or showing a dialog), and the updater logs "started but not confirmed" and exits
(`Q~3`).

**Restore previous version** (Help): runs the same updater with the target "previous" from `previous.json`:
the checkout back to the previous commit (releases: `git checkout --detach <commit>`; branch: `git reset --keep
<commit>` on that branch, which moves only the local ref and never loses a commit the repo's branch doesn't have:
checked first; `Q~4`), and `R.previous` swapped back when that update rebuilt the venv (the current one becomes
`R.previous`, so Restore can be undone by Restore). The same refusals, waiting, relaunch and started mark.
A restored commit is skipped by the startup reminder until something newer appears.

**What's kept**: one previous commit and at most one `R.previous`. A later successful update with a rebuild
replaces `R.previous`: the older one is deleted only after the new version's started mark (housekeeping, to be
listed in AGENTS.md's list; `Q~8`). Leftover `updater-*.py`, `ready-*`, `started-*` and update logs beyond the
log count are removed at the next start (housekeeping, same list).

## 8. What HeLab does before quitting for an update

Unchanged quit path (no change to the quit window or `running.lock`): "Quit and update" closes the main window
as File › Quit does, so `closeEvent` stops Live (saving its shots) and, if any save is still running, the quit
window waits for it (each save stops itself after its no-progress timeout; Quit now skips them as today: nothing
is lost). The update window's text says so beforehand ("Live is on in 1 tab: it stops and its new shots are
saved"). HeLab refuses to start the updater during a cache move (§6). The updater waits for HeLab, its helpers and
the locks, so a slow quit only delays it.

## 9. Invariants kept

- The GUI never waits on the network (`QNetworkAccessManager` signals), the updater (`QProcess` signals, a
  `QTimer` poll) or a helper.
- Only GETs to `api.github.com` with `User-Agent: HeLab/<version>`; `git fetch` from the matched remote only in
  stage 2, started by a person. No telemetry, no free-text repo.
- HeLab never changes code it or a helper runs: every file change waits for §6's three conditions.
- Never from an SSH or elevated session (checked in HeLab and in the updater).
- Nothing removed without asking beyond the housekeeping listed in §7; a stash is never dropped or popped.

## 10. Tests

All without network, real data, this checkout's git state or Tony's remotes.

- `tests/test_updates_versions.py`: the status for release, pre-release, development, dirty and frozen (same
  commit, same status), channels, drafts ignored, Skip this version, a development version offered only newer
  releases; parsing fake feeds (JSON fixtures under `tests/data/updates/`, shaped like GitHub's, the check runs
  trimmed from a real reply).
- `tests/test_updates_github.py`: the CI-green rule (all green; one OS missing; a failure; in progress; a re-run
  that turned green; a push and a PR run of one commit; another app's fake success; a fourth test group), compare
  statuses, annotated tags, the ETag cache (sends `If-None-Match`, 304 reuses, a malformed cache file).
- `tests/test_updates_check.py` (Qt): `UpdateCheck` with a fake transport: the startup timer and daily gate,
  quiet failures at startup and explained ones by hand, rate-limit wording, one check at a time, the status-bar
  mark and Help entries (shown, hidden, skipped), Settings › General's rows saved and read, About's lines.
- `tests/test_updates_updater.py`: the script **run as a subprocess** on every OS, against temporary repos: a
  bare repo as "the remote", a clone as "the checkout", both under `tmp_path`, the clone's remote URL
  `https://github.com/HeBECANU/HeLab` rewritten to the bare repo by the clone's own `url.<bare>.insteadOf`
  (matching is by the raw URL, so the real matching code runs; no request leaves the machine); git isolated with
  `GIT_CONFIG_GLOBAL` (an empty temp file), `GIT_CONFIG_NOSYSTEM=1`, `GIT_TERMINAL_PROMPT=0`. A **fake uv**
  (a Python script given as the request's `uv` command) that makes a fake venv whose interpreter imports the temp
  checkout's stub `helab` package, and fails on demand. A **fake HeLab** for the relaunch that writes the started
  mark, or exits 1, or hangs. A dummy process stands in for HeLab's pid and one for a helper (its command line
  names the checkout); a test-held lock for another instance. Cases: each refusal in §6's table; releases and
  branch success; the venv rebuilt only when the lock changed, reused otherwise; a `venv` symlink kept (POSIX;
  Windows where symlinks can be made); a failed venv build or import leaving the old version; a relaunch that
  exits → rolled back and the old one started; Restore (commit and venv back); the updater waits for the
  HeLab pid, the helper and the locks before touching a file (the tree is checked unchanged while they live);
  a stash made and kept; the test guard refusing a path outside the temp folder.
- `tests/test_updates_launch.py` (Qt): the copy, the request file, the handshake (ready seen → close called; not
  seen in time → message, no quit), the started mark written only with the token, `last.json` shown once.
- Existing tests I expect to touch (lists only): `tests/test_headless_imports.py` (`PURE`),
  `tests/test_accessible_names.py`; `tests/test_settings_defaults.py` should pass as is (new rows); possibly a
  test that pins the Help menu's items or About's text (to check; CoCo asked before changing one).

## 11. Questions for Tony (provisional)

- **Q~1 Default repo.** (a) A source checkout: the repo its current branch's upstream remote points at, when that
  is a known one, else `HeBECANU/HeLab`; a frozen build: its stamped `repository` when known, else
  `HeBECANU/HeLab` (**proposed**: a checkout of `TonyXTYan/HeLab`'s `dev/v0.0.9` then follows that branch with no
  setting changed, which Q65.3's "the branch HeLab runs from" needs). (b) Always `HeBECANU/HeLab` (the plan's
  default; a dev-branch checkout then finds no such branch until set).
- **Q~2 Branch mode's target.** (a) The newest commit with green CI, even if a later one is red or unfinished
  (that one just isn't offered yet) (**proposed**). (b) Stop before the first commit that isn't green.
- **Q~3 A new version that doesn't confirm its start in 3 min.** (a) Roll back only if it exited; never kill a
  running HeLab (**proposed**). (b) Kill it and roll back.
- **Q~4 Restore in branch mode.** (a) Move the local branch back (`git reset --keep`; only commits the repo's
  branch has are left behind) (**proposed**). (b) Detach at the previous commit (the checkout then defaults to
  releases).
- **Q~5 When the venv is rebuilt.** (a) `requirements.lock` changed (decided) **or** `setup.py` changed (its
  entry points and package data; **proposed**). (b) The lock only.
- **Q~6 No remote matches the repo.** (a) Fetch from the repo's URL directly, without adding a remote
  (**proposed**). (b) Refuse, showing the `git remote add` command.
- **Q~7 The relaunch.** (a) The venv's Python `-m helab`, no console (`pythonw.exe` on Windows) (**proposed**).
  (b) The command HeLab was started with (`sys.orig_argv`), console included.
- **Q~8 What's kept.** (a) One previous commit and one previous venv; the older venv deleted after the new
  version's started mark, listed as housekeeping (**proposed**). (b) Keep every previous venv until deleted by
  hand.
- **Q~9 The compiled converter kernel** (built in place by `native/build.py`, ignored by Git). (a) After an
  update whose `native/` or `helab/convert/backends/cython/` changed, rebuild it if one was built before, with
  the venv's Cython; a failure is a warning and HeLab uses NumPy (**proposed**). (b) Leave it; the window says to
  run `python native/build.py`.
- **Q~10 "Don't offer updates"** (the plan's per-PC switch for a measurement campaign). (a) The startup switch
  covers it: off, nothing shows until Help › Check for Updates… (**proposed**). (b) A separate switch that also
  hides the Help entry.
