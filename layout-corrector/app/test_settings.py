"""AP-4 settings, portable part: validation, runtime effect, persistence and its failures, exception-list commands, hotkey fallback (fake registrar),
Reset, Delete all data. Temporary directories only; no OS registration, no interface. The real hotkey registration and "start at login" are NOT RUN."""
import json, os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lfsettings as G, lfstore as S, lfruntime as R, lfengine as L, lflifecycle as K

CHECKS = 0
def T(c, w):
    global CHECKS
    CHECKS += 1
    if not c: raise AssertionError(w)
def raises(fn, exc=G.SettingsError):
    try: fn()
    except exc: return True
    return False
M1 = {L.READ_RANGE, L.REPLACE_RANGE, L.READBACK, L.ROLLBACK}
def new_rt(): return R.Runtime(L.Engine(L.example_cal(), lambda ids: [-3, 9, -2], {"en": {"hello"}, "ru": {"мир"}}), L.HookHealth(canary=False))
def typed(rt, fld, w, t0=100):
    for i, (ch, k) in enumerate(zip(w, L.keys_from_text(w, "en"))):
        fld.type_user(ch); rt.on_hook_event(L.Event("key", k, "en", t0 + i), sig=("k", t0 + i))
    fld.type_user(" "); return rt.on_hook_event(L.Event("space", None, "en", t0 + len(w)))
def make(store=True, autostart=None, platform="windows", cipher=None):
    rt = new_rt(); fld = L.SimField("", M1); rt.on_focus("A", fld, "AUTO"); rt.on_gate(L.GATE_ALLOW)
    d = tempfile.mkdtemp(prefix="lfset_"); st = S.Store(os.path.join(d, "settings.json"), cipher or S.TestOnlyCipher(b"k"), allow_test_cipher=True) if store else None
    state = st.load() if st else S.StoreState()
    if st: S.apply_to_engine(rt.engine, state)
    return G.Settings(st, state, rt, autostart, platform), rt, fld, st, d

# ---- chords
for c in ("Pause", "Ctrl+Alt+Pause", "Ctrl+Alt+Space", "Ctrl+Shift+K", "F9", "Ctrl+F12", "Win+Q"):
    T(G.valid_chord(c, "windows"), f"windows chord accepted: {c}")
for c in ("Ctrl+Alt+Cmd+Space", "Ctrl+Alt+Cmd+L", "Ctrl+Alt+Cmd+K", "Shift+Cmd+F1"):
    T(G.valid_chord(c, "macos"), f"macos chord accepted: {c}")
for c in ("", None, 5, "Ctrl+", "+K", "K", "Space", "Esc", "Ctrl+Ctrl+K", "Alt+Ctrl+K", "Ctrl+Alt+Cmd+K", "Ctrl+Alt+k", "Ctrl+F25", "Ctrl+Alt+Pause+K", "Ctrl +K", "Ctrl+⌃", "Ctrl+Alt+Pause\n", "x" * 60):
    T(not G.valid_chord(c, "windows"), f"windows chord refused: {c!r}")
T(not G.valid_chord("Ctrl+Alt+Win+K", "macos") and not G.valid_chord("Pause", "linux"), "mac has no Win, unknown platform refused")
T(G.DEFAULT_CHORD["windows"] == "Pause" and G.FALLBACK_CHORDS["windows"] == ("Ctrl+Alt+Pause", "Ctrl+Alt+Space") and G.FALLBACK_CHORDS["macos"] == ("Ctrl+Alt+Cmd+L", "Ctrl+Alt+Cmd+K"), "defaults and fallbacks as written in 13.3 (proposed, not confirmed)")
T(all(G.valid_chord(c, p) for p in ("windows", "macos") for c in [G.DEFAULT_CHORD[p]] + list(G.FALLBACK_CHORDS[p])), "every listed chord is valid")
def registrar(taken, log):
    def reg(c):
        log.append(c); return c not in taken
    return reg
