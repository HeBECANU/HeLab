"""The version status (Release / Pre-release / Development version / Update available) and the offer, from
``BuildInfo`` and what a check learnt from the chosen repo (``github.Facts``). Pure: no Qt, no network.

A run's status depends only on its commit, its version and whether its tree is dirty, so a source run and a
frozen build of one commit get the same one. Versions compare with ``packaging.version.Version`` (the tag
without its ``v``); a tag that isn't PEP 440 is never a release here.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from packaging.version import InvalidVersion, Version

from helab.build_info import BuildInfo

# What a source checkout updates to (Q65.3): its branch, fast-forward only, or releases, tag to tag.
BRANCH = "branch"
RELEASES = "releases"
MODES = (BRANCH, RELEASES)

# The status kinds.
RELEASE = "release"
PRE_RELEASE = "pre-release"
DEVELOPMENT = "development"
UNCHECKED = "unchecked"


def parse_version(text: str) -> Version | None:
    """``text`` (a tag, with or without ``v``) as a PEP 440 version, or None."""
    try:
        return Version(text[1:] if text[:1] in "vV" else text)
    except InvalidVersion:
        return None


@dataclass(frozen=True)
class Release:
    """A published GitHub release (drafts never reach here)."""
    tag: str
    version: str  # The tag without "v", normalised.
    prerelease: bool  # GitHub marks it pre-release, or its version is a PEP 440 pre-release.
    published_at: str = ""
    html_url: str = ""
    notes: str = ""
    name: str = ""
    assets: tuple[tuple[str, str], ...] = ()  # (name, download URL)

    def asset_for(self, platform: str) -> str:
        """The download URL of this OS's zip (``HeLab-<os>.zip``; ``platform`` is ``sys.platform``), or ""."""
        wanted = {"darwin": "macos", "win32": "windows"}.get(platform, "ubuntu" if platform.startswith("linux") else "")
        for name, url in self.assets:
            if wanted and wanted in name.lower() and name.lower().endswith(".zip"):
                return url
        return ""


@dataclass(frozen=True)
class Commit:
    sha: str
    subject: str = ""
    date: str = ""
    html_url: str = ""

    @property
    def short(self) -> str:
        return self.sha[:6].upper()


@dataclass(frozen=True)
class BranchFacts:
    """The repo's branch against the running commit (``github``'s compare), and the newest green candidate."""
    branch: str
    state: str  # "identical", "ahead" (the repo has newer commits), "behind", "diverged", "missing"
    candidates: tuple[Commit, ...] = ()  # The branch's own newer commits (first-parent, from the tip), newest first.
    ci: tuple[tuple[str, str], ...] = ()  # (sha, "green" / "pending" / "red" and why) for the ones looked at
    target: Commit | None = None  # The newest candidate whose CI is green on all three OSes.
    more: bool = False  # The line goes on past the commits GitHub listed: counts are floors.

    def ci_of(self, sha: str) -> str:
        return dict(self.ci).get(sha, "")


@dataclass(frozen=True)
class Facts:
    """What one check learnt from a repo."""
    repository: str
    releases: tuple[Release, ...] = ()  # Newest first, as GitHub lists them.
    tags: tuple[tuple[str, str], ...] = ()  # (tag, commit) for the release tags resolved
    off_main: tuple[str, ...] = ()  # Release tags whose commit isn't on the repo's main: never offered.
    on_main: tuple[str, ...] = ()  # Release tags checked to be on main.
    branch: BranchFacts | None = None

    def tag_commit(self, tag: str) -> str:
        return dict(self.tags).get(tag, "")


@dataclass(frozen=True)
class Offer:
    """Something newer to update to: a release, or a branch's newest green commit."""
    kind: str  # RELEASES or BRANCH
    key: str  # What Skip this version stores: the version, or the commit.
    label: str  # "0.0.9", "dev/v0.0.9 +3"
    release: Release | None = None
    commit: Commit | None = None  # The commit it moves to (a release's tag commit, or the branch's target).
    ahead: int = 0  # Branch: how many commits it moves forward.


