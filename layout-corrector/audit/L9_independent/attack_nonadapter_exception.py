"""F2: RT-7 says an error after step 4 began MUST end in RESTORED or UNRECOVERED with notice, incident counter and
quarantine.  run_transaction only catches AdapterError.  Any other exception raised by an adapter call after the write
began escapes: no rollback, no outcome, no incident, no quarantine, partial text left in the field.
(The caller sees an exception; 13.5 row 11 then says 'the current word is KEEP' - but the field is NOT the typed text.)
Run: python3 attack_nonadapter_exception.py"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "reference"))
import lfengine as L

M1 = {L.READ_RANGE, L.REPLACE_RANGE, L.READBACK, L.ROLLBACK}
M2 = {L.READ_RANGE, L.SYNTHETIC_INPUT}
OLD, NEW = "ghbdtn", "привет"


class HalfThenOSError(L.SimField):
    """A real adapter maps a COM/AX failure to its own exception type (OSError, TimeoutError, KeyError ...)."""
    exc = OSError

    def replace(self, start, end, text):
        half = text[:len(text) // 2] + self.text[start + len(text) // 2:end]
        self.text = self.text[:start] + half + self.text[end:]
        raise self.exc("AX timeout")

    def send(self, events):
        for k, (kind, ch) in enumerate(events, 1):
            if k == 9:
                raise self.exc("SendInput failed")
            super().send([(kind, ch)])


for label, caps, mode, fld in (("M1 replace raises OSError after a partial write", M1, "AUTO", "Hello ghbdtn "),
                               ("M2 send raises OSError in the middle of the batch", M2, "MANUAL_ONLY", "Hello ghbdtn ")):
    f = HalfThenOSError(fld, caps)
    try:
        r = L.run_transaction(f, OLD, NEW, "", mode=mode)
        print(label, "-> returned", r)
    except Exception as e:
        print(f"{label}\n   -> run_transaction RAISED {type(e).__name__}({e}); no TxResult, so no incident, no quarantine, no rollback;"
              f"\n   field now {f.text!r} (typed was {fld!r})")
