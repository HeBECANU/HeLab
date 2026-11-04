"""The user manual's site (Q54.2) is published only when a release is published, never by a push, a PR
or the release job's draft: read from the workflow files as text (CI's tests have no YAML parser)."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"


def _on_block(text: str) -> list[str]:
    """The workflow's top-level ``on:`` block, its lines stripped."""
    lines = text.splitlines()
    start = lines.index("on:")
    block = []
    for line in lines[start + 1:]:
        if line and not line.startswith((" ", "#")):
            break
        if line.strip() and not line.lstrip().startswith("#"):
            block.append(line.strip())
    return block


def test_the_site_is_published_only_when_a_release_is_published() -> None:
    text = (WORKFLOWS / "docs-site.yml").read_text(encoding="utf-8")
    assert _on_block(text) == ["release:", "types: [published]"]
    assert "docs/publish/site_versions.py" in text and "${{ github.repository }}" in text and "TonyXTYan" not in text


def test_no_other_workflow_publishes_the_site() -> None:
    for path in sorted(WORKFLOWS.glob("*.yml")):
        if path.name != "docs-site.yml":
            text = path.read_text(encoding="utf-8")
            assert "mike " not in text and "gh-pages" not in text, path.name


def test_a_release_of_a_commit_without_the_manual_skips() -> None:
    """A release of an older commit (before the manual) skips the deploy with a notice, as ci-build.yml
    builds such a commit without the manual, rather than failing on a missing requirements-docs.lock."""
    text = (WORKFLOWS / "docs-site.yml").read_text(encoding="utf-8")
    assert "[ -f mkdocs.yml ] && [ -f requirements-docs.lock ]" in text
    steps = text.split("- name: ")[1:]
    after_check = [step for step in steps if not step.startswith(("Checkout", "Check this commit"))]
    assert after_check and all("if: steps.manual.outputs.present == 'true'" in step for step in after_check)


def test_the_pages_name_no_fixed_repository() -> None:
    """Each copy of the repo publishes its own site (Q54.2): a page links its repository through
    ``{repo_url}`` (docs/hooks/repo_links.py), never a fixed github.com/<owner>/HeLab."""
    docs = WORKFLOWS.parents[1] / "docs"
    pages = [path for path in docs.rglob("*.md") if ".ai-generated" not in path.parts]
    assert pages
    for path in pages:
        assert "github.com/" not in path.read_text(encoding="utf-8").replace("github.com/{", ""), path