log = []; T(G.activate_hotkey("windows", None, registrar(set(), log)) == ("Pause", []) and log == ["Pause"], "first choice accepted: nothing else is tried, no notice")
log = []; r = G.activate_hotkey("windows", None, registrar({"Pause"}, log)); T(r == ("Ctrl+Alt+Pause", [("hotkey_fallback", "Ctrl+Alt+Pause")]) and log == ["Pause", "Ctrl+Alt+Pause"], "default taken: the first fallback, the user is told which chord is active")
log = []; r = G.activate_hotkey("windows", None, registrar({"Pause", "Ctrl+Alt+Pause"}, log)); T(r[0] == "Ctrl+Alt+Space" and log[-1] == "Ctrl+Alt+Space", "second fallback")
log = []; r = G.activate_hotkey("windows", None, registrar({"Pause", "Ctrl+Alt+Pause", "Ctrl+Alt+Space"}, log)); T(r == (None, [("hotkey_unavailable", "")]) and len(log) == 3, "all taken: no chord is bound, the user is told")
log = []; r = G.activate_hotkey("macos", None, registrar({"Ctrl+Alt+Cmd+Space"}, log)); T(r[0] == "Ctrl+Alt+Cmd+L", "macOS fallback list")
log = []; r = G.activate_hotkey("windows", "Ctrl+Shift+K", registrar({"Ctrl+Shift+K"}, log)); T(r[0] == "Pause" and log == ["Ctrl+Shift+K", "Pause"], "a taken user chord goes on to the default and the fallbacks, never bound silently")
log = []; r = G.activate_hotkey("windows", "Pause", registrar(set(), log)); T(log == ["Pause"], "the chosen chord equal to the default is tried once")
log = []; r = G.activate_hotkey("windows", "bad chord", registrar(set(), log)); T(r[0] == "Pause" and log == ["Pause"], "an invalid chosen chord is never offered to the OS")
def raising(c): raise OSError("registration")
T(G.activate_hotkey("windows", None, raising) == (None, [("hotkey_unavailable", "")]), "a registrar that raises means not bound")
for odd in ("yes", 1, None, [True], "True"):
    T(G.activate_hotkey("windows", None, lambda c, odd=odd: odd)[0] is None, f"only an exact True counts as accepted: {odd!r}")
T(raises(lambda: G.activate_hotkey("linux", None, lambda c: True)), "unknown platform")

# ---- automatic correction on/off
s, rt, fld, st, d = make()
T(rt.explain("A") == ("AUTO", []), "setup: AUTO")
T(s.set_auto_correction(False) is True and rt.explain("A") == ("MANUAL_ONLY", ["auto_off"]) and rt.engine.mode == "MANUAL_ONLY", "off: MANUAL_ONLY with the reason 'auto_off', not OFF")
typed(rt, fld, "ghbdtn"); T(fld.text == "ghbdtn ", "off: a typed wrong-layout word is not converted")
r = rt.hotkey_toggle(900) if False else None
T(s.set_auto_correction(True) is True and rt.explain("A") == ("AUTO", []), "on again: AUTO")
fld2 = L.SimField("", M1); rt.on_focus("A", fld2, "AUTO"); rt.on_gate(L.GATE_ALLOW); typed(rt, fld2, "ghbdtn", 2000); T("привет" in fld2.text, "on: converted")
for bad in (1, 0, "yes", None, [True]):
    T(raises(lambda: s.set_auto_correction(bad)), f"auto_correction needs a bool: {bad!r}")
T(S.Store(st.path, S.TestOnlyCipher(b"k"), allow_test_cipher=True).load().settings["auto_correction"] is True, "saved")
s.set_auto_correction(False); T(S.Store(st.path, S.TestOnlyCipher(b"k"), allow_test_cipher=True).load().settings["auto_correction"] is False, "saved off")
st2 = S.Store(st.path, S.TestOnlyCipher(b"k"), allow_test_cipher=True); s2 = G.Settings(st2, st2.load(), new_rt())
T(s2.rt.auto_enabled is False, "a new session starts with the stored value")

# ---- the other settings
s, rt, fld, st, d = make()
for ch in ("beta", "stable", "a", "x" * 32, "nightly-2", "ring_1"):
    T(s.set_update_channel(ch) is True and s.get()["update_channel"] == ch, f"channel accepted: {ch}")
for ch in ("", "Beta", "1a", "../x", "a b", "x" * 33, None, 5, "a\n", "é"):
    T(raises(lambda: s.set_update_channel(ch)) and s.get()["update_channel"] == "x" * 0 + "ring_1", f"channel refused: {ch!r}")
