"""AP-11 diagnostics, portable part: numeric counters, a preview, an export on an explicit command. Nothing is sent anywhere (this module has no network code
and no sender); nothing is written unless the user asks for an export; nothing is persisted (the counters live in memory, see audit/AP7_RT19_readings.md,
section 9). Counting happens only while `opt_in()` is true.

Specification: AP-11 "Counters only (corrections, undos, manual conversions, reason codes, incidents). They are shown to the user before the opt-in and can be
exported by the user"; 14 (field quality signal) "Opt-in counters: corrections, undos, manual conversions by length and direction".
OPEN, NOT decided here: the length classes. The specification says "by length" and fixes no class boundaries; PROPOSED_EDGES below is a placeholder that keeps
the module testable and is NOT a decision. Everything in an export is a fixed key with an integer value: no typed text, no word, no application name, no path."""
import json
import os
import stat
import tempfile

SCHEMA, VERSION = "lf-diagnostics", 1
DIRECTIONS = ("en2ru", "ru2en")
OUTCOMES = ("RESTORED", "UNRECOVERED")
REASONS = ("instance", "support_unknown", "blacklist", "quarantine", "permission", "layout", "no_write_capability", "support_manual", "no_auto_capability",
           "models", "stream", "watchdog", "worker", "auto_off")
PROPOSED_EDGES = (3, 6, 12)                       # PLACEHOLDER (open question): classes 1-3, 4-6, 7-12, 13 and more
EXPORT_NAME = "layout-corrector-diagnostics.json"


def labels(edges):
    out, lo = [], 1
    for e in edges:
        out.append(f"{lo}-{e}")
        lo = e + 1
    return out + [f"{lo}+"]


class Diagnostics:
    def __init__(self, opt_in, edges=PROPOSED_EDGES):
        if not (isinstance(edges, tuple) and edges and all(isinstance(e, int) and not isinstance(e, bool) and e >= 1 for e in edges) and list(edges) == sorted(set(edges))):
            raise ValueError("edges")
        self.opt_in, self.edges, self.labels = opt_in, edges, labels(edges)
        self._active = set()
        self.delete()

    def delete(self):
        """Delete all data (AP-5): the counters are zero again. Exports the user made are theirs and are not touched."""
        self.corrections = {d: 0 for d in DIRECTIONS}
        self.undos = {d: 0 for d in DIRECTIONS}
        self.manual = {d: {b: 0 for b in self.labels} for d in DIRECTIONS}
        self.incidents = {o: 0 for o in OUTCOMES}
        self.reasons = {r: 0 for r in REASONS}
        self.rejected = 0

    def _on(self):
        try:
            return self.opt_in() is True
        except Exception:
            return False                                           # when in doubt, nothing is counted

    def bucket(self, length):
        for e, lab in zip(self.edges, self.labels):
            if length <= e:
                return lab
        return self.labels[-1]

    def record_correction(self, direction):
        if not self._on():
            return
        if direction in DIRECTIONS:
            self.corrections[direction] += 1
        else:
            self.rejected += 1

    def record_undo(self, direction):
        if not self._on():
            return
        if direction in DIRECTIONS:
            self.undos[direction] += 1
        else:
            self.rejected += 1

    def record_manual(self, direction, length):
        if not self._on():
            return
        if direction in DIRECTIONS and isinstance(length, int) and not isinstance(length, bool) and length >= 1:
            self.manual[direction][self.bucket(length)] += 1
        else:
            self.rejected += 1

    def record_incident(self, outcome):
        if not self._on():
            return
        if outcome in OUTCOMES:
            self.incidents[outcome] += 1
        else:
            self.rejected += 1

    def record_reason(self, code):
        if not self._on():
            return
        if code in REASONS:
            self.reasons[code] += 1
        else:
            self.rejected += 1

    def poll_runtime(self, rt):
        """Counts a reason code each time it appears for the focused application (not at every call while it stays)."""
        try:
            now = set(rt.explain(rt.app_id)[1]) & set(REASONS) if rt.app_id is not None else set()
        except Exception:
            now = set()
        for r in sorted(now - self._active):
            self.record_reason(r)
        self._active = now

    # ---- what the user sees and exports
    def snapshot(self):
        return {"schema": SCHEMA, "version": VERSION, "opt_in": self._on(), "length_classes": "placeholder_open",
                "counters": {"corrections": dict(self.corrections), "undos": dict(self.undos),
                             "manual_conversions": {d: dict(v) for d, v in self.manual.items()},
                             "incidents": dict(self.incidents), "reasons": dict(self.reasons), "rejected": self.rejected}}

    def preview(self):
        """The exact document an export would contain, available before the opt-in (it then shows zeros: nothing is counted without it)."""
        doc = self.snapshot()
        if validate_export(doc, self.labels):
            raise ValueError("snapshot is not a valid export")
        return doc

    def export_json(self):
        return json.dumps(self.preview(), indent=1, sort_keys=True) + "\n"

    def write_export(self, directory, name=EXPORT_NAME):
        """Only on the user's explicit command: writes `name` into the directory the user chose (atomic, mode 0600). Refuses a link in place of the file and
        a name with path parts. Returns the path."""
        if not isinstance(name, str) or not name or os.path.basename(name) != name or name in (".", ".."):
            raise ValueError("name")
        text = self.export_json()
        path = os.path.join(directory, name)
        if os.path.islink(path) or (os.path.exists(path) and not stat.S_ISREG(os.lstat(path).st_mode)):
            raise ValueError("refusing to replace anything but a regular file")
        fd, tmp = tempfile.mkstemp(dir=directory, prefix=".lf-diag-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text)
                f.flush()
                os.fsync(f.fileno())
            os.chmod(tmp, 0o600)
            os.replace(tmp, path)
        except BaseException:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise
        return path


def validate_export(doc, class_labels):
    """Allow-list check: fixed keys only, integer values only (a bool is not an integer here). Empty list = acceptable."""
    bad = []
    def ints(d, keys, where):
        if not isinstance(d, dict) or sorted(d) != sorted(keys):
            bad.append(where + ": keys")
            return
        for k, v in d.items():
            if not (isinstance(v, int) and not isinstance(v, bool) and v >= 0):
                bad.append(f"{where}.{k}: not a count")
    if not isinstance(doc, dict) or sorted(doc) != ["counters", "length_classes", "opt_in", "schema", "version"]:
        return ["shape"]
    if doc["schema"] != SCHEMA or doc["version"] != VERSION or doc["length_classes"] != "placeholder_open" or not isinstance(doc["opt_in"], bool):
        bad.append("header")
    c = doc["counters"]
    if not isinstance(c, dict) or sorted(c) != ["corrections", "incidents", "manual_conversions", "reasons", "rejected", "undos"]:
        return bad + ["counters: keys"]
    ints(c["corrections"], DIRECTIONS, "corrections"); ints(c["undos"], DIRECTIONS, "undos"); ints(c["incidents"], OUTCOMES, "incidents"); ints(c["reasons"], REASONS, "reasons")
    if not (isinstance(c["rejected"], int) and not isinstance(c["rejected"], bool) and c["rejected"] >= 0):
        bad.append("rejected")
    m = c["manual_conversions"]
    if not isinstance(m, dict) or sorted(m) != sorted(DIRECTIONS):
        bad.append("manual: directions")
    else:
        for d in DIRECTIONS:
            ints(m[d], class_labels, "manual." + d)
    return bad
