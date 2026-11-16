"""AP-8 notifications, portable part: 24 h limit (boundaries), one action per notice, no free text, links to runtime reasons, settings and store notices,
adapter failures. Fake adapter and fake clock only; the real notification display is NOT RUN."""
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lfnotify as N, lfruntime as R, lfengine as L, lfsettings as G, lfstore as S

CHECKS = 0
def T(c, w):
    global CHECKS
    CHECKS += 1
    if not c: raise AssertionError(w)
class Clock:
    def __init__(self, t=1000): self.t = t
    def __call__(self): return self.t
M1 = {L.READ_RANGE, L.REPLACE_RANGE, L.READBACK, L.ROLLBACK}
def mk(show=None, **kw):
    shown = []
    clk = Clock()
    def default(n): shown.append(n); return True
    return N.Notifier(show or default, clk, **kw), clk, shown

# ---- catalogue: every kind has exactly one action from the allowed two, row numbers from 13.5, valid by itself
T(set(N.ACTIONS) == {"open_settings", "re_enable"}, "the two actions of AP-8")
for kind, (row, action) in N.CATALOGUE.items():
    n = N.build(kind, params={"permission": "input_monitoring"} if kind == "permission_missing" else ({"chord": "Pause"} if kind == "hotkey_fallback" else None))
    T(action in N.ACTIONS and n["takes_focus"] is False and N.validate(n) == [] and (row is None or row in (9, 10, 11, 12, 13, 14)), f"catalogue entry {kind}")
T(N.CATALOGUE["incident"] == (10, "re_enable") and N.CATALOGUE["permission_missing"] == (14, "open_settings") and N.CATALOGUE["watchdog"] == (9, "re_enable") and N.CATALOGUE["stream_lost"][0] == 13 and N.CATALOGUE["worker_failed_twice"][0] == 11, "rows 9, 10, 11, 13, 14 as in the table")
T(N.build("incident", "unrecovered")["text_id"] == "notice.incident.unrecovered" and N.build("incident", "restored")["text_id"] == "notice.incident.restored" and N.build("incident", "whatever")["text_id"] == "notice.incident.restored", "row 10: the UNRECOVERED wording is a different text; an unknown variant is not copied")
T(N.build("nope") is None, "unknown kind")
# validation refuses everything outside the allow-list
good = N.build("incident", "unrecovered", {"target": "com.example.A"})
T(N.validate(good) == [], "a good notice")
def bad(**ch):
    n = dict(good); n.update(ch); return N.validate(n) != []
T(bad(action="open_settings") and bad(action=None) and bad(action="a,b") and bad(action=["open_settings", "re_enable"]), "exactly one action, and the one of the kind")
T(bad(takes_focus=True) and bad(takes_focus=0) and bad(kind="x") and bad(row=9) and bad(text_id="ghbdtn привет") and bad(text_id="notice.a b"), "focus, kind, row, text id")
T(bad(params={"text": "ghbdtn"}) and bad(params={"target": "a\\nb".replace("\\n", "\n")}) and bad(params={"target": ""}) and bad(params={"target": "x" * 513}) and bad(params="x") and bad(params={"permission": "camera"}), "free text, control characters, long or empty target, bad permission")
T(N.validate({**N.build("worker_failed_twice"), "params": {"target": "A"}}) != [], "a target belongs only to the re_enable action")
T(N.validate(N.build("permission_missing")) != [], "row 14 names the permission")
T(N.validate(N.build("hotkey_fallback", params={"chord": "Ctrl+K+Z"})) != [] and N.validate(N.build("hotkey_fallback", params={"chord": "ghbdtn"})) != [], "a chord must be a valid chord")
N.CATALOGUE["zz"] = (None, "close_everything"); zz = N.build("zz"); T(N.validate(zz) != [], "an action outside the two is refused even if the catalogue were wrong"); del N.CATALOGUE["zz"]
T(N.validate(None) != [] and N.validate({}) != [] and N.validate({**good, "extra": 1}) != [], "shape")

