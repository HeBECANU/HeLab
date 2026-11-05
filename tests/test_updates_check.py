"""The update check on HeLab's side (``helab.updates.check``, ``settings``, ``settings_rows``, ``dialog``) and its
place in the main window: a fake transport stands in for GitHub (no network), replies arrive later from the event
loop as Qt's would, and the GUI never waits."""
from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from PyQt6 import QtWebEngineWidgets  # noqa: F401  (before any QApplication: the main window)
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QFormLayout, QMessageBox, QWidget
from pytestqt.qtbot import QtBot

from helab import build_info
from helab.build_info import BuildInfo
from helab.updates import check as update_check, github, settings as update_settings
from helab.updates.check import Reply, UpdateCheck
from helab.updates.dialog import UpdateWindow
from helab.updates.settings_rows import UpdateSettingsRows
from helab.updates.versions import BRANCH, RELEASES
from helab.utils.settings_defaults import (
    UPDATES_LAST_CHECK_SETTING, UPDATES_MODE_SETTING, UPDATES_REPOSITORY_SETTING, UPDATES_SKIPPED_SETTING)
from helab.utils.settings_store import app_settings
from test_updates_github import C_NEW, C_OLD, C_REL, compare, ref, release, runs

REPO = github.DEFAULT_REPOSITORY  # (HeBECANU/HeLab: the default for a build that names no repo.)
RELEASE_BUILD = BuildInfo(version="0.0.8", commit=C_REL, branch="detached", dirty=False)


class FakeGitHub:
    """Replies by path, sent from the event loop (never inside ``get``); records what was sent."""

    def __init__(self, replies: dict[str, Any]) -> None:
        self.replies = replies
        self.sent: list[tuple[str, dict[str, str]]] = []
        self.etags: dict[str, str] = {}

    def get(self, url: str, headers: dict[str, str], done: Callable[[Reply], None]) -> None:
        assert url.startswith("https://api.github.com/")
        self.sent.append((url, dict(headers)))
        path = url.removeprefix(github.API)
        reply: Reply = (404, "", b"", {}, "")
        for known, answer in self.replies.items():
            if path == known or path.startswith(known + "?"):
                if isinstance(answer, tuple):
                    reply = answer
                else:
                    etag = f'W/"{abs(hash(path))}"'
                    reply = ((304, etag, b"", {}, "") if headers.get("If-None-Match") == etag
                             else (200, etag, json.dumps(answer).encode(), {"ETag": etag}, ""))
        QTimer.singleShot(0, lambda: done(reply))


def replies(repo: str = REPO, **extra: Any) -> dict[str, Any]:
    found: dict[str, Any] = {
        f"/repos/{repo}/releases": [release("v0.0.9", notes="New things"), release("v0.0.8")],
        f"/repos/{repo}/git/matching-refs/tags/v": [ref("v0.0.9", C_NEW), ref("v0.0.8", C_REL)],
        f"/repos/{repo}/compare/{C_NEW}...main": compare("identical", []),
    }
    found.update(extra)
    return found


def made(qtbot: QtBot, tmp_path: Path, build: BuildInfo, fake: FakeGitHub,
         now: Callable[[], datetime] | None = None) -> UpdateCheck:
    return UpdateCheck(build, str(tmp_path), None, transport=fake, now=now)


def test_a_manual_check_finds_the_newer_release_and_reuses_etags_next_time(qtbot: QtBot, tmp_path: Path) -> None:
    fake = FakeGitHub(replies())
    check = made(qtbot, tmp_path, RELEASE_BUILD, fake)
    assert check.status.offer is None  # (Nothing cached yet.)
    with qtbot.waitSignal(check.finished, timeout=5000) as finished:
        assert check.start(manual=True)
        assert check.running  # (Returned at once: the replies come later.)
    assert finished.args == [True, ""]
    found = check.status
    assert found.text == "Release 0.0.8" and found.offer is not None and found.offer.label == "0.0.9"
    assert all(headers["User-Agent"].startswith("HeLab/") for _, headers in fake.sent)
    assert not any("If-None-Match" in headers for _, headers in fake.sent)
    assert app_settings().value(UPDATES_LAST_CHECK_SETTING)
    fake.sent.clear()
    with qtbot.waitSignal(check.finished, timeout=5000):
        check.start(manual=True)
    assert fake.sent and all("If-None-Match" in headers for _, headers in fake.sent)
    assert check.status.offer is not None and check.status.offer.label == "0.0.9"


def test_the_status_at_start_comes_from_the_cache_without_a_request(qtbot: QtBot, tmp_path: Path) -> None:
    first = made(qtbot, tmp_path, RELEASE_BUILD, FakeGitHub(replies()))
    with qtbot.waitSignal(first.finished, timeout=5000):
        first.start(manual=True)
    offline = FakeGitHub({})
    again = made(qtbot, tmp_path, RELEASE_BUILD, offline)
    assert again.status.offer is not None and again.status.offer.label == "0.0.9"
    assert offline.sent == []


