"""AP-6 uninstall, portable part: order, checks and fail-safe rules over a fake adapter; the glue to the startup entry and the store runs on temporary places
(a fake registry, a temporary 'LaunchAgents', a temporary store directory). No real application, no real startup entry, no real process is touched."""
import os, plistlib, shutil, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lfuninstall as U, lfautostart as A, lfstore as S

CHECKS = 0
def T(c, w):
    global CHECKS
    CHECKS += 1
    if not c: raise AssertionError(w)

class Fake:
    def __init__(self, procs=("engine:1", "supervisor:2"), stubborn=0, forever=(), startup="removed", app="removed", data=(["settings.json"], []), data_fn=None):
        self.procs = list(procs); self.stubborn = stubborn; self.forever = set(forever); self.log = []
        self.startup, self.app, self.data, self.data_fn = startup, app, data, data_fn
        self.stops = 0; self.fail = set(); self.bad_list = False; self.on_end = None; self.sleeps = []
    def _f(self, n):
        self.log.append(n)
        if n in self.fail: raise RuntimeError("boom")
    def processes(self):
        self.log.append("list")
        if "list" in self.fail: raise RuntimeError("boom")
        return "garbage" if self.bad_list else list(self.procs)
    def stop(self, ids):
        self._f("stop"); self.stops += 1
        if self.stops > self.stubborn:                       # the processes end after `stubborn` asks, except the forever ones
            ended = [p for p in self.procs if p not in self.forever]
            self.procs = [p for p in self.procs if p in self.forever]
            if ended and self.on_end: self.on_end()          # a process that ends writes its files (the engine saves at its end)
    def sleep(self, ms): self.sleeps.append(ms)
    def remove_startup(self): self._f("startup"); return self.startup
    def remove_application(self): self._f("app"); return self.app
    def remove_user_data(self):
        self._f("data")
        return self.data_fn() if self.data_fn else self.data

def idx(log, n): return log.index(n)
# ---- the normal run: order, and the result carries codes only
a = Fake(); r = U.uninstall(a, delete_data=True)
T(r["result"] == "complete" and r["leftovers"] == [] and r["steps"] == {"startup": "ok", "processes": "ok", "application": "ok", "data": "ok", "final_check": "ok"}, f"complete: {r}")
T(a.log.index("startup") < a.log.index("stop") < a.log.index("app") < a.log.index("data") and a.log[-1] == "list", f"the order: startup, stop, application, data, final check: {a.log}")
T(r["rounds"] == 2 and a.stops == 1 and a.sleeps == [200], "one ask, then a look: no process left")
T(set(r) == {"result", "steps", "leftovers", "rounds"} and all(isinstance(x, (str, int, list, dict)) for x in r.values()) and "engine:1" not in repr(r), "the result names no process, no path, no file")
# data only on request
a = Fake(); r = U.uninstall(a)
T("data" not in a.log and r["steps"]["data"] == "not_run" and r["result"] == "complete" and "app" in a.log and r["steps"]["application"] == "ok", "no data is touched unless requested; the application is removed anyway")
# nothing running: no stop at all
a = Fake(procs=()); r = U.uninstall(a, True)
T("stop" not in a.log and r["steps"]["processes"] == "absent" and r["result"] == "complete" and r["rounds"] == 1, "no process: no stop is asked")
# a stubborn process: asked again, bounded
a = Fake(stubborn=3); r = U.uninstall(a, True)
T(r["result"] == "complete" and a.stops == 4, f"a process that needs four asks is stopped in the fourth round ({a.stops})")
a = Fake(stubborn=99); r = U.uninstall(a, True, max_rounds=3)
T(a.stops == 3 and r["result"] == "incomplete" and r["steps"]["processes"] == "failed" and "process_running" in r["leftovers"] and len(a.sleeps) == 3, "a process that never ends: bounded asks, incomplete")
T("app" not in a.log and "data" not in a.log and r["steps"]["application"] == "not_run" and r["steps"]["data"] == "not_run" and "application" in r["leftovers"] and "user_data" in r["leftovers"], "while a process runs nothing is deleted")
T(a.log.index("startup") < a.log.index("stop"), "the startup entry is removed first even then")
a = Fake(forever=("engine:1",)); r = U.uninstall(a); T(r["result"] == "incomplete" and "process_running" in r["leftovers"] and "app" not in a.log, "one of two processes stays: no deletion")
# the list cannot be read: it cannot be claimed that none is left
a = Fake(); a.bad_list = True; r = U.uninstall(a, True)
T(r["steps"]["processes"] == "unverified" and "process_unverified" in r["leftovers"] and "app" not in a.log and "data" not in a.log and r["result"] == "incomplete", "an unreadable process list: unverified, nothing deleted")
for bad in (None, "x", [1], ["a b"], ["../x"], ["x" * 65], [""], ["a\n"], ["ok"] * 257, 5, {"a": 1}):
    a = Fake(); a.procs = bad; a.processes = (lambda b=bad: b)
    r = U.uninstall(a, True); T(r["result"] == "incomplete" and r["steps"]["processes"] in ("unverified", "failed") and "app" not in a.log, f"a bad process list is refused: {bad!r}"[:80])
