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
T(rt.hotkey_convert(2100).reason == "no_word" and fld.text == "ghbdtn ", "the hotkey still works; the caret is behind a Space, so there is no word")

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

# 12. U-2: an empty selection converts the last token before the caret, only through the manual transaction
for caps in (M1, M2):
    rt, fld = make(caps=caps, support="MANUAL", text="say ghbdtn")
    r = rt.hotkey_convert(10)
    T(r.outcome == "VERIFIED" and fld.text == "say привет" and fld.selection() == (10, 10), f"U-2: last word converted, {sorted(caps)[0]}")
    T(rt.hotkey_toggle(20).outcome == "VERIFIED" and fld.text == "say ghbdtn", "U-2: the toggle brings the last word back")
rt, fld = make(support="MANUAL", text="ghbdtn ")
T(rt.hotkey_convert(10).reason == "no_word" and fld.text == "ghbdtn ", "U-2: the caret behind a space has no word")
rt, fld = make(support="MANUAL", text="")
T(rt.hotkey_convert(10).reason == "no_word", "U-2: an empty field")
rt, fld = make(support="MANUAL", text="a " + "x" * 300)          # longer than the first read window
r = rt.hotkey_convert(10)
T(r.outcome == "VERIFIED" and fld.text == "a " + "ч" * 300, "U-2: a token longer than the first window")
rt, fld = make(support="MANUAL", text="x" * 10_001)
T(rt.hotkey_convert(10).reason == "length" and fld.text == "x" * 10_001, "U-2: more than 10,000 characters writes nothing")
rt, fld = make(support="UNKNOWN", text="ghbdtn")
T(rt.hotkey_convert(10).reason == "mode_off" and fld.text == "ghbdtn", "U-2: mode OFF writes nothing")
rt, fld = make(support="MANUAL", text="ghbdtn", faults={("read", 1): "none"})
T(rt.hotkey_convert(10).reason == "not_readable" and fld.text == "ghbdtn", "U-2: an unreadable field writes nothing")
rt, fld = make(support="MANUAL", text="ghbdtn", faults={("read", 2): "user:q"})
r = rt.hotkey_convert(10)
T(r.outcome != "VERIFIED" or fld.text != "привет", "U-2: a user key during the transaction is never VERIFIED over it")

# 13. _word_before: the largest read is MANUAL_MAX + 2 and the window grows 64, 256, 1024, 4096, 10002
class CountRead(L.SimField):
    sizes = None
    def read(self, a, b):
        self.sizes.append(b - a)
        return super().read(a, b)
for n, want_ok in ((9_999, True), (10_000, True), (10_001, False), (20_000, False)):
    fld = CountRead("a " + "x" * n, M1); fld.sizes = []
    rt = R.Runtime(L.Engine(L.example_cal(), scorer, {}), L.HookHealth(canary=False)); rt.on_focus("app.t", fld, "MANUAL"); rt.on_gate(L.GATE_ALLOW)
    fld.sizes.clear()
    w = rt._word_before(len(fld.text))
    T(max(fld.sizes) <= L.MANUAL_MAX + 2, f"U-2: no read longer than MANUAL_MAX + 2 for a token of {n}: {fld.sizes}")
    T(len(w) == n if n <= L.MANUAL_MAX else len(w) > L.MANUAL_MAX, f"U-2: the token of {n} is found whole or refused as too long")
    fld.sizes.clear()
    r = rt.hotkey_convert(5)
    T((r.outcome == "VERIFIED") == want_ok and (want_ok or r.reason == "length"), f"U-2: boundary, token of {n}: {r.outcome} {r.reason}")
fld = CountRead("a " + "x" * 5000, M1); fld.sizes = []
rt = R.Runtime(L.Engine(L.example_cal(), scorer, {}), L.HookHealth(canary=False)); rt.on_focus("app.t", fld, "MANUAL"); rt.on_gate(L.GATE_ALLOW)
rt._word_before(len(fld.text))
T(fld.sizes == [64, 256, 1024, 4096, 5002], f"U-2: the window grows 64, 256, 1024, 4096 and stops at the start of the field: {fld.sizes}")
fld = CountRead("a " + "x" * 20_000, M1); fld.sizes = []
rt = R.Runtime(L.Engine(L.example_cal(), scorer, {}), L.HookHealth(canary=False)); rt.on_focus("app.t", fld, "MANUAL"); rt.on_gate(L.GATE_ALLOW)
fld.sizes.clear(); rt._word_before(len(fld.text))
T(fld.sizes == [64, 256, 1024, 4096, 10002], f"U-2: a very long token stops at MANUAL_MAX + 2: {fld.sizes}")


# 14. fault injection (audit 6): an adapter that answers with something unusable never raises into the caller and never writes
class Wrap:
    def __init__(self, f, **ov): self.f, self.ov = f, ov
    def __getattr__(self, n): return self.ov[n] if n in self.ov else getattr(self.f, n)
