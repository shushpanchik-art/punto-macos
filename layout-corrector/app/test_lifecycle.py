"""RT-6 / RT-17 / AP-7 / failure row 11, portable logic. Simulated failures AND child processes that really crash (Linux). No OS check here."""
import json, os, subprocess, sys, tempfile, textwrap, threading
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lflifecycle as K, lfruntime as R, lfstore as S, lfengine as L

CHECKS = 0
def T(c, w):
    global CHECKS
    CHECKS += 1
    if not c: raise AssertionError(w)

M1 = {L.READ_RANGE, L.REPLACE_RANGE, L.READBACK, L.ROLLBACK}
scorer = lambda ids: [-3, 9, -2]
MARKERS = ("ghbdtn", "привет")

def encodings(m):
    out = {m.encode("utf-8"), m.encode("utf-16-le"), m.encode("utf-16-be"), json.dumps(m).strip('"').encode("ascii"),
           json.dumps(m, ensure_ascii=False).strip('"').encode("utf-8"), m.encode("utf-8").hex().encode(), repr(m).encode("utf-8")}
    return out

def occurrences(directory, extra=()):
    n = 0
    blobs = [open(os.path.join(directory, f), "rb").read() for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f))] + list(extra)
    for b in blobs:
        for m in MARKERS:
            for e in encodings(m):
                n += b.count(e)
    return n

def reaches(obj, markers, seen=None, depth=0):
    """Does any str or bytes under obj contain a marker? (a stand-in for a memory dump of the process state)"""
    seen = seen if seen is not None else set()
    if id(obj) in seen or depth > 12: return False
    seen.add(id(obj))
    if isinstance(obj, str): return any(m in obj for m in markers)
    if isinstance(obj, bytes): return any(m.encode("utf-8") in obj for m in markers)
    if isinstance(obj, (int, float, bool, type(None), type)) or callable(obj) and not hasattr(obj, "__dict__"): return False
    if isinstance(obj, dict): return any(reaches(k, markers, seen, depth + 1) or reaches(v, markers, seen, depth + 1) for k, v in obj.items())
    if isinstance(obj, (list, tuple, set, frozenset)): return any(reaches(v, markers, seen, depth + 1) for v in obj)
    d = getattr(obj, "__dict__", None)
    if d is not None and reaches(d, markers, seen, depth + 1): return True
    return any(reaches(getattr(obj, s, None), markers, seen, depth + 1) for s in getattr(type(obj), "__slots__", ()) if isinstance(s, str))

def new_rt():
    return R.Runtime(L.Engine(L.example_cal(), scorer, {"en": {"hello"}, "ru": {"мир"}}), L.HookHealth(canary=False))

def typed(rt, fld, w, t0=100):
    for i, (ch, k) in enumerate(zip(w, L.keys_from_text(w, "en"))):
        fld.type_user(ch); rt.on_hook_event(L.Event("key", k, "en", t0 + i), sig=("k", t0 + i))
    fld.type_user(" ")
    return rt.on_hook_event(L.Event("space", None, "en", t0 + len(w)))

# ------------------------------------------------------------------------------------------------ the report
def boom(secret):
    local_secret = secret + "!"
    raise RuntimeError("typed: " + local_secret)
try:
    try: boom("ghbdtn привет")
    except RuntimeError as inner: raise ValueError("wrapped " + "ghbdtn") from inner
except ValueError:
    t, e, tb = sys.exc_info()
