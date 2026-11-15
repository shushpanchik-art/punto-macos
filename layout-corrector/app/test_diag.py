"""AP-11 diagnostics, portable part: numeric counters only, collected only with the opt-in, preview, export on explicit command, no transmission. The length
classes are an OPEN question: the tests use the PLACEHOLDER classes and decide nothing about them."""
import json, os, re, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lfdiag as D, lfruntime as R, lfengine as L, lfsettings as G, lfstore as S

CHECKS = 0
def T(c, w):
    global CHECKS
    CHECKS += 1
    if not c: raise AssertionError(w)
def raises(fn, exc=ValueError):
    try: fn()
    except exc: return True
    return False
M1 = {L.READ_RANGE, L.REPLACE_RANGE, L.READBACK, L.ROLLBACK}
on = [True]
def mk(edges=D.PROPOSED_EDGES): return D.Diagnostics(lambda: on[0], edges)
def total(doc):
    c = doc["counters"]; n = sum(c["corrections"].values()) + sum(c["undos"].values()) + sum(c["incidents"].values()) + sum(c["reasons"].values()) + c["rejected"]
    return n + sum(v for d in c["manual_conversions"].values() for v in d.values())

# ---- nothing without the opt-in; the preview is available before it
on[0] = False; d = mk()
d.record_correction("en2ru"); d.record_undo("ru2en"); d.record_manual("en2ru", 5); d.record_incident("UNRECOVERED"); d.record_reason("stream"); d.record_correction("bad")
p = d.preview()
T(total(p) == 0 and p["opt_in"] is False and D.validate_export(p, d.labels) == [], "before the opt-in the preview is the full document with zeros; nothing was counted, not even a rejection")
for odd in ("yes", 1, None, [True]):
    dd = D.Diagnostics(lambda odd=odd: odd); dd.record_correction("en2ru"); T(total(dd.preview()) == 0, f"only an exact True opts in: {odd!r}")
def boom(): raise RuntimeError("x")
dd = D.Diagnostics(boom); dd.record_correction("en2ru"); T(total(dd.preview()) == 0 and dd.preview()["opt_in"] is False, "an opt-in function that fails counts as no opt-in")
# ---- counting
on[0] = True; d = mk()
d.record_correction("en2ru"); d.record_correction("en2ru"); d.record_correction("ru2en"); d.record_undo("en2ru"); d.record_incident("RESTORED"); d.record_incident("UNRECOVERED"); d.record_incident("UNRECOVERED"); d.record_reason("stream")
c = d.preview()["counters"]
T(c["corrections"] == {"en2ru": 2, "ru2en": 1} and c["undos"] == {"en2ru": 1, "ru2en": 0} and c["incidents"] == {"RESTORED": 1, "UNRECOVERED": 2} and c["reasons"]["stream"] == 1 and c["rejected"] == 0, "the counters count")
for ln, lab in ((1, "1-3"), (3, "1-3"), (4, "4-6"), (6, "4-6"), (7, "7-12"), (12, "7-12"), (13, "13+"), (10000, "13+")):
    T(d.bucket(ln) == lab, f"placeholder class of {ln}: {lab}")
d.record_manual("en2ru", 5); d.record_manual("ru2en", 13); d.record_manual("en2ru", 5)
T(d.preview()["counters"]["manual_conversions"]["en2ru"]["4-6"] == 2 and d.preview()["counters"]["manual_conversions"]["ru2en"]["13+"] == 1, "manual conversions by direction and class")
T(D.labels((2, 5)) == ["1-2", "3-5", "6+"] and mk((2, 5)).bucket(3) == "3-5" and mk((1,)).labels == ["1-1", "2+"], "the classes come from the constructor, not from a fixed rule")
for bad in ((), (0,), (3, 3), (6, 3), (3.5,), [3], (True,), ("a",), None): T(raises(lambda: D.Diagnostics(lambda: True, bad)), f"bad edges refused: {bad!r}")
# invalid input is rejected and counted as a number only, never stored
before = total(d.preview())
for call in (lambda: d.record_correction("ghbdtn привет"), lambda: d.record_undo(None), lambda: d.record_manual("en2ru", 0), lambda: d.record_manual("en2ru", True), lambda: d.record_manual("en2ru", "5"), lambda: d.record_manual("xx", 5),
             lambda: d.record_incident("VERIFIED"), lambda: d.record_reason("ghbdtn"), lambda: d.record_reason(5)):
    call()
