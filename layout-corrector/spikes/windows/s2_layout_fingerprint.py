#!/usr/bin/env python3
"""Spike S-2 (Windows 10 1607+): can the layout of ANOTHER process's thread be read and used?

Question (13.7): does GetKeyboardLayout(thread id of the foreground window) work for a thread of another process, and does
ToUnicodeEx accept that HKL with the flag 4 (state unchanged)? If not, the pair stays OFF (13.5 row 7).

What it does, with the machine's installed layouts (GetKeyboardLayoutList): for each HKL it computes the fingerprint of 13.7 /
20.14 (94 entries: 47 keys, Shift off and on, one ToUnicodeEx call each; a negative result is a dead key = "\\x00") and checks
that the fingerprints of different layouts differ. For the foreign-thread part it reads the HKL of the foreground window's
thread (run it while another program, for example Notepad, has the focus: --wait 5 gives five seconds to switch) and, with that
HKL, computes the fingerprint again; the two must give the same value as the list entry with the same HKL.

Run on Windows:  python s2_layout_fingerprint.py out.json [--wait 5]     Output: the result file of spikes.py for S-2.
STATE: written in this repository, NOT RUN on Windows (the container has none). The Win32 binding is the only part that needs it;
the logic is tested with a fake binding in test_measure.py, and that test proves nothing about Windows."""
import ctypes
import hashlib
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import common  # noqa: E402

KEYS_STATE_FLAG = 4          # wFlags of ToUnicodeEx: the keyboard state is not changed (documented from Windows 10 1607)


def fingerprint_entries(translate):
    """translate(scan, shift) -> str ('' for no character, '\\x00' for a dead key). Returns the 94 entries of 13.7."""
    out = []
    for scan in common.SCAN:
        for shift in (0, 1):
            ch = translate(scan, shift)
            out.append(ch if ch else "\x00")
    return out


def sha(entries):
    return hashlib.sha256("\n".join(entries).encode("utf-8")).hexdigest()


def measure(api, wait_s=0):
    """api: object with layouts() -> list of HKL ints, foreground_hkl() -> int or None (raises on failure),
    translate(hkl, scan, shift) -> str. Returns the S-2 result body (without the header)."""
    if wait_s:
        time.sleep(wait_s)
    hkls = api.layouts()
    fps = {}
    for hkl in hkls:
        fps[f"{hkl:#010x}"] = sha(fingerprint_entries(lambda scan, shift, h=hkl: api.translate(h, scan, shift)))
    foreign_ok = False
    accepts = False
    try:
        fh = api.foreground_hkl()
        foreign_ok = bool(fh)
        if foreign_ok:
            again = sha(fingerprint_entries(lambda scan, shift: api.translate(fh, scan, shift)))
            accepts = fps.get(f"{fh:#010x}") == again if f"{fh:#010x}" in fps else bool(again)
    except Exception:
        foreign_ok = False
    return {"foreign_thread_hkl_ok": foreign_ok, "to_unicode_ex_accepts_foreign_hkl": accepts,
            "fingerprints": fps, "layouts_tested": len(fps)}


class Win32:
    """The real binding (ctypes). Importing it anywhere but on Windows raises, on purpose."""
    def __init__(self):
        if sys.platform != "win32":
            raise RuntimeError("Windows only")
        self.u = ctypes.windll.user32
        self.u.GetKeyboardLayout.restype = ctypes.c_void_p
        self.u.MapVirtualKeyExW.restype = ctypes.c_uint
        self.u.ToUnicodeEx.argtypes = [ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int, ctypes.c_uint, ctypes.c_void_p]

    def layouts(self):
        n = self.u.GetKeyboardLayoutList(0, None)
        arr = (ctypes.c_void_p * n)()
        self.u.GetKeyboardLayoutList(n, arr)
        return [int(h or 0) for h in arr]

    def foreground_hkl(self):
        hwnd = self.u.GetForegroundWindow()
        if not hwnd:
            raise RuntimeError("no foreground window")
        tid = self.u.GetWindowThreadProcessId(hwnd, None)
        h = self.u.GetKeyboardLayout(tid)
        if not h:
            raise RuntimeError("GetKeyboardLayout failed for the foreground thread")
        return int(h)

    def translate(self, hkl, scan, shift):
        MAPVK_VSC_TO_VK_EX = 3
        vk = self.u.MapVirtualKeyExW(scan, MAPVK_VSC_TO_VK_EX, ctypes.c_void_p(hkl))
        state = (ctypes.c_ubyte * 256)()
        if shift:
            state[0x10] = 0x80                      # VK_SHIFT; Caps Lock and every other modifier stay off
        buf = ctypes.create_unicode_buffer(8)
        r = self.u.ToUnicodeEx(vk, scan, state, buf, 8, KEYS_STATE_FLAG, ctypes.c_void_p(hkl))
        if r < 0:
            return "\x00"                           # a dead key; the call may have stored it: flag 4 prevents that
        return buf.value[:r] if r else ""

    def build(self):
        v = sys.getwindowsversion()
        return f"{v.major}.{v.minor}.{v.build}"


def main(argv):
    out = common.main_out(argv, "s2_result.json")
    wait = int(argv[argv.index("--wait") + 1]) if "--wait" in argv else 0
    api = Win32()
    res = common.header("S-2", "windows", api.build())
    res.update(measure(api, wait))
    common.write(res, out)


if __name__ == "__main__":
    main(sys.argv)