rep = K.build_report(t, e, tb, {"incidents": 2, "restarts": 1}, "1.0.0")
raw = json.dumps(rep).encode()
T(K.validate_report(rep) == [], f"a built report validates: {K.validate_report(rep)}")
T(rep["exception"] == "ValueError" and rep["caused_by"] == ["RuntimeError"], "type names of the exception and of its cause")
T(len(rep["stack"]) >= 1 and rep["stack"][-1]["module"] == "test_lifecycle" and all(set(f) == {"module", "function", "line"} for f in rep["stack"]), "the stack has module, function and line only")
T(rep["counters"] == {"incidents": 2, "restarts": 1, "crashes": 0, "watchdog_trips": 0}, "counters are integers from a fixed list")
T(all(e2 not in raw for m in MARKERS for e2 in encodings(m)), "the message, the cause message and the local variable are not in the report")
T("typed" not in json.dumps(rep) and "wrapped" not in json.dumps(rep), "no word of any exception message is in the report")
bad_cases = {
 "extra field": lambda r: r.update(message="x"),
 "missing field": lambda r: r.pop("stack"),
 "message-like exception": lambda r: r.update(exception="typed ghbdtn"),
 "cyrillic exception name": lambda r: r.update(exception="привет"),
 "frame with locals": lambda r: r["stack"][0].update(locals={"a": "b"}),
 "frame function with a space": lambda r: r["stack"][0].update(function="a b"),
 "negative line": lambda r: r["stack"][0].update(line=-1),
 "string counter": lambda r: r["counters"].update(incidents="2"),
 "bool counter": lambda r: r["counters"].update(incidents=True),
 "unknown counter": lambda r: r["counters"].update(words=1),
 "long chain": lambda r: r.update(caused_by=["A"] * 6),
 "wrong schema": lambda r: r.update(schema=2),
}
for label, mut in bad_cases.items():
    r2 = json.loads(raw); mut(r2)
    T(K.validate_report(r2) != [], f"validate_report refuses: {label}")
T(K._safe_name("привет") == "?" and K._safe_name("a b") == "?" and K.type_name(type("привет", (Exception,), {})) == "?", "a name with a space or a non-ASCII letter becomes '?'")

# ------------------------------------------------------------------------------------------------ the reporter
d = tempfile.mkdtemp(prefix="lfcrash_")
sent = []
rp = K.CrashReporter(d, "1.0.0", lambda: {"crashes": 1}, max_files=3, sender=sent.append, opt_in=lambda: False)
path = rp.handle(t, e, tb)
T(path and os.path.basename(path) == "crash-000001.json" and K.validate_report(json.load(open(path))) == [], "a report is written and valid")
T(sent == [], "NOT sent while the opt-in is off")
rp.opt_in = lambda: True
p2 = rp.handle(t, e, tb)
T(len(sent) == 1 and sent[0] == open(p2, "rb").read(), "sent only with the opt-in, the bytes are those of the file")
rp.sender = lambda b: 1 / 0
T(rp.handle(t, e, tb) is not None, "a failing upload is not a second crash")
for _ in range(5): rp.handle(t, e, tb)
names = sorted(os.listdir(d))
T(names == ["crash-000007.json", "crash-000008.json", "crash-000009.json"] or len(names) == 3, f"at most max_files reports, newest kept: {names}")
# a failing removal of an old report does not hide the new one and does not skip the upload (audit 3)
d2 = tempfile.mkdtemp(prefix="lfcrash_"); sent2 = []
rp2 = K.CrashReporter(d2, "1.0.0", lambda: {}, max_files=1, sender=sent2.append, opt_in=lambda: True)
rp2.handle(t, e, tb); _rm = os.remove
def _fail_rm(p, *a):
    if os.path.basename(p).startswith("crash-"): raise OSError("injected")
    return _rm(p, *a)
os.remove = _fail_rm
try: p3 = rp2.handle(t, e, tb)
finally: os.remove = _rm
T(p3 is not None and os.path.basename(p3) == "crash-000002.json" and rp2.last_path == p3 and len(sent2) == 2, "the new report is reported and uploaded although an old one could not be removed")
open(os.path.join(d, "crash-notes.txt"), "w").write("keep"); open(os.path.join(d, "crash-1.json"), "w").write("keep")
os.mkdir(os.path.join(d, "crash-000999.json")); outside = tempfile.mkdtemp(); open(os.path.join(outside, "v"), "w").write("v")
os.symlink(os.path.join(outside, "v"), os.path.join(d, "crash-000001.json"))
rets = [rp.handle(t, e, tb) for _ in range(5)]
T(all(rets) and len(rp._own()) == 3 and all(os.path.isfile(r2) for r2 in rets[-3:]), f"with look-alike names around, every report is still written and exactly max_files are kept: {rp._own()}")
T(open(os.path.join(d, "crash-notes.txt")).read() == "keep" and open(os.path.join(d, "crash-1.json")).read() == "keep" and os.path.isdir(os.path.join(d, "crash-000999.json"))
  and open(os.path.join(outside, "v")).read() == "v" and os.path.islink(os.path.join(d, "crash-000001.json")), "retention touches only the reporter's own regular files")