doc = d.preview(); T(doc["counters"]["rejected"] == 9 and total(doc) == before + 9 and "ghbdtn" not in json.dumps(doc) and "привет" not in json.dumps(doc), "invalid input: counted as rejected, never stored")
T(all(r in doc["counters"]["reasons"] for r in D.REASONS) and set(doc["counters"]["reasons"]) == set(D.REASONS), "reason codes are the fixed list")

# ---- the export is numbers under fixed keys
def leaves(x, path=()):
    if isinstance(x, dict):
        for k, v in x.items(): yield from leaves(v, path + (k,))
    else: yield path, x
doc = d.preview(); keys = set()
for path, v in leaves(doc["counters"]):
    T(isinstance(v, int) and not isinstance(v, bool), f"a count: {path}")
    keys.update(path)
T(keys <= set(D.DIRECTIONS) | set(D.OUTCOMES) | set(D.REASONS) | set(d.labels) | {"corrections", "undos", "manual_conversions", "incidents", "reasons", "rejected"}, "every key is a fixed code")
def invalid(mut):
    x = json.loads(json.dumps(doc)); mut(x); return D.validate_export(x, d.labels) != []
T(invalid(lambda x: x["counters"]["corrections"].update(en2ru="3")) and invalid(lambda x: x["counters"]["corrections"].update(en2ru=True)) and invalid(lambda x: x["counters"]["corrections"].update(en2ru=-1)) and invalid(lambda x: x["counters"]["undos"].update(extra=1)) and invalid(lambda x: x["counters"].update(words=["ghbdtn"])) and invalid(lambda x: x.update(note="hello")) and invalid(lambda x: x["counters"]["reasons"].pop("stream")) and invalid(lambda x: x.update(version=2)) and invalid(lambda x: x.update(opt_in="yes")), "the validator refuses text, wrong types, extra and missing keys")
T(D.validate_export([], d.labels) != [] and D.validate_export({}, d.labels) != [], "shape")
# ---- explicit export only
cwd = os.getcwd(); work = tempfile.mkdtemp(prefix="lfdiag_"); os.chdir(work)
try:
    d2 = mk(); d2.record_correction("en2ru"); d2.record_manual("ru2en", 8); d2.preview(); d2.export_json()
    T(os.listdir(work) == [], "counting, preview and export_json write nothing anywhere")
finally: os.chdir(cwd)
out = tempfile.mkdtemp(prefix="lfdiagout_")
p = d2.write_export(out)
T(p == os.path.join(out, D.EXPORT_NAME) and open(p).read() == d2.export_json() and (os.stat(p).st_mode & 0o777) == 0o600 and os.listdir(out) == [D.EXPORT_NAME], "the export command writes one file, 0600, the same document, no temporary file")
d2.record_correction("en2ru"); p2 = d2.write_export(out); T(json.load(open(p2))["counters"]["corrections"]["en2ru"] == 2, "a second export replaces the first")
for badname in ("", "../x", "a/b", ".", "..", None, 5): T(raises(lambda: d2.write_export(out, badname)), f"name refused: {badname!r}")
victim = os.path.join(out, "victim"); open(victim, "w").write("keep"); os.symlink(victim, os.path.join(out, "lnk.json"))
T(raises(lambda: d2.write_export(out, "lnk.json")) and open(victim).read() == "keep", "a link in place of the file is refused, target untouched")
os.mkdir(os.path.join(out, "dir.json")); T(raises(lambda: d2.write_export(out, "dir.json")), "a directory in place of the file is refused")
T(raises(lambda: d2.write_export(os.path.join(out, "missing")), OSError) and sorted(os.listdir(out)) == sorted([D.EXPORT_NAME, "victim", "lnk.json", "dir.json"]), "a missing directory: an error, nothing left behind")
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "lfdiag.py")).read()
T(not re.search(r"^\s*(import|from)\s+(socket|ssl|http|urllib|requests|smtplib|ftplib|asyncio|subprocess|webbrowser)", src, re.M), "the module has no network or process code: nothing can be sent")
T(re.search(r"^\s*(import|from)\s+(\w+)", src, re.M) is not None and set(re.findall(r"^\s*(?:import|from)\s+(\w+)", src, re.M)) <= {"json", "os", "stat", "tempfile"}, "only json, os, stat, tempfile are imported")

# ---- with the runtime: real events of the simulated field
def scorer(ids): return [-3, 9, -2]
def new(faults=None, opt=True, sc=scorer):
    f = L.SimField("", M1, faults); rt = R.Runtime(L.Engine(L.example_cal(), sc, {"en": {"hello"}, "ru": {"привет"}}), L.HookHealth(canary=False))
    on[0] = opt; dg = mk(); rt.diag = dg; rt.on_focus("A", f, "AUTO"); rt.on_gate(L.GATE_ALLOW); return rt, f, dg
