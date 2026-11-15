"""AP-9 updates, portable part: staging, verification, switch-in rule, staged rollout, one-step rollback, on a temporary directory. The signature is a FAKE
(a keyed hash that stands for a verifier); no network, no operating-system call, no real package, no real signature scheme."""
import hashlib, json, os, sys, tempfile, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lfupdate as U, lfnotify as N, lfruntime as R, lfengine as L

CHECKS = 0
def T(c, w):
    global CHECKS
    CHECKS += 1
    if not c: raise AssertionError(w)

def sign(data): return hashlib.sha256(b"fake-key" + data).digest()
def verify(data, sig): return sig == sign(data)
def pkg(v, files=None, pct=100, **over):
    files = {"model": b"m" + v.encode(), "calibration": b"c" + v.encode()} if files is None else files
    m = {"version": v, "rollout_percent": pct, "sha256": {n: hashlib.sha256(b).hexdigest() for n, b in files.items()}}
    m.update(over)
    return m, sign(U.canonical(m)), files
def tree(root):
    out = []
    for d, _, fs in os.walk(root):
        for f in sorted(fs): out.append((os.path.relpath(os.path.join(d, f), root), open(os.path.join(d, f), "rb").read()))
    return sorted(out)

class Env:
    def __init__(self, **kw):
        self.root = tempfile.mkdtemp(prefix="lfu_"); self.shown = []
        self.now = [10_000]; self.nt = N.Notifier(lambda n: self.shown.append(n) or True, lambda: self.now[0])
        self.kw = kw; self.u = U.Updater(self.root, verify, notifier=self.nt, **kw)
    def reopen(self, **kw): self.u = U.Updater(self.root, verify, notifier=self.nt, **dict(self.kw, **kw)); return self.u
    def done(self): shutil.rmtree(self.root, ignore_errors=True)

# ---- the helpers themselves
T(U.vkey("1.2.3") == (1, 2, 3) and all(U.vkey(x) is None for x in ("1.2", "01.2.3", "1.2.3.4", "a.b.c", "1.2.3\n", "", None, 5, "-1.0.0", "10000.0.0")), "the version grammar")
T(U.canonical({"b": 1, "a": [2]}) == b'{"a":[2],"b":1}', "canonical bytes: sorted keys, no spaces")

# ---- a good package, then a bad one never replaces it
e = Env()
T(e.u.state == {"active": "builtin", "previous": None, "staged": None, "blocked": []} and e.u.active_files() == {}, "start: the built-in package")
m, s, f = pkg("1.0.0"); T(e.u.stage(m, s, f) == "staged" and e.u.state["staged"] == "1.0.0" and e.u.state["active"] == "builtin", "staged, not active")
T(e.u.stage(m, s, f) == "duplicate" and e.u.counters["duplicate"] == 1, "the same package again: nothing is written twice")
T(e.u.switch_if_idle(R.Runtime(L.Engine(L.example_cal(), lambda ids: [0, 0, 0], {}), L.HookHealth(canary=False))) == "switched" and e.u.state == {"active": "1.0.0", "previous": "builtin", "staged": None, "blocked": []}, "switched when idle")
T(sorted(e.u.active_files()) == ["calibration", "model"] and open(e.u.active_files()["model"], "rb").read() == b"m1.0.0", "the active files are the package's")
before = tree(e.root)
def rejected(m, s, f, code, why):
    global before
    r = e.u.stage(m, s, f)
    T(r == "rejected:" + code, f"{why}: {r}")
    T(tree(e.root) == before and e.u.state["active"] == "1.0.0", f"{why}: the previous package stays active and nothing changed")
