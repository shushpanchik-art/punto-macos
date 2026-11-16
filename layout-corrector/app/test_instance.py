"""RT-19 portable part: start decision, POSIX file lock (real second processes on Linux), runtime stays OFF without the lock. The Windows mutex
backend is compiled only; "start two copies, type 1,000 words" on a real OS is NOT RUN."""
import os, stat, subprocess, sys, tempfile, textwrap, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lfinstance as I, lfruntime as R, lfengine as L
CHECKS = 0
def T(c, w):
    global CHECKS
    CHECKS += 1
    if not c: raise AssertionError(w)
here = os.path.dirname(os.path.abspath(__file__))
def newdir(mode=0o700):
    d = tempfile.mkdtemp(prefix="lfinst_"); os.chmod(d, mode); return d

# ---- the decision (fake backends)
calls = []
p, ok, lk = I.start_gate(lambda: I.Lock(I.HELD, lambda: calls.append("rel")))
T((p, ok) == (True, True) and lk.state == I.HELD, "HELD: proceed, the instance runs")
lk.release(); lk.release(); T(calls == ["rel"], "release runs once")
seen = []
p, ok, lk = I.start_gate(lambda: I.Lock(I.ALREADY_RUNNING), on_second=lambda: seen.append(1))
T((p, ok) == (False, False) and seen == [1], "ALREADY_RUNNING: the second start exits at once")
p, ok, lk = I.start_gate(lambda: I.Lock(I.UNAVAILABLE, why="directory"))
T((p, ok) == (True, False), "UNAVAILABLE: the process runs, the engine does not")
def boom(): raise RuntimeError("x")
p, ok, lk = I.start_gate(boom); T((p, ok, lk.state) == (True, False, I.UNAVAILABLE), "a backend exception is UNAVAILABLE, never 'held'")
p, ok, lk = I.start_gate(lambda: I.Lock("weird")); T((p, ok) == (True, False), "an unknown state is not a lock")
p, ok, lk = I.start_gate(lambda: None); T((p, ok) == (True, False), "a missing lock object is not a lock")

# ---- POSIX lock, same process
d = newdir(); a = I.acquire_posix(d)
T(a.state == I.HELD and os.listdir(d) == ["instance.lock"] and stat.S_IMODE(os.stat(os.path.join(d, "instance.lock")).st_mode) == 0o600 and os.path.getsize(os.path.join(d, "instance.lock")) == 0, "first: HELD, file 0600, empty (no pid, no text)")
b = I.acquire_posix(d); T(b.state == I.ALREADY_RUNNING, "second while held: ALREADY_RUNNING")
a.release(); c = I.acquire_posix(d); T(c.state == I.HELD, "after release the lock can be taken again"); c.release()
T(all(I.acquire_posix(newdir(m)).state == I.UNAVAILABLE for m in (0o775, 0o770, 0o777, 0o702, 0o720)), "a directory writable by group or others is refused")
T(I.acquire_posix(os.path.join(d, "missing")).state == I.UNAVAILABLE, "a missing directory is UNAVAILABLE (nothing is created)")
T(not os.path.exists(os.path.join(d, "missing")), "and was not created")
f = os.path.join(d, "afile"); open(f, "w").close(); T(I.acquire_posix(f).state == I.UNAVAILABLE, "a file in place of the directory")
ld = newdir(); os.symlink(d, os.path.join(ld, "lnk")); T(I.acquire_posix(os.path.join(ld, "lnk")).state == I.UNAVAILABLE, "a link in place of the directory")
sd = newdir(); victim = os.path.join(sd, "victim"); open(victim, "w").write("keep"); os.symlink(victim, os.path.join(sd, "instance.lock"))
T(I.acquire_posix(sd).state == I.UNAVAILABLE and open(victim).read() == "keep", "a link in place of the lock file is refused, target untouched")
dd = newdir(); os.mkdir(os.path.join(dd, "instance.lock")); T(I.acquire_posix(dd).state == I.UNAVAILABLE, "a directory in place of the lock file")
# nothing of the lock states carries a path or text
T(all(not (w and ("/" in w or " " in w)) for w in (a.why, b.why)), "the reason codes are short words")

# ---- two real processes and a kill -9
CH = textwrap.dedent('''
    import sys, time, os; sys.path.insert(0, {here!r})
    import lfinstance as I
    proceed, ok, lock = I.start_gate(lambda: I.acquire_posix({d!r}))
    print("proceed" if proceed else "exit", ok, flush=True)
    if proceed and ok: time.sleep(30)
''')
def child(d):
    s = os.path.join(tempfile.mkdtemp(), "c.py"); open(s, "w").write(CH.format(here=here, d=d))
    return subprocess.Popen([sys.executable, s], stdout=subprocess.PIPE, text=True)
d = newdir(); one = child(d); l1 = one.stdout.readline().strip()
two = child(d); t0 = time.time(); l2 = two.stdout.readline().strip(); two.wait(10)
T(l1 == "proceed True" and l2 == "exit False" and two.returncode == 0 and time.time() - t0 < 10, f"two copies: the first runs, the second exits at once with status 0 ({l1!r}, {l2!r})")
one.kill(); one.wait(); three = child(d); l3 = three.stdout.readline().strip()
T(l3 == "proceed True", "the first copy killed with -9: the lock is gone with it, a new start takes it")
three.kill(); three.wait()
bad = newdir(0o777); four = child(bad); l4 = four.stdout.readline().strip(); four.wait(10)
T(l4 == "proceed False" and four.returncode == 0, "a lock that cannot be established: the process runs, the engine is not enabled")

