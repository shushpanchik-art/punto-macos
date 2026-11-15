"""AP-3 layout pair selection and row 7, deterministic part. Key tables are synthesised from the reference tables (RT-15 (b) style variants); no operating
system is asked anything. The real installed-sources query and the fingerprint calls are NOT RUN."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lfpair as P, lfruntime as R, lfengine as L, lfstatus as ST

CHECKS = 0
def T(c, w):
    global CHECKS
    CHECKS += 1
    if not c: raise AssertionError(w)
EN, RU = L.table_entries("en"), L.table_entries("ru")
def variant(base, idx, ch): e = list(base); e[idx] = ch; return e
RU_MNEMONIC = variant(RU, 10, "ж")                   # a different Russian table (one key moved), like RT-15 (b)
RU_TYPEW = variant(RU, 8, "$")
EN_INTL = variant(EN, 0, "\x00")                     # a dead key reads as \x00 (RT-15 (c))
def src(i, e): return P.Source(i, e)

T(P.classify(src("us", EN)) == "en" and P.classify(src("ru", RU)) == "ru", "the supported tables are identified by fingerprint")
for name, e in (("mnemonic", RU_MNEMONIC), ("typewriter", RU_TYPEW), ("international", EN_INTL), ("not a layout", None), ("too short", EN[:93]), ("too long", EN + ["x"]), ("not a list", "abc"), ("line feed", variant(EN, 3, "a\nb")), ("ints", [1] * 94), ("tuple of ints", tuple(range(94))), ("empty", []), ("an int", 5), ("a dict", {i: "a" for i in range(94)})):
    T(P.classify(src("x", e)) is None, f"not supported: {name}")
T(P.classify(src("t", tuple(EN))) == "en", "a tuple of entries is read the same way")
# ---- exactly one of each: the pair
r = P.select_pair([src("us", EN), src("ru", RU)])
T((r.state, r.en, r.ru, r.origin) == (P.PAIR, "us", "ru", "single") and r.layout_of("us") == "en" and r.layout_of("ru") == "ru" and r.layout_of("other") is None, "one English and one Russian: that pair")
r = P.select_pair([src("ru", RU), src("us", EN)]); T(r.state == P.PAIR and r.en == "us", "the order of the list does not matter")
# unsupported variants installed besides: still the pair; the variants are listed and are not members
r = P.select_pair([src("us", EN), src("ru", RU), src("mn", RU_MNEMONIC), src("intl", EN_INTL), src("ime", None)])
T(r.state == P.PAIR and r.unsupported == ["mn", "intl", "ime"] and r.layout_of("mn") is None and r.layout_of("intl") is None and r.layout_of("ime") is None, "unsupported variants next to a supported pair: the pair is used, the variants are not members")
# no pair
for lst, name in (([src("us", EN)], "no Russian"), ([src("ru", RU)], "no English"), ([], "nothing"), ([src("mn", RU_MNEMONIC), src("us", EN)], "only an unsupported Russian"), ([src("ime", None), src("ime2", None)], "only non-layouts")):
    r = P.select_pair(lst); T(r.state == P.NONE and r.layout_of("us") is None, f"no pair: {name}")
# several supported: the user chooses
r = P.select_pair([src("us", EN), src("abc", EN), src("ru", RU)])
T(r.state == P.CHOOSE and r.candidates == {"en": ["us", "abc"], "ru": ["ru"]} and r.en is None and r.layout_of("us") is None, "two supported English sources (same fingerprint): the user chooses, nothing is active until then")
two = [src("us", EN), src("abc", EN), src("ru", RU), src("ru2", RU)]
T(P.select_pair(two).state == P.CHOOSE, "two of each: the user chooses")
r = P.select_pair(two, {"en": "abc", "ru": "ru2"}); T((r.state, r.en, r.ru, r.origin) == (P.PAIR, "abc", "ru2", "user") and r.layout_of("us") is None, "a valid choice makes the pair")
for bad in ({"en": "zz", "ru": "ru"}, {"en": "us"}, {"en": "us", "ru": "ru", "x": 1}, {"en": "ru", "ru": "us"}, {"en": "mn", "ru": "ru"}, "us", None, 5, {"en": None, "ru": None}, {"en": ["us"], "ru": "ru"}):
    T(P.select_pair(two, bad).state == P.CHOOSE, f"an invalid or stale choice is ignored: {bad!r}")
r = P.select_pair([src("us", EN), src("ru", RU)], {"en": "us", "ru": "ru"}); T(r.origin == "single", "a choice with nothing to choose from changes nothing")
r = P.select_pair([src("us", EN), src("ru", RU)], {"en": "gone", "ru": "ru"}); T(r.state == P.PAIR and r.origin == "single", "a stale choice does not break the single pair")
# a bad list is NONE
for lst, name in (("x", "not a list"), (None, "None"), ([src("a", EN)] * 2, "repeated id"), ([src("", EN), src("ru", RU)], "empty id"), ([src("a\nb", EN), src("ru", RU)], "control character in id"), ([src("x" * 257, EN), src("ru", RU)], "long id"), ([src(5, EN), src("ru", RU)], "id not a string"), (["us", "ru"], "not Source objects"), ([src(str(i), EN) for i in range(65)], "too many")):
    T(P.select_pair(lst).state == P.NONE, f"a malformed list gives no pair: {name}")
T(P.select_pair([src(str(i), None) for i in range(62)] + [src("us", EN), src("ru", RU)]).state == P.PAIR, "64 sources are accepted in size")
T(P.select_pair([src(str(i), None) for i in range(63)] + [src("us", EN), src("ru", RU)]).state == P.NONE, "65 are not")
T("ghbdtn" not in repr(P.select_pair([src("us", EN)]).__dict__) and repr(src("us", EN)) == "Source('us')", "entries do not appear in a representation")

# ---- the runtime: row 7
M1 = {L.READ_RANGE, L.REPLACE_RANGE, L.READBACK, L.ROLLBACK}
def rt_new():
    rt = R.Runtime(L.Engine(L.example_cal(), lambda ids: [-3, 9, -2], {"en": {"hello"}, "ru": {"привет"}}), L.HookHealth(canary=False))
    f = L.SimField("", M1); rt.on_focus("A", f, "AUTO"); rt.on_gate(L.GATE_ALLOW); return rt, f
pair = P.select_pair([src("us", EN), src("ru", RU), src("mn", RU_MNEMONIC)])
rt, f = rt_new()
T(P.apply_active(rt, pair, "us") == "en" and ST.status(rt) == ("Active", []), "a member is active: the tool works")
T(P.apply_active(rt, pair, "mn") is None and ST.status(rt) == ("Off", ["layout"]) and rt.engine.mode == "OFF", "the unsupported variant becomes active: OFF with the reason layout (the icon says 'layout not supported')")
T(P.apply_active(rt, pair, "ru") == "ru" and ST.status(rt)[0] == "Active", "a supported layout is active again: back")
T(P.apply_active(rt, pair, "unknown-source") is None and rt.explain("A") == ("OFF", ["layout"]), "a source that is not in the list: OFF")
choose = P.select_pair([src("us", EN), src("abc", EN), src("ru", RU)])
T(P.apply_active(rt, choose, "us") is None and rt.engine.mode == "OFF", "the pair is not chosen yet: OFF whatever is active")
none = P.select_pair([src("us", EN)]); T(P.apply_active(rt, none, "us") is None and rt.engine.mode == "OFF", "no pair: OFF")
T(P.apply_active(rt, "not a result", "us") is None and rt.layout_ok is False, "a missing result is OFF, never a guess")
# a word typed while OFF for the layout is not converted
rt, f = rt_new(); P.apply_active(rt, pair, "mn")
for i, (ch, k) in enumerate(zip("ghbdtn", L.keys_from_text("ghbdtn", "en"))):
    f.type_user(ch); rt.on_hook_event(L.Event("key", k, "en", 100 + i), sig=("k", 100 + i))
f.type_user(" "); rt.on_hook_event(L.Event("space", None, "en", 106))
T(f.text == "ghbdtn ", "while the unsupported variant is active nothing is converted")
# re-identification: a table that changes is a different layout
src_live = src("us", list(EN)); pr = P.select_pair([src_live, src("ru", RU)]); T(pr.state == P.PAIR, "setup")
src_live.entries = variant(EN, 5, "q"); T(P.select_pair([src_live, src("ru", RU)]).state == P.NONE, "the same source with a changed table is no longer supported when identified again")
print(f"OK ({CHECKS} layout pair checks; synthetic tables; no operating-system call)")
