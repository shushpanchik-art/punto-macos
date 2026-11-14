"""AP-4 application list, blacklist, safe re-enable, Esc opt-in, and the persistence bridge (lfstore). Simulated fields only."""
import itertools, os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lfruntime as R
import lfstore as S
import lfengine as L

CHECKS = 0
def T(c, w):
    global CHECKS
    CHECKS += 1
    if not c: raise AssertionError(w)

M1 = {L.READ_RANGE, L.REPLACE_RANGE, L.READBACK, L.ROLLBACK}
M2 = {L.READ_RANGE, L.READBACK, L.SYNTHETIC_INPUT}
scorer = lambda ids: [-3, 9, -2]

def new_rt(**kw):
    return R.Runtime(L.Engine(L.example_cal(), scorer, {"en": {"hello"}, "ru": {"привет"}}), L.HookHealth(canary=False), **kw)

def focus(rt, app, fld, support="AUTO"):
    rt.on_focus(app, fld, support); rt.on_gate(L.GATE_ALLOW)

def word(rt, fld, w, t0):
    for i, (ch, k) in enumerate(zip(w, L.keys_from_text(w, "en"))):
        fld.type_user(ch); rt.on_hook_event(L.Event("key", k, "en", t0 + i), sig=("k", t0 + i))
    fld.type_user(" ")
    return rt.on_hook_event(L.Event("space", None, "en", t0 + len(w)))

# 1. the quarantine belongs to one application: it never follows the focus (the bug this found)
rt = new_rt(); fa, fb = L.SimField("", M1, {("replace", 1): "autocorrect"}), L.SimField("", M1)
focus(rt, "A", fa); word(rt, fa, "ghbdtn", 100)
T(rt.apps["A"].quarantined and rt.engine.mode == "OFF", "A: incident, quarantined, OFF")
focus(rt, "B", fb)
T(rt.engine.mode == "AUTO" and not rt.engine.quarantined, "B: AUTO, the engine does not carry A's quarantine")
d = word(rt, fb, "ghbdtn", 300)
T(d is not None and d.action == "CONVERT" and fb.text == "привет ", "B converts normally after A's incident")
focus(rt, "A", fa)
T(rt.engine.mode == "OFF" and rt.apps["A"].quarantined, "back in A: still quarantined and OFF")
rt.release_quarantine("B")
T(rt.apps["A"].quarantined and rt.engine.mode == "OFF", "releasing B never releases A")

# 2. explain() agrees with engine_mode for every combination of facts (blacklist aside)
n = 0
for caps, sup, perm, lay, mod, hk, wd, q in itertools.product((M1, M2, {L.READ_RANGE}, set()), ("UNKNOWN", "MANUAL", "AUTO"), (True, False), (True, False),
                                                              (True, False), (True, False), (True, False), (False, True)):
    rt = new_rt(models_ok=mod, permission_ok=perm)
    rt.layout_ok, rt.watchdog_ok = lay, wd
    f = L.SimField("", caps); focus(rt, "X", f, sup); rt.apps["X"].quarantined = q
    if not hk:
        rt.health._lose("canary_missing")
    mode, why = rt.explain("X")
    want = L.engine_mode(caps, sup, models_ok=mod, layout_ok=lay, permission_ok=perm, hook_ok=hk, watchdog_ok=wd, quarantined=q)
    T(mode == want and ((mode == "AUTO") == (why == [])), f"explain agrees with engine_mode: {caps} {sup} {perm} {lay} {mod} {hk} {wd} {q}: {mode} {why} {want}")
    n += 1
T(n == 4 * 3 * 64, "all combinations were checked")

# 3. the list, the blacklist and the re-enable
rt = new_rt(); fa = L.SimField("", M1, {("replace", 1): "autocorrect"}); fm = L.SimField("", M2)
focus(rt, "A", fa); word(rt, fa, "ghbdtn", 100)
focus(rt, "M", fm, "MANUAL")
rows = {r["app"]: r for r in rt.app_list()}
T(rows["A"]["mode"] == "OFF" and rows["A"]["reasons"] == ["quarantine"] and rows["A"]["can_reenable"] and rows["A"]["incidents"] == 1, "list: A quarantined, one counted incident")
T(rows["M"]["mode"] == "MANUAL_ONLY" and rows["M"]["reasons"] == ["support_manual", "no_auto_capability"] and not rows["M"]["can_reenable"], "list: M MANUAL_ONLY with its reasons")
focus(rt, "A", fa)
res = rt.reenable("A")
T(res == ("AUTO", []) and rt.apps["A"].support == "AUTO" and rt.apps["A"].incidents == 1 and ("reenabled", "A") in rt.notices, "re-enable: AUTO, support and incident counter unchanged")
fa.faults[("replace", fa.count["replace"] + 1)] = "autocorrect"
word(rt, fa, "ghbdtn", 500)
T(rt.apps["A"].quarantined and rt.apps["A"].incidents == 2, "the next incident quarantines again")
T(rt.reenable("nope") is None, "re-enable of an unknown application")

