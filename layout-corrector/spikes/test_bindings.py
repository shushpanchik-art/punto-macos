"""Portable logic of the S-4 bindings: BackendControl over FAKE backends through control_probe.classify. The OS backends
(UiaBackend, AxBackend) are only compiled here, never run."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backend_control as B, control_probe as P

CHECKS = 0
def T(c, w):
    global CHECKS
    CHECKS += 1
    if not c: raise AssertionError(w)

class Fake:
    def __init__(self, readable=True, ro=False, replace=True, set_ok=True, clamp=False):
        self.t, self.s, self.readable, self.ro, self.rep, self.set_ok = "", (0, 0), readable, ro, replace, set_ok
    def text(self): return self.t if self.readable else None
    def set_text(self, s):
        if not self.set_ok: return False
        self.t, self.s = s, (len(s), len(s)); return True
    def read_only(self): return self.ro
    def selection(self): return self.s
    def set_selection(self, a, b): self.s = (a, b)
    def replace_selection(self, s):
        if not self.rep: return False
        a, b = self.s; self.t = self.t[:a] + s + self.t[b:]; self.s = (a + len(s), a + len(s)); return True

r = P.classify(B.BackendControl(Fake()))
T(r["full_value"] and r["range_replace"] and r["rollback_verified"] and not r["read_only"] and not r["unsupported"], f"a full backend: {r}")
T(r["caret_kept"] is False, "a backend that leaves the caret behind the replaced text does not keep the old caret (measured, not assumed)")
r = P.classify(B.BackendControl(Fake(replace=False)))
T(r["full_value"] and not r["range_replace"] and not r["rollback_verified"], "UI Automation style: whole value only")
r = P.classify(B.BackendControl(Fake(ro=True)))
T(r["read_only"] and not r["full_value"] and not r["range_replace"], "a read-only control")
r = P.classify(B.BackendControl(Fake(readable=False)))
T(r["unsupported"], "an unreadable control is unsupported")
r = P.classify(B.BackendControl(Fake(set_ok=False)))
T(not r["full_value"], "a refused whole-value write is recorded")
class Raises(Fake):
    def set_selection(self, a, b): raise RuntimeError("x")
r = P.classify(B.BackendControl(Raises()))
T(not r["range_replace"] and not r["rollback_verified"], "a backend that raises never counts as success")
for f in ("windows/s4_uia_control.py", "macos/s4_ax_control.py"):
    compile(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), f), encoding="utf-8").read(), f, "exec")
    T(True, f"{f} compiles (not run)")
print(f"OK ({CHECKS} backend binding checks, fake backends; the UIA and AX backends are compiled only)")