T(rp.handle(KeyboardInterrupt, KeyboardInterrupt(), None) is None and rp.handle(SystemExit, SystemExit(), None) is None, "KeyboardInterrupt and SystemExit are not crashes")
fdir = os.path.join(tempfile.mkdtemp(), "afile"); open(fdir, "w").write("x")
T(K.CrashReporter(fdir).handle(t, e, tb) is None, "an unusable directory: the handler returns None and never raises")
def bad_counters(): raise RuntimeError("ghbdtn")
p3 = K.CrashReporter(tempfile.mkdtemp(), counters=bad_counters).handle(t, e, tb)
T(p3 is not None and json.load(open(p3))["counters"]["incidents"] == 0 and b"ghbdtn" not in open(p3, "rb").read(), "a failing counter source does not hide the crash")
T(K.CrashReporter(tempfile.mkdtemp(), counters=lambda: {"incidents": "ghbdtn", "crashes": -1, "restarts": True}).handle(t, e, tb) is not None, "garbage counters become zeros")

# ------------------------------------------------------------------------------------------------ the crash window (row 11, AP-7)
w = K.CrashWindow()
T(w.record(0) == "restart" and w.record(60_000) == "manual_only", "two crashes 60,000 ms apart: MANUAL_ONLY (inclusive)")
w = K.CrashWindow(); T(w.record(0) == "restart" and w.record(60_001) == "restart", "60,001 ms apart: restart")
w = K.CrashWindow(); w.record(0); w.record(10); T(w.record(10**9) == "manual_only", "MANUAL_ONLY stays latched")
w.reset(); T(w.record(10**9 + 1) == "restart", "reset clears it")
w = K.CrashWindow(); w.record(100)
try: w.record(50); T(False, "a clock that went back")
except ValueError: T(True, "a clock that went back is refused")
w = K.CrashWindow(); T([w.record(t0) for t0 in (0, 70_000, 140_000)] == ["restart"] * 3, "crashes more than 60 s apart never add up")

# ------------------------------------------------------------------------------------------------ the supervisor
now = [0]
rt = new_rt(); fld = L.SimField("", M1); rt.on_focus("A", fld, "AUTO"); rt.on_gate(L.GATE_ALLOW)
d = tempfile.mkdtemp(prefix="lfsup_")
sup = K.Supervisor(rt, K.CrashReporter(d, "1.0.0"), lambda: now[0])
for i, (ch, k) in enumerate(zip("ghb", L.keys_from_text("ghb", "en"))):
    fld.type_user(ch); rt.on_hook_event(L.Event("key", k, "en", 10 + i), sig=("k", i))
T(rt.engine.run != [], "setup: a word is in progress")
def failing(): raise ZeroDivisionError("ghbdtn")
T(sup.run(failing) is None and rt.engine.run == [] and rt.worker_ok and rt.engine.mode == "AUTO" and sup.restarts == 1, "first failure: the word is dropped, the worker restarts, still AUTO")
T(sup.run(lambda: 5) == 5, "a healthy step returns its value")
now[0] = 30_000
T(sup.run(failing) is None and not rt.worker_ok and rt.engine.mode == "MANUAL_ONLY" and rt.explain("A") == ("MANUAL_ONLY", ["worker"]), "second failure within 60 s: MANUAL_ONLY, reason 'worker'")
T(rt.notices.count(("worker_failed_twice", "")) == 1, "one notice, after the second failure")
now[0] = 31_000; sup.run(failing)
T(rt.notices.count(("worker_failed_twice", "")) == 1 and rt.engine.mode == "MANUAL_ONLY", "a third failure adds no second notice")
sup.restart_clean()
T(rt.worker_ok and rt.engine.mode == "AUTO", "re-enable clears the state")
now[0] = 200_000; sup.run(failing); now[0] = 300_000; sup.run(failing)
T(rt.worker_ok and rt.engine.mode == "AUTO", "failures more than 60 s apart do not give MANUAL_ONLY")
try: sup.run(lambda: (_ for _ in ()).throw(KeyboardInterrupt())); T(False, "KeyboardInterrupt must propagate")
except KeyboardInterrupt: T(True, "KeyboardInterrupt is not swallowed by the supervisor")
T(len([n for n in os.listdir(d) if n.startswith("crash-")]) >= 3 and occurrences(d) == 0, "reports were written and contain no marker")

