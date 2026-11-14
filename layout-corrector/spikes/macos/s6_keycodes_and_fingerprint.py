#!/usr/bin/env python3
"""Spike S-6 (macOS 13+): are the virtual key codes (kCGKeyboardEventKeycode) independent of the input source, in particular on
the Russian - PC layout, and does UCKeyTranslate give the fingerprint of 13.7 for the supported layouts?

For every keyboard-layout input source that is enabled (at least U.S. and Russian - PC must be): (1) the fingerprint from
UCKeyTranslate (94 entries: 47 keys, Shift off and on, no other modifier, a dead key = NUL) and (2) the character that really
arrives in a text view of the program's window when the physical key (code, with and without Shift) is posted while that source
is selected. The key codes are independent of the source when, on every source, (2) equals (1) for all 94 states. The fingerprints
must differ between sources, and for U.S. and Russian - PC they must equal the supported fingerprints of the reference engine.

Run on macOS:  python3 s6_keycodes_and_fingerprint.py out.json          (pip install pyobjc-framework-Quartz pyobjc-framework-Cocoa)
It selects input sources with TISSelectInputSource and restores the one that was active; it asks for no permission itself and
changes no setting beyond that temporary selection.
STATE: written here, NOT RUN on macOS. Logic tested with a fake binding (test_measure.py), which proves nothing about macOS."""
import ctypes
import hashlib
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import common  # noqa: E402

# kVK_ANSI_* of the 47 keys, in the order of 19.1 (Events.h)
KEYCODE = [50, 18, 19, 20, 21, 23, 22, 26, 28, 25, 29, 27, 24,
           12, 13, 14, 15, 17, 16, 32, 34, 31, 35, 33, 30, 42,
           0, 1, 2, 3, 5, 4, 38, 40, 37, 41, 39,
           6, 7, 8, 9, 11, 45, 46, 43, 47, 44]
assert len(KEYCODE) == 47 and len(set(KEYCODE)) == 47


def entries(char_for):
    """char_for(keycode, shift) -> str ('' none, NUL for dead). Returns the 94 entries of 13.7."""
    out = []
    for kc in KEYCODE:
        for shift in (0, 1):
            c = char_for(kc, shift)
            out.append(c if c else "\x00")
    return out


def sha(es):
    return hashlib.sha256("\n".join(es).encode("utf-8")).hexdigest()


def measure(api, supported):
    """api: sources() -> [name], select(name), uc_char(keycode, shift) -> str for the selected source, typed_char(keycode, shift) -> str
    that arrived in the text view. supported: {'U.S.': fp, 'Russian - PC': fp} expected fingerprints."""
    fps, equal = {}, True
    for name in api.sources():
        api.select(name)
        es = entries(api.uc_char)
        fps[name] = sha(es)
        for i, kc in enumerate(KEYCODE):
            for shift in (0, 1):
                if api.typed_char(kc, shift) != (es[2 * i + shift] if es[2 * i + shift] != "\x00" else ""):
                    equal = False
    distinct = len(set(fps.values())) == len(fps)
    matches = all(fps.get(n) == fp for n, fp in supported.items() if n in fps)
    return {"layouts": sorted(fps), "keycodes_equal_on_all": equal, "fingerprints": fps,
            "fingerprint_call": "UCKeyTranslate", "fingerprint_distinct": distinct and matches,
            "matches_supported_fingerprints": matches}


class Mac:
    def __init__(self):
        if sys.platform != "darwin":
            raise RuntimeError("macOS only")
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
        import s7_tag_and_batch as s7
        self.m = s7.Mac()
        import Quartz  # noqa: F401
        self.c = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/Carbon.framework/Carbon")
        self.cf = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
        self.c.TISCopyCurrentKeyboardLayoutInputSource.restype = ctypes.c_void_p
        self.c.TISGetInputSourceProperty.restype = ctypes.c_void_p
        self.c.TISGetInputSourceProperty.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        self.cf.CFDataGetBytePtr.restype = ctypes.c_void_p
        self.cf.CFDataGetBytePtr.argtypes = [ctypes.c_void_p]
        self.original = self.c.TISCopyCurrentKeyboardLayoutInputSource()
        self._src = {}

    def _prop(self, src, name):
        key = ctypes.c_void_p.in_dll(self.c, name)
        return self.c.TISGetInputSourceProperty(ctypes.c_void_p(src), key)

    def sources(self):
        import Quartz
        from Foundation import NSString
        self.c.TISCreateInputSourceList.restype = ctypes.c_void_p
        lst = self.c.TISCreateInputSourceList(None, False)
        from objc import objc_object  # noqa: F401
        import CoreFoundation as CF
        arr = CF.CFArrayRef(lst) if hasattr(CF, "CFArrayRef") else lst
        out = []
        for i in range(CF.CFArrayGetCount(arr)):
            s = CF.CFArrayGetValueAtIndex(arr, i)
            sid = self._prop(int(ctypes.c_void_p(id(s)).value or 0), "kTISPropertyInputSourceID")
            out.append(str(sid))
            self._src[str(sid)] = s
        return out

    def select(self, name):
        self.c.TISSelectInputSource(ctypes.c_void_p(int(self._src[name])))
        self.m._spin(0.2)

    def uc_char(self, keycode, shift):
        data = self._prop(int(self._src_current()), "kTISPropertyUnicodeKeyLayoutData")
        if not data:
            return ""
        layout = self.cf.CFDataGetBytePtr(data)
        dead, buf, n = ctypes.c_uint32(0), (ctypes.c_uint16 * 4)(), ctypes.c_ulong(0)
        self.c.UCKeyTranslate.argtypes = [ctypes.c_void_p, ctypes.c_uint16, ctypes.c_uint16, ctypes.c_uint32, ctypes.c_uint32,
                                          ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32), ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong), ctypes.c_void_p]
        kUCKeyActionDown, kUCKeyTranslateNoDeadKeysMask = 0, 1
        mods = (2 if shift else 0)              # shiftKey >> 8
        r = self.c.UCKeyTranslate(layout, keycode, kUCKeyActionDown, mods, 0, 0, ctypes.byref(dead), 4, ctypes.byref(n), buf)
        if r != 0 or dead.value:
            return "\x00"
        return "".join(chr(buf[i]) for i in range(n.value))

    def _src_current(self):
        return self.c.TISCopyCurrentKeyboardLayoutInputSource()

    def typed_char(self, keycode, shift):
        self.m.reset()
        self.m.press(keycode, bool(shift))
        return self.m.delivered()

    def build(self):
        import platform
        return platform.mac_ver()[0]

    def restore(self):
        self.c.TISSelectInputSource(ctypes.c_void_p(self.original))


def main(argv):
    out = common.main_out(argv, "s6_result.json")
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "reference"))
    import lfengine as E
    supported = {"U.S.": E.layout_fingerprint(E.table_entries(E.EN)), "Russian - PC": E.layout_fingerprint(E.table_entries(E.RU))}
    api = Mac()
    try:
        res = common.header("S-6", "macos", api.build())
        res.update(measure(api, supported))
    finally:
        api.restore()
    common.write(res, out)


if __name__ == "__main__":
    main(sys.argv)
