#!/usr/bin/env python3
"""Spike S-4, Windows UI Automation binding (13.7): the five write tests on a control of ANOTHER process through UI Automation
(ValuePattern for the whole value, TextPattern for text and selection). UI Automation has no range replace: `replace_selection`
reports False, so the probe records `range_replace` false for a control that offers only these patterns; that is a measured
result, not an omission. Needs the `uiautomation` package (pip install uiautomation).
Run:  python s4_uia_control.py out.json --application "Windows Terminal" --control-class "UIA Edit" [--name "Text editor"] [--trials 100]
STATE: written here; NOT RUN on Windows and NOT EVEN IMPORTED here (the package and the OS are absent). The calls of the
`uiautomation` wrapper below follow its documented names and are the least certain part: the first real run decides."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import backend_control  # noqa: E402
import common  # noqa: E402
import control_probe  # noqa: E402


class UiaBackend:
    def __init__(self, element):
        self.e = element

    def _vp(self):
        return self.e.GetValuePattern()

    def _tp(self):
        return self.e.GetTextPattern()

    def text(self):
        tp = self._tp()
        if tp:
            return tp.DocumentRange.GetText(-1)
        vp = self._vp()
        return vp.Value if vp else None

    def set_text(self, s):
        vp = self._vp()
        if not vp:
            return False
        vp.SetValue(s)
        return True

    def read_only(self):
        vp = self._vp()
        return bool(vp.IsReadOnly) if vp else False

    def selection(self):
        tp = self._tp()
        doc = tp.DocumentRange
        sel = tp.GetSelection()[0]
        # offsets: the text from the document start to the selection start / end
        from uiautomation import TextPatternRangeEndpoint as E
        head = doc.Clone()
        head.MoveEndpointByRange(E.End, sel, E.Start)
        a = len(head.GetText(-1))
        head.MoveEndpointByRange(E.End, sel, E.End)
        return (a, len(head.GetText(-1)))

    def set_selection(self, a, b):
        from uiautomation import TextPatternRangeEndpoint as E, TextUnit
        r = self._tp().DocumentRange.Clone()
        r.MoveEndpointByRange(E.End, r, E.Start)            # collapse to the start
        r.Move(TextUnit.Character, a)
        r.MoveEndpointByUnit(E.End, TextUnit.Character, b - a)
        r.Select()

    def replace_selection(self, s):
        return False                                         # UI Automation offers no write over a text range


def main(argv):
    import uiautomation as auto
    out = common.main_out(argv, "s4_row.json")
    arg = lambda k, d=None: argv[argv.index(k) + 1] if k in argv else d
    app = arg("--application")
    if not app:
        raise SystemExit("--application is required")
    el = auto.GetFocusedControl() if not arg("--name") else auto.EditControl(searchDepth=12, Name=arg("--name"))
    row = control_probe.classify(backend_control.BackendControl(UiaBackend(el)), int(arg("--trials", 100)))
    row.update({"application": app, "control_class": arg("--control-class", "UIA Edit")})
    v = sys.getwindowsversion()
    res = common.header("S-4", "windows", f"{v.major}.{v.minor}.{v.build}")
    res["classes"] = [row]
    common.write(res, out)


if __name__ == "__main__":
    main(sys.argv)