m, s, f = pkg("1.1.0")
rejected(dict(m, extra=1), s, f, "shape", "an extra field")
mm = dict(m); del mm["rollout_percent"]; rejected(mm, s, f, "shape", "a missing field")
rejected("x", s, f, "shape", "not a dict"); rejected(m, s, [], "shape", "files not a dict")
for bad in ("1.1", "01.1.0", "1.1.0\n", None, 5): rejected(*pkg("1.1.0", version=bad)[:1], s, f, "version", f"version {bad!r}")
for bad in (True, 101, -1, 50.0, "100", None): rejected(*pkg("1.1.0", pct=bad)[:1], s, f, "rollout", f"rollout {bad!r}")
mx = dict(m, sha256={"model": "0" * 64, "x": "0" * 64}); rejected(mx, s, {"model": b"", "x": b""}, "components", "unknown component")
rejected(m, s, {"model": f["model"]}, "components", "files do not match the hash list")
rejected(dict(m, sha256={}), s, {}, "components", "no component")
for h in ("A" * 64, "0" * 63, 5, None, "g" * 64): rejected(dict(m, sha256={"model": h, "calibration": m["sha256"]["calibration"]}), s, f, "components", f"bad hash text {h!r}")
mo, so, fo = pkg("1.1.0", {"model": b"x"}); rejected(mo, so, fo, "calibration_hash_missing", "a model without the calibration hash (DP-7)")
mt = pkg("1.1.0", {"lexicon": b"x"}); mt = (mt[0], mt[1], {"lexicon": "text"}); rejected(*mt, "size", "files that are not bytes")
mo, so, fo = pkg("1.1.0", {"lexicon": b"x"}); T(e.u.stage(mo, so, fo) == "staged", "a lexicon alone needs no calibration")
e.u._save(dict(e.u.state, staged=None)); e.u._gc(); before = tree(e.root)
rejected(m, b"wrong", f, "signature", "a wrong signature")
rejected(m, None, f, "signature", "no signature")
class Boom:
    def __call__(self, d, s): raise RuntimeError("x")
e.u.verify = Boom(); rejected(m, s, f, "signature", "a failing verifier"); e.u.verify = lambda d, s: 1; rejected(m, s, f, "signature", "a verifier that answers 1 is not True"); e.u.verify = lambda d, s: "yes"; rejected(m, s, f, "signature", "a verifier that answers 'yes'"); e.u.verify = verify
f2 = dict(f, model=b"tampered"); rejected(m, s, f2, "hash", "a changed file")
m2, s2, f3 = pkg("1.1.0"); m2b = dict(m2, version="1.1.1"); rejected(m2b, s2, f3, "signature", "a changed manifest keeps the old signature and fails")
big = {"model": b"x" * (U.MAX_BYTES + 1), "calibration": b"c"}; mb, sb, fb = pkg("1.1.0", big); rejected(mb, sb, fb, "size", "over 10 MB")
ok_big = {"lexicon": b"x" * U.MAX_BYTES}; mb, sb, fb = pkg("1.1.0", ok_big); T(e.u.stage(mb, sb, fb) == "staged", "exactly 10 MB is allowed"); e.u._save(dict(e.u.state, staged=None)); e.u._gc(); before = tree(e.root)
T(e.shown == [] and len(e.nt.pending) == 1 and e.nt.pending[0][1]["kind"] == "update_failed" and e.nt.pending[0][1]["row"] == 12 and e.nt.pending[0][1]["action"] == "open_settings" and e.nt.pending[0][1]["takes_focus"] is False,
  "every failure queues one row 12 notice (one cause, so one entry), with one action")
e.nt.deliver(); T(len(e.shown) == 1, "shown once")
for _ in range(3): e.u.stage(m, b"bad", f)
e.nt.deliver(); T(len(e.shown) == 1, "within 24 h no second notice (13.5)")
# versions
mo, so, fo = pkg("1.0.0"); rejected(mo, so, fo, "not_newer", "the active version again")
mo, so, fo = pkg("0.9.9"); rejected(mo, so, fo, "not_newer", "an older version")
# staging a newer package replaces the staged one; an older one than the staged is refused
m11, s11, f11 = pkg("1.1.0"); m12, s12, f12 = pkg("1.2.0"); m105, s105, f105 = pkg("1.0.5")
T(e.u.stage(m11, s11, f11) == "staged" and e.u.stage(m12, s12, f12) == "staged" and e.u.state["staged"] == "1.2.0", "a newer package replaces the staged one")
T(sorted(os.listdir(os.path.join(e.root, "packages"))) == ["1.0.0", "1.2.0"], "the replaced staged files are gone")
T(e.u.stage(m11, s11, f11) == "rejected:not_newer" and e.u.state["staged"] == "1.2.0", "an older package than the staged one is refused")
# ---- the switch-in rule: restart, or no word in progress
rt = R.Runtime(L.Engine(L.example_cal(), lambda ids: [-3, 9, -2], {"en": {"hello"}, "ru": {"привет"}}), L.HookHealth(canary=False))
f_ = L.SimField("", {L.READ_RANGE, L.REPLACE_RANGE, L.READBACK, L.ROLLBACK}); rt.on_focus("A", f_, "AUTO"); rt.on_gate(L.GATE_ALLOW)
for i, (ch, k) in enumerate(zip("ghb", L.keys_from_text("ghb", "en"))):
    f_.type_user(ch); rt.on_hook_event(L.Event("key", k, "en", 100 + i), sig=("k", 100 + i))
