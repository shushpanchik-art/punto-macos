#!/usr/bin/env python3
"""L9: attempts to break the replacement transaction of the reference (20.14), independent of conformance.py.

Usage: python3 L9_attacks.py     (standard library only; imports ../reference/lfengine.py)
Part A: random fuzz of 1 to 3 faults per run on M1, M1 without rollback and M2, with four field shapes and typed-ahead keys.
        Invariants checked on every run (the user's own keys are the letter 'x', which occurs nowhere else):
        I1 outcome vocabulary; I2 VERIFIED: the text without the user's keys is exactly the expected text, the caret check passed;
        I3 ABORTED: nothing written (M2: nothing sent) and the text without user keys is the original;
        I4 RESTORED: the text without user keys is the original; I5 UNRECOVERED: incident and quarantine set;
        I6 every user key is in the field exactly once unless the outcome is UNRECOVERED; I7 no crash.
Part B: named attacks that the fault vocabulary of SimField does not contain; each prints what the reference does.
"""
import os, random, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reference"))
import lfengine as L

M1 = {L.READ_RANGE, L.REPLACE_RANGE, L.READBACK, L.ROLLBACK}
M1N = {L.READ_RANGE, L.REPLACE_RANGE, L.READBACK}
M2 = {L.READ_RANGE, L.READBACK, L.SYNTHETIC_INPUT}
OLD, NEW = "ghbdtn", "привет"
SHAPES = [("Hello ghbdtn ", ""), ("ghbdtn ", ""), ("Hello ghbdtn ab", "ab"), ("ghbdtn ghbdtn ", ""), ("a ghbdtn  ", " ")]
OPS = {"gate": ["DENY", "UNKNOWN", "raise"], "caret": ["back", "forward", "forward2", "raise"],
       "read": ["none", "stale", "raise", "user:x", "key"],
       "replace": ["raise", "partial", "applied_error", "autocorrect", "ignored", "spill", "user:x", "key"],
       "event": ["raise", "user:x", "drop", "key"]}
rng = random.Random(9)
runs = bad = 0
stats = {}
for it in range(60000):
    caps = rng.choice([M1, M1N, M2])
    text, ahead = rng.choice(SHAPES)
    if caps is M2:
        ahead, text = "", "Hello ghbdtn "
    faults = {}
    for _ in range(rng.choice([1, 1, 2, 3])):
        op = rng.choice(list(OPS) if caps is M2 else [o for o in OPS if o != "event"])
        k = rng.randint(1, 3 if op != "event" else 14)
        faults[(op, k)] = rng.choice(OPS[op])
    f = L.SimField(text, caps, faults)
    mode = "AUTO" if caps is M1 else "MANUAL_ONLY"
    original = text.replace("x", "")
    res = L.run_transaction(f, OLD, NEW, ahead, mode=mode)
    runs += 1
    body = f.text.replace("x", "")
    expected = original.replace(OLD + " ", NEW + " ", 1) if text.count(OLD + " ") == 1 else None
    if text.startswith("ghbdtn ghbdtn"):               # the word that is replaced is the one before the caret
        expected = "ghbdtn " + NEW + " "
    problems = []
    if res.outcome not in L.OUTCOMES:
        problems.append("I1 outcome")
    if res.outcome == "VERIFIED" and expected is not None and body != expected:
        problems.append("I2 VERIFIED with wrong text: %r expected %r" % (body, expected))
    if res.outcome == "ABORTED" and (f.sent != 0 or body != original):
        problems.append("I3 ABORTED changed something: %r" % body)
    if res.outcome == "RESTORED" and body != original:
        problems.append("I4 RESTORED with another text: %r" % body)
    if res.outcome == "UNRECOVERED" and not (res.incident and res.quarantine):
        problems.append("I5 UNRECOVERED without incident")
    if res.outcome != "UNRECOVERED" and f.text.count("x") != len(f.user):
        problems.append("I6 a user key was lost or duplicated")
    stats[res.outcome] = stats.get(res.outcome, 0) + 1
    if problems:
        bad += 1
        if bad <= 10:
            print("PART A VIOLATION", problems, caps is M1, caps is M2, repr(text), repr(ahead), faults)
print("PART A: %d runs, %d violations, outcomes %s" % (runs, bad, dict(sorted(stats.items()))))


class Shift(L.SimField):
    """B1: the application inserts text BEFORE the word between the read and the write (autocomplete, collaboration)."""
    def replace(self, start, end, text):
        if not getattr(self, "shifted", False):
            self.shifted = True
            self.text, self.pos = "!" + self.text, self.pos + 1
        return super().replace(start, end, text)


f = Shift("Hello ghbdtn ", M1)
r = L.run_transaction(f, OLD, NEW)
print("B1 text shifted before the range between read and write ->", r.outcome, r.reason, repr(f.text))

f = L.SimField("Hello ghbdtn ", M1, {("caret", 2): "back"})
r = L.run_transaction(f, OLD, NEW)
print("B2 harmless arrow-left (caret one place back) between read and verify ->", r.outcome, "quarantine" if r.quarantine else "no quarantine", repr(f.text))

f = L.SimField("Hello ghbdtn ", M1, {("read", 2): "key"})
r = L.run_transaction(f, OLD, NEW)
print("B3 a non-character key (Shift) between write and verify ->", r.outcome, r.reason)

f = L.SimField("Hello ghbdtn ", M1)
f.text = "hello ghbdtn "                                     # B4 old text equal to the replacement is impossible for equal-length words
r = L.run_transaction(f, "ghbdtn", "ghbdtn")
print("B4 old == new ->", r.outcome, r.reason)

f = L.SimField("Hello ghbdtn ", M1)
r = L.run_transaction(f, "", "")
print("B5 empty word ->", r.outcome, r.reason, repr(f.text))

f = L.SimField("Hello ghbdtn ", M2, {("event", 5): "drop", ("event", 9): "drop"})
r = L.run_transaction(f, OLD, NEW, "", mode="MANUAL_ONLY")
print("B6 two dropped synthetic events (M2) ->", r.outcome, r.reason, repr(f.text))

f = L.SimField("Hello ghbdtn ", M1, {("replace", 1): "partial", ("replace", 2): "raise"})
r = L.run_transaction(f, OLD, NEW)
print("B7 partial write and a failing rollback ->", r.outcome, r.reason, repr(f.text))
