"""A plot's memory warning on its settings page: one line, shown while the memory its settings would take
(``DatasetAnalysis.estimated_bytes``) reaches ``budget_core.ESTIMATE_WARN_SHARE`` of HeLab's RAM budget, with
**Undo** (the settings as they were while under it) and **Cancel** (the run in flight). Hidden otherwise, with the
budget unknown, and for a script that gives no estimate. The plot runs either way; the logic is the plot's
(``AnalysisInstance._memory_check``)."""
from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QWidget

from helab.utils.accessible import identify
from helab.utils.colours import AMBER
from helab.views.ElidedLabel import ElidedLabel
from helab.views.gaps import LABEL_GAP


class MemoryRow(QWidget):
    """The line: the warning (``label``, elided, in full in its tooltip), ``undo`` and ``cancel``."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        identify(self, "plot_memory", "Memory warning")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(LABEL_GAP)
        self.label = identify(ElidedLabel("", self), "plot_memory_warning", "Memory warning")
        self.label.setStyleSheet(f"color: {AMBER};")
        layout.addWidget(self.label, 1)
        self.undo = identify(QPushButton("Undo", self), "plot_memory_undo", "Undo the settings",
                             "Put back the settings as they were before the memory estimate reached the warning")
        layout.addWidget(self.undo)
        self.cancel = identify(QPushButton("Cancel", self), "plot_memory_cancel", "Cancel the run",
                               "Cancel this plot's run in flight")
        layout.addWidget(self.cancel)
        self.cancel.setEnabled(False)
        self.hide()

    def show_warning(self, text: str, undo: str) -> None:
        """Shown with ``text``; ``undo``: what Undo puts back, for its tooltip ("" disables it)."""
        self.label.setText(f"⚠ {text}")
        self.label.setToolTip(f"⚠ {text}. The plot still runs: Undo puts the settings back, Cancel stops the run.")
        self.undo.setEnabled(bool(undo))
        self.undo.setToolTip(f"Put back: {undo}" if undo else "No settings under the warning to go back to")
        self.show()
