#!/usr/bin/env python3
"""Spike S-7 (macOS 13+): (a) does an event tap see the tool's own 64-bit tag (kCGEventSourceUserData) on the tool's own
synthetic events; (b) how many UTF-16 units of one CGEventKeyboardSetUnicodeString event reach a text view whole (the M2 batch
size of 13.7 is 20 units).

The program posts keyboard events that carry the tag and a string of L units (L = 1..40) into a text view of its own window and
compares the text that arrived with the string; then it posts `own_events` events of 20 units. A listen-only tap on the session
counts the events whose user data equals the tag. Needs the Accessibility / Input Monitoring permission for the Python
interpreter: the program only reports; it never changes any permission setting.

Run on macOS:  python3 s7_tag_and_batch.py out.json [--events 1000]       (pip install pyobjc-framework-Quartz pyobjc-framework-Cocoa)
STATE: written here, NOT RUN on macOS. Logic tested with a fake binding (test_measure.py), which proves nothing about macOS."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import common  # noqa: E402

TAG = 0x50554E544F533031          # "PUNTOS01"
PAYLOAD = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"


def measure(api, own_events=1000, max_units=40):
    """api: post(text) posts one tagged event with that string; delivered() -> the text that reached the view since the last
    reset() (reset() empties it); tag_count() -> events with the tag that the tap saw. Returns the S-7 body."""
    whole = 0
    broken = False
    for n in range(1, max_units + 1):
        api.reset()
        s = PAYLOAD[:n]
        api.post(s)
        if api.delivered() == s and not broken:
            whole = n
        else:
            broken = True
    api.reset()
    t0 = api.tag_count()
    for _ in range(own_events):
        api.post(PAYLOAD[:20])
    seen = api.tag_count() - t0
    return {"tag_seen_by_tap": seen == own_events, "own_events": own_events, "tag_seen_count": seen,
            "max_units_per_batch_tested": max_units, "max_units_delivered_whole": whole}


class Mac:
    def __init__(self):
        if sys.platform != "darwin":
            raise RuntimeError("macOS only")
        import Quartz
        import AppKit
        self.Q, self.A = Quartz, AppKit
        self.count = 0
        app = AppKit.NSApplication.sharedApplication()
        self.win = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(((200, 200), (400, 200)), 15, 2, False)
        self.view = AppKit.NSTextView.alloc().initWithFrame_(((0, 0), (400, 200)))
        self.win.setContentView_(self.view)
        self.win.makeKeyAndOrderFront_(None)
        app.activateIgnoringOtherApps_(True)
        self.src = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)
        Quartz.CGEventSourceSetUserData(self.src, TAG)

        def cb(proxy, typ, ev, refcon):
            if Quartz.CGEventGetIntegerValueField(ev, Quartz.kCGEventSourceUserData) == TAG:
                self.count += 1
            return ev
        self._cb = cb
        self.tap = Quartz.CGEventTapCreate(Quartz.kCGSessionEventTap, Quartz.kCGHeadInsertEventTap, Quartz.kCGEventTapOptionListenOnly,
                                           Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown), cb, None)
        if not self.tap:
            raise RuntimeError("the event tap could not be created: Input Monitoring is not granted to this interpreter")
        src = Quartz.CFMachPortCreateRunLoopSource(None, self.tap, 0)
        Quartz.CFRunLoopAddSource(Quartz.CFRunLoopGetCurrent(), src, Quartz.kCFRunLoopCommonModes)
        Quartz.CGEventTapEnable(self.tap, True)

    def _spin(self, s=0.03):
        self.Q.CFRunLoopRunInMode(self.Q.kCFRunLoopDefaultMode, s, False)

    def reset(self):
        self.view.setString_("")
        self._spin()

    def post(self, text):
        for down in (True, False):
            ev = self.Q.CGEventCreateKeyboardEvent(self.src, 0, down)
            self.Q.CGEventKeyboardSetUnicodeString(ev, len(text.encode("utf-16-le")) // 2, text)
            self.Q.CGEventPost(self.Q.kCGSessionEventTap, ev)
        self._spin()

    def press(self, keycode, shift=False):
        """A physical key (virtual key code, no Unicode string): the active input source turns it into a character."""
        for down in (True, False):
            ev = self.Q.CGEventCreateKeyboardEvent(self.src, keycode, down)
            self.Q.CGEventSetFlags(ev, self.Q.kCGEventFlagMaskShift if shift else 0)
            self.Q.CGEventPost(self.Q.kCGSessionEventTap, ev)
        self._spin()

    def delivered(self):
        return str(self.view.string())

    def tag_count(self):
        return self.count

    def build(self):
        import platform
        return platform.mac_ver()[0]


def main(argv):
    out = common.main_out(argv, "s7_result.json")
    n = int(argv[argv.index("--events") + 1]) if "--events" in argv else 1000
    api = Mac()
    res = common.header("S-7", "macos", api.build())
    res.update(measure(api, n))
    common.write(res, out)


if __name__ == "__main__":
    main(sys.argv)
