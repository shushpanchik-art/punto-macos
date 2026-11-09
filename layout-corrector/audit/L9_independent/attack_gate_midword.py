"""F-B (P1): the engine records the TAIL of a word when the gate / the mode becomes ALLOW / AUTO in the middle of it,
and the transaction (which matches only old+' ' before the caret and never looks at the character in front of the
fragment) converts the tail and reports VERIFIED: 'Hello gпривет' instead of 'Hello ghbdtn' (or 'Hello привет').
13.1: 'A focus-change notification sets the cache to UNKNOWN at once' - the keys typed while it is UNKNOWN are not
recorded; the verdict then turns ALLOW in the middle of the word (that is the normal sequence when the user starts typing
at once after focusing a field).  Engine.set_gate(ALLOW) and Engine.set_mode(AUTO) do not set `skip` (the way `gap` does),
so the rest of a word whose head was never recorded is classified as a word.
13.2 'A word starts with the first printable key after a Space or a break' is true of the recorder, but the word
in the FIELD started earlier.
 (a) focus: gate UNKNOWN -> ALLOW after 1 key       (b) mode MANUAL_ONLY -> AUTO after 1 key (hook trusted again)
 (c) HookHealth: the hook lost the first key; the canary has not fired at the Space (word typed in < 300 ms)
Run: python3 attack_gate_midword.py"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "work"))
import lfengine as L

M1 = {L.READ_RANGE, L.REPLACE_RANGE, L.READBACK, L.ROLLBACK}
scorer = lambda ids: [-3, 9, -2]


def pipeline(label, drive, field_text="Hello ghbdtn "):
    e = L.Engine(L.example_cal(), scorer, {})
    f = L.SimField("Hello ", M1)
    d, seen = drive(e, f)
    old = L.render(seen, "en")
    print(label)
    print("   engine saw %r -> %s %s" % (old, d.action, d.reason))
    if d.action == "CONVERT":
        r = L.run_transaction(f, old, d.replacement, "")
        e.on_outcome(r.outcome)
        bad = r.outcome == "VERIFIED" and f.text != "Hello привет "
        print("   transaction: %s %s   field=%r   %s" % (r.outcome, r.reason, f.text,
              "<== SILENT HALF-CONVERTED WORD (VERIFIED)" if bad else ""))
        return bad
    return False


def typ(e, f, text, t0, seen=None, record=True):
    for i, k in enumerate(L.keys_from_text(text, "en")):
        f.type_user(L.render_key(k, "en"))
        if record and seen is not None:
            seen.append(k)
        e.on_event(L.Event("key", k, "en", t0 + i * 40))


def a(e, f):
    seen = []
    e.set_gate("UNKNOWN")                                    # focus change: nothing is recorded
    typ(e, f, "g", 1000, record=False)                        # first key: typed at once, verdict not there yet
    e.set_gate("ALLOW")                                       # the verdict arrives
    typ(e, f, "hbdtn", 1100, seen)
    f.type_user(" ")
    return e.on_event(L.Event("space", None, "en", 1400)), seen


def b(e, f):
    seen = []
    e.set_mode("MANUAL_ONLY")                                 # e.g. the hook was lost; the engine records nothing
    typ(e, f, "g", 1000, record=False)
    e.set_mode("AUTO")                                        # the hook is trusted again (3 pairs) in the middle of the word
    typ(e, f, "hbdtn", 1100, seen)
    f.type_user(" ")
    return e.on_event(L.Event("space", None, "en", 1400)), seen


def c(e, f):
    """HookHealth: the hook lost 'g' (raw observer saw it).  The word is typed in 250 ms, the Space comes at 280 ms."""
    hh = L.HookHealth()
    seen, t = [], 1000
    keys = L.keys_from_text("ghbdtn", "en")
    for i, k in enumerate(keys):
        f.type_user(L.render_key(k, "en"))
        hh.raw_key(t + i * 40, ("scan", k.id, "down"))
        if i > 0:                                             # the hook delivered every key except the first
            hh.hook_key(t + i * 40 + 1, ("scan", k.id, "down"))
            seen.append(k)
            e.on_event(L.Event("key", k, "en", t + i * 40 + 1))
        hh.check(t + i * 40 + 2)
    f.type_user(" ")
    hh.raw_key(t + 280, ("scan", 99, "down")); hh.hook_key(t + 281, ("scan", 99, "down"))
    ok = hh.check(t + 282)
    print("   HookHealth at the Space: ok=%s (the loss is declared only after %d ms)" % (ok, L.HookHealth.CANARY_MS))
    return e.on_event(L.Event("space", None, "en", t + 281)), seen


n = 0
n += pipeline("(a) focus: gate UNKNOWN -> ALLOW in the middle of the word", a)
n += pipeline("(b) mode MANUAL_ONLY -> AUTO in the middle of the word", b)
n += pipeline("(c) the hook lost the first key, Space within 300 ms (canary not fired yet)", c)
print("silent half-converted words:", n, "of 3")