def typed(rt, f, w, t0):
    for i, (ch, k) in enumerate(zip(w, L.keys_from_text(w, "en"))):
        f.type_user(ch); rt.on_hook_event(L.Event("key", k, "en", t0 + i), sig=("k", t0 + i))
    f.type_user(" "); rt.on_hook_event(L.Event("space", None, "en", t0 + len(w)))
rt, f, dg = new(); typed(rt, f, "ghbdtn", 100)
T("привет" in f.text and dg.preview()["counters"]["corrections"] == {"en2ru": 1, "ru2en": 0}, "an automatic correction that was VERIFIED counts")
r = rt.hotkey_undo(300); c = dg.preview()["counters"]
T(r is not None and r.outcome == "VERIFIED" and c["undos"]["en2ru"] == 1 and c["corrections"]["en2ru"] == 1, "an undo counts")
# ---- the other direction, produced by the engine itself: a scorer that favours English makes a Russian-layout word an English one (no counter is touched by hand)
def typed_ru(rt, f, w, t0):
    for i, (ch, k) in enumerate(zip(w, L.keys_from_text(w, "ru"))):
        f.type_user(ch); rt.on_hook_event(L.Event("key", k, "ru", t0 + i), sig=("k", t0 + i))
    f.type_user(" "); rt.on_hook_event(L.Event("space", None, "ru", t0 + len(w)))
EN_FAVOURED = lambda ids: [9, -3, -2]
rt, f, dg = new(sc=EN_FAVOURED); typed_ru(rt, f, "руддщ", 100)
T(f.text == "hello " and dg.preview()["counters"]["corrections"] == {"en2ru": 0, "ru2en": 1}, f"ru2en: the engine converted the word and it was counted on the ru2en side only ({f.text!r})")
r = rt.hotkey_undo(300); c = dg.preview()["counters"]
T(r is not None and r.outcome == "VERIFIED" and f.text == "руддщ " and c["undos"] == {"en2ru": 0, "ru2en": 1} and c["corrections"] == {"en2ru": 0, "ru2en": 1}, "ru2en: a VERIFIED undo is counted on the ru2en side only")
# both sides in one runtime: the counters are independent
rt, f, dg = new(sc=EN_FAVOURED if False else scorer); typed(rt, f, "ghbdtn", 100); rt.hotkey_undo(300)
rt2, f2, _ = new(sc=EN_FAVOURED); rt2.diag = dg                    # a second runtime (the cooldown after an undo is normative: 3 words) shares the counters
typed_ru(rt2, f2, "руддщ", 2000); rt2.hotkey_undo(2300)
c = dg.preview()["counters"]
T(c["corrections"] == {"en2ru": 1, "ru2en": 1} and c["undos"] == {"en2ru": 1, "ru2en": 1} and total(dg.preview()) == 4, "both directions: one correction and one undo each, nothing else")
# an undo of a word that was kept (no correction) counts nothing
rt, f, dg = new(sc=EN_FAVOURED); T(rt.hotkey_undo(10) is None and total(dg.preview()) == 0, "an undo with nothing to undo counts nothing")
rt, f, dg = new(); f.type_user("ghbdtn"); f.select(0, 6); r = rt.hotkey_convert(1000)
T(r.outcome == "VERIFIED" and dg.preview()["counters"]["manual_conversions"]["en2ru"]["4-6"] == 1, "a manual conversion counts by direction and class of its length")
rt, f, dg = new(); f.type_user("ghbdtn"); f.select(0, 6); rt.hotkey_convert(1000); rt.hotkey_toggle(1100)
T(total(dg.preview()) == 1, "a toggle is not a separate count (the specification lists none)")
rt, f, dg = new(faults={("replace", 1): "autocorrect"}); typed(rt, f, "ghbdtn", 100); c = dg.preview()["counters"]
T(rt.last_result.outcome in ("RESTORED", "UNRECOVERED") and c["incidents"][rt.last_result.outcome] == 1 and sum(c["corrections"].values()) == 0, "a replacement incident counts as an incident and not as a correction")
rt, f, dg = new(opt=False); typed(rt, f, "ghbdtn", 100); T("привет" in f.text and total(dg.preview()) == 0, "without the opt-in the product works and nothing is counted")
on[0] = True; rt.hotkey_undo(300); T(total(dg.preview()) == 1, "and counting starts when the opt-in is given")
class Bad:
    def record_correction(self, *a): raise RuntimeError("x")