T(not U.Updater.idle(rt) and e.u.switch_if_idle(rt) == "busy" and e.u.state["active"] == "1.0.0" and e.u.state["staged"] == "1.2.0" and e.u.counters["busy"] == 1, "a word in progress: not switched, still staged")
T(e.u.switch_if_idle(rt) == "busy" and e.u.counters["busy"] == 2, "asking again changes nothing")
rt.engine.run = []; T(U.Updater.idle(rt), "no word: idle")
rt.engine.undoing = object(); T(not U.Updater.idle(rt) and e.u.switch_if_idle(rt) == "busy", "an undo in flight is not idle"); rt.engine.undoing = None
rt.engine.manual = object(); T(not U.Updater.idle(rt), "a manual conversion in flight is not idle"); rt.engine.manual = None
rt.engine.toggling = object(); T(not U.Updater.idle(rt), "a toggle in flight is not idle"); rt.engine.toggling = None
rt.engine.run = ["k"]; T(e.u.at_restart() == "switched" and e.u.state["active"] == "1.2.0" and e.u.state["previous"] == "1.0.0", "a restart switches whatever the engine holds")
T(e.u.at_restart() == "nothing_staged" and e.u.switch_if_idle(rt) == "nothing_staged", "nothing staged: nothing to do")
T(sorted(os.listdir(os.path.join(e.root, "packages"))) == ["1.0.0", "1.2.0"], "the package two steps back is removed")
# ---- rollback: one step
T(e.u.rollback() == "rolled_back" and e.u.state == {"active": "1.0.0", "previous": None, "staged": None, "blocked": ["1.2.0"]}, "one step back to the previous package")
T(e.u.rollback() == "nothing" and e.u.counters["nothing_to_roll_back"] == 1 and e.u.state["active"] == "1.0.0", "a second rollback does nothing")
T(sorted(os.listdir(os.path.join(e.root, "packages"))) == ["1.0.0"], "the package rolled back from is removed")
T(e.u.stage(m12, s12, f12) == "rejected:blocked", "the version rolled back from is not staged again")
m13, s13, f13 = pkg("1.3.0"); T(e.u.stage(m13, s13, f13) == "staged" and e.u.at_restart() == "switched" and e.u.rollback() == "rolled_back" and e.u.state["active"] == "1.0.0" and e.u.state["blocked"] == ["1.2.0", "1.3.0"], "later versions work, and each rollback blocks its version")
# the first update rolls back to the built-in package
e2 = Env(); a1, b1, c1 = pkg("2.0.0"); e2.u.stage(a1, b1, c1); e2.u.at_restart()
T(e2.u.rollback() == "rolled_back" and e2.u.state["active"] == "builtin" and e2.u.active_files() == {} and e2.u.state["blocked"] == ["2.0.0"], "from the first update back to the built-in package")
T(e2.u.rollback() == "nothing", "nothing below the built-in package")
e2.done()
# the blocked list is bounded: the oldest entries go
e3 = Env()
for i in range(1, 19):
    a, b, c = pkg(f"3.{i}.0"); e3.u.stage(a, b, c); e3.u.at_restart(); e3.u.rollback()
