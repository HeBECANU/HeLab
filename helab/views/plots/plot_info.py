"""A plot's "Plot info" section (LR-4): a collapsible block at the top of its settings page holding what was
repeated between the plot dock's source lines, the plot's own title and the settings page: the input, its
revision and Live state, the shots used, the TXY source, the analysis and its saved-result mark, the settings in
short and the full record. Closed, it is one line (the input, cut at the edge, all of it in the tooltip); open,
its lines wrap to the panel's width, long folder names included.

Also ``wrapped_tip``, a tooltip that wraps (LR-3): Qt wraps only rich-text tooltips, so a long plain one ran
across the screen."""
from __future__ import annotations

import html
from typing import Iterable, Optional

from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QScrollArea, QSizePolicy, QToolButton, QVBoxLayout, QWidget

from helab.utils.accessible import identify
from helab.views.ElidedLabel import ElidedLabel
from helab.views.gaps import LABEL_GAP

# Qt wraps a label's words after "/" and "-" but not "_", so a folder name like run_0042_bragg_scan_… was cut at
# the panel's edge: the shown text gets a zero-width break after each "_" (``lines()`` keeps the plain text).
BREAK = "\u200b"
BODY_LINES = 12  # The open section's most height, in lines: more scrolls (the settings below keep their room).


def breakable(text: str) -> str:
    """``text`` as shown in a wrapped label: a place to wrap after each underscore."""
    return text.replace("_", "_" + BREAK)


def rich(text: str) -> bool:
    """Whether Qt shows ``text`` as rich text (and so wraps it as a tooltip): it opens with a tag, as Qt's own
    test (``Qt::mightBeRichText``, which PyQt6 doesn't offer) mostly decides."""
    stripped = text.lstrip()
    return stripped.startswith("<") and ">" in stripped


def wrapped_tip(text: str) -> str:
    """``text`` as a tooltip that wraps: rich text (Qt wraps a rich tooltip, a long folder name anywhere, as a
    word-wrapped label does), escaped, its lines kept. "" stays ""."""
    if not text:
        return ""
    return "<qt>" + "<br>".join(html.escape(line, quote=False) for line in text.splitlines()) + "</qt>"


class TipLabel(ElidedLabel):
    """A one-line label (elided at its width, ``text()`` the full text) whose tooltip is its whole text,
    wrapped, unless one is set (``setToolTip``, wrapped too): a plot's status line, its input line (LR-3)."""

    def __init__(self, text: str = "", parent: Optional[QWidget] = None) -> None:
        self._own_tip = False
        super().__init__(text, parent)

    def setText(self, a0: Optional[str]) -> None:
        super().setText(a0)
        self._own_tip = False
        super().setToolTip(wrapped_tip(a0 or ""))

    def setToolTip(self, a0: Optional[str]) -> None:
        text = a0 or ""
        self._own_tip = bool(text)
        super().setToolTip(text if rich(text) else wrapped_tip(text))


class PlotInfo(QWidget):
    """The section: a toggle ("▸ Plot info"), the plot's input line beside it (``summary``, the plot's own
    ``input_label``: one line, elided), and the wrapped lines below it while open. ``toggled(open)``."""

    toggled = pyqtSignal(bool)

    def __init__(self, summary: ElidedLabel, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(LABEL_GAP)
        self.toggle = identify(QToolButton(self), "plot_info", "Plot info",
                               "Show or hide this plot's input, shots, TXY source, analysis and record")
        self.toggle.setCheckable(True)
        self.toggle.setAutoRaise(True)
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.setText("Plot info")
        self.toggle.toggled.connect(self._toggled)
        header.addWidget(self.toggle)
        self.summary = summary
        summary.setParent(self)
        header.addWidget(summary, 1)
        layout.addLayout(header)
        self.text = identify(QLabel(self), "plot_info_text", "Plot info details")
        self.text.setTextFormat(Qt.TextFormat.PlainText)
        self.text.setWordWrap(True)
        self.text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        policy = QSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Minimum)
        policy.setHeightForWidth(True)  # (Its wrapped lines' height at its width.)
        self.text.setSizePolicy(policy)
        self.text.setContentsMargins(LABEL_GAP, 0, 0, 0)
        # Open, at most BODY_LINES high and scrolling beyond, never cut at the bottom nor squeezing the page.
        self.body = QScrollArea(self)
        self.body.setFrameShape(QFrame.Shape.NoFrame)
        self.body.setWidgetResizable(True)
        self.body.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.body.setWidget(self.text)
        self.body.setMaximumHeight(self.text.fontMetrics().lineSpacing() * BODY_LINES)
        self.body.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Maximum)
        layout.addWidget(self.body)
        self._lines: tuple[str, ...] = ()
        self._show_state(False)

    def is_open(self) -> bool:
        return self.toggle.isChecked()

    def set_open(self, opened: bool) -> None:
        self.toggle.setChecked(opened)

    def lines(self) -> tuple[str, ...]:
        """The section's lines as set."""
        return self._lines

    def set_lines(self, lines: Iterable[str]) -> None:
        """The lines shown while open (each wraps; empty lines are left out)."""
        self._lines = tuple(line for line in lines if line)
        self.text.setText("\n".join(breakable(line) for line in self._lines))

    def set_summary_tip(self, text: str) -> None:
        """The closed line's tooltip: its whole text, wrapped."""
        self.summary.setToolTip(wrapped_tip(text))

    @pyqtSlot(bool)
    def _toggled(self, opened: bool) -> None:
        self._show_state(opened)
        self.toggled.emit(opened)

    def _show_state(self, opened: bool) -> None:
        self.toggle.setArrowType(Qt.ArrowType.DownArrow if opened else Qt.ArrowType.RightArrow)
        self.body.setVisible(opened)