def test_one_check_at_a_time(qtbot: QtBot, tmp_path: Path) -> None:
    check = made(qtbot, tmp_path, RELEASE_BUILD, FakeGitHub(replies()))
    with qtbot.waitSignal(check.finished, timeout=5000):
        assert check.start(manual=False)
        assert not check.start(manual=True)


def test_a_failed_startup_check_is_quiet_and_a_manual_one_says_why(qtbot: QtBot, tmp_path: Path) -> None:
    offline: dict[str, Any] = {f"/repos/{REPO}/releases": (0, "", b"", {}, "Host api.github.com not found")}
    check = made(qtbot, tmp_path, RELEASE_BUILD, FakeGitHub(offline))
    with qtbot.waitSignal(check.finished, timeout=5000) as finished:
        check.start(manual=False)
    assert finished.args is not None
    assert finished.args[0] is False and "Couldn't reach GitHub" in finished.args[1]
    assert not app_settings().value(UPDATES_LAST_CHECK_SETTING)  # (Tried again at the next start.)
    window = UpdateWindow(check)
    qtbot.addWidget(window)
    assert "reach GitHub" in window.status_label.text()


def test_the_rate_limit_is_explained(qtbot: QtBot, tmp_path: Path) -> None:
    limited = {f"/repos/{REPO}/releases": (403, "", b"{}", {"X-RateLimit-Remaining": "0",
                                                           "X-RateLimit-Reset": "9999999999"}, "")}
    check = made(qtbot, tmp_path, RELEASE_BUILD, FakeGitHub(limited))
    with qtbot.waitSignal(check.finished, timeout=5000) as finished:
        check.start(manual=True)
    assert finished.args is not None and "60 requests an hour" in finished.args[1]


@pytest.mark.parametrize("ago, runs_check", [(None, True), (timedelta(hours=25), True), (timedelta(hours=2), False),
                                             (timedelta(hours=-3), True)])
def test_the_startup_check_runs_at_most_once_a_day(qtbot: QtBot, tmp_path: Path, ago: timedelta | None,
                                                   runs_check: bool) -> None:
    now = datetime(2026, 11, 5, 12, tzinfo=timezone.utc)
    if ago is not None:
        app_settings().setValue(UPDATES_LAST_CHECK_SETTING, (now - ago).isoformat())
    fake = FakeGitHub(replies())
    check = made(qtbot, tmp_path, RELEASE_BUILD, fake, now=lambda: now)
    check.schedule_startup(0)
    qtbot.wait(100)
    qtbot.waitUntil(lambda: not check.running, timeout=5000)
    assert bool(fake.sent) is runs_check


def test_the_startup_switch_turns_the_startup_check_off(qtbot: QtBot, tmp_path: Path) -> None:
    app_settings().setValue("updates_check_at_start", False)
    fake = FakeGitHub(replies())
    check = made(qtbot, tmp_path, RELEASE_BUILD, fake)
    check.schedule_startup(0)
    qtbot.wait(100)
    assert fake.sent == []


def test_skip_this_version_in_the_window(qtbot: QtBot, tmp_path: Path) -> None:
    check = made(qtbot, tmp_path, RELEASE_BUILD, FakeGitHub(replies()))
    with qtbot.waitSignal(check.finished, timeout=5000):
        check.start(manual=True)
    window = UpdateWindow(check)
    qtbot.addWidget(window)
    window.show()
    assert window.skip_button.isVisible() and window.update_button.isVisible()  # (A source checkout.)
    assert "New things" in window.details.toPlainText()
    window.skip_button.click()
    assert app_settings().value(UPDATES_SKIPPED_SETTING) == "0.0.9"
    assert check.status.skipped and not check.status.available and window.skip_button.text() == "Don't skip"
    window.skip_button.click()
    assert check.status.available


def test_a_compiled_build_downloads_and_a_source_checkout_updates(qtbot: QtBot, tmp_path: Path) -> None:
    frozen = BuildInfo(version="0.0.8", commit=C_REL, branch="main", dirty=False, built_at="2026-11-01T00:00:00+00:00")
    check = made(qtbot, tmp_path, frozen, FakeGitHub(replies()))
    with qtbot.waitSignal(check.finished, timeout=5000):
        check.start(manual=True)
    window = UpdateWindow(check)
    qtbot.addWidget(window)
    window.show()
    assert window.download_button.isVisible() and window.update_button.isHidden()
    source = made(qtbot, tmp_path, RELEASE_BUILD, FakeGitHub(replies()))
    with qtbot.waitSignal(source.finished, timeout=5000):
        source.start(manual=True)
    asked: list[str] = []
    window = UpdateWindow(source, update=lambda offer, stash, confirmed: asked.append(offer.key))
    qtbot.addWidget(window)
    window.show()
    assert window.update_button.isVisible() and window.download_button.isHidden()
    window.update_button.click()
    assert asked == ["0.0.9"]


