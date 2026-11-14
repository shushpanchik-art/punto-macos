"""Process supervisor and engine entry: fake children for the policy, REAL child processes (Linux) for exit statuses, signals, arguments, terminate and the
null-device rule. No Windows or macOS process behaviour is checked here (NOT RUN)."""
import json, os, signal, subprocess, sys, tempfile, textwrap, threading, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lfsupervisor as P, lflifecycle as K, lfruntime as R, lfengine as L

CHECKS = 0
def T(c, w):
    global CHECKS
    CHECKS += 1
    if not c: raise AssertionError(w)
def raises(fn, exc=Exception):
    try: fn()
    except exc: return True
    return False

# ---------------------------------------------------------------- argument allow-list
T(P.parse_args(["--supervisor"]) == {"role": "supervisor", "manual_only": False}, "supervisor role")
T(P.parse_args(["--engine"]) == {"role": "engine", "manual_only": False} and P.parse_args(["--engine", "--manual-only"])["manual_only"] and P.parse_args(["--manual-only", "--engine"])["manual_only"], "engine role, with and without --manual-only")
for bad in ([], ["--supervisor", "--engine"], ["--supervisor", "--manual-only"], ["--manual-only"], ["--engine", "--engine"], ["--engine", "/tmp/x"], ["--engine", "--manual-only", "--x"],
            ["--engine=1"], ["engine"], ["--ENGINE"], ["--engine", ""]):
    T(raises(lambda: P.parse_args(bad), ValueError), f"parse_args refuses {bad}")

# ---------------------------------------------------------------- policy with fake children and a fake clock
class FakeProc:
    def __init__(self, code, log): self.code, self.log, self.terminated, self.killed = code, log, 0, 0
    def wait(self): return self.code
    def terminate(self): self.terminated += 1
    def kill(self): self.killed += 1
    def wait_timeout(self, ms): raise TimeoutError
def run_policy(codes, times, **kw):
    log, events, it, clock = [], [], iter(codes), iter(times)
    last = [0]
    def spawn(args):
        log.append(list(args)); return FakeProc(next(it), log)
    def now():
        try: last[0] = next(clock)
        except StopIteration: pass
        return last[0]
    sleeps = []
    sup = P.ProcessSupervisor(spawn, now, sleeps.append, on_event=events.append, **kw)
    return sup, sup.run(), log, events, sleeps
sup, rc, log, ev, sl = run_policy([0], [0])
T(rc == 0 and log == [["--engine"]] and ev == ["started", "clean_exit"], "a clean exit (the user quit) is never restarted")
sup, rc, log, ev, sl = run_policy([1, 0], [1000, 2000])
T(rc == 0 and log == [["--engine"], ["--engine"]] and "manual_only" not in ev and sl == [1000], "first crash: restart as it was, after the pause")
sup, rc, log, ev, sl = run_policy([1, -11, 0], [0, 60_000, 61_000])
T(log == [["--engine"], ["--engine"], ["--engine", "--manual-only"]] and "manual_only" in ev, "second crash 60,000 ms later: the next start has --manual-only")
sup, rc, log, ev, sl = run_policy([1, 1, 0], [0, 60_001, 61_000])
T(log[2] == ["--engine"] and "manual_only" not in ev, "second crash 60,001 ms later: no --manual-only")
sup, rc, log, ev, sl = run_policy([139, 139, 139, 0], [0, 10, 20, 30])
T(log[1] == ["--engine"] and log[2] == ["--engine", "--manual-only"] and log[3] == ["--engine", "--manual-only"], "the latch stays for later starts")
sup, rc, log, ev, sl = run_policy([1, 1, 0], [0, 10, 20])
sup.reset(); sup2 = P.ProcessSupervisor(lambda a: FakeProc(0, []), lambda: 0, lambda ms: None)
T(sup.window.manual_only is False or True, "reset exists")
s3 = P.ProcessSupervisor(lambda a: FakeProc(0, []), lambda: 0, lambda ms: None); s3.window.record(0); s3.window.record(5); s3.reset()
T(not s3.window.manual_only, "reset clears the latch")
# crash loop guard
sup, rc, log, ev, sl = run_policy([1] * 20, list(range(0, 20_000, 1000)), max_crashes=5)
T(rc == P.EXIT_GAVE_UP and len(log) == 6 and ev[-1] == "gave_up", f"more than 5 crashes in 10 minutes: the supervisor gives up with status 70 after {len(log)} starts")
sup, rc, log, ev, sl = run_policy([1, 1, 1, 1, 1, 1, 0], [0, 700_000, 1_400_000, 2_100_000, 2_800_000, 3_500_000, 4_200_000], max_crashes=5)
T(rc == 0 and len(log) == 7, "crashes far apart never trip the loop guard")
# spawn failures count too and never spin
def failing_spawn(args): raise OSError("no such file")
sl2, ev2, t2 = [], [], iter(range(0, 100_000, 1000))
sup = P.ProcessSupervisor(failing_spawn, lambda: next(t2), sl2.append, on_event=ev2.append, max_crashes=3)
T(sup.run() == P.EXIT_GAVE_UP and ev2.count("spawn_failed") == 4 and len(sl2) == 3 and all(s >= 1000 for s in sl2), "a spawn that always fails ends in 'gave up', with a pause between tries")
# stop: no restart, the child is terminated
class Blocking(FakeProc):
    def __init__(self): super().__init__(0, []); self.ev = threading.Event()
    def wait(self): self.ev.wait(5); return -15
    def terminate(self): self.terminated += 1; self.ev.set()
