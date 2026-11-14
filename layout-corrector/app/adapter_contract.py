"""adapter_contract.py - contract tests that EVERY OS adapter must pass (13.7, 20.14). Standard library only.

An OS adapter (Windows UI Automation, macOS Accessibility) is wrapped in a `Driver` that can also act as the user, so the
same checks run against the in-memory double (`SimDriver`, here, synthetic) and later against a real control on a device.
Passing against `SimDriver` proves only that the checks are consistent with the reference double and that they catch the
broken adapters of `test_adapter_contract.py`; it says nothing about an OS. A real run is BLOCKED until a device exists.

Driver (what the harness needs besides the Adapter itself):
    ad                      the Adapter under test (13.7), already gated (ALLOW) on its element
    set_text(text, caret)   reset the control to this text with an empty selection at `caret`
    user_type(ch)           the user types one character at the caret
    user_key()              a key that types nothing (Shift, an arrow)
    user_click(pos)         a pointer press that moves the caret
    user_select(a, b)       the user selects a range
    focus_other()           the focus moves to another element
    text()                  the real content of the control (ground truth, not through the adapter)
`run_contract(make_driver, caps)` returns a list of (check name, ok, detail). Nothing here may be skipped for a capability
the adapter declares: a declared capability that is not delivered is a failure.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reference"))
import lfengine as L  # noqa: E402


class SimDriver:
    def __init__(self, caps):
        self.f = L.SimField("", caps)
        self.ad = self.f

    def set_text(self, text, caret):
        self.f.text, self.f.pos, self.f.sel = text, caret, None
        self.f.focus = "main"
        self.f.gate()

    def user_type(self, ch): self.f.type_user(ch)
    def user_key(self): self.f.silent += 1
    def user_click(self, pos): self.f.click(pos)
    def user_select(self, a, b): self.f.select(a, b)
    def focus_other(self): self.f.focus = "other"
    def text(self): return self.f.text


def _raises(fn, exc=Exception):
    try:
        fn()
    except exc:
        return True
    return False


def run_contract(make_driver, caps):
    caps = frozenset(caps)
    out = []

    def check(name, cond, detail=""):
        out.append((name, bool(cond), detail))

    d = make_driver(caps)
    ad = d.ad
    check("caps are a set of known capabilities", frozenset(ad.caps) == caps and ad.caps <= {L.READ_RANGE, L.REPLACE_RANGE, L.READBACK, L.ROLLBACK, L.SYNTHETIC_INPUT})
    check("gate is ALLOW, DENY or UNKNOWN", ad.gate() in (L.GATE_ALLOW, "DENY", "UNKNOWN"))

    # position queries
    d.set_text("say ghbdtn now", 14)
    check("caret reports an empty selection", ad.caret() == 14 and ad.selection() == (14, 14))
    d.user_select(4, 10)
    check("selection reports (start, end)", ad.selection() == (4, 10))
    check("caret FAILS on a non-empty selection (the automatic transaction can never write over a selection)", _raises(ad.caret, L.AdapterError))

    # read
    d.set_text("say ghbdtn now", 14)
    if L.READ_RANGE in caps:
        check("read returns exactly the range", ad.read(4, 10) == "ghbdtn" and ad.read(0, 3) == "say" and ad.read(11, 14) == "now")
        check("read past the end is clipped, never padded", ad.read(11, 99) == "now")
        check("read of an empty range is empty", ad.read(5, 5) == "")
    else:
        check("a field that is not readable answers None or fails, never invents text", (not _raises(lambda: ad.read(0, 3))) is False or ad.read(0, 3) is None)

    # replace (M1)
    if L.REPLACE_RANGE in caps:
        d.set_text("say ghbdtn now", 14)
        ad.replace(4, 10, "привет")
        check("replace writes the range and nothing else", d.text() == "say привет now", d.text())
        d.set_text("say ghbdtn now", 14)
        d.user_select(4, 10)
        ad.replace(4, 10, "привет")
        check("replace keeps the selection on the written range (or leaves the caret behind it)", ad.selection() in ((4, 10), (10, 10)), str(ad.selection()))
        d.set_text("ab", 2)
        ad.replace(0, 2, "фи")
        check("replace in a short field does not touch the neighbours", d.text() == "фи")

    # synthetic input (M2)
    if L.SYNTHETIC_INPUT in caps:
        d.set_text("say ghbdtn", 10)
        ad.send([("bs", "")] * 6 + [("ch", c) for c in "привет"])
        check("send: n Backspaces and n characters rewrite the word before the caret", d.text() == "say привет", d.text())
        check("modifier_down is a bool", isinstance(ad.modifier_down(), bool))

    # the user's input counter
    d.set_text("abc", 3)
    m = ad.mark()
    check("no input since the mark: zero", ad.keys_since(m) == 0)
    d.user_type("x")
    check("a typed character counts", ad.keys_since(m) == 1)
    d.user_key()
    check("a key that types nothing counts (Shift, an arrow)", ad.keys_since(m) == 2)
    d.user_click(0)
    check("a pointer press counts", ad.keys_since(m) == 3)
    m2 = ad.mark()
    check("a new mark starts from zero", ad.keys_since(m2) == 0 and ad.keys_since(m) == 3)
    # our own writes are not the user's input
    if L.REPLACE_RANGE in caps:
        d.set_text("say ghbdtn", 10)
        m3 = ad.mark()
        ad.replace(4, 10, "привет")
        check("the adapter's own replace is not counted as user input", ad.keys_since(m3) == 0)
    if L.SYNTHETIC_INPUT in caps:
        d.set_text("ab", 2)
        m3 = ad.mark()
        ad.send([("bs", ""), ("ch", "x")])
        check("the adapter's own synthetic events are not counted as user input", ad.keys_since(m3) == 0)

    # element identity: after the focus moved, no call may reach the other element
    d.set_text("say ghbdtn", 10)
    tok = ad.element()
    check("element is stable while the focus stays", ad.element() == tok)
    d.focus_other()
    check("element changes with the focus", ad.element() != tok)
    for name, fn in (("caret", ad.caret), ("selection", ad.selection), ("read", lambda: ad.read(0, 3)),
                     ("replace", lambda: ad.replace(0, 1, "x")), ("send", lambda: ad.send([("ch", "x")]))):
        if name == "read" and L.READ_RANGE not in caps or name == "replace" and L.REPLACE_RANGE not in caps or name == "send" and L.SYNTHETIC_INPUT not in caps:
            continue
        before = d.text()
        ok = _raises(fn, L.AdapterError)
        check(f"{name} on another focused element raises AdapterError and writes nothing", ok and d.text() == before)
    return out