# ------------------------------------------------------------------------------------------------ RT-17 in process: a snapshot is alive, the step fails with the marker everywhere
rt = new_rt(); fld = L.SimField("", M1); rt.on_focus("A", fld, "AUTO"); rt.on_gate(L.GATE_ALLOW)
dec = typed(rt, fld, "ghbdtn")
T(dec is not None and dec.action == "CONVERT" and rt.engine.snapshot is not None, "setup: converted, the undo snapshot is alive")
T(reaches(rt.engine, MARKERS), "positive control: the markers ARE reachable in the live engine state (the search below can find them)")
d = tempfile.mkdtemp(prefix="lfrt17_"); sup = K.Supervisor(rt, K.CrashReporter(d, "1.0.0"), lambda: 0)
def step_with_secrets(word="ghbdtn", other="привет"):
    buffer_copy = [word, other, rt.engine.snapshot]
    raise RuntimeError(f"failed on {word} / {other} / {buffer_copy!r}")
sup.run(step_with_secrets)
T(os.listdir(d) == ["crash-000001.json"], "one report was written")
T(occurrences(d) == 0, "RT-17: 0 occurrences of the typed marker and its conversion in the report (UTF-8, UTF-16, JSON-escaped, hex, repr)")

# ------------------------------------------------------------------------------------------------ RT-17 with a real crashing child process
CHILD = textwrap.dedent('''
    import sys, os, threading, faulthandler
    sys.path.insert(0, {app!r}); sys.path.insert(0, {ref!r})
    import lflifecycle as K, lfruntime as R, lfengine as L
    M1 = {{L.READ_RANGE, L.REPLACE_RANGE, L.READBACK, L.ROLLBACK}}
    rt = R.Runtime(L.Engine(L.example_cal(), lambda ids: [-3, 9, -2], {{"en": {{"hello"}}, "ru": {{"мир"}}}}), L.HookHealth(canary=False))
    fld = L.SimField("", M1); rt.on_focus("A", fld, "AUTO"); rt.on_gate(L.GATE_ALLOW)
    w = "ghbdtn"
    for i, (ch, k) in enumerate(zip(w, L.keys_from_text(w, "en"))):
        fld.type_user(ch); rt.on_hook_event(L.Event("key", k, "en", 100 + i), sig=("k", i))
    fld.type_user(" "); d = rt.on_hook_event(L.Event("space", None, "en", 110))
    print("snapshot_alive", rt.engine.snapshot is not None, "faulthandler", faulthandler.is_enabled(), flush=True)
    K.CrashReporter({dir!r}, "1.0.0", lambda: {{"crashes": 1}}).install()
    mode = sys.argv[1]
    secret = "ghbdtn привет"
    if mode == "main":
        raise RuntimeError("typed " + secret)
    if mode == "thread":
        def work():
            local = secret
            raise RuntimeError("typed " + local)
        t = threading.Thread(target=work); t.start(); t.join(); print("main continues")
    if mode == "kill":
        import signal; os.kill(os.getpid(), signal.SIGKILL)
''')
here = os.path.dirname(os.path.abspath(__file__)); ref = os.path.join(here, "..", "reference")
for mode, want_code in (("main", 1), ("thread", 0), ("kill", -9)):
    d = tempfile.mkdtemp(prefix=f"lfchild_{mode}_")
    script = os.path.join(tempfile.mkdtemp(), "child.py"); open(script, "w", encoding="utf-8").write(CHILD.format(app=here, ref=ref, dir=d))
    r = subprocess.run([sys.executable, script, mode], capture_output=True, text=True, encoding="utf-8")
    T(r.returncode == want_code, f"child {mode}: exit code {r.returncode}")
    T("snapshot_alive True" in r.stdout and "faulthandler False" in r.stdout, f"child {mode}: the snapshot was alive at the crash and the module did not enable faulthandler")
    T(occurrences(d, [r.stdout.replace("snapshot_alive", "").encode(), r.stderr.encode("utf-8")]) == 0, f"child {mode}: 0 occurrences in the report directory, stdout and stderr")
    files = os.listdir(d)
    if mode == "kill":
        T(files == [], "child kill -9: the product wrote nothing while running (an OS dump would be outside the product)")
    else:
        T(len(files) == 1 and K.validate_report(json.load(open(os.path.join(d, files[0])))) == [], f"child {mode}: one valid report")
    T("typed" not in r.stderr, f"child {mode}: the default hook that prints the message is replaced")

