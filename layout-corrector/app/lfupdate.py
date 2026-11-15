"""AP-9 updates, portable part: staging, verification, the switch-in rule, staged rollout and one-step rollback of the signed packages, on a directory. Standard
library only. Nothing is downloaded and no operating-system call is made; the package source, the signature scheme and the keys are NOT defined by the
specification and are injected (`verify`).

Specification: AP-9 "Application, model, lexicon and calibration package are signed and versioned (DP-7). A new package is switched in only at restart or when no
word is in progress; staged rollout; one-step rollback; a failed verification keeps the previous package (failure row 12)". DP-7: "signed and versioned, MUST carry
the hash of the calibration package (D5), and MUST support one-step rollback". Row 12: "A package update fails signature or hash verification: the previous package
stays active; a notice". Row 6: a calibration package refused by the validation of CA-9 leaves the previous valid package active.

MY READINGS (audit/AP7_RT19_readings.md, section 13; none agreed): the manifest fields and their canonical bytes; a package is a non-empty subset of four components
and carries the calibration hash whenever it carries a model; the version is three integers and must be newer than the active one; the staged rollout is
`bucket < rollout_percent` with a bucket the adapter supplies (the specification names no bucket and a persistent identifier would be a privacy decision);
'no word in progress' means no word being recorded and no undo or toggle in flight; rollback goes to the previous package or to the built-in one, discards the
package rolled back from and blocks its version; a state file that cannot be read means the built-in package."""
import hashlib
import json
import os
import re
import shutil

COMPONENTS = ("application", "model", "lexicon", "calibration")
MAX_BYTES = 10 * 1024 * 1024               # "Whole package ... at most 10 MB" (13.9 budget table); the value is the table's, the check is mine
BUILTIN = "builtin"
_VER = re.compile(r"(0|[1-9][0-9]{0,3})\.(0|[1-9][0-9]{0,3})\.(0|[1-9][0-9]{0,3})")
_HEX = re.compile(r"[0-9a-f]{64}")
MANIFEST_KEYS = {"version", "rollout_percent", "sha256"}
MAX_BLOCKED = 16


def vkey(v):
    m = _VER.fullmatch(v) if isinstance(v, str) else None
    return tuple(int(x) for x in m.groups()) if m else None


def canonical(manifest):
    return json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


