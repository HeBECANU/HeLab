# Brief: v0.0.8 follow-ups (`agent/followups`)

Coordinator: CoCo, 2026-11-03. Tony (Chat, 2026-11-03 evening): "go follow-ups". These are his decisions, recorded
in `.ai/DECISIONS_TODO.md` under "Recently decided" ("Tony in Chat, 2026-11-03 evening") and in block 56. One
Worker; one Reviewer at landing.

## Read first

- `AGENTS.md`.
- The decisions: Q48.2, Q48.3, Q49.3, Q56.1, Q56.3. For background, their old entries are in git history:
  `git show 752e935:.ai/DECISIONS_TODO.md`, blocks 48, 49 and 56.
- The handoffs that built the code you change:
  - `.ai/sessions/2026-11-02-claude-converter-ux/` (the read-stopped line, A37.1; the share questions, A39.5);
  - `.ai/sessions/2026-11-02-claude-live-scripts/` (reload);
  - `.ai/sessions/2026-11-03-claude-docs-manual/` (the manual, `docs-site.yml`, the bundled copy, Help).
- `.ai/architecture/converter.md`, `plots-and-scripts.md`, `release-and-ci.md` and `app-runtime-and-ui.md`.

## Base and branch

Base: `dev/v0.0.8`, `6a0fb25`. Branch: `agent/followups`. You're the only
floor working, besides Caching v2, which is idle.

## Objective (in this order; commit each separately; stop and report to CoCo at each ◆)

1. **Q48.2.** A raw read that stopped early also sends a system notification, once per file per session, as a
   damaged file does (through `helab/utils/events.py`). Add a test.
2. **Q48.3.** `helab convert`'s `--yes` is replaced by **`--output beside-forced`**, like `cache-forced`:
   - it writes beside the raw files even on a share, with no question, and still logs a warning;
   - plain `--output beside` on a share asks on a terminal, and without one falls back to HeLab's folder with a
     warning that names `beside-forced`;
   - `--yes` goes; passing it is an argparse error that names `--output beside-forced`.

   Update the help text, the manual's convert page and the tests.
3. **Q49.3 (b), the try-import.** Before HeLab imports a script folder, at start (remembered folders) and on
   every reload (manual or on save), it try-imports that folder's scripts in a **separate helper process with a
   time limit**. A folder that hangs or crashes there is skipped, with a message in the Scripts panel ("didn't
   load: its import didn't finish within N s"). The real import stays on the GUI thread, as now.
   - **The GUI never waits:** the helper runs asynchronously (QProcess or the existing helper machinery), and
     the import follows when it answers.
   - **The frozen app:** the helper needs an entry point that works in the frozen app, through `main.py`'s
     frozen helper dispatch before any GUI import (AGENTS.md).
   - **The time limit:** propose it, e.g. 10 s, as a settings row or a constant.
   - **The double import:** the manual's script page says, in one line, that a script's import-time code runs
     twice.
   - **The existing loading marker:** keep it, or say why it's no longer needed.

   ◆ **Send CoCo a short design (`design.md`) before code:** the helper's entry, the protocol, the time limit,
   reload's flow, and the tests.
4. **Q56.3, the site's versions.**
   - The site's front page is the newest **stable** release.
   - Until there is one, a short "No stable release yet" page links to the pre-releases.
   - The version menu lists each release, plus a **pre-release** alias for the newest alpha or beta.
   - No dev channel: the manual's README section says how to build it locally.
   - Help › User manual's site URL follows: the running version's page.

   Change `docs-site.yml`'s mike calls and aliases and `helab/utils/user_manual.py` if needed, with tests. Still
   deploy only on a published release.
5. **Q56.1, Zensical.** Tony: "use Zensical then, I want offline search, version menu, dark mode, and other
   things".
   - First check, on this branch, that Zensical gives all of these:
     - offline search in the copy bundled in the app, from `file://`;
     - a version menu with mike, or Zensical's own versioning;
     - mkdocstrings' API reference;
     - dark mode;
     - code copy;
     - navigation sections;
     - `--strict`-like warnings as errors in CI.
   - ◆ **Report the result to CoCo before switching.** If anything Tony named is missing or immature, say so,
     with the alternative.
   - On CoCo's word, switch: the config, `requirements-docs.*`, the Docs job, the deploy, the bundle in
     `HeLab.spec`, the README.
6. **Docs proposals** in the handoff, plus provisional `Q~`/`A~`/`M~` items.

## Rules

Owned paths:
- `helab/convert_cli.py`;
- the read-stopped notification's code path (`helab/views/explorer_live.py`, `FolderDetailsPanel.py` or
  wherever the read-stopped line is handled; name it in the commit);
- `helab/utils/events.py`;
- `helab/scripts/scripts_manager.py`;
- a new `helab/scripts/probe.py` (or similar) for the try-import;
- `helab/views/plots/script_tree.py`;
- `helab/main.py` (the frozen dispatch entry only);
- `docs/**`, `mkdocs.yml` (or Zensical's config), `requirements-docs.*`;
- `.github/workflows/docs-site.yml` and the Docs job in `dev-cicd.yml`;
- `HeLab.spec` (the manual's build only);
- `helab/utils/user_manual.py`;
- the README's docs section;
- their tests.

Ask CoCo before any other file.

- Strict typing, including `--platform win32` and `pyright --pythonplatform Windows`.
- Tests never touch real data.
- Before each ◆ and the handoff: the full suite (`-n` with `--reruns 5 --reruns-delay 1`) and the five type
  checks, with every RERUN reported.
- Docs go in `.ai/sessions/2026-11-03-claude-followups/` only.
- Push at checkpoints. Before reporting a CI run, read every job's log for RERUN.
- No version bump, release, tag, PR or Pages deploy.

When done: `maestri ask "CoCo" "Follow-ups: done at <hash>, suite <N> passed, RERUNs <…>, CI <run>"`.