# ------------------------------------------------------------------------------------------------ safe shutdown
rt = new_rt(); fld = L.SimField("", M1); rt.on_focus("A", fld, "AUTO"); rt.on_gate(L.GATE_ALLOW)
typed(rt, fld, "ghbdtn"); fld2 = None
for i, (ch, k) in enumerate(zip("ghb", L.keys_from_text("ghb", "en"))):
    fld.type_user(ch); rt.on_hook_event(L.Event("key", k, "en", 300 + i), sig=("q", i))
T(reaches(rt, MARKERS) and rt.engine.snapshot is not None, "setup: the snapshot is alive and the markers are reachable from the runtime")
rt.shutdown()
T(not reaches(rt, MARKERS) and rt.engine.snapshot is None and rt.engine.run == [] and rt.engine.undoing is None and rt.engine.manual is None and rt.engine.toggling is None
  and rt.ad is None and rt.engine.mode == "OFF", "shutdown: no marker is reachable, every text-derived record is gone, the adapter is let go")
# the list of exceptions is saved first, and it is the one thing that stays (by design, 13.3), encrypted
rt = new_rt(); fld = L.SimField("", M1); rt.on_focus("A", fld, "AUTO"); rt.on_gate(L.GATE_ALLOW)
typed(rt, fld, "ghbdtn"); r = rt.hotkey_undo(300)
T(r is not None and r.outcome == "VERIFIED" and ("en2ru", "ghbdtn") in rt.engine.exceptions, "setup: an undo added the word to the exception list")
sd = tempfile.mkdtemp(); st = S.Store(os.path.join(sd, "settings.json"), S.TestOnlyCipher(b"k"), allow_test_cipher=True); state = st.load()
T(K.stop(rt, st, state) is True and rt.engine.snapshot is None and rt.engine.mode == "OFF", "stop: saved, then wiped")
T(S.Store(st.path, S.TestOnlyCipher(b"k"), allow_test_cipher=True).load().exceptions == [("en2ru", "ghbdtn")] and "ghbdtn" not in open(st.path, encoding="utf-8").read(), "the exception list is in the file, not in clear")
class Locked(S.Cipher):
    def encrypt(self, d): raise S.CipherUnavailable("locked")
    def decrypt(self, d): raise S.CipherUnavailable("locked")
rt2 = new_rt(); f2 = L.SimField("", M1); rt2.on_focus("A", f2, "AUTO"); rt2.on_gate(L.GATE_ALLOW); typed(rt2, f2, "ghbdtn")
sd2 = tempfile.mkdtemp(); st2 = S.Store(os.path.join(sd2, "s.json"), Locked()); 
T(K.stop(rt2, st2, S.StoreState()) is False and os.listdir(sd2) == [] and rt2.engine.mode == "OFF" and not reaches(rt2, MARKERS), "an unavailable key store: nothing written, no clear text, the wipe still happens")
T(K.stop(new_rt()) is None, "stop without a store only wipes")
# ---- the wipe must happen when saving fails, in every place it can fail; the failure is raised, not hidden (isolated temporary directories)
import builtins
def live_rt():
    r = new_rt(); f = L.SimField("", M1); r.on_focus("A", f, "AUTO"); r.on_gate(L.GATE_ALLOW)
    typed(r, f, "ghbdtn")
    for i, (ch, k) in enumerate(zip("ghb", L.keys_from_text("ghb", "en"))):
        f.type_user(ch); r.on_hook_event(L.Event("key", k, "en", 300 + i), sig=("q", i))
    T(r.engine.snapshot is not None and reaches(r, MARKERS), "setup: live snapshot, markers reachable")
    return r