class Updater:
    def __init__(self, root, verify, validate=None, bucket=0, notifier=None):
        self.root, self.verify, self.validate, self.bucket, self.notifier = root, verify, validate, bucket, notifier
        self.counters = {}
        self.log = []                                   # (event, detail) codes, never text of a package
        os.makedirs(os.path.join(root, "packages"), exist_ok=True)
        self.state = self._load()
        self._gc()

    # -- state ---------------------------------------------------------------------------------------------------------------
    def _count(self, k):
        self.counters[k] = self.counters.get(k, 0) + 1

    def _path(self, *p):
        return os.path.join(self.root, *p)

    def _fresh(self):
        return {"active": BUILTIN, "previous": None, "staged": None, "blocked": []}

    def _ok_state(self, s):
        if not isinstance(s, dict) or set(s) != {"active", "previous", "staged", "blocked"}:
            return False
        def ver(v, allow_none, allow_builtin):
            return (v is None and allow_none) or (v == BUILTIN and allow_builtin) or vkey(v) is not None
        return (ver(s["active"], False, True) and ver(s["previous"], True, True) and ver(s["staged"], True, False)
                and isinstance(s["blocked"], list) and len(s["blocked"]) <= MAX_BLOCKED and all(vkey(b) for b in s["blocked"]))

    def _load(self):
        p = self._path("state.json")
        try:
            with open(p, "r", encoding="utf-8") as f:
                s = json.load(f)
            if self._ok_state(s):
                return s
        except FileNotFoundError:
            return self._fresh()
        except (OSError, ValueError):
            pass
        try:
            os.replace(p, p + ".bad")                   # the unreadable state is kept aside; the built-in package is used
        except OSError:
            pass
        self._count("state_unreadable")
        return self._fresh()

    def _save(self, s):
        tmp = self._path("state.json.tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(s, f, sort_keys=True)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self._path("state.json"))
        except BaseException:
            try:
                os.remove(tmp)                           # the module's own temporary file never stays behind
            except OSError:
                pass
            raise
        self.state = s

    def _gc(self):
        """Removes what the state does not reference (a crashed staging, a package that was replaced)."""
        keep = {v for v in (self.state["active"], self.state["previous"], self.state["staged"]) if v and v != BUILTIN}
        d = self._path("packages")
        for n in os.listdir(d):
            if n not in keep:
                shutil.rmtree(os.path.join(d, n), ignore_errors=True)

    def _fail(self, code):
        self._count("rejected_" + code)
        self.log.append(("rejected", code))
        if self.notifier is not None:
            try:
                self.notifier.submit("update_failed")
            except Exception:
                self._count("notify_failed")
        return "rejected:" + code

    # -- staging -------------------------------------------------------------------------------------------------------------
    def stage(self, manifest, signature, files):
        """Verifies a package and stages it. `files` maps a component name to bytes. Returns 'staged', 'duplicate', 'not_yet' (the rollout has not reached this
        device; no notice) or 'rejected:<code>' (the previous package stays active and a notice is queued, row 12). Nothing of the active package is touched."""
        try:
            if not isinstance(manifest, dict) or set(manifest) != MANIFEST_KEYS or not isinstance(files, dict):
                return self._fail("shape")
            v, pct, sums = manifest["version"], manifest["rollout_percent"], manifest["sha256"]
            if vkey(v) is None:
                return self._fail("version")
            if type(pct) is not int or not 0 <= pct <= 100:
                return self._fail("rollout")
            if (not isinstance(sums, dict) or not sums or not set(sums) <= set(COMPONENTS) or set(sums) != set(files)
                    or not all(isinstance(h, str) and _HEX.fullmatch(h) for h in sums.values())):
                return self._fail("components")
            if "model" in sums and "calibration" not in sums:
                return self._fail("calibration_hash_missing")          # DP-7
            if not all(isinstance(b, (bytes, bytearray)) for b in files.values()) or sum(len(b) for b in files.values()) > MAX_BYTES:
                return self._fail("size")
            try:
                ok = self.verify(canonical(manifest), signature) is True
            except Exception:
                ok = False
            if not ok:
                return self._fail("signature")
            for n, b in files.items():
                if hashlib.sha256(bytes(b)).hexdigest() != sums[n]:
                    return self._fail("hash")
            if v in self.state["blocked"]:
                return self._fail("blocked")
            if vkey(v) <= max([vkey(self.state["active"])] if self.state["active"] != BUILTIN else [(0, 0, 0)]):
                return self._fail("not_newer")
            if v == self.state["staged"]:
                self._count("duplicate")
                return "duplicate"
            if self.state["staged"] is not None and vkey(v) <= vkey(self.state["staged"]):
                return self._fail("not_newer")
            if not (type(self.bucket) is int and 0 <= self.bucket < 100):
                return self._fail("bucket")
            if self.bucket >= pct:
                self._count("not_yet")
                return "not_yet"
        except Exception:
            return self._fail("error")
        d = self._path("packages", v)
        tmp = d + ".tmp"
        try:
            shutil.rmtree(tmp, ignore_errors=True)
            os.makedirs(tmp)
            for n, b in files.items():
                with open(os.path.join(tmp, n), "wb") as f:
                    f.write(bytes(b))
                    f.flush()
                    os.fsync(f.fileno())
            shutil.rmtree(d, ignore_errors=True)
            os.replace(tmp, d)
            s = dict(self.state, staged=v)
            self._save(s)
        except OSError:
            shutil.rmtree(tmp, ignore_errors=True)
            self._gc()
            return self._fail("storage")
        self._gc()                                       # a replaced staged package goes
        self.log.append(("staged", v))
        return "staged"

    # -- the switch ----------------------------------------------------------------------------------------------------------
    @staticmethod
    def idle(rt):
        """No word in progress: nothing is being recorded and no undo or toggle is in flight."""
        e = rt.engine
        return not e.run and e.undoing is None and getattr(e, "toggling", None) is None and getattr(e, "manual", None) is None

    def switch_if_idle(self, rt):
        return self._switch(self.idle(rt))

    def at_restart(self):
        """The one other moment the specification allows: a restart (no word exists in a new process)."""
        return self._switch(True)

    def _switch(self, allowed):
        s = self.state
        if s["staged"] is None:
            return "nothing_staged"
        if not allowed:
            self._count("busy")
            return "busy"
        v = s["staged"]
        paths = {n: os.path.join(self._path("packages", v), n) for n in os.listdir(self._path("packages", v))}
        try:
            ok = True if self.validate is None else self.validate(v, paths) is True
        except Exception:
            ok = False
        if not ok:
            self._save(dict(s, staged=None))
            self._gc()
            return self._fail("validation")
        try:
            self._save({"active": v, "previous": s["active"], "staged": None, "blocked": s["blocked"]})
        except OSError:
            return self._fail("storage")
        self._gc()
        self.log.append(("switched", v))
        return "switched"

    def rollback(self):
        """One step back: to the previous package or the built-in one. The package rolled back from is discarded and its version blocked. A second call with no
        new switch in between does nothing."""
        s = self.state
        if s["previous"] is None:
            self._count("nothing_to_roll_back")
            return "nothing"
        bad = s["active"]
        blocked = (s["blocked"] + ([bad] if bad != BUILTIN else []))[-MAX_BLOCKED:]
        try:
            self._save({"active": s["previous"], "previous": None, "staged": s["staged"], "blocked": blocked})
        except OSError:
            return self._fail("storage")
        self._gc()
        self.log.append(("rolled_back", bad))
        return "rolled_back"

    def active_files(self):
        """{component: path} of the active package, empty for the built-in one."""
        v = self.state["active"]
        if v == BUILTIN:
            return {}
        d = self._path("packages", v)
        return {n: os.path.join(d, n) for n in sorted(os.listdir(d))}
