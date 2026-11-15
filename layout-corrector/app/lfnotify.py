"""AP-8 notifications, portable part: what is shown, how often, with which single action. The display is an adapter function `show(notice) -> True`
that MUST be non-blocking and MUST NOT take focus (it is called from the interface thread by `deliver`, never from the engine thread).

Specification: 13.5 "A notice is shown at most once per cause and per 24 hours, and never takes focus"; AP-8 "Non-blocking, never take focus, rate-limited as in 13.5;
each offers one action (open settings, re-enable)". NOT defined by the specification, so NOT invented here: priorities between notices (delivery is first
come, first served), any wording (a notice carries a text identifier, the words belong to the interface), persistence of the 24 h memory across restarts.
MY READINGS (listed in audit/AP7_RT19_readings.md, section 7): the cause is the kind plus, for incidents, the outcome; two shows exactly 24 h apart are allowed;
the action of each kind; the mapping of runtime reasons and of the store and settings notices to kinds.
A notice carries NO free text: kind, row, text identifier, one action, and parameters that pass an allow-list (a permission name, a hotkey chord, the opaque
identifier of the application the re-enable action points at). Details coming in from other modules only select a variant from a fixed list, never copied."""
import re

import lfsettings as G

DAY_MS = 86_400_000
ACTIONS = ("open_settings", "re_enable")
PERMISSIONS = ("input_monitoring", "post_event", "accessibility", "hook")
_APP = re.compile(r"[^\x00-\x1f\x7f]{1,512}")

# kind -> (13.5 row or None when the table has no row, action). Text identifiers are "notice." + kind (+ "." + variant).
CATALOGUE = {
    "incident": (10, "re_enable"),                  # variants: restored, unrecovered ("the field may differ ... the application's own undo is the way back")
    "permission_missing": (14, "open_settings"),    # names the permission; row 8 (gate UNKNOWN through a revoked text interface) uses the same kind
    "stream_lost": (13, "re_enable"),
    "watchdog": (9, "re_enable"),
    "update_failed": (12, "open_settings"),          # AP-9: a package fails signature, hash or validation; the previous package stays active
    "worker_failed_twice": (11, "open_settings"),
    "models_unavailable": (None, "open_settings"),  # rows 3 to 6 and 12 cannot be told apart by the runtime flag `models_ok`
    "manual_only_after_crashes": (None, "open_settings"),   # my name for AP-7; not in the table
    "instance_lock_unavailable": (None, "open_settings"),   # RT-19 asks for OFF, not for a notice; not in the table
    "settings_not_saved": (None, "open_settings"),
    "delete_failed": (None, "open_settings"),               # "Delete all data" could not remove a file (AP-5)
    "autostart_failed": (None, "open_settings"),
    "hotkey_fallback": (None, "open_settings"),
    "hotkey_unavailable": (None, "open_settings"),
    "cipher_unavailable": (None, "open_settings"),          # AP-5
    "file_unreadable_defaults": (None, "open_settings"),    # AP-5
    "newer_file_kept": (None, "open_settings"),             # AP-5
}
IGNORED = ("reenabled", "migrated")                 # the answer to the user's own action; an informational line of the file migration
REASON_KIND = {"permission": "permission_missing", "stream": "stream_lost", "watchdog": "watchdog", "models": "models_unavailable"}
# reason "layout" (row 7) is shown by the status icon, not by a notice; "instance" is an event notice of lfinstance.


def cause_of(kind, variant=""):
    return (kind, variant) if kind == "incident" else (kind, "")


def build(kind, variant="", params=None):
    """The notice dictionary, or None for an unknown kind. `variant` selects wording only for incidents ('restored' or 'unrecovered')."""
    if kind not in CATALOGUE:
        return None
    row, action = CATALOGUE[kind]
    v = variant if (kind == "incident" and variant in ("restored", "unrecovered")) else ("restored" if kind == "incident" else "")
    return {"kind": kind, "row": row, "text_id": "notice." + kind + ("." + v if v else ""), "action": action, "params": dict(params or {}), "takes_focus": False}


def validate(n):
    """Problems of a notice; an empty list means it may be shown. Allow-list only: no free text can pass."""
    if not isinstance(n, dict) or set(n) != {"kind", "row", "text_id", "action", "params", "takes_focus"}:
        return ["shape"]
    bad = []
    if n["kind"] not in CATALOGUE or CATALOGUE[n["kind"]][1] != n["action"] or CATALOGUE[n["kind"]][0] != n["row"]:
        bad.append("kind, row or action")
    if n["action"] not in ACTIONS:
        bad.append("action: exactly one of the allowed ones")
    if n["takes_focus"] is not False:
        bad.append("takes focus")
    if not (isinstance(n["text_id"], str) and re.fullmatch(r"notice\.[a-z_]+(\.[a-z]+)?", n["text_id"])):
        bad.append("text id")
    p = n["params"]
    if not isinstance(p, dict) or not set(p) <= {"permission", "chord", "target"}:
        return bad + ["params"]
    if "permission" in p and p["permission"] not in PERMISSIONS:
        bad.append("permission")
    if "chord" in p and not (n["kind"] == "hotkey_fallback" and any(G.valid_chord(p["chord"], pf) for pf in ("windows", "macos"))):
        bad.append("chord")
    if "target" in p and not (n["action"] == "re_enable" and isinstance(p["target"], str) and _APP.fullmatch(p["target"])):
        bad.append("target")
    if n["kind"] == "permission_missing" and "permission" not in p:
        bad.append("permission is named")
    return bad


