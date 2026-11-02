"""Plain PyQt: a Python-owned top-level widget in a reference cycle, collected by the garbage collector
while Qt polishes it (Python code runs in a child label's changeEvent during the polish)."""
import faulthandler
import gc
import sys

from PyQt6.QtCore import QEvent
from PyQt6.QtWidgets import QApplication, QLabel, QPushButton, QVBoxLayout, QWidget

faulthandler.enable()
app = QApplication(sys.argv[:1] + ["-platform", "offscreen"])
parented = len(sys.argv) > 1 and sys.argv[1] == "parented"
keeper = QWidget()  # (A Qt parent for the "parented" case, as a window would be.)


class Note(QLabel):
    def changeEvent(self, event: QEvent | None) -> None:  # Python code in the polish, as ElidedLabel's
        super().changeEvent(event)
        if event is not None and event.type() == QEvent.Type.PaletteChange:
            gc.collect()  # (The cyclic collector, which any Python allocation can start.)


class Panel(QWidget):
    def __init__(self, parent: QWidget | None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.note = Note(self)
        self.note.setStyleSheet("color: #e0a000;")  # polish sets its palette
        layout.addWidget(self.note)
        button = QPushButton("Plot", self)
        button.clicked.connect(lambda: self.close())  # a cycle: panel -> button -> closure -> panel
        layout.addWidget(button)


gc.disable()  # (Only the forced collections, at the worst moment.)
for round_ in range(200):
    Panel(keeper if parented else None)  # Its PolishRequest is posted; Python drops it at once.
    app.processEvents()
print("survived", "parented" if parented else "python-owned")