for bad in ([f"p{i}" for i in range(257)], ["a\n"], ["a b"]):
    a = Fake(procs=bad); r = U.uninstall(a, True)
    T(r["result"] == "incomplete" and r["steps"]["processes"] == "unverified" and a.stops == 0 and "app" not in a.log, f"a process list that is too long or has a bad identifier is refused even when its processes would end: {bad[0]!r}")
a = Fake(procs=["p%d" % i for i in range(256)]); r = U.uninstall(a, True); T(r["result"] == "complete", "256 identifiers are the limit and are allowed")
a = Fake(); a.fail.add("list"); r = U.uninstall(a, True)
T(r["steps"]["processes"] == "unverified" and r["result"] == "incomplete" and "app" not in a.log, "a failing process query: unverified")
a = Fake(); a.fail.add("stop"); r = U.uninstall(a, True)
T(r["result"] == "incomplete" and "app" not in a.log and "data" not in a.log and "process_unverified" in r["leftovers"], "a failing stop: nothing is deleted")
# the final check
class Late(Fake):
    """a helper appears after the application is removed"""
    def remove_application(self): r = super().remove_application(); self.procs = ["helper:9"]; return r
a = Late(); r = U.uninstall(a, True)
T(r["result"] == "incomplete" and r["steps"]["final_check"] == "failed" and "process_running" in r["leftovers"], "a process found at the end makes the result incomplete")
class Blind(Fake):
    def remove_application(self): r = super().remove_application(); self.bad_list = True; return r
a = Blind(); r = U.uninstall(a, True); T(r["result"] == "incomplete" and r["steps"]["final_check"] == "unverified" and "process_unverified" in r["leftovers"], "an unreadable final check is not a success")
# one failing step does not stop the others
a = Fake(); a.fail.add("startup"); r = U.uninstall(a, True)
T(r["steps"]["startup"] == "failed" and r["steps"]["application"] == "ok" and r["steps"]["data"] == "ok" and r["leftovers"] == ["startup_entry"] and r["result"] == "incomplete", "a failing startup removal is reported and the rest goes on")
a = Fake(); a.fail.add("app"); r = U.uninstall(a, True)
T(r["steps"]["application"] == "failed" and r["steps"]["data"] == "not_run" and "data" not in a.log and r["leftovers"] == ["application", "user_data"] and r["result"] == "incomplete", "a failing application removal: the data, an irreversible step, is not deleted (my reading, open)")
a = Fake(app="absent"); r = U.uninstall(a, True); T(r["steps"]["data"] == "ok", "an application already gone does not hold the data back")
a = Fake(); a.fail.add("data"); r = U.uninstall(a, True); T(r["steps"]["data"] == "failed" and r["leftovers"] == ["user_data"] and r["steps"]["final_check"] == "ok", "a failing data removal is reported")
for bad in ("yes", None, "", 1, "REMOVED"):
    a = Fake(startup=bad, app=bad); r = U.uninstall(a, True)
    T(r["steps"]["startup"] == "failed" and r["steps"]["application"] == "failed", f"an answer that is not removed/absent is a failure: {bad!r}")
for bad in (None, "x", (["a"],), ([], None), (None, []), 5, ("ab", [])):
    a = Fake(data=bad); r = U.uninstall(a, True); T(r["steps"]["data"] == "failed" and "user_data" in r["leftovers"], f"a data answer of a wrong shape is a failure: {bad!r}")
a = Fake(data=(["a"], ["link"])); r = U.uninstall(a, True)
T(r["steps"]["data"] == "skipped" and r["leftovers"] == ["user_data_partial"] and r["result"] == "incomplete", "what the store skipped (a link, a directory) leaves the result incomplete")
a = Fake(data=([], [])); r = U.uninstall(a, True); T(r["steps"]["data"] == "absent" and r["result"] == "complete", "no data: absent")
a = Fake(startup="absent", app="absent", procs=()); r = U.uninstall(a, True)
T(r["steps"] == {"startup": "absent", "processes": "absent", "application": "absent", "data": "ok", "final_check": "ok"} and r["result"] == "complete", "a second uninstall finds everything gone and is complete")
# ---- an interrupted uninstall leaves a state that a second run finishes (a BaseException is not swallowed, nothing is half-recorded)
class Stop(BaseException): pass
class Inter(Fake):
    def remove_application(self): self.log.append("app"); raise Stop()
