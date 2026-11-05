"""Build provenance without importing GUI services or depending on the launch folder."""

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import cast

from helab._version import __version__

BUILD_INFO_FILENAME = "_build_info.json"
PACKAGE_DIR = Path(__file__).resolve().parent
# A GitHub repository, "owner/name", and the remote URLs that name one (https or ssh, with or without .git).
REPOSITORY = re.compile(r"[A-Za-z0-9-]+/[A-Za-z0-9._-]+")
GITHUB_REMOTE = re.compile(r"(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)"
                           r"(?P<owner>[A-Za-z0-9-]+)/(?P<name>[A-Za-z0-9._-]+?)(?:\.git)?/?")


@dataclass(frozen=True)
class BuildInfo:
    version: str = __version__
    commit: str = "unknown"
    branch: str = "unknown"
    built_at: str | None = None
    dirty: bool | None = None
    build_ref: str = "unknown"
    # The GitHub repository the build came from ("owner/name"), stamped at build time only
    # (``write_build_info``), never read from Git at runtime: Help › User manual opens that
    # repository's site (``helab.utils.user_manual``). "unknown" for a source run or an older stamp.
    repository: str = "unknown"

    @property
    def short_commit(self) -> str:
        return self.commit[:6].upper() if self.commit != "unknown" else "unknown"

    def description(self) -> str:
        state = "unknown" if self.dirty is None else "modified" if self.dirty else "clean"
        return (f"HeLab {self.version}\nCommit: {self.commit}\nBranch: {self.branch}\n"
                f"Build ref: {self.build_ref}\n"
                f"Repository: {self.repository}\n"
                f"Built (UTC): {self.built_at or 'source checkout / unavailable'}\n"
                f"Source state: {state}")


def _git(root: Path, *arguments: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(root), *arguments], stderr=subprocess.DEVNULL,
        timeout=2, text=True,
    ).strip()


def checkout_build_info(root: Path) -> BuildInfo:
    """Only query the package's own checkout, never an enclosing/unrelated repository."""
    root = root.resolve()
    try:
        if not (root / ".git").exists() or Path(_git(root, "rev-parse", "--show-toplevel")).resolve() != root:
            return BuildInfo()
        commit = _git(root, "rev-parse", "HEAD")
        branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
        if branch == "HEAD":
            branch = "detached"
        dirty = bool(_git(root, "status", "--porcelain", "--untracked-files=normal"))
        ref = f"refs/heads/{branch}" if branch != "detached" else "unknown"
        return BuildInfo(commit=commit, branch=branch, dirty=dirty, build_ref=ref)
    except (OSError, subprocess.SubprocessError):
        return BuildInfo()


def read_build_info(path: Path) -> BuildInfo | None:
    """Missing, malformed or mismatched metadata cannot masquerade as a valid build."""
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return None
        data = cast(dict[str, object], payload)
        commit, branch = data.get("commit"), data.get("branch")
        built_at, dirty = data.get("built_at"), data.get("dirty")
        build_ref = data.get("build_ref", "unknown")
        if data.get("version") != __version__ or not isinstance(commit, str):
            return None
        if commit != "unknown" and not re.fullmatch(r"[0-9a-f]{40,64}", commit):
            return None
        if not isinstance(branch, str) or not branch:
            return None
        if not isinstance(build_ref, str) or not build_ref:
            return None
        if not isinstance(built_at, str) or datetime.fromisoformat(built_at).utcoffset() != timezone.utc.utcoffset(None):
            return None
        if dirty is not None and not isinstance(dirty, bool):
            return None
        # Stamps from before the field have none; one that isn't "owner/name" is unknown.
        repository = data.get("repository", "unknown")
        if not isinstance(repository, str) or not REPOSITORY.fullmatch(repository):
            repository = "unknown"
        return BuildInfo(commit=commit, branch=branch, built_at=built_at, dirty=dirty, build_ref=build_ref,
                         repository=repository)
    except (OSError, ValueError, TypeError):
        return None


def get_build_info() -> BuildInfo:
    metadata = PACKAGE_DIR / BUILD_INFO_FILENAME
    if metadata.exists():
        return read_build_info(metadata) or BuildInfo()
    if getattr(sys, "frozen", False):
        return BuildInfo()
    return checkout_build_info(PACKAGE_DIR.parent)


def build_repository(root: Path) -> str:
    """The GitHub repository a build comes from, "owner/name" (build time only): CI's own
    (``HELAB_BUILD_REPOSITORY``, else GitHub's ``GITHUB_REPOSITORY``), else the checkout's
    ``origin`` remote when it is on GitHub; "unknown" otherwise."""
    named = os.environ.get("HELAB_BUILD_REPOSITORY")
    if not named and os.environ.get("GITHUB_ACTIONS") == "true":
        named = os.environ.get("GITHUB_REPOSITORY")
    if named:
        return named if REPOSITORY.fullmatch(named) else "unknown"
    try:
        if not (root / ".git").exists():
            return "unknown"
        remote = _git(root, "remote", "get-url", "origin")
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    match = GITHUB_REMOTE.fullmatch(remote)
    return f"{match['owner']}/{match['name']}" if match else "unknown"


def upstream_repository(root: Path, branch: str) -> str:
    """The GitHub repository ("owner/name") of ``branch``'s upstream remote in the package's own checkout
    (its raw configured URL, never a remote's name), or "unknown": the update check's default repo for a
    source run (``helab.updates.settings``). Read-only, two local ``git config`` reads."""
    root = root.resolve()
    if branch in ("unknown", "detached") or not (root / ".git").exists():
        return "unknown"
    try:
        remote = _git(root, "config", "--get", f"branch.{branch}.remote")
        url = _git(root, "config", "--get", f"remote.{remote}.url") if remote and remote != "." else ""
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    match = GITHUB_REMOTE.fullmatch(url)
    return f"{match['owner']}/{match['name']}" if match else "unknown"


def write_build_info(root: Path, destination: Path) -> BuildInfo:
    """Write into build output, leaving the source package untouched."""
    info = replace(checkout_build_info(root), built_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    # These labels describe the CI source/build ref; commit always comes from Git HEAD.
    branch = os.environ.get("HELAB_BUILD_BRANCH")
    ref = os.environ.get("HELAB_BUILD_REF")
    if os.environ.get("GITHUB_ACTIONS") == "true":
        branch = branch or os.environ.get("GITHUB_HEAD_REF") or os.environ.get("GITHUB_REF_NAME")
        ref = ref or os.environ.get("GITHUB_REF")
    info = replace(info, branch=branch or info.branch, build_ref=ref or info.build_ref,
                   repository=build_repository(root.resolve()))
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(asdict(info), indent=2) + "\n", encoding="utf-8")
    return info
