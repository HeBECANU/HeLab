"""Converting on a share and after a refused beside write (A39.5, Q38.1): the one-time warnings, Folder
details' offer and its conversion, and the Retry / cache / temp choice, in the app (``explorer_convert``,
``explorer_live``). No real share: ``cache_location.share_of`` is patched for the test's folder, and the
helpers run in-process as in ``test_live_convert``."""
from __future__ import annotations

from pathlib import Path
import time
from typing import Any, Iterator

import pytest
from PyQt6.QtWidgets import QMessageBox, QPushButton
from pytestqt.qtbot import QtBot

from helab.io_ops import convert
from helab.utils import cache_location
from helab.utils.io_service import IOService
from helab.views import explorer_convert
from helab.views.FolderDetailsPanel import FolderDetailsPanel
from helab.views.FolderExplorer import FolderExplorer
from test_convert_helab import raw_bytes
from helab.io_ops.loading import load
from test_live import age_folder, deliver, job_of, producer, replay, service  # noqa: F401
from test_live_convert import check, cycle, line, run_convert, watching_raw_folder, write_raw

SHARE = "//labserver/data"


@pytest.fixture(autouse=True)
def one_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(convert, "DEFAULT_WORKERS", 1)


@pytest.fixture(autouse=True)
def fresh_confirmations() -> Iterator[None]:
    explorer_convert.beside_confirmed.clear()
    explorer_convert.instead.clear()
    yield
    explorer_convert.beside_confirmed.clear()
    explorer_convert.instead.clear()


