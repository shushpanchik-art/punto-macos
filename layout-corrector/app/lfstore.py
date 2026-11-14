"""lfstore.py - portable storage of the settings and the exception list (AP-4, AP-5, 13.3). Standard library only.

What it implements from the specification:
  * one versioned file per user with `schema_version`; a file of an OLDER version is migrated forward after a backup copy is
    made; an unreadable file is renamed aside and replaced by defaults, with a notice (AP-5);
  * the exception list: (direction, case-folded word) pairs, at most MAX_EXCEPTIONS, oldest first so that the least recently
    undone word is the one evicted after a restart as well (13.3), encrypted through a `Cipher` (13.3, AP-5);
  * view / delete one / clear all / export (AP-4); "Reset" restores the SETTINGS defaults and keeps the exceptions (my reading of
    AP-5: only "Delete all data" removes the exceptions); "Delete all data" removes the file and every copy this module made;
  * what is NOT stored, on purpose: the quarantine (13.5 row 10: "until restart or until the user re-enables it"), the incident
    counter (a counter in memory; diagnostics are opt-in and not part of this module), the support status (13.8: a result of the
    test suite shipped with the release, "never exceeds what the capabilities allow"), no typed text of any kind (RT-6).
Decisions that the specification does not make (marked, for the requester): a file with a NEWER schema_version than this program
knows is NOT touched: it is kept as it is, the program runs on defaults in memory and never writes (a downgrade must not destroy
the newer data); an exception entry or setting of the wrong type makes the whole file unreadable.
NOT here: the real `Cipher` (Windows DPAPI / Credential Manager, macOS Keychain) is OS code and BLOCKED. `TestOnlyCipher` is a
format check, NOT encryption."""
import base64
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reference"))
import lfengine as L  # noqa: E402

SCHEMA_VERSION = 1
DEFAULT_SETTINGS = {"auto_correction": True, "hotkey": None, "start_at_login": True, "diagnostics_opt_in": False,
                    "update_channel": "stable"}
_SETTING_TYPES = {"auto_correction": bool, "start_at_login": bool, "diagnostics_opt_in": bool, "update_channel": str}
DIRECTIONS = ("en2ru", "ru2en")


class Cipher:
    def encrypt(self, data: bytes) -> bytes: raise NotImplementedError
    def decrypt(self, data: bytes) -> bytes: raise NotImplementedError      # must raise on a wrong key or damaged data


class TestOnlyCipher(Cipher):
    """NOT ENCRYPTION: a keyed XOR with a check value, so that tests can see a wrong key and damaged data."""
    __test__ = False

    def __init__(self, key: bytes = b"k"):
        self.key = key

    def _x(self, d):
        return bytes(b ^ self.key[i % len(self.key)] for i, b in enumerate(d))

    def encrypt(self, data):
        return b"T1" + self._x(data)

    def decrypt(self, data):
        if not data.startswith(b"T1"):
            raise ValueError("bad header")
        out = self._x(data[2:])
        json.loads(out.decode("utf-8"))           # a wrong key yields garbage here
        return out


class StoreState:
    def __init__(self):
        self.settings = dict(DEFAULT_SETTINGS)
        self.apps = {}                            # app id -> {"blacklist": bool, "esc_undoes": bool}
        self.exceptions = []                      # [(direction, word)], oldest first


def _valid(doc):
    if not isinstance(doc, dict) or not isinstance(doc.get("schema_version"), int) or isinstance(doc.get("schema_version"), bool):
        raise ValueError("schema_version")
    st = doc.get("settings")
    if not isinstance(st, dict) or set(st) != set(DEFAULT_SETTINGS):
        raise ValueError("settings keys")
    for k, t in _SETTING_TYPES.items():
        if not isinstance(st[k], t):
            raise ValueError(k)
    if st["hotkey"] is not None and not isinstance(st["hotkey"], str):
        raise ValueError("hotkey")
    apps = doc.get("apps")
    if not isinstance(apps, dict):
        raise ValueError("apps")
    for k, v in apps.items():
        if not isinstance(k, str) or not k or not isinstance(v, dict) or set(v) != {"blacklist", "esc_undoes"} or \
                not all(isinstance(x, bool) for x in v.values()):
            raise ValueError("app entry")
    if not isinstance(doc.get("exceptions"), str):
        raise ValueError("exceptions")


