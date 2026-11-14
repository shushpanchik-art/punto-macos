#!/usr/bin/env python3
"""Spike S-4, macOS Accessibility binding (13.7): the five write tests on the focused control of another process through the
AX API: AXValue (whole value), AXSelectedTextRange and AXSelectedText (a range replace is: select the range, write AXSelectedText).
Needs PyObjC (pip install pyobjc-framework-ApplicationServices) and the Accessibility permission for the terminal.
AX ranges are UTF-16 units; the probe text is within the BMP (Latin and Cyrillic), so units equal code points here. A real adapter
must convert (S-7 batch rule).
Run:  python s4_ax_control.py out.json --application TextEdit --control-class "AXTextArea" [--trials 100]
STATE: written here; NOT RUN on macOS and NOT IMPORTED here (no PyObjC, no macOS). The PyObjC call shapes are the least certain part."""
import os
import platform
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import backend_control  # noqa: E402
import common  # noqa: E402
import control_probe  # noqa: E402


class AxBackend:
    def __init__(self, element):
        import ApplicationServices as A
        self.A, self.e = A, element

    def _get(self, attr):
        err, v = self.A.AXUIElementCopyAttributeValue(self.e, attr, None)
        if err != 0:
            raise RuntimeError(f"AX error {err} reading {attr}")
        return v

    def _set(self, attr, v):
        return self.A.AXUIElementSetAttributeValue(self.e, attr, v) == 0

    def text(self):
        try:
            v = self._get(self.A.kAXValueAttribute)
        except RuntimeError:
            return None
        return str(v) if v is not None else None

    def set_text(self, s):
        return self._set(self.A.kAXValueAttribute, s)

    def read_only(self):
        err, settable = self.A.AXUIElementIsAttributeSettable(self.e, self.A.kAXValueAttribute, None)
        return err == 0 and not settable

    def selection(self):
        ok, r = self.A.AXValueGetValue(self._get(self.A.kAXSelectedTextRangeAttribute), self.A.kAXValueCFRangeType, None)
        if not ok:
            raise RuntimeError("no selected range")
        return (r.location, r.location + r.length)

    def set_selection(self, a, b):
        v = self.A.AXValueCreate(self.A.kAXValueCFRangeType, (a, b - a))
        if not self._set(self.A.kAXSelectedTextRangeAttribute, v):
            raise RuntimeError("selection refused")

    def replace_selection(self, s):
        return self._set(self.A.kAXSelectedTextAttribute, s)


def main(argv):
    import ApplicationServices as A
    out = common.main_out(argv, "s4_row.json")
    arg = lambda k, d=None: argv[argv.index(k) + 1] if k in argv else d
    app = arg("--application")
    if not app:
        raise SystemExit("--application is required")
    err, el = A.AXUIElementCopyAttributeValue(A.AXUIElementCreateSystemWide(), A.kAXFocusedUIElementAttribute, None)
    if err != 0:
        raise SystemExit(f"no focused element (AX error {err}); grant Accessibility and focus the control")
    row = control_probe.classify(backend_control.BackendControl(AxBackend(el)), int(arg("--trials", 100)))
    row.update({"application": app, "control_class": arg("--control-class", "AXTextArea")})
    res = common.header("S-4", "macos", platform.mac_ver()[0])
    res["classes"] = [row]
    common.write(res, out)


if __name__ == "__main__":
    main(sys.argv)