T(s.set_hotkey("Ctrl+Shift+K") is True and s.get()["hotkey"] == "Ctrl+Shift+K" and s.set_hotkey(None) is True and s.get()["hotkey"] is None, "hotkey stored, None means the default")
for c in ("K", "Ctrl+Ctrl+K", "Ctrl+Alt+Cmd+K", "", 5): T(raises(lambda: s.set_hotkey(c)), f"hotkey refused: {c!r}")
sent = []
rep = K.CrashReporter(tempfile.mkdtemp(), "1", sender=sent.append, opt_in=s.diagnostics_opt_in)
try: raise ValueError("ghbdtn")
except ValueError: ei = sys.exc_info()
rep.handle(*ei); T(sent == [], "diagnostics off: nothing is sent")
T(s.set_diagnostics_opt_in(True) is True, "opt-in on"); rep.handle(*ei); T(len(sent) == 1 and b"ghbdtn" not in sent[0], "diagnostics on: one content-free report is sent")
s.set_diagnostics_opt_in(False); rep.handle(*ei); T(len(sent) == 1, "off again: nothing more is sent")
T(raises(lambda: s.set_diagnostics_opt_in("yes")), "opt-in needs a bool")
# start at login: the OS registration decides
calls = []
s, rt, fld, st, d = make(autostart=lambda on: (calls.append(on), True)[1])
T(s.set_start_at_login(False) is True and s.get()["start_at_login"] is False and calls == [False], "adapter accepted: stored")
for res in (False, None, "yes", 1):
    s, rt, fld, st, d = make(autostart=lambda on, res=res: res)
    T(s.set_start_at_login(False) is False and s.get()["start_at_login"] is True and ("autostart_failed", "") in s.notices, f"adapter answered {res!r}: the stored value does not change, one notice")
def bad_adapter(on): raise OSError("x")
s, rt, fld, st, d = make(autostart=bad_adapter); T(s.set_start_at_login(False) is False and s.get()["start_at_login"] is True, "an adapter that raises: unchanged")
s, rt, fld, st, d = make(); T(s.set_start_at_login(False) is False and s.get()["start_at_login"] is True and s.set_start_at_login(True) is True, "no adapter: a change is refused, the same value is accepted")
T(raises(lambda: s.set_start_at_login("on")), "start_at_login needs a bool")

# ---- persistence failures are reported, never hidden, never thrown at the caller
class Boom(Exception): pass
s, rt, fld, st, d = make()
real = st.save
def failing(state): raise Boom("disk")
st.save = failing
T(s.set_auto_correction(False) is False and ("settings_not_saved", "") in s.notices and rt.explain("A")[1] == ["auto_off"], "a failing save: False, a notice, the choice still holds in this session")
st.save = real; T(s.set_auto_correction(True) is True, "and works again")
class Locked(S.Cipher):
    def encrypt(self, d): raise S.CipherUnavailable("locked")
    def decrypt(self, d): raise S.CipherUnavailable("locked")
s, rt, fld, st, d = make(cipher=Locked())
T(s.set_auto_correction(False) is False and os.listdir(d) == [] and ("settings_not_saved", "") in s.notices, "an unavailable key store: nothing written, reported")

# ---- application list persistence
s, rt, fld, st, d = make()
s.set_esc_undoes("com.example.A", True); s.set_blacklist("com.example.B", True)
T(st.load().apps == {"com.example.A": {"blacklist": False, "esc_undoes": True}, "com.example.B": {"blacklist": True, "esc_undoes": False}}, "the two per-application choices are saved")
T(raises(lambda: s.set_esc_undoes("", True)) and raises(lambda: s.set_blacklist("x", "yes")) and raises(lambda: s.set_esc_undoes(5, True)), "application settings are validated")
st3 = S.Store(st.path, S.TestOnlyCipher(b"k"), allow_test_cipher=True); s3 = G.Settings(st3, st3.load(), new_rt())
T(s3.rt.apps["com.example.B"].blacklisted and s3.rt.apps["com.example.A"].esc_undoes and s3.rt.explain("com.example.B")[1][0] == "blacklist", "a new session has them")
r = s.reenable("com.example.B"); T(st.load().apps.get("com.example.B") is None and r is not None, "re-enable is saved")
T(s.reenable("com.example.unknown") is None, "re-enable of an unknown application")

