"""Help › User manual: which page it opens (``helab.utils.user_manual``), and the menu item's
asynchronous site check, against a local server only (never the real network)."""
from __future__ import annotations

import http.server
import json
import threading
from collections.abc import Iterator
from dataclasses import asdict, replace
from pathlib import Path

import pytest
from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QAction, QDesktopServices
from PyQt6.QtWidgets import QMainWindow
from pytestqt.qtbot import QtBot

from helab import build_info
from helab.build_info import BuildInfo, read_build_info
from helab.utils import user_manual
from helab.views.HelabMainWindow import HelabMainWindow

BUILT = BuildInfo(version="0.0.8", commit="a" * 40, branch="main", built_at="2026-11-03T00:00:00+00:00",
                  dirty=False, build_ref="refs/heads/main", repository="TonyXTYan/HeLab")


def test_site_is_the_running_versions_page_on_the_builds_own_repository() -> None:
    assert user_manual.site_url(BUILT) == "https://tonyxtyan.github.io/HeLab/0.0.8/"
    # A build of another copy of the repo opens that copy's site.
    assert user_manual.site_url(replace(BUILT, repository="HeBECANU/HeLab")) == "https://hebecanu.github.io/HeLab/0.0.8/"
    # A source run (no stamp) or a stamp from before the field knows no repository: no site.
    assert user_manual.site_url(BuildInfo()) is None
    assert user_manual.site_url(replace(BUILT, repository="unknown")) is None


def test_fallback_is_the_bundled_copy_else_githubs_page(tmp_path: Path) -> None:
    assert user_manual.targets(BUILT, tmp_path) == user_manual.ManualTargets(
        "https://tonyxtyan.github.io/HeLab/0.0.8/", "https://github.com/TonyXTYan/HeLab/blob/HEAD/docs/index.md")
    index = tmp_path / "manual" / "index.html"
    index.parent.mkdir()
    index.write_text("<html></html>", encoding="utf-8")
    found = user_manual.targets(BuildInfo(), tmp_path)
    assert found.site is None and found.fallback == index.resolve().as_uri()
    assert user_manual.github_page(replace(BUILT, repository="HeBECANU/HeLab")).startswith(
        "https://github.com/HeBECANU/HeLab/")


def test_source_package_has_no_bundled_manual() -> None:
    """The built manual goes only into the app (HeLab.spec), never into the source package."""
    assert user_manual.bundled_index(build_info.PACKAGE_DIR) is None


def test_repository_is_stamped_at_build_time_and_old_stamps_still_read(tmp_path: Path,
                                                                     monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HELAB_BUILD_REPOSITORY", "HeBECANU/HeLab")
    stamp = tmp_path / "stamp.json"
    info = build_info.write_build_info(Path(build_info.PACKAGE_DIR).parent, stamp)
    assert info.repository == "HeBECANU/HeLab" and read_build_info(stamp) == info
    old = {key: value for key, value in asdict(info).items() if key != "repository"}
    stamp.write_text(json.dumps(old), encoding="utf-8")
    assert read_build_info(stamp) == replace(info, repository="unknown")
    stamp.write_text(json.dumps({**old, "repository": "not a repository"}), encoding="utf-8")
    assert read_build_info(stamp) == replace(info, repository="unknown")
    monkeypatch.setenv("HELAB_BUILD_REPOSITORY", "https://example.com/x")
    assert build_info.build_repository(tmp_path) == "unknown"


@pytest.mark.parametrize("remote, expected", [
    ("https://github.com/TonyXTYan/HeLab.git", "TonyXTYan/HeLab"),
    ("https://github.com/TonyXTYan/HeLab/", "TonyXTYan/HeLab"),
    ("git@github.com:HeBECANU/HeLab.git", "HeBECANU/HeLab"),
    ("https://example.com/HeLab.git", None),
])
def test_github_remotes(remote: str, expected: str | None) -> None:
    match = build_info.GITHUB_REMOTE.fullmatch(remote)
    assert (f"{match['owner']}/{match['name']}" if match else None) == expected


class _Server(http.server.BaseHTTPRequestHandler):
    status = 200

    def do_HEAD(self) -> None:
        self.send_response(type(self).status)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        pass


@pytest.fixture
def local_site() -> Iterator[tuple[str, type[_Server]]]:
    handler = type("Handler", (_Server,), {"status": 200})
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/HeLab/0.0.8/", handler
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)


class _Window(HelabMainWindow):
    """The window's Help › User manual alone, without starting HeLab's services."""

    def __init__(self) -> None:
        QMainWindow.__init__(self)


def _opened(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, targets: user_manual.ManualTargets) -> list[str]:
    opened: list[str] = []

    def open_url(url: QUrl) -> bool:
        opened.append(url.toString())
        return True
    monkeypatch.setattr(QDesktopServices, "openUrl", open_url)
    monkeypatch.setattr(user_manual, "targets", lambda info, package_dir=None: targets)
    window = _Window()
    qtbot.addWidget(window)
    window.open_user_manual()
    window.open_user_manual()  # a second click while checking adds no check and opens nothing more
    qtbot.waitUntil(lambda: bool(opened), timeout=10_000)
    qtbot.wait(100)
    assert window._manual_check is None
    return opened


def test_menu_opens_the_site_when_it_answers(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch,
                                             local_site: tuple[str, type[_Server]]) -> None:
    site, _ = local_site
    assert _opened(qtbot, monkeypatch, user_manual.ManualTargets(site, "file:///manual/index.html")) == [site]


def test_menu_falls_back_when_the_site_has_no_page(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch,
                                                   local_site: tuple[str, type[_Server]]) -> None:
    site, handler = local_site
    handler.status = 404  # e.g. a development build's version, never deployed
    found = user_manual.ManualTargets(site, "file:///manual/index.html")
    assert _opened(qtbot, monkeypatch, found) == ["file:///manual/index.html"]


def test_menu_falls_back_when_the_site_cant_be_reached(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    # A port nothing listens on (the discard port): the connection is refused.
    found = user_manual.ManualTargets("http://127.0.0.1:9/HeLab/0.0.8/", "file:///manual/index.html")
    assert _opened(qtbot, monkeypatch, found) == ["file:///manual/index.html"]


def test_menu_opens_the_fallback_at_once_without_a_site(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    found = user_manual.ManualTargets(None, "https://github.com/TonyXTYan/HeLab/blob/HEAD/docs/index.md")
    assert _opened(qtbot, monkeypatch, found) == [found.fallback, found.fallback]


def test_menu_item_has_a_name_and_an_id(qtbot: QtBot) -> None:
    window = HelabMainWindow()
    qtbot.addWidget(window)
    try:
        actions = [action for action in window.findChildren(QAction) if action.objectName() == "help_user_manual"]
        assert [action.text() for action in actions] == ["User manual"]
        assert actions[0].toolTip()
    finally:
        window.close()


def test_a_pre_release_opens_its_own_versions_page() -> None:
    """Q56.3: every release, pre-releases too, is a version of the site named by its version without ``v``
    (docs/publish/site_versions.py), so a pre-release opens its own manual, never ``latest``'s."""
    assert user_manual.site_url(replace(BUILT, version="0.0.8a1")) == "https://tonyxtyan.github.io/HeLab/0.0.8a1/"