@dataclass(frozen=True)
class Status:
    kind: str  # RELEASE, PRE_RELEASE, DEVELOPMENT or UNCHECKED
    version: str
    offer: Offer | None = None
    skipped: bool = False  # The offer is the version (or commit) the user skipped.
    notes: tuple[str, ...] = field(default=())  # Why nothing is offered, when that needs saying.

    @property
    def text(self) -> str:
        if self.kind == RELEASE:
            return f"Release {self.version}"
        if self.kind == PRE_RELEASE:
            return f"Pre-release {self.version}"
        if self.kind == DEVELOPMENT:
            return f"Development version (based on {self.version})"
        return f"{self.version} (not checked yet)"

    @property
    def available(self) -> bool:
        """An offer that isn't skipped: what the status-bar mark and the Help entry show."""
        return self.offer is not None and not self.skipped

    def summary(self) -> str:
        """One line: the status, and the offer if any."""
        if self.offer is None:
            return self.text
        return f"{self.text}; update available: {self.offer.label}" + (" (skipped)" if self.skipped else "")


def on_channel(release: Release, prereleases: bool) -> bool:
    """Stable only, unless "Include pre-releases" is on."""
    return prereleases or not release.prerelease


def running_release(build: BuildInfo, facts: Facts) -> Release | None:
    """The published release whose tag names the running commit (a clean tree only)."""
    if build.commit == "unknown" or build.dirty:
        return None
    for release in facts.releases:
        if facts.tag_commit(release.tag) == build.commit:
            return release
    return None


def newer_releases(build: BuildInfo, facts: Facts, prereleases: bool) -> list[Release]:
    """The releases on the channel newer than the running version, newest first."""
    running = parse_version(build.version)
    found = []
    for release in facts.releases:
        version = parse_version(release.version)
        if version is None or not on_channel(release, prereleases):
            continue
        if running is None or version > running:
            found.append((version, release))
    return [release for _, release in sorted(found, key=lambda pair: pair[0], reverse=True)]


def release_offer(build: BuildInfo, facts: Facts, prereleases: bool) -> Offer | None:
    """The newest newer release on the channel whose tag commit is known and on main."""
    for release in newer_releases(build, facts, prereleases):
        commit = facts.tag_commit(release.tag)
        if commit and release.tag in facts.on_main and release.tag not in facts.off_main:
            return Offer(RELEASES, release.version, release.version, release=release,
                         commit=Commit(commit, release.name or release.tag, release.published_at, release.html_url))
    return None


def branch_offer(facts: Facts) -> Offer | None:
    branch = facts.branch
    if branch is None or branch.target is None:
        return None
    ahead = len(branch.candidates) - [c.sha for c in branch.candidates].index(branch.target.sha)
    return Offer(BRANCH, branch.target.sha, f"{branch.branch} +{ahead}{'+' if branch.more else ''}",
                 commit=branch.target, ahead=ahead)


def status(build: BuildInfo, facts: Facts | None, mode: str, prereleases: bool, skipped: str = "") -> Status:
    """The run's status and what it is offered. ``mode`` is the mode in use (a frozen build always
    RELEASES); ``skipped`` the version or commit Skip this version stored."""
    if facts is None:
        return Status(DEVELOPMENT if build.built_at is None and build.commit != "unknown" else UNCHECKED,
                      build.version)
    found = running_release(build, facts)
    kind, version = DEVELOPMENT, build.version
    if found is not None:
        kind, version = (PRE_RELEASE if found.prerelease else RELEASE), found.version
    offer = branch_offer(facts) if mode == BRANCH else release_offer(build, facts, prereleases)
    notes: list[str] = []
    if mode == BRANCH and facts.branch is not None and offer is None:
        notes.append(branch_note(facts.branch))
    return Status(kind, version, offer, skipped=offer is not None and bool(skipped) and offer.key == skipped,
                  notes=tuple(note for note in notes if note))


def branch_note(branch: BranchFacts) -> str:
    """Why a branch offers nothing, in words."""
    if branch.state == "identical":
        return f"Up to date with {branch.branch}."
    if branch.state in ("behind", "diverged"):
        return f"This checkout has commits {branch.branch} on GitHub doesn't: nothing to fast-forward to."
    if branch.state == "missing":
        return f"This commit or {branch.branch} isn't on the chosen repository."
    if branch.state == "ahead":
        return (f"{branch.branch} has {len(branch.candidates)}{'+' if branch.more else ''} newer commit(s), "
                "none of them (of those checked) "
                "with CI passed on macOS, Windows and Ubuntu yet.")
    return ""
