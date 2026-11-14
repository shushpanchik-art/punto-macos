"""lfruntime.py - the portable runtime that an OS adapter drives (13.5, 13.7, 20.14). Standard library only.

What it is: the glue between the reference engine (`reference/lfengine.py`), the event-stream health (`HookHealth`)
and an `Adapter` (the five or six calls of 13.7). It holds no text of its own: the only text-derived state is the one
of the engine (the word buffer, the undo snapshot, the toggle record), and it is never logged.

What it is NOT: an OS adapter. Nothing here reads a keyboard hook, an accessibility tree or a window. An adapter
(Windows: UI Automation + low-level hook + Raw Input; macOS: CGEventTap + Accessibility) calls the methods below and
implements `Adapter`; until it exists and passes RT-1 to RT-27 on a device, the evidence level stays REFERENCE_VERIFIED.

Contracts that this module enforces for the adapter (and that its tests check):
  * every gate change goes through `on_gate`, which also tells `HookHealth` (L9 P-2: no signature queued in DENY);
  * a lost event (hook gap, tap disabled) sends `Event("gap")` to the engine and lowers the mode to MANUAL_ONLY until
    the stream is trusted again (13.5 row 13);
  * the mode of an application is a pure function of facts (`engine_mode`): an incident quarantines the application;
  * an automatic conversion runs only through `run_transaction`, with the element identity taken at the Space (L9 F4);
  * the user's undo and toggle hotkeys write only through a transaction and report its outcome to the engine.
U-1 (closed in the reference, 13.3 and 20.14): the undo after further typing passes `ahead_len=snapshot.after` to
`run_transaction`: the characters typed since are read from the field, never written, and only M1 may do it.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reference"))
import lfengine as L  # noqa: E402



class AppState:
    """Per-application facts (13.5, 13.7): support status and quarantine. Keyed by bundle id or executable path and
    signature, never by a window title. Memory only here; persistence is the adapter's job (13.7)."""

    def __init__(self, support: str = "UNKNOWN"):
        if support not in L.SUPPORT_STATUS:
            raise ValueError(support)
        self.support = support
        self.quarantined = False
        self.incidents = 0                       # a counter, never text (13.2 step 6); memory only, like the quarantine
        self.blacklisted = False                 # the user switched the application off (AP-4); persisted by lfstore
        self.esc_undoes = False                  # "Esc also undoes", opt-in per application (AP-4); persisted by lfstore
        self.caps = None                         # the capabilities its adapter reported at the last focus; memory only