# ---- the exception list
s, rt, fld, st, d = make()
typed(rt, fld, "ghbdtn"); rr = rt.hotkey_undo(300)
T(rr is not None and s.exceptions() == [("en2ru", "ghbdtn")], "setup: an undo added an exception")
T(s.delete_exception("ru2en", "zzz") is False and s.delete_exception("en2ru", "ghbdtn") is True and s.exceptions() == [] and ("en2ru", "ghbdtn") not in rt.engine.exceptions, "delete one: gone from the engine")
s.shutdown(); T(S.Store(st.path, S.TestOnlyCipher(b"k"), allow_test_cipher=True).load().exceptions == [], "and it does not come back at shutdown (the engine list is what is saved)")
s, rt, fld, st, d = make(); typed(rt, fld, "ghbdtn"); rt.hotkey_undo(300)
exp = json.loads(s.export_exceptions()); T(exp == [{"direction": "en2ru", "word": "ghbdtn"}], "export")
T(s.clear_exceptions() is True and s.exceptions() == [] and json.loads(s.export_exceptions()) == [], "clear all")
s.shutdown(); T(S.Store(st.path, S.TestOnlyCipher(b"k"), allow_test_cipher=True).load().exceptions == [], "cleared stays cleared")

# ---- Reset keeps the exceptions; Delete all data removes everything
s, rt, fld, st, d = make(); typed(rt, fld, "ghbdtn"); rt.hotkey_undo(300)
s.set_auto_correction(False); s.set_update_channel("beta"); s.set_blacklist("com.example.B", True); s.set_esc_undoes("com.example.A", True)
T(s.reset() is True, "reset")
T(s.get() == S.DEFAULT_SETTINGS and rt.auto_enabled is True and not rt.apps["com.example.B"].blacklisted and not rt.apps["com.example.A"].esc_undoes and st.load().apps == {} and s.exceptions() == [("en2ru", "ghbdtn")], "reset: defaults, application choices cleared, exceptions kept, runtime follows")
foreign = os.path.join(d, "foreign.txt"); open(foreign, "w").write("mine")
s.set_blacklist("com.example.B", True)
out = s.delete_all_data()
T(out is not None and "settings.json" in out[0] and not os.path.exists(st.path) and open(foreign).read() == "mine", "delete all data: the store's files are gone, a foreign file is not touched")
T(s.exceptions() == [] and s.get() == S.DEFAULT_SETTINGS and not rt.apps["com.example.B"].blacklisted, "memory is emptied too")
s.shutdown(); T(not os.path.exists(st.path) and sorted(os.listdir(d)) == ["foreign.txt"], "shutdown after 'delete all' writes nothing back")
s.set_auto_correction(False); T(os.path.exists(st.path), "a new choice made afterwards is saved again")
os.remove(st.path); s.shutdown(); T(os.path.exists(st.path) and S.Store(st.path, S.TestOnlyCipher(b"k"), allow_test_cipher=True).load().settings["auto_correction"] is False, "and shutdown saves it again (the deleted flag ends with the new choice)")
# ---- Reset and Delete all keep start_at_login equal to what the SYSTEM does (defect confirmed on 8b3510e: Reset wrote True without calling the adapter)
def on_disk(st): return S.Store(st.path, S.TestOnlyCipher(b"k"), allow_test_cipher=True).load().settings
calls = []
s, rt, fld, st, d = make(autostart=lambda on: (calls.append(on), True)[1])
s.set_start_at_login(False); s.set_auto_correction(False); s.set_update_channel("beta")
T(s.reset() is True and calls == [False, True] and s.get() == S.DEFAULT_SETTINGS and on_disk(st) == S.DEFAULT_SETTINGS, "Reset with a working adapter: the adapter is told to register again, then the default is stored")
calls.clear(); T(s.reset() is True and calls == [], "Reset when the value already is the default: the adapter is not called")
for res in (False, None, "yes", 1):
    s, rt, fld, st, d = make(autostart=lambda on, res=res: res)
    s.autostart = lambda on: True; s.set_start_at_login(False); s.autostart = lambda on, res=res: res
    s.set_auto_correction(False); s.set_update_channel("beta")
    T(s.reset() is True and s.get()["start_at_login"] is False and s.get()["auto_correction"] is True and s.get()["update_channel"] == "stable" and ("autostart_failed", "") in s.notices, f"Reset, adapter answered {res!r}: everything else is reset, start_at_login keeps the real state, one notice")
    T(on_disk(st)["start_at_login"] is False and on_disk(st)["update_channel"] == "stable", f"and the file says the same ({res!r})")
