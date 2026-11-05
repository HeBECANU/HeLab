"""Single-line label that elides to its width instead of wrapping or widening its parent."""
from __future__ import annotations

import html

from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QResizeEvent, QTextDocument
from PyQt6.QtWidgets import QLabel, QSizePolicy, QWidget

from helab.views.tooltips import rich_text


class ElidedLabel(QLabel):
    """``text()`` returns the full text; the label shows as much as fits.

    Its height never depends on the text, so status rows keep their height and
    the widgets below them do not move. While it is elided, the tooltip shown has the full text first
    (``hover_tip``, shown by the app's ``tooltips.TooltipWrap``), so what is cut can always be read (LR-3);
    ``toolTip()`` stays as set.
    """

    def __init__(self, text: str = "", parent: QWidget | None = None,
                 mode: Qt.TextElideMode = Qt.TextElideMode.ElideRight) -> None:
        super().__init__(parent)
        self._full = ""
        self._mode = mode
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setWordWrap(False)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.setText(text)

    def setText(self, a0: str | None) -> None:
        self._full = a0 or ""
        self._elide()

    def text(self) -> str:
        return self._full

    def clear(self) -> None:
        self.setText("")

    def natural_width(self) -> int:
        """Width of the full text, for rows that share their width between labels."""
        margins = self.contentsMargins()
        return self.fontMetrics().horizontalAdvance(self._full) + margins.left() + margins.right() + 1

    def elided(self) -> bool:
        """Whether the label shows less than its text."""
        return bool(self._full) and QLabel.text(self) != self._full

    def hover_tip(self) -> str:
        """The tooltip it shows: the set one, with the full text first while elided (unless the set
        tooltip already holds it)."""
        tip = self.toolTip()
        if not self.elided():
            return tip
        if rich_text(tip):
            document = QTextDocument()
            document.setHtml(tip)
            if self._full in document.toPlainText():
                return tip
            return f"{html.escape(self._full)}<br><br>{tip}"
        if self._full in tip:
            return tip
        return f"{self._full}\n\n{tip}" if tip else self._full

    def changeEvent(self, a0: QEvent | None) -> None:
        super().changeEvent(a0)
        if a0 is not None and a0.type() == QEvent.Type.FontChange:
            self._elide()

    def resizeEvent(self, a0: QResizeEvent | None) -> None:
        super().resizeEvent(a0)
        self._elide()

    def _elide(self) -> None:
        width = max(0, self.contentsRect().width())
        super().setText(self.fontMetrics().elidedText(self._full, self._mode, width))
