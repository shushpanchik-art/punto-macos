"""lflifecycle.py - crash handling, restart policy and safe shutdown (RT-6, RT-17, AP-6, AP-7, failure row 11). Standard library only.

STATE: portable logic, tested here with simulated failures and with child processes that really crash (Linux). Nothing here is an OS check:
the supervisor PROCESS (a Windows service or Task, a macOS LaunchAgent that restarts the engine), the start at login and the OS crash
reporter are OS code and are NOT RUN here. Dumps that the operating system or an administrator makes are outside the product (13.4, RT-17).

What a crash report may contain (and nothing else, `validate_report` refuses anything more): a schema number, the product version, the type name
of the exception and of its causes, the stack as module, function and line number, and a few integer counters. NEVER: the message of the exception
(it can carry typed text), local variables, argument values, source lines, file contents, paths, exception-list words, keys. The handler does not call
`traceback.format_exception` and never touches `f_locals`. `faulthandler` is not enabled by this module (its dump files are not ours to write).
Reports are written locally and sent only through an injected `sender`, and only while the diagnostics opt-in is on (AP-7, RT-6).

Restart policy (failure row 11, AP-7): the first crash restarts the worker with the current word dropped (KEEP); a second crash within 60 000 ms
of the previous one (inclusive) gives MANUAL_ONLY with a notice after that second failure. "Until restart" is my reading of the row, as for row 9;
`Supervisor.restart_clean` is the user's re-enable."""
import json
import os
import re
import sys
import threading

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reference"))
import lfengine as L  # noqa: E402

SCHEMA = 1
CRASH_WINDOW_MS = 60_000
COUNTER_KEYS = ("incidents", "restarts", "crashes", "watchdog_trips")
_NAME = re.compile(r"[A-Za-z0-9_.<>\-]{1,120}\Z")
_FILE = re.compile(r"crash-[0-9]{6}\.json\Z")
MAX_FRAMES, MAX_CHAIN = 64, 5


def _safe_name(s) -> str:
    s = s if isinstance(s, str) else "?"
    return s if _NAME.match(s) else "?"


def type_name(t) -> str:
    try:
        mod = getattr(t, "__module__", "") or ""
        return _safe_name(f"{mod}.{t.__qualname__}" if mod and mod != "builtins" else t.__qualname__)
    except Exception:
        return "?"


def _frames(tb):
    out = []
    while tb is not None and len(out) < MAX_FRAMES:
        code = tb.tb_frame.f_code
        mod = os.path.splitext(os.path.basename(code.co_filename or ""))[0]
        out.append({"module": _safe_name(mod), "function": _safe_name(code.co_name), "line": int(tb.tb_lineno)})
        tb = tb.tb_next
    return out


def build_report(exc_type, exc, tb, counters, version):
    """The content-free report of one crash. `exc` is used ONLY to walk the chain of causes by type; its text is never read."""
    chain, e, seen = [], exc, set()
    while e is not None and id(e) not in seen and len(chain) < MAX_CHAIN:
        seen.add(id(e))
        e = e.__cause__ or e.__context__
        if e is not None:
            chain.append(type_name(type(e)))
    c = {}
    for k in COUNTER_KEYS:
        v = (counters or {}).get(k, 0)
        c[k] = v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else 0
    return {"schema": SCHEMA, "product_version": _safe_name(str(version)), "exception": type_name(exc_type), "caused_by": chain,
            "stack": _frames(tb), "counters": c}


def validate_report(r) -> list:
    """The problems of a report (empty: it contains only what the specification allows)."""
    bad = []
    if not isinstance(r, dict) or set(r) != {"schema", "product_version", "exception", "caused_by", "stack", "counters"}:
        return ["fields"]
    if r["schema"] != SCHEMA: bad.append("schema")
    for k in ("product_version", "exception"):
        if not isinstance(r[k], str) or not _NAME.match(r[k]): bad.append(k)
    if not isinstance(r["caused_by"], list) or len(r["caused_by"]) > MAX_CHAIN or not all(isinstance(x, str) and _NAME.match(x) for x in r["caused_by"]):
        bad.append("caused_by")
    st = r["stack"]
    if not isinstance(st, list) or len(st) > MAX_FRAMES: bad.append("stack")
    else:
        for f in st:
            if not (isinstance(f, dict) and set(f) == {"module", "function", "line"} and isinstance(f["module"], str) and _NAME.match(f["module"])
                    and isinstance(f["function"], str) and _NAME.match(f["function"]) and isinstance(f["line"], int) and not isinstance(f["line"], bool) and f["line"] >= 0):
                bad.append("frame"); break
    c = r["counters"]
    if not (isinstance(c, dict) and set(c) == set(COUNTER_KEYS) and all(isinstance(v, int) and not isinstance(v, bool) and v >= 0 for v in c.values())):
        bad.append("counters")
    return bad