@pytest.fixture
def on_a_share(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> list[str]:
    """Folders under ``tmp_path`` are on SHARE; the paths asked about (all lexical: never resolved)."""
    asked: list[str] = []

    def share_of(path: str, mounts: Any = None, *, resolve: bool = False) -> str:
        assert not resolve, "the GUI resolved a source path"
        asked.append(path)
        return SHARE if path.startswith(str(tmp_path)) else ""
    monkeypatch.setattr(cache_location, "share_of", share_of)
    return asked


def click(box: QMessageBox | None, ident: str) -> None:
    assert box is not None and box.isVisible()
    button = box.findChild(QPushButton, ident)
    assert button is not None, [child.objectName() for child in box.findChildren(QPushButton)]
    button.click()


def recording(saved: list[tuple[str, bool]]) -> Any:
    """``FolderCache.set_write_beside`` noting each choice instead of asking a helper."""
    def set_write_beside(folder: str, on: bool) -> str:
        saved.append((folder, on))
        return "owner"  # (Its job's owner: queued.)
    return set_write_beside


def beside_flag(explorer: FolderExplorer, path: str) -> None:
    """The folder's beside flag as the store would answer it (memory: the helper isn't asked here)."""
    explorer.model.cache._remember_convert_prefs(path, {"write_beside": True, "set_at": time.time()})


# Live's auto-convert on a share (A39.5).

def test_auto_convert_beside_on_a_share_asks_once_and_cache_instead_writes_nothing_there(
        qtbot: QtBot, service: IOService, tmp_path: Path, on_a_share: list[str]) -> None:
    explorer, path = watching_raw_folder(qtbot, tmp_path)
    cache, control = explorer.model.cache, explorer.live_control
    session = explorer.live
    assert session is not None and session.convert is not None
    cycle(qtbot, explorer, path, tmp_path)  # (The first conversion: the flag not known yet.)
    beside_flag(explorer, path)
    write_raw(Path(path), 1, raw_bytes(10_000))
    qtbot.waitUntil(lambda: control.box is not None)
    assert ("convert", path) not in cache.jobs  # Nothing converts while asked.
    box = control.box
    assert box is not None and SHARE in box.text() and "acquisition PC" in box.text()
    assert {button.objectName() for button in box.findChildren(QPushButton)} == {
        "live_share_beside", "live_share_cache", "live_share_off"}
    assert box.defaultButton() is box.findChild(QPushButton, "live_share_cache")
    session.convert.ended_at = -1e9  # (An answer within a check interval of the last conversion waits a tick.)
    click(box, "live_share_cache")
    qtbot.waitUntil(lambda: ("convert", path) in cache.jobs)
    payload = producer(cache, path, "convert").payload
    assert payload["destination"] == "cache" and payload["beside"] is False
    sent = run_convert(cache, path)
    assert [event["output"] for event in sent if event["kind"] == "convert_plan"] == ["cache"]
    assert not (Path(path) / "d_txy_helab_m19v1_1.txt").exists()
    assert "instead of beside the raw files" in line(explorer)[1]
    explorer.stop_live(save=False)
    explorer.close_cleanup()


@pytest.mark.parametrize("choice", ["beside", "off"])
def test_auto_convert_beside_on_a_share_once_confirmed_or_turned_off(
        qtbot: QtBot, service: IOService, tmp_path: Path, on_a_share: list[str], choice: str) -> None:
    explorer, path = watching_raw_folder(qtbot, tmp_path)
    cache, control = explorer.model.cache, explorer.live_control
    cycle(qtbot, explorer, path, tmp_path)
    beside_flag(explorer, path)
    qtbot.waitUntil(lambda: control.box is not None)
    session = explorer.live
    assert session is not None and session.convert is not None
    session.convert.ended_at = -1e9  # (An answer within a check interval of the last conversion waits a tick.)
    click(control.box, f"live_share_{choice}")
    if choice == "off":
        assert explorer.live is not None and explorer.live.convert is None and path not in cache.auto_convert
        assert explorer_convert.beside_confirmed == set()
    else:
        qtbot.waitUntil(lambda: ("convert", path) in cache.jobs)
        payload = producer(cache, path, "convert").payload
        assert payload["beside"] is True and payload["destination"] == "cache"  # (Beside, the flag on.)
        assert explorer_convert.share_to_confirm(path) == ""  # Not asked again this session.
        run_convert(cache, path)
        check(cache, path, tmp_path)
        assert control.box is None
    explorer.stop_live(save=False)
    explorer.close_cleanup()


def test_turning_beside_on_for_a_share_folder_shows_the_share_warning(
        qtbot: QtBot, service: IOService, tmp_path: Path, on_a_share: list[str], monkeypatch: pytest.MonkeyPatch) -> None:
    explorer, path = watching_raw_folder(qtbot, tmp_path)
    cache = explorer.model.cache
    saved: list[tuple[str, bool]] = []
    monkeypatch.setattr(cache, "set_write_beside", recording(saved))
    shown: list[QMessageBox] = []

    def answering(clicked: str) -> Any:
        def exec_(box: QMessageBox) -> int:
            shown.append(box)
            assert SHARE in box.text() and "Saved for this folder" in box.informativeText()
            assert {button.objectName() for button in box.findChildren(QPushButton)} >= {
                "share_beside_confirm_beside", "share_beside_confirm_cancel"}
            button = box.findChild(QPushButton, clicked)
            assert button is not None
            button.click()
            return 0
        return exec_
    monkeypatch.setattr(QMessageBox, "exec", answering("share_beside_confirm_cancel"))
    explorer.live_control._set_write_beside(path, True)
    assert saved == [] and len(shown) == 1
    monkeypatch.setattr(QMessageBox, "exec", answering("share_beside_confirm_beside"))
    explorer.live_control._set_write_beside(path, True)
    assert saved == [(path, True)] and explorer_convert.share_to_confirm(path) == ""
    explorer.live_control._set_write_beside(path, False)  # (Off asks nothing.)
    assert saved[-1] == (path, False) and len(shown) == 2
    explorer.stop_live(save=False)
    explorer.close_cleanup()


# Q38.1 in Live.

@pytest.mark.parametrize("choice, destination", [("retry", None), ("cache", "cache"), ("temp", "temp"),
                                                 ("later", None)])
def test_a_refused_beside_write_in_live_asks_retry_or_hellabs_folders(
        qtbot: QtBot, service: IOService, tmp_path: Path, choice: str, destination: str | None) -> None:
    explorer, path = watching_raw_folder(qtbot, tmp_path)
    cache, control = explorer.model.cache, explorer.live_control
    session = explorer.live
    assert session is not None and session.convert is not None
    request, _ = cycle(qtbot, explorer, path, tmp_path)
    beside_flag(explorer, path)  # (A local folder: no share question.)
    convert_state = session.convert
    convert_state.request = True
    message = "Not written: this folder's file system can't add a file without risking replacing one already there"
    control._convert_event(session, {"kind": "beside_refused", "path": path, "shot": 1, "txy": path + "/d_txy_helab_m19v1_1.txt",
                                     "message": message})
    control._convert_event(session, {"kind": "error", "message": f"[Errno 45] {message}"})
    assert convert_state.error and convert_state.refused == message
    box = control.box
    assert box is not None and "never risks replacing" in box.informativeText()
    assert {button.objectName() for button in box.findChildren(QPushButton)} == {
        "beside_refused_retry", "beside_refused_cache", "beside_refused_temp", "beside_refused_later"}
    convert_state.ended_at = -1e9
    click(box, f"beside_refused_{choice}")
    if choice == "later":
        assert convert_state.error and ("convert", path) not in cache.jobs
        assert "turn the folder's beside setting off" in line(explorer)[1]
    else:
        assert not convert_state.error and not convert_state.refused
        assert explorer_convert.instead_of_beside(path) == destination
        qtbot.waitUntil(lambda: ("convert", path) in cache.jobs)
        payload = producer(cache, path, "convert").payload
        assert payload["destination"] == (destination or "cache")
        assert payload["beside"] is (destination is None)  # Retry: beside again; else HeLab's folder.
    explorer.stop_live(save=False)
    explorer.close_cleanup()


# Folder details' offer (A39.5).

def raw_folder(qtbot: QtBot, tmp_path: Path, shots: int = 2) -> tuple[FolderExplorer, str, FolderDetailsPanel]:
    """A tab showing a folder of raw files only (listed, not loaded) and a Folder details panel on it."""
    folder = tmp_path / "raw-only"
    folder.mkdir()
    for shot in range(1, shots + 1):
        write_raw(folder, shot, raw_bytes(10_000, 50_000 * shot))
    age_folder(folder, 120)
    path = str(folder)
    explorer = FolderExplorer(path, path, path, [0, 4, 5])
    qtbot.addWidget(explorer)
    cache = explorer.model.cache
    cache.live_interval = 0.02
    qtbot.waitUntil(lambda: ("list", path) in cache.jobs)
    replay(cache, path, tmp_path, "list")
    qtbot.waitUntil(lambda: explorer.model.nodes[path].report is not None)
    assert explorer.model.nodes[path].raw_count == shots and not explorer.model.nodes[path].txy_count
    panel = FolderDetailsPanel()
    qtbot.addWidget(panel)
    panel.show_explorer(explorer, None)
    return explorer, path, panel


def load_as_the_helper_does(cache: Any, path: str, tmp_path: Path) -> list[dict[str, Any]]:
    """The queued load run with the fields ``io_helper`` passes that ``test_live.replay`` leaves out (HeLab's
    TXY: ``txy``), its events delivered."""
    request = producer(cache, path)
    payload = request.payload
    output = tmp_path / f"artifacts-{time.monotonic_ns()}"
    output.mkdir()
    sent: list[Any] = []
    try:
        load(path, str(output), sent.append, payload.get("cache"), payload.get("memory"),
             payload.get("base_signature", ""), payload.get("signature", ""), limits=payload.get("limits"),
             no_cache=bool(payload.get("no_cache")), check_level=str(payload.get("check_level") or "medium"),
             txy=payload.get("txy"), memory_origins=payload.get("memory_origins"))
        sent.append({"kind": "done"})
    except Exception as exc:
        sent.append({"kind": "error", "message": str(exc)})
    cache.service.pending.remove(request)
    return deliver(cache, request, sent)


def test_a_local_raw_only_folder_has_no_offer(qtbot: QtBot, service: IOService, tmp_path: Path,
                                              monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cache_location, "share_of", lambda path, mounts=None, *, resolve=False: "")
    explorer, path, panel = raw_folder(qtbot, tmp_path)
    assert panel.text("offer") == "" and explorer.converter.row(path) is None
    explorer.close_cleanup()


@pytest.mark.parametrize("choice", ["cache", "temp"])
def test_a_share_folder_without_txy_offers_hellabs_folders_and_converts_there(
        qtbot: QtBot, service: IOService, tmp_path: Path, on_a_share: list[str], choice: str) -> None:
    explorer, path, panel = raw_folder(qtbot, tmp_path)
    cache, converter = explorer.model.cache, explorer.converter
    assert panel.text("offer") == "No TXY · on a share · Convert…"
    assert "acquisition PC" in panel.values["offer"].toolTip()
    converter.clicked(path)
    box = converter.box
    assert box is not None and SHARE in box.text() and "acquisition PC" in box.informativeText()
    assert {button.objectName() for button in box.findChildren(QPushButton)} == {
        "convert_offer_cache", "convert_offer_temp", "convert_offer_beside", "convert_offer_cancel"}
    assert box.defaultButton() is box.findChild(QPushButton, "convert_offer_cache")
    click(box, f"convert_offer_{choice}")
    assert converter.box is None
    for expected_pass in (1, 2):
        qtbot.waitUntil(lambda: ("convert", path) in cache.jobs)
        request = producer(cache, path, "convert")
        job = job_of(cache, path, "convert")
        assert job is not None and converter.owner in {asker.owner for asker in job.subscribers.values()}
        assert request.payload["destination"] == choice
        assert request.payload["beside"] is False
        run_convert(cache, path)
        assert converter.conversions[path].passes == expected_pass
    conversion = converter.conversions[path]
    assert conversion.finished and conversion.converted == 2 and conversion.output == choice
    assert not list(Path(path).glob("d_txy_helab_*"))  # Nothing written to the share.
    panel.show_explorer(explorer, None)
    assert panel.text("offer") == f"2 converted to {explorer_convert.WHERE[choice]}"
    qtbot.waitUntil(lambda: ("list", path) in cache.jobs)  # Listed and loaded again: HeLab's TXY show.
    replay(cache, path, tmp_path, "list")
    qtbot.waitUntil(lambda: job_of(cache, path) is not None)
    load_as_the_helper_does(cache, path, tmp_path)
    qtbot.waitUntil(lambda: explorer.displayed_dataset is not None and explorer.displayed_dataset.path == path)
    shown = explorer.displayed_dataset
    assert shown is not None and sorted(shown.data) == [1, 2]
    panel.show_explorer(explorer, None)
    assert panel.text("offer") == f"2 converted to {explorer_convert.WHERE[choice]}"  # (Its result, not the offer.)
    explorer.close_cleanup()


def test_converting_beside_on_the_share_asks_first_and_sets_the_folders_flag(
        qtbot: QtBot, service: IOService, tmp_path: Path, on_a_share: list[str], monkeypatch: pytest.MonkeyPatch) -> None:
    explorer, path, panel = raw_folder(qtbot, tmp_path)
    cache, converter = explorer.model.cache, explorer.converter
    answers = [False, True]
    monkeypatch.setattr(explorer_convert, "confirm_beside_on_share",
                        lambda parent, folder, share: answers.pop(0))
    saved: list[tuple[str, bool]] = []
    monkeypatch.setattr(cache, "set_write_beside", recording(saved))
    converter.clicked(path)
    click(converter.box, "convert_offer_beside")
    assert saved == [] and path not in converter.conversions  # Declined: nothing.
    converter.clicked(path)
    click(converter.box, "convert_offer_beside")
    assert saved == [(path, True)]
    beside_flag(explorer, path)  # (The store's answer.)
    qtbot.waitUntil(lambda: ("convert", path) in cache.jobs)
    assert producer(cache, path, "convert").payload["beside"] is True
    converter.close()
    explorer.close_cleanup()


@pytest.mark.parametrize("choice, destination", [("temp", "temp"), ("retry", "beside")])
def test_a_refused_beside_write_from_folder_details_asks_too(
        qtbot: QtBot, service: IOService, tmp_path: Path, on_a_share: list[str], choice: str, destination: str) -> None:
    explorer, path, panel = raw_folder(qtbot, tmp_path)
    cache, converter = explorer.model.cache, explorer.converter
    beside_flag(explorer, path)
    assert converter.start(path, "beside")
    request = producer(cache, path, "convert")
    cache.service.pending.remove(request)
    message = "Not written: this folder's file system can't add a file without risking replacing one already there"
    for event in ({"kind": "beside_refused", "path": path, "shot": 1, "txy": "x", "message": message},
                  {"kind": "error", "message": message}):
        cache.service.resultReady.emit(request, event)
    conversion = converter.conversions[path]
    assert conversion.error and conversion.refused == message
    panel.show_explorer(explorer, None)
    assert panel.text("offer").startswith("Conversion stopped:")
    assert "Click to choose" in panel.values["offer"].toolTip()
    click(converter.box, f"beside_refused_{choice}")
    qtbot.waitUntil(lambda: ("convert", path) in cache.jobs)
    assert converter.conversions[path].destination == destination and not converter.conversions[path].error
    payload = producer(cache, path, "convert").payload
    # (Retry: beside again, asked explicitly; temp is never beside, and is now the folder's for the session.)
    assert payload["beside"] is (destination == "beside")
    assert payload["destination"] == ("temp" if destination == "temp" else "cache")
    assert explorer_convert.instead_of_beside(path) == (None if destination == "beside" else "temp")
    converter.close()
    explorer.close_cleanup()


# Strata's review (2026-11-03).

def test_the_offers_beside_is_gated_like_the_live_menu(
        qtbot: QtBot, service: IOService, tmp_path: Path, on_a_share: list[str], monkeypatch: pytest.MonkeyPatch) -> None:
    """Finding 1: without a confirmed .helab-root (or the disk cache), beside can't be saved for the folder:
    the offer's beside button is disabled with the reason, and choosing it starts nothing."""
    explorer, path, panel = raw_folder(qtbot, tmp_path)
    cache, converter = explorer.model.cache, explorer.converter
    monkeypatch.setattr(cache, "no_root", lambda folder: "no .helab-root found here or above")
    asked: list[str] = []

    def confirm(parent: Any, folder: str, share: str) -> bool:
        asked.append(folder)
        return True
    monkeypatch.setattr(explorer_convert, "confirm_beside_on_share", confirm)
    assert explorer_convert.beside_unavailable(cache, path).startswith("no .helab-root")
    converter.clicked(path)
    box = converter.box
    assert box is not None
    beside = box.findChild(QPushButton, "convert_offer_beside")
    assert beside is not None and not beside.isEnabled() and "no .helab-root" in box.informativeText()
    converter._offer_answered(path, "beside")
    assert asked == [] and path not in converter.conversions and ("convert", path) not in cache.jobs
    box.close()
    explorer.close_cleanup()


def test_the_offers_beside_waits_for_the_folders_flag_then_converts_beside(
        qtbot: QtBot, service: IOService, tmp_path: Path, on_a_share: list[str], monkeypatch: pytest.MonkeyPatch) -> None:
    """Finding 1: the beside conversion starts once the store says the folder's flag is on, and asks for
    beside explicitly; a flag that can't be saved stops it, said in the row."""
    explorer, path, panel = raw_folder(qtbot, tmp_path)
    cache, converter = explorer.model.cache, explorer.converter
    monkeypatch.setattr(explorer_convert, "confirm_beside_on_share", lambda parent, folder, share: True)
    saved: list[tuple[str, bool]] = []
    monkeypatch.setattr(cache, "set_write_beside", recording(saved))
    converter.clicked(path)
    click(converter.box, "convert_offer_beside")
    assert saved == [(path, True)] and ("convert", path) not in cache.jobs  # Not before the flag is known.
    panel.show_explorer(explorer, None)
    assert "beside setting" in panel.text("offer")
    beside_flag(explorer, path)  # (The store's answer.)
    qtbot.waitUntil(lambda: ("convert", path) in cache.jobs)
    assert producer(cache, path, "convert").payload["beside"] is True
    converter.close()
    explorer.close_cleanup()


def test_a_beside_flag_that_cant_be_saved_stops_the_offers_conversion(
        qtbot: QtBot, service: IOService, tmp_path: Path, on_a_share: list[str], monkeypatch: pytest.MonkeyPatch) -> None:
    explorer, path, panel = raw_folder(qtbot, tmp_path)
    cache, converter = explorer.model.cache, explorer.converter
    monkeypatch.setattr(explorer_convert, "confirm_beside_on_share", lambda parent, folder, share: True)
    monkeypatch.setattr(cache, "set_write_beside", lambda folder, on: "")  # (Not queued.)
    converter.clicked(path)
    click(converter.box, "convert_offer_beside")
    conversion = converter.conversions[path]
    assert conversion.error.startswith("the folder's beside setting couldn't be saved")
    monkeypatch.setattr(cache, "set_write_beside", lambda folder, on: "owner")
    converter.start(path, "beside")
    cache.cacheAdminResult.emit("convert_prefs", {"kind": "error", "message": "the store is busy"})
    assert converter.conversions[path].error == "the folder's beside setting couldn't be saved: the store is busy"
    assert ("convert", path) not in cache.jobs
    explorer.close_cleanup()


def test_lives_question_goes_with_auto_convert_and_a_later_one_converts(
        qtbot: QtBot, service: IOService, tmp_path: Path, on_a_share: list[str]) -> None:
    """Finding 2: turning auto-convert off (or Live) closes Live's open question, so a later auto-convert
    isn't held by it."""
    explorer, path = watching_raw_folder(qtbot, tmp_path)
    cache, control = explorer.model.cache, explorer.live_control
    cycle(qtbot, explorer, path, tmp_path)
    beside_flag(explorer, path)
    qtbot.waitUntil(lambda: control.box is not None)
    box = control.box
    control.set_auto_convert(False)
    assert control.box is None and box is not None and not box.isVisible()
    explorer_convert.confirm_share(path)
    control.set_auto_convert(True)
    request, _ = cycle(qtbot, explorer, path, tmp_path)  # (Not held by the closed question.)
    assert request.payload["beside"] is True and control.box is None
    explorer.stop_live(save=False)
    assert control.box is None
    explorer.close_cleanup()


def test_lives_question_goes_when_live_stops(
        qtbot: QtBot, service: IOService, tmp_path: Path, on_a_share: list[str]) -> None:
    explorer, path = watching_raw_folder(qtbot, tmp_path)
    control = explorer.live_control
    cycle(qtbot, explorer, path, tmp_path)
    beside_flag(explorer, path)
    qtbot.waitUntil(lambda: control.box is not None)
    box = control.box
    explorer.stop_live(save=False)
    assert control.box is None and box is not None and not box.isVisible()
    explorer.close_cleanup()


def test_the_choice_after_a_refusal_holds_for_the_folder_in_live_and_folder_details(
        qtbot: QtBot, service: IOService, tmp_path: Path) -> None:
    """Finding 3: HeLab's cache or temp folder instead of beside, chosen in Folder details, is the folder's
    for the session: Live's auto-convert of that folder writes there too (and the other way round)."""
    explorer, path = watching_raw_folder(qtbot, tmp_path)
    cache, control, converter = explorer.model.cache, explorer.live_control, explorer.converter
    cycle(qtbot, explorer, path, tmp_path)
    beside_flag(explorer, path)
    converter.conversions[path] = explorer_convert.FolderConversion(path, "beside", time.time(), error="refused",
                                                                    refused="Not written: …")
    converter._refusal_answered(path, "temp")
    assert explorer_convert.instead_of_beside(path) == "temp"
    converter.close()
    session = explorer.live
    assert session is not None and session.convert is not None
    session.convert.ended_at = -1e9
    qtbot.waitUntil(lambda: ("convert", path) in cache.jobs)
    payload = producer(cache, path, "convert").payload
    assert payload["destination"] == "temp" and payload["beside"] is False
    assert "HeLab's temp folder instead of beside" in line(explorer)[1]
    explorer_convert.instead.clear()
    # Live's own choice is the folder's too.
    run_convert(cache, path)
    session.convert.request = True
    control._convert_event(session, {"kind": "beside_refused", "path": path, "shot": 1, "txy": "x",
                                     "message": "Not written: …"})
    control._convert_event(session, {"kind": "error", "message": "Not written: …"})
    click(control.box, "beside_refused_cache")
    assert explorer_convert.instead_of_beside(path) == "cache"
    explorer.stop_live(save=False)
    explorer.close_cleanup()
