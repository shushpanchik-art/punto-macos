#!/usr/bin/env python3
"""Spikes S-1 and S-3 (Windows): the low-level hook against the independent Raw Input observer, compared one by one by signature.

PROTOCOL (the program only records; the keystrokes come from a physical generator that is NOT this tool's injection, for example
a USB HID keystroke generator or a person typing; LLKHF_INJECTED events are dropped from the hook stream and Raw Input never
reports injected events):
  S-1:  python s1_s3_capture.py s1 out.json --generator "name of the device" --events 1000000 [--slow-hook-ms 120]
        Records until `--events` Raw Input key events were seen, compares both streams (streams.compare, window 300 ms) and
        writes lost_by_hook, extra_in_hook and the counts. `--slow-hook-ms` is the time in which the PRODUCT's observer detected a
        deliberately slowed hook; this program cannot measure it (the product's HookHealth adapter does not exist yet), so
        without it the field is null and the validator answers INCOMPLETE. It is never filled in by this program.
  S-3:  python s1_s3_capture.py s3 out.json --generator "name"
        Stage 1 (automatic): the hotkey conflict rule: the same chord registered twice from two threads must fail the second
        time. Stage 2 (a person or the generator, 100+ keys): type into an ELEVATED window (for example an elevated console); the
        program checks that the foreground process is elevated and compares the two streams for those keys. Stage 3 (hold a key
        for 30 seconds, 1,000+ auto-repeat events): the two streams are compared and every difference is a mismatch.
The hook callback only copies the event into a list and calls CallNextHookEx.
STATE: written here, NOT RUN on Windows. The decision logic (finish_s1, finish_s3) is tested with generated streams (test_capture.py);
those tests prove nothing about Windows."""
import ctypes
import os
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import common  # noqa: E402
import streams  # noqa: E402


def finish_s1(raw, hook, generator, slow_hook_ms=None, hook_removed=False):
    c = streams.compare(raw, hook)
    return {"events_total": c["events_a"], "matched": c["matched"], "lost_by_hook": c["lost_by_b"], "extra_in_hook": c["extra_in_b"],
            "hook_removed_by_os": bool(hook_removed), "generator": generator, "generator_is_tool_injection": False,
            "slow_hook_detect_ms": slow_hook_ms}


def finish_s3(conflict_error, fg_elevated, raw_el, hook_el, raw_rep, hook_rep):
    """conflict_error: the second registration failed; fg_elevated: the foreground process was elevated during stage 2."""
    if not fg_elevated:                      # no elevated window was in the foreground: nothing about elevated windows was measured
        raw_el, hook_el = [], []
    ce = streams.compare(raw_el, hook_el)
    cr = streams.compare(raw_rep, hook_rep)
    return {"conflict_reported_by_os": bool(conflict_error), "foreground_was_elevated": bool(fg_elevated),
            "elevated_events_raw": ce["events_a"], "elevated_events_hook": ce["matched"] + ce["extra_in_b"],
            "elevated_input_reaches_hook": ce["matched"] + ce["extra_in_b"] == ce["events_a"] and ce["lost_by_b"] == 0,
            "autorepeat_events": cr["events_a"], "autorepeat_mismatches": cr["lost_by_b"] + cr["extra_in_b"]}