rt, f, dg = new(); rt.diag = Bad(); typed(rt, f, "ghbdtn", 100); T("привет" in f.text, "a failing diagnostics object never disturbs a correction")
rt, f, dg = new(); dg.poll_runtime(rt); dg.poll_runtime(rt); rt.permission_ok = False; rt.apply_mode(); dg.poll_runtime(rt); dg.poll_runtime(rt)
T(dg.preview()["counters"]["reasons"]["permission"] == 1 and total(dg.preview()) == 1, "a reason code counts when it appears, not at every poll")
rt.permission_ok = True; rt.apply_mode(); dg.poll_runtime(rt); rt.permission_ok = False; rt.apply_mode(); dg.poll_runtime(rt)
T(dg.preview()["counters"]["reasons"]["permission"] == 2, "and again when it comes back")
# ---- consent transitions and Delete all while a reason code is active
# reading (section 9): a reason counts when it APPEARS while counting is on; one that is already there when the opt-in is given is not counted until it has gone and come back
rt, f, dg = new(opt=False); rt.permission_ok = False; rt.apply_mode(); dg.poll_runtime(rt)
T(dg.preview()["counters"]["reasons"]["permission"] == 0, "opt-in off: the reason appears, nothing is counted")
on[0] = True; dg.poll_runtime(rt); dg.poll_runtime(rt)
T(dg.preview()["counters"]["reasons"]["permission"] == 0, "opt-in given while the reason is active: it is not counted at once or at later polls")
rt.permission_ok = True; rt.apply_mode(); dg.poll_runtime(rt); rt.permission_ok = False; rt.apply_mode(); dg.poll_runtime(rt)
T(dg.preview()["counters"]["reasons"]["permission"] == 1, "gone and back with the opt-in on: counted")
on[0] = False; rt.permission_ok = True; rt.apply_mode(); dg.poll_runtime(rt); rt.permission_ok = False; rt.apply_mode(); dg.poll_runtime(rt)
T(dg.preview()["counters"]["reasons"]["permission"] == 1 and dg.preview()["opt_in"] is False, "opt-in withdrawn: appearances are not counted; the earlier count stays until the user deletes it")
on[0] = True; dg.poll_runtime(rt); T(dg.preview()["counters"]["reasons"]["permission"] == 1, "opt-in given again with the reason active: still not counted")
dg.delete(); T(total(dg.preview()) == 0, "Delete all with a reason active: zero")
dg.poll_runtime(rt); T(total(dg.preview()) == 0, "and the reason that is still active is not counted again after the deletion")
rt.permission_ok = True; rt.apply_mode(); dg.poll_runtime(rt); rt.permission_ok = False; rt.apply_mode(); dg.poll_runtime(rt)
T(dg.preview()["counters"]["reasons"]["permission"] == 1 and total(dg.preview()) == 1, "a new appearance after the deletion counts again")
# opt-in withdrawn: counters already collected are shown as they are, new events add nothing
rt, f, dg = new(); typed(rt, f, "ghbdtn", 100); on[0] = False; rt.hotkey_undo(300)
T(dg.preview()["counters"]["corrections"]["en2ru"] == 1 and dg.preview()["counters"]["undos"]["en2ru"] == 0 and dg.preview()["opt_in"] is False, "withdrawing the opt-in stops counting, the preview is still the real document")
on[0] = True
# ---- Settings: the opt-in setting is the switch; Delete all data clears the counters, not the user's exports
sd = tempfile.mkdtemp(prefix="lfdiagset_"); st = S.Store(os.path.join(sd, "settings.json"), S.TestOnlyCipher(b"k"), allow_test_cipher=True)
rt, f, _ = new(); sg = G.Settings(st, st.load(), rt); dg = D.Diagnostics(sg.diagnostics_opt_in); rt.diag = dg; sg.diag = dg
typed(rt, f, "ghbdtn", 100); T(total(dg.preview()) == 0 and dg.preview()["opt_in"] is False, "setting off: nothing counted")
sg.set_diagnostics_opt_in(True); f2 = L.SimField("", M1); rt.on_focus("A", f2, "AUTO"); rt.on_gate(L.GATE_ALLOW); typed(rt, f2, "ghbdtn", 1000)
T(dg.preview()["counters"]["corrections"]["en2ru"] == 1 and dg.preview()["opt_in"] is True, "setting on: counted")
ex = dg.write_export(out, "mine.json"); sg.delete_all_data(); T(total(dg.preview()) == 0 and os.path.exists(ex), "Delete all data: counters are zero, the user's own export file is not touched")
print(f"OK ({CHECKS} diagnostics checks; numeric counters under fixed keys, no transmission; the length classes are a PLACEHOLDER of an open question)")