# ---- the 24 hour limit, boundaries
nf, clk, shown = mk()
T(nf.submit("watchdog") == "queued" and len(nf.deliver()) == 1 and len(shown) == 1, "first notice is shown")
clk.t = 1000 + N.DAY_MS - 1; T(nf.submit("watchdog") == "suppressed" and nf.deliver() == [], "24 h minus 1 ms later: suppressed")
clk.t = 1000 + N.DAY_MS; T(nf.submit("watchdog") == "queued" and len(nf.deliver()) == 1 and len(shown) == 2, "exactly 24 h later: shown (my reading, listed)")
clk.t = 1000 + N.DAY_MS + 5; T(nf.submit("watchdog") == "suppressed", "the new slot starts at the new show")
clk.t = 10; T(nf.submit("watchdog") == "suppressed", "a clock that went backwards never opens a slot")
nf, clk, shown = mk()
T(nf.submit("watchdog") == "queued" and nf.submit("watchdog") == "duplicate" and len(nf.pending) == 1, "the same cause twice before delivery: one in the queue")
nf.deliver(); T(len(shown) == 1 and nf.counters["duplicate"] == 1, "delivered once, the repeat only counted")
T(all(isinstance(v, int) for v in nf.counters.values()), "counters are integers")
# causes are independent
nf, clk, shown = mk()
for k in ("watchdog", "stream_lost", "worker_failed_twice"): T(nf.submit(k) == "queued", k)
T([n["kind"] for n in nf.deliver()] == ["watchdog", "stream_lost", "worker_failed_twice"], "different causes: all shown, first come first served (the specification defines no priority)")
# incidents: restored and unrecovered are different causes; unrecovered is never hidden by an earlier restored one
nf, clk, shown = mk()
nf.submit("incident", "restored", {"target": "A"}); nf.deliver(); clk.t += 1000
T(nf.submit("incident", "restored", {"target": "A"}) == "suppressed" and nf.submit("incident", "unrecovered", {"target": "A"}) == "queued", "a later UNRECOVERED incident is shown although a RESTORED one was shown a moment ago")
# window other than 24 h only through the constructor (the constant itself is normative)
T(N.DAY_MS == 86_400_000, "24 hours")

# ---- adapter failures
def raising(n): raise OSError("display")
nf, clk, shown = mk(raising); nf.submit("watchdog")
for i in range(2): T(nf.deliver() == [] and len(nf.pending) == 1, f"failure {i + 1}: kept for another try")
T(nf.deliver() == [] and nf.pending == [] and nf.counters["dropped"] == 1 and nf.counters["show_failed"] == 2, "third failure: dropped and counted, never an exception")
T("watchdog" not in [c[0] for c in nf.last_shown], "a failed show does not use up the 24 h slot")
nf.show = lambda n: True; T(nf.submit("watchdog") == "queued" and len(nf.deliver()) == 1, "later the cause can be shown")
for odd in (None, "yes", 1, [1]):
    nf, clk, shown = mk(lambda n, odd=odd: odd); nf.submit("watchdog"); nf.deliver()
    T(nf.last_shown == {} and len(nf.pending) == 1, f"only an exact True counts as shown: {odd!r}")
def clock_bad(): raise RuntimeError("clock")
nf = N.Notifier(lambda n: True, clock_bad); T(nf.submit("watchdog") == "suppressed" and nf.counters["clock_failed"] == 1, "a failing clock: nothing shown, no exception")
nf, clk, shown = mk(); T(nf.submit("watchdog") == "queued", "queued"); nf.clock = clock_bad; T(nf.deliver() == [] and len(nf.pending) == 1, "a clock that fails at delivery: kept")
try:
    N.Notifier(lambda n: True, Clock(), permission="camera"); T(False, "permission name")
except ValueError:
    T(True, "bad permission name refused")
# the adapter receives a copy-safe, valid notice only
seen = []; nf, clk, shown = mk(lambda n: (seen.append(N.validate(n)), True)[1]); [nf.submit(k) for k in ("permission_missing", "stream_lost", "models_unavailable")]; nf.deliver()
T(seen == [[], [], []], "everything handed to the adapter is valid")

# ---- links to the runtime
def new_rt():
    rt = R.Runtime(L.Engine(L.example_cal(), lambda ids: [-3, 9, -2], {"en": {"hello"}, "ru": {"мир"}}), L.HookHealth(canary=False))
    f = L.SimField("", M1); rt.on_focus("com.example.A", f, "AUTO"); rt.on_gate(L.GATE_ALLOW); return rt, f