class Runtime:
    def __init__(self, engine: "L.Engine", health: "L.HookHealth", *, models_ok: bool = True, permission_ok: bool = True):
        self.engine = engine
        self.health = health
        self.apps = {}
        self.app_id = None
        self.ad = None
        self.models_ok = models_ok
        self.permission_ok = permission_ok
        self.layout_ok = True
        self.watchdog_ok = True
        self.worker_ok = True                    # False after two worker failures within 60 s (failure row 11); memory only
        self.notices = []                        # (kind, reason): what the user would be told; never text
        self.last_result = None

    # -- facts -> mode ---------------------------------------------------------------------------------------------
    def _mode(self) -> str:
        app = self.apps.get(self.app_id)
        if app is None or self.ad is None or app.blacklisted:
            return "OFF"
        return L.engine_mode(self.ad.caps, app.support, models_ok=self.models_ok, layout_ok=self.layout_ok,
                             permission_ok=self.permission_ok, hook_ok=self.health.ok and not self.health.sticky,
                             watchdog_ok=self.watchdog_ok and self.worker_ok, quarantined=app.quarantined)

    def apply_mode(self):
        app = self.apps.get(self.app_id)
        if app is not None and not app.quarantined and self.engine.quarantined:
            self.engine.release_quarantine()      # the quarantine belongs to ONE application; it never follows the focus (found by test)
        self.engine.set_mode(self._mode())

    # -- focus, gate -----------------------------------------------------------------------------------------------
    def on_focus(self, app_id: str, adapter, support: str = "UNKNOWN"):
        """Another element or application has the focus: nothing of the old one survives (RT-20, 13.2 step 1)."""
        self.apps.setdefault(app_id, AppState(support)).caps = frozenset(adapter.caps)
        self.app_id, self.ad = app_id, adapter
        self.engine.on_event(L.Event("break"))
        self.engine.set_gate(L.GATE_UNKNOWN)
        self.health.set_gate_open(False)
        self.apply_mode()

    def on_gate(self, gate: str):
        """The verdict of the gate for the focused element (ALLOW | DENY | UNKNOWN). The only entry for it."""
        self.engine.set_gate(gate)
        self.health.set_gate_open(gate == L.GATE_ALLOW)

    def set_support(self, app_id: str, support: str):
        if support not in L.SUPPORT_STATUS:
            raise ValueError(support)
        self.apps.setdefault(app_id, AppState(support)).support = support
        self.apply_mode()

    def release_quarantine(self, app_id: str):
        """An explicit user action or a restart (13.2 step 6). Prefer `reenable`, which also reports what the mode is now."""
        a = self.apps.get(app_id)
        if a is not None:
            a.quarantined = False
        if app_id == self.app_id:
            self.engine.release_quarantine()
        self.apply_mode()

    # -- the application list (AP-4) ----------------------------------------------------------------------------------
    def explain(self, app_id: str):
        """(mode, reasons) of one application, derived from the same facts as `_mode` and in the order of `engine_mode`.
        Reasons: blacklist, quarantine, permission, layout, support_unknown, no_write_capability (all give OFF);
        support_manual, no_auto_capability, models, stream, watchdog, worker (MANUAL_ONLY); an empty list is AUTO. A name only, never text."""
        a = self.apps.get(app_id)
        if a is None:
            return "OFF", ["support_unknown"]
        if a.caps is None:                       # never focused: its capabilities are not known
            return "OFF", (["blacklist"] if a.blacklisted else []) + ["support_unknown"]
        r = []
        if a.blacklisted: r.append("blacklist")
        if a.quarantined: r.append("quarantine")
        if not self.permission_ok: r.append("permission")
        if not self.layout_ok: r.append("layout")
        if a.support == "UNKNOWN": r.append("support_unknown")
        if L.REPLACE_RANGE not in a.caps and L.SYNTHETIC_INPUT not in a.caps: r.append("no_write_capability")
        if r:
            return "OFF", r
        if a.support != "AUTO": r.append("support_manual")
        if not L.AUTO_REQUIRES <= a.caps: r.append("no_auto_capability")
        if not self.models_ok: r.append("models")
        if not (self.health.ok and not self.health.sticky): r.append("stream")
        if not self.watchdog_ok: r.append("watchdog")
        if not self.worker_ok: r.append("worker")
        return ("MANUAL_ONLY" if r else "AUTO"), r

    def app_list(self):
        """One row per application seen: id, support status, mode, reasons, incident count (AP-4). Sorted by id."""
        out = []
        for k in sorted(self.apps):
            mode, why = self.explain(k)
            out.append({"app": k, "support": self.apps[k].support, "mode": mode, "reasons": why, "incidents": self.apps[k].incidents,
                        "can_reenable": self.apps[k].quarantined or self.apps[k].blacklisted})
        return out

    def blacklist(self, app_id: str, on: bool = True):
        """The user switches an application off (or removes it from the list). Only `reenable` or this undoes it."""
        self.apps.setdefault(app_id, AppState("UNKNOWN")).blacklisted = bool(on)
        if app_id == self.app_id:
            self.engine.on_event(L.Event("break"))
        self.apply_mode()

    def reenable(self, app_id: str):
        """The re-enable button (13.5 row 10, AP-4). It clears the blacklist and the quarantine of that application and nothing
        else: the support status is never changed, AUTO is returned only when every fact still allows it (`explain`), the
        incident counter stays, the focused application starts from a clean state (no word, no snapshot) and the next incident
        quarantines it again. Returns (mode, reasons), or None for an unknown application."""
        a = self.apps.get(app_id)
        if a is None:
            return None
        a.quarantined = a.blacklisted = False
        if app_id == self.app_id:
            self.engine.release_quarantine()
            self.engine.on_event(L.Event("break"))
        self.apply_mode()
        self.notices.append(("reenabled", app_id))
        return self.explain(app_id)

    def prefs(self):
        """What is persisted per application (lfstore `apps`): the user's two choices, nothing else."""
        return {k: {"blacklist": v.blacklisted, "esc_undoes": v.esc_undoes} for k, v in self.apps.items() if v.blacklisted or v.esc_undoes}

    def load_prefs(self, apps: dict):
        for k, v in apps.items():
            a = self.apps.setdefault(k, AppState("UNKNOWN"))
            a.blacklisted, a.esc_undoes = bool(v["blacklist"]), bool(v["esc_undoes"])
        self.apply_mode()

    def on_esc(self, now_ms: int):
        """Esc pressed (it always passes through to the application): undo only where the user opted in (AP-4)."""
        a = self.apps.get(self.app_id)
        if a is None or not a.esc_undoes:
            return None
        return self.hotkey_undo(now_ms)

    # -- event stream health ----------------------------------------------------------------------------------------
    def _health_gap(self, reason_hint: str = ""):
        if self.health.take_gap():
            self.engine.on_event(L.Event("gap"))
            self.notices.append(("stream_lost", self.health.reason))
        self.apply_mode()

    def on_raw_key(self, now_ms: int, sig):
        """Windows: the independent Raw Input observer saw a physical key event."""
        self.health.raw_key(now_ms, sig)
        self._health_gap()

    def on_tap_disabled(self, reason: str):
        self.health.tap_disabled(reason)
        self._health_gap()

    def on_stream_restored(self, now_ms: int):
        self.health.reinstalled(now_ms if not self.health.canary else None)
        self.apply_mode()

    def on_tick(self, now_ms: int):
        """The runtime timer (at most every 100 ms): ages the snapshot and the toggle, runs the canary check."""
        self.engine.tick(now_ms)
        self.health.check(now_ms)
        self._health_gap()

    # -- the event of the hook ---------------------------------------------------------------------------------------
    def on_hook_event(self, ev: "L.Event", sig=None, injected: bool = False):
        """A key, Space, Backspace, break or layout event that the hook (Windows) or the tap (macOS) delivered. The hook only
        observes: this method never delays, drops or replays the physical key (RT-8); a conversion runs after the Space."""
        if ev.kind == "key" and sig is not None:
            self.health.hook_key(ev.ts_ms, sig, injected=injected)
            self._health_gap()
        d = self.engine.on_event(ev)
        if d is not None and d.action == "CONVERT" and ev.kind == "space":
            self._convert(d)
        return d

    def _convert(self, d: "L.Decision"):
        s = self.engine.snapshot
        old = L.render(s.keys, s.layout)
        try:
            res = L.run_transaction(self.ad, old, d.replacement, "", mode=self.engine.mode, element=self.ad.element())
        except Exception:                                                  # an adapter bug is an incident, never a crash
            res = L.TxResult("UNRECOVERED", "adapter_exception", "", True, True)
        self.last_result = res
        self.engine.on_outcome(res.outcome, res.quarantine)
        self._after(res)

    def _after(self, res: "L.TxResult"):
        if res.incident or res.quarantine:
            app = self.apps[self.app_id]
            app.incidents += 1
            app.quarantined = True
            self.notices.append(("incident", res.reason))
            self.apply_mode()

    # -- the hotkeys ---------------------------------------------------------------------------------------------------
    def hotkey_convert(self, now_ms: int) -> "L.TxResult":
        """Convert the selection, or with an empty selection the last whitespace-delimited token before the caret (13.3,
        manual transaction; U-2). The token is read through the adapter in growing windows, so that a field of any length
        costs one short read in the common case. Any mode except OFF allows it. The 13.3 shortcut "the last run still in
        the buffer" is not used: the field text is the single source and gives the same word."""
        mode = self.engine.mode
        if mode == "OFF" or self.ad is None:
            return L.TxResult("ABORTED", "mode_off")
        source = "selection"
        try:
            s, e = self.ad.selection()
            if s == e:
                source = "last_word"
                old = self._word_before(s)
                if old is None:
                    return L.TxResult("ABORTED", "not_readable")
                if old == "":
                    return L.TxResult("ABORTED", "no_word")
                if len(old) > L.MANUAL_MAX:
                    return L.TxResult("ABORTED", "length")
            else:
                old = self.ad.read(s, e)
        except Exception:
            return L.TxResult("ABORTED", "adapter_error")
        if old is None:
            return L.TxResult("ABORTED", "not_readable")
        direction, new = L.manual_convert(old)
        if direction is None or new == old:
            return L.TxResult("ABORTED", "nothing_to_convert")
        try:
            res = L.run_manual_transaction(self.ad, old, new, source=source, mode="MANUAL_ONLY", element=self.ad.element())
        except Exception:
            res = L.TxResult("UNRECOVERED", "adapter_exception", "", True, True)
        self.last_result = res
        self.engine.manual_outcome(old, new, direction, res.outcome, now_ms, res.quarantine)
        self._after(res)
        return res

    def _word_before(self, caret: int):
        """The whitespace-delimited token that ends at `caret`: "" when the character before the caret is white space or
        the field is empty there, None when the text is not readable. No read is longer than MANUAL_MAX + 2 characters: the
        window grows 64, 256, 1024, 4096, then is capped at that size. A token of more than MANUAL_MAX characters is
        returned as it is found (at least MANUAL_MAX + 1 of them), and the caller refuses it as too long."""
        cap = L.MANUAL_MAX + 2
        w = 64
        while True:
            w = min(w, cap)
            lo = max(caret - w, 0)
            t = self.ad.read(lo, caret)
            if t is None:
                return None
            i = len(t)
            while i > 0 and not t[i - 1].isspace():
                i -= 1
            if i > 0 or lo == 0 or w >= cap:
                return t[i:]
            w *= 4

    def shutdown(self):
        """The end of the process or of a session (AP-6, RT-6): nothing derived from typed text stays reachable. The engine is put to OFF
        (its buffer, run credit, snapshot, undo record and toggle record are destroyed), the gate closes, the stream-health queues are emptied
        and the adapter is let go. The exception list is NOT touched here: it is saved by the caller before this (lflifecycle.stop)."""
        self.engine.on_event(L.Event("break"))
        self.engine.set_gate(L.GATE_UNKNOWN)
        self.engine.set_mode("OFF")
        self.health.set_gate_open(False)
        self.ad, self.app_id = None, None

    def hotkey_toggle(self, now_ms: int):
        """Convert back what a manual conversion just wrote (13.3). None when there is nothing to toggle."""
        t = self.engine.toggle(now_ms)
        if t is None:
            return None
        expected, restore = t
        try:
            res = L.run_manual_transaction(self.ad, expected, restore, source="toggle", mode="MANUAL_ONLY", element=self.ad.element())
        except Exception:
            res = L.TxResult("UNRECOVERED", "adapter_exception", "", True, True)
        self.last_result = res
        self.engine.toggle_outcome(res.outcome, res.quarantine)
        self._after(res)
        return res

    def hotkey_undo(self, now_ms: int):
        """Undo the last automatic conversion (13.3). Returns the TxResult, or None when nothing happens."""
        s = self.engine.snapshot
        if s is None or not s.confirmed:
            return None
        typed = self.engine.undo(now_ms)
        if typed is None:
            return None
        converted = L.render(s.keys, "ru" if s.direction == "en2ru" else "en")
        try:
            res = L.run_transaction(self.ad, converted, typed, "", mode="MANUAL_ONLY", element=self.ad.element(), ahead_len=s.after)
        except Exception:
            res = L.TxResult("UNRECOVERED", "adapter_exception", "", True, True)
        self.last_result = res
        self.engine.undo_outcome(res.outcome, res.quarantine)
        self._after(res)
        return res