class Store:
    def __init__(self, path, cipher: Cipher, migrations=None):
        self.path, self.cipher = path, cipher
        self.migrations = dict(migrations or {})      # {from_version: fn(doc) -> doc of the next version}
        self.read_only = False                        # a newer file: never written
        self.notices = []

    # -- file helpers ------------------------------------------------------------------------------------------------
    def _aside(self, tag):
        n = 0
        while os.path.exists(f"{self.path}.{tag}-{n}"):
            n += 1
        return f"{self.path}.{tag}-{n}"

    def _write(self, doc):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=1)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)

    def _encode(self, st: StoreState):
        ex = [[d, w] for d, w in st.exceptions]
        blob = self.cipher.encrypt(json.dumps(ex, ensure_ascii=False).encode("utf-8"))
        return {"schema_version": SCHEMA_VERSION, "settings": st.settings, "apps": st.apps,
                "exceptions": base64.b64encode(blob).decode("ascii")}

    def _decode(self, doc):
        _valid(doc)
        st = StoreState()
        st.settings, st.apps = dict(doc["settings"]), {k: dict(v) for k, v in doc["apps"].items()}
        ex = json.loads(self.cipher.decrypt(base64.b64decode(doc["exceptions"], validate=True)).decode("utf-8"))
        seen = {}
        for e in ex:
            if not (isinstance(e, list) and len(e) == 2 and e[0] in DIRECTIONS and isinstance(e[1], str) and e[1]
                    and not any(c.isspace() for c in e[1])):
                raise ValueError("exception entry")
            seen.pop((e[0], e[1]), None)
            seen[(e[0], e[1])] = None
        st.exceptions = list(seen)[-L.MAX_EXCEPTIONS:]       # the newest ones stay
        return st

    # -- load and save -----------------------------------------------------------------------------------------------
    def load(self) -> StoreState:
        self.notices, self.read_only = [], False
        if not os.path.exists(self.path):
            return StoreState()
        try:
            with open(self.path, encoding="utf-8") as f:
                doc = json.load(f)
            v = doc.get("schema_version") if isinstance(doc, dict) else None
            if isinstance(v, int) and not isinstance(v, bool) and v > SCHEMA_VERSION:
                self.read_only = True
                self.notices.append("newer_file_kept")
                return StoreState()
            migrated = False
            if isinstance(v, int) and not isinstance(v, bool) and v < SCHEMA_VERSION:
                bak = self._aside(f"backup-v{v}")
                with open(self.path, "rb") as a, open(bak, "wb") as b:
                    b.write(a.read())
                while doc["schema_version"] < SCHEMA_VERSION:
                    doc = self.migrations[doc["schema_version"]](doc)
                migrated = True
            st = self._decode(doc)
        except Exception:
            os.replace(self.path, self._aside("corrupt"))
            self.notices.append("file_unreadable_defaults")
            return StoreState()
        if migrated:
            self._write(self._encode(st))
            self.notices.append("migrated")
        return st

    def save(self, st: StoreState) -> bool:
        if self.read_only:
            return False
        self._write(self._encode(st))
        return True

    # -- the user's commands (AP-4) ----------------------------------------------------------------------------------
    def reset(self, st: StoreState):
        st.settings, st.apps = dict(DEFAULT_SETTINGS), {}
        return self.save(st)

    def delete_all(self):
        d, base = os.path.dirname(os.path.abspath(self.path)), os.path.basename(self.path)
        for n in os.listdir(d):
            if n == base or n.startswith(base + "."):
                os.remove(os.path.join(d, n))
        self.read_only = False

    @staticmethod
    def delete_exception(st: StoreState, direction, word):
        item = (direction, word)
        if item in st.exceptions:
            st.exceptions.remove(item)
            return True
        return False

    @staticmethod
    def clear_exceptions(st: StoreState):
        st.exceptions = []

    @staticmethod
    def export_exceptions(st: StoreState):
        return json.dumps([{"direction": d, "word": w} for d, w in st.exceptions], ensure_ascii=False, indent=1)


# -- the bridge to the engine ---------------------------------------------------------------------------------------
def apply_to_engine(engine, st: StoreState):
    """Load the stored exceptions into a new engine. `Engine.__init__` sorts them, so the recency order is restored here, through
    the engine's own ordering structure, so that after a restart the least recently undone word is the one evicted (13.3)."""
    engine.exceptions = set(st.exceptions)
    engine._exc_order = dict.fromkeys(st.exceptions)


def sync_from_engine(engine, st: StoreState):
    """Copy the engine's exception list (oldest first) into the state to be saved."""
    st.exceptions = list(engine._exc_order)
