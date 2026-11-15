"""AP-6 uninstall, portable part: the ORDER and the checks of an uninstall over injected adapters. No file of the real application, no real startup entry and no
real process is touched here; the adapters decide what the real operations are (and are NOT written: the installer, the package, the signing).

Specification (13.9 AP-6): "A signed installer or package, per user and without elevation where the OS allows. The uninstaller removes the application, its login
item or startup entry and, on request, all user data, and leaves no hook or helper process running". AP-5: "Delete all data" removes settings, exceptions and
diagnostics. The release checklist also names "uninstall".

The order (my reading, audit/AP7_RT19_readings.md section 14): 1 the startup entry (so that nothing starts again whatever happens later), 2 stop every engine,
supervisor and helper process and CHECK that none is left, 3 the application files, 4 the user data (only on request, and only when no process is left, because a
running engine writes its files again at its end), 5 a final check for processes. A step that fails does not stop the others, except that nothing is deleted while
a process may still run or while that cannot be told (the fail-safe direction). The result names codes only: no path, no file name, no text.

Adapter (a fake in the tests): processes() -> list of opaque ids; stop(ids) asks them to end; remove_startup() and remove_application() -> 'removed' | 'absent';
remove_user_data() -> (deleted, skipped) lists of names; sleep(ms)."""
import re

OK, ABSENT, SKIPPED, FAILED, NOT_RUN, UNVERIFIED = "ok", "absent", "skipped", "failed", "not_run", "unverified"
_ID = re.compile(r"[A-Za-z0-9_.:-]{1,64}")


class _Unreadable(Exception):
    pass


def _ids(v):
    if not isinstance(v, (list, tuple)) or len(v) > 256 or not all(isinstance(x, str) and _ID.fullmatch(x) for x in v):
        raise _Unreadable()
    return list(v)


def _simple(fn):
    r = fn()
    if r == "removed":
        return OK
    if r == "absent":
        return ABSENT
    raise ValueError("answer")


def _process_check(ad):
    """OK when none is left; FAILED when some are; UNVERIFIED when the list cannot be read or the query fails."""
    try:
        return FAILED if _ids(ad.processes()) else OK
    except Exception:
        return UNVERIFIED


def uninstall(ad, delete_data=False, max_rounds=5, wait_ms=200):
    """Returns {'result': 'complete' | 'incomplete', 'steps': {...}, 'leftovers': [codes], 'rounds': n}. Never raises for an adapter failure."""
    steps = {"startup": NOT_RUN, "processes": NOT_RUN, "application": NOT_RUN, "data": NOT_RUN, "final_check": NOT_RUN}
    left = []
    rounds = 0

    def run(name, fn, code):
        try:
            steps[name] = fn()
        except Exception:
            steps[name] = FAILED
            left.append(code)

    run("startup", lambda: _simple(ad.remove_startup), "startup_entry")

    # 2. processes: ask, look again, a bounded number of times
    try:
        for rounds in range(1, max_rounds + 1):
            ids = _ids(ad.processes())
            if not ids:
                steps["processes"] = ABSENT if rounds == 1 else OK
                break
            ad.stop(ids)
            ad.sleep(wait_ms)
        else:
            steps["processes"] = _process_check(ad)
    except Exception:
        steps["processes"] = UNVERIFIED
    if steps["processes"] not in (OK, ABSENT):
        left.append("process_running" if steps["processes"] == FAILED else "process_unverified")
        # nothing is deleted while a process may run: the application and the data stay, and the result says so
        left.append("application")
        if delete_data:
            left.append("user_data")
        return {"result": "incomplete", "steps": steps, "leftovers": left, "rounds": rounds}

    run("application", lambda: _simple(ad.remove_application), "application")
    if delete_data:
        def data():
            d, s = ad.remove_user_data()
            if not (isinstance(d, (list, tuple)) and isinstance(s, (list, tuple))):
                raise ValueError("answer")
            if s:
                left.append("user_data_partial")
                return SKIPPED
            return OK if d else ABSENT
        run("data", data, "user_data")
    steps["final_check"] = _process_check(ad)
    if steps["final_check"] != OK:
        left.append("process_running" if steps["final_check"] == FAILED else "process_unverified")
    return {"result": "complete" if not left else "incomplete", "steps": steps, "leftovers": left, "rounds": rounds}


# -- glue to the portable parts that already exist (used by the real adapters; the tests run them on temporary places) ----------------------------
def startup_launchd(directory, label, allow_real=False):
    import lfautostart as A
    return lambda: "removed" if A.remove_launch_agent(directory, label, allow_real) else "absent"


def startup_run_value(backend, exe_path):
    import lfautostart as A
    return lambda: "removed" if A.uninstall_run_value(backend, exe_path) else "absent"


def data_of_store(store):
    return store.delete_all
