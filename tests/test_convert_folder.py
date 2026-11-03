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


def test_a_conversion_of_another_profile_is_never_joined(qtbot: QtBot, service: IOService, tmp_path: Path,
                                                         local: None) -> None:
    """TP-5: one conversion per folder; one of another profile isn't joined (it would report the other's
    results): Convert this folder… says so, FolderCache refuses it, and Live's tick waits."""
    from helab.convert.profile import MATLAB_2019
    explorer, path, _ = raw_folder(qtbot, tmp_path)
    cache, converter = explorer.model.cache, explorer.converter
    assert cache.converting_with(path) == ""
    assert cache.convert("other-tab", path, profile_used=MATLAB_2023_LAB_EDIT)
    assert cache.converting_with(path) == "matlab-2023-lab-edit"
    assert not cache.convert("live", path, profile_used=MATLAB_2019)  # (Not joined.)
    assert cache.convert("third", path, profile_used=MATLAB_2023_LAB_EDIT)  # (The same profile joins.)
    assert "with matlab-2023-lab-edit is running" in converter.convert_unavailable(path)
    assert converter.ask_convert(path) is None
    explorer.close_cleanup()


def test_lives_tick_waits_while_another_profiles_conversion_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    """TP-5: Live's Auto-convert never joins Convert this folder… of another profile: its tick waits."""
    from types import SimpleNamespace
    from helab.convert.profile import MATLAB_2019
    from helab.views import explorer_live
    asked: list[str] = []

    def convert(*args: Any, **kwargs: Any) -> bool:
        asked.append("convert")
        return True
    cache = SimpleNamespace(live_interval=0.0, auto_convert_profile=lambda path: MATLAB_2019,
                            converting_with=lambda path, profile=None: "matlab-2023-lab-edit",
                            write_beside=lambda path: False, convert=convert)
    monkeypatch.setattr(explorer_convert, "instead_of_beside", lambda path: None)
    control: Any = SimpleNamespace(explorer=SimpleNamespace(model=SimpleNamespace(cache=cache), live_owner="live"),
                                   box=None)
    session: Any = SimpleNamespace(path="/data/run", convert=explorer_live.AutoConvert(started_at=0.0))
    explorer_live.LiveController._convert_tick(control, session)
    assert asked == [] and not session.convert.request and not session.convert.error
    cache.converting_with = lambda path, profile=None: ""  # (Its own profile's: joins, as before.)
    explorer_live.LiveController._convert_tick(control, session)
    assert asked == ["convert"] and session.convert.request


def test_convert_this_folder_never_refuses_silently(qtbot: QtBot, service: IOService, tmp_path: Path, local: None,
                                                    monkeypatch: pytest.MonkeyPatch) -> None:
    """TP-9: while another converter question is open the item says why (disabled); beside no longer available
    when the dialog is answered: a message says so."""
    from PyQt6.QtWidgets import QMessageBox
    explorer, path, _ = raw_folder(qtbot, tmp_path)
    converter = explorer.converter
    monkeypatch.setattr(explorer_convert, "beside_unavailable", lambda cache, folder: "")
    dialog = converter.ask_convert(path)
    monkeypatch.setattr(explorer_convert, "beside_unavailable", lambda cache, folder: "the disk cache is off")
    answer(dialog, M23, "beside")
    box = converter.box
    assert isinstance(box, QMessageBox) and "the disk cache is off" in box.informativeText()
    assert path not in converter.conversions
    assert "question is open" in converter.convert_unavailable(path) and converter.ask_convert(path) is None
    box.close()
    assert converter.box is None and converter.convert_unavailable(path) == ""
    explorer.close_cleanup()


def test_lives_tick_waits_for_an_edited_profile_of_the_same_name(qtbot: QtBot, service: IOService, tmp_path: Path,
                                                                 local: None) -> None:
    """TP-11: a running conversion with a profile of the same name but other content (edited meanwhile) isn't
    Live's to join: Live's tick waits instead of stopping Auto-convert with "couldn't be queued"."""
    from types import SimpleNamespace
    from helab.convert.profile import MATLAB_2019
    from helab.views import explorer_live
    explorer, path, _ = raw_folder(qtbot, tmp_path)
    cache = explorer.model.cache
    edited = MATLAB_2019.replace(search_depth=40)  # (Same name, other content.)
    assert edited.name == MATLAB_2019.name and edited.to_dict() != MATLAB_2019.to_dict()
    assert cache.convert("details", path, profile_used=MATLAB_2019)
    setattr(cache, "auto_convert_profile", lambda folder: edited)  # (Live converts with the edited one.)
    control: Any = SimpleNamespace(explorer=SimpleNamespace(model=SimpleNamespace(cache=cache), live_owner="live"),
                                   box=None)
    session: Any = SimpleNamespace(path=path, convert=explorer_live.AutoConvert(started_at=0.0))
    explorer_live.LiveController._convert_tick(control, session)
    assert not session.convert.error and not session.convert.request  # (Waits: the next tick converts.)
    assert cache.converting_with(path, edited) == "matlab-2019" and cache.converting_with(path, MATLAB_2019) == ""
    explorer.close_cleanup()
