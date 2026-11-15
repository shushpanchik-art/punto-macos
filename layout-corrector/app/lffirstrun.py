"""AP-1 first run and permissions, portable part: a state machine over an injected permission adapter. No operating-system call is made here.

Specification (13.9 AP-1): "The first screen says what is observed (keystrokes in text fields, processed on the device, never stored or sent, 13.4) and asks for
the OS permissions one at a time, each with a link to the right system settings pane. Until all are granted the state is OFF and the status icon names the
missing permission. The user can quit from this screen." 13.5 row 14: a permission that is missing or revoked while the tool runs gives OFF and a notice
that names it. 13.7 (macOS): Input Monitoring (observing), Post Event (M2), Accessibility (AX text interface), "requested one by one (AP-1)".

The adapter (a fake in the tests) offers: status(name) -> 'granted' | 'denied' | 'unknown' (a query, it never prompts), request(name) -> 'granted' | 'denied' |
'pending' (asks the OS to show its prompt), settings_link(name) -> an opaque identifier of the settings pane. Anything else, or an exception, counts as NOT granted:
the fail-safe direction. The module shows no text: a screen is a dictionary of identifiers (text ids and one link id).

MY READINGS (audit/AP7_RT19_readings.md, section 12; none is agreed): the order is the order of 13.7; all three are required, Post Event included, although it
serves the hotkey only; the information screen does not gate the permissions or the state (the specification gates the state on the permissions alone) and its
'seen' flag is memory only (the settings schema has no field); what a denial or a cancel leaves; how a repeated request is treated."""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reference"))
import lfengine as L  # noqa: E402
import lfnotify as N  # noqa: E402
import lfstatus as ST  # noqa: E402

MACOS_ORDER = ("input_monitoring", "post_event", "accessibility")      # 13.7 lists them in this order (reading); Windows has no OS permission to request
OBSERVED = ("firstrun.observed.keystrokes_in_text_fields", "firstrun.observed.processed_on_device", "firstrun.observed.never_stored", "firstrun.observed.never_sent")
INTRO, PERMISSION, DONE, QUIT = "intro", "permission", "done", "quit"
_LINK = re.compile(r"[A-Za-z0-9_.:/-]{1,128}")


