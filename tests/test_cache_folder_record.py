"""A44.2: the GUI records its cache folder (``cache-folder.json`` in the app folder) at startup, for
``helab cache``; ``helab convert``, which resolves the cache folder the same way, never writes it."""
from __future__ import annotations

import json
from pathlib import Path
from types import ModuleType
import pytest
from PyQt6 import QtWebEngineWidgets  # noqa: F401  (before any QApplication: helab.main)
from pytestqt.qtbot import QtBot

from helab.utils.cache_locks import FileLock
from test_one_running import entry  # noqa: F401  (a fixture)


def test_the_app_records_its_cache_folder_and_helab_convert_does_not(
        entry: ModuleType, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:  # noqa: F811
    from helab import convert_cli
    from helab.utils import constants
    monkeypatch.setenv("HELAB_APP_DIR_OVERRIDE", str(tmp_path / "app"))  # (This test's own app folder.)
    recorded = Path(constants.app_folder()) / constants.CACHE_FOLDER_FILE
    _, instance = convert_cli._start_cache()
    assert isinstance(instance, FileLock)
    instance.unlock()
    assert not recorded.exists()
    monkeypatch.setattr(entry, "_recover_in_helper", lambda settings, token: ("", True))
    entry._start_cache()
    try:
        assert json.loads(recorded.read_text(encoding="utf-8"))["cache_folder"] == constants.cache_dir()
    finally:
        entry._INSTANCE_LOCK.pop().unlock()

