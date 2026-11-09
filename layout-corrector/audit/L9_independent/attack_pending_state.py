"""F-C (P2) and F-D (P2/P3): the engine updates its state at the DECISION, the transaction ends up to 250 ms later,
and Engine.on_outcome carries no identity of the transaction it reports.
Spec 13.2 step 7: 'Record the undo snapshot only for a VERIFIED outcome'; 10.2: the run prior (w=0.25 instead of 0.01) is
earned by a conversion.  In the reference code the credit and the snapshot exist from the decision on.
 (1) word A is decided CONVERT, its transaction is ABORTED (typed_ahead: the worker was slow, > 3 keys typed).  Word B,
     decided while A was pending, used the run prior earned by A's conversion that never happened: B is converted with
     a score that is below the threshold in the default state.
 (2) the late on_outcome(ABORTED) of A then drops the snapshot of B and clears the credit: B's conversion is VERIFIED
     in the field but the undo chord does nothing (13.3: 'within 10 seconds after an automatic correction ... Undo').
 (3) undo() before the outcome: the chord pressed while the transaction is queued returns text, adds the word to the
     exception list and starts the cool-down although no conversion exists yet; the conversion then runs and stands.
 (4) an exception that is not an AdapterError between decision and outcome leaves the snapshot and the credit alive.
Run: python3 attack_pending_state.py"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "work"))
import lfengine as L

M1 = {L.READ_RANGE, L.REPLACE_RANGE, L.READBACK, L.ROLLBACK}
# strong evidence for short words, borderline for words of 8+ keys: above the threshold only with the run prior
scorer = lambda ids: [-3, 12, -2] if len(ids) - 2 < 8 else [-3, 6.0, -2]


def word(e, text, t0, lay="en"):
    for i, k in enumerate(L.keys_from_text(text, lay)):
        e.on_event(L.Event("key", k, lay, t0 + i * 10))
    return e.on_event(L.Event("space", None, lay, t0 + len(text) * 10 + 5))


print("control: word B alone (default prior)")
e = L.Engine(L.example_cal(), scorer, {})
dB = word(e, "ytghbdtn", 1000)
print("   B decision:", dB.action, dB.reason, "margin %.2f" % dB.margin)

print("(1)+(2) A pending, B decided meanwhile, then A is ABORTED")
e = L.Engine(L.example_cal(), scorer, {})
dA = word(e, "ghbdtn", 1000)                                   # CONVERT, credit := 3, snapshot A
dB = word(e, "ytghbdtn", 1100)                                 # decided while A's transaction has not ended
print("   A:", dA.action, "| B:", dB.action, dB.reason, "(B used the run prior: engine.credit was", 3, "from A)")
fieldB = L.SimField("ghbdtn ytghbdtn ", M1)                    # the user typed A, then B; A was never converted (aborted)
e.on_outcome("ABORTED")                                         # outcome of A arrives (typed_ahead abort) after B's decision
print("   after on_outcome(ABORTED of A): snapshot of B =", e.snapshot, "credit =", e.credit)
rB = L.run_transaction(fieldB, "ytghbdtn", dB.replacement)
e.on_outcome(rB.outcome)
print("   B's transaction:", rB.outcome, "field=%r" % fieldB.text, "| undo chord ->", e.undo(1500))

print("(3) undo before the outcome")
e = L.Engine(L.example_cal(), scorer, {})
d = word(e, "ghbdtn", 1000)
field = L.SimField("ghbdtn ", M1)                               # transaction still queued: the field shows the typed text
t = e.undo(1100)
print("   undo() ->", repr(t), "| exception added:", ("en2ru", "ghbdtn") in e.exceptions, "| cool_words =", e.cool_words)
r = L.run_transaction(field, "ghbdtn", d.replacement)
print("   then the transaction:", r.outcome, "field=%r" % field.text, "(the word is converted AND an exception)")

print("(4) a non-AdapterError between decision and outcome")
e = L.Engine(L.example_cal(), scorer, {})
d = word(e, "ghbdtn", 1000)
class Boom(L.SimField):
    def gate(self): raise RuntimeError("bug in the adapter")
try:
    L.run_transaction(Boom("ghbdtn ", M1), "ghbdtn", d.replacement)
except RuntimeError:
    pass                                                        # row 11: the worker restarts, the word is KEEP
print("   snapshot alive:", e.snapshot is not None, "credit:", e.credit, "-> undo():", repr(e.undo(2000)), "(a conversion that never happened)")