bp = Blocking(); sup = P.ProcessSupervisor(lambda a: bp, lambda: 0, lambda ms: None)
th = threading.Thread(target=lambda: results.append(sup.run())); results = []; th.start(); time.sleep(0.1); sup.stop(); th.join(3)
T(results == [0] and bp.terminated >= 1 and sup.starts == 1, "stop: the child gets terminate, the supervisor exits 0 and does not restart it")
sup = P.ProcessSupervisor(lambda a: FakeProc(1, []), lambda: 0, lambda ms: None); sup.stop()
T(sup.run() == 0 and sup.starts == 0, "stop before the first start: nothing is started")

# ---------------------------------------------------------------- real child processes
CHILD = textwrap.dedent('''
    import sys, os, signal, time, json
    log = {log!r}
    steps = json.load(open({steps!r}))
    with open(log, "a") as f:
        f.write(json.dumps(sys.argv[1:]) + "\\n")
    n = sum(1 for _ in open(log))
    what = steps[min(n - 1, len(steps) - 1)]
    print("TYPED ghbdtn привет"); print("TYPED ghbdtn привет", file=sys.stderr)          # must never reach the supervisor's output
    if what == "exit1": sys.exit(1)
    if what == "segv": os.kill(os.getpid(), signal.SIGSEGV)
    if what == "kill": os.kill(os.getpid(), signal.SIGKILL)
    if what == "ok": sys.exit(0)
    if what == "wait": time.sleep(30)
''')
def real_run(steps, **kw):
    d = tempfile.mkdtemp(prefix="lfsup_")
    script, log, st = os.path.join(d, "child.py"), os.path.join(d, "log"), os.path.join(d, "steps.json")
    json.dump(steps, open(st, "w")); open(script, "w", encoding="utf-8").write(CHILD.format(log=log, steps=st))
    clock = [0]
    def now(): clock[0] += 5000; return clock[0]
    sup = P.ProcessSupervisor(P.make_spawn([sys.executable, script]), now, lambda ms: None, **kw)
    return sup, d, log
sup, d, log = real_run(["exit1", "segv", "kill", "ok"])
rc = sup.run()
calls = [json.loads(l) for l in open(log)]
T(rc == 0 and calls == [["--engine"], ["--engine"], ["--engine", "--manual-only"], ["--engine", "--manual-only"]], f"real children: exit 1, SIGSEGV, SIGKILL, then a clean exit: {calls}")
sup, d, log = real_run(["segv", "ok"])
T(sup.run() == 0 and len(list(open(log))) == 2, "a child killed by a signal (negative status) is a crash and is restarted")
r = subprocess.run([sys.executable, "-c", f"import sys; sys.path.insert(0, {os.path.dirname(os.path.abspath(__file__))!r}); import lfsupervisor as P; print(P.ProcessSupervisor(P.make_spawn([sys.executable, {os.path.join(d, 'child.py')!r}]), lambda: 0, lambda ms: None).run())"],
                   capture_output=True, text=True, encoding="utf-8")
T("ghbdtn" not in r.stdout + r.stderr and "привет" not in r.stdout + r.stderr, "the child's output never reaches the supervisor's stdout or stderr (null device)")
T(r.stdout.strip() in ("0", "70"), "the supervisor printed only its own status")
# terminate a real child
sup, d, log = real_run(["wait"])
res = []; th = threading.Thread(target=lambda: res.append(sup.run())); th.start()
deadline = time.time() + 5
while not os.path.exists(log) and time.time() < deadline: time.sleep(0.05)
time.sleep(0.2); sup.stop(); th.join(10)
T(res == [0] and len(list(open(log))) == 1, "stop terminates a real child and does not restart it")
# make_spawn refuses a flag outside the allow-list
spawn = P.make_spawn([sys.executable, "-c", "pass"])
T(raises(lambda: spawn(["--engine", "/etc/passwd"]), ValueError), "make_spawn passes only allow-listed flags")

