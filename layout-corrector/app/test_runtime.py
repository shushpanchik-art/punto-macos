"""Tests of lfruntime.py against the simulated field of the reference (SimField). Run: python3 test_runtime.py
They test the runtime glue (gate -> HookHealth, gap -> mode, incident -> quarantine, hotkeys), not an OS adapter:
`SimField` is a test double, so nothing here is evidence about a real application (that is INTEGRATION_VERIFIED work)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lfruntime as R  # noqa: E402
L = R.L

CHECKS = 0


def T(cond, what):
    global CHECKS
    CHECKS += 1
    if not cond:
        raise AssertionError(what)


M1 = {L.READ_RANGE, L.REPLACE_RANGE, L.READBACK, L.ROLLBACK}
M2 = {L.READ_RANGE, L.READBACK, L.SYNTHETIC_INPUT}
scorer = lambda ids: [-3, 9, -2]


def make(caps=M1, support="AUTO", canary=False, faults=None, text=""):
    fld = L.SimField(text, caps, faults)
    rt = R.Runtime(L.Engine(L.example_cal(), scorer, {"en": {"hello"}, "ru": {"привет"}}), L.HookHealth(canary=canary))
    rt.on_focus("app.test", fld, support)
    rt.on_gate(L.GATE_ALLOW)
    return rt, fld


def type_word(rt, fld, word, lay, t0, space=True):
    for i, (ch, k) in enumerate(zip(word, L.keys_from_text(word, lay))):
        fld.type_user(ch)
        if rt.health.canary:
            rt.on_raw_key(t0 + i, ("k", t0 + i))              # the independent observer sees the same physical key
        rt.on_hook_event(L.Event("key", k, lay, t0 + i), sig=("k", t0 + i))
    d = None
    if space:
        fld.type_user(" ")
        d = rt.on_hook_event(L.Event("space", None, lay, t0 + len(word)))
    return d


# 1. an automatic conversion end to end: the field holds the converted word and the Space, the undo works at once
rt, fld = make()
T(rt.engine.mode == "AUTO", "AUTO on a full-capability field with status AUTO")
d = type_word(rt, fld, "ghbdtn", "en", 1000)
T(d.action == "CONVERT" and fld.text == "привет " and rt.last_result.outcome == "VERIFIED", "automatic conversion VERIFIED")
T(rt.engine.snapshot is not None and rt.engine.snapshot.confirmed, "VERIFIED confirms the undo snapshot")
r = rt.hotkey_undo(2000)
T(r is not None and r.outcome == "VERIFIED" and fld.text == "ghbdtn ", "undo restores the typed text")
T(("en2ru", "ghbdtn") in rt.engine.exceptions and rt.engine.snapshot is None, "a VERIFIED undo learns the exception")

# 2. undo after further typing (U-1): the word is restored, what the user typed since is untouched
rt, fld = make()
type_word(rt, fld, "ghbdtn", "en", 1000)
fld.type_user("x"); rt.on_hook_event(L.Event("key", L.keys_from_text("x", "en")[0], "en", 1100), sig=("k", 1))
r = rt.hotkey_undo(1200)
T(r is not None and r.outcome == "VERIFIED" and fld.text == "ghbdtn x" and ("en2ru", "ghbdtn") in rt.engine.exceptions,
  "U-1: undo after typing restores the word and keeps the typed character")

# 3. status UNKNOWN or MANUAL: no automatic conversion, no recording
for st in ("UNKNOWN", "MANUAL"):
    rt, fld = make(support=st)
    d = type_word(rt, fld, "ghbdtn", "en", 1000)
    T(d is None and fld.text == "ghbdtn " and rt.engine.mode == ("OFF" if st == "UNKNOWN" else "MANUAL_ONLY"), f"status {st}: nothing is converted")

# 4. an incident quarantines the application: RESTORED and UNRECOVERED always do
rt, fld = make(faults={("replace", 1): "autocorrect"})
type_word(rt, fld, "ghbdtn", "en", 1000)
T(rt.last_result.outcome in ("RESTORED", "UNRECOVERED") and rt.apps["app.test"].quarantined and rt.engine.mode == "OFF"
  and rt.apps["app.test"].incidents == 1 and rt.notices[-1][0] == "incident", "incident: quarantine, mode OFF, one counted notice")
d = type_word(rt, fld, "ghbdtn", "en", 5000)
T(d is None, "a quarantined application records and converts nothing")
rt.release_quarantine("app.test")
T(rt.engine.mode == "AUTO", "an explicit release returns the mode")

# 5. a hook that raises an unexpected exception inside the adapter is an incident, never a crash
class Boom(L.SimField):
    def replace(self, *a):
        raise RuntimeError("adapter bug")
fld = Boom("", M1)
rt = R.Runtime(L.Engine(L.example_cal(), scorer, {}), L.HookHealth(canary=False))
rt.on_focus("app.boom", fld, "AUTO"); rt.on_gate(L.GATE_ALLOW)
type_word(rt, fld, "ghbdtn", "en", 1000)
T(rt.last_result.outcome in ("UNRECOVERED", "RESTORED") and rt.apps["app.boom"].quarantined, "an adapter exception is an incident")

# 6. the gate: DENY empties the HookHealth queues (L9 P-2) and stops recording
rt, fld = make(canary=True)
rt.on_raw_key(100, ("s", 1))
T(len(rt.health.raw_only) == 1, "setup: a raw signature waits for its counterpart")
rt.on_gate(L.GATE_DENY)
T(rt.health.raw_only == [] and rt.engine.on_event(L.Event("key", L.keys_from_text("g", "en")[0], "en", 110)) is None,
  "DENY: queues emptied, nothing recorded")
rt.on_raw_key(120, ("s", 2))
T(rt.health.raw_only == [], "DENY: a raw key is not queued")
rt.on_gate(L.GATE_ALLOW)
T(len(rt.health.raw_only) == 0 and rt.health.gate_open, "ALLOW opens the queue again, empty")

# 7. a lost key (Windows canary) = a gap, MANUAL_ONLY, the word and snapshot are discarded
rt, fld = make(canary=True)
type_word(rt, fld, "ghbdtn", "en", 1000, space=False)
rt.on_raw_key(1500, ("lost", 1))                       # the hook never reports it
rt.on_tick(1900)                                       # 400 ms later
T(not rt.health.ok and rt.engine.mode == "MANUAL_ONLY" and rt.engine.run == [] and ("stream_lost", "canary_missing") in rt.notices,
  "canary: a missing hook event drops to MANUAL_ONLY and discards the word")
fld.type_user(" ")
T(rt.on_hook_event(L.Event("space", None, "en", 2000)) is None and fld.text == "ghbdtn ", "no conversion while the stream is not trusted")
T(rt.hotkey_convert(2100).reason == "no_selection", "the hotkey still works, here it has no selection")

# 8. macOS: tap disabled -> MANUAL_ONLY; trusted again after enabling, 4th time in 60 s stays MANUAL_ONLY
rt, fld = make(canary=False)
for i, t in enumerate((1000, 2000, 3000, 4000)):
    rt.on_tap_disabled("timeout"); T(rt.engine.mode == "MANUAL_ONLY", f"tap disabled #{i + 1}: MANUAL_ONLY")
    rt.on_stream_restored(t)
    T((rt.engine.mode == "AUTO") == (i < 3), f"tap enabled again #{i + 1}: {'AUTO' if i < 3 else 'stays MANUAL_ONLY (flapping)'}")
rt.health.user_rearm(); rt.apply_mode()
T(rt.engine.mode == "AUTO", "the user re-arms AUTO after flapping")

# 9. manual conversion of a selection and the toggle; then any other event ends the toggle window
rt, fld = make(support="MANUAL", text="say ghbdtn now")
fld.select(4, 10)
r = rt.hotkey_convert(1000)
T(r.outcome == "VERIFIED" and fld.text == "say привет now", "hotkey converts the selection")
r = rt.hotkey_toggle(2000)
T(r is not None and r.outcome == "VERIFIED" and fld.text == "say ghbdtn now", "toggle brings the original back")
fld.select(4, 10); rt.hotkey_convert(3000)
rt.on_hook_event(L.Event("key", L.keys_from_text("x", "en")[0], "en", 3100))
T(rt.hotkey_toggle(3200) is None, "any user event ends the toggle window")

# 10. OFF: the hotkey does nothing; no selection: nothing
rt, fld = make(support="UNKNOWN", text="ghbdtn")
fld.select(0, 6)
T(rt.hotkey_convert(10).reason == "mode_off" and fld.text == "ghbdtn", "mode OFF: the hotkey writes nothing")

# 11. M2 field (no rollback): automatic conversion is never run, the hotkey may
rt, fld = make(caps=M2, support="AUTO", text="ghbdtn")
T(rt.engine.mode == "MANUAL_ONLY", "M2 alone is MANUAL_ONLY at best")
fld.select(0, 6)
r = rt.hotkey_convert(10)
T(r.outcome == "VERIFIED" and fld.text == "привет", "M2 hotkey converts the selection")

print(f"OK ({CHECKS} runtime checks)")
