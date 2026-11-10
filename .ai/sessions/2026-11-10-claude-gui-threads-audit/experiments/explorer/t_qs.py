import timeit, os
from PyQt6.QtCore import QSettings, QCoreApplication
app = QCoreApplication([])
s = QSettings("HeLabAuditTmp", "gt-audit"); s.setValue("k", 5); s.sync(); del s
def native():
    return QSettings("HeLabAuditTmp", "gt-audit").value("k", 0)
ini = "/private/tmp/claude-501/gt-audit-explorer/t.ini"
q = QSettings(ini, QSettings.Format.IniFormat); 
for i in range(300): q.setValue(f"g/k{i}", "x"*50)
q.sync(); del q
def inif():
    return QSettings(ini, QSettings.Format.IniFormat).value("g/k5", 0)
for f in (native, inif):
    n=2000
    t = timeit.timeit(f, number=n)/n
    print(f.__name__, f"{t*1e6:.0f} us")
s = QSettings("HeLabAuditTmp", "gt-audit"); s.clear(); s.sync()