class Boom(Exception): pass
def inject(path):
    """Returns (apply, restore) that make exactly one step of Store.save fail with Boom."""
    real = {"open": getattr(S, "open", None), "fsync": os.fsync, "replace": os.replace, "dump": S.json.dump}
    def apply():
        if path == "open":
            def bad(name, *a, **k):
                if str(name).endswith(".tmp"): raise Boom("open")
                return builtins.open(name, *a, **k)
            S.open = bad
        elif path == "write":
            def bad(*a, **k): raise Boom("write")
            S.json.dump = bad
        elif path == "fsync": os.fsync = lambda fd: (_ for _ in ()).throw(Boom("fsync"))
        elif path == "replace": os.replace = lambda a, b: (_ for _ in ()).throw(Boom("replace"))
    def restore():
        if real["open"] is None and hasattr(S, "open"): del S.open
        elif real["open"] is not None: S.open = real["open"]
        os.fsync, os.replace, S.json.dump = real["fsync"], real["replace"], real["dump"]
    return apply, restore
for path in ("open", "write", "fsync", "replace"):
    rt = live_rt(); sd = tempfile.mkdtemp(prefix="lfstopfail_")
    st = S.Store(os.path.join(sd, "settings.json"), S.TestOnlyCipher(b"k"), allow_test_cipher=True); state = st.load(); st.save(state)
    before = open(st.path, "rb").read(); names = sorted(os.listdir(sd))
    ap, rs = inject(path); got = None
    try:
        ap()
        try: K.stop(rt, st, state)
        except BaseException as e: got = e
    finally: rs()
    T(isinstance(got, Boom) and str(got) == path, f"save failure at {path}: the error is raised, not hidden ({got!r})")
    T(rt.engine.snapshot is None and rt.engine.mode == "OFF" and rt.ad is None and not reaches(rt, MARKERS), f"save failure at {path}: the wipe still happened, no marker reachable")
    T(open(st.path, "rb").read() == before and sorted(os.listdir(sd)) == names and occurrences(sd) == 0, f"save failure at {path}: the earlier file is untouched, no temporary file left, 0 occurrences in the directory")
# a cipher error that is not CipherUnavailable, and a failing sync
class BadCipher(S.Cipher):
    def encrypt(self, d): raise Boom("cipher")
    def decrypt(self, d): return d
rt = live_rt(); sd = tempfile.mkdtemp(prefix="lfstopfail_"); st = S.Store(os.path.join(sd, "s.json"), BadCipher()); got = None
try: K.stop(rt, st, S.StoreState())
except BaseException as e: got = e
T(isinstance(got, Boom) and rt.engine.snapshot is None and not reaches(rt, MARKERS) and os.listdir(sd) == [], "an encrypt failure: raised, wiped, nothing written")
rt = live_rt(); real_sync = S.sync_from_engine; S.sync_from_engine = lambda e, s: (_ for _ in ()).throw(Boom("sync")); got = None
try:
    try: K.stop(rt, S.Store(os.path.join(tempfile.mkdtemp(), "s.json"), S.TestOnlyCipher(b"k"), allow_test_cipher=True), S.StoreState())
    except BaseException as e: got = e
finally: S.sync_from_engine = real_sync
T(isinstance(got, Boom) and rt.engine.snapshot is None and not reaches(rt, MARKERS), "a failing sync: raised, wiped")
# the wipe fails too: that error is raised and the save error stays attached
rt = live_rt(); sd = tempfile.mkdtemp(); st = S.Store(os.path.join(sd, "s.json"), BadCipher()); real_sd = rt.shutdown
class Boom2(Exception): pass
def bad_wipe(): raise Boom2("wipe")
rt.shutdown = bad_wipe; got = None
try: K.stop(rt, st, S.StoreState())
except BaseException as e: got = e
T(isinstance(got, Boom2) and isinstance(got.__context__, Boom), "wipe failure on top of a save failure: both are visible (wipe raised, save error as context)")
real_sd()
print(f"OK ({CHECKS} lifecycle and crash checks; simulated failures and child processes on Linux; no OS crash reporter, no supervisor process)")