rt, f = new_rt(); nf, clk, shown = mk()
nf.poll_runtime(rt); T(nf.pending == [], "a healthy runtime: nothing")
rt.permission_ok = False; rt.apply_mode(); nf.poll_runtime(rt); nf.poll_runtime(rt)
T(nf.counters.get("duplicate", 0) == 0 and nf.counters.get("suppressed", 0) == 0, "a reason that stays is not submitted again at every poll")
T([n["kind"] for _, n, _ in nf.pending] == ["permission_missing"] and nf.pending[0][1]["params"] == {"permission": "input_monitoring"}, "a revoked permission: one notice naming the permission, a second poll adds nothing")
nf.deliver(); rt.permission_ok = True; rt.apply_mode(); nf.poll_runtime(rt); rt.permission_ok = False; rt.apply_mode(); nf.poll_runtime(rt)
T(nf.pending == [] and len(shown) == 1, "the reason came back within 24 h: suppressed")
rt.permission_ok = True; rt.models_ok = False; rt.watchdog_ok = False; rt.apply_mode(); nf.poll_runtime(rt)
T(sorted(n["kind"] for _, n, _ in nf.pending) == ["models_unavailable", "watchdog"], "reasons models and watchdog")
rt, f = new_rt(); nf, clk, shown = mk(); rt.health.hook_gap = None if False else None
rt.on_raw_key(500, ("sc", 1, "down")); rt.on_raw_key(900, ("sc", 2, "down")) if False else None
rt.notices.append(("stream_lost", "canary_missing")); nf.poll_runtime(rt); T([n["kind"] for _, n, _ in nf.pending] == ["stream_lost"], "the stream-lost event")
rt.notices.append(("stream_lost", "ghbdtn привет")); nf.poll_runtime(rt); T(len(nf.pending) == 1, "a second event of the same cause adds nothing, and its detail is never copied")
T("ghbdtn" not in repr(nf.pending) and "привет" not in repr(nf.pending), "no detail text in the queue")
# incident from a real replacement incident
rt, f = new_rt(); nf, clk, shown = mk()
class BadAd(L.SimField):
    pass
rt.notices.append(("incident", "UNRECOVERED:adapter_exception")); rt.incident_apps.append("com.example.A"); nf.poll_runtime(rt)
T(nf.pending[0][1]["text_id"] == "notice.incident.unrecovered" and nf.pending[0][1]["params"] == {"target": "com.example.A"} and nf.pending[0][1]["action"] == "re_enable", "an UNRECOVERED incident: its wording, one action, pointing at the application")
rt.notices.append(("incident", "RESTORED:verify")); rt.incident_apps.append("com.example.B"); nf.poll_runtime(rt)
T([n["text_id"] for _, n, _ in nf.pending] == ["notice.incident.unrecovered", "notice.incident.restored"] and nf.pending[1][1]["params"] == {"target": "com.example.B"}, "the next incident points at ITS application")
rt.notices.append(("incident", "garbage")); rt.incident_apps.append("x\ny"); nf.poll_runtime(rt); T(len(nf.pending) == 2, "a malformed incident: no new cause (restored already queued)")
rt.notices.append(("reenabled", "com.example.A")); rt.notices.append(("surprise", "ghbdtn")); nf.poll_runtime(rt)
T(len(nf.pending) == 2 and nf.counters["unknown"] == 1, "the user's own re-enable is not a notice; an unknown kind is counted, not shown")
# a REAL replacement incident end to end (the same fault as in test_runtime)
def scorer(ids): return [-3, 9, -2]
for kindfault, expect in (("autocorrect", None),):
    f = L.SimField("", M1, {("replace", 1): kindfault})
    rt = R.Runtime(L.Engine(L.example_cal(), scorer, {"en": {"hello"}, "ru": {"привет"}}), L.HookHealth(canary=False)); rt.on_focus("com.example.A", f, "AUTO"); rt.on_gate(L.GATE_ALLOW)
    nf, clk, shown = mk()
    for i, (ch, k) in enumerate(zip("ghbdtn", L.keys_from_text("ghbdtn", "en"))):
        f.type_user(ch); rt.on_hook_event(L.Event("key", k, "en", 1000 + i), sig=("k", 1000 + i))
    f.type_user(" "); rt.on_hook_event(L.Event("space", None, "en", 1006))
    nf.poll_runtime(rt); inc = [n for _, n, _ in nf.pending if n["kind"] == "incident"]
    T(rt.apps["com.example.A"].quarantined and len(inc) == 1 and inc[0]["params"] == {"target": "com.example.A"} and N.validate(inc[0]) == [] and inc[0]["text_id"] == "notice.incident." + ("unrecovered" if rt.last_result.outcome == "UNRECOVERED" else "restored"), f"a real {rt.last_result.outcome} incident reaches the notifier with its application and its wording")
