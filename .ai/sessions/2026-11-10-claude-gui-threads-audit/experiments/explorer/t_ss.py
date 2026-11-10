import timeit
from PyQt6.QtWidgets import QApplication, QLabel
app = QApplication([])
l = QLabel("Large folder · ~12 GiB in RAM · right-click › Load data"); l.show(); app.processEvents()
for s in ("", "color: #b86c1d;"):
    l.setStyleSheet(s); app.processEvents()
    def f():
        l.setStyleSheet(s); app.processEvents()
    n=500; print(repr(s), f"{timeit.timeit(f, number=n)/n*1e6:.0f} us per setStyleSheet+processEvents")