def test_branch_mode_offers_the_newest_green_commit(qtbot: QtBot, tmp_path: Path,
                                                    monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(build_info, "upstream_repository", lambda root, branch: "TonyXTYan/HeLab")
    update_settings._upstream.cache_clear()
    build = BuildInfo(version="0.0.8a1", commit=C_OLD, branch="dev/v0.0.9", dirty=False)
    green, red = "2" * 40, "3" * 40
    fake = FakeGitHub(replies("TonyXTYan/HeLab", **{
        f"/repos/TonyXTYan/HeLab/compare/{C_OLD}...dev/v0.0.9": compare("ahead", [green, red]),
        f"/repos/TonyXTYan/HeLab/commits/{red}/check-runs": runs({"macos Build": "cancelled"}),
        f"/repos/TonyXTYan/HeLab/commits/{green}/check-runs": runs()}))
    check = made(qtbot, tmp_path, build, fake)
    chosen = check.settings()
    assert (chosen.repository, chosen.mode) == ("TonyXTYan/HeLab", BRANCH)
    with qtbot.waitSignal(check.finished, timeout=5000):
        check.start(manual=True)
    offer = check.status.offer
    assert offer is not None and offer.commit is not None and offer.commit.sha == green
    window = UpdateWindow(check)
    qtbot.addWidget(window)
    assert "red" in window.details.toPlainText() and "Commit 2" in window.details.toPlainText()
    update_settings._upstream.cache_clear()


def test_the_transport_never_reaches_the_network_under_tests(qtbot: QtBot) -> None:
    host = QWidget()
    qtbot.addWidget(host)
    transport = update_check.QtTransport(host)
    with pytest.raises(RuntimeError, match="network"):
        transport.get(github.API + "/repos/HeBECANU/HeLab/releases", {}, lambda reply: None)
    with pytest.raises(ValueError):
        transport.get("https://example.com/", {}, lambda reply: None)


def test_a_request_follows_redirects_only_within_api_github_com() -> None:
    from PyQt6.QtNetwork import QNetworkRequest
    request = update_check.network_request(github.API + "/repos/HeBECANU/HeLab/releases", {"User-Agent": "HeLab/x"})
    assert request.attribute(QNetworkRequest.Attribute.RedirectPolicyAttribute) == \
        QNetworkRequest.RedirectPolicy.SameOriginRedirectPolicy
    assert request.transferTimeout() == github.TIMEOUT_MS and request.rawHeader(b"User-Agent").data() == b"HeLab/x"


# -- Settings ------------------------------------------------------------------------------------------

def test_the_default_mode_follows_what_the_checkout_is_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(build_info, "upstream_repository", lambda root, branch: "unknown")
    update_settings._upstream.cache_clear()
    settings = app_settings()
    on_branch = BuildInfo(commit=C_OLD, branch="dev/v0.0.9")
    assert update_settings.read(settings, on_branch).mode == BRANCH
    assert update_settings.read(settings, BuildInfo(commit=C_OLD, branch="detached")).mode == RELEASES
    frozen = BuildInfo(commit=C_OLD, branch="main", built_at="2026-11-01T00:00:00+00:00")
    assert update_settings.read(settings, frozen).mode == RELEASES
    settings.setValue(UPDATES_MODE_SETTING, "releases")
    assert update_settings.read(settings, on_branch).mode == RELEASES
    settings.setValue(UPDATES_MODE_SETTING, "branch")
    assert update_settings.read(settings, frozen).mode == RELEASES  # (A compiled build only checks releases.)
    update_settings._upstream.cache_clear()


def test_only_a_known_repository_is_used(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(build_info, "upstream_repository", lambda root, branch: "tonyxtyan/helab")
    update_settings._upstream.cache_clear()
    settings = app_settings()
    on_branch = BuildInfo(commit=C_OLD, branch="dev/v0.0.9")
    assert update_settings.read(settings, on_branch).repository == "TonyXTYan/HeLab"  # (Q~1: its upstream's.)
    settings.setValue(UPDATES_REPOSITORY_SETTING, "someone/HeLab")
    assert update_settings.read(settings, on_branch).repository == "TonyXTYan/HeLab"
    settings.setValue(UPDATES_REPOSITORY_SETTING, "HeBECANU/HeLab")
    assert update_settings.read(settings, on_branch).repository == "HeBECANU/HeLab"
    stamped = BuildInfo(commit=C_OLD, built_at="2026-11-01T00:00:00+00:00", repository="TonyXTYan/HeLab")
    settings.remove(UPDATES_REPOSITORY_SETTING)
    assert update_settings.read(settings, stamped).repository == "TonyXTYan/HeLab"
    assert update_settings.read(settings, BuildInfo(commit=C_OLD, branch="detached")).repository == "HeBECANU/HeLab"
    update_settings._upstream.cache_clear()


def test_the_upstream_repository_comes_from_the_raw_remote_url(tmp_path: Path) -> None:
    import subprocess
    repo = tmp_path / "checkout"
    repo.mkdir()
    env_git = ["git", "-C", str(repo), "-c", "init.defaultBranch=main"]
    subprocess.run([*env_git, "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(repo), "remote", "add", "lab", "https://github.com/HeBECANU/HeLab.git"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "branch.main.remote", "lab"], check=True)
    assert build_info.upstream_repository(repo, "main") == "HeBECANU/HeLab"
    assert build_info.upstream_repository(repo, "other") == "unknown"
    assert build_info.upstream_repository(repo, "detached") == "unknown"


def test_settings_rows_save_and_load(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(build_info, "upstream_repository", lambda root, branch: "unknown")
    update_settings._upstream.cache_clear()
    host = QWidget()
    qtbot.addWidget(host)
    form = QFormLayout(host)
    build = BuildInfo(commit=C_OLD, branch="dev/v0.0.9")
    rows = UpdateSettingsRows(build, form, host)
    settings = app_settings()
    rows.load(settings)
    assert rows.check_at_start.isChecked() and not rows.prereleases.isChecked()
    assert rows.mode.currentData() == BRANCH and rows.mode.isEnabled()
    rows.mode.setCurrentIndex(rows.mode.findData(RELEASES))
    rows.repository.setCurrentIndex(rows.repository.findData("TonyXTYan/HeLab"))
    rows.prereleases.setChecked(True)
    rows.check_at_start.setChecked(False)
    rows.save(settings)
    chosen = update_settings.read(settings, build)
    assert (chosen.mode, chosen.repository, chosen.prereleases, chosen.check_at_start) == (
        RELEASES, "TonyXTYan/HeLab", True, False)
    rows.mode.setCurrentIndex(rows.mode.findData(BRANCH))
    rows.save(settings)
    assert settings.value(UPDATES_MODE_SETTING) is None  # (The default keeps following the checkout.)
    frozen = UpdateSettingsRows(BuildInfo(commit=C_OLD, built_at="2026-11-01T00:00:00+00:00"), form, host)
    assert not frozen.mode.isEnabled() and frozen.mode.count() == 1


# -- The main window ---------------------------------------------------------------------------------

@pytest.fixture
def window(qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    """The main window, its check on a release build of the default repo (never this checkout's own git)."""
    from helab.views.HelabMainWindow import HelabMainWindow
    monkeypatch.setattr(build_info, "upstream_repository", lambda root, branch: "unknown")
    update_settings._upstream.cache_clear()
    main = HelabMainWindow()
    qtbot.addWidget(main)
    monkeypatch.setattr(main.update_check, "build", RELEASE_BUILD)
    main.update_check.transport = FakeGitHub(replies(main.update_check.settings().repository))
    yield main
    main.close()
    update_settings._upstream.cache_clear()


def test_the_status_bar_mark_and_help_entry_show_an_available_update(qtbot: QtBot, window: Any,
                                                                     monkeypatch: pytest.MonkeyPatch) -> None:
    check = window.update_check
    assert check.settings().repository == REPO
    assert window.update_button.isHidden() and not window.action_update_available.isVisible()
    help_menu = next(item.menu() for item in window.menu_bar.actions() if item.text() == "Help")
    assert "Check for Updates…" in [a.text() for a in help_menu.actions()]
    with qtbot.waitSignal(check.finished, timeout=5000):
        window.check_for_updates()
    assert window.update_window is not None and window.update_window.isVisible()
    assert not window.update_button.isHidden() and window.update_button.text() == "⬆ 0.0.9"
    assert window.action_update_available.isVisible()
    assert window.action_update_available.text() == "HeLab 0.0.9 is available…"
    assert window.update_button.objectName() == "update_available" and window.update_button.accessibleName()
    check.skip("0.0.9")
    assert window.update_button.isHidden() and not window.action_update_available.isVisible()


def test_about_shows_the_status_the_mode_and_the_last_check(window: Any) -> None:
    from helab.utils.constants import APP_BUILD_INFO
    with patch.object(QMessageBox, "about") as about:
        window.show_about_dialog()
    text = about.call_args.args[2]
    assert text.startswith(APP_BUILD_INFO.description())
    assert "Version status: " in text and "Updates: " in text and "Last check: never" in text
