"""GT-9: HeLab opens local folders and files in the file manager through a detached process, never
``QDesktopServices.openUrl``, whose shell open runs on the GUI thread and can stall on a share that went away."""
from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

from helab.utils import file_manager

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("platform,command", [
    ("darwin", ("open", ["/Volumes/share/run"])),
    ("linux", ("xdg-open", ["/Volumes/share/run"])),
])
def test_each_os_opens_with_its_own_program(monkeypatch: pytest.MonkeyPatch, platform: str,
                                            command: tuple[str, list[str]]) -> None:
    monkeypatch.setattr(file_manager, "sys", SimpleNamespace(platform=platform))
    assert file_manager.open_command("/Volumes/share/run") == command


def test_windows_opens_with_explorer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(file_manager, "sys", SimpleNamespace(platform="win32"))
    program, arguments = file_manager.open_command("O:/data/run")
    assert program == "explorer" and len(arguments) == 1


def test_show_launches_detached_and_says_when_it_couldnt(
        no_file_manager: list[tuple[str, list[str]]], monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture) -> None:
    assert file_manager.show("/somewhere") and no_file_manager == [file_manager.open_command("/somewhere")]
    monkeypatch.setattr(file_manager, "launch", lambda program, arguments: False)
    assert not file_manager.show("/somewhere") and "Couldn't open /somewhere" in caplog.text


def test_no_gui_module_opens_a_local_path_with_open_url() -> None:
    """``openUrl`` stays for web addresses only (``QUrl(url)``); a ``QUrl.fromLocalFile`` goes to ``show``."""
    found = []
    for path in sorted((ROOT / "helab").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "openUrl"
                    and "fromLocalFile" in ast.unparse(node)):
                found.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert found == [], found
