"""HeLab's side of an update or a Restore (stage 2, source only): the updater copied out of the checkout, its
request, the dry run, the detached start and the handshake, the started mark, the last outcome, and tidying.

Nothing here waits: the dry run is a ``QProcess`` (its output read on ``finished``), the start is
``QProcess.startDetached``, and the updater's ``ready-<token>`` file is polled with a ``QTimer``. HeLab quits only
once the updater holds a handle on its process; it never changes a file of the checkout itself.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import json
import logging
import os
from pathlib import Path
import shutil
import sys
import time
from typing import Any

from PyQt6.QtCore import QObject, QProcess, QTimer, pyqtSignal

from helab.build_info import PACKAGE_DIR, BuildInfo
from helab.updates import updater
from helab.updates.versions import RELEASES, Offer, parse_version

TOKEN_ENV = "HELAB_UPDATE_TOKEN"
UPDATER_SOURCE = Path(updater.__file__)
READY_TIMEOUT_S = 15.0
DRY_RUN_TIMEOUT_MS = 180_000  # (It fetches: a slow network.)
TIDY_AGE_S = 3600.0  # Leftover updater copies, requests and marks older than this go at start.
LOGS_KEPT = 20


def updates_dir(app_dir: str) -> Path:
    return Path(app_dir) / "updates"


def checkout() -> Path:
    return PACKAGE_DIR.parent


def venv_prefix() -> str:
    """HeLab's environment (``sys.prefix``): the checkout's venv when it is set up as the README says."""
    return sys.prefix


def base_python(windowed: bool = False) -> str:
    """The Python the venv was made from, outside it (uv's managed one), the windowed one on Windows."""
    base = Path(getattr(sys, "_base_executable", "") or sys.executable)
    if windowed and sys.platform == "win32":
        candidate = base.with_name("pythonw.exe")
        if candidate.is_file():
            return str(candidate)
    return str(base)


def venv_python(windowed: bool = False) -> str:
    """The venv's own Python (HeLab's ``sys.prefix``), for the relaunch: its name survives a venv swap."""
    prefix = Path(venv_prefix())
    if sys.platform == "win32":
        return str(prefix / "Scripts" / ("pythonw.exe" if windowed else "python.exe"))
    return str(prefix / "bin" / "python")


def find_tool(name: str) -> str:
    """``name`` on ``PATH``, then where its installers put it (a HeLab started from a shortcut may have a short
    ``PATH``); "" if nowhere."""
    found = shutil.which(name)
    if found:
        return found
    home = Path.home()
    exe = f"{name}.exe" if sys.platform == "win32" else name
    places = [home / ".local" / "bin" / exe, home / ".cargo" / "bin" / exe]
    if sys.platform == "win32":
        places += [Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Git" / "cmd" / exe,
                   Path(os.environ.get("LOCALAPPDATA", str(home))) / "Programs" / "Git" / "cmd" / exe]
    else:
        places += [Path("/opt/homebrew/bin") / exe, Path("/usr/local/bin") / exe, Path("/usr/bin") / exe]
    for place in places:
        if place.is_file():
            return str(place)
    return ""


@dataclass(frozen=True)
class Asked:
    """What a person asked for: an update to ``offer``, or a Restore (``offer`` None)."""
    offer: Offer | None
    mode: str
    repository: str
    branch: str
    stash: bool = False

    @property
    def action(self) -> str:
        return updater.RESTORE if self.offer is None else updater.UPDATE


def write_request(app_dir: str, asked: Asked, token: str) -> Path:
    """The updater's request file (JSON), beside its copy."""
    offer = asked.offer
    folder = updates_dir(app_dir)
    folder.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = {
        "token": token, "action": asked.action, "checkout": str(checkout()), "venv": venv_prefix(),
        "app_dir": app_dir, "pid": os.getpid(), "mode": asked.mode, "repository": asked.repository,
        "branch": asked.branch, "tag": f"v{offer.release.version}" if offer and offer.release else "",
        "target": offer.commit.sha if offer and offer.commit else "", "stash": asked.stash,
        "git": [find_tool("git") or "git"], "uv": [found] if (found := find_tool("uv")) else [],
        "python": base_python(), "relaunch": [venv_python(windowed=True), "-m", "helab"]}
    if asked.offer is not None and asked.offer.release is not None and asked.mode != RELEASES:
        raise ValueError("a release is updated to in releases mode")
    path = folder / f"request-{token}.json"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def copy_updater(app_dir: str, token: str) -> Path:
    """The updater, copied outside the checkout it changes."""
    folder = updates_dir(app_dir)
    folder.mkdir(parents=True, exist_ok=True)
    copy = folder / f"updater-{token}.py"
    shutil.copyfile(UPDATER_SOURCE, copy)
    return copy


class UpdateLauncher(QObject):
    """``planned(result)`` after a dry run (``updater.check``'s dict, or one with ``refusals`` saying why it
    couldn't run); ``ready()`` once the updater holds HeLab's process (HeLab then quits); ``failed(reason)``."""
    planned = pyqtSignal(dict)
    ready = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(self, build: BuildInfo, app_dir: str, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.build = build
        self.app_dir = app_dir
        self._dry: QProcess | None = None
        self._token = ""
        self._deadline = 0.0
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self._poll_ready)
        # Replaceable in tests: how the updater is started (program, arguments, working folder) → started.
        self.start_detached: Callable[[str, list[str], str], bool] = _start_detached

    @property
    def busy(self) -> bool:
        return self._dry is not None or self.timer.isActive()

    def _command(self, asked: Asked) -> tuple[str, Path, Path, str]:
        token = os.urandom(8).hex()
        return base_python(), copy_updater(self.app_dir, token), write_request(self.app_dir, asked, token), token

    def dry_run(self, asked: Asked) -> bool:
        """The updater's ``--check`` (it fetches the target): ``planned`` when it ends. False while one runs."""
        if self.busy:
            return False
        python, script, request, _ = self._command(asked)
        process = QProcess(self)
        process.setWorkingDirectory(str(updates_dir(self.app_dir)))
        process.finished.connect(self._dry_done)
        self._dry = process
        QTimer.singleShot(DRY_RUN_TIMEOUT_MS, self._dry_timeout)
        process.start(python, [str(script), str(request), "--check"])
        return True

    def _dry_timeout(self) -> None:
        process = self._dry
        if process is not None and process.state() != QProcess.ProcessState.NotRunning:
            process.kill()  # (``finished`` follows.)

    def _dry_done(self) -> None:
        process, self._dry = self._dry, None
        if process is None:
            return
        output = bytes(process.readAllStandardOutput().data()).decode("utf-8", "replace")
        errors = bytes(process.readAllStandardError().data()).decode("utf-8", "replace")
        process.deleteLater()
        result: dict[str, Any] = {}
        for line in reversed(output.splitlines()):
            try:
                found = json.loads(line)
            except ValueError:
                continue
            if isinstance(found, dict):
                result = found
                break
        if not result:
            logging.warning("The updater's check gave no answer: %s", errors.strip()[-500:])
            result = {"ok": False, "refusals": ["HeLab's updater couldn't check this checkout: "
                                                + (errors.strip().splitlines() or ["no answer"])[-1][:300]]}
        self.planned.emit(result)

    def start(self, asked: Asked) -> bool:
        """Start the updater detached; ``ready`` once it holds HeLab's process, else ``failed``."""
        if self.busy:
            return False
        python, script, request, token = self._command(asked)
        windowed = base_python(windowed=True)
        if not self.start_detached(windowed if Path(windowed).is_file() else python, [str(script), str(request)],
                                   str(updates_dir(self.app_dir))):
            self.failed.emit("HeLab couldn't start its updater.")
            return False
        logging.info("Started the updater (%s) for %s", asked.action, asked.offer.label if asked.offer else "Restore")
        self._token, self._deadline = token, time.monotonic() + READY_TIMEOUT_S
        self.timer.start()
        return True

    def _poll_ready(self) -> None:
        if (updates_dir(self.app_dir) / f"ready-{self._token}").exists():
            self.timer.stop()
            self.ready.emit()
        elif time.monotonic() > self._deadline:
            self.timer.stop()
            self.failed.emit("The updater didn't start, so HeLab stays as it is. Its log is in the app folder's "
                             "updates folder.")


def _start_detached(program: str, arguments: list[str], folder: str) -> bool:
    started, _ = QProcess.startDetached(program, arguments, folder)
    return bool(started)


# -- At start ---------------------------------------------------------------------------------------------

def mark_started(app_dir: str) -> str:
    """Started by the updater (``HELAB_UPDATE_TOKEN``): tell it this version runs, once the window has shown
    (``main``); the token, or "" when not started by an updater (or the mark couldn't be written). The token goes
    from the environment, so helpers and the next updater don't inherit it."""
    token = os.environ.pop(TOKEN_ENV, "")
    if not token or not token.isalnum():
        return ""
    try:
        folder = updates_dir(app_dir)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"started-{token}").write_text(str(os.getpid()), encoding="utf-8")
    except OSError:
        logging.exception("Couldn't tell the updater HeLab started")
        return ""
    return token