# re-enable never grants more than the facts allow
for kw, why in (({"permission_ok": False}, ["permission"]), ({"models_ok": False}, ["models"])):
    rt = new_rt(**kw); f = L.SimField("", M1); focus(rt, "A", f); rt.apps["A"].quarantined = True; rt.apply_mode()
    mode, r = rt.reenable("A")
    T(r == why and mode == ("OFF" if "permission" in why else "MANUAL_ONLY"), f"re-enable does not override {why}")
rt = new_rt(); f = L.SimField("", M1); focus(rt, "A", f, "UNKNOWN"); rt.apps["A"].quarantined = True
T(rt.reenable("A") == ("OFF", ["support_unknown"]) and rt.apps["A"].support == "UNKNOWN", "re-enable never changes the support status")

# a stale word and snapshot do not survive a re-enable
rt = new_rt(); f = L.SimField("", M1); focus(rt, "A", f)
for i, (ch, k) in enumerate(zip("ghb", L.keys_from_text("ghb", "en"))):
    f.type_user(ch); rt.on_hook_event(L.Event("key", k, "en", 10 + i), sig=("k", i))
T(len(rt.engine.run) > 0, "setup: a word is in progress")
rt.apps["A"].quarantined = True; rt.reenable("A")
T(rt.engine.run == [], "re-enable of the focused application starts from a clean state")

# blacklist
rt = new_rt(); f = L.SimField("", M1); focus(rt, "A", f)
rt.blacklist("A")
d = word(rt, f, "ghbdtn", 100)
T(d is None and f.text == "ghbdtn " and rt.engine.mode == "OFF" and rt.explain("A") == ("OFF", ["blacklist"]), "a blacklisted application records and converts nothing")
T(rt.app_list()[0]["can_reenable"], "the list offers the re-enable for a blacklisted application")
T(rt.reenable("A") == ("AUTO", []), "re-enable removes the blacklist")
rt.blacklist("new.app"); T(rt.explain("new.app") == ("OFF", ["blacklist", "support_unknown"]), "a blacklist entry may precede the first focus")

# 4. persistence: only the two user choices go to the file
rt = new_rt(); f = L.SimField("", M1, {("replace", 1): "autocorrect"}); focus(rt, "A", f); word(rt, f, "ghbdtn", 100)
focus(rt, "B", L.SimField("", M1)); rt.blacklist("B"); rt.apps["B"].esc_undoes = True
P = rt.prefs()
T(P == {"B": {"blacklist": True, "esc_undoes": True}}, f"only the user's choices are persisted, not quarantine or incidents: {P}")
d = tempfile.mkdtemp(); st = S.Store(os.path.join(d, "s.json"), S.TestOnlyCipher(b"k"), allow_test_cipher=True)
state = st.load(); state.apps = P; st.save(state)
raw = open(st.path, encoding="utf-8").read()
T("quarantin" not in raw and "incident" not in raw, "the file has no quarantine and no incident")
rt2 = new_rt(); rt2.load_prefs(S.Store(st.path, S.TestOnlyCipher(b"k"), allow_test_cipher=True).load().apps)
T(rt2.apps["B"].blacklisted and rt2.apps["B"].esc_undoes and not rt2.apps.get("A"), "after a restart: the choices are back, the quarantine of A is gone")

# 5. Esc undoes only where the user opted in
rt = new_rt(); f = L.SimField("", M1); focus(rt, "A", f); word(rt, f, "ghbdtn", 100)
T(rt.on_esc(200) is None and f.text == "привет ", "Esc without the opt-in does nothing")
rt.apps["A"].esc_undoes = True
r = rt.on_esc(300)
T(r is not None and r.outcome == "VERIFIED" and f.text == "ghbdtn ", "Esc with the opt-in undoes")
T(rt.on_esc(400) is None, "Esc with nothing to undo does nothing")
print(f"OK ({CHECKS} application list and re-enable checks; simulated fields, temporary files)")
