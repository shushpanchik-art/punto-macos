"""F5: the Adapter contract has no element identity.  Step 2 asks the gate once; steps 3-6 then read/write 'the focused
element' - whatever that is at the moment of each call.  If focus moves between step 3 and step 4 (Tab, a page script,
a notification stealing focus, Alt-Tab), the write lands in ANOTHER element at the offsets read in the first one, and
step 5 reads that other element back.  13.2 promises 'nothing outside the fragment is ever written'.
 (a) other ordinary field, caret elsewhere: UNRECOVERED (reported) but the other field's text is destroyed;
 (b) other field with the same text length: caret differs by one -> RESTORED ('the field holds what the user typed'
     - true only of the FIRST field; the other one was overwritten and rolled back with the wrong text);
     caret coincides -> VERIFIED, the original field is untouched and still wrong, another field has been overwritten;
 (c) the other element is a PASSWORD field: the gate is not asked again, and the transaction READS its content (13.1 says
     the tool must not read text it is not allowed to read; RT-2).
Run: python3 attack_focus_switch.py"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "work"))
import lfengine as L

M1 = {L.READ_RANGE, L.REPLACE_RANGE, L.READBACK, L.ROLLBACK}
OLD, NEW = "ghbdtn", "привет"


class TwoFields(L.SimField):
    """Focus moves to field B right after the k-th read (the match read of step 3)."""
    def __init__(self, a_text, b_text, caps, b_secure=False, switch_after_read=1):
        super().__init__(a_text, caps)
        self.A = (a_text, len(a_text))
        self.B = [b_text, len(b_text)]
        self.b_secure, self.switch_after_read, self.reads_of_secret = b_secure, switch_after_read, 0
        self.on_b = False

    def _swap(self):
        a_state = (self.text, self.pos)
        self.text, self.pos = self.B
        self.B = list(a_state)
        self.on_b = not self.on_b

    def read(self, start, end):
        t = super().read(start, end)
        if self.on_b and self.b_secure:
            self.reads_of_secret += 1
        if self.count["read"] == self.switch_after_read and not self.on_b:
            self._swap()
        return t


for label, b_text, secure in (("(a) other field, different caret", "user@example.org", False),
                              ("(b1) other field, caret differs by one", "Hello abcdef  ", False),
                              ("(b2) other field, same length and caret", "Hello abcdef ", False),
                              ("(c) other element is a password field", "hunter2!hunter2", True)):
    f = TwoFields("Hello ghbdtn ", b_text, M1, b_secure=secure)
    r = L.run_transaction(f, OLD, NEW)
    a_text = f.B[0] if f.on_b else f.text
    b_now = f.text if f.on_b else f.B[0]
    print(f"{label}\n   outcome={r.outcome} {r.reason}  A(original field)={a_text!r}  B(other)={b_now!r} (was {b_text!r})"
          + (f"\n   reads performed on the secure element: {f.reads_of_secret}" if secure else ""))
