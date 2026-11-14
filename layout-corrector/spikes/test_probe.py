#!/usr/bin/env python3
"""Tests of control_probe.classify and merge_s4 with FAKE controls. They prove the protocol's logic, nothing about any application."""
import json, os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import control_probe as P, merge_s4, spikes as S
N = 0
def T(c, w):
    global N; N += 1
    if not c: raise AssertionError(w)

class Good:
    """a control that does everything right, caret included"""
    def __init__(self): self.t, self.sel = "", (0, 0)
    def readable(self): return True
    def read(self): return self.t
    def set_value(self, x): self.t = x; self.sel = (len(x), len(x)); return True
    def select(self, a, b): self.sel = (a, b)
    def selection(self): return self.sel
    def replace(self, a, b, x): keep = self.sel; self.t = self.t[:a] + x + self.t[b:]; self.sel = keep; return True
class MovesCaret(Good):
    def replace(self, a, b, x): self.t = self.t[:a] + x + self.t[b:]; self.sel = (a + len(x), a + len(x)); return True
class Spills(Good):
    def replace(self, a, b, x): self.t = self.t[:a] + x + self.t[b:]; self.t = self.t[:b + 1] + "?" + self.t[b + 2:]; return True
class NoRollback(Good):
    n = 0
    def replace(self, a, b, x):
        NoRollback.n += 1
        if NoRollback.n % 2 == 0: return True            # the second write of a trial (the rollback) does nothing
        return Good.replace(self, a, b, x)
class RefusesWrites(Good):
    def set_value(self, x): raise PermissionError
    def replace(self, a, b, x): return False
    def read(self): return "fixed text"
class NoText(Good):
    def readable(self): return False
class ValueOnly(Good):
    def replace(self, a, b, x): return False
class Raises(Good):
    def replace(self, a, b, x): raise RuntimeError("AX error")

r = P.classify(Good(), 100); T(r["full_value"] and r["range_replace"] and r["caret_kept"] and r["rollback_verified"] and not r["read_only"] and not r["unsupported"], "a good control passes all")
r = P.classify(MovesCaret(), 100); T(r["range_replace"] and not r["caret_kept"], "a caret that moves is result 3 failing: REPLACE_RANGE is then not granted")
r = P.classify(Spills(), 100); T(not r["range_replace"] and not r["rollback_verified"], "a write that spills is no range replace")
NoRollback.n = 0; r = P.classify(NoRollback(), 100); T(r["range_replace"] and not r["rollback_verified"], "no verified rollback")
r = P.classify(RefusesWrites(), 100); T(r["read_only"] and not r["full_value"] and not r["range_replace"] and not r["unsupported"], "read only")
r = P.classify(NoText(), 100); T(r["unsupported"] and not r["read_only"] and r["trials"] == 0, "not supported")
r = P.classify(ValueOnly(), 100); T(r["full_value"] and not r["range_replace"] and not r["read_only"], "only the whole value: no capability by itself")
r = P.classify(Raises(), 100); T(not r["range_replace"], "a raising control is a failure, not a crash")

# the rows feed the validator: the capability is the one the control earned
def row(r, app): return {"application": app, "control_class": "fake", **{k: r[k] for k in ("trials", "full_value", "range_replace", "caret_kept", "rollback_verified", "read_only", "unsupported")}}
def verdict(r, app="x"):
    d = {"spike": "S-4", "os": "windows", "os_build": "b", "machine": "m", "tool_revision": "t", "started_utc": "u", "synthetic": False, "classes": [row(r, app)]}
    return S.evaluate(d)
for ctl, cap in ((Good(), "REPLACE_RANGE"), (RefusesWrites(), "READ_RANGE"), (NoText(), "NONE")):
    v = verdict(P.classify(ctl, 100) if ctl.readable() else {**P.classify(ctl, 100), "trials": 100})
    T(v[0] in ("CONFIRMED", "INCOMPLETE") and (v[0] == "INCOMPLETE" or cap in v[1][0]), f"validator takes the row of {type(ctl).__name__}")
T(verdict(P.classify(MovesCaret(), 100))[0] == "INVALID" or "REPLACE_RANGE" not in verdict(P.classify(MovesCaret(), 100))[1][0], "a moving caret never yields REPLACE_RANGE")

# merge_s4
d = tempfile.mkdtemp()
def w(name, **kw):
    x = {"spike": "S-4", "os": "windows", "os_build": "b", "machine": "m", "tool_revision": "t", "started_utc": "u", "synthetic": False, "classes": [{"application": name}]}; x.update(kw)
    p = os.path.join(d, name + ".json"); json.dump(x, open(p, "w")); return p
m = merge_s4.merge([w("a"), w("b")]); T([c["application"] for c in m["classes"]] == ["a", "b"], "rows are merged")
for bad in (dict(machine="other"), dict(synthetic=True), dict(os_build="c"), dict(spike="S-5")):
    try: merge_s4.merge([w("a"), w("z", **bad)]); T(False, f"{bad} must be refused")
    except SystemExit: T(True, "")
print(f"OK ({N} control probe checks, fake controls only)")