def take_last_outcome(app_dir: str, token: str = "") -> dict[str, Any]:
    """The last update's outcome, once: {} when there is none, it was shown already, or (``token`` given) it is
    another run's than the updater that started this HeLab."""
    path = updates_dir(app_dir) / "last.json"
    found = updater.read_json(path)
    if not found or found.get("shown") or (token and found.get("token") != token):
        return {}
    try:
        updater.write_json(path, dict(found, shown=True))
    except OSError:
        return {}
    return found


def restored_key(found: dict[str, Any]) -> str:
    """What a Restore left, as Skip this version stores it (the version in releases mode, else the commit), so
    the startup reminder doesn't offer it straight back (design §7); "" when it isn't a restore."""
    if found.get("outcome") != "restored":
        return ""
    version = parse_version(str(found.get("tag", ""))) if found.get("mode") == RELEASES else None
    return str(version) if version is not None else str(found.get("from", ""))


def outcome_words(found: dict[str, Any]) -> tuple[bool, str]:
    """(fine, text) for the last outcome: a status notice when fine, else a message."""
    outcome = str(found.get("outcome", ""))
    to, before = str(found.get("to", ""))[:6].upper(), str(found.get("from", ""))[:6].upper()
    stash = str(found.get("stash", ""))
    kept = f' Your changes were stashed as "{stash}" (git stash list).' if stash else ""
    if outcome == "updated":
        return True, f"HeLab was updated to {to}.{kept}"
    if outcome == "restored":
        return True, f"HeLab's previous version ({to}) was restored."
    if outcome == "unconfirmed":
        return True, f"HeLab was updated to {to}."
    reason = str(found.get("reason", "")) or "no reason was recorded"
    log = str(found.get("log", ""))
    verb = {"refused": "HeLab wasn't updated", "rolled back": "The update was rolled back",
            "failed": "The update didn't finish"}.get(outcome, "The update didn't finish")
    return False, f"{verb}: {reason}{' (HeLab is still ' + before + ')' if before else ''}.{kept}" + (
        f"\n\nIts log: {log}" if log else "")


