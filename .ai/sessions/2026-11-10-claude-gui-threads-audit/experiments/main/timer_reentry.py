import sys, time
from PyQt6.QtCore import QTimer, QEventLoop, QCoreApplication
from PyQt6.QtWidgets import QApplication
app = QApplication(sys.argv)
fires = []
other = []
nested = {"done": False}
t = QTimer(); t.setInterval(10)
def tick():
    fires.append(time.monotonic())
    if not nested["done"]:
        nested["done"] = True
        loop = QEventLoop()
        QTimer.singleShot(500, loop.quit)
        loop.exec()   # like box.exec() inside a resultReady slot
        print("inside-nested fires of same timer:", len(fires) - 1, "other timer fires:", len(other))
        app.quit()
t.timeout.connect(tick)
o = QTimer(); o.setInterval(10); o.timeout.connect(lambda: other.append(1)); o.start()
t.start()
app.exec()
