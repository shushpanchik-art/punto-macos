"""Contract harness: it must pass the reference double for every capability set and must FAIL each broken adapter."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import adapter_contract as C  # noqa: E402
import lfengine as L  # noqa: E402

CHECKS = 0


def T(cond, what):
    global CHECKS
    CHECKS += 1
    if not cond:
        raise AssertionError(what)


M1 = {L.READ_RANGE, L.REPLACE_RANGE, L.READBACK, L.ROLLBACK}
M2 = {L.READ_RANGE, L.READBACK, L.SYNTHETIC_INPUT}
BOTH = M1 | {L.SYNTHETIC_INPUT}

for name, caps in (("M1", M1), ("M2", M2), ("M1+M2", BOTH)):
    res = C.run_contract(C.SimDriver, caps)
    bad = [n for n, ok, _ in res if not ok]
    T(not bad and len(res) >= 20, f"the reference double passes the contract, {name}: {bad}")


def broken(patch):
    class D(C.SimDriver):
        def __init__(self, caps):
            super().__init__(caps)
            patch(self.f)
    return D


def not_counting_silent_keys(f):
    f.keys_since = lambda m: len(f.user) - m
    f.mark = lambda: len(f.user)

def caret_on_selection(f):
    f.caret = lambda: f.pos

def replace_spills(f):
    old = f.replace
    def r(s, e, t):
        old(s, e, t)
        f.text = f.text[:e] + "?" + f.text[e + 1:] if len(f.text) > e else f.text
    f.replace = r

def counts_own_writes(f):
    old = f.replace
    def r(s, e, t):
        old(s, e, t); f.silent += 1
    f.replace = r

def element_never_changes(f):
    f.element = lambda: "main"
    f._chk = lambda fault=None: None

def read_pads(f):
    old = f.read
    f.read = lambda s, e: (old(s, e) or "") + " " if e > len(f.text) else old(s, e)

def selection_lies(f):
    f.selection = lambda: (f.pos, f.pos)

for label, patch, caps, expect in (
        ("keys_since ignores keys that type nothing", not_counting_silent_keys, M1, "a key that types nothing counts"),
        ("caret works on a selection", caret_on_selection, M1, "caret FAILS"),
        ("replace spills over the neighbour", replace_spills, M1, "replace writes the range and nothing else"),
        ("replace counted as user input", counts_own_writes, M1, "the adapter's own replace is not counted"),
        ("element never changes, other element reachable", element_never_changes, M1, "element changes with the focus"),
        ("read pads past the end", read_pads, M1, "read past the end is clipped"),
        ("selection hides the selection", selection_lies, M1, "selection reports (start, end)")):
    res = C.run_contract(broken(patch), caps)
    failed = [n for n, ok, _ in res if not ok]
    T(any(expect in n for n in failed), f"negative control: '{label}' must fail '{expect}', failed: {failed}")

print(f"OK ({CHECKS} adapter contract checks; reference double only, no OS adapter exists)")
