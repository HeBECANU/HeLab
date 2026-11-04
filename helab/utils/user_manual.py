"""Where Help › User manual opens the manual, always in the system browser (never a QtWebEngine
view: some lab PCs' can't draw).

In order (``targets``):

1. the manual's site for the running version, on the GitHub Pages of the repository the build came
   from (``BuildInfo.repository``, stamped at build time, so a build of another copy of the repo opens
   that copy's site): ``https://<owner>.github.io/<name>/<version>/``. The menu item checks it first,
   asynchronously; a failed or slow check falls back;
2. the copy built into the app (``manual/index.html`` beside the package, added by ``HeLab.spec``;
   never in the source package): used when the site can't be reached, or straight away when the
   build has no site (a source run);
3. the manual's first page on GitHub at the repository's default branch, when there is neither.

Qt-free and pure: the window does the check and the opening.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from helab import build_info
from helab.build_info import REPOSITORY, BuildInfo

# The repository whose GitHub page a source run opens: it knows no repository of its own (the build
# stamp records one; a source run never asks Git at runtime).
DEFAULT_REPOSITORY = "TonyXTYan/HeLab"
# The built manual in a frozen app, relative to the package folder.
BUNDLED_INDEX = Path("manual") / "index.html"
# How long the site check may take before the bundled copy opens instead (ms; Qt's transfer
# timeout, which counts time without progress).
SITE_CHECK_TIMEOUT_MS = 3000


@dataclass(frozen=True)
class ManualTargets:
    """Where the manual opens: ``site`` once a check finds it (None: no site to check), else
    ``fallback``, a URL that needs no check (the bundled copy as a ``file://`` URL, or GitHub's
    page)."""

    site: str | None
    fallback: str


def site_url(info: BuildInfo) -> str | None:
    """The running version's page on the build's repository's GitHub Pages; None when the build
    doesn't know its repository (a source run, or a stamp from before the field)."""
    if not REPOSITORY.fullmatch(info.repository) or not info.version:
        return None
    owner, name = info.repository.split("/", 1)
    return f"https://{owner.lower()}.github.io/{name}/{info.version}/"


def github_page(info: BuildInfo) -> str:
    """The manual's first page on GitHub at the default branch of the build's repository (this
    repository for a source run)."""
    repository = info.repository if REPOSITORY.fullmatch(info.repository) else DEFAULT_REPOSITORY
    return f"https://github.com/{repository}/blob/HEAD/docs/index.md"


def bundled_index(package_dir: Path) -> Path | None:
    """The manual built into the app, if this one has it."""
    index = package_dir / BUNDLED_INDEX
    return index if index.is_file() else None


def targets(info: BuildInfo, package_dir: Path | None = None) -> ManualTargets:
    """Where Help › User manual opens for this build: its site, then its bundled copy, then GitHub.
    ``package_dir``: where the bundled copy is looked for (default: HeLab's package folder)."""
    bundled = bundled_index(build_info.PACKAGE_DIR if package_dir is None else package_dir)
    fallback = bundled.resolve().as_uri() if bundled is not None else github_page(info)
    return ManualTargets(site_url(info), fallback)