T(len(e3.u.state["blocked"]) == U.MAX_BLOCKED and e3.u.state["blocked"][0] == "3.3.0" and e3.u.state["blocked"][-1] == "3.18.0", "at most 16 versions stay blocked, the oldest are dropped")
e3.done()
# a hash text must be exactly 64 lower-case hex digits: a trailing line break is not allowed
e3 = Env(); m_, s_, f_x = pkg("1.9.0")
T(e3.u.stage(dict(m_, sha256={"model": m_["sha256"]["model"] + "\n", "calibration": m_["sha256"]["calibration"]}), s_, f_x) == "rejected:components" and tree(e3.root) == [], "a hash text with a trailing line break")
e3.done()
# ---- persistence
u = e.reopen(); T(u.state["active"] == "1.0.0" and u.state["blocked"] == ["1.2.0", "1.3.0"], "the state survives a restart")
os.makedirs(os.path.join(e.root, "packages", "9.9.9")); os.makedirs(os.path.join(e.root, "packages", "7.7.7.tmp")); e.reopen()
T(sorted(os.listdir(os.path.join(e.root, "packages"))) == ["1.0.0"], "at start what the state does not reference is removed")
for bad in (b"{not json", b"[]", json.dumps({"active": "1.0.0"}).encode(), json.dumps({"active": "evil/../x", "previous": None, "staged": None, "blocked": []}).encode(),
            json.dumps({"active": "1.0.0", "previous": None, "staged": "builtin", "blocked": []}).encode(), json.dumps({"active": "1.0.0", "previous": None, "staged": None, "blocked": ["x"] * 3}).encode(),
            json.dumps({"active": "1.0.0", "previous": None, "staged": None, "blocked": ["1.0.0"] * 17}).encode(), json.dumps({"active": None, "previous": None, "staged": None, "blocked": []}).encode(),
            json.dumps({"active": "1.0.0", "previous": None, "staged": None, "blocked": [], "x": 1}).encode()):
    open(os.path.join(e.root, "state.json"), "wb").write(bad); u = e.reopen()
    T(u.state == {"active": "builtin", "previous": None, "staged": None, "blocked": []} and u.counters["state_unreadable"] == 1 and os.path.exists(os.path.join(e.root, "state.json.bad")), f"an unreadable state means the built-in package: {bad[:30]!r}")
    os.remove(os.path.join(e.root, "state.json.bad"))
T(os.listdir(os.path.join(e.root, "packages")) == [], "an unreadable state leaves no package referenced, so none is kept")
e.done()
# ---- a failed write leaves the active package alone
e = Env(); a1, b1, c1 = pkg("1.0.0"); e.u.stage(a1, b1, c1); e.u.at_restart(); snap = tree(e.root)
real = os.replace
def failing(src, dst, *a):
    if str(dst).endswith("state.json"): raise OSError("disk")
    return real(src, dst, *a)
