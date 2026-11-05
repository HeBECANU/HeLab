"""The Scripts panel's groups (LR-12): each entry once, "Basic Plots" holding its versions as nodes, newest first
and only the newest expanded; the selector's popup as wide as its longest entry, never cut."""
from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QFileDialog, QMainWindow, QPushButton, QTreeWidgetItem
from pytestqt.qtbot import QtBot

from helab.scripts import standard
from helab.scripts.standard import group as group_v1
from helab.scripts.standard_v2 import group as group_v2
from helab.views.plots import script_tree
from helab.views.plots.script_tree import TreePanelWidget, entry_of, nodes_of
from helab.views.plots.workspace import PlotWorkspace

SCRIPT = '''
from typing import Any, List
from helab.scripts.base import HelabAnalysisScript, ScriptMetadata

class {cls}(HelabAnalysisScript):
    def get_metadata(self) -> ScriptMetadata:
        return self.create_metadata("{name}", "A user's script", "{group}", __file__, "lab.{ident}", "1")

    def get_actions(self) -> List[str]:
        return ["Plot"]

    def execute_action(self, action_name: str, **kwargs: Any) -> None:
        pass
'''


def panel(qtbot: QtBot) -> TreePanelWidget:
    widget = TreePanelWidget(PlotWorkspace(QMainWindow()))
    qtbot.addWidget(widget)
    return widget


def entries(widget: TreePanelWidget) -> list[str]:
    return [widget.group_selector.itemText(index) for index in range(widget.group_selector.count())]


def tops(widget: TreePanelWidget) -> list[QTreeWidgetItem]:
    tree = widget.tree_widget
    return [item for index in range(tree.topLevelItemCount()) if (item := tree.topLevelItem(index)) is not None]


def tree(widget: TreePanelWidget) -> dict[str, tuple[bool, list[str]]]:
    """Each top-level node: whether it is expanded, and its scripts."""
    return {top.text(0): (top.isExpanded(), [child.text(0) for index in range(top.childCount())
                                             if (child := top.child(index)) is not None]) for top in tops(widget)}


def versions(widget: TreePanelWidget) -> list[str]:
    return [top.text(0) for top in tops(widget) if top.text(0).startswith("v")]


@pytest.fixture
def user_folder(tmp_path: Path) -> Path:
    """A user's folder whose scripts use the family's names and an own group."""
    folder = tmp_path / "lab_scripts"
    folder.mkdir()
    for ident, (cls, name, group) in enumerate((("Mine", "My counts", group_v1.NAME),
                                                ("Named", "Named like the family", standard.FAMILY),
                                                ("Lab", "Lab plot", "Lab"))):
        (folder / f"script_{ident}.py").write_text(SCRIPT.format(cls=cls, name=name, group=group, ident=ident))
    return folder


def test_the_family_is_one_entry() -> None:
    assert standard.FAMILY == "Basic Plots"
    assert [name for name, _ in standard.FAMILY_GROUPS] == [group_v2.NAME, group_v1.NAME]  # Newest first.
    assert [label for _, label in standard.FAMILY_GROUPS] == ["v2", "v1"]
    assert group_v1.NAME == "Basic plots v1"  # v1's group stays as it was.
    for name in (group_v2.NAME, group_v1.NAME, standard.FAMILY):
        assert entry_of(name) == "Basic Plots"
    assert entry_of("DLD Front Panel Port") == "DLD Front Panel Port" and entry_of("Lab") == "Lab"
    nodes = nodes_of("Basic Plots", [group_v1.NAME, "Lab", standard.FAMILY, group_v2.NAME])
    assert [(node.label, node.group, node.older) for node in nodes] == [
        ("v2", group_v2.NAME, False), ("v1", group_v1.NAME, True), ("Basic Plots", "Basic Plots", False)]
    assert nodes_of("Lab", ["Lab"])[0].label == "Lab" and nodes_of("Gone", ["Lab"]) == []


def test_the_selector_lists_each_entry_once(qtbot: QtBot) -> None:
    widget = panel(qtbot)
    assert entries(widget) == ["Basic Plots", "DLD Front Panel Port"]
    assert widget.group_selector.currentText() == "Basic Plots"
    for _ in range(3):
        widget._refresh()
    assert entries(widget) == ["Basic Plots", "DLD Front Panel Port"]
    assert set(versions(widget)) <= {"v2", "v1"} and "v1" in versions(widget)


