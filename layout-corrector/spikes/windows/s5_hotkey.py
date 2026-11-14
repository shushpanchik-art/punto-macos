#!/usr/bin/env python3
"""Spike S-5 (Windows): RegisterHotKey. Is the chord withheld from the focused application, is a second registration of the same
chord an error, and does UnregisterHotKey free the chord? (13.7 row "Hotkey": the page does not say that the key is withheld.)

The program creates a small visible window of its own, registers Ctrl+Alt+F23 (a chord that no program uses) for it, brings the
window to the foreground and injects the chord with SendInput `trials` times. For every trial it counts WM_HOTKEY (the hotkey
works) and WM_KEYDOWN of F23 in the focused window (the application got the key too: that refutes "withheld"). Then it tries to
register the same chord from a second thread (must fail with ERROR_HOTKEY_ALREADY_REGISTERED), unregisters it and registers it
again (must succeed).

Run on Windows:  python s5_hotkey.py out.json [--trials 100]
STATE: written here, NOT RUN on Windows. Logic tested with a fake binding (test_measure.py), which proves nothing about Windows."""
import ctypes
import os
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import common  # noqa: E402

MOD_ALT, MOD_CONTROL, MOD_NOREPEAT = 0x1, 0x2, 0x4000
VK_F23, VK_CONTROL, VK_MENU = 0x86, 0x11, 0x12
ERROR_HOTKEY_ALREADY_REGISTERED = 1409


def measure(api, trials=100):
    """api: register() -> bool, register_other_thread() -> int (0 = succeeded, else the error code), unregister() -> bool,
    run_trial() -> (hotkey_messages, keydown_messages) for one injected chord. Returns the S-5 body."""
    registered = api.register()
    hot = down = 0
    if registered:
        for _ in range(trials):
            h, d = api.run_trial()
            hot += h
            down += d
    err = api.register_other_thread() if registered else 0
    conflict_error = registered and err == ERROR_HOTKEY_ALREADY_REGISTERED
    released = bool(api.unregister()) and api.register() and bool(api.unregister()) if registered else False
    return {"registered": bool(registered) and hot == trials, "key_reached_application": down > 0,
            "conflict_error": bool(conflict_error), "released_cleanly": bool(released), "trials": trials,
            "hotkey_messages": hot, "keydown_messages_in_focused_window": down}


class Win32:
    def __init__(self):
        if sys.platform != "win32":
            raise RuntimeError("Windows only")
        from ctypes import wintypes
        self.w = wintypes
        self.u = ctypes.windll.user32
        self.k = ctypes.windll.kernel32
        self.hot = self.down = 0
        self.hwnd = None
        self._ready = threading.Event()
        self._stop = False
        self.t = threading.Thread(target=self._loop, daemon=True)
        self.t.start()
        if not self._ready.wait(10):
            raise RuntimeError("window thread did not start")

    # --- the window thread: its own message loop, as the product's hotkey thread would have
    def _loop(self):
        w = self.w
        WM_HOTKEY, WM_KEYDOWN = 0x0312, 0x0100
        WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, w.HWND, ctypes.c_uint, w.WPARAM, w.LPARAM)

        def proc(hwnd, msg, wp, lp):
            if msg == WM_HOTKEY:
                self.hot += 1
            elif msg == WM_KEYDOWN and wp == VK_F23:
                self.down += 1
            return self.u.DefWindowProcW(hwnd, msg, wp, lp)
        self._proc = WNDPROC(proc)

        class WNDCLASS(ctypes.Structure):
            _fields_ = [("style", ctypes.c_uint), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                        ("hInstance", w.HANDLE), ("hIcon", w.HANDLE), ("hCursor", w.HANDLE), ("hbrBackground", w.HANDLE),
                        ("lpszMenuName", w.LPCWSTR), ("lpszClassName", w.LPCWSTR)]
        self.u.DefWindowProcW.argtypes = [w.HWND, ctypes.c_uint, w.WPARAM, w.LPARAM]
        self.u.DefWindowProcW.restype = ctypes.c_ssize_t
        wc = WNDCLASS()
        wc.lpfnWndProc, wc.lpszClassName, wc.hInstance = self._proc, "PuntoS5", self.k.GetModuleHandleW(None)
        self.u.RegisterClassW(ctypes.byref(wc))
        self.hwnd = self.u.CreateWindowExW(0, "PuntoS5", "S-5", 0x10CF0000, 100, 100, 300, 100, None, None, wc.hInstance, None)  # WS_OVERLAPPEDWINDOW|WS_VISIBLE
        self.u.SetForegroundWindow(self.hwnd)
        self._ready.set()
        msg = w.MSG()
        while not self._stop and self.u.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            self.u.TranslateMessage(ctypes.byref(msg))
            self.u.DispatchMessageW(ctypes.byref(msg))

    def register(self):
        return bool(self.u.RegisterHotKey(self.hwnd, 1, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, VK_F23))

    def unregister(self):
        return bool(self.u.UnregisterHotKey(self.hwnd, 1))

    def register_other_thread(self):
        out = []

        def go():
            ok = self.u.RegisterHotKey(None, 2, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, VK_F23)
            out.append(0 if ok else self.k.GetLastError())
            if ok:
                self.u.UnregisterHotKey(None, 2)
        th = threading.Thread(target=go)
        th.start()
        th.join()
        return out[0]

    def run_trial(self):
        h0, d0 = self.hot, self.down
        self.u.SetForegroundWindow(self.hwnd)
        self._chord()
        time.sleep(0.05)
        return self.hot - h0, self.down - d0

    def _chord(self):
        w = self.w

        class KI(ctypes.Structure):
            _fields_ = [("wVk", w.WORD), ("wScan", w.WORD), ("dwFlags", w.DWORD), ("time", w.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

        class IN(ctypes.Structure):
            _fields_ = [("type", w.DWORD), ("ki", KI), ("pad", ctypes.c_ubyte * 8)]
        seq = [(VK_CONTROL, 0), (VK_MENU, 0), (VK_F23, 0), (VK_F23, 2), (VK_MENU, 2), (VK_CONTROL, 2)]
        arr = (IN * len(seq))(*[IN(1, KI(vk, 0, fl, 0, 0)) for vk, fl in seq])
        self.u.SendInput(len(seq), arr, ctypes.sizeof(IN))

    def build(self):
        v = sys.getwindowsversion()
        return f"{v.major}.{v.minor}.{v.build}"


def main(argv):
    out = common.main_out(argv, "s5_result.json")
    trials = int(argv[argv.index("--trials") + 1]) if "--trials" in argv else 100
    api = Win32()
    res = common.header("S-5", "windows", api.build())
    res.update(measure(api, trials))
    common.write(res, out)


if __name__ == "__main__":
    main(sys.argv)
