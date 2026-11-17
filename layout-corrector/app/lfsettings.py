"""AP-4 settings, portable part: validated setters, effect on the runtime, persistence through the store, the exception list commands, the hotkey
fallback procedure of 13.3. No user interface, no OS registration: "start at login" and the OS hotkey registration go through functions the OS adapter
injects (none exists here). Notices are names only. Items marked MY READING are not in the specification (see audit/AP7_RT19_readings.md style lists)."""
import re

import lfruntime as R
import lfstore as S

# ---- hotkey (13.3). The defaults are "proposed ... to be confirmed by the requester (16.3)": OPEN, nothing here confirms them. Chords are ASCII names.
DEFAULT_CHORD = {"windows": "Pause", "macos": "Ctrl+Alt+Cmd+Space"}
FALLBACK_CHORDS = {"windows": ("Ctrl+Alt+Pause", "Ctrl+Alt+Space"), "macos": ("Ctrl+Alt+Cmd+L", "Ctrl+Alt+Cmd+K")}
_MODS = ("Ctrl", "Alt", "Shift", "Cmd", "Win")
_KEY = re.compile(r"[A-Z0-9]|F(?:[1-9]|1[0-9]|2[0-4])|Space|Pause|Esc|Tab|Enter|Insert|Delete|Home|End|PageUp|PageDown|Left|Right|Up|Down")
_NEEDS_MOD = re.compile(r"[A-Z0-9]|Space|Tab|Enter|Esc|Delete|Home|End|PageUp|PageDown|Left|Right|Up|Down|Insert")   # MY READING: a bare key that types or edits would be swallowed
_CHANNEL = re.compile(r"[a-z][a-z0-9_-]{0,31}")          # the specification names an update channel but no values (AP-4, AP-9): shape only, no list


class SettingsError(ValueError):
    pass


def valid_chord(chord, platform):
    """True for 'Mod+Mod+Key' in the canonical order, modifiers from the platform's set, each at most once; a key that would type or edit needs a modifier."""
    if not isinstance(chord, str) or len(chord) > 40 or platform not in DEFAULT_CHORD:
        return False
    parts = chord.split("+")
    mods, key = parts[:-1], parts[-1]
    allowed = tuple(m for m in _MODS if m != ("Win" if platform == "macos" else "Cmd"))
    if len(set(mods)) != len(mods) or any(m not in allowed for m in mods) or mods != sorted(mods, key=_MODS.index):
        return False
    if _KEY.fullmatch(key) is None:
        return False
    return bool(mods) or _NEEDS_MOD.fullmatch(key) is None


def activate_hotkey(platform, requested, register):
    """13.3: try the chosen chord, then the default, then the fallback list; `register(chord)` returns True only when the OS accepted it (anything else, an
    exception included, means taken or failed). Never binds to a chord that was not accepted. Returns (active chord or None, [notice]). The notice tells the
    user which chord is active (MY READING: also when the first choice worked nothing is said)."""
    if platform not in DEFAULT_CHORD:
        raise SettingsError("platform")
    order = []
    for c in ([requested] if requested else []) + [DEFAULT_CHORD[platform]] + list(FALLBACK_CHORDS[platform]):
        if c not in order and valid_chord(c, platform):
            order.append(c)
    for i, c in enumerate(order):
        try:
            ok = register(c) is True
        except Exception:
            ok = False
        if ok:
            return c, ([] if i == 0 else [("hotkey_fallback", c)])
    return None, [("hotkey_unavailable", "")]