class CrashReporter:
    """Writes reports into `directory` (given by the caller; this class never decides where the OS keeps anything, changes no system setting)."""

    def __init__(self, directory, version="0", counters=lambda: {}, max_files=10, sender=None, opt_in=lambda: False):
        self.dir, self.version, self.counters, self.max_files = directory, version, counters, int(max_files)
        self.sender, self.opt_in = sender, opt_in
        self._old = None
        self.last_path = None

    def _own(self):
        return sorted(n for n in os.listdir(self.dir) if _FILE.match(n) and os.path.isfile(os.path.join(self.dir, n)) and not os.path.islink(os.path.join(self.dir, n)))

    def handle(self, exc_type, exc, tb):
        """Never raises. Returns the path of the report, or None."""
        try:
            if exc_type is not None and issubclass(exc_type, (KeyboardInterrupt, SystemExit)):
                return None
            try:
                counters = self.counters()
            except Exception:
                counters = {}                                     # a broken counter source never hides the crash
            rep = build_report(exc_type, exc, tb, counters, self.version)
            if validate_report(rep):
                return None
            data = json.dumps(rep, ensure_ascii=True, sort_keys=True, indent=1).encode("ascii")
            os.makedirs(self.dir, exist_ok=True)
            own = self._own()
            n = (int(own[-1][6:12]) + 1) if own else 1
            path = os.path.join(self.dir, f"crash-{n:06d}.json")
            tmp = path + ".tmp"
            with open(tmp, "wb") as f:
                f.write(data); f.flush(); os.fsync(f.fileno())
            os.replace(tmp, path)
            for old in self._own()[:-self.max_files] if self.max_files > 0 else []:
                os.remove(os.path.join(self.dir, old))
            self.last_path = path
            try:
                if self.sender is not None and self.opt_in():
                    self.sender(data)
            except Exception:
                pass                                              # a failed upload never becomes a second crash
            return path
        except Exception:
            return None

    def install(self):
        """Replace sys.excepthook and threading.excepthook (the default ones print the exception MESSAGE). Returns a function that restores them."""
        old_sys, old_thr = sys.excepthook, threading.excepthook
        self._old = (old_sys, old_thr)

        def hook(t, e, tb):
            self.handle(t, e, tb)

        def thook(args):
            self.handle(args.exc_type, args.exc_value, args.exc_traceback)
        sys.excepthook, threading.excepthook = hook, thook

        def restore():
            sys.excepthook, threading.excepthook = old_sys, old_thr
        return restore


class CrashWindow:
    """Two crashes within 60 s give MANUAL_ONLY (failure row 11, AP-7). Times are monotonic milliseconds."""

    def __init__(self, window_ms=CRASH_WINDOW_MS):
        self.window, self.last, self.manual_only, self.crashes = window_ms, None, False, 0

    def record(self, now_ms: int) -> str:
        if self.last is not None and now_ms < self.last:
            raise ValueError("the clock went back")
        self.crashes += 1
        within = self.last is not None and now_ms - self.last <= self.window
        self.last = now_ms
        if within:
            self.manual_only = True
        return "manual_only" if self.manual_only else "restart"

    def reset(self):
        self.last, self.manual_only = None, False


class Supervisor:
    """Runs worker steps of a Runtime. An exception in a step: the report is written, the current word is dropped (KEEP), the worker
    restarts once; a second failure within 60 s sets MANUAL_ONLY with a notice."""

    def __init__(self, runtime, reporter, clock_ms):
        self.rt, self.rep, self.clock = runtime, reporter, clock_ms
        self.window = CrashWindow()
        self.restarts = 0

    def counters(self):
        return {"incidents": sum(a.incidents for a in self.rt.apps.values()), "restarts": self.restarts, "crashes": self.window.crashes, "watchdog_trips": 0}

    def run(self, fn, *args, **kw):
        try:
            return fn(*args, **kw)
        except Exception:
            t, e, tb = sys.exc_info()
            self.rep.handle(t, e, tb)
            del tb
            verdict = self.window.record(self.clock())
            self.rt.engine.on_event(L.Event("break"))          # the word that was being handled is KEEP; nothing of it survives
            if verdict == "restart":
                self.restarts += 1
            elif self.rt.worker_ok:
                self.rt.worker_ok = False
                self.rt.notices.append(("worker_failed_twice", ""))
            self.rt.apply_mode()
            return None

    def restart_clean(self):
        """The user re-enables (or the process restarts): the window and the flag are cleared."""
        self.window.reset()
        self.rt.worker_ok = True
        self.rt.apply_mode()


def stop(runtime, store=None, state=None):
    """Orderly end: save the exception list first (when a store is given), then wipe what is derived from typed text."""
    saved = None
    if store is not None and state is not None:
        import lfstore as S
        S.sync_from_engine(runtime.engine, state)
        saved = store.save(state)
    runtime.shutdown()
    return saved