# ---- settings and store notices
nf, clk, shown = mk()
nf.poll_list("settings", [("settings_not_saved", ""), ("autostart_failed", ""), ("hotkey_fallback", "Ctrl+Alt+Pause"), ("hotkey_unavailable", "")])
T([n["kind"] for _, n, _ in nf.pending] == ["settings_not_saved", "autostart_failed", "hotkey_fallback", "hotkey_unavailable"] and nf.pending[2][1]["params"] == {"chord": "Ctrl+Alt+Pause"}, "settings notices, the chord is a valid chord")
nf.poll_list("settings", [("settings_not_saved", ""), ("autostart_failed", ""), ("hotkey_fallback", "Ctrl+Alt+Pause"), ("hotkey_unavailable", ""), ("hotkey_fallback", "ghbdtn")]); T(len(nf.pending) == 4 and nf.counters["invalid"] == 1, "only new entries are taken; a chord that is not a chord is invalid, not shown")
nf, clk, shown = mk(); nf.poll_list("store", ["cipher_unavailable", "file_unreadable_defaults", "newer_file_kept", "migrated"])
T([n["kind"] for _, n, _ in nf.pending] == ["cipher_unavailable", "file_unreadable_defaults", "newer_file_kept"], "store notices; the migration line is informational")
# a real store and settings object end to end
d = tempfile.mkdtemp(prefix="lfnot_")
class Locked(S.Cipher):
    def encrypt(self, x): raise S.CipherUnavailable("x")
    def decrypt(self, x): raise S.CipherUnavailable("x")
open(os.path.join(d, "settings.json"), "wb").write(b"opaque")
st = S.Store(os.path.join(d, "settings.json"), Locked()); state = st.load(); rt, f = new_rt(); sg = G.Settings(st, state, rt); sg.set_auto_correction(False)
nf, clk, shown = mk(); nf.poll_list("store", st.notices); nf.poll_list("settings", sg.notices)
T(sorted(n["kind"] for _, n, _ in nf.pending) == ["cipher_unavailable", "file_unreadable_defaults", "settings_not_saved"], "a real locked store and a failed save give their notices")
# ---- nothing typed anywhere
nf, clk, shown = mk(); rt, f = new_rt()
rt.notices += [("stream_lost", "ghbdtn привет"), ("incident", "UNRECOVERED:ghbdtn привет")]; rt.incident_apps.append("com.example.A")
nf.poll_runtime(rt); nf.deliver()
T(all(N.validate(n) == [] for n in shown) and "ghbdtn" not in repr(shown) + repr(nf.counters) and "привет" not in repr(shown) + repr(nf.pending), "no typed text in anything shown, queued or counted")

# ---- fault injection (audit 6): malformed input from other modules, an adapter that tampers with the notice it is given
import copy as _copy
nf = N.Notifier(lambda x: True, lambda: 0)
for label, entries in (("an empty tuple", [()]), ("None", [None]), ("a list as kind", [(["a"], "")]), ("an int", [5]), ("a bytes kind", [(b"x", "")])):
    try: nf.poll_list("src_" + label, entries); err = None
    except Exception as e: err = e
    T(err is None, f"poll_list with {label}: no exception ({err!r})")
T(nf.counters.get("malformed") == 5 and nf.pending == [], f"the malformed entries are counted, none is queued ({nf.counters})")
nf.poll_list("mixed", [(), "settings_not_saved", None, ("delete_failed", "")])
T([c for c, _, _ in nf.pending] == [("settings_not_saved", ""), ("delete_failed", "")], "one malformed entry does not stop the entries after it")
for label, args in (("params an int", ("incident", "", 5)), ("kind a list", (["x"],)), ("variant a list", ("incident", ["x"])), ("kind None", (None,))):
    try: r = nf.submit(*args); err = None
    except Exception as e: r, err = None, e
    T(err is None and r in ("invalid", "unknown"), f"submit with {label}: never raises ({err!r} {r})")
rt = R.Runtime(L.Engine(L.example_cal(), lambda ids: [-3, 9, -2], {"en": {"hello"}}), L.HookHealth(canary=False))
rt.notices += [(), ("stream_lost",), 7, ("watchdog", "")]
try: nf.poll_runtime(rt); err = None
except Exception as e: err = e
T(err is None, f"poll_runtime with malformed runtime notices: no exception ({err!r})")
seen = []
def tamper(n):
    seen.append(_copy.deepcopy(n))
    if len(seen) == 1:
        n["params"]["target"] = "SECRET TEXT"; n["text_id"] = "notice.evil"; raise OSError("x")
    return True
nf2 = N.Notifier(tamper, lambda: 0); nf2.submit("settings_not_saved"); nf2.deliver(); shown = nf2.deliver()
T(len(seen) == 2 and N.validate(seen[1]) == [] and seen[1]["text_id"] == "notice.settings_not_saved" and seen[1]["params"] == {}, f"an adapter that changes the notice it was given and then fails: the next attempt shows the validated notice ({seen[1:]})")
T(all(N.validate(n) == [] for n in shown), "and what deliver returns is valid")
print(f"OK ({CHECKS} notification checks; fake adapter and clock; no real notification display)")
