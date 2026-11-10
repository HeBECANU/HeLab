import threading, time, os, sys
def watch():
    time.sleep(1.0)
    os.write(2, b"watchdog fired\n")
    os._exit(7)
threading.Thread(target=watch, daemon=True).start()
class Slow:
    def __del__(self):
        os.write(2, b"slow __del__ start\n")
        time.sleep(3)
        os.write(2, b"slow __del__ done\n")
import gc; gc.disable()
a = Slow(); a.self = a   # a cycle, freed only by the finalization-time collection
del a
sys.exit(0)
