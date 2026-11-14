import json, os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lfstore as S
import lfengine as L

CHECKS = 0
def T(c, w):
    global CHECKS
    CHECKS += 1
    if not c: raise AssertionError(w)

def fresh():
    d = tempfile.mkdtemp(prefix="lfstore_")
    return d, S.Store(os.path.join(d, "settings.json"), S.TestOnlyCipher(b"key"), allow_test_cipher=True)

d, s = fresh()
st = s.load()
T(st.settings == S.DEFAULT_SETTINGS and st.apps == {} and st.exceptions == [] and not os.path.exists(s.path), "no file: defaults, nothing written")
st.settings["auto_correction"] = False
st.apps["com.example.app"] = {"blacklist": True, "esc_undoes": False}
st.exceptions = [("en2ru", "ghbdtn"), ("ru2en", "руддщ")]
T(s.save(st) and not os.path.exists(s.path + ".tmp"), "save is atomic: no temp file is left")
raw = open(s.path, encoding="utf-8").read()
T("ghbdtn" not in raw and "руддщ" not in raw, "the exception words are not in the file in clear (they go through the Cipher)")
st2 = S.Store(s.path, S.TestOnlyCipher(b"key"), allow_test_cipher=True).load()
T(st2.settings["auto_correction"] is False and st2.apps == st.apps and st2.exceptions == st.exceptions, "round trip keeps settings, apps and the exception order")
T("quarantine" not in raw and "incident" not in raw and "support" not in raw, "quarantine, incidents and support status are not stored")

# unreadable: garbage, wrong key, wrong types, bad entries, bad base64
def bad(mut, label, cipher=None):
    d, s = fresh()
    st = S.StoreState(); st.exceptions = [("en2ru", "abc")]; s.save(st)
    doc = json.load(open(s.path, encoding="utf-8"))
    if mut is not None:
        mut(doc)
        json.dump(doc, open(s.path, "w", encoding="utf-8"))
    else:
        open(s.path, "w").write("{not json")
    s2 = S.Store(s.path, cipher or S.TestOnlyCipher(b"key"), allow_test_cipher=True)
    r = s2.load()
    names = os.listdir(d)
    T(r.settings == S.DEFAULT_SETTINGS and r.exceptions == [] and "file_unreadable_defaults" in s2.notices
      and any(n.startswith("settings.json.corrupt-") for n in names) and not os.path.exists(s.path), f"unreadable file renamed and defaults used: {label}")
bad(None, "not JSON")
bad(lambda x: x["settings"].update(auto_correction="yes"), "setting type")
bad(lambda x: x["settings"].pop("hotkey"), "missing setting")
bad(lambda x: x.update(exceptions="!!!"), "not base64")
bad(lambda x: x["apps"].update({"a": {"blacklist": 1, "esc_undoes": False}}), "app flag type")
bad(lambda x: x.update(schema_version=True), "schema_version bool")
bad(lambda x: x.update(schema_version=0), "older version without a migration")
d, s = fresh(); st = S.StoreState(); st.exceptions = [("en2ru", "abc")]; s.save(st)
s3 = S.Store(s.path, S.TestOnlyCipher(b"other"), allow_test_cipher=True); r = s3.load()
T(r.exceptions == [] and "file_unreadable_defaults" in s3.notices, "a wrong key makes the file unreadable, never half-read")
d, s = fresh(); st = S.StoreState(); st.exceptions = [("xx", "abc")]; s.save(st)
r = S.Store(s.path, S.TestOnlyCipher(b"key"), allow_test_cipher=True).load()
T(r.exceptions == [], "an exception with an unknown direction makes the file unreadable")
d, s = fresh(); st = S.StoreState(); st.exceptions = [("en2ru", "a b")]; s.save(st)
T(S.Store(s.path, S.TestOnlyCipher(b"key"), allow_test_cipher=True).load().exceptions == [], "an exception with white space makes the file unreadable")

# newer file: kept, never written
d, s = fresh(); st = S.StoreState(); s.save(st)
doc = json.load(open(s.path, encoding="utf-8")); doc["schema_version"] = 99; json.dump(doc, open(s.path, "w", encoding="utf-8"))
before = open(s.path, encoding="utf-8").read()
s2 = S.Store(s.path, S.TestOnlyCipher(b"key"), allow_test_cipher=True); r = s2.load()
T(r.settings == S.DEFAULT_SETTINGS and s2.read_only and "newer_file_kept" in s2.notices and s2.save(r) is False
  and open(s.path, encoding="utf-8").read() == before and os.listdir(d) == ["settings.json"], "a newer file is kept untouched and never written")

# migration forward with a backup
d, s = fresh(); st = S.StoreState(); st.exceptions = [("en2ru", "abc")]; s.save(st)
doc = json.load(open(s.path, encoding="utf-8")); doc["schema_version"] = 0; doc["old"] = 1; json.dump(doc, open(s.path, "w", encoding="utf-8"))
def mig(doc):
    doc = dict(doc); doc.pop("old"); doc["schema_version"] = 1; return doc
