"""HeLab's side of an update (``helab.updates.launch``) and its place in the window: the request, the dry run as
a real ``QProcess`` against a temporary repo (``test_updates_updater``'s ``Lab``: never this checkout), the ready
handshake, the started mark, the last outcome shown once, tidying, Update and restart's two clicks, and Restore.
The updater is never started for real against anything here."""
from __future__ import annotations

from collections.abc import Iterator
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from typing import Any
from unittest.mock import patch

import pytest
from PyQt6 import QtWebEngineWidgets  # noqa: F401  (before any QApplication: the main window)
from PyQt6.QtWidgets import QMessageBox
from pytestqt.qtbot import QtBot

from helab.build_info import BuildInfo
from helab.updates import launch, updater
from helab.updates.check import UpdateCheck
from helab.updates.dialog import UpdateWindow
from helab.updates.versions import BRANCH, RELEASES, Commit, Offer, Release
from test_updates_check import FakeGitHub, RELEASE_BUILD, replies
from test_updates_updater import Lab

OFFER = Offer(RELEASES, "0.0.9", "0.0.9", release=Release("v0.0.9", "0.0.9", False), commit=Commit("d" * 40))


def test_the_request_names_the_checkout_its_venv_this_process_and_the_relaunch(tmp_path: Path) -> None:
    asked = launch.Asked(OFFER, RELEASES, "HeBECANU/HeLab", "detached")
    path = launch.write_request(str(tmp_path), asked, "0123456789abcdef")
    data = json.loads(path.read_text())
    assert data["checkout"] == str(launch.checkout()) and data["venv"] == sys.prefix and data["pid"] == os.getpid()
    assert (data["action"], data["tag"], data["target"], data["mode"]) == ("update", "v0.0.9", "d" * 40, RELEASES)
    assert data["relaunch"][1:] == ["-m", "helab"] and Path(data["relaunch"][0]).parent.parent == Path(sys.prefix)
    copy = launch.copy_updater(str(tmp_path), "0123456789abcdef")
    assert copy.read_bytes() == Path(updater.__file__).read_bytes() and copy.parent == tmp_path / "updates"
    job = updater.read_job(path)
    assert job.pid == os.getpid() and job.checkout == launch.checkout()


def test_a_restore_request_has_no_target(tmp_path: Path) -> None:
    data = json.loads(launch.write_request(str(tmp_path), launch.Asked(None, BRANCH, "TonyXTYan/HeLab", "dev"),
                                           "0123456789abcdef").read_text())
    assert (data["action"], data["tag"], data["target"]) == ("restore", "", "")


