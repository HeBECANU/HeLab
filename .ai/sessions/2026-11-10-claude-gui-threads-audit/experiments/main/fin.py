import threading, time, os, sys
def watch():
    time.sleep(1.0)
    os.write(2, b"watchdog fired\n")
    os._exit(7)
threading.Thread(target=watch, daemon=True).start()
class Slow:
    def __del__(self):
        time.sleep(3)   # a destructor that blocks during module teardown
        os.write(2, b"slow __del__ done\n")
keep = Slow()          # module global: destroyed at finalization
sys.exit(0)