def previous_kept(app_dir: str) -> dict[str, Any]:
    """``previous.json`` when it is this checkout's: what Restore previous version goes back to."""
    found = updater.read_json(updates_dir(app_dir) / "previous.json")
    if not found or os.path.normcase(str(found.get("checkout", ""))) != os.path.normcase(str(checkout())):
        return {}
    return found


def tidy(app_dir: str, now: float | None = None) -> list[str]:
    """Housekeeping at start: the updater's own copies, requests and marks over an hour old (a program can't
    delete itself on Windows), and update logs beyond the newest ``LOGS_KEPT``. Nothing else."""
    folder = updates_dir(app_dir)
    if not folder.is_dir():
        return []
    now = time.time() if now is None else now
    removed = []
    for pattern in ("updater-*.py", "request-*.json", "ready-*", "started-*"):
        for path in folder.glob(pattern):
            try:
                if path.is_file() and not path.is_symlink() and now - path.stat().st_mtime > TIDY_AGE_S:
                    path.unlink()
                    removed.append(path.name)
            except OSError:
                pass
    logs = sorted(folder.glob("update-*.log"), key=lambda path: path.stat().st_mtime, reverse=True)
    for path in logs[LOGS_KEPT:]:
        try:
            path.unlink()
            removed.append(path.name)
        except OSError:
            pass
    return removed