a = Inter()
try: U.uninstall(a, True); T(False, "the interruption must propagate")
except Stop: T(True, "")
T("data" not in a.log and a.procs == [], "interrupted at the application step: the data was not touched, the processes are already gone")
a2 = Fake(procs=(), startup="absent"); r = U.uninstall(a2, True); T(r["result"] == "complete", "a second run after the interruption completes")
# an adapter that fails in stop() or sleep() leaves nothing deleted
class BadSleep(Fake):
    def sleep(self, ms): raise RuntimeError("x")
a = BadSleep(); r = U.uninstall(a, True); T(r["result"] == "incomplete" and "app" not in a.log and "data" not in a.log, "a failing sleep: nothing is deleted")
# the processes are asked once per round, not twice
a = Fake(stubborn=2); U.uninstall(a); T(a.stops == 3 and len([x for x in a.log if x == "stop"]) == 3, "one stop request per round")
# ---- data is removed only after the processes have ended: a process writes its files again when it ends
d = tempfile.mkdtemp(prefix="lfun_"); sp = os.path.join(d, "settings.json"); st = S.Store(sp, S.TestOnlyCipher(b"key"), allow_test_cipher=True)
state = st.load(); st.save(state); T(os.path.exists(sp), "the store file exists")
def rewrite(): st.save(st.load())                                   # the engine saves its state at its end
a = Fake(data_fn=U.data_of_store(st)); a.on_end = rewrite
r = U.uninstall(a, True)
T(r["result"] == "complete" and not os.path.exists(sp) and os.listdir(d) == [], f"the data stays deleted although the process wrote it again when it ended ({os.listdir(d)})")
# the same data with a store of an extra link
st.save(st.load()); victim = os.path.join(d, "victim"); open(victim, "w").write("keep"); os.symlink(victim, sp + ".tmp")
r = U.uninstall(Fake(procs=(), data_fn=U.data_of_store(st)), True)
T(r["steps"]["data"] == "skipped" and open(victim).read() == "keep" and not os.path.exists(sp), "a link with the name of a temporary file is skipped, its target is kept, the result is incomplete")
shutil.rmtree(d, ignore_errors=True)
# ---- the startup glue on temporary places
tmp = tempfile.mkdtemp(prefix="lfun_"); agents = os.path.join(tmp, "LaunchAgents"); LAB = "com.example.layoutcorrector"; EXE = "/Applications/LayoutCorrector.app/Contents/MacOS/lc-supervisor"
A.write_launch_agent(agents, A.launch_agent(LAB, EXE))
f = U.startup_launchd(agents, LAB)
T(f() == "removed" and f() == "absent" and os.listdir(agents) == [], "the launchd description is removed once, then absent")
plistlib.dump({"Label": LAB, "ProgramArguments": ["/bin/sh"]}, open(os.path.join(agents, LAB + ".plist"), "wb"))
T(f() == "absent" and os.listdir(agents) == [LAB + ".plist"], "a description the user changed is not removed")
try: U.startup_launchd(os.path.expanduser("~/Library/LaunchAgents"), LAB)(); T(False, "the real directory is refused")
except A.AutostartError: T(True, "")
a = Fake(); a.remove_startup = U.startup_launchd(os.path.expanduser("~/Library/LaunchAgents"), LAB); r = U.uninstall(a, False)
T(r["steps"]["startup"] == "failed" and r["leftovers"] == ["startup_entry"], "a refusal of the glue is a failed step, not a crash")
reg = A.MemoryRegistry(); WEXE = "C:\\Program Files\\LC\\lc.exe"
g = U.startup_run_value(reg, WEXE); T(g() == "absent", "no value: absent")
A.install_run_value(reg, WEXE); T(g() == "removed" and reg.values == {} and g() == "absent", "the Run value is removed once")
reg.set(A.RUN_VALUE, "C:\\Other\\x.exe"); T(g() == "absent" and reg.values == {A.RUN_VALUE: "C:\\Other\\x.exe"}, "a value someone else changed is left")
shutil.rmtree(tmp, ignore_errors=True)
print(f"OK ({CHECKS} uninstall checks; fake adapter, temporary places only; the installer, the package, a real startup entry and real processes are NOT written / NOT RUN)")