class Settings:
    """`store` may be None (memory only). `autostart(enabled) -> bool` is the OS adapter's registration (none here)."""

    def __init__(self, store, state, runtime, autostart=None, platform="windows", diag=None):
        self.store, self.state, self.rt, self.autostart, self.platform, self.diag = store, state, runtime, autostart, platform, diag
        self.notices = []
        self.deleted = False                 # after delete_all_data nothing is written back at shutdown until the user changes something again
        self.apply_to_runtime()

    # ---- reading
    def get(self):
        return dict(self.state.settings)

    def diagnostics_opt_in(self):
        """The opt-in callable of the crash reporter (`CrashReporter(opt_in=...)`): always the current stored value."""
        return self.state.settings["diagnostics_opt_in"] is True

    def apply_to_runtime(self):
        self.rt.auto_enabled = self.state.settings["auto_correction"] is True
        self.rt.load_prefs(self.state.apps)
        self.rt.apply_mode()

    # ---- persistence: memory is the truth of this session; a failed save is reported, never hidden, never an exception for the caller
    def _persist(self):
        self.deleted = False
        if self.store is None:
            return True
        try:
            S.sync_from_engine(self.rt.engine, self.state)
            ok = self.store.save(self.state) is True
        except Exception:
            ok = False
        if not ok:
            self.notices.append(("settings_not_saved", ""))
        return ok

    def _set(self, key, value):
        self.state.settings[key] = value
        return self._persist()

    # ---- the settings of AP-4
    def set_auto_correction(self, on):
        if not isinstance(on, bool):
            raise SettingsError("auto_correction")
        self.rt.auto_enabled = on
        self.rt.apply_mode()
        return self._set("auto_correction", on)

    def set_diagnostics_opt_in(self, on):
        if not isinstance(on, bool):
            raise SettingsError("diagnostics_opt_in")
        return self._set("diagnostics_opt_in", on)

    def set_update_channel(self, name):
        if not isinstance(name, str) or _CHANNEL.fullmatch(name) is None:
            raise SettingsError("update_channel")
        return self._set("update_channel", name)

    def set_hotkey(self, chord):
        """Stores the CHOSEN chord (None = the default). Registering it is `activate_hotkey` with the OS adapter's `register`."""
        if chord is not None and not valid_chord(chord, self.platform):
            raise SettingsError("hotkey")
        return self._set("hotkey", chord)

    def set_start_at_login(self, on):
        """The OS registration comes first; the setting changes only when it succeeded, so the stored value never claims what the system does not do."""
        if not isinstance(on, bool):
            raise SettingsError("start_at_login")
        if self.autostart is not None:
            try:
                done = self.autostart(on) is True
            except Exception:
                done = False
            if not done:
                self.notices.append(("autostart_failed", ""))
                return False
        elif on != self.state.settings["start_at_login"]:
            self.notices.append(("autostart_failed", ""))      # no adapter: the registration cannot be done, so the stored value is not changed
            return False
        return self._set("start_at_login", on)

    def set_esc_undoes(self, app_id, on):
        if not R.valid_app_id(app_id) or not isinstance(on, bool):
            raise SettingsError("esc_undoes")
        self.rt.apps.setdefault(app_id, R.AppState("UNKNOWN")).esc_undoes = on
        self.state.apps = self.rt.prefs()
        return self._persist()

    def set_blacklist(self, app_id, on):
        if not R.valid_app_id(app_id) or not isinstance(on, bool):
            raise SettingsError("blacklist")
        self.rt.blacklist(app_id, on)
        self.state.apps = self.rt.prefs()
        return self._persist()

    def reenable(self, app_id):
        r = self.rt.reenable(app_id)
        self.state.apps = self.rt.prefs()
        self._persist()
        return r

    # ---- the exception list: the ENGINE's list is the source (sync_from_engine copies it back at every save and at stop), so every command acts on it first
    def exceptions(self):
        return list(self.rt.engine._exc_order)

    def delete_exception(self, direction, word):
        item = (direction, word)
        if item not in self.rt.engine._exc_order:
            return False
        self.rt.engine._exc_order.pop(item, None)
        self.rt.engine.exceptions.discard(item)
        self._persist()
        return True

    def clear_exceptions(self):
        self.rt.engine._exc_order.clear()
        self.rt.engine.exceptions.clear()
        return self._persist()

    def export_exceptions(self):
        S.sync_from_engine(self.rt.engine, self.state)
        return S.Store.export_exceptions(self.state)

    # ---- Reset and Delete all data (AP-5)
    def _defaults(self, call_adapter):
        """The default settings, except that `start_at_login` keeps describing what the SYSTEM does: it changes to the default only when the OS
        registration was really changed (Reset: the adapter is called) and otherwise stays as it is (no adapter, a failing adapter, or Delete all data,
        which must not register or unregister anything). A failure is reported with the notice `autostart_failed`."""
        d, cur = dict(S.DEFAULT_SETTINGS), self.state.settings["start_at_login"]
        want = d["start_at_login"]
        if cur == want:
            return d
        if call_adapter and self.autostart is not None:
            try:
                done = self.autostart(want) is True
            except Exception:
                done = False
            if done:
                return d
        if call_adapter:
            self.notices.append(("autostart_failed", ""))
        d["start_at_login"] = cur
        return d

    def reset(self):
        """Defaults for settings and the application list; the exception list is kept (a reading of mine, as in the matrix)."""
        S.sync_from_engine(self.rt.engine, self.state)
        self.state.settings, self.state.apps = self._defaults(True), {}
        for a in self.rt.apps.values():
            a.blacklisted = a.esc_undoes = False
        self.apply_to_runtime()
        return self._persist()

    def delete_all_data(self):
        """Settings, exceptions and the store's own files; the exception list of the engine is emptied too, so nothing is written back at stop.
        Returns (deleted, skipped) names, or None without a store."""
        self.rt.engine._exc_order.clear(); self.rt.engine.exceptions.clear()
        self.state.settings, self.state.apps, self.state.exceptions = self._defaults(False), {}, []
        for a in self.rt.apps.values():
            a.blacklisted = a.esc_undoes = False
        self.apply_to_runtime()
        self.deleted = True
        if self.diag is not None:
            try:
                self.diag.delete()                # AP-5: "Delete all data" removes the diagnostics too (they live in memory only)
            except Exception:
                self.notices.append(("delete_failed", ""))     # reported, and the files of the store are still removed below
        if self.store is None:
            return None
        try:
            return self.store.delete_all()
        except Exception:
            self.notices.append(("delete_failed", ""))      # memory is already empty; the files that could not be removed are reported, not hidden
            return None

    def shutdown(self):
        """The orderly end (lflifecycle.stop). Right after `delete_all_data` the store is not written again: \"Delete all data\" must stay deleted."""
        import lflifecycle as K
        return K.stop(self.rt, None if (self.deleted or self.store is None) else self.store, None if (self.deleted or self.store is None) else self.state)