s, rt, fld, st, d = make(autostart=lambda on: True); s.set_start_at_login(False)
def bad_adapter2(on): raise OSError("x")
s.autostart = bad_adapter2; s.reset(); T(s.get()["start_at_login"] is False and ("autostart_failed", "") in s.notices, "Reset, adapter raises: unchanged, noticed")
# no adapter in a later session
s, rt, fld, st, d = make(autostart=lambda on: True); s.set_start_at_login(False)
st9 = S.Store(st.path, S.TestOnlyCipher(b"k"), allow_test_cipher=True); s9 = G.Settings(st9, st9.load(), new_rt())
T(s9.get()["start_at_login"] is False and s9.reset() is True and s9.get()["start_at_login"] is False and ("autostart_failed", "") in s9.notices, "Reset without any adapter: the stored value is not claimed to have changed")
# Reset when saving fails: memory follows the adapter, the failure is reported
s, rt, fld, st, d = make(autostart=lambda on: True); s.set_start_at_login(False)
def failing_save(state): raise Boom("disk")
st.save = failing_save
T(s.reset() is False and ("settings_not_saved", "") in s.notices and s.get()["start_at_login"] is True, "Reset with a failing save: False, noticed, the memory shows what the adapter did")
# Delete all data neither registers nor unregisters anything
calls = []
s, rt, fld, st, d = make(autostart=lambda on: (calls.append(on), True)[1]); s.set_start_at_login(False); s.set_auto_correction(False)
out = s.delete_all_data()
T(out is not None and calls == [False] and s.get()["start_at_login"] is False and s.get()["auto_correction"] is True and not os.path.exists(st.path), "Delete all data: the adapter is not called again, start_at_login keeps the real state, the rest is default, the files are gone")
s.shutdown(); T(not os.path.exists(st.path) and ("autostart_failed", "") not in s.notices, "nothing is written back and no failure is reported")
# Delete all data when removing fails
s, rt, fld, st, d = make(); real_del = st.delete_all
def failing_delete(): raise OSError("busy")
st.delete_all = failing_delete; typed(rt, fld, "ghbdtn"); rt.hotkey_undo(300)
T(s.delete_all_data() is None and ("delete_failed", "") in s.notices and s.exceptions() == [] and s.get() == S.DEFAULT_SETTINGS, "Delete all data, a failing removal: reported, memory is empty anyway")
st.delete_all = real_del
# no text anywhere
s, rt, fld, st, d = make(); typed(rt, fld, "ghbdtn"); rt.hotkey_undo(300); s.set_auto_correction(False)
blob = b"".join(open(os.path.join(d, f), "rb").read() for f in os.listdir(d)) + repr(s.notices).encode()
T(b"ghbdtn" not in blob and "привет".encode() not in blob, "no typed word in the files (the exception list is encrypted) or in the notices")
# ---- fault injection (audit 6): failing writes keep the file, are reported, can be retried; a failing diagnostics delete does not stop Delete all data
import errno
for name in ("fsync", "replace"):
    st_, rt, fld, st, d = make(); st_.set_update_channel("beta"); before = open(st.path, "rb").read()
    real = getattr(os, name)
    def boom(*a, **k): raise OSError(errno.EIO, "injected")
    setattr(os, name, boom)
    try: ok = st_.set_update_channel("stable")
    finally: setattr(os, name, real)
    T(ok is False and open(st.path, "rb").read() == before and ("settings_not_saved", "") in st_.notices, f"a failing {name}: False, the old file is intact, one notice")
    T(not [f for f in os.listdir(d) if f != "settings.json" and "lock" not in f], f"a failing {name}: no temporary file left")
    T(st_.get()["update_channel"] == "stable", "memory stays the truth of this session")
    T(S.Store(st.path, S.TestOnlyCipher(b"k"), allow_test_cipher=True).load().settings["update_channel"] == "beta", f"after a failing {name} a restart reads the previous value")
    T(st_.set_update_channel("stable") is True and S.Store(st.path, S.TestOnlyCipher(b"k"), allow_test_cipher=True).load().settings["update_channel"] == "stable", f"retry after {name} succeeds and is read back after a restart")
class BadDiag:
    def delete(self): raise RuntimeError("injected")
st_, rt, fld, st, d = make(); st_.diag = BadDiag(); st_.set_update_channel("beta")
try: r = st_.delete_all_data(); err = None
except Exception as e: r, err = None, e
T(err is None and not os.path.exists(st.path), f"a failing diagnostics delete does not stop Delete all data: the store files are still removed ({err!r})")
T(("delete_failed", "") in st_.notices, "and it is reported by name")
print(f"OK ({CHECKS} settings checks; temporary directories, fake registrar and fake adapter; no OS registration, no user interface)")
