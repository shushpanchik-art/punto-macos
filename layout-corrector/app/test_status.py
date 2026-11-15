"""AP-2 status and pause: the four labels, pause = gate DENY (nothing recorded), resume, precedence readings. Simulated field only; the real icon is NOT RUN."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lfstatus as ST, lfruntime as R, lfengine as L
CHECKS = 0
def T(c, w):
    global CHECKS
    CHECKS += 1
    if not c: raise AssertionError(w)
M1 = {L.READ_RANGE, L.REPLACE_RANGE, L.READBACK, L.ROLLBACK}
def new(app="A", support="AUTO", caps=M1):
    rt = R.Runtime(L.Engine(L.example_cal(), lambda ids: [-3, 9, -2], {"en": {"hello"}, "ru": {"мир"}}), L.HookHealth(canary=False))
    f = L.SimField("", caps); rt.on_focus(app, f, support); rt.on_gate(L.GATE_ALLOW); return rt, f
def typed(rt, f, w, t0):
    for i, (ch, k) in enumerate(zip(w, L.keys_from_text(w, "en"))):
        f.type_user(ch); rt.on_hook_event(L.Event("key", k, "en", t0 + i), sig=("k", t0 + i))
def space(rt, f, t): f.type_user(" "); return rt.on_hook_event(L.Event("space", None, "en", t))

T(ST.LABELS == ("Active", "Paused", "Manual only", "Off"), "the four labels of AP-2")
rt, f = new(); T(ST.status(rt) == ("Active", []), "Active")
rt, f = new(support="MANUAL"); T(ST.status(rt)[0] == "Manual only" and ST.status(rt)[1] == ["support_manual"], "Manual only: the reason is named")
rt, f = new(support="UNKNOWN"); T(ST.status(rt)[0] == "Off", "an unknown application: Off")
rt = R.Runtime(L.Engine(L.example_cal(), lambda ids: [-3, 9, -2], {}), L.HookHealth(canary=False)); T(ST.status(rt) == ("Off", ["no_focus"]), "nothing focused: Off")
rt, f = new(); rt.permission_ok = False; rt.apply_mode(); T(ST.status(rt) == ("Off", ["permission"]), "a missing permission: Off and the icon can name it")
rt.set_paused(True); T(ST.status(rt) == ("Off", ["permission"]), "paused with a missing permission still says Off and why (my reading)")
rt, f = new(); rt.instance_ok = False; rt.apply_mode(); T(ST.status(rt) == ("Off", ["instance"]), "no instance lock: Off")
rt, f = new(); rt.set_blacklist = None if False else None; rt.apps["A"].blacklisted = True; rt.apply_mode(); T(ST.status(rt)[0] == "Off" and "blacklist" in ST.status(rt)[1], "blacklisted application: Off")
rt, f = new(); rt.auto_enabled = False; rt.apply_mode(); T(ST.status(rt) == ("Manual only", ["auto_off"]), "automatic correction off: Manual only")

# ---- pause
rt, f = new()
rt.set_paused(True); T(ST.status(rt) == ("Paused", ["paused"]) and rt.engine.gate == L.GATE_DENY and rt.health.gate_open is False, "paused: label, gate DENY, no signatures queued")
typed(rt, f, "ghbdtn", 100); space(rt, f, 106)
T(f.text == "ghbdtn " and rt.engine.run == [], "while paused nothing is converted and nothing is recorded")
rt.on_gate(L.GATE_ALLOW); T(rt.engine.gate == L.GATE_DENY and ST.status(rt)[0] == "Paused", "the adapter cannot lift the pause")
rt.on_focus("B", L.SimField("", M1), "AUTO"); T(rt.engine.gate == L.GATE_DENY and rt.health.gate_open is False, "a focus change keeps the gate DENY even before the adapter answers"); rt.on_gate(L.GATE_ALLOW); T(rt.engine.gate == L.GATE_DENY, "a focus change does not lift it either")
rt.on_focus("A", f, "AUTO"); rt.on_gate(L.GATE_ALLOW)
rt.set_paused(False); T(rt.engine.gate == L.GATE_ALLOW and ST.status(rt)[0] == "Active" and rt.health.gate_open is True, "resume: the last verdict comes back without a new adapter call")
f2 = L.SimField("", M1); rt.on_focus("A", f2, "AUTO"); rt.on_gate(L.GATE_ALLOW); typed(rt, f2, "ghbdtn", 1000); space(rt, f2, 1006)
T("привет" in f2.text, f"after the resume a new word is converted ({f2.text!r})")
# a word in progress is dropped by pausing and by resuming
rt, f = new(); typed(rt, f, "ghb", 100); rt.set_paused(True); T(rt.engine.run == [], "pausing drops the word in progress")
rt.set_paused(False); typed(rt, f, "dtn", 110); d = space(rt, f, 114)
T(f.text == "ghbdtn " , f"the rest of a half-typed word is not converted after a resume ({f.text!r})")
# idempotence and validation
rt, f = new(); rt.set_paused(True); rt.set_paused(True); rt.set_paused(False); rt.set_paused(False); T(rt.engine.gate == L.GATE_ALLOW and not rt.paused, "repeated calls are harmless")
for bad in (1, 0, "yes", None, [True]):
    try: rt.set_paused(bad); T(False, f"set_paused accepted {bad!r}")
    except ValueError: T(True, "")
# pause with unknown gate keeps DENY; resume restores UNKNOWN, not ALLOW
rt, f = new(); rt.on_gate(L.GATE_UNKNOWN); rt.set_paused(True); rt.set_paused(False); T(rt.engine.gate == L.GATE_UNKNOWN, "resume never turns an UNKNOWN gate into ALLOW")
rt, f = new(); rt.on_gate(L.GATE_DENY); rt.set_paused(True); rt.set_paused(False); T(rt.engine.gate == L.GATE_DENY, "nor a DENY gate")
# "Pause for this application" is the application list's blacklist entry (AP-4 re-enable button undoes it)
rt, f = new(); rt.blacklist("A", True); T(ST.status(rt)[0] == "Off" and rt.engine.mode == "OFF", "pause for this application: that application is Off")
rt.blacklist("A", False); T(ST.status(rt)[0] == "Active", "and back")
# quarantine shows Off, not Paused
rt, f = new(); rt.apps["A"].quarantined = True; rt.apply_mode(); T(ST.status(rt) == ("Off", ["quarantine"]), "a quarantined application: Off with its reason")
rt.set_paused(True); T(ST.status(rt)[0] == "Paused", "paused wins over a per-application Off (my reading)")
print(f"OK ({CHECKS} status and pause checks; simulated field; the real icon and the real click are NOT RUN)")