# ---- the runtime stays OFF without the lock
M1 = {L.READ_RANGE, L.REPLACE_RANGE, L.READBACK, L.ROLLBACK}
def rt_with(instance_ok):
    rt = R.Runtime(L.Engine(L.example_cal(), lambda ids: [-3, 9, -2], {"en": {"hello"}, "ru": {"мир"}}), L.HookHealth(canary=False))
    f = L.SimField("", M1); rt.on_focus("A", f, "AUTO"); rt.on_gate(L.GATE_ALLOW)
    I.apply_to_runtime(rt, instance_ok); return rt, f
def type_word(rt, f, w):
    for i, (ch, k) in enumerate(zip(w, L.keys_from_text(w, "en"))):
        f.type_user(ch); rt.on_hook_event(L.Event("key", k, "en", 100 + i), sig=("k", 100 + i))
    f.type_user(" "); rt.on_hook_event(L.Event("space", None, "en", 100 + len(w)))
a_rt, a_f = rt_with(True); b_rt, b_f = rt_with(False)
type_word(a_rt, a_f, "ghbdtn"); type_word(b_rt, b_f, "ghbdtn")
T(a_f.text != "ghbdtn " and "привет" in a_f.text, f"the instance that holds the lock converts ({a_f.text!r})")
T(b_f.text == "ghbdtn " and b_rt.engine.mode == "OFF" and b_rt.explain("A") == ("OFF", ["instance"]) and ("instance_lock_unavailable", "") in b_rt.notices, "without the lock: the word stays, mode OFF, reason 'instance', one notice")
b_rt.hotkey_toggle(500); T(b_f.text == "ghbdtn ", "without the lock the hotkey converts nothing either")
# one conversion per word across both: only the lock holder acts
total_a = total_b = 0
for _ in range(20):
    for rt, f in ((a_rt, a_f), (b_rt, b_f)):
        before = f.text; type_word(rt, f, "ghbdtn")
        changed = f.text != before + "ghbdtn "
        if rt is a_rt: total_a += changed
        else: total_b += changed
T(total_a == 20 and total_b == 0 and b_f.text == "ghbdtn " * 21, f"20 more words: one conversion each, all by the lock holder ({total_a}, {total_b})")
b_rt.instance_ok = True; b_rt.apply_mode()
T(b_rt.explain("A")[0] != "OFF" or "instance" not in b_rt.explain("A")[1], "when the fact changes the mode is recomputed")
# ---- fault injection (audit 5): descriptors are closed once and never leak; a failing release never raises
import errno, fcntl
def nfd(): return len(os.listdir("/proc/self/fd")) if os.path.isdir("/proc/self/fd") else None
base = nfd()
_fl = fcntl.flock
def _enolck(fd, op):
    if op & fcntl.LOCK_EX: raise OSError(errno.ENOLCK, "injected")
    return _fl(fd, op)
fcntl.flock = _enolck
try: r = I.acquire_posix(newdir())
finally: fcntl.flock = _fl
T(r.state == I.UNAVAILABLE and nfd() == base, "a flock that fails with another error: UNAVAILABLE, no descriptor left open")
_fs = os.fstat
def _eio(fd): raise OSError(errno.EIO, "injected")
os.fstat = _eio
try: r = I.acquire_posix(newdir())
finally: os.fstat = _fs
T(r.state == I.UNAVAILABLE and nfd() == base, "an fstat that fails: UNAVAILABLE, no descriptor left open")
dq = newdir(); os.mkfifo(os.path.join(dq, "instance.lock")); closes = []; _cl = os.close
def _cfail(fd): closes.append(fd); _cl(fd); raise OSError(errno.EIO, "injected")
os.close = _cfail
try: r = I.acquire_posix(dq)
finally: os.close = _cl
T(r.state == I.UNAVAILABLE and len(closes) == 1, f"a failing close of a refused lock file is not repeated ({closes})")
dh = newdir(); a = I.acquire_posix(dh); a2 = I.acquire_posix(dh); closes = []
os.close = _cfail
try: a2.release(); a.release(); r2 = True
except Exception: r2 = False
finally: os.close = _cl
T(r2 is True and a2.state == I.ALREADY_RUNNING, "a failing close in release does not raise")
dl = newdir(); a = I.acquire_posix(dl)
def _unfail(fd, op):
    if op == fcntl.LOCK_UN: raise OSError(errno.EIO, "injected")
    return _fl(fd, op)
fcntl.flock = _unfail
try: a.release(); raised = False
except Exception: raised = True
finally: fcntl.flock = _fl
T(not raised and nfd() == base, "a failing unlock in release does not raise and the descriptor is closed")
a.release(); b = I.acquire_posix(dl); T(b.state == I.HELD, "after the failing release the lock can be taken again"); b.release()
T(nfd() == base, "no descriptor is left after all of it")
print(f"OK ({CHECKS} single-instance checks; POSIX lock with real processes on Linux; Windows mutex compiled only; two real OS instances NOT RUN)")