def _site_versions() -> Any:
    """``docs/publish/site_versions.py`` (not a package module: loaded from its file)."""
    path = WORKFLOWS.parents[1] / "docs" / "publish" / "site_versions.py"
    spec = importlib.util.spec_from_file_location("site_versions", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _deployed(*entries: tuple[str, list[str]]) -> list[dict[str, Any]]:
    return [{"version": version, "title": version, "aliases": aliases} for version, aliases in entries]


def test_the_workflow_deploys_through_the_site_versions_plan() -> None:
    """Q56.3: the deploy runs docs/publish/site_versions.py for the release's version (no fixed alias)."""
    text = (WORKFLOWS / "docs-site.yml").read_text(encoding="utf-8")
    assert 'python docs/publish/site_versions.py "$version"' in text
    assert "mike deploy --push --update-aliases \"$version\" latest" not in text
    assert "[ -f docs/publish/site_versions.py ]" in text


def test_until_a_stable_release_the_front_page_says_so_and_links_the_newest_pre_release() -> None:
    """Q56.3: each pre-release is a version; the newest takes ``pre-release``; with no stable release the
    front page is the "No stable release yet" template, linking to ``pre-release``."""
    site = _site_versions()
    template = site.NO_STABLE_TEMPLATE
    assert site.plan("0.0.8a1", []) == [
        ["mike", "deploy", "--push", "--update-aliases", "0.0.8a1", "pre-release"],
        ["mike", "set-default", "--push", "--template", template, "pre-release"]]
    assert site.plan("0.0.8b1", _deployed(("0.0.8a1", ["pre-release"])))[0][-1] == "pre-release"
    # An older pre-release published late: its version only.
    assert site.plan("0.0.7a1", _deployed(("0.0.8a1", ["pre-release"])))[0] == [
        "mike", "deploy", "--push", "--update-aliases", "0.0.7a1"]
    text = Path(template).read_text(encoding="utf-8")
    assert "No stable release yet" in text and 'href="{{href}}"' in text


def test_the_newest_stable_release_is_latest_and_the_front_page() -> None:
    """Q56.3: a stable release takes ``latest`` and the front page; after it, a pre-release moves
    ``pre-release`` only, and an older stable release published late moves no alias."""
    site = _site_versions()
    assert site.plan("0.0.8", _deployed(("0.0.8a1", ["pre-release"]))) == [
        ["mike", "deploy", "--push", "--update-aliases", "0.0.8", "latest"],
        ["mike", "delete", "--push", "pre-release"],  # (Q58.3 (b): a newer stable release removes it.)
        ["mike", "set-default", "--push", "latest"]]
    after = _deployed(("0.0.8", ["latest"]), ("0.0.8a1", ["pre-release"]))
    assert site.plan("0.0.9a1", after) == [
        ["mike", "deploy", "--push", "--update-aliases", "0.0.9a1", "pre-release"],
        ["mike", "set-default", "--push", "latest"]]
    assert site.plan("0.0.7", after)[0] == ["mike", "deploy", "--push", "--update-aliases", "0.0.7"]
    assert site.plan("0.0.8rc1", after)[1] == ["mike", "set-default", "--push", "latest"]
    # Publishing a version again (a fixed release's docs) keeps its alias.
    assert site.plan("0.0.8", after)[0][-1] == "latest"
    # An entry that isn't a version (deployed by hand) is left alone.
    assert site.plan("0.0.9", [*after, {"version": "dev", "aliases": []}])[0][-1] == "latest"


def _check_offline() -> Any:
    path = WORKFLOWS.parents[1] / "docs" / "publish" / "check_offline.py"
    spec = importlib.util.spec_from_file_location("check_offline", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_offline_check_names_each_script_from_elsewhere(tmp_path: Path) -> None:
    """The bundled manual must search from file:// without a network: a page loading a script from
    elsewhere (unpkg's iframe-worker shim, a protocol-relative URL) is named; the site's own files and
    data: URLs aren't; external stylesheets (fonts) aren't counted."""
    check = _check_offline()
    (tmp_path / "how-to").mkdir()
    (tmp_path / "index.html").write_text(
        '<html><head><script src="https://unpkg.com/iframe-worker/shim"></script>'
        '<link rel="stylesheet" href="https://fonts.googleapis.com/css"></head>'
        '<body><script src="js/iframe-worker-shim.js"></script><script>inline()</script></body></html>')
    (tmp_path / "how-to" / "live.html").write_text(
        '<script src="//cdn.example.org/x.js"></script><script src="data:text/javascript,1"></script>'
        '<script src="../assets/javascripts/bundle.js"></script>')
    assert check.external_scripts(tmp_path) == [
        ("how-to/live.html", "//cdn.example.org/x.js"), ("index.html", "https://unpkg.com/iframe-worker/shim")]
    assert check.main([str(tmp_path)]) == 1
    (tmp_path / "index.html").write_text('<script src="js/iframe-worker-shim.js"></script>')
    (tmp_path / "how-to" / "live.html").write_text('<script src="../assets/javascripts/bundle.js"></script>')
    assert check.main([str(tmp_path)]) == 0


def test_the_shim_is_vendored_with_its_licence_and_the_docs_job_checks_the_offline_copy() -> None:
    """Material's offline plugin loads the iframe-worker shim from unpkg.com unless a polyfill names it:
    the vendored copy (MIT, its licence beside it) is listed, and the Docs job checks the offline build."""
    root = WORKFLOWS.parents[1]
    shim = (root / "docs" / "js" / "iframe-worker-shim.js").read_text(encoding="utf-8")
    assert shim.startswith("/*! iframe-worker 1.0.4") and "location.protocol===\"file:\"" in shim
    licence = (root / "docs" / "js" / "LICENSE-iframe-worker.txt").read_text(encoding="utf-8")
    assert "Permission is hereby granted, free of charge" in licence
    assert "  polyfills:\n    - js/iframe-worker-shim.js\n" in (root / "mkdocs.yml").read_text(encoding="utf-8")
    docs_job = (WORKFLOWS / "dev-cicd.yml").read_text(encoding="utf-8")
    assert "HELAB_DOCS_OFFLINE: 'true'" in docs_job and 'python docs/publish/check_offline.py "$RUNNER_TEMP/offline"' in docs_job


def test_a_failing_mike_list_stops_the_deploy(monkeypatch: Any, capsys: Any) -> None:
    """Without gh-pages, ``mike list --json`` prints [] and succeeds; a failure is a real one, and planning
    as if nothing were deployed could put "No stable release yet" over a stable release (review nit)."""
    import subprocess
    site = _site_versions()
    ran: list[list[str]] = []

    def failing(command: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        ran.append(command)
        return subprocess.CompletedProcess(command, 1, "", "fatal: bad object gh-pages")
    monkeypatch.setattr(site.subprocess, "run", failing)
    assert site.main(["0.0.8a1"]) == 1
    assert ran == [["mike", "list", "--json"]] and "mike list failed (1): fatal: bad object" in capsys.readouterr().err


def _apply(commands: list[list[str]], deployed: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str]:
    """``deployed`` after ``commands``, as mike does it (deploy with ``--update-aliases`` moves its aliases to
    the version; ``delete`` of an alias removes only the alias), and the front page's default."""
    state = [{**entry, "aliases": list(entry["aliases"])} for entry in deployed]
    default = ""
    for command in commands:
        verb, rest = command[1], [part for part in command[2:] if not part.startswith("--")]
        if verb == "deploy":
            version, aliases = rest[0], rest[1:]
            for entry in state:
                entry["aliases"] = [alias for alias in entry["aliases"] if alias not in aliases]
            state = [entry for entry in state if entry["version"] != version]
            state.append({"version": version, "title": version, "aliases": aliases})
        elif verb == "delete":
            for entry in state:
                entry["aliases"] = [alias for alias in entry["aliases"] if alias not in rest]
        elif verb == "set-default":
            default = "no-stable" if "--template" in command else rest[-1]
    return state, default


def test_a_newer_stable_release_removes_the_pre_release_alias_until_the_next_pre_release() -> None:
    """Q58.3 (b) (Tony, 2026-11-03): 0.0.8a1, 0.0.8b1, 0.0.8, 0.0.9a1. ``pre-release`` follows the newest
    pre-release; the stable 0.0.8 removes it (rather than pointing it at ``latest``, which would call the
    stable release a pre-release too) and takes ``latest`` and the front page; 0.0.9a1 brings it back. A
    pre-release published late, older than the stable release, doesn't take it."""
    site = _site_versions()
    deployed: list[dict[str, Any]] = []
    menus = []
    for version in ("0.0.8a1", "0.0.8b1", "0.0.8", "0.0.9a1", "0.0.8rc1"):
        deployed, default = _apply(site.plan(version, deployed), deployed)
        menus.append(({entry["version"]: entry["aliases"] for entry in deployed}, default))
    assert menus == [
        ({"0.0.8a1": ["pre-release"]}, "no-stable"),
        ({"0.0.8a1": [], "0.0.8b1": ["pre-release"]}, "no-stable"),
        ({"0.0.8a1": [], "0.0.8b1": [], "0.0.8": ["latest"]}, "latest"),
        ({"0.0.8a1": [], "0.0.8b1": [], "0.0.8": ["latest"], "0.0.9a1": ["pre-release"]}, "latest"),
        ({"0.0.8a1": [], "0.0.8b1": [], "0.0.8": ["latest"], "0.0.9a1": ["pre-release"], "0.0.8rc1": []}, "latest")]
    # A stable release older than the alias's target (0.0.8.1 after 0.0.9a1) leaves it alone.
    assert ["mike", "delete", "--push", "pre-release"] not in site.plan("0.0.8.1", deployed)