@pytest.fixture
def lab(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Lab]:
    """A temporary checkout as HeLab's own, and the environment its updater runs with."""
    import shutil
    if shutil.which("git") is None:
        pytest.skip("git isn't installed")
    made = Lab(tmp_path)
    for key, value in made.env.items():
        if key.startswith(("GIT_", "HELAB_UPDATER_")):
            monkeypatch.setenv(key, value)
    for key in ("SSH_CONNECTION", "SSH_CLIENT", "SSH_TTY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(launch, "checkout", lambda: made.checkout)
    monkeypatch.setattr(launch, "venv_prefix", lambda: str(made.venv))
    yield made


def test_the_dry_run_runs_the_updater_copy_in_a_qprocess_and_never_waits(qtbot: QtBot, lab: Lab) -> None:
    target = lab.publish("0.0.2")
    launcher = launch.UpdateLauncher(RELEASE_BUILD, str(lab.app_dir))
    offer = Offer(BRANCH, target, "main +1", commit=Commit(target))
    with qtbot.waitSignal(launcher.planned, timeout=60_000) as planned:
        assert launcher.dry_run(launch.Asked(offer, BRANCH, "HeBECANU/HeLab", "main"))
        assert launcher.busy and not launcher.dry_run(launch.Asked(offer, BRANCH, "HeBECANU/HeLab", "main"))
    assert planned.args is not None
    result: dict[str, Any] = planned.args[0]
    assert result["ok"], result
    assert result["target"] == target and lab.head() != target  # (The dry run changes nothing.)


def test_the_dry_run_of_this_checkout_is_refused_by_the_test_guard(qtbot: QtBot, tmp_path: Path,
                                                                   monkeypatch: pytest.MonkeyPatch) -> None:
    """Belt and braces: a test that forgot to point HeLab at a temporary checkout gets a refusal, no fetch."""
    monkeypatch.delenv("HELAB_UPDATER_TEST_ROOT", raising=False)
    monkeypatch.setenv("GIT_ALLOW_PROTOCOL", "file")
    launcher = launch.UpdateLauncher(RELEASE_BUILD, str(tmp_path))
    with qtbot.waitSignal(launcher.planned, timeout=60_000) as planned:
        launcher.dry_run(launch.Asked(OFFER, RELEASES, "HeBECANU/HeLab", "detached"))
    assert planned.args is not None
    assert planned.args[0]["refusals"] == ["Under tests, the updater needs HELAB_UPDATER_TEST_ROOT."]


def test_ready_from_the_updater_lets_helab_quit_and_none_in_time_says_so(qtbot: QtBot, tmp_path: Path,
                                                                         monkeypatch: pytest.MonkeyPatch) -> None:
    launcher = launch.UpdateLauncher(RELEASE_BUILD, str(tmp_path))
    started: list[list[str]] = []

    def answering(program: str, arguments: list[str], folder: str) -> bool:
        started.append([program, *arguments])
        token = json.loads(Path(arguments[1]).read_text())["token"]
        (Path(folder) / f"ready-{token}").write_text("{}")
        return True
    launcher.start_detached = answering
    with qtbot.waitSignal(launcher.ready, timeout=5000):
        assert launcher.start(launch.Asked(OFFER, RELEASES, "HeBECANU/HeLab", "detached"))
    assert started and started[0][1].endswith(".py") and Path(started[0][1]).parent == tmp_path / "updates"
    monkeypatch.setattr(launch, "READY_TIMEOUT_S", 0.3)
    launcher.start_detached = lambda program, arguments, folder: True
    with qtbot.waitSignal(launcher.failed, timeout=5000) as failed:
        launcher.start(launch.Asked(OFFER, RELEASES, "HeBECANU/HeLab", "detached"))
    assert failed.args is not None and "didn't start" in failed.args[0]
    launcher.start_detached = lambda program, arguments, folder: False
    with qtbot.waitSignal(launcher.failed, timeout=5000):
        assert not launcher.start(launch.Asked(OFFER, RELEASES, "HeBECANU/HeLab", "detached"))


def test_the_started_mark_is_written_only_with_the_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(launch.TOKEN_ENV, raising=False)
    assert not launch.mark_started(str(tmp_path))
    monkeypatch.setenv(launch.TOKEN_ENV, "0123abcd0123abcd")
    assert launch.mark_started(str(tmp_path)) == "0123abcd0123abcd"
    assert (tmp_path / "updates" / "started-0123abcd0123abcd").read_text() == str(os.getpid())
    assert launch.TOKEN_ENV not in os.environ  # (Helpers and the next updater don't inherit it.)
    monkeypatch.setenv(launch.TOKEN_ENV, "../evil")
    assert not launch.mark_started(str(tmp_path))


def test_the_last_outcome_is_shown_once(tmp_path: Path) -> None:
    updater.write_json(tmp_path / "updates" / "last.json", {"outcome": "rolled back", "reason": "It crashed.",
                                                             "from": "a" * 40, "to": "b" * 40, "log": "/x.log"})
    found = launch.take_last_outcome(str(tmp_path))
    fine, text = launch.outcome_words(found)
    assert not fine and "rolled back: It crashed." in text and "AAAAAA" in text and "/x.log" in text
    assert launch.take_last_outcome(str(tmp_path)) == {}
    assert launch.outcome_words({"outcome": "updated", "to": "b" * 40, "stash": "HeLab update a → b"}) == (
        True, 'HeLab was updated to BBBBBB. Your changes were stashed as "HeLab update a → b" (git stash list).')


def test_tidying_removes_only_the_updaters_old_leftovers(tmp_path: Path) -> None:
    folder = tmp_path / "updates"
    folder.mkdir()
    old = time.time() - 2 * launch.TIDY_AGE_S
    for name in ("updater-1.py", "request-1.json", "ready-1", "started-1", "updater-2.py", "last.json",
                 "previous.json", "github-cache.json"):
        (folder / name).write_text("")
    for name in ("updater-1.py", "request-1.json", "ready-1", "started-1", "last.json", "previous.json"):
        os.utime(folder / name, (old, old))
    for index in range(launch.LOGS_KEPT + 3):
        log = folder / f"update-{index:03}.log"
        log.write_text("")
        os.utime(log, (old + index, old + index))
    removed = launch.tidy(str(tmp_path))
    assert sorted(removed) == sorted(["updater-1.py", "request-1.json", "ready-1", "started-1",
                                      "update-000.log", "update-001.log", "update-002.log"])
    assert {"updater-2.py", "last.json", "previous.json", "github-cache.json"} <= {p.name for p in folder.iterdir()}


# -- The window's two clicks ---------------------------------------------------------------------------

def test_update_and_restart_runs_the_dry_run_first_then_quit_and_update(qtbot: QtBot, tmp_path: Path) -> None:
    check = UpdateCheck(RELEASE_BUILD, str(tmp_path), None, transport=FakeGitHub(replies()))
    with qtbot.waitSignal(check.finished, timeout=5000):
        check.start(manual=True)
    calls: list[tuple[str, bool, bool]] = []
    window = UpdateWindow(check, update=lambda offer, stash, confirmed: calls.append((offer.key, stash, confirmed)))
    qtbot.addWidget(window)
    window.show()
    window.update_button.click()
    assert calls == [("0.0.9", False, False)] and not window.update_button.isEnabled()
    window.plan_ready({"ok": False, "refusals": ["This checkout has changes (a.py): commit or stash them first."],
                       "stashable": True})
    assert "Can't update" in window.plan_label.text() and window.stash_box.isVisible()
    assert not window.update_button.isEnabled()
    window.stash_box.setChecked(True)  # (A new choice: the dry run again.)
    assert window.update_button.isEnabled() and window.update_button.text() == "Update and restart…"
    window.update_button.click()
    assert calls[-1] == ("0.0.9", True, False)
    window.plan_ready({"ok": True, "refusals": [], "steps": ["Fetch from HeBECANU/HeLab and check out v0.0.9"]},
                      "Live is on in 1 tab: it stops.")
    assert window.update_button.text() == "Quit and update" and "Live is on in 1 tab" in window.plan_label.text()
    window.update_button.click()
    assert calls[-1] == ("0.0.9", True, True)


# -- The main window --------------------------------------------------------------------------------------

@pytest.fixture
def window(qtbot: QtBot) -> Iterator[Any]:
    from helab.views.HelabMainWindow import HelabMainWindow
    main = HelabMainWindow()
    qtbot.addWidget(main)
    yield main
    main.close()


def test_the_last_outcome_shows_at_start(window: Any, qtbot: QtBot) -> None:
    from helab.utils.constants import app_folder
    updater.write_json(Path(app_folder()) / "updates" / "last.json", {"outcome": "updated", "to": "c" * 40})
    window.show_last_update()
    assert window._status_notice is not None and "updated to CCCCCC" in window._status_notice[0]
    updater.write_json(Path(app_folder()) / "updates" / "last.json", {"outcome": "failed", "reason": "No uv."})
    with patch.object(QMessageBox, "warning") as warning:
        window.show_last_update()
        qtbot.waitUntil(lambda: warning.called, timeout=2000)
    assert "No uv." in warning.call_args.args[2]


def test_a_helab_the_updater_started_shows_that_updates_outcome_on_this_start(
        window: Any, qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``main``'s order, with the updater's own wait and record: the window after its start writes the mark; the
    updater, seeing it, records "updated"; the notice shows on this start (not at the next one)."""
    from helab.utils.constants import app_folder
    app = Path(app_folder())
    updater.write_json(app / "updates" / "last.json", {"token": "0" * 16, "outcome": "updated", "to": "e" * 40,
                                                       "shown": True})  # (The run before, shown then.)
    token = "1234abcd1234abcd"
    monkeypatch.setenv(launch.TOKEN_ENV, token)
    job = updater.Job(token=token, action=updater.UPDATE, checkout=tmp_path, venv=tmp_path, app_dir=app, pid=0,
                      mode=BRANCH, repository="HeBECANU/HeLab", branch="main", tag="", target="", stash=False,
                      git=["git"], uv=[], python=sys.executable, relaunch=[], timeouts=dict(updater.TIMEOUTS, started=30))
    log = updater.Log(tmp_path / "update.log")
    new_helab = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])

    def the_updater() -> None:
        state = updater.wait_started(job, new_helab, token)
        updater.record(job, "updated" if state == "started" else state, "", "a" * 40, "f" * 40, log)

    thread = threading.Thread(target=the_updater)
    thread.start()
    try:
        window.after_start()
        qtbot.waitUntil(lambda: window._status_notice is not None
                        and "updated to FFFFFF" in window._status_notice[0], timeout=15000)
        assert updater.read_json(app / "updates" / "last.json")["shown"] is True  # (Once.)
    finally:
        new_helab.kill()
        new_helab.wait()
        thread.join(40)


def test_a_restore_skips_what_it_left_so_it_isnt_offered_straight_back(window: Any) -> None:
    from helab.utils.constants import app_folder
    from helab.utils.settings_defaults import UPDATES_SKIPPED_SETTING
    from helab.utils.settings_store import app_settings
    last = Path(app_folder()) / "updates" / "last.json"
    updater.write_json(last, {"outcome": "restored", "action": "restore", "mode": BRANCH, "tag": "",
                              "from": "b" * 40, "to": "a" * 40})
    window.show_last_update()
    assert app_settings().value(UPDATES_SKIPPED_SETTING) == "b" * 40
    updater.write_json(last, {"outcome": "restored", "action": "restore", "mode": RELEASES, "tag": "v0.0.9",
                              "from": "c" * 40, "to": "a" * 40})
    window.show_last_update()
    assert app_settings().value(UPDATES_SKIPPED_SETTING) == "0.0.9"
    assert launch.restored_key({"outcome": "updated", "from": "c" * 40}) == ""


def test_restore_is_offered_only_with_this_checkouts_previous_version(window: Any) -> None:
    from helab.utils.constants import app_folder
    from helab.updates import settings as update_settings
    window._update_restore_action()
    assert not window.action_restore_previous.isEnabled()
    updater.write_json(Path(app_folder()) / "updates" / "previous.json",
                       {"checkout": str(launch.checkout()), "from": "a" * 40, "to": "b" * 40, "mode": BRANCH})
    window._update_restore_action()
    assert window.action_restore_previous.isEnabled() is update_settings.is_source(window.update_check.build)
    updater.write_json(Path(app_folder()) / "updates" / "previous.json", {"checkout": "/elsewhere"})
    window._update_restore_action()
    assert not window.action_restore_previous.isEnabled()


def test_ready_quits_through_the_normal_path(window: Any) -> None:
    with patch.object(type(window), "close") as close:
        window.update_launcher.ready.emit()
    close.assert_called_once()


def test_the_quit_note_names_live(window: Any) -> None:
    assert "Live" not in window._quit_note()
    explorers = window._explorers()
    if explorers:
        # (Put back before the fixture closes the window: closing stops Live, which a stand-in can't.)
        explorer = explorers[0][1]
        before = explorer.live
        explorer.live = object()
        try:
            assert "Live is on in 1 tab" in window._quit_note()
        finally:
            explorer.live = before


def test_a_frozen_build_never_offers_update_and_restart(qtbot: QtBot, tmp_path: Path) -> None:
    frozen = BuildInfo(version="0.0.8", commit="b" * 40, built_at="2026-11-01T00:00:00+00:00", dirty=False)
    from helab.updates import settings as update_settings
    assert not update_settings.is_source(frozen)
