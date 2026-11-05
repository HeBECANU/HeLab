"""Plain-text tooltips wrapped to a readable width, app-wide (LR-3, T4; Tony 2026-11-05).

Qt wraps a plain-text tooltip only once it is wider than the screen, so a long one showed as a single
line across most of it. ``TooltipWrap``, installed on the application, shows any plain-text tooltip
with a line wider than ``WIDTH`` px wrapped at word boundaries (a long path or name is broken where it
must be, after a "/" or "_" when it can), and an elided ``ElidedLabel``'s tooltip with its full text first
(``hover_tip``: a filter, as an ``event`` override there was called on labels being deleted). Rich-text tooltips stay as they are (Qt wraps those), and so
does a tooltip that fits. The text is never changed, only how it is shown: ``toolTip()`` and the
models' tooltips keep what was set.
"""
from __future__ import annotations

import re

from PyQt6.QtCore import QEvent, QObject, Qt
from PyQt6.QtGui import QFontMetrics, QHelpEvent
from PyQt6.QtWidgets import QAbstractItemView, QApplication, QTabBar, QToolTip, QWidget

WIDTH = 600  # px: the widest line a wrapped tooltip shows.


def rich_text(text: str) -> bool:
    """Qt's guess whether ``text`` is rich text, as its tooltips and labels make it (``Qt::mightBeRichText``;
    not in PyQt6's type stubs)."""
    return bool(getattr(Qt, "mightBeRichText")(text))


def _fit(text: str, metrics: QFontMetrics, width: int) -> int:
    """How many of ``text``'s first characters fit in ``width`` (at least one), cut after a "/", "_", "-"
    or "." in the second half when there is one."""
    low, high = 1, len(text)
    while low < high:
        mid = (low + high + 1) // 2
        if metrics.horizontalAdvance(text[:mid]) <= width:
            low = mid
        else:
            high = mid - 1
    cut = max(text.rfind(mark, 0, low) for mark in "/_-.") + 1
    return cut if cut > low // 2 else low


def wrap_tip(text: str, metrics: QFontMetrics, width: int = WIDTH) -> str:
    """``text`` (plain) with each line wider than ``width`` px broken at spaces into lines that fit; a
    word wider than ``width`` is broken by ``_fit``. Lines that fit, and the line breaks given, stay."""
    lines: list[str] = []
    for line in text.split("\n"):
        if metrics.horizontalAdvance(line) <= width:
            lines.append(line)
            continue
        current = ""
        for word in re.split(r"(?<= )", line):
            if current and metrics.horizontalAdvance((current + word).rstrip()) > width:
                lines.append(current.rstrip())
                current = ""
            current += word
            while metrics.horizontalAdvance(current.rstrip()) > width:
                cut = _fit(current, metrics, width)
                lines.append(current[:cut])
                current = current[cut:]
        lines.append(current.rstrip())
    return "\n".join(lines)


def needs_wrap(text: str, metrics: QFontMetrics, width: int = WIDTH) -> bool:
    """Whether ``text`` is a plain-text tooltip with a line wider than ``width``."""
    return bool(text) and not rich_text(text) and any(
        metrics.horizontalAdvance(line) > width for line in text.split("\n"))


def tooltip_at(obj: QObject, event: QHelpEvent) -> str:
    """The tooltip Qt would show for ``event`` on ``obj``: an item view's cell's (on its viewport), a tab's,
    or the widget's own (an ``ElidedLabel``'s with its full text while elided: ``hover_tip``)."""
    parent = obj.parent() if isinstance(obj, QWidget) else None
    if isinstance(parent, QAbstractItemView) and obj is parent.viewport():
        index = parent.indexAt(event.pos())
        value = index.data(Qt.ItemDataRole.ToolTipRole) if index.isValid() else None
        return value if isinstance(value, str) else ""
    if isinstance(obj, QTabBar):
        tab = obj.tabAt(event.pos())
        return obj.tabToolTip(tab) if tab >= 0 else ""
    if isinstance(obj, QWidget):
        hover = getattr(obj, "hover_tip", None)
        return str(hover()) if callable(hover) else obj.toolTip()
    return ""


class TooltipWrap(QObject):
    """The application's event filter that shows long plain-text tooltips wrapped (``wrap_tip``)."""

    def eventFilter(self, a0: QObject | None, a1: QEvent | None) -> bool:
        if a0 is None or a1 is None or a1.type() != QEvent.Type.ToolTip or not isinstance(a1, QHelpEvent):
            return False
        text = tooltip_at(a0, a1)
        metrics = QFontMetrics(QToolTip.font())
        # Its own: an elided label's full text with its tooltip (``hover_tip``), not what Qt would show.
        own = getattr(a0, "hover_tip", None) is not None and text != getattr(a0, "toolTip")()
        if not own and not needs_wrap(text, metrics):
            return False  # (Qt shows it as it is, or hides an empty one.)
        widget = a0 if isinstance(a0, QWidget) else None
        QToolTip.showText(a1.globalPos(), wrap_tip(text, metrics) if needs_wrap(text, metrics) else text, widget)
        return True


_installed: TooltipWrap | None = None


def install(app: QApplication) -> TooltipWrap:
    """Wrap long plain-text tooltips in ``app`` (once; ``helab/main.py`` calls it)."""
    global _installed
    if _installed is None:
        _installed = TooltipWrap(app)
        app.installEventFilter(_installed)
    return _installed
