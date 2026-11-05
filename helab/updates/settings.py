"""The update settings (Settings › General's rows, ``settings_defaults``' ``updates_*`` rows), read through
``read_setting``, with their defaults resolved for this run: the repo (Q~1: the branch's upstream remote's
when it is a known one, else HeBECANU/HeLab) and the mode (Q65.3: a source checkout on a branch follows
that branch; a detached checkout and a compiled build follow releases).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from functools import cache
import sys

from PyQt6.QtCore import QSettings

from helab import build_info
from helab.build_info import BuildInfo
from helab.updates.github import DEFAULT_REPOSITORY, REPOSITORIES
from helab.updates.versions import BRANCH, MODES, RELEASES
from helab.utils.settings_defaults import (
    UPDATES_CHECK_AT_START_SETTING, UPDATES_LAST_CHECK_SETTING, UPDATES_MODE_SETTING, UPDATES_PRERELEASES_SETTING,
    UPDATES_REPOSITORY_SETTING, UPDATES_SKIPPED_SETTING, read_setting)


def is_source(build: BuildInfo) -> bool:
    """A git checkout run from source (it can update itself); a frozen or packaged build only checks."""
    return not getattr(sys, "frozen", False) and build.built_at is None and build.commit != "unknown"


def on_branch(build: BuildInfo) -> bool:
    return build.branch not in ("unknown", "detached", "HEAD", "")


def known_repository(name: str) -> str:
    """``name`` as one of the known repos (GitHub's names ignore case), or ""."""
    for repository in REPOSITORIES:
        if name.lower() == repository.lower():
            return repository
    return ""


@cache
def _upstream(build: BuildInfo) -> str:
    return build_info.upstream_repository(build_info.PACKAGE_DIR.parent, build.branch)


def default_repository(build: BuildInfo) -> str:
    """Q~1 (a): a source checkout follows its branch's upstream remote when that is a known repo; a build
    its stamped repository when known; else HeBECANU/HeLab."""
    found = known_repository(_upstream(build)) if is_source(build) and on_branch(build) else ""
    return found or known_repository(build.repository) or DEFAULT_REPOSITORY


def default_mode(build: BuildInfo) -> str:
    return BRANCH if is_source(build) and on_branch(build) else RELEASES


@dataclass(frozen=True)
class UpdateSettings:
    check_at_start: bool
    repository: str  # Always a known repo.
    mode: str  # The mode in use: RELEASES for a compiled build or a checkout off a branch.
    prereleases: bool
    skipped: str
    last_check: datetime | None
    chosen_repository: str = ""  # What's saved ("": the default)
    chosen_mode: str = ""

    def due(self, now: datetime) -> bool:
        """Whether the startup check runs: on, and the last successful check over a day ago (or in the
        future, or never)."""
        if not self.check_at_start:
            return False
        if self.last_check is None or self.last_check > now:
            return True
        return (now - self.last_check).total_seconds() >= 24 * 3600


def parse_time(text: str) -> datetime | None:
    try:
        found = datetime.fromisoformat(text)
    except ValueError:
        return None
    return found if found.tzinfo is not None else found.replace(tzinfo=timezone.utc)


def read(settings: QSettings, build: BuildInfo) -> UpdateSettings:
    repository = known_repository(str(read_setting(settings, UPDATES_REPOSITORY_SETTING, typed=True)))
    mode = str(read_setting(settings, UPDATES_MODE_SETTING, typed=True))
    mode = mode if mode in MODES else ""
    effective = (mode or default_mode(build)) if is_source(build) and on_branch(build) else RELEASES
    return UpdateSettings(
        check_at_start=bool(read_setting(settings, UPDATES_CHECK_AT_START_SETTING, typed=True)),
        repository=repository or default_repository(build), mode=effective,
        prereleases=bool(read_setting(settings, UPDATES_PRERELEASES_SETTING, typed=True)),
        skipped=str(read_setting(settings, UPDATES_SKIPPED_SETTING, typed=True)),
        last_check=parse_time(str(read_setting(settings, UPDATES_LAST_CHECK_SETTING, typed=True))),
        chosen_repository=repository, chosen_mode=mode)


def write(settings: QSettings, *, check_at_start: bool, repository: str, mode: str, prereleases: bool) -> None:
    """Settings › General's rows. "" (the default) removes the key, so the default follows the checkout."""
    settings.setValue(UPDATES_CHECK_AT_START_SETTING, check_at_start)
    for key, value in ((UPDATES_REPOSITORY_SETTING, known_repository(repository)),
                       (UPDATES_MODE_SETTING, mode if mode in MODES else "")):
        if value:
            settings.setValue(key, value)
        else:
            settings.remove(key)
    settings.setValue(UPDATES_PRERELEASES_SETTING, prereleases)


def mode_words(build: BuildInfo, chosen: UpdateSettings) -> str:
    """About's *Updates* line (Q65.3)."""
    pre = " (pre-releases included)" if chosen.prereleases else ""
    if not is_source(build):
        return f"releases of {chosen.repository}{pre} (checked only: download them by hand)"
    if chosen.mode == BRANCH:
        return (f"the branch {build.branch} of {chosen.repository}, fast-forward only, to commits whose CI passed "
                "on macOS, Windows and Ubuntu")
    return f"releases of {chosen.repository}{pre}, tag to tag"