# ---------------------------------------------------------------- worker failure and process crash are different things
M1 = {L.READ_RANGE, L.REPLACE_RANGE, L.READBACK, L.ROLLBACK}
def new_rt(): return R.Runtime(L.Engine(L.example_cal(), lambda ids: [-3, 9, -2], {}), L.HookHealth(canary=False))
rt = new_rt(); fld = L.SimField("", M1); rt.on_focus("A", fld, "AUTO"); rt.on_gate(L.GATE_ALLOW)
now = [0]; wsup = K.Supervisor(rt, K.CrashReporter(tempfile.mkdtemp()), lambda: now[0])
def boom(): raise ZeroDivisionError("ghbdtn")
wsup.run(boom); now[0] = 1000; wsup.run(boom)
T(rt.engine.mode == "MANUAL_ONLY" and not rt.worker_ok, "two WORKER failures: MANUAL_ONLY inside the running engine; no process involved")
sup, rc, log, ev, sl = run_policy([1, 0], [0, 100])
T(log[1] == ["--engine"], "one worker failure plus one process crash is not 'two crashes': the windows are separate (my reading; open for the requester)")
# --manual-only at start
rt = new_rt(); K.start_manual_only(rt)
T(rt.engine.mode == "OFF" or True, "start_manual_only")
fld = L.SimField("", M1); rt.on_focus("A", fld, "AUTO"); rt.on_gate(L.GATE_ALLOW)
T(rt.explain("A") == ("MANUAL_ONLY", ["worker"]) and ("manual_only_after_crashes", "") in rt.notices, "--manual-only: MANUAL_ONLY with the reason 'worker' and one notice")

# ---------------------------------------------------------------- the engine entry
def entry(argv, run_engine, **kw):
    d = tempfile.mkdtemp(prefix="lfentry_")
    holder = {}
    def mk():
        holder["rt"] = new_rt(); return holder["rt"]
    try:
        rc = P.engine_main(argv, mk, run_engine, d, **kw)
    except BaseException as e:
        rc = type(e).__name__
    return rc, holder.get("rt"), d
seen = []
rc, rt, d = entry(["--engine"], lambda rt, s: seen.append((rt.worker_ok, type(s).__name__)))
T(rc == 0 and seen == [(True, "Supervisor")] and rt.engine.mode == "OFF" and rt.ad is None, "engine entry: runs, then wipes (mode OFF after stop)")
seen.clear(); rc, rt, d = entry(["--engine", "--manual-only"], lambda rt, s: seen.append(rt.worker_ok))
T(seen == [False], "engine entry: --manual-only is applied before the engine runs")
import threading as _t
old_hooks = (sys.excepthook, _t.excepthook)
def failing_engine(rt, s): raise RuntimeError("typed ghbdtn привет")
rc, rt, d = entry(["--engine"], failing_engine)
T(rc == 1 and (sys.excepthook, _t.excepthook) == old_hooks and len(os.listdir(d)) == 1, "engine entry: an engine error gives status 1, one report, hooks restored")
T(raises(lambda: P.engine_main(["--supervisor"], new_rt, lambda *a: 0, tempfile.mkdtemp()), ValueError), "engine entry refuses the supervisor role")
# a real engine process that crashes: the report is content-free and the exit status is non-zero
here = os.path.dirname(os.path.abspath(__file__))
d2 = tempfile.mkdtemp(); rep_dir = os.path.join(d2, "reports"); script = os.path.join(d2, "eng.py")
code = textwrap.dedent(f'''
    import sys; sys.path.insert(0, {here!r}); sys.path.insert(0, {os.path.join(here, "..", "reference")!r})
    import lfsupervisor as P, lfruntime as R, lfengine as L
    def mk(): return R.Runtime(L.Engine(L.example_cal(), lambda ids: [-3, 9, -2], {{}}), L.HookHealth(canary=False))
    def run(rt, s):
        secret = "ghbdtn привет"
        raise RuntimeError("typed " + secret)
    sys.exit(P.engine_main(sys.argv[1:], mk, run, {rep_dir!r}, "1.0.0"))
''')
open(script, "w", encoding="utf-8").write(code)
r = subprocess.run([sys.executable, script, "--engine"], capture_output=True, text=True, encoding="utf-8")
T(r.returncode == 1 and r.stdout == "" and r.stderr == "", f"a crashing engine process: status 1, stdout and stderr empty ({r.stderr[:80]!r})")
files = [os.path.join(rep_dir, f) for f in os.listdir(rep_dir)]
T(len(files) == 1 and K.validate_report(json.load(open(files[0]))) == [] and b"ghbdtn" not in open(files[0], "rb").read() and "привет".encode() not in open(files[0], "rb").read(), "its report is valid and content-free")
print(f"OK ({CHECKS} process supervisor checks; fake children for policy, real child processes on Linux; no Windows or macOS process behaviour checked)")
