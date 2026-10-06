"""Thread-safe access to the registry. The Invoice-Check JP `Registry` wraps one SQLite connection; concurrent use of that connection from several
threads (LangSmith's `evaluate` with max_concurrency > 1, FastAPI's thread pool) intermittently raises `sqlite3.InterfaceError: bad parameter or
other API misuse`. Reads are cheap, so every call is serialised behind a lock."""
import threading


class LockedRegistry:
    def __init__(self, inner):
        self._inner = inner
        self._lock = threading.Lock()

    def lookup(self, reg_no):
        with self._lock:
            return self._inner.lookup(reg_no)

    def status(self, reg_no, on_date):
        with self._lock:
            return self._inner.status(reg_no, on_date)

    def count(self):
        with self._lock:
            return self._inner.count()