def wrapped(**ov):
    f = L.SimField("say ghbdtn", M1); rt = R.Runtime(L.Engine(L.example_cal(), scorer, {"en": {"hello"}, "ru": {"привет"}}), L.HookHealth(canary=False))
    rt.on_focus("app.t", Wrap(f, **ov), "AUTO"); rt.on_gate(L.GATE_ALLOW); return rt, f
for label, rd in (("an int", lambda s, e: 5), ("bytes", lambda s, e: b"ghbdtn"), ("a list", lambda s, e: ["g"])):
    rt, f = wrapped(selection=lambda: (4, 10), read=rd)
    try: r = rt.hotkey_convert(1000); err = None
    except Exception as e: r, err = None, e
    T(err is None and r.outcome == "ABORTED" and r.reason == "not_readable" and f.text == "say ghbdtn", f"read of the selection returns {label}: ABORTED not_readable, no exception, nothing written ({err!r})")
    T("ghbdtn" not in repr(rt.notices) + repr(r), "and no text in the notices or the result")
asked = []
rt, f = wrapped(selection=lambda: (0, 10 ** 9), read=lambda s, e: asked.append((s, e)) or "x")
r = rt.hotkey_convert(1000)
T(r.outcome == "ABORTED" and r.reason == "length" and asked == [], f"a selection of 10**9 characters is refused as 'length' before any read ({asked})")
rt, f = wrapped(selection=lambda: (10, 4), read=lambda s, e: asked.append((s, e)) or "x")
T(rt.hotkey_convert(1000).outcome == "ABORTED", "a reversed selection is handled without an exception")
asked.clear(); rt, f = wrapped(selection=lambda: (0, L.MANUAL_MAX), read=lambda s, e: asked.append((s, e)) or "a" * (e - s))
r = rt.hotkey_convert(1000); T(asked and asked[0] == (0, L.MANUAL_MAX) and r.reason != "length", "a selection of exactly MANUAL_MAX is still read and not refused as too long (the limit is inclusive)")
# a focus event whose element cannot be described: the old element must not stay active
class BadCaps:
    @property
    def caps(self): raise OSError("injected")
class NotIter:
    caps = 5
for label, ad in (("raises", BadCaps()), ("is not iterable", NotIter())):
    rt, fld = make(); type_word(rt, fld, "he", "en", 100, space=False)
    try: ok = rt.on_focus("app.new", ad, "AUTO"); err = None
    except Exception as e: ok, err = None, e
    T(err is None and ok is False and rt.ad is None and rt.app_id is None and rt.engine.mode == "OFF" and rt.gate_verdict == L.GATE_UNKNOWN, f"focus event whose caps {label}: no exception, engine OFF, the old element is let go ({err!r})")
    T(rt.engine.snapshot is None and rt.hotkey_convert(5).reason == "mode_off", "and nothing of the old element survives")
    T(rt.on_focus("app.ok", L.SimField("", M1), "AUTO") is True and rt.ad is not None, "a later working focus event recovers")

# 15. shutdown: every wipe step runs even when an earlier one fails; the first failure is still raised; a repeated shutdown is harmless
def boom(*a, **k): raise RuntimeError("injected")
for obj, name in (("engine", "on_event"), ("engine", "set_gate"), ("health", "set_gate_open")):
    rt, fld = make(); type_word(rt, fld, "he", "en", 100, space=False)
    o = getattr(rt, obj); orig = getattr(o, name); setattr(o, name, boom)
    try: rt.shutdown(); err = None
    except RuntimeError as e: err = e
    finally: setattr(o, name, orig)
    T(err is not None and rt.ad is None and rt.app_id is None and rt.engine.mode == "OFF", f"shutdown with a failing {obj}.{name}: the failure is raised, the adapter is let go, the engine is OFF")
    rt.shutdown(); rt.shutdown(); T(rt.ad is None and rt.engine.mode == "OFF", "a repeated shutdown does nothing more")
rt, fld = make(); orig = rt.engine.set_mode; rt.engine.set_mode = boom
try: rt.shutdown(); err = None
except RuntimeError as e: err = e
finally: rt.engine.set_mode = orig
T(err is not None and rt.ad is None and rt.app_id is None, "shutdown with a failing set_mode: later steps (adapter release) still ran")
# a focus event that fails also sends the engine an explicit break (defence in depth, in addition to the mode change)
rt, fld = make(); events = []; o = rt.engine.on_event
rt.engine.on_event = lambda ev: (events.append(ev.kind), o(ev))[1]
rt.on_focus("app.new", BadCaps(), "AUTO")
T("break" in events, "a failed focus event sends the engine a break")
print(f"OK ({CHECKS} runtime checks)")
