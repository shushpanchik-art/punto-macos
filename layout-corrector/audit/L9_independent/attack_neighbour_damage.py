"""F4: step 5 verifies only the fragment [start, end) and the caret.  Text just outside the fragment - the character before
the word, and everything after the caret (the user was editing in the middle of a document) - is never read.
An application that touches it as a side effect of the write (smart-quote / auto-capitalise / auto-space of the neighbour,
a collaborative merge) produces a VERIFIED outcome with a damaged document.  RT-4 counts that as a 'silent corruption'.
Run: python3 attack_neighbour_damage.py"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "work"))
import lfengine as L

M1 = {L.READ_RANGE, L.REPLACE_RANGE, L.READBACK, L.ROLLBACK}
OLD, NEW = "ghbdtn", "привет"


class Damage(L.SimField):
    def __init__(self, text, caps, where, caret_at=None):
        super().__init__(text, caps)
        self.where = where
        if caret_at is not None:
            self.pos = caret_at

    def replace(self, start, end, text):
        super().replace(start, end, text)
        t = self.text
        if self.where == "before":      # the application 'fixes' the neighbour in front (same length, caret unchanged)
            self.text = t[:start - 1] + "?" + t[start:]
        elif self.where == "after":     # ... or the text after the caret (suffix of the document)
            self.text = t[:end + 1] + "#" + t[end + 2:]


for where, field, caret in (("before", "Hello, ghbdtn ", None), ("after", "Hello ghbdtn  and the rest of the sentence", 13)):
    f = Damage(field, M1, where, caret)
    r = L.run_transaction(f, OLD, NEW)
    print(f"damage {where:6s}: {r.outcome:9s} {r.reason:3s} incident={r.incident}\n   before: {field!r}\n   after : {f.text!r}")
