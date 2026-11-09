"""F-A (P1): M2 batch + an ARROW key between two synthetic events -> VERIFIED with a corrupted field.
13.2: 'The race that remains is not hidden: it ends in UNRECOVERED and a quarantine, never in a silent VERIFIED
(the reference model puts a user key before each of the 14 events ... and checks this, 20.13)'.
The reference test uses SimField fault 'key' = a key that TYPES NOTHING AND DOES NOT MOVE THE CARET.  A real arrow key
(or Home/End) moves the caret: the remaining Backspaces and characters then land elsewhere.  Step 5 reads only
[start,end) and accepts any caret c <= caret <= c+k, so the damage that lies OUTSIDE the fragment is invisible.
Run: python3 attack_m2_arrow_midbatch.py"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "work"))
import lfengine as L

M2 = {L.READ_RANGE, L.SYNTHETIC_INPUT}
OLD, NEW, FIELD = "ghbdtn", "привет", "Hello ghbdtn "


class ArrowsInBatch(L.SimField):
    """arrow keys (each counted by the key counter, each moves the caret) arrive just before synthetic event k:
    plan = {k: [delta, ...]}"""
    def __init__(self, text, caps, plan):
        super().__init__(text, caps)
        self.plan = plan

    def send(self, events):
        for i, ev in enumerate(events, 1):
            for d in self.plan.get(i, ()):
                self.pos = max(0, min(len(self.text), self.pos + d))
                self.silent += 1
            super().send([ev])


CASES = (("(1) word at the start of the field, ONE Left arrow before event 1", "", {1: [-1]}),
         ("(2) word at the start of the field, ONE Left arrow before event 9", "", {9: [-1]}),
         ("(3) 'Hello ' in front, Left x2 before event 1 and Right x2 before event 7", "Hello ", {1: [-2], 7: [2]}),
         ("(4) control: 'Hello ' in front, ONE Left arrow before event 3", "Hello ", {3: [-1]}))
bad = 0
for label, prefix, plan in CASES:
    f = ArrowsInBatch(prefix + OLD + " ", M2, plan)
    r = L.run_transaction(f, OLD, NEW, "", mode="MANUAL_ONLY")
    want = prefix + NEW + " "
    silent = r.outcome == "VERIFIED" and f.text != want
    bad += silent
    print(f"{label}\n    {r.outcome} {r.reason} incident={r.incident}  field={f.text!r}  expected {want!r}{'   <== SILENT CORRUPTION' if silent else ''}")
print("silent corruptions:", bad, "of", len(CASES))
