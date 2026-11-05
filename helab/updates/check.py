"""The update check on HeLab's side (stage 1): ``github.check``'s requests over ``QNetworkAccessManager`` on the
GUI thread's event loop (no thread, no helper; Qt's transfer timeout), with ETags; the once-a-day startup check;
Skip this version; and the status the window, the status-bar mark, the Help menu and About show.

The GUI never waits: each reply arrives as a signal and sends the next request. At startup the status comes from
the cached replies alone (no request), so a lab PC offline still shows what it last knew. A failed startup check
is quiet (logged) and tried again at the next start; a manual one says why.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
import logging
import os
from pathlib import Path
import time
from typing import Any, Protocol

from PyQt6.QtCore import QObject, QTimer, QUrl, pyqtSignal

from helab.build_info import BuildInfo
from helab.updates import github, settings as update_settings
from helab.updates.github import CheckFailed, EtagCache, Fetched, Request
from helab.updates.versions import Facts, Status, status
from helab.utils.settings_defaults import UPDATES_LAST_CHECK_SETTING, UPDATES_SKIPPED_SETTING
from helab.utils.settings_store import app_settings

STARTUP_DELAY_MS = 30_000  # After the window shows: startup is never delayed by the check.
CACHE_FILE = "github-cache.json"

# A reply: (HTTP status, 0 if none; its ETag; its body; its headers; a network error in words, "" if none).
Reply = tuple[int, str, bytes, dict[str, str], str]


class Transport(Protocol):
    def get(self, url: str, headers: dict[str, str], done: Callable[[Reply], None]) -> None:
        """Start a GET of ``url``; ``done`` is called once, later, from the event loop."""


def network_request(url: str, headers: dict[str, str]) -> Any:
    """A ``QNetworkRequest`` for ``url``: Qt's transfer timeout, no cookies, no disk cache, and redirects followed
    only within the same origin (``api.github.com``, as for a renamed repo), so nothing else is ever asked."""
    from PyQt6.QtNetwork import QNetworkRequest
    request = QNetworkRequest(QUrl(url))
    request.setTransferTimeout(github.TIMEOUT_MS)
    request.setAttribute(QNetworkRequest.Attribute.CacheLoadControlAttribute,
                         QNetworkRequest.CacheLoadControl.AlwaysNetwork)
    request.setAttribute(QNetworkRequest.Attribute.CookieLoadControlAttribute, QNetworkRequest.LoadControl.Manual)
    request.setAttribute(QNetworkRequest.Attribute.CookieSaveControlAttribute, QNetworkRequest.LoadControl.Manual)
    request.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,
                         QNetworkRequest.RedirectPolicy.SameOriginRedirectPolicy)
    for key, value in headers.items():
        request.setRawHeader(key.encode(), value.encode())
    return request


class QtTransport:
    """GETs on ``QNetworkAccessManager``: asynchronous, no cookies, no disk cache, Qt's transfer timeout."""

    def __init__(self, parent: QObject) -> None:
        from PyQt6.QtNetwork import QNetworkAccessManager
        self.manager = QNetworkAccessManager(parent)
        self.manager.setCookieJar(None)

    def get(self, url: str, headers: dict[str, str], done: Callable[[Reply], None]) -> None:
        from PyQt6.QtNetwork import QNetworkReply, QNetworkRequest
        if not url.startswith(github.API + "/"):
            raise ValueError(f"Update checks only ask {github.API}")
        if os.environ.get("HELAB_TEST_SOURCE_GUARD"):  # (tests/conftest.py: tests never reach the network.)
            raise RuntimeError("Update checks don't reach the network under tests: give UpdateCheck a transport")
        reply = self.manager.get(network_request(url, headers))
        assert reply is not None

        def finished() -> None:
            code = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
            status_code = code if isinstance(code, int) else 0
            reply_headers = {k.data().decode("latin-1"): v.data().decode("latin-1")
                             for k, v in reply.rawHeaderPairs()}
            error = ""
            if reply.error() != QNetworkReply.NetworkError.NoError and status_code == 0:
                error = reply.errorString() or "no reply"
            body = bytes(reply.readAll().data())
            reply.deleteLater()
            done((status_code, reply_headers.get("ETag", reply_headers.get("etag", "")), body, reply_headers, error))
        reply.finished.connect(finished)