class FirstRun:
    def __init__(self, adapter, required=MACOS_ORDER, on_quit=None):
        req = tuple(required) if isinstance(required, (tuple, list)) else None
        if req is None or len(req) > 8 or len(set(req)) != len(req) or any(r not in N.PERMISSIONS or r == "hook" for r in req):
            raise ValueError("required")
        self.ad, self.required, self.on_quit = adapter, req, on_quit
        self.intro_seen = False
        self.quit_requested = False
        self.requests = []                    # names the adapter was asked to prompt for, in order (a record, never a decision input)
        self.counters = {}
        self._granted = {r: False for r in req}
        self._ever = set()                    # permissions seen granted at some point: a later loss is a revoke (13.5 row 14)
        self._pending = None                  # the permission whose prompt is open
        self._denied = set()                  # answered 'denied' since the last change of its status
        self.revoked = []                     # names whose grant was lost while running, in order, until noticed
        self._quit_done = False
        self.refresh()

    def _count(self, k):
        self.counters[k] = self.counters.get(k, 0) + 1

    def _status(self, name):
        try:
            s = self.ad.status(name)
        except Exception:
            self._count("status_failed")
            return "unknown"
        return s if s in ("granted", "denied") else "unknown"

    # -- facts -------------------------------------------------------------------------------------------------------------
    def refresh(self):
        """Reads every status again (the user may have used the settings pane). Idempotent: the same facts change nothing and cause no action. Returns True when
        something changed."""
        changed = False
        for r in self.required:
            now = self._status(r) == "granted"
            if now != self._granted[r]:
                changed = True
                self._granted[r] = now
                if now:
                    self._ever.add(r)
                    self._denied.discard(r)
                    if self._pending == r:
                        self._pending = None
                else:
                    if r in self._ever and r not in self.revoked:
                        self.revoked.append(r)
                    if self._pending == r:
                        self._pending = None
        return changed

    def missing(self):
        """The permissions not granted, in order."""
        return [r for r in self.required if not self._granted[r]]

    def all_granted(self):
        return not self.missing()

    def current(self):
        """The one permission being asked for: the first missing one (one at a time), or None."""
        m = self.missing()
        return m[0] if m else None

    # -- user actions ------------------------------------------------------------------------------------------------------
    def acknowledge(self):
        """The user has read the information screen and goes on."""
        self.intro_seen = True

    def request_current(self):
        """The user presses the button for the current permission. At most one prompt is open: a second press while it is open does nothing. Returns the
        permission asked for, or None when no request was made."""
        self.refresh()
        if self.quit_requested:
            self._count("ignored_after_quit")
            return None
        cur = self.current()
        if cur is None:
            self._count("nothing_to_ask")
            return None
        if self._pending == cur:
            self._count("duplicate_press")
            return None
        self.requests.append(cur)
        try:
            ans = self.ad.request(cur)
        except Exception:
            self._count("request_failed")
            ans = "pending"
        if ans == "granted" and self._status(cur) == "granted":     # the answer is only believed when the status agrees
            self.refresh()
        elif ans == "denied":
            self._denied.add(cur)
            self._pending = None
        else:
            self._pending = cur
        return cur

    def cancel(self):
        """The user cancels the open prompt or the step. Nothing is requested, nothing is granted, the state stays OFF at the same permission."""
        if self._pending is None:
            self._count("nothing_to_cancel")
        self._pending = None

    def quit(self):
        """'The user can quit from this screen.' The host's callback is called once; the permissions stay as they are."""
        self.quit_requested = True
        if not self._quit_done:
            self._quit_done = True
            if self.on_quit is not None:
                try:
                    self.on_quit()
                except Exception:
                    self._count("quit_callback_failed")

    def resume(self):
        """Back into the flow after a quit that did not end the process (re-entry); the next quit calls the host again."""
        self.quit_requested = False
        self._quit_done = False
        self.refresh()

    # -- what the screen shows ----------------------------------------------------------------------------------------------
    def link(self, name):
        try:
            v = self.ad.settings_link(name)
        except Exception:
            return None
        return v if isinstance(v, str) and _LINK.fullmatch(v) else None

    def view(self):
        """A dictionary of identifiers: the screen, what is observed, the current permission with its link and whether it was denied or its prompt is open. The
        user can always quit (`can_quit`)."""
        self.refresh()
        v = {"screen": None, "observed": list(OBSERVED), "missing": self.missing(), "permission": None, "link": None, "state": "OFF", "can_quit": True,
             "prompt_open": False, "denied": False}
        if self.quit_requested:
            v["screen"] = QUIT
        elif self.all_granted():
            v["screen"], v["state"] = DONE, "READY"
        elif not self.intro_seen:
            v["screen"] = INTRO
        else:
            cur = self.current()
            v.update(screen=PERMISSION, permission=cur, link=self.link(cur), prompt_open=self._pending == cur, denied=cur in self._denied)
        if v["screen"] == INTRO:
            v["permission"] = self.current()
        return v

    # -- links to the rest of the product -----------------------------------------------------------------------------------
    def apply(self, rt):
        """permission_ok of the runtime is true only while every required permission is granted. A loss while running makes the mode OFF at once (engine_mode)
        and the engine sees a break; a grant only allows the modes the other facts allow. Returns the permission named by the icon, or None."""
        self.refresh()
        ok = self.all_granted()
        if rt.permission_ok != ok:
            rt.permission_ok = ok
            if not ok:
                rt.engine.on_event(L.Event("break"))
            rt.apply_mode()
        return self.current()

    def icon(self, rt):
        """(label, reasons, missing permission or None): the status of AP-2 with the missing permission named (AP-1)."""
        name = self.apply(rt)
        label, reasons = ST.status(rt)
        return label, reasons, (name if "permission" in reasons else None)

    def notify(self, notifier):
        """13.5 row 14: a permission that was lost while running is named in a notice. A notice is queued once per loss; the 24 h limit is the notifier's.
        During the first run nothing is queued (the screen is the explanation). Returns the submit answers."""
        self.refresh()
        out = [notifier.submit("permission_missing", params={"permission": r}) for r in self.revoked]
        self.revoked = []
        return out
