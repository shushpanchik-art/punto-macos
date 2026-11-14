#!/usr/bin/env python3
"""Spike S-4, Windows binding: the five write tests (control_probe.py) on a classic Win32 EDIT or RichEdit control of ANOTHER
process, with the messages of 13.7 (WM_SETTEXT, EM_SETSEL, EM_REPLACESEL, WM_GETTEXT, EM_GETSEL). These messages are marshalled
across processes by the system; EM_GETTEXTRANGE is not used because it needs memory in the other process.

Run:  python s4_edit_control.py out.json --application Notepad [--hwnd 0x1234] [--trials 100]
Without --hwnd it takes the first top-level window whose class is the one given with --window-class (default Notepad) and the
child of class Edit or RichEditD2DPT. One run measures ONE control class of ONE application; the result file lists it as one row
and the rows of several runs are merged by merge_s4.py. UI Automation and macOS controls are other bindings (not written).
STATE: written here, NOT RUN on Windows. The logic is tested with fake controls (test_probe.py)."""
import ctypes
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import common  # noqa: E402
import control_probe  # noqa: E402

WM_GETTEXT, WM_GETTEXTLENGTH, WM_SETTEXT = 0x000D, 0x000E, 0x000C
EM_GETSEL, EM_SETSEL, EM_REPLACESEL = 0x00B0, 0x00B1, 0x00C2


class EditControl:
    def __init__(self, hwnd):
        if sys.platform != "win32":
            raise RuntimeError("Windows only")
        self.u = ctypes.windll.user32
        self.u.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_void_p]
        self.u.SendMessageW.restype = ctypes.c_ssize_t
        self.h = hwnd

    def readable(self):
        return self.u.SendMessageW(self.h, WM_GETTEXTLENGTH, 0, None) >= 0

    def read(self):
        n = self.u.SendMessageW(self.h, WM_GETTEXTLENGTH, 0, None)
        buf = ctypes.create_unicode_buffer(n + 1)
        self.u.SendMessageW(self.h, WM_GETTEXT, n + 1, ctypes.cast(buf, ctypes.c_void_p))
        return buf.value

    def set_value(self, text):
        return bool(self.u.SendMessageW(self.h, WM_SETTEXT, 0, ctypes.cast(ctypes.create_unicode_buffer(text), ctypes.c_void_p)))

    def select(self, a, b):
        self.u.SendMessageW(self.h, EM_SETSEL, a, ctypes.c_void_p(b))

    def selection(self):
        a, b = ctypes.c_uint(), ctypes.c_uint()
        self.u.SendMessageW(self.h, EM_GETSEL, ctypes.addressof(a), ctypes.c_void_p(ctypes.addressof(b)))
        return (a.value, b.value)

    def replace(self, a, b, text):
        self.select(a, b)
        self.u.SendMessageW(self.h, EM_REPLACESEL, 1, ctypes.cast(ctypes.create_unicode_buffer(text), ctypes.c_void_p))   # undoable
        # the caret is NOT restored here: result 3 measures what the control does alone
        return True


def find_edit(window_class, hwnd=None):
    u = ctypes.windll.user32
    if hwnd:
        return int(hwnd, 0)
    top = u.FindWindowW(window_class, None)
    for cls in ("Edit", "RichEditD2DPT", "RICHEDIT50W"):
        child = u.FindWindowExW(top, None, cls, None)
        if child:
            return child
    raise RuntimeError("no edit control found: start the application first or give --hwnd")


def main(argv):
    out = common.main_out(argv, "s4_row.json")
    arg = lambda k, d=None: argv[argv.index(k) + 1] if k in argv else d
    app = arg("--application")
    if not app:
        raise SystemExit("--application is required")
    hwnd = find_edit(arg("--window-class", "Notepad"), arg("--hwnd"))
    row = control_probe.classify(EditControl(hwnd), int(arg("--trials", 100)))
    row.update({"application": app, "control_class": arg("--control-class", "Win32 Edit / RichEdit")})
    v = sys.getwindowsversion()
    res = common.header("S-4", "windows", f"{v.major}.{v.minor}.{v.build}")
    res["classes"] = [row]
    common.write(res, out)


if __name__ == "__main__":
    main(sys.argv)