a2, b2, c2 = pkg("1.1.0"); os.replace = failing
try: r = e.u.stage(a2, b2, c2)
finally: os.replace = real
T(r == "rejected:storage" and e.u.state["active"] == "1.0.0" and e.u.state["staged"] is None and tree(e.root) == snap, "a state write that fails while staging: previous stays, nothing left over")
e.u.stage(a2, b2, c2); snap = tree(e.root); os.replace = failing
try: r = e.u.at_restart()
finally: os.replace = real
T(r == "rejected:storage" and e.u.state["active"] == "1.0.0" and e.u.state["staged"] == "1.1.0", "a failing switch keeps the old package and the staged one")
os.replace = failing
try: r = e.u.rollback()
finally: os.replace = real
T(r == "rejected:storage" and e.u.state["active"] == "1.0.0" and e.u.state["previous"] == "builtin" and not os.path.exists(os.path.join(e.root, "state.json.tmp")), "a failing rollback write changes nothing and leaves no temporary file")
e.done()
# ---- the validation at the switch (row 6: the calibration is validated before an engine is created); the real CA-9 check of the reference
cals = {}
def validate(v, paths): L.check_calibration_package(cals[v]); return True
e = Env(validate=validate); import copy
good = copy.deepcopy(L.example_cal()); bad = copy.deepcopy(L.example_cal()); bad.pop(next(iter(bad)))
cals["1.0.0"] = good; cals["1.1.0"] = bad
a1, b1, c1 = pkg("1.0.0"); e.u.stage(a1, b1, c1); T(e.u.at_restart() == "switched", "a valid calibration is switched in")
a2, b2, c2 = pkg("1.1.0"); e.u.stage(a2, b2, c2)
T(e.u.at_restart() == "rejected:validation" and e.u.state["active"] == "1.0.0" and e.u.state["staged"] is None and os.listdir(os.path.join(e.root, "packages")) == ["1.0.0"], "a refused calibration package: the previous one stays active, the new one is dropped")
e.u.validate = lambda v, p: 1; a3, b3, c3 = pkg("1.2.0"); e.u.stage(a3, b3, c3); T(e.u.at_restart() == "rejected:validation", "a validator that does not answer True refuses")
e.u.validate = lambda v, p: 1 / 0; e.u.stage(a3, b3, c3); T(e.u.at_restart() == "rejected:validation" and e.u.state["active"] == "1.0.0", "a failing validator refuses")
e.done()
# ---- the stored package is checked again when it is used (audit of AP-9: atomicity, tampering after staging, loss of the previous state)
def fresh(v1="1.0.0", v2=None):
    en = Env(); a, b, c = pkg(v1); en.u.stage(a, b, c); en.u.at_restart()
    if v2: a, b, c = pkg(v2); en.u.stage(a, b, c)
    return en
P = lambda en, v, n="": os.path.join(en.root, "packages", v, n)
# a file changed after it was staged
en = fresh("1.0.0", "1.1.0"); open(P(en, "1.1.0", "model"), "wb").write(b"evil")
T(en.u.at_restart() == "rejected:integrity" and en.u.state["active"] == "1.0.0" and en.u.state["staged"] is None and not os.path.exists(P(en, "1.1.0")), "a staged file changed before the switch: not used, dropped, the active one stays")
T(len(en.nt.pending) == 1 and en.nt.pending[0][1]["kind"] == "update_failed", "and a row 12 notice is queued"); en.done()
# the stored manifest or signature changed, the directory removed, a file added, a link in place of a file, a key that no longer verifies
for what in ("sig", "manifest", "rmdir", "extra", "link", "missing_file", "revoked_key", "garbage_manifest"):
    en = fresh("1.0.0", "1.1.0"); d = P(en, "1.1.0")
    if what == "sig":
        r = json.load(open(d + "/manifest.json")); r["signature"] = "00" * 32; json.dump(r, open(d + "/manifest.json", "w"))
    elif what == "manifest":
        r = json.load(open(d + "/manifest.json")); r["manifest"]["rollout_percent"] = 1; json.dump(r, open(d + "/manifest.json", "w"))
    elif what == "rmdir": shutil.rmtree(d)
    elif what == "extra": open(d + "/lexicon", "wb").write(b"x")
    elif what == "link": os.remove(d + "/model"); os.symlink(P(en, "1.0.0", "model"), d + "/model")
    elif what == "missing_file": os.remove(d + "/model")
    elif what == "revoked_key": en.u.verify = lambda data, sig: False
    elif what == "garbage_manifest": open(d + "/manifest.json", "w").write("{")
    r = en.u.at_restart()
    T(r == "rejected:integrity" and en.u.state["active"] == "1.0.0" and en.u.state["staged"] is None, f"integrity: {what}: {r}")
    en.done()