s2 = S.Store(s.path, S.TestOnlyCipher(b"key"), {0: mig}, allow_test_cipher=True); r = s2.load()
T(r.exceptions == [("en2ru", "abc")] and "migrated" in s2.notices and any(n.startswith("settings.json.backup-v0-") for n in os.listdir(d))
  and json.load(open(s.path, encoding="utf-8"))["schema_version"] == 1, "an older file is migrated forward after a backup copy")
s2 = S.Store(s.path, S.TestOnlyCipher(b"key"), {0: lambda d: 1 / 0}, allow_test_cipher=True)
doc = json.load(open(s.path, encoding="utf-8")); doc["schema_version"] = 0; json.dump(doc, open(s.path, "w", encoding="utf-8"))
r = s2.load()
T(r.exceptions == [] and "file_unreadable_defaults" in s2.notices, "a failing migration ends as an unreadable file; the backup stays")

# the user's commands
d, s = fresh(); st = S.StoreState(); st.settings["auto_correction"] = False; st.apps["x"] = {"blacklist": True, "esc_undoes": True}
st.exceptions = [("en2ru", "a"), ("en2ru", "b"), ("ru2en", "в")]; s.save(st)
T(S.Store.delete_exception(st, "en2ru", "a") and not S.Store.delete_exception(st, "en2ru", "a") and st.exceptions == [("en2ru", "b"), ("ru2en", "в")], "delete one entry")
ex = json.loads(S.Store.export_exceptions(st))
T(ex == [{"direction": "en2ru", "word": "b"}, {"direction": "ru2en", "word": "в"}], "export")
s.reset(st)
T(st.settings == S.DEFAULT_SETTINGS and st.apps == {} and len(st.exceptions) == 2, "Reset restores settings and keeps the exceptions")
S.Store.clear_exceptions(st); T(st.exceptions == [], "clear all")
s.save(st); s.delete_all()
T(os.listdir(d) == [], "Delete all data removes the file")
d, s = fresh(); open(s.path, "w").write("x"); s.load(); s.delete_all()
T(os.listdir(d) == [], "Delete all data also removes the copies the module made")

# the limit and the order
d, s = fresh(); st = S.StoreState(); st.exceptions = [("en2ru", f"w{i}") for i in range(L.MAX_EXCEPTIONS + 5)]; s.save(st)
r = S.Store(s.path, S.TestOnlyCipher(b"key"), allow_test_cipher=True).load()
T(len(r.exceptions) == L.MAX_EXCEPTIONS and r.exceptions[0] == ("en2ru", "w5"), "more than 10,000 entries: the oldest leave first")

# the engine: the order survives a restart, the next undo evicts the OLDEST stored word
scorer = lambda ids: [-3, 9, -2]
e = L.Engine(L.example_cal(), scorer, {})
st = S.StoreState(); st.exceptions = [("en2ru", f"w{i}") for i in range(L.MAX_EXCEPTIONS)]
S.apply_to_engine(e, st)
T(len(e.exceptions) == L.MAX_EXCEPTIONS and next(iter(e._exc_order)) == ("en2ru", "w0"), "the engine gets the stored order")
e.snapshot = None
M1 = {L.READ_RANGE, L.REPLACE_RANGE, L.READBACK, L.ROLLBACK}
import lfruntime as R
fld = L.SimField("", M1)
rt = R.Runtime(e, L.HookHealth(canary=False)); rt.on_focus("a", fld, "AUTO"); rt.on_gate(L.GATE_ALLOW)
for i, (ch, k) in enumerate(zip("ghbdtn", L.keys_from_text("ghbdtn", "en"))):
    fld.type_user(ch); rt.on_hook_event(L.Event("key", k, "en", 100 + i), sig=("k", i))
fld.type_user(" "); rt.on_hook_event(L.Event("space", None, "en", 200))
r = rt.hotkey_undo(300)
T(r is not None and r.outcome == "VERIFIED" and ("en2ru", "w0") not in e.exceptions and ("en2ru", "w1") in e.exceptions
  and ("en2ru", "ghbdtn") in e.exceptions, "after a restart the least recently undone stored word is evicted first")
st2 = S.StoreState(); S.sync_from_engine(e, st2)
T(st2.exceptions[-1] == ("en2ru", "ghbdtn") and len(st2.exceptions) == L.MAX_EXCEPTIONS, "the engine's list is copied back, newest last")
for bad_c in (S.TestOnlyCipher(b"k"), object(), None):
    try:
        S.Store(os.path.join(tempfile.mkdtemp(), "f.json"), bad_c); T(False, "a test cipher or a non-cipher must be refused")
    except (ValueError, TypeError):
        T(True, "the test double and non-ciphers are refused for a real store")