class Capture:
    """Both sources in one process, as the product would have them: a hook thread and a Raw Input window thread."""
    WM_INPUT, RIDEV_INPUTSINK, WH_KEYBOARD_LL = 0x00FF, 0x100, 13

    def __init__(self):
        if sys.platform != "win32":
            raise RuntimeError("Windows only")
        from ctypes import wintypes
        self.w = wintypes
        self.u, self.k = ctypes.windll.user32, ctypes.windll.kernel32
        self.raw, self.hook = [], []
        self.hook_removed = False
        self.t0 = time.perf_counter()
        self._ready = [threading.Event(), threading.Event()]
        threading.Thread(target=self._raw_thread, daemon=True).start()
        threading.Thread(target=self._hook_thread, daemon=True).start()
        for e in self._ready:
            if not e.wait(10):
                raise RuntimeError("a capture thread did not start (a Raw Input registration or the hook failed)")

    def now_ms(self):
        return (time.perf_counter() - self.t0) * 1000.0

    def _hook_thread(self):
        w = self.w

        class KB(ctypes.Structure):
            _fields_ = [("vkCode", w.DWORD), ("scanCode", w.DWORD), ("flags", w.DWORD), ("time", w.DWORD), ("dwExtraInfo", ctypes.c_size_t)]
        PROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, w.WPARAM, ctypes.POINTER(KB))
        self.u.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int, w.WPARAM, ctypes.c_void_p]
        self.u.CallNextHookEx.restype = ctypes.c_ssize_t

        def cb(n, wp, lp):
            if n >= 0:
                k = lp.contents
                if not (k.flags & 0x10):                                 # LLKHF_INJECTED: not compared
                    self.hook.append((self.now_ms(), k.scanCode, 1 if k.flags & 1 else 0, 1 if k.flags & 0x80 else 0))
            return self.u.CallNextHookEx(None, n, wp, ctypes.cast(lp, ctypes.c_void_p))
        self._cb = PROC(cb)
        self.u.SetWindowsHookExW.argtypes = [ctypes.c_int, PROC, ctypes.c_void_p, w.DWORD]
        self.u.SetWindowsHookExW.restype = ctypes.c_void_p
        h = self.u.SetWindowsHookExW(self.WH_KEYBOARD_LL, self._cb, self.k.GetModuleHandleW(None), 0)
        if not h:
            return
        self._ready[0].set()
        msg = w.MSG()
        while self.u.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            pass
        self.hook_removed = True

    def _raw_thread(self):
        w = self.w
        HWND_MESSAGE = ctypes.c_void_p(-3)

        class RAWINPUTDEVICE(ctypes.Structure):
            _fields_ = [("usUsagePage", w.USHORT), ("usUsage", w.USHORT), ("dwFlags", w.DWORD), ("hwndTarget", ctypes.c_void_p)]

        class RAWINPUTHEADER(ctypes.Structure):
            _fields_ = [("dwType", w.DWORD), ("dwSize", w.DWORD), ("hDevice", ctypes.c_void_p), ("wParam", w.WPARAM)]

        class RAWKEYBOARD(ctypes.Structure):
            _fields_ = [("MakeCode", w.USHORT), ("Flags", w.USHORT), ("Reserved", w.USHORT), ("VKey", w.USHORT), ("Message", w.UINT), ("ExtraInformation", w.ULONG)]

        class RAWINPUT(ctypes.Structure):
            _fields_ = [("header", RAWINPUTHEADER), ("kb", RAWKEYBOARD)]
        WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, w.HWND, ctypes.c_uint, w.WPARAM, w.LPARAM)
        self.u.DefWindowProcW.argtypes = [w.HWND, ctypes.c_uint, w.WPARAM, w.LPARAM]
        self.u.DefWindowProcW.restype = ctypes.c_ssize_t

        def proc(hwnd, msg, wp, lp):
            if msg == self.WM_INPUT:
                ri = RAWINPUT()
                size = w.UINT(ctypes.sizeof(ri))
                got = self.u.GetRawInputData(ctypes.c_void_p(lp), 0x10000003, ctypes.byref(ri), ctypes.byref(size), ctypes.sizeof(RAWINPUTHEADER))
                if got != 0xFFFFFFFF and ri.header.dwType == 1:
                    f = ri.kb.Flags
                    self.raw.append((self.now_ms(), ri.kb.MakeCode, 1 if f & 2 else 0, 1 if f & 1 else 0))
            return self.u.DefWindowProcW(hwnd, msg, wp, lp)                  # every WM_INPUT goes to DefWindowProc (13.7)
        self._rproc = WNDPROC(proc)

        class WNDCLASS(ctypes.Structure):
            _fields_ = [("style", ctypes.c_uint), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int), ("hInstance", w.HANDLE),
                        ("hIcon", w.HANDLE), ("hCursor", w.HANDLE), ("hbrBackground", w.HANDLE), ("lpszMenuName", w.LPCWSTR), ("lpszClassName", w.LPCWSTR)]
        wc = WNDCLASS()
        wc.lpfnWndProc, wc.lpszClassName, wc.hInstance = self._rproc, "PuntoRaw", self.k.GetModuleHandleW(None)
        self.u.RegisterClassW(ctypes.byref(wc))
        hwnd = self.u.CreateWindowExW(0, "PuntoRaw", None, 0, 0, 0, 0, 0, HWND_MESSAGE, None, wc.hInstance, None)
        rid = RAWINPUTDEVICE(1, 6, self.RIDEV_INPUTSINK, hwnd)
        if not self.u.RegisterRawInputDevices(ctypes.byref(rid), 1, ctypes.sizeof(rid)):
            return
        self._ready[1].set()
        msg = w.MSG()
        while self.u.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            self.u.TranslateMessage(ctypes.byref(msg))
            self.u.DispatchMessageW(ctypes.byref(msg))

    def foreground_elevated(self):
        a = ctypes.windll.advapi32
        hwnd = self.u.GetForegroundWindow()
        pid = self.w.DWORD()
        self.u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        ph = self.k.OpenProcess(0x1000, False, pid.value)                    # PROCESS_QUERY_LIMITED_INFORMATION
        if not ph:
            return True                                                      # cannot even open it: treat as elevated (the stricter reading)
        tok = self.w.HANDLE()
        if not a.OpenProcessToken(ph, 0x8, ctypes.byref(tok)):               # TOKEN_QUERY
            return True
        elev = self.w.DWORD()
        n = self.w.DWORD()
        a.GetTokenInformation(tok, 20, ctypes.byref(elev), ctypes.sizeof(elev), ctypes.byref(n))   # TokenElevation
        return bool(elev.value)

    def conflict(self):
        MOD_CONTROL, MOD_ALT, MOD_NOREPEAT, VK_F23 = 0x2, 0x1, 0x4000, 0x86
        ok1 = self.u.RegisterHotKey(None, 91, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, VK_F23)
        out = []
        t = threading.Thread(target=lambda: out.append(bool(self.u.RegisterHotKey(None, 92, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, VK_F23))))
        t.start(); t.join()
        self.u.UnregisterHotKey(None, 91)
        if out and out[0]:
            self.u.UnregisterHotKey(None, 92)
        return bool(ok1) and out == [False]

    def build(self):
        v = sys.getwindowsversion()
        return f"{v.major}.{v.minor}.{v.build}"