def test_version_nodes_newest_first_only_the_newest_expanded(qtbot: QtBot) -> None:
    widget = panel(qtbot)
    listed = tree(widget)
    assert versions(widget) == [label for name, label in standard.FAMILY_GROUPS
                                if name in widget.script_manager.get_groups()]
    assert listed["v1"][1] == ["3D scatter", "Counts per shot", "T, X, Y histograms", "Transfer fractions"]
    [first, *others] = versions(widget)
    assert listed[first][0] and not any(listed[label][0] for label in others)
    widget.group_selector.setCurrentText("DLD Front Panel Port")
    assert list(tree(widget)) == ["DLD Front Panel Port"] and tree(widget)["DLD Front Panel Port"][0]


def test_a_node_opened_or_closed_stays_so_for_the_session(qtbot: QtBot) -> None:
    widget = panel(qtbot)
    [first, *_] = tops(widget)
    first.setExpanded(False)  # The user closes the newest.
    widget.group_selector.setCurrentText("DLD Front Panel Port")
    widget.group_selector.setCurrentText("Basic Plots")
    assert not tops(widget)[0].isExpanded()
    tops(widget)[0].setExpanded(True)
    widget._refresh()
    assert tops(widget)[0].isExpanded()


def test_older_versions_name_theirs_on_their_run_buttons(qtbot: QtBot) -> None:
    widget = panel(qtbot)
    tree_widget = widget.tree_widget
    for top in tops(widget):
        for index in range(top.childCount()):
            button = tree_widget.itemWidget(top.child(index), 1)
            assert isinstance(button, QPushButton)
            name = top.child(index).text(0)  # type: ignore[union-attr]
            older = top.text(0) != versions(widget)[0]
            assert button.accessibleName() == f"Plot {name}" + (f" ({top.text(0)})" if older else "")
            if top.text(0) == "v1":
                assert button.objectName().startswith("run_helab.") and "helab.v2." not in button.objectName()


def test_user_groups_named_like_the_family_join_it(qtbot: QtBot, user_folder: Path,
                                                   monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(script_tree, "PROBING", False)
    widget = panel(qtbot)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args, **kwargs: str(user_folder))
    widget.load_dir_button.click()
    qtbot.waitUntil(lambda: "Lab" in entries(widget), timeout=30_000)
    assert entries(widget) == ["Basic Plots", "DLD Front Panel Port", "Lab"]
    listed = tree(widget)
    assert "My counts" in listed["v1"][1]  # Its group is v1's: beside v1's plots.
    assert listed["Basic Plots"] == (False, ["Named like the family"])  # Its own node, after the versions.
    widget.reload_scripts()
    qtbot.waitUntil(lambda: not widget._pending and not widget._probing, timeout=30_000)
    for _ in range(2):
        widget._refresh()
    assert entries(widget) == ["Basic Plots", "DLD Front Panel Port", "Lab"]
    widget.remove_folder(str(user_folder))
    assert entries(widget) == ["Basic Plots", "DLD Front Panel Port"]
    assert "Basic Plots" not in tree(widget) and "My counts" not in tree(widget)["v1"][1]


@pytest.fixture
def windows_style() -> Iterator[None]:
    """The Windows style, whose combo popup Qt doesn't widen to its entries (as on the lab's PCs)."""
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    old = app.style()
    name = old.name() if old is not None else "Fusion"
    app.setStyle("Windows")
    yield
    app.setStyle(name)


@pytest.mark.parametrize("width", [120, 200])
def test_the_popup_fits_its_longest_entry_uncut(qtbot: QtBot, windows_style: None, width: int) -> None:
    widget = panel(qtbot)
    widget.resize(width, 400)
    widget.show()
    qtbot.waitExposed(widget)
    selector = widget.group_selector
    view, model = selector.view(), selector.model()
    assert view is not None and model is not None
    assert selector.width() < view.fontMetrics().horizontalAdvance("DLD Front Panel Port")  # Narrow.
    selector.showPopup()
    try:
        qtbot.waitUntil(lambda: view.isVisible(), timeout=5_000)
        assert view.textElideMode() == Qt.TextElideMode.ElideNone
        metrics = view.fontMetrics()
        for index in range(selector.count()):
            text = selector.itemText(index)
            viewport = view.viewport()
            assert viewport is not None and viewport.width() >= metrics.horizontalAdvance(text), text
            assert view.visualRect(model.index(index, 0)).width() >= metrics.horizontalAdvance(text)
    finally:
        selector.hidePopup()
