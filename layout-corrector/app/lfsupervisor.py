"""lfsupervisor.py - the restart supervisor PROCESS and the engine entry (AP-7, failure row 11). Standard library only.

Three failures are kept apart (they are different things in the specification):
  * a WORKER failure: an exception in a step of the engine; handled INSIDE the engine process by `lflifecycle.Supervisor` (the word is dropped,
    one restart, a second failure within 60 s gives MANUAL_ONLY). The process stays alive and the exit code is not involved;
  * a crash of the ENGINE process (a fatal signal, a native fault, an uncaught exception that ends the process): seen from outside as an exit status
    other than zero. `ProcessSupervisor` restarts it; the second such crash within 60 000 ms (inclusive) restarts it with `--manual-only`;
  * a crash of the SUPERVISOR itself: it is a few lines and holds no text; something outside restarts it (macOS: launchd `KeepAlive`, see lfautostart;
    Windows: nothing, the next logon). Not covered here, not claimed.
The two 60-second windows are SEPARATE: a worker failure followed by a process crash is not "two crashes" (my reading of the specification, which does not
say; for the requester). The user's quit is exit status 0 and is never restarted.
Beyond the specification (marked): a pause of at least `min_delay_ms` between starts, and a crash loop guard: more than `max_crashes` crashes inside
`loop_window_ms` (default 5 in 10 minutes) and the supervisor stops restarting and exits with status 70, instead of spinning forever.
The child's stdin, stdout and stderr are the null device: nothing it prints can reach a log of the supervisor, and the supervisor prints nothing.
STATE: portable logic; the tests start real child processes on Linux. No Windows or macOS process behaviour was checked (NOT RUN)."""
import os
import subprocess
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lflifecycle as K  # noqa: E402

EXIT_GAVE_UP = 70
ROLES = ("--supervisor", "--engine")


def parse_args(argv):
    """argv without the program name. Exactly one role, and `--manual-only` only for the engine. Nothing else is accepted: no path, no value."""
    if not 1 <= len(argv) <= 2 or len(set(argv)) != len(argv):
        raise ValueError("usage: (--supervisor | --engine [--manual-only])")
    roles = [a for a in argv if a in ROLES]
    extra = [a for a in argv if a not in ROLES]
    if len(roles) != 1 or any(a != "--manual-only" for a in extra) or (extra and roles[0] != "--engine"):
        raise ValueError("usage: (--supervisor | --engine [--manual-only])")
    return {"role": roles[0][2:], "manual_only": bool(extra)}


class ProcessSupervisor:
    """spawn(args: list[str]) -> handle with wait() -> int, terminate(), kill(); `wait` returns the exit status (negative for a signal on POSIX)."""

    def __init__(self, spawn, clock_ms, sleep_ms, max_crashes=5, loop_window_ms=600_000, min_delay_ms=1000, term_timeout_ms=10_000, on_event=None):
        self.spawn, self.clock, self.sleep = spawn, clock_ms, sleep_ms
        self.max_crashes, self.loop_window, self.min_delay, self.term_timeout = max_crashes, loop_window_ms, min_delay_ms, term_timeout_ms
        self.on_event = on_event or (lambda name: None)        # names only, never text
        self.window = K.CrashWindow()
        self.crash_times = []
        self.starts = 0
        self._stop = False
        self._proc = None
        self._lock = threading.Lock()

    def reset(self):
        """The user's re-enable: the latch is cleared (the next start has no --manual-only)."""
        self.window.reset()

    def stop(self):
        """The user quits: the child gets terminate, then kill after term_timeout_ms; no restart follows."""
        with self._lock:
            self._stop = True
            p = self._proc
        if p is not None:
            try:
                p.terminate()
            except Exception:
                pass

    def run(self) -> int:
        while True:
            with self._lock:
                if self._stop:
                    return 0
            args = ["--engine"] + (["--manual-only"] if self.window.manual_only else [])
            try:
                proc = self.spawn(args)
            except Exception:
                self.on_event("spawn_failed")
                if self._count_crash(self.clock()):
                    return EXIT_GAVE_UP
                self.sleep(max(self.min_delay, 1))
                continue
            self.starts += 1
            with self._lock:
                self._proc = proc
                stopped = self._stop
            if stopped:
                self._end(proc)
                return 0
            self.on_event("started")
            code = proc.wait()
            with self._lock:
                self._proc = None
                stopped = self._stop
            if stopped:
                self._end(proc)
                return 0
            if code == 0:
                self.on_event("clean_exit")
                return 0
            self.on_event("engine_crashed")
            now = self.clock()                      # one reading per crash: both windows see the same instant
            verdict = self.window.record(now)
            if verdict == "manual_only":
                self.on_event("manual_only")
            if self._count_crash(now):
                return EXIT_GAVE_UP
            self.sleep(self.min_delay)

    def _count_crash(self, now):
        self.crash_times = [t for t in self.crash_times if now - t <= self.loop_window] + [now]
        if len(self.crash_times) > self.max_crashes:
            self.on_event("gave_up")
            return True
        return False

    def _end(self, proc):
        try:
            proc.terminate()
        except Exception:
            pass
        self.sleep(0)
        try:
            proc.wait_timeout(self.term_timeout)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


class RealChild:
    """A real child process; stdin, stdout and stderr are the null device."""

    def __init__(self, argv, term_timeout_s=10):
        self.p = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
        self.term_timeout_s = term_timeout_s

    def wait(self):
        return self.p.wait()

    def terminate(self):
        if self.p.poll() is None:
            self.p.terminate()

    def kill(self):
        if self.p.poll() is None:
            self.p.kill()

    def wait_timeout(self, ms):
        try:
            self.p.wait(timeout=ms / 1000.0)
        except subprocess.TimeoutExpired:
            self.kill()
            self.p.wait()


def make_spawn(command_prefix):
    """command_prefix: the fixed argv of the engine executable, for example [exe] or [sys.executable, script]. Only the allow-listed flags are appended."""
    prefix = list(command_prefix)

    def spawn(args):
        parse_args(list(args))
        return RealChild(prefix + list(args))
    return spawn


def engine_main(argv, make_runtime, run_engine, crash_dir, version="0"):
    """The engine process: parse the flags, install the content-free crash handler, apply `--manual-only`, run, then stop in order.
    `make_runtime()` and `run_engine(runtime, worker_supervisor)` come from an OS adapter (none exists in this repository). An exception
    from the engine is reported here and ends the process with status 1 (nothing is printed) (a crash for the process supervisor)."""
    opts = parse_args(argv)
    if opts["role"] != "engine":
        raise ValueError("engine_main runs the engine role")
    rt = make_runtime()
    reporter = K.CrashReporter(crash_dir, version)
    sup = K.Supervisor(rt, reporter, lambda: _monotonic_ms())
    reporter.counters = sup.counters
    restore = reporter.install()
    try:
        if opts["manual_only"]:
            K.start_manual_only(rt)
        run_engine(rt, sup)
        return 0
    except Exception:
        # Report here, content-free, and END with status 1: re-raising after restore() would let the default hook print the exception MESSAGE.
        reporter.handle(*sys.exc_info())
        return 1
    finally:
        K.stop(rt)
        restore()


def _monotonic_ms():
    import time
    return int(time.monotonic() * 1000)