def main(argv):
    arg = lambda k, d=None: argv[argv.index(k) + 1] if k in argv else d
    if len(argv) < 3 or argv[1] not in ("s1", "s3"):
        raise SystemExit(__doc__)
    gen = arg("--generator")
    if not gen:
        raise SystemExit("--generator is required: name the physical generator (it must not be this tool's own injection)")
    cap = Capture()
    res = common.header("S-1" if argv[1] == "s1" else "S-3", "windows", cap.build())
    if argv[1] == "s1":
        want = int(arg("--events", 1_000_000))
        while len(cap.raw) < want:
            time.sleep(0.5)
            print(f"\r{len(cap.raw)}/{want} raw events, {len(cap.hook)} hook events", end="")
        time.sleep(0.5)
        slow = arg("--slow-hook-ms")
        res.update(finish_s1(list(cap.raw), list(cap.hook), gen, float(slow) if slow else None, cap.hook_removed))
    else:
        conflict = cap.conflict()
        input("Stage 2: press Enter here, then focus an ELEVATED window and type 100+ keys with the generator; come back and press Enter. ")
        i0, j0, samples, stop = len(cap.raw), len(cap.hook), [], threading.Event()

        def sample():
            while not stop.is_set():
                samples.append(cap.foreground_elevated())
                time.sleep(0.2)
        th = threading.Thread(target=sample, daemon=True)
        th.start()
        input("")
        stop.set(); th.join()
        elevated = sum(1 for x in samples if x) >= 5                  # an elevated window was in the foreground for at least a second
        raw_el, hook_el = cap.raw[i0:], cap.hook[j0:]
        input("Stage 3: press Enter, then hold a key for 30 s (1,000+ auto-repeat events); press Enter again. ")
        i1, j1 = len(cap.raw), len(cap.hook)
        input("")
        res.update(finish_s3(conflict, elevated, raw_el, hook_el, cap.raw[i1:], cap.hook[j1:]))
    common.write(res, arg("--out", argv[2]))


if __name__ == "__main__":
    main(sys.argv)
