"""Q~3 (Tony, 2026-11-10; GT-8): the two boxes startup shows while it waits, "Another HeLab is moving the
cache…" and "Finishing an interrupted cache move…", have a Quit (they had no button and no limit). Quit ends
HeLab; the other HeLab's move goes on, or the interrupted move is finished at the next start. A box closed because
the wait ended is not a Quit."""
from __future__ import annotations

from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, Callable

import pytest
from PyQt6 import QtWebEngineWidgets  # noqa: F401  (before any QApplication: helab.main)
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QMessageBox
from pytestqt.qtbot import QtBot

from test_one_running import entry  # noqa: F401  (a fixture)


def shown_box() -> QMessageBox:
    [box] = [widget for widget in QApplication.topLevelWidgets()
             if isinstance(widget, QMessageBox) and widget.isVisible()]
    return box


def quit_button(box: QMessageBox) -> Any:
    [button] = box.buttons()
    assert button.text() == "Quit" and button.objectName() == "startup_wait_rejectrole"
    return button


def test_a_box_closed_by_its_wait_ending_is_no_quit(entry: ModuleType, qtbot: QtBot) -> None:  # noqa: F811
    quitting: list[bool] = []
    box = entry.startup_box("Waiting…", "Quit ends HeLab.", quitting)
    box.show()
    box.blockSignals(True)
    box.close()
    assert not quitting
    box = entry.startup_box("Waiting…", "Quit ends HeLab.", quitting)
    box.show()
    quit_button(box).click()
    assert quitting == [True] and box.informativeText() == "Quit ends HeLab."


def test_quit_while_another_helab_moves_the_cache_ends_this_one(
        entry: ModuleType, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    from helab.utils import cache_locks

    def startup(app_dir: str, recover: Callable[[str], str], wait: Callable[[], None]) -> Any:
        wait()  # (The box shows.)
        box = shown_box()
        assert box.text() == "Another HeLab is moving the cache…"
        quit_button(box).click()
        while True:
            wait()  # (Quit: the next wait ends HeLab, holding nothing.)
    monkeypatch.setattr(cache_locks, "startup", startup)
    with pytest.raises(SystemExit) as ended:
        entry._start_cache()
    assert ended.value.code == 0


def test_quit_while_an_interrupted_move_is_finished_leaves_it_for_the_next_start(
        entry: ModuleType, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:  # noqa: F811
    from helab.utils import cache_move, io_service
    cancelled: list[str] = []
    service = SimpleNamespace(resultReady=SimpleNamespace(connect=lambda slot: None, disconnect=lambda slot: None),
                              submit=lambda *args, **kwargs: True, cancel=cancelled.append)
    monkeypatch.setattr(cache_move, "read_record", lambda app_dir: {"step": "copied"})
    monkeypatch.setattr(io_service, "get_io_service", lambda: service)
    QTimer.singleShot(50, lambda: quit_button(shown_box()).click())
    settings = SimpleNamespace(fileName=lambda: str(tmp_path / "settings.ini"), format=lambda: None)
    monkeypatch.setattr("helab.utils.cache_setting.settings_spec", lambda settings: {})
    with pytest.raises(SystemExit):
        entry._recover_in_helper(settings, "token")
    assert cancelled == ["startup-recovery"]