class Notifier:
    def __init__(self, show, clock_ms, window_ms=DAY_MS, permission="input_monitoring", max_attempts=3):
        if permission not in PERMISSIONS:
            raise ValueError("permission")
        self.show, self.clock, self.window, self.permission, self.max_attempts = show, clock_ms, window_ms, permission, max_attempts
        self.last_shown = {}                 # cause -> time of the last SHOWN notice (memory only)
        self.pending = []                    # [(cause, notice, failed_attempts)], first come first served
        self.counters = {}                   # (name, outcome) -> int: counts only
        self._active = set()                 # runtime reasons that were present at the last poll
        self._seen = {}                      # source name -> number of entries already taken
        self._incident_seen = 0

    def _count(self, name):
        self.counters[name] = self.counters.get(name, 0) + 1

    def _due(self, cause, now):
        last = self.last_shown.get(cause)
        return last is None or now - last >= self.window            # exactly one window later is allowed; a clock that went backwards is not

    def submit(self, kind, variant="", params=None):
        """Returns 'queued', 'suppressed', 'duplicate', 'unknown' or 'invalid'. Never raises, never calls the adapter."""
        n = build(kind, variant, params)
        if n is None:
            self._count("unknown")
            return "unknown"
        if kind == "permission_missing" and "permission" not in n["params"]:
            n["params"]["permission"] = self.permission
        if validate(n):
            self._count("invalid")
            return "invalid"
        cause = cause_of(kind, "" if kind != "incident" else n["text_id"].rsplit(".", 1)[1])
        if any(c == cause for c, _, _ in self.pending):
            self._count("duplicate")
            return "duplicate"
        try:
            now = self.clock()
        except Exception:
            self._count("clock_failed")
            return "suppressed"
        if not self._due(cause, now):
            self._count("suppressed")
            return "suppressed"
        self.pending.append((cause, n, 0))
        return "queued"

    def deliver(self):
        """Shows what is queued, in order. The 24 h slot is used up only when the adapter answered exactly True; a failing adapter is tried again at the next
        call, at most `max_attempts` times per notice, then the notice is dropped and counted. Returns the notices shown."""
        shown, keep = [], []
        for cause, n, tries in self.pending:
            try:
                now = self.clock()
                if not self._due(cause, now):
                    self._count("suppressed")
                    continue
                ok = self.show(n) is True
            except Exception:
                ok = False
                now = None
            if ok:
                self.last_shown[cause] = now
                shown.append(n)
                self._count("shown")
            elif tries + 1 >= self.max_attempts:
                self._count("dropped")
            else:
                self._count("show_failed")
                keep.append((cause, n, tries + 1))
        self.pending = keep
        return shown

    # ---- links to the rest of the product
    def poll_runtime(self, rt):
        """Takes the runtime's new notices and the reasons that appeared since the last call (13.5 rows 9, 10, 13, 14 and the models flag)."""
        new = rt.notices[self._seen.get("runtime", 0):]
        self._seen["runtime"] = len(rt.notices)
        for kind, detail in new:
            if kind == "incident":
                i = self._incident_seen
                self._incident_seen += 1
                outcome = detail.split(":", 1)[0] if isinstance(detail, str) else ""
                target = rt.incident_apps[i] if i < len(rt.incident_apps) else None
                p = {"target": target} if isinstance(target, str) and _APP.fullmatch(target or "") else {}
                self.submit("incident", "unrecovered" if outcome == "UNRECOVERED" else "restored", p)
            elif kind in IGNORED:
                continue
            else:
                self.submit(kind)
        try:
            reasons = set(rt.explain(rt.app_id)[1]) if rt.app_id is not None else set()
        except Exception:
            reasons = set()
        for r in sorted((reasons & set(REASON_KIND)) - self._active):
            self.submit(REASON_KIND[r])
        self._active = reasons & set(REASON_KIND)

    def poll_list(self, name, entries):
        """Another module's notice list: tuples (kind, detail) or plain strings (the store). Only the kind is used, except for a hotkey chord."""
        new = entries[self._seen.get(name, 0):]
        self._seen[name] = len(entries)
        for e in new:
            kind, detail = (e, "") if isinstance(e, str) else (e[0], e[1] if len(e) > 1 else "")
            if kind in IGNORED:
                continue
            self.submit(kind, "", {"chord": detail} if kind == "hotkey_fallback" and detail else None)