# a signed package of ANOTHER version put into the staged directory
en = fresh("1.0.0", "1.1.0"); shutil.rmtree(P(en, "1.1.0")); shutil.copytree(P(en, "1.0.0"), P(en, "1.1.0"))
T(en.u.at_restart() == "rejected:integrity" and en.u.state["active"] == "1.0.0", "a valid package of another version in the staged directory is refused"); en.done()
# a link in place of a component, pointing to a file with the very same content
en = fresh("1.0.0", "1.1.0"); outside = os.path.join(en.root, "outside"); open(outside, "wb").write(b"m1.1.0"); os.remove(P(en, "1.1.0", "model")); os.symlink(outside, P(en, "1.1.0", "model"))
T(en.u.at_restart() == "rejected:integrity", "a link is refused even when the content would match"); en.done()
# exactly 10 MB is staged AND switched
en = Env(); a, b, c = pkg("1.0.0", {"lexicon": b"x" * U.MAX_BYTES}); T(en.u.stage(a, b, c) == "staged" and en.u.at_restart() == "switched" and en.u.state["active"] == "1.0.0", "a package of exactly 10 MB passes the check at the switch"); en.done()
# the active and the previous package both damaged
en = fresh("1.0.0", "1.1.0"); en.u.at_restart(); open(P(en, "1.1.0", "model"), "wb").write(b"evil"); open(P(en, "1.0.0", "model"), "wb").write(b"evil"); u = en.reopen()
T(u.state["active"] == "builtin" and u.state["previous"] is None and u.counters["active_damaged"] == 1, "both damaged at start: the built-in package"); en.done()
# the blocked list stays bounded when a damaged active package is found
en = fresh("1.0.0"); st_ = json.load(open(os.path.join(en.root, "state.json"))); st_["blocked"] = ["9.%d.0" % i for i in range(16)]; json.dump(st_, open(os.path.join(en.root, "state.json"), "w")); open(P(en, "1.0.0", "model"), "wb").write(b"evil")
u = en.reopen(); T(len(u.state["blocked"]) == 16 and u.state["blocked"][-1] == "1.0.0" and u.state["blocked"][0] == "9.1.0", "the blocked list stays at 16"); en.done()
# the verifier must still answer exactly True when the package is used
en = fresh("1.0.0", "1.1.0"); en.u.verify = lambda d, sg: 1
T(en.u.at_restart() == "rejected:integrity", "a verifier that answers 1 at the switch does not pass the stored package"); en.done()
# a signature of a wrong type with a verifier that says True
en = Env(); en.u.verify = lambda d, s: True; a, b, c = pkg("1.0.0")
T(en.u.stage(a, 5, c) == "rejected:signature" and en.u.stage(a, [1], c) == "rejected:signature", "an integer or a list is not a signature"); en.done()
# a verifier that returns True and a signature that is not bytes
en = Env(); en.u.verify = lambda d, s: True; a, b, c = pkg("1.0.0")
T(en.u.stage(a, "text", c) == "rejected:signature" and en.u.stage(a, bytearray(b"x"), c) == "staged", "a signature that is not bytes is refused; a bytearray is accepted as bytes"); en.done()
# the active package damaged: found at start, the previous one (when it verifies) or the built-in one is used
en = fresh("1.0.0", "1.1.0"); en.u.at_restart(); open(P(en, "1.1.0", "model"), "wb").write(b"evil")
u = en.reopen()
T(u.state["active"] == "1.0.0" and u.state["previous"] is None and u.state["blocked"] == ["1.1.0"] and u.counters["active_damaged"] == 1 and not os.path.exists(P(en, "1.1.0")), "a damaged active package: the previous one is used, the damaged one is blocked and removed")
open(P(en, "1.0.0", "model"), "wb").write(b"evil"); u = en.reopen()
T(u.state["active"] == "builtin" and u.active_files() == {} and u.state["blocked"] == ["1.1.0", "1.0.0"], "the previous one damaged too: the built-in package")
en.done()
en = fresh("1.0.0", "1.1.0"); en.u.at_restart(); shutil.rmtree(P(en, "1.1.0")); u = en.reopen()
T(u.state["active"] == "1.0.0" and u.counters["active_damaged"] == 1, "the active directory is gone: the previous one is used"); en.done()
# a rollback to a damaged previous package goes to the built-in one
en = fresh("1.0.0", "1.1.0"); en.u.at_restart(); open(P(en, "1.0.0", "model"), "wb").write(b"evil")
T(en.u.rollback() == "rolled_back" and en.u.state["active"] == "builtin" and en.u.counters["previous_damaged"] == 1 and en.u.state["blocked"] == ["1.1.0"], "rollback never activates a damaged previous package"); en.done()
# an unreadable state: the packages it referred to are kept aside with it, not deleted
en = fresh("1.0.0"); open(os.path.join(en.root, "state.json"), "w").write("{bad"); u = en.reopen()
T(os.path.isdir(os.path.join(en.root, "packages.bad", "1.0.0")) and os.listdir(os.path.join(en.root, "packages")) == [] and u.state["active"] == "builtin" and os.path.exists(os.path.join(en.root, "state.json.bad")), "an unreadable state keeps its packages aside")
a, b, c = pkg("2.0.0"); u.stage(a, b, c); u.at_restart()
open(os.path.join(en.root, "state.json"), "w").write("{bad"); u = en.reopen()
T(os.listdir(os.path.join(en.root, "packages.bad")) == ["2.0.0"], "a second unreadable state replaces the aside copy by the newer one"); en.done()
# an interruption while staging (not an OSError) leaves nothing that the next start does not remove, and the state is untouched
en = fresh("1.0.0"); snap_state = open(os.path.join(en.root, "state.json")).read(); a, b, c = pkg("1.1.0"); realfsync = os.fsync
def intr(fd): raise KeyboardInterrupt()
os.fsync = intr
try:
    try: en.u.stage(a, b, c)
    except KeyboardInterrupt: pass
