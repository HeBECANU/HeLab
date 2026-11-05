"""A row of buttons that takes more rows only when it doesn't fit (LR-3, Tony 2026-11-05)."""
from __future__ import annotations

from typing import Sequence

from PyQt6.QtCore import QSize
from PyQt6.QtGui import QResizeEvent
from PyQt6.QtWidgets import QHBoxLayout, QLayout, QVBoxLayout, QWidget


class WrapRow(QWidget):
    """``order``'s widgets on one line while they fit at their size hints; else each of ``groups`` on a
    line of its own. Its least width is the widest group's, so a window can still be narrowed to it."""

    def __init__(self, order: Sequence[QWidget], groups: Sequence[Sequence[QWidget]], spacing: int = 6,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        assert sorted(map(id, order)) == sorted(id(w) for group in groups for w in group), "each widget once"
        self.order, self.groups, self.spacing = list(order), [list(group) for group in groups], spacing
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        # (Its least width is ``minimumSizeHint``'s, not one line's, even as a window of its own.)
        self._layout.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        self._layout.setSpacing(spacing // 2 + 2)
        self.rows: list[QHBoxLayout] = []
        self.wrapped: bool | None = None
        self._arrange(False)

    def _width(self, widgets: Sequence[QWidget]) -> int:
        shown = [w for w in widgets if not w.isHidden()]
        return sum(w.sizeHint().width() for w in shown) + self.spacing * max(0, len(shown) - 1)

    def fits(self, width: int) -> bool:
        """Whether ``order`` fits on one line ``width`` px wide."""
        return self._width(self.order) <= width

    def _arrange(self, wrapped: bool) -> None:
        if wrapped == self.wrapped:
            return
        self.wrapped = wrapped
        for row in self.rows:
            while row.count():
                row.takeAt(0)
            self._layout.removeItem(row)
        self.rows = []
        for line in (self.groups if wrapped else [self.order]):
            row = QHBoxLayout()
            row.setSpacing(self.spacing)
            for widget in line:
                row.addWidget(widget)
            row.addStretch(1)
            self._layout.addLayout(row)
            self.rows.append(row)
        self.updateGeometry()

    def resizeEvent(self, a0: QResizeEvent | None) -> None:
        super().resizeEvent(a0)
        self._arrange(not self.fits(self.width()))

    def minimumSizeHint(self) -> QSize:
        return QSize(max(self._width(group) for group in self.groups), super().minimumSizeHint().height())

    def sizeHint(self) -> QSize:
        hint = super().sizeHint()
        return QSize(self._width(self.order), hint.height())
