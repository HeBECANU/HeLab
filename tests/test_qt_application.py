"""No test makes the worker's QApplication with an empty argument list (known-issues 139, 162).

QtWebEngine needs the program name: with ``QApplication([])`` it ends the process at the first web view
("Argument list is empty, the program name is not passed to QCoreApplication. base::CommandLine cannot be
properly initialized.", a qFatal in ``QtWebEngineCore::WebContentsAdapter``, from ``QWebEngineView.setUrl``).
An xdist worker whose first Qt test made its own ``QApplication([])`` (test_memroyUsageWindow's fixture, for
one) aborted at its first Plotly plot: CI's "worker crashed" in test_plot_backends' Plotly cases."""
from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APPLICATIONS = {"QApplication", "QGuiApplication", "QCoreApplication"}


def _empty_applications(tree: ast.AST) -> list[int]:
    """The lines of every ``Q*Application()`` or ``Q*Application([])`` in ``tree``, and in the scripts its
    strings hold (a test's subprocess script)."""
    lines: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and "\n" in node.value:
            try:
                script = ast.parse(node.value)
            except SyntaxError:
                continue
            lines += [node.lineno] * len(_empty_applications(script))
        if not isinstance(node, ast.Call) or node.keywords or len(node.args) > 1:
            continue
        name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", None)
        if name not in APPLICATIONS:
            continue
        argument = node.args[0] if node.args else None
        if argument is None or isinstance(argument, (ast.List, ast.Tuple)) and not argument.elts:
            lines.append(node.lineno)
    return lines


def test_no_code_makes_a_qapplication_without_a_program_name() -> None:
    found = [f"{path.relative_to(ROOT)}:{line}"
             for folder in ("helab", "tests") for path in sorted((ROOT / folder).rglob("*.py"))
             if path != Path(__file__).resolve()  # its own samples, below
             for line in _empty_applications(ast.parse(path.read_text(encoding="utf-8")))]
    assert not found, f"QApplication([]) aborts the process at its first web view; use qapp or conftest.qt_application: {found}"


def test_the_check_finds_an_empty_application() -> None:
    script = 'from PyQt6 import QtWidgets\napp = QtWidgets.QApplication([])\nscript = """\nimport sys\nQCoreApplication()\n"""\n'
    assert _empty_applications(ast.parse(script)) == [2, 3]
    assert not _empty_applications(ast.parse("QApplication(sys.argv)\nQApplication(['helab'])\n"))


def test_a_plotly_plot_after_the_memory_window_test_keeps_its_worker(tmp_path: Path) -> None:
    """CI's worker order (41488725971, Ubuntu group 2/3, gw1): test_memroyUsageWindow was the worker's first
    Qt test, and its fixture made the QApplication; the worker aborted (SIGABRT) at its next Plotly plot."""
    done = subprocess.run([sys.executable, "-X", "faulthandler", "-m", "pytest", "-q", "-p", "no:randomly",
                           "-p", "no:cacheprovider", "-p", "no:xdist", "-p", "no:rerunfailures",
                           f"--basetemp={tmp_path / 'nested'}",
                           "tests/test_memroyUsageWindow.py::test_memory_usage_window_initialization",
                           "tests/test_plot_backends.py::test_2d_plots_draw_with_every_library[values0-Plotly-TxyHistograms]"],
                          capture_output=True, text=True, timeout=300, cwd=str(ROOT), env=dict(os.environ))
    assert done.returncode == 0, (done.returncode, done.stdout[-1500:], done.stderr[:1500])  # the qFatal comes first
