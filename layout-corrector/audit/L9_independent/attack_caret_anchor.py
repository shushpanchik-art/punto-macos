"""F1: the caret read at step 3 is the only anchor of the fragment; a caret that moved between the freeze (mark)
and the read, onto an identical earlier word, makes the transaction convert the WRONG word and report VERIFIED.
Variants: (a) an arrow key (counted by mark, but the counter is only compared with the caret AFTER the move),
(b) a mouse click (not a key: never counted), (c) M2 with a click.  Run: python3 attack_caret_anchor.py"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "reference"))
import lfengine as L

M1 = {L.READ_RANGE, L.REPLACE_RANGE, L.READBACK, L.ROLLBACK}
M2 = {L.READ_RANGE, L.SYNTHETIC_INPUT}
OLD, NEW = "ghbdtn", "привет"
FIELD = "ghbdtn ghbdtn "          # the user typed the same word twice; the engine decided CONVERT for the second one


class MoveBeforeCaretRead(L.SimField):
    """The user moves the caret to the end of the first word (Home + Right x7, or a click) just before the caret is read
    in step 3.  `counted` tells whether the move is a key event the adapter counts (arrow key) or not (mouse)."""
    def __init__(self, *a, counted=True, **kw):
        super().__init__(*a, **kw)
        self.counted = counted

    def caret(self):
        if self.count.get("caret", 0) == 0:
            self.pos = 7                       # end of the first "ghbdtn "
            if self.counted:
                self.silent += 1               # an arrow key: typed no character, but is a key event
        return super().caret()


def run(caps, counted, mode="AUTO"):
    f = MoveBeforeCaretRead(FIELD, caps, counted=counted)
    r = L.run_transaction(f, OLD, NEW, "", mode=mode)
    return r, f


for label, caps, counted, mode in (("M1 + arrow key (counted)", M1, True, "AUTO"),
                                   ("M1 + pointer press (counted, contract 20.14)", M1, True, "AUTO"),
                                   ("M1 + caret move no hook sees (RESIDUAL, 13.2)", M1, False, "AUTO"),
                                   ("M2 + caret move no hook sees (RESIDUAL, 13.2)", M2, False, "MANUAL_ONLY"),
                                   ("M2 + arrow key (counted)", M2, True, "MANUAL_ONLY")):
    r, f = run(caps, counted, mode)
    wrong = r.outcome == "VERIFIED" and f.text != "ghbdtn привет "
    print(f"{label:32s} -> {r.outcome:10s} {r.reason:12s} field={f.text!r}  {'<== SILENT WRONG WORD (only the documented residual may print this)' if wrong else ''}")
