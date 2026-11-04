"""MkDocs hook: ``{repo_url}`` in a page is this site's repository (mkdocs.yml's ``repo_url``).

CI sets ``HELAB_DOCS_REPO_URL`` to the repository the site is built from, so each copy of the repo
(a fork, the lab's) links its own clone URL and releases; a local build uses mkdocs.yml's default.
Not a page: mkdocs.yml's ``exclude_docs`` keeps this folder out of the site.
"""
from __future__ import annotations

from typing import Any


def on_page_markdown(markdown: str, page: Any, config: Any, files: Any) -> str:
    """The page with ``{repo_url}`` replaced by the site's repository URL (no trailing slash)."""
    return markdown.replace("{repo_url}", str(config["repo_url"]).rstrip("/"))
