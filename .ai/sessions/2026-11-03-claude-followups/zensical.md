# Zensical check (Q56.1), for CoCo's ◆ before switching

Worker: Mend, Follow-ups floor, 2026-11-03. Zensical **0.0.74** (zensical-ui 0.0.41) from PyPI, with
mkdocstrings[python], in a scratch venv (`.ai/temp/zensical-venv`, not in the lock). Built from this
branch's unchanged `mkdocs.yml` (Zensical reads it; `!ENV` tags work, which `zensical.toml` can't do), and
compared with today's Material 9.8.0 build. Searches driven in the installed Chrome through Playwright
(scratch only), from `file://`, with the network on and off.

| Tony's list | Zensical 0.0.74 | Evidence |
|---|---|---|
| Offline search in the bundled copy, from `file://` | **Yes, once the shim is bundled** (see 1) | offline build, Chrome offline: "12 results" for *converter* with `extra.polyfills: [js/iframe-worker-shim.js]`; "Search is unavailable" without it |
| Version menu | **Only through mike's fork, untested here** (see 2) | the theme's bundle reads `versions.json`; config accepts the `mike` plugin; fork install was blocked locally |
| mkdocstrings' API reference | Yes | same 39 headings and 41 links on the Script page as Material; autorefs resolve |
| Dark mode | Yes | both palettes (`default`, `slate`), the toggle named "Dark mode"; dark rendering checked by screenshot |
| Code copy | Yes | `content.code.copy`: a copy button per code block (in the browser) |
| Navigation sections | Yes | `navigation.sections` renders the groups as now |
| Warnings as errors in CI | **Yes for links and anchors**; not for pages missing from `nav` | `zensical build --strict` exits 1 on a missing page and a missing anchor; Zensical checks only links so far (its config: "we only support validation of links right now") |
| Build time | 1.3 s (Material: 1.7 s) | |

## What would change or is missing

1. **Offline search needs a bundled shim, in both tools.** The bundled copy loads the `file://` shim
   (`iframe-worker`) from `unpkg.com`. **Today's Material copy has the same gap:** from `file://` with no
   network, its search stays at "Initializing search" (checked). Fix in either: vendor
   `iframe-worker@1.0.4/shim` (1.4 KB, MIT) as `docs/js/iframe-worker-shim.js`; Zensical takes it through
   `extra.polyfills` (file name must contain `iframe-worker`), checked working offline. This is worth doing
   whatever the answer below (a lab PC offline has no manual search today).
2. **The version menu needs mike's Zensical fork,** `pip install git+https://github.com/squidfunk/mike.git`:
   not on PyPI, "based on mike 2.2.0, compatibility fixes but no new features", called *transitional* by
   Zensical's docs until native versioning (no date). PyPI's mike 2.2.0 runs `mkdocs build` itself, so it
   can't build a Zensical site. The lock would pin the fork by commit (`git+…@<sha>`), and CI's docs-site job
   needs git (it has it). I couldn't install the fork here (the permission check blocks installs from a git
   URL), so the deploy through it is unverified: the first real check would be a dry run in CI or on Tony's
   say-so locally. `docs/publish/site_versions.py` (Q56.3) only calls `mike deploy/set-default/list`, which
   the fork keeps.
3. **MkDocs hooks don't run.** `docs/hooks/repo_links.py` (the `{repo_url}` in pages) is silently ignored:
   the built pages link to `../{repo_url}/releases`, and strict mode doesn't notice. Replacement checked:
   Zensical's built-in `macros` with `{{ config.repo_url }}` in the two pages (a fork's URL from
   `HELAB_DOCS_REPO_URL` comes out right). No page has other `{{`/`{%` text.
4. **`validation.nav.omitted_files`** (a page left out of `nav`) isn't checked by Zensical; links and anchors
   are. Minor: `nav` is short and hand-kept.
5. **Maturity:** 0.0.x releases (0.0.74), the UI a separate package; the theme looks like Material's
   "modern" variant (Inter font, new search dialog, ⌘K). Material 9.8 still builds (with its end-of-life
   banner in every build).

## The switch, if CoCo says go

- `mkdocs.yml`: keep the file (Zensical reads it, `!ENV` needs YAML); `hooks:` → `plugins: - macros`; the two
  `{repo_url}` pages → `{{ config.repo_url }}`; `extra.polyfills` with the vendored shim; drop the
  Material-only bits Zensical ignores. Theme name stays `material` (Zensical's compatible theme).
  `zensical build` has no `-d` (output folder) option, only `-f`, `--clean`, `--strict`: CI's
  `mkdocs build -d …` becomes `site_dir: !ENV [HELAB_DOCS_SITE_DIR, site]` and the variable.
- `requirements-docs.txt` / `.lock`: `zensical`, `mkdocstrings[python]`, mike's fork pinned by commit, `ruff`;
  drop `mkdocs-material` and PyPI's `mike`.
- The Docs job (`dev-cicd.yml`): `zensical build --strict`.
- The deploy (`docs-site.yml`): the same planner; the fork in the lock.
- The bundle: `HeLab.spec` reads `build/manual/index.html`, which `ci-build.yml`'s manual step builds with
  `mkdocs build`: **that step is in `ci-build.yml`, outside my owned paths** (needs CoCo's word).
- README's User manual section; `docs/hooks/repo_links.py` removed; tests that name `mkdocs` updated.

## Alternative

Stay on Material 9.8 for v0.0.8 (it works and keeps PyPI's mike), vendor the shim now (item 1, either way),
and move to Zensical when it has native versioning or the fork is on PyPI, before Material's end of life
(2027-05-05).