finally: os.fsync = realfsync
T(open(os.path.join(en.root, "state.json")).read() == snap_state, "an interrupted staging does not touch the state")
u = en.reopen(); T(sorted(os.listdir(os.path.join(en.root, "packages"))) == ["1.0.0"] and u.state["active"] == "1.0.0", "the next start removes what the interrupted staging left"); en.done()
# a failing manifest write while staging: storage failure, nothing left
en = fresh("1.0.0"); snap = tree(en.root); realdump = json.dump
def failing_dump(obj, fp, **kw):
    if isinstance(obj, dict) and "manifest" in obj: raise OSError("disk")
    return realdump(obj, fp, **kw)
json.dump = failing_dump
try: r = en.u.stage(*pkg("1.1.0"))
finally: json.dump = realdump
T(r == "rejected:storage" and tree(en.root) == snap, "a failing manifest write: nothing left"); en.done()
# validation sees the components only, never the manifest file
seen = []
en = Env(validate=lambda v, p: seen.append(sorted(p)) or True); a, b, c = pkg("1.0.0"); en.u.stage(a, b, c); en.u.at_restart()
T(seen == [["calibration", "model"]], "the validator is given the components only"); en.done()

# ---- the staged rollout
for bucket, pct, want in ((0, 100, "staged"), (99, 100, "staged"), (99, 99, "not_yet"), (0, 1, "staged"), (1, 1, "not_yet"), (0, 0, "not_yet"), (50, 50, "not_yet"), (49, 50, "staged")):
    e = Env(bucket=bucket); a, b, c = pkg("1.0.0", pct=pct); T(e.u.stage(a, b, c) == want, f"bucket {bucket}, rollout {pct}: {want}")
    T(want == "staged" or (e.u.state["staged"] is None and tree(e.root) == [] and e.nt.pending == []), "a package the rollout has not reached is neither stored nor reported")
    e.done()
for bad in (100, -1, True, None, "5", 5.0):
    e = Env(bucket=bad); a, b, c = pkg("1.0.0"); T(e.u.stage(a, b, c) == "rejected:bucket", f"an invalid bucket {bad!r} is refused"); e.done()
e = Env(bucket=50); a, b, c = pkg("1.0.0", pct=10); e.u.stage(a, b, c); a, b, c = pkg("1.0.0", pct=60); T(e.u.stage(a, b, c) == "staged", "the rollout widens: the same version reaches the device later"); e.done()
# ---- nothing leaves the directory; component names cannot be paths
e = Env(); a, b, c = pkg("1.0.0", {"../x": b"x"}); T(e.u.stage(a, b, c) == "rejected:components" and not os.path.exists(os.path.join(e.root, "..", "x")), "a component name is never a path"); e.done()
print(f"OK ({CHECKS} update checks; fake signature, temporary directory only; no download, no real signature, no installer, no real restart)")