class UpdateCheck(QObject):
    """One per main window. ``changed`` after every status change; ``finished(manual, error)`` when a check
    ends ("" when it succeeded)."""
    changed = pyqtSignal()
    finished = pyqtSignal(bool, str)

    def __init__(self, build: BuildInfo, app_dir: str, parent: QObject | None = None, *,
                 transport: Transport | None = None, now: Callable[[], datetime] | None = None) -> None:
        super().__init__(parent)
        self.build = build
        self.cache = EtagCache(Path(app_dir) / "updates" / CACHE_FILE)
        self.transport: Transport = transport if transport is not None else QtTransport(self)
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.facts: Facts | None = None
        self.error = ""  # The last check's failure ("" if it succeeded or none ran).
        self.checked_at: datetime | None = None  # This session's last successful check.
        self.running = False
        self._manual = False
        self._steps: github.Check | None = None
        self._request: Request | None = None
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._startup_check)
        self.load_cached()

    # -- State ----------------------------------------------------------------------------------------

    def settings(self) -> update_settings.UpdateSettings:
        return update_settings.read(app_settings(), self.build)

    @property
    def status(self) -> Status:
        chosen = self.settings()
        facts = self.facts if self.facts is not None and self.facts.repository == chosen.repository else None
        return status(self.build, facts, chosen.mode, chosen.prereleases, chosen.skipped)

    def _steps_for(self, chosen: update_settings.UpdateSettings) -> github.Check:
        return github.check(chosen.repository, self.build.commit, self.build.version, chosen.mode,
                            self.build.branch, chosen.prereleases)

    def load_cached(self) -> None:
        """The status from the cached replies alone: no request."""
        try:
            self.facts = github.drive(self._steps_for(self.settings()), self.cache.replay)
        except CheckFailed:
            self.facts = None
        self.changed.emit()

    def last_check(self) -> datetime | None:
        return self.checked_at or self.settings().last_check

    def last_check_words(self) -> str:
        """About's *Last check* line."""
        when = self.last_check()
        if self.running:
            return "checking now…"
        if self.error:
            return f"failed: {self.error}"
        if when is None:
            return "never"
        local = when.astimezone()
        return local.strftime("%Y-%m-%d %H:%M")

    # -- Checking -------------------------------------------------------------------------------------

    def schedule_startup(self, delay_ms: int = STARTUP_DELAY_MS) -> None:
        """The startup check, ``delay_ms`` after now, if it is on and due (at most once a day)."""
        self.timer.start(delay_ms)

    def _startup_check(self) -> None:
        if self.settings().due(self.now()):
            self.start(manual=False)

    def start(self, manual: bool) -> bool:
        """Start a check; False if one is running (it then reports as asked by whoever started it)."""
        if self.running:
            self._manual = self._manual or manual
            return False
        self.running, self._manual, self.error = True, manual, ""
        self._steps = self._steps_for(self.settings())
        self.changed.emit()
        self._advance(None)
        return True

    def _advance(self, fetched: Fetched | None) -> None:
        steps = self._steps
        assert steps is not None
        try:
            request = next(steps) if fetched is None else steps.send(fetched)
        except StopIteration as done:
            self._finish(done.value, "")
            return
        except CheckFailed as failed:
            self._finish(None, str(failed))
            return
        self._request = request
        sent = github.headers(self.build.version)
        etag = self.cache.etag(request.url)
        if etag:
            sent["If-None-Match"] = etag
        try:
            self.transport.get(request.url, sent, self._replied)
        except Exception as exc:  # A transport that can't start: the check fails, HeLab goes on.
            logging.exception("Update check: couldn't send %s", request.url)
            self._finish(None, f"Couldn't ask GitHub ({exc}).")

    def _replied(self, reply: Reply) -> None:
        request = self._request
        if request is None or not self.running:
            return
        code, etag, body, reply_headers, network_error = reply
        error = github.failure(code, reply_headers, network_error, time.time())
        fetched = self.cache.answer(request, code, etag, body, error if code != 404 else "")
        self._advance(fetched)

    def _finish(self, facts: Facts | None, error: str) -> None:
        manual = self._manual
        self.running, self._steps, self._request = False, None, None
        self.cache.save()
        if facts is not None:
            self.facts, self.error = facts, ""
            self.checked_at = self.now()
            app_settings().setValue(UPDATES_LAST_CHECK_SETTING, self.checked_at.isoformat(timespec="seconds"))
            logging.info("Update check (%s): %s", facts.repository, self.status.summary())
        else:
            self.error = error
            logging.info("Update check failed%s: %s", "" if manual else " (at start, quietly)", error)
        self.changed.emit()
        self.finished.emit(manual, self.error)

    # -- Skip this version ----------------------------------------------------------------------------

    def skip(self, key: str) -> None:
        app_settings().setValue(UPDATES_SKIPPED_SETTING, key)
        self.changed.emit()

    def unskip(self) -> None:
        app_settings().remove(UPDATES_SKIPPED_SETTING)
        self.changed.emit()

    def settings_changed(self) -> None:
        """Settings › General saved: the status for the (maybe new) repo and mode, from the cache."""
        if not self.running:
            self.load_cached()


def describe(check: UpdateCheck) -> list[tuple[str, str]]:
    """About's lines: (label, text)."""
    chosen = check.settings()
    found: Any = check.status
    return [("Version status", found.summary()),
            ("Updates", update_settings.mode_words(check.build, chosen)),
            ("Last check", check.last_check_words())]
