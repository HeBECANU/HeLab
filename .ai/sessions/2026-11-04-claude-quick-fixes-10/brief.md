# Brief: Quick Fixes 10 (`agent/quick-fixes-10`)

Coordinator: CoCo, 2026-11-04. Tony (Chat): "A59.1 ok / A59.2 ok / A56.7 ok / A58.2 ok". Worker: Rivet (Quick
Fixer, own worktree). CoCo reviews and lands on `dev/v0.0.9`.

Not in scope (Tony): A56.3 (leave `docs/.ai-generated/` where it is); A56.5 (hold until Tony has tried v0.0.8);
A56.4 (being explained to Tony).

## Items (AI_TODO has the full text; one commit each, with tests)

1. **A59.1 Release notes that link their tags** (`dev-cicd.yml`'s release job, `helab/release_draft.py`):
   - the tag named and linked;
   - a "Full Changelog: <previous>...<tag>" link, where the previous tag is the newest earlier `v*` tag in the
     commit's history;
   - GitHub's generated notes, with the manifest marker kept;
   - the Workflow Run link from `github.server_url`.

   Keep the draft-recovery path and its tests (`tests/test_release_recovery.py` and friends) working. Bodies are
   rewritten only while drafts. Test what can be tested offline: the body builder and the previous-tag choice, with
   fake tags including the v0.0.7a1 gap and non-`v` tags like `CI-CD-everything-passed` and `v.0.0.1i`.
2. **A59.2 (b) The no-stable front page** (`docs/publish/no-stable.html`, `docs/publish/site_versions.py`): name the
   newest pre-release as the latest download, e.g. "Latest: 0.0.8a1 (alpha)", linking to `pre-release/`. Test it.
   Propose the rule for `release-and-ci.md` in the handoff; don't edit `.ai/architecture/`.
3. **A56.7 `helab --help`**: `helab/main.py` prints a short usage and exits 0 before anything starts. The usage
   covers the app, `--version`, `--geometry`, `convert` and `cache`, each with its `--help`. The frozen helper
   dispatch stays first (AGENTS.md). Test it in a subprocess: no GUI, no `running.lock`.
4. **A58.2 Folder details' conversion and a read stopped early**: `explorer_convert.ExplorerConverter` names a read
   that stopped early and notifies once per file per session, as Live's auto-convert does (Q48.1, Q48.2). Use the
   same stop handling, and add a test.

## Base, branch, rules

- **Base and branch:** `dev/v0.0.9` at its HEAD when you start, a committed hash. Branch `agent/quick-fixes-10`,
  in your own worktree (`.ai/temp/quick-fixes-10`).
- **Owned paths:** `.github/workflows/dev-cicd.yml` (the release job only), `helab/release_draft.py`,
  `helab/release.py` if needed, `docs/publish/`, `helab/main.py` (argument handling before the GUI),
  `helab/views/explorer_convert.py` and the stop-handling code it shares, and their tests. Ask CoCo before any
  other file.
- **Checks:**
  - strict typing, including `--platform win32` and `pyright --pythonplatform Windows`;
  - tests never touch real data;
  - before the handoff, the full suite (`-n` with `--reruns 5 --reruns-delay 1`) and the five type checks, with
    every RERUN reported;
  - if `docs/` changes, also `ruff check` and `mkdocs build --strict`.
- **Handoff:** `.ai/sessions/2026-11-04-claude-quick-fixes-10/handoff.md`, with doc proposals (`release-and-ci.md`,
  `converter.md` or `app-runtime-and-ui.md`) and provisional `Q~`/`A~`/`M~` items.
- **Push and CI:** push once when done, then read every CI job's log for RERUN.
- **Not allowed:** no version bump, release, tag, PR, or edit of a published release.

When done: `maestri ask "CoCo" "QF10: done at <hash>, items <…>, suite <N>, RERUNs <…>, CI <run>"`.
