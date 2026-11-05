"""A plot's "Plot info" section (LR-4): a collapsible block at the top of its settings page holding what was
repeated between the plot dock's source lines, the plot's own title and the settings page: the input, its
revision and Live state, the shots used, the TXY source, the analysis and its saved-result mark, the settings in
short and the full record. Closed, it is one line (the input, an ``ElidedLabel``: cut at the edge, its full text
in the tooltip); open, its lines wrap to the panel's width, long folder names included (``explorer_text.breakable``).
Its tooltips are plain text, which the app wraps (``helab/views/tooltips.py``)."""
from __future__ import annotations

from typing import Iterable, Optional

from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QScrollArea, QSizePolicy, QToolButton, QVBoxLayout, QWidget

from helab.utils.accessible import identify
from helab.views.ElidedLabel import ElidedLabel
from helab.views.explorer_text import breakable
from helab.views.gaps import LABEL_GAP

BODY_LINES = 12  # The open section's most height, in lines: more scrolls (the settings below keep their room).


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
        """The closed line's tooltip (plain: the app wraps it; elided, the label puts its full text first)."""
        self.summary.setToolTip(text)

    @pyqtSlot(bool)
    def _toggled(self, opened: bool) -> None:
        self._show_state(opened)
        self.toggled.emit(opened)

    def _show_state(self, opened: bool) -> None:
        self.toggle.setArrowType(Qt.ArrowType.DownArrow if opened else Qt.ArrowType.RightArrow)
        self.body.setVisible(opened)
