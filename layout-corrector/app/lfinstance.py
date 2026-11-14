"""RT-19: at most one instance per user session. A second start exits at once; when the lock cannot be established the engine stays OFF.

Portable part: the decision logic and a POSIX file-lock backend (fcntl.flock on a file inside a directory the CALLER names; the lock dies with the process,
including kill -9, so a crash never leaves a stale lock). The Windows backend (a named mutex in the `Local\\` namespace, which is per session) is written and
COMPILED ONLY. The POSIX file lock is per USER, not per login session: that is a divergence from "per-user session" on systems with several sessions of one
user (reported in audit/AP7_RT19_readings.md). The lock file carries no content: no process id, no text, no path of the user.
"""
import os
import stat
import sys

HELD, ALREADY_RUNNING, UNAVAILABLE = "HELD", "ALREADY_RUNNING", "UNAVAILABLE"
LOCK_NAME = "instance.lock"
EXIT_ALREADY_RUNNING = 0          # a second start is not an error: exit at once, quietly


class Lock:
    """Result of acquire(): `.state` is HELD, ALREADY_RUNNING or UNAVAILABLE; `.release()` is safe to call twice."""
    def __init__(self, state, release=lambda: None, why=""):
        self.state, self._release, self.why = state, release, why     # `why`: a short code, never a path or text

    def release(self):
        r, self._release = self._release, (lambda: None)
        r()


def acquire_posix(directory):
    """flock on `directory/instance.lock`. The directory must exist, be a real directory (not a link), be owned by the caller and not writable by
    group or others; the file is opened without following links, created 0600, must be a regular file owned by the caller. Any failure to establish
    the lock is UNAVAILABLE (never 'maybe held'): the engine stays OFF."""
    try:
        import fcntl
    except ImportError:
        return Lock(UNAVAILABLE, why="no_fcntl")
    fd = None
    try:
        dst = os.lstat(directory)
        if not stat.S_ISDIR(dst.st_mode) or dst.st_uid != os.geteuid() or dst.st_mode & 0o022:
            return Lock(UNAVAILABLE, why="directory")
        path = os.path.join(directory, LOCK_NAME)
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        fd = os.open(path, flags, 0o600)
        fst = os.fstat(fd)
        if not stat.S_ISREG(fst.st_mode) or fst.st_uid != os.geteuid():
            os.close(fd)
            return Lock(UNAVAILABLE, why="file")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, PermissionError) as e:
            os.close(fd)
            return Lock(ALREADY_RUNNING if isinstance(e, BlockingIOError) else UNAVAILABLE, why="held" if isinstance(e, BlockingIOError) else "flock")
        held = fd

        def release():
            try:
                fcntl.flock(held, fcntl.LOCK_UN)
            finally:
                os.close(held)
        return Lock(HELD, release)
    except OSError:
        if fd is not None:
            try: os.close(fd)
            except OSError: pass
        return Lock(UNAVAILABLE, why="os_error")


def acquire_windows(name):  # pragma: no cover - compiled only, never run by the tests
    """Named mutex `Local\\<name>` (Local\\ is the per-session namespace). ERROR_ALREADY_EXISTS (183) after CreateMutexW means another instance."""
    import ctypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateMutexW.restype = ctypes.c_void_p
    k32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
    k32.CloseHandle.argtypes = [ctypes.c_void_p]
    h = k32.CreateMutexW(None, 0, "Local\\" + name)
    err = ctypes.get_last_error()
    if not h:
        return Lock(UNAVAILABLE, why="create")
    if err == 183:
        k32.CloseHandle(h)
        return Lock(ALREADY_RUNNING, why="held")
    return Lock(HELD, lambda: k32.CloseHandle(h))


def start_gate(acquire, on_second=lambda: None):
    """The startup decision. `acquire()` returns a Lock. Returns (proceed, instance_ok, lock):
    HELD -> (True, True, lock); ALREADY_RUNNING -> exit at once (False, False, lock), `on_second()` is called; anything else, or an exception from the
    backend -> (True, False, lock): the process may run but the engine stays OFF."""
    try:
        lock = acquire()
        state = lock.state
    except Exception:
        return True, False, Lock(UNAVAILABLE, why="exception")
    if state == HELD:
        return True, True, lock
    if state == ALREADY_RUNNING:
        on_second()
        return False, False, lock
    return True, False, lock


def apply_to_runtime(runtime, instance_ok):
    """Engine OFF unless this process holds the lock. One notice, never text."""
    runtime.instance_ok = bool(instance_ok)
    if not instance_ok:
        runtime.notices.append(("instance_lock_unavailable", ""))
    runtime.apply_mode()
