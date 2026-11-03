"""The user manual's site (Q54.2) is published only when a release is published, never by a push, a PR
or the release job's draft: read from the workflow files as text (CI's tests have no YAML parser)."""
from __future__ import annotations

from pathlib import Path

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
    assert "mike deploy" in text and "${{ github.repository }}" in text and "TonyXTYan" not in text


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
