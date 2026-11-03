"""Convert this folder… (Q~4, Tony 2026-11-03): right-click and File › Convert This Folder… pick any profile
and a destination (HeLab's cache, its temp folder, beside the raw files); the conversion runs as Folder
details' do (``ExplorerConverter``), with that profile, the folder only; beside on a share asks first. Temp
folders only; helpers run in-process as in ``test_explorer_convert``."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pytestqt.qtbot import QtBot

from helab.convert.profile import MATLAB_2023_LAB_EDIT, file_tag
from helab.utils import cache_location
from helab.utils.io_service import IOService
from helab.views import explorer_convert
from test_explorer_convert import (beside_flag, fresh_confirmations, on_a_share, one_worker,  # noqa: F401
                                   raw_folder, recording)
from test_live import job_of, producer, service  # noqa: F401
from test_live_convert import run_convert

M23 = file_tag(MATLAB_2023_LAB_EDIT)


def answer(dialog: explorer_convert.ConvertFolderDialog | None, tag: str, where: str) -> None:
    assert dialog is not None
    dialog.profile_combo.setCurrentIndex(dialog.profile_combo.findData(tag))
    dialog.radios[where].setChecked(True)
    dialog.accept()


@pytest.fixture
def local(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cache_location, "share_of", lambda path, mounts=None, *, resolve=False: "")


def test_convert_this_folder_with_another_profile_to_temp(qtbot: QtBot, service: IOService, tmp_path: Path,
                                                          local: None) -> None:
    explorer, path, _ = raw_folder(qtbot, tmp_path)
    cache, converter = explorer.model.cache, explorer.converter
    dialog = converter.ask_convert(path)
    assert dialog is not None and dialog.profile_combo.currentData() == file_tag(cache.convert_profile())
    assert dialog.profile_combo.findData(M23) >= 0 and dialog.radios["cache"].isChecked()
    answer(dialog, M23, "temp")
    for expected_pass in (1, 2):
        qtbot.waitUntil(lambda: ("convert", path) in cache.jobs)
        request = producer(cache, path, "convert")
        assert request.payload["profile"]["name"] == "matlab-2023-lab-edit"
        assert request.payload["destination"] == "temp" and request.payload["beside"] is False
        run_convert(cache, path)
        assert converter.conversions[path].passes == expected_pass
    conversion = converter.conversions[path]
    assert conversion.finished and conversion.converted == 2 and conversion.output == "temp"
    assert not list(Path(path).glob("d_txy_helab_*"))  # (Nothing beside the raw files.)
    row = converter.row(path)
    assert row is not None and f"with {M23}" in row[1]
    explorer.close_cleanup()


def test_cancel_converts_nothing_and_live_auto_convert_blocks_it(qtbot: QtBot, service: IOService, tmp_path: Path,
                                                                 local: None, monkeypatch: pytest.MonkeyPatch) -> None:
    explorer, path, _ = raw_folder(qtbot, tmp_path)
    converter = explorer.converter
    dialog = converter.ask_convert(path)
    assert dialog is not None
    dialog.reject()
    assert path not in converter.conversions and ("convert", path) not in explorer.model.cache.jobs
    monkeypatch.setattr(explorer.live_control, "auto_converting", lambda folder=None: True)
    assert "Auto-convert" in converter.convert_unavailable(path) and converter.ask_convert(path) is None
    explorer.close_cleanup()


def test_beside_on_a_share_asks_first_then_converts_beside(qtbot: QtBot, service: IOService, tmp_path: Path,
                                                           on_a_share: list[str],
                                                           monkeypatch: pytest.MonkeyPatch) -> None:
    explorer, path, _ = raw_folder(qtbot, tmp_path)
    cache, converter = explorer.model.cache, explorer.converter
    monkeypatch.setattr(explorer_convert, "beside_unavailable", lambda cache, folder: "")
    answers = [False, True]
    monkeypatch.setattr(explorer_convert, "confirm_beside_on_share", lambda parent, folder, share: answers.pop(0))
    saved: list[tuple[str, bool]] = []
    monkeypatch.setattr(cache, "set_write_beside", recording(saved))
    answer(converter.ask_convert(path), M23, "beside")
    assert saved == [] and path not in converter.conversions  # Declined: nothing.
    answer(converter.ask_convert(path), M23, "beside")
    assert saved == [(path, True)]  # (The folder's beside setting, as Folder details' offer turns it on.)
    beside_flag(explorer, path)
    qtbot.waitUntil(lambda: ("convert", path) in cache.jobs)
    request = producer(cache, path, "convert")
    assert request.payload["beside"] is True and request.payload["profile"]["name"] == "matlab-2023-lab-edit"
    converter.close()
    explorer.close_cleanup()


def test_beside_isnt_offered_where_the_folders_setting_cant_be_saved(qtbot: QtBot, service: IOService,
                                                                     tmp_path: Path, local: None) -> None:
    explorer, path, _ = raw_folder(qtbot, tmp_path)
    dialog = explorer.converter.ask_convert(path)
    assert dialog is not None
    why = explorer_convert.beside_unavailable(explorer.model.cache, path)
    assert dialog.radios["beside"].isEnabled() is (not why)
    dialog.reject()
    explorer.close_cleanup()


def test_the_menu_bar_item_converts_the_tabs_selected_folder(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace
    from helab.views.HelabMainWindow import HelabMainWindow
    asked: list[str] = []

    def ask_convert(path: str) -> object:
        asked.append(path)
        return object()
    converter = SimpleNamespace(convert_unavailable=lambda path: "", ask_convert=ask_convert)
    explorer = SimpleNamespace(converter=converter)
    window: Any = SimpleNamespace(_place_root_target=lambda: (explorer, "/data/run"))
    assert HelabMainWindow.convert_folder_in_current_tab(window) and asked == ["/data/run"]
    converter.convert_unavailable = lambda path: "busy"
    assert not HelabMainWindow.convert_folder_in_current_tab(window) and asked == ["/data/run"]
