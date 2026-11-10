"""Engine / mode / quarantine attacks (one section per finding).  Run: python3 attack_engine_state.py
 F6  snapshot + run credit are created at the DECISION, not at VERIFIED (13.2 step 7): undo works on a word that was never
     converted, and a crash between decision and outcome leaves snapshot and credit alive
 F7  an incident (RESTORED/UNRECOVERED) does not stop the engine: on_outcome only drops snapshot and credit, the next
     word is decided and converted at once (quarantine exists only as a flag in TxResult)
 F8  a layout change that arrives only as the layout id of a KEY (no 'layout' event) keeps the snapshot and does not set
     after_switch; inside a word it drops the word but keeps the snapshot
 F9  Backspace inside a dropped word is ignored without limit: the user can erase the converted word and the snapshot lives on
 F10 clock handling: undo(now) with now < created is never expired; ts_ms == 0 never ticks
 F11 exception list has no 10,000-entry limit and no LRU (13.3)
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "reference"))
import lfengine as L
import random

M1 = {L.READ_RANGE, L.REPLACE_RANGE, L.READBACK, L.ROLLBACK}
scorer = lambda ids: [-3, 9, -2]


def key_events(text, lay, t0):
    return [L.Event("key", k, lay, t0 + i) for i, k in enumerate(L.keys_from_text(text, lay))]


def word(e, text, lay="en", t0=1000):
    for ev in key_events(text, lay, t0):
        e.on_event(ev)
    return e.on_event(L.Event("space", None, lay, t0 + len(text)))


def new_engine():
    return L.Engine(L.example_cal(), scorer, {})


print("== F6: snapshot exists before the replacement has happened")
e = new_engine()
d = word(e, "ghbdtn")
field = L.SimField("ghbdtn ", M1)                 # the transaction has NOT run yet (worker busy / queued)
restore = e.undo(1500)                              # the undo chord arrives now
print("   decision:", d.action, "| snapshot alive before any write; undo() ->", repr(restore),
      "| exception added:", ("en2ru", "ghbdtn") in e.exceptions, "| field still", repr(field.text))
r = L.run_transaction(field, "ghbdtn", d.replacement)
e.on_outcome(r.outcome)
print("   then the transaction runs:", r.outcome, "-> field", repr(field.text), "| snapshot:", e.snapshot, "(the user's undo was consumed, the word is now a permanent exception, the conversion stands)")
e = new_engine()
d = word(e, "ghbdtn")
class GateBug(L.SimField):
    def gate(self):
        raise RuntimeError("unexpected adapter exception (not an AdapterError)")


try:
    L.run_transaction(GateBug("ghbdtn ", M1), "ghbdtn", d.replacement)   # escapes: the caller never reaches on_outcome
except RuntimeError:
    pass
print("   worker error between decision and outcome: snapshot alive =", e.snapshot is not None, ", credit =", e.credit, "(a conversion that never happened earns the run prior)")

print("== F7: incident does not stop the engine")
e = new_engine()
d = word(e, "ghbdtn", t0=1000)
f = L.SimField("ghbdtn ", M1, {("replace", 1): "partial"})
r = L.run_transaction(f, "ghbdtn", d.replacement)
e.on_outcome(r.outcome, r.quarantine)
d2 = word(e, "ytdtyj", t0=2000)
print("   outcome", r.outcome, "quarantine flag", r.quarantine, "| engine.mode =", e.mode, "| next word decision:", d2, "| engine.quarantined =", e.quarantined, "(a second transaction would start on a quarantined application)")

print("== F8: layout change seen only in key.layout")
e = new_engine()
word(e, "ghbdtn", t0=1000)
e.on_event(L.Event("key", L.keys_from_text("a", "en")[0], "en", 1100))     # typed ahead in EN
e.on_event(L.Event("key", L.keys_from_text("б", "ru")[0], "ru", 1101))     # next key arrives with RU layout id
print("   word dropped (skip =", e.skip, ") snapshot alive =", e.snapshot is not None, "after_switch =", e.after_switch, "(13.3: a layout change destroys the snapshot)")
e = new_engine()
word(e, "ghbdtn", t0=1000)
word(e, "к", "ru", t0=1100)         # first key of the next word arrives with the other layout id, no 'layout' event
print("   whole next word in other layout: snapshot alive =", e.snapshot is not None, "after_switch =", e.after_switch)

print("== F9: Backspace in a dropped word")
e = new_engine()
word(e, "ghbdtn", t0=1000)
e.on_event(L.Event("key", L.keys_from_text("a", "en")[0], "en", 1100))
e.on_event(L.Event("key", L.keys_from_text("б", "ru")[0], "ru", 1101))     # word dropped, skip = True
for i in range(9):
    e.on_event(L.Event("backspace", None, None, 1200 + i))                 # erases 'ab', the Space and the converted word
print("   after 9 Backspaces (field text would be empty) snapshot alive =", e.snapshot is not None, "(a Backspace on an empty buffer is a break, except inside a dropped word)")

print("== F10: clock")
e = new_engine(); word(e, "ghbdtn", t0=1_000_000)
print("   undo with now earlier than the replacement (clock stepped back 1 h):", repr(e.undo(1_000_000 - 3_600_000)))
e = new_engine(); word(e, "ghbdtn", t0=100)
e.on_event(L.Event("key", L.Key(5), "en", 0))       # ts_ms == 0 is falsy: tick is skipped
e.on_event(L.Event("key", L.Key(5), "en", 50_000))
print("   (control) a later event expires it:", e.snapshot is None)
e = new_engine(); word(e, "ghbdtn", t0=100)
e.tick(100 + 10_001)
e2 = new_engine(); word(e2, "ghbdtn", t0=100)
e2.on_event(L.Event("key", L.Key(5), "en", 0))      # time 0 after time 100: never expires anything either
print("   ts_ms=0 event after a snapshot (non-monotonic input) leaves it alive:", e2.snapshot is not None)

print("== F11: exception list bound")
e = new_engine(); rnd = random.Random(3); LK = sorted(L.LETTER_KEYS); t = 0; n = 0
while n < 10_050:
    t += 30_000
    keys = [L.Key(rnd.choice(LK)) for _ in range(rnd.randrange(5, 12))]
    for i, k in enumerate(keys):
        e.on_event(L.Event("key", k, "en", t + i))
    d = e.on_event(L.Event("space", None, "en", t + 20))
    if d is not None and d.action == "CONVERT":
        e.undo(t + 25); n += 1
    e.cool_words = 0
print(f"   {n} undone words -> len(exceptions) = {len(e.exceptions)} (spec: at most 10,000, least-recently-used eviction)")