# delete_all removes only what this store owns (regression: a prefix test used to delete neighbours)
import re as _re
def make_tree(base="settings.json"):
    d = tempfile.mkdtemp(prefix="lfdel_")
    outside = tempfile.mkdtemp(prefix="lfout_")
    mk = lambda n, c="x": open(os.path.join(d, n), "w").write(c)
    owned = [base, base + ".tmp", base + ".corrupt-0", base + ".corrupt-12", base + ".backup-v0-0", base + ".backup-v3-7"]
    for n in owned: mk(n)
    foreign = [base + ".old", base + ".bak", base + ".corrupt-x", base + ".corrupt-", base + ".backup-v0", base + ".backup-v-1", base + ".tmp2",
               base + "X", "my." + base, base + ".json", base[:-1], "other.json", base + ".corrupt-0.keep", base + " copy", base + ".tmp.bak", base.upper()]
    for n in foreign: mk(n, "keep")
    os.mkdir(os.path.join(d, base + ".corrupt-5")); open(os.path.join(d, base + ".corrupt-5", "inner"), "w").write("keep")
    target = os.path.join(outside, "victim"); open(target, "w").write("victim")
    os.symlink(target, os.path.join(d, base + ".backup-v1-0"))
    os.symlink(outside, os.path.join(d, base + ".corrupt-9"))
    return d, outside, target, owned, foreign
d, outside, target, owned, foreign = make_tree()
s = S.Store(os.path.join(d, "settings.json"), S.TestOnlyCipher(b"k"), allow_test_cipher=True)
T(s.owned_names()[1] == sorted(owned + ["settings.json.backup-v1-0", "settings.json.corrupt-5", "settings.json.corrupt-9"]), "owned_names: only the exact patterns, links and a directory included in the CANDIDATES")
deleted, skipped = s.delete_all()
T(sorted(deleted) == sorted(owned), f"only the owned regular files are deleted: {sorted(deleted)}")
T(sorted(skipped) == ["settings.json.backup-v1-0", "settings.json.corrupt-5", "settings.json.corrupt-9"], f"links and a directory are skipped, reported: {skipped}")
left = sorted(os.listdir(d))
T(all(n in left for n in foreign), "every foreign file with a similar name is still there")
T(not any(n in left for n in owned), "no owned file is left")
T(open(os.path.join(d, "settings.json.corrupt-5", "inner")).read() == "keep", "the directory and its content are untouched")
T(os.path.islink(os.path.join(d, "settings.json.backup-v1-0")) and open(target).read() == "victim" and os.listdir(outside) == ["victim"], "a link is not followed: its target is intact, the link stays")
# the store file itself is a symlink: never followed, never removed
d2 = tempfile.mkdtemp(); out2 = tempfile.mkdtemp(); tg = os.path.join(out2, "t"); open(tg, "w").write("t")
os.symlink(tg, os.path.join(d2, "settings.json"))
s2 = S.Store(os.path.join(d2, "settings.json"), S.TestOnlyCipher(b"k"), allow_test_cipher=True)
T(s2.delete_all() == ([], ["settings.json"]) and open(tg).read() == "t" and os.path.islink(os.path.join(d2, "settings.json")), "a symbolic link as the store file is skipped")
# names with regular-expression characters; an empty or missing directory entry
d3 = tempfile.mkdtemp(); base = "a+b(1).json"
for n in (base, base + ".tmp", "aab(1)xjson", "a+b(1).jsonX"): open(os.path.join(d3, n), "w").write("x")
s3 = S.Store(os.path.join(d3, base), S.TestOnlyCipher(b"k"), allow_test_cipher=True)
dd, sk = s3.delete_all()
T(sorted(dd) == sorted([base, base + ".tmp"]) and sorted(os.listdir(d3)) == ["a+b(1).jsonX", "aab(1)xjson"], "regular-expression characters in the file name are literal")
T(S.Store(os.path.join(tempfile.mkdtemp(), "none.json"), S.TestOnlyCipher(b"k"), allow_test_cipher=True).delete_all() == ([], []), "nothing to delete")
# the names this module itself creates are exactly the owned ones
d4 = tempfile.mkdtemp(); s4 = S.Store(os.path.join(d4, "s.json"), S.TestOnlyCipher(b"k"), allow_test_cipher=True)
st4 = S.StoreState(); s4.save(st4); open(s4.path, "w").write("{bad"); s4.load(); s4.save(st4)
doc = json.load(open(s4.path, encoding="utf-8")); doc["schema_version"] = 0; json.dump(doc, open(s4.path, "w", encoding="utf-8"))
S.Store(s4.path, S.TestOnlyCipher(b"k"), {0: lambda x: {**x, "schema_version": 1}}, allow_test_cipher=True).load()
names = sorted(os.listdir(d4)); T(len(names) >= 3 and s4.owned_names()[1] == names, f"everything the module creates is owned: {names}")
dd, sk = s4.delete_all(); T(sorted(dd) == names and sk == [] and os.listdir(d4) == [], "and delete_all removes all of it")
print(f"OK ({CHECKS} storage checks; test cipher only, no OS key store, files in a temporary directory)")
