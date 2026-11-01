"""conformance.py - property, negative and fault-injection tests of section 20.13 (standard library only).
Usage:  python conformance.py [N]      N = number of fuzz events (default 200000; the audit runs 1000000)
Run it in the folder that holds lfengine.py. It prints OK, or raises AssertionError. It also works under
`python -O`, because it never uses the assert statement (asserts disappear when optimised)."""
import sys, random, math, itertools, copy, json; sys.path.insert(0, ".")
import lfengine as L

N = int(sys.argv[1]) if len(sys.argv) > 1 else 200_000
R = random.Random(1)
CHECKS = 0


def T(cond, what=""):
    """The one check function: a failed condition always raises, with or without -O."""
    global CHECKS
    CHECKS += 1
    if not cond:
        raise AssertionError(what or "check failed")


def raises(exc, fn, what):
    global CHECKS
    CHECKS += 1
    try:
        fn()
    except exc:
        return
    except Exception as e:                                # a wrong exception type is also a failure
        raise AssertionError(f"{what}: raised {type(e).__name__}, expected {exc.__name__}")
    raise AssertionError(f"{what}: nothing was raised")


# ---- P1 tokens, rendering, candidate -------------------------------------------------------------------
for _ in range(N):
    run = [L.Key(R.randrange(47), R.random() < .5, R.random() < .3) for _ in range(R.randrange(1, 12))]
    T(all(1 <= L.token(k) <= 94 for k in run), "token range")
    for lay in ("en", "ru"):
        txt = L.render(run, lay)
        T(L.render([L.Key(k.id, L.effective_shift(k, lay)) for k in run], lay) == txt, "effective shift")
        T(L.render(L.keys_from_text(txt, lay), lay) == txt, "round trip")
    for tgt in ("en", "ru"):
        c = L.candidate(run, tgt)
        if c:
            T(c.lead + c.core + c.trail == tuple(run), "a key was lost or duplicated by segmentation")
            T(len(c.lead) <= 1 and len(c.trail) <= 2 and len(c.core) >= 1, "peel limits")
            T(all(L.is_letter_in(tgt, k.id) for k in c.core), "the core is letters only")

# ---- P2 every prior is a probability vector ------------------------------------------------------------
for a in ("en", "ru"):
    for st in L.STATES:
        cal = L.example_cal()
        T(abs(sum(L.deployment_prior(a, cal["w"][a][st], cal["o_lat"])) - 1) < 1e-12, "prior sums to 1")

# ---- P3 calibration package: every mutation is refused with CalibrationError, and the engine does not start ----
ok_cal = L.example_cal()
L.check_calibration_package(ok_cal)
T(L.pi_from_counts(ok_cal["pi_train_counts"]) == ok_cal["pi_train"], "pi_train is derived from the counts")


def mutated(path, value):
    c = copy.deepcopy(ok_cal)
    cur = c
    for p in path[:-1]:
        cur = cur[p]
    if value is DELETE:
        del cur[path[-1]]
    else:
        cur[path[-1]] = value
    return c


DELETE = object()
nan, inf = float("nan"), float("inf")
BAD = {
    "unit mix-up (a probability stored as nats)": (["lambda_nats", "network", "en2ru", "5-7"], 0.997),
    "network table missing": (["lambda_nats", "network"], DELETE),
    "ngram table missing": (["lambda_nats", "ngram"], DELETE),
    "direction missing": (["lambda_nats", "network", "ru2en"], DELETE),
    "bucket missing": (["lambda_nats", "ngram", "en2ru", "8+"], DELETE),
    "bucket is a string": (["lambda_nats", "network", "en2ru", "3-4"], "6.9"),
    "bucket is NaN": (["lambda_nats", "network", "en2ru", "3-4"], nan),
    "bucket is +Inf": (["lambda_nats", "network", "en2ru", "3-4"], inf),
    "bucket is a bool": (["lambda_nats", "network", "en2ru", "3-4"], True),
    "table is a list": (["lambda_nats", "network", "en2ru"], [6.9, 5.8, 5.3]),
    "T is NaN": (["temperature", "network"], nan),
    "T is +Inf": (["temperature", "network"], inf),
    "T is -Inf": (["temperature", "ngram"], -inf),
    "T is zero": (["temperature", "network"], 0.0),
    "T is negative": (["temperature", "ngram"], -1.0),
    "T is too large": (["temperature", "network"], 99.0),
    "T of one scorer missing": (["temperature", "ngram"], DELETE),
    "T is a per-class list": (["temperature", "network"], [1.0, 1.0, 1.0]),
    "pi_train too short": (["pi_train"], [0.5, 0.5]),
    "pi_train has a zero": (["pi_train"], [0.5, 0.5, 0.0]),
    "pi_train has a negative": (["pi_train"], [0.6, 0.5, -0.1]),
    "pi_train is not normalised": (["pi_train"], [0.39, 0.40, 0.22]),
    "pi_train differs from its counts": (["pi_train"], [0.40, 0.38, 0.22]),
    "counts have a zero": (["pi_train_counts"], [38000, 40000, 0]),
    "counts are floats": (["pi_train_counts"], [38000.0, 40000.0, 22000.0]),
    "counts too short": (["pi_train_counts"], [38000, 40000]),
    "o_lat is 1": (["o_lat"], 1.0),
    "o_lat is NaN": (["o_lat"], nan),
    "w[en] missing a state": (["w", "en", "run"], DELETE),
    "w is zero": (["w", "ru", "default"], 0.0),
    "w[run] above its cap": (["w", "en", "run"], 0.4),
    "two-key list missing": (["two_key_allow", "ru2en"], DELETE),
    "two-key list empty": (["two_key_allow", "en2ru"], set()),
    "two-key word of three letters": (["two_key_allow", "en2ru"], {"на", "она"}),
    "two-key word of one letter": (["two_key_allow", "en2ru"], {"на", "н"}),
    "two-key word not case-folded": (["two_key_allow", "en2ru"], {"На"}),
    "two-key word with a space": (["two_key_allow", "en2ru"], {"н "}),
    "two-key list is a list, not a set": (["two_key_allow", "en2ru"], ["на"]),
    "two-key list is a string": (["two_key_allow", "en2ru"], "на не"),
    "wrong schema": (["schema"], "LFC0"),
    "unknown field": (["extra"], 1),
    "field missing": (["o_lat"], DELETE),
}
for what, (path, value) in BAD.items():
    bad = mutated(path, value)
    raises(L.CalibrationError, lambda b=bad: L.check_calibration_package(b), what)
    raises(L.CalibrationError, lambda b=bad: L.Engine(b, lambda ids: [0, 0, 0]), "engine must not start: " + what)
raises(L.CalibrationError, lambda: L.check_calibration_package(None), "package is None")
raises(L.CalibrationError, lambda: L.check_calibration_package([]), "package is a list")
raises(L.CalibrationError, lambda: L.Engine(ok_cal, lambda ids: [0, 0, 0], kind="forest"), "unknown scorer kind")
good_json = L.cal_to_json(ok_cal)
T(L.cal_to_json(L.cal_from_json(good_json)) == good_json, "JSON round trip")
for what, text in {
    "NaN": good_json.replace('"network": 1.0', '"network": NaN', 1),
    "Infinity": good_json.replace('"network": 1.0', '"network": Infinity', 1),
    "duplicate key": good_json.replace('"o_lat"', '"o_lat": 0.25, "o_lat"', 1),
    "not JSON": "{",
    "not an object": "[1]",
    "allow list of numbers": good_json.replace('"на"', "5", 1),
    "allow list is a string": json.dumps({**json.loads(good_json), "two_key_allow": {**json.loads(good_json)["two_key_allow"], "en2ru": "на не но"}}, ensure_ascii=False),
    "allow list is null": json.dumps({**json.loads(good_json), "two_key_allow": {**json.loads(good_json)["two_key_allow"], "en2ru": None}}, ensure_ascii=False),
    "allow list has a duplicate": json.dumps({**json.loads(good_json), "two_key_allow": {**json.loads(good_json)["two_key_allow"], "en2ru": ["на", "на"]}}, ensure_ascii=False),
    "allow list of one-letter words": json.dumps({**json.loads(good_json), "two_key_allow": {**json.loads(good_json)["two_key_allow"], "en2ru": ["н", "а"]}}, ensure_ascii=False),
    "allow list is empty": json.dumps({**json.loads(good_json), "two_key_allow": {**json.loads(good_json)["two_key_allow"], "en2ru": []}}, ensure_ascii=False),
}.items():
    raises(L.CalibrationError, lambda t=text: L.cal_from_json(t), "JSON: " + what)
# the runtime reaction: a refused package gives a defined mode, never a half-activated engine
T(L.engine_mode({L.READ_RANGE, L.REPLACE_RANGE, L.READBACK, L.ROLLBACK}, "AUTO", models_ok=False) == "MANUAL_ONLY",
  "refused package: MANUAL_ONLY")

# ---- P4 LFB1 round trip equals the in-memory model -----------------------------------------------------
cal = L.example_cal()
rows = [[L.BOS] + [L.token(L.Key(R.randrange(47), R.random() < .3)) for _ in range(R.randrange(2, 9))] + [L.EOS]
        for _ in range(300)]
ms = [L.WittenBell().fit(rows[i::3]) for i in range(3)]
pkg = L.lfb_load(L.lfb_pack(ms, [math.log(x) for x in cal["pi_train"]]))
T(max(abs(L.lfb_logp(pkg, c, r) - ms[c].logp(r)) for c in range(3) for r in rows[:100]) < 1e-12, "LFB1 round trip")

# ---- P5 LFW1: size is header + 4 bytes per parameter; three finite logits -------------------------------
tw = L.toy_weights()
T(len(tw) == 16 + 4 * 3 + 4 * L.lfw_size(4, 4, (3, 5, 3)), "LFW1 size")
out = L.lfw_forward(L.lfw_load(tw), L.tokens(L.keys_from_text("ghbdtn", "en")))
T(len(out) == 3 and all(math.isfinite(v) for v in out), "LFW1 forward")

# ---- P6 Caps Lock: the token formula, key by key ---------------------------------------------------------
RU_ONLY = (0, 23, 24, 35, 36, 44, 45)                       # ` [ ] ; ' , .  (letters only in Russian)
T(sorted(set(L.LETTER_KEYS) - {k for k in range(47) if L.TABLE["en"][0][k].isalpha()}) == sorted(RU_ONLY), "L")
for kid in range(47):
    for sh, cp in itertools.product((False, True), repeat=2):
        k = L.Key(kid, sh, cp)
        expect = 1 + 2 * kid + int(sh ^ (cp and kid in L.LETTER_KEYS))
        T(L.token(k) == expect, f"token formula key {kid} shift {sh} caps {cp}")
        if L.TABLE["en"][0][kid].isalpha():                  # Latin letters: the token equals the shift of BOTH layouts
            T(bool((L.token(k) - 1) & 1) == L.effective_shift(k, "en") == L.effective_shift(k, "ru"), "latin letter")
        if kid in RU_ONLY:                                   # seven keys: the token carries the flip, English rendering does not
            T(bool((L.token(k) - 1) & 1) == L.effective_shift(k, "ru"), "ru-only letter follows the Russian layout")
            T(L.render_key(k, "en") == L.TABLE["en"][int(sh)][kid], "Caps Lock does not change the English character")
        if kid not in L.LETTER_KEYS:                         # digits, - = \ / : Caps Lock never reaches the token
            T(L.token(k) == 1 + 2 * kid + int(sh), "non-letter key")

# ---- P7 engine_mode: the whole truth table, plus the invariants that matter -------------------------------
CAPS = sorted(L.CAPABILITIES)
for r in range(len(CAPS) + 1):
    for caps in itertools.combinations(CAPS, r):
        for support in L.SUPPORT_STATUS:
            for flags in itertools.product((True, False), repeat=6):
                kw = dict(zip(("models_ok", "layout_ok", "permission_ok", "hook_ok", "watchdog_ok", "quarantined"), flags))
                m = L.engine_mode(caps, support, **kw)
                fs = frozenset(caps)
                if m == "AUTO":
                    T(L.AUTO_REQUIRES <= fs and support == "AUTO" and kw["models_ok"] and kw["hook_ok"]
                      and kw["watchdog_ok"] and kw["layout_ok"] and kw["permission_ok"] and not kw["quarantined"],
                      f"AUTO granted wrongly: {caps} {support} {kw}")
                if L.SYNTHETIC_INPUT in fs and not L.AUTO_REQUIRES <= fs:
                    T(m != "AUTO", "synthetic input without rollback must never be AUTO")
                if support == "UNKNOWN" or kw["quarantined"] or not kw["permission_ok"] or not kw["layout_ok"]:
                    T(m == "OFF", "unknown, quarantined, no permission or unsupported layout is OFF")
                if m != "OFF" and not kw["hook_ok"]:
                    T(m == "MANUAL_ONLY", "a lost hook can never leave AUTO active")
raises(ValueError, lambda: L.engine_mode({"TELEPATHY"}, "AUTO"), "unknown capability")
raises(ValueError, lambda: L.engine_mode(set(), "MAYBE"), "unknown status")
M1 = {L.READ_RANGE, L.REPLACE_RANGE, L.READBACK, L.ROLLBACK}
M1_NOROLL = {L.READ_RANGE, L.REPLACE_RANGE, L.READBACK}
M2 = {L.READ_RANGE, L.READBACK, L.SYNTHETIC_INPUT}
T(L.engine_mode(M1, "AUTO") == "AUTO" and L.engine_mode(M1_NOROLL, "AUTO") == "MANUAL_ONLY"
  and L.engine_mode(M2, "AUTO") == "MANUAL_ONLY" and L.engine_mode(M2, "MANUAL") == "MANUAL_ONLY"
  and L.engine_mode(M1, "MANUAL") == "MANUAL_ONLY" and L.engine_mode(M1, "UNKNOWN") == "OFF"
  and L.engine_mode({L.READ_RANGE}, "AUTO") == "OFF", "mode examples")

# ---- P8 outcome classification --------------------------------------------------------------------------
T(L.classify_outcome(False, "a", "b", None, False) == "ABORTED", "not started")
T(L.classify_outcome(True, "a", "b", "b", True) == "VERIFIED", "verified")
T(L.classify_outcome(True, "a", "b", "b", False) == "UNRECOVERED", "new text without a passed verification is not VERIFIED")
T(L.classify_outcome(True, "a", "b", "a", False) == "RESTORED", "restored")
T(L.classify_outcome(True, "a", "b", "c", False) == "UNRECOVERED", "other text")
T(L.classify_outcome(True, "a", "b", None, False) == "UNRECOVERED", "unreadable range")

# ---- P9 the replacement transaction against injected faults (the matrix of 13.2) ------------------------------
import os, vectors
V = vectors.build()                                                   # fails by itself when a hand-written prediction is wrong
if os.path.exists("vectors_out.json"):
    with open("vectors_out.json", encoding="utf-8") as fh:
        T(json.load(fh) == json.loads(vectors.render(V)), "vectors_out.json is not what vectors.py generates")
BASE, OLD, NEW = "Hello ghbdtn ", "ghbdtn", "привет"
T(len(V["tx"]) == 45, "fault matrix size")
for name, caps, text, faults, ahead, kw, outcome, reason, final, incident in V["tx"]:
    f = L.SimField(text, caps, {(k.split(":")[0], int(k.split(":")[1])): v for k, v in faults.items()})
    res = L.run_transaction(f, OLD, NEW, ahead, **kw)
    T((res.outcome, res.reason, f.text, res.incident, res.quarantine) == (outcome, reason, final, incident, incident), name)
    T(res.outcome in L.OUTCOMES, "outcome vocabulary")
    # invariants of every row (the safety matrix of 13.2):
    T(res.outcome != "VERIFIED" or f.text[6:12] == NEW, f"{name}: VERIFIED text")
    T(res.outcome != "RESTORED" or f.text[6:12] == OLD, f"{name}: RESTORED text")
    T(res.outcome != "ABORTED" or f.text.replace("x", "") == text.replace("x", ""), f"{name}: ABORTED must not change the field")
    T(res.incident == (res.outcome in ("RESTORED", "UNRECOVERED")), f"{name}: an incident only after the write began")
    T(f.user == [c for c in f.user if c == "x"], f"{name}: only the scripted user keys")
    if res.method == "M2" and res.outcome == "UNRECOVERED":          # the event-level guarantee holds, the field one does not
        T(f.sent == (14 if reason == "verify_failed" else 4) and f.user == ["x"] * len(f.user),
          f"{name}: G-EVENT: synthetic events are exactly those of the plan, user keys exactly once")

# Every fault of one phase, applied to every step, never ends in a silent VERIFIED with wrong text, and never
# crashes (an exhaustive sweep over single faults and pairs of faults, M1 with rollback).
FAULT_SLOTS = [("gate", 1, ["DENY", "raise"]), ("caret", 1, ["raise", "back", "forward"]), ("caret", 2, ["raise", "back", "forward"]),
               ("read", 1, ["none", "stale", "raise", "user:x"]), ("read", 2, ["none", "stale", "raise", "user:x"]),
               ("read", 3, ["none", "stale", "raise"]),
               ("replace", 1, ["raise", "partial", "applied_error", "autocorrect", "ignored", "spill", "user:x"]),
               ("replace", 2, ["raise", "partial", "applied_error", "autocorrect", "ignored", "spill", "user:x"])]
sweep = 0
for combo in itertools.chain(([s] for s in FAULT_SLOTS), itertools.combinations(FAULT_SLOTS, 2)):
    for picks in itertools.product(*[[(op, k, v) for v in vs] for op, k, vs in combo]):
        faults = {(op, k): v for op, k, v in picks}
        f = L.SimField(BASE, M1, faults)
        res = L.run_transaction(f, OLD, NEW)
        sweep += 1
        body = f.text.replace("x", "")
        T(res.outcome in L.OUTCOMES, "vocabulary")
        T(res.outcome != "VERIFIED" or body == "Hello привет ", f"sweep VERIFIED with wrong text {faults}")
        T(res.outcome != "RESTORED" or body == BASE, f"sweep RESTORED with wrong text {faults}")
        T(res.outcome != "ABORTED" or body == BASE, f"sweep ABORTED changed the field {faults}")
        T(res.outcome != "UNRECOVERED" or (res.incident and res.quarantine), f"sweep UNRECOVERED without incident {faults}")
        T(f.user == ["x"] * len(f.user), "user keys are exactly the scripted ones")
        T(body.count("привет") + body.count("ghbdtn") <= 1 or res.outcome == "UNRECOVERED", f"sweep duplicated text {faults}")
M1_SWEEP = sweep

# The same sweep for M2 (the hotkey path): events 1 to 14 are the plan (7 Backspace, 6 characters, the Space).
# Invariants: a user key seen before the first event means nothing is sent; whatever is written, the user's own
# keys are never lost or duplicated by the plan (G-EVENT) and a wrong text is never VERIFIED.
M2_SLOTS = [("gate", 1, ["DENY", "raise"]), ("caret", 1, ["raise", "back", "forward"]), ("caret", 2, ["raise", "back", "forward"]),
            ("read", 1, ["none", "stale", "raise", "user:x"]), ("read", 2, ["none", "stale", "raise", "user:x"]),
            ("read", 3, ["none", "stale", "raise"])] + [("event", k, ["raise", "user:x", "drop"]) for k in range(1, 15)]
for combo in itertools.chain(([s] for s in M2_SLOTS), itertools.combinations(M2_SLOTS[:6] + M2_SLOTS[6:9] + M2_SLOTS[-3:], 2)):
    for picks in itertools.product(*[[(op, k, v) for v in vs] for op, k, vs in combo]):
        faults = {(op, k): v for op, k, v in picks}
        f = L.SimField(BASE, M2, faults)
        res = L.run_transaction(f, OLD, NEW, "", mode="MANUAL_ONLY")
        sweep += 1
        body = f.text.replace("x", "")
        T(res.outcome in L.OUTCOMES, "M2 vocabulary")
        T(res.outcome != "VERIFIED" or body == "Hello привет ", f"M2 sweep VERIFIED with wrong text {faults}")
        T(res.outcome != "ABORTED" or (f.sent == 0 and body == BASE), f"M2 sweep ABORTED wrote something {faults}")
        T(res.outcome != "UNRECOVERED" or (res.incident and res.quarantine), f"M2 sweep UNRECOVERED without incident {faults}")
        T(f.sent in (0, 14) or any(k == "event" for (k, _) in faults) or res.outcome == "UNRECOVERED", f"M2 sweep partial plan {faults}")
        T(f.user == ["x"] * len(f.user), "M2 user keys are exactly the scripted ones")
        if faults.get(("read", 1)) == "user:x":                  # the key came before the first event: nothing may be sent
            T(f.sent == 0 and res.outcome == "ABORTED", f"M2 sweep: key before the write {faults}")
T((M1_SWEEP, sweep) == (497, 1184), f"sweep size {M1_SWEEP} / {sweep}")

# ---- P10 engine: undo snapshot lifecycle, modes, outcomes, stream gap ---------------------------------------
scorer = lambda ids: [-3, 9, -2]
LEX = {"en": {"hello"}, "ru": {"привет"}}


def feed(e, text, lay, t0, then_space=True):
    d = None
    for i, k in enumerate(L.keys_from_text(text, lay)):
        e.on_event(L.Event("key", k, lay, t0 + i))
    if then_space:
        d = e.on_event(L.Event("space", None, lay, t0 + len(text)))
    return d


e = L.Engine(L.example_cal(), scorer, LEX)
d = feed(e, "ghbdtn", "en", 1000)
T(d.action == "CONVERT" and e.snapshot is not None, "convert makes one snapshot")
T(e.snapshot.layout == "en" and e.snapshot.direction == "en2ru" and e.snapshot.typed == "ghbdtn", "snapshot content")
T(e.undo(2000) == "ghbdtn", "undo returns the typed text")
T(("en2ru", "ghbdtn") in e.exceptions and e.credit == 0 and e.cool_words == 3 and e.snapshot is None,
  "undo: exception, credit, cool-down, snapshot destroyed")
T(e.undo(2100) is None, "a second undo does nothing")
d = feed(e, "ghbdtn", "en", 3000)
T(d.action == "KEEP" and d.reason == "cooldown", "cool-down suppresses the correction")
# caps lock keys are restored exactly
e = L.Engine(L.example_cal(), scorer, LEX)
for i, k in enumerate(L.keys_from_text("ghbdtn", "en")):
    e.on_event(L.Event("key", L.Key(k.id, False, True), "en", i))
d = e.on_event(L.Event("space", None, "en", 10))
T(d.action == "CONVERT" and e.undo(20) == "GHBDTN", "undo with Caps Lock restores the typed capitals")
# russian to english
e = L.Engine(L.example_cal(), lambda ids: [9, -3, -2], LEX)
d = feed(e, "руддщ", "ru", 0)
T(d.action == "CONVERT" and d.replacement == "hello" and e.undo(5) == "руддщ", "ru2en undo")
# expiry: 10 s and 100 characters
for dt, alive in ((10_000, True), (10_001, False)):
    e = L.Engine(L.example_cal(), scorer, LEX); feed(e, "ghbdtn", "en", 1000)
    e.tick(1006 + dt)
    T((e.snapshot is not None) == alive, f"expiry at {dt} ms")
for n_after, alive in ((100, True), (101, False)):
    e = L.Engine(L.example_cal(), scorer, LEX); feed(e, "ghbdtn", "en", 1000)
    for i in range(n_after):
        e.on_event(L.Event("key", L.Key(i % 47), "en", 1010 + i))
    T((e.snapshot is not None) == alive, f"{n_after} characters after the replacement")
# everything that must destroy it
for what, act in {
    "break": lambda e: e.on_event(L.Event("break")),
    "layout change": lambda e: e.on_event(L.Event("layout", None, "ru")),
    "gap": lambda e: e.on_event(L.Event("gap")),
    "gate DENY": lambda e: e.set_gate("DENY"),
    "gate UNKNOWN": lambda e: e.set_gate("UNKNOWN"),
    "mode MANUAL_ONLY": lambda e: e.set_mode("MANUAL_ONLY"),
    "mode OFF": lambda e: e.set_mode("OFF"),
    "backspace before the word": lambda e: e.on_event(L.Event("backspace")),
    "outcome RESTORED": lambda e: e.on_outcome("RESTORED"),
    "outcome UNRECOVERED": lambda e: e.on_outcome("UNRECOVERED"),
    "outcome ABORTED": lambda e: e.on_outcome("ABORTED"),
}.items():
    e = L.Engine(L.example_cal(), scorer, LEX); feed(e, "ghbdtn", "en", 1000)
    T(e.snapshot is not None, "setup " + what)
    act(e)
    T(e.snapshot is None and e.undo(1100) is None, "the snapshot must not survive: " + what)
e = L.Engine(L.example_cal(), scorer, LEX); feed(e, "ghbdtn", "en", 1000)
e.on_outcome("VERIFIED")
T(e.snapshot is not None and e.credit == 3, "a verified replacement keeps snapshot and credit")
e.on_event(L.Event("space", None, "en", 1500))                       # an empty run: nothing happens, the snapshot lives on
T(e.snapshot is not None, "a Space with no word keeps the snapshot")
feed(e, "ytdtyj", "en", 1600)                                         # a second conversion replaces the first snapshot
T(e.snapshot is None or e.snapshot.typed != "ghbdtn", "one snapshot only")
raises(ValueError, lambda: e.on_outcome("MAYBE"), "outcome vocabulary")
# modes
e = L.Engine(L.example_cal(), scorer, LEX); e.set_mode("MANUAL_ONLY")
T(feed(e, "ghbdtn", "en", 0) is None and e.snapshot is None, "MANUAL_ONLY never decides")
e.set_mode("OFF"); e.on_event(L.Event("key", L.Key(5), "en", 0))
T(e.run == [], "OFF records nothing")
e.set_mode("AUTO")
T(feed(e, "ghbdtn", "en", 0).action == "CONVERT", "AUTO decides again")
# a gap drops the interrupted word, whatever follows
e = L.Engine(L.example_cal(), scorer, LEX)
for k in L.keys_from_text("ghb", "en"):
    e.on_event(L.Event("key", k, "en", 0))
e.on_event(L.Event("gap"))
for k in L.keys_from_text("dtn", "en"):
    e.on_event(L.Event("key", k, "en", 1))
T(e.on_event(L.Event("space", None, "en", 2)) is None, "the tail of an interrupted word is ignored")
T(feed(e, "ghbdtn", "en", 10).action == "CONVERT", "the next word is decided normally")
# scorer fails closed
for bad in ([nan, 0, 0], [inf, 0, 0], [1, 2], "abc", [None, 1, 2]):
    e = L.Engine(L.example_cal(), lambda ids, b=bad: b, LEX)
    dd = feed(e, "ghbdtn", "en", 0)
    T(dd.action == "KEEP" and dd.reason == "scorer_invalid", f"scorer output {bad!r} fails closed")

# ---- P11 layout identity ---------------------------------------------------------------------------------
en_e, ru_e = L.table_entries("en"), L.table_entries("ru")
T(L.identify_layout(en_e) == "en" and L.identify_layout(ru_e) == "ru", "supported layouts are recognised")
T(len(set(L.SUPPORTED_FINGERPRINTS)) == 2, "two distinct fingerprints")
for lay, ent in (("en", en_e), ("ru", ru_e)):
    for i in range(94):                                               # any single wrong entry means: not supported
        alt = list(ent); alt[i] = "\x00" if ent[i] != "\x00" else "a"
        T(L.identify_layout(alt) is None, f"{lay} entry {i} changed")
        alt[i] = ent[i] + "́"
        T(L.identify_layout(alt) is None, f"{lay} entry {i} gets a combining mark")
T(L.identify_layout(en_e[1:] + en_e[:1]) is None, "rotated table")
swap = list(ru_e); swap[2 * 0], swap[2 * 0 + 1] = swap[1], swap[0]
T(L.identify_layout(swap) is None, "shift states swapped")
# a Russian layout that differs from the supported one in the punctuation row (the typewriter style)
typew = list(ru_e); typew[2 * 4 + 1] = "$"
T(L.identify_layout(typew) is None, "another Russian variant is not supported")
raises(ValueError, lambda: L.layout_fingerprint(en_e[:-1]), "93 entries")
raises(ValueError, lambda: L.layout_fingerprint(en_e[:-1] + ["a\nb"]), "an entry with a line feed")
T(L.layout_fingerprint(en_e) == "7b35aa964f372005ccef6558a1049dce2a550d772939090e3dba51302c0f3078", "fingerprint en is stable")
T(L.layout_fingerprint(ru_e) == "3aced72548d6d46da951f06cdbed60aac96487c338ad7b805e95402eb37204de", "fingerprint ru is stable")

# ---- P12 hook health -------------------------------------------------------------------------------------
h = L.HookHealth(canary=True)
for t in (0, 100, 200):
    h.raw_key(t, ("a", t)); h.hook_key(t + 5, ("a", t))
T(h.check(250) and h.ok and not h.take_gap(), "healthy stream")
h.raw_key(1000, "x")                                                  # the hook does not see this key
T(h.check(1000 + L.HookHealth.CANARY_MS) and h.ok, "exactly at the limit is still healthy")
T(not h.check(1000 + L.HookHealth.CANARY_MS + 1) and h.take_gap() and not h.take_gap(), "canary loses the hook, one gap")
T(h.reason == "canary_missing", "a physical key the hook never reported")
T(L.engine_mode(M1, "AUTO", hook_ok=h.ok) == "MANUAL_ONLY", "a lost hook limits the mode")
for t in (2000, 2100, 2200, 2300):                                    # keys typed while the hook is still not installed again
    h.raw_key(t, t); h.check(t + 10)
T(not h.ok, "still lost")
h.reinstalled()
for i in range(L.HookHealth.REARM_PAIRS - 1):
    h.raw_key(3000 + i, i); h.hook_key(3000 + i, i)
T(not h.ok, "re-arm needs the full number of pairs")
h.raw_key(3100, 9); h.hook_key(3100, 9)
T(h.ok and h.reason is None, "re-armed after three matched pairs")
m = L.HookHealth(canary=False)                                        # macOS
T(m.ok, "mac healthy")
m.tap_disabled("timeout")
T(not m.ok and m.take_gap() and m.reason == "tap_timeout", "tapDisabledByTimeout")
m.reinstalled()
T(m.ok, "tap enabled again")
m.tap_disabled("user_input"); T(not m.ok and m.reason == "tap_user_input", "tapDisabledByUserInput")
m.reinstalled(); m.poll(False); T(not m.ok and m.reason == "poll", "poll finds the tap disabled")
raises(ValueError, lambda: m.tap_disabled("other"), "unknown reason")
e = L.Engine(L.example_cal(), scorer, LEX)                            # the runtime sends the gap to the engine
for k in L.keys_from_text("ghb", "en"):
    e.on_event(L.Event("key", k, "en", 0))
h2 = L.HookHealth(canary=False); h2.tap_disabled("timeout")
if h2.take_gap():
    e.on_event(L.Event("gap"))
T(e.run == [] and e.skip, "the runtime delivers the gap")

# ---- P13 fuzz: invariants of the event state machine --------------------------------------------------------
fz = random.Random(7)
LK = sorted(L.LETTER_KEYS)
conv = checked_undo = 0
for rnd in range(max(1, N // 20_000)):
    e = L.Engine(L.example_cal(), lambda ids: [fz.uniform(-4, 4), fz.uniform(0, 14), fz.uniform(-4, 4)], LEX)
    now = 0
    for step in range(20_000):
        now += fz.choice((1, 5, 50, 700, 4000))
        x = fz.random()
        evs = []
        if x < .45:                                                     # a whole word on one layout, usually ended by Space
            lay = fz.choice(("en", "ru"))
            evs = [L.Event("key", L.Key(fz.choice(LK), fz.random() < .2, fz.random() < .05), lay, now) for _ in range(fz.randrange(2, 9))]
            if fz.random() < .8:
                evs.append(L.Event("space", None, lay if fz.random() < .95 else L.OTHER_LAYOUT[lay], now))
        elif x < .55:
            evs = [L.Event("key", L.Key(fz.randrange(47), fz.random() < .3), fz.choice(("en", "ru")), now)]
        elif x < .65:
            evs = [L.Event("space", None, fz.choice(("en", "ru")), now)]
        elif x < .72:
            evs = [L.Event("backspace", None, None, now)]
        elif x < .78:
            evs = [L.Event(fz.choice(("break", "gap")), None, None, now)]
        elif x < .80:
            evs = [L.Event("layout", None, fz.choice(("en", "ru")), now)]
        elif x < .90:
            ops = [lambda: e.set_gate(fz.choice(("ALLOW", "ALLOW", "ALLOW", "ALLOW", "ALLOW", "DENY", "UNKNOWN"))),
                   lambda: e.set_mode(fz.choice(("AUTO", "AUTO", "AUTO", "AUTO", "AUTO", "MANUAL_ONLY", "OFF"))),
                   lambda: e.on_outcome(fz.choice(L.OUTCOMES)),
                   lambda: e.tick(now)]
            fz.choice(ops)()
        else:
            evs = [L.Event("space", None, "en", now)]
        for ev in evs:
            d = e.on_event(ev)
            if d is not None and d.action == "CONVERT":
                conv += 1
                T(e.gate == "ALLOW" and e.mode == "AUTO", "CONVERT outside AUTO or gate ALLOW")
                T(e.snapshot is not None and len(d.replacement) == len(e.snapshot.keys), "a key was lost or duplicated")
                T(len(e.snapshot.keys) <= L.MAX_BUF, "snapshot size")
            if ev.kind in ("break", "layout", "gap"):
                T(e.snapshot is None and e.run == [], f"{ev.kind} must leave no buffer and no snapshot")
        T(len(e.run) <= L.MAX_BUF, "buffer bound")
        T(e.gate == "ALLOW" or (e.run == [] and e.snapshot is None), "no state under DENY or UNKNOWN")
        T(e.mode != "OFF" or (e.run == [] and e.snapshot is None), "no state in OFF")
        s = e.snapshot
        if s is not None:
            T(s.after <= L.UNDO_MAX_CHARS, "snapshot character bound")
            if fz.random() < .3:
                e.tick(now)
                if e.snapshot is not None:
                    T(now - e.snapshot.created_ms <= L.UNDO_WINDOW_MS, "snapshot age bound after tick")
                    keys, lay = e.snapshot.keys, e.snapshot.layout
                    txt = e.undo(now)
                    T(txt == L.render(keys, lay) and e.snapshot is None,
                      "undo returns the recorded keys rendered with the recorded layout")
                    checked_undo += 1
T(conv > N // 4000 and checked_undo > N // 20000, f"fuzz coverage: {conv} conversions, {checked_undo} undos")

# ---- P14 boundaries, defaults and format errors: every threshold is tested on both sides of its edge ---------
# (written against the survivors of the mutation run, audit line L3: a constant that nothing pins is a defect)
T([L.bucket(n) for n in (0, 1, 2, 3, 4, 5, 7, 8, 20)] == [None, None, "2", "3-4", "3-4", "5-7", "5-7", "8+", "8+"], "bucket edges")


def accepts(path, value):
    try:
        L.check_calibration_package(mutated(path, value))
        return True
    except L.CalibrationError:
        return False


# closed and open bounds of every numeric field of the calibration package
T(accepts(["temperature", "network"], 20.0) and accepts(["temperature", "network"], 15.0) and accepts(["temperature", "ngram"], 1e-9),
  "T: 1e-9, 15 and 20 are valid")
T(not accepts(["temperature", "network"], 20.001) and not accepts(["temperature", "ngram"], 21.0), "T above 20 is refused")
T(accepts(["o_lat"], 0.6) and accepts(["o_lat"], 0.999999) and accepts(["o_lat"], 1e-9), "o_lat valid values")
T(not accepts(["o_lat"], 0.0) and not accepts(["o_lat"], 1.0) and not accepts(["o_lat"], -0.1), "o_lat 0 and 1 are refused")
T(not accepts(["o_lat"], 1.5) and not accepts(["o_lat"], 2.0), "o_lat above 1 is refused")


def accepts_counts(counts):
    c = copy.deepcopy(ok_cal)
    c["pi_train_counts"] = counts
    c["pi_train"] = L.pi_from_counts(counts)
    try:
        L.check_calibration_package(c)
        return True
    except L.CalibrationError:
        return False


T(accepts_counts([60000, 30000, 10000]) and accepts_counts([1, 1, 1]) and accepts_counts([98, 1, 1]),
  "a class share above one half is a valid training mix")
T(accepts(["w", "en", "default"], 0.0005) and not accepts(["w", "en", "default"], 0.0004), "w lower edge is closed")
T(accepts(["w", "ru", "after_switch"], 0.5) and not accepts(["w", "ru", "after_switch"], 0.51), "w upper edge is closed")
T(accepts(["w", "en", "run"], 0.3) and not accepts(["w", "en", "run"], 0.3000001), "w[run] cap is 0.3, inclusive")
T(accepts(["lambda_nats", "network", "en2ru", "3-4"], 4.0) and not accepts(["lambda_nats", "network", "en2ru", "3-4"], 3.99),
  "lambda lower edge 4 nats is closed")
T(accepts(["lambda_nats", "ngram", "ru2en", "8+"], 16.0) and accepts(["lambda_nats", "ngram", "ru2en", "8+"], 9.0)
  and not accepts(["lambda_nats", "ngram", "ru2en", "8+"], 16.01), "lambda upper edge 16 nats is closed")
raises(L.CalibrationError, lambda: L.check_calibration_package(mutated(["pi_train"], ok_cal["pi_train"] + [1e-12])), "pi_train too long")
p0, p1, p2 = ok_cal["pi_train"]
T(not accepts(["pi_train"], [p0 + 1.5e-9, p1 - 1.5e-9, p2]), "pi_train element 1.5e-9 off its count is refused")
T(accepts(["pi_train"], [p0 + 0.8e-9, p1 - 0.8e-9, p2]), "pi_train element 0.8e-9 off its count is accepted")
T(not accepts(["pi_train"], [p0 + 0.4e-9, p1 + 0.4e-9, p2 + 0.4e-9]), "pi_train sum 1.2e-9 off 1 is refused")
T(accepts(["pi_train"], [p0 + 0.3e-9, p1 + 0.3e-9, p2 + 0.3e-9]), "pi_train sum 0.9e-9 off 1 is accepted")

# defaults of decide(): the two-key rule is closed unless a run is active
KEYS2 = L.keys_from_text("yf", "en")                                   # 'на' on the Russian layout, in the allow list
cal0 = L.example_cal()
T(L.decide(KEYS2, "en", cal0, scorer).reason == "two_key_rule", "two keys without a run: kept")
T(L.decide(KEYS2, "en", cal0, scorer, run_active=True).reason == "two_key_allow_list", "two keys inside a run: converted")
# the scorer sees BOS ... EOS
seen = []
L.decide(L.keys_from_text("ghbdtn", "en"), "en", cal0, lambda ids: seen.append(list(ids)) or [-3, 9, -2])
T(seen and seen[0][0] == L.BOS and seen[0][-1] == L.EOS and len(seen[0]) == 8, "the scorer input is BOS, 6 key tokens, EOS")
# a margin of exactly zero converts (the rule is s >= lambda)
G = L.keys_from_text("ghbdtn", "en")
s_exact = L.score([-3, 9, -2], "en", cal0, cal0["w"]["en"]["default"], "network")
cal_edge = copy.deepcopy(cal0); cal_edge["lambda_nats"]["network"]["en2ru"]["5-7"] = s_exact
T(L.decide(G, "en", cal_edge, scorer).action == "CONVERT" and L.decide(G, "en", cal_edge, scorer).margin == 0.0, "margin 0 converts")
cal_edge["lambda_nats"]["network"]["en2ru"]["5-7"] = s_exact + 1e-9
T(L.decide(G, "en", cal_edge, scorer).action == "KEEP", "margin -1e-9 abstains")


def word(e, text, lay, ts):
    for k in L.keys_from_text(text, lay):
        e.on_event(L.Event("key", k, lay, ts))
    return e.on_event(L.Event("space", None, lay, ts))


# buffer bound: 64 keys are decided, the 65th makes the word an overflow
e = L.Engine(L.example_cal(), scorer, LEX)
for _ in range(64):
    e.on_event(L.Event("key", L.Key(11), "en", 0))
T(len(e.run) == 64 and not e.overflow and e.on_event(L.Event("space", None, "en", 1)).reason != "overflow", "64 keys")
for _ in range(65):
    e.on_event(L.Event("key", L.Key(11), "en", 2))
T(len(e.run) == 64 and e.overflow and e.on_event(L.Event("space", None, "en", 3)).reason == "overflow", "65 keys")
# the lexicon is used when it is given
e = L.Engine(L.example_cal(), scorer, LEX)
T(word(e, "hello", "en", 0).reason == "lexicon_active", "the lexicon of the engine is consulted")
# evidence for the active language ends the run credit
e = L.Engine(L.example_cal(), scorer, LEX)
T(word(e, "ghbdtn", "en", 0).action == "CONVERT" and e.credit == 3, "credit after a conversion")
T(word(e, "hello", "en", 10).reason == "lexicon_active" and e.credit == 0, "a word of the active language resets the credit")
# two keys: the allow list opens only while the run credit lives
e = L.Engine(L.example_cal(), scorer, LEX)
T(word(e, "yf", "en", 0).reason == "two_key_rule", "no credit: two keys are kept")
word(e, "ghbdtn", "en", 10)
T(word(e, "yf", "en", 20).reason == "two_key_allow_list", "credit: two keys are converted")
# cool-down: three words and 10 s, each edge
e = L.Engine(L.example_cal(), scorer, LEX)
T(word(e, "ghbdtn", "en", 1000).action == "CONVERT" and e.undo(2000) == "ghbdtn", "setup cool-down")
T([word(e, "ytdtyj", "en", 20_000 + 100 * i).reason for i in range(3)] == ["cooldown"] * 3, "three words are suppressed")
T(word(e, "ytdtyj", "en", 20_300).action == "CONVERT", "the fourth word is decided")
for ts, reason in ((11_999, "cooldown"), (12_000, "score_above_threshold")):
    e = L.Engine(L.example_cal(), scorer, LEX)
    word(e, "ghbdtn", "en", 1000); e.undo(2000); e.cool_words = 0
    T(word(e, "ytdtyj", "en", ts).reason == reason, f"cool-down time edge at {ts} ms")
# the clock of every event expires the snapshot
for dt, alive in ((10_000, True), (10_001, False)):
    e = L.Engine(L.example_cal(), scorer, LEX); word(e, "ghbdtn", "en", 1000)
    e.on_event(L.Event("key", L.Key(5), "en", 1000 + dt))
    T((e.snapshot is not None) == alive, f"snapshot age {dt} ms seen by an ordinary event")
# a layout change inside a word, and the tail that follows
e = L.Engine(L.example_cal(), scorer, LEX)
for k in L.keys_from_text("gh", "en"):
    e.on_event(L.Event("key", k, "en", 0))
e.on_event(L.Event("key", L.Key(3), "ru", 1))
T(e.run == [] and e.skip, "a layout change inside a word empties the buffer and skips the rest")
for k in L.keys_from_text("bdtn", "en"):
    e.on_event(L.Event("key", k, "en", 2))
T(e.run == [], "the tail of a dropped word is not recorded")
T(e.on_event(L.Event("space", None, "en", 3)) is None and not e.skip, "the Space ends the skipped word")
e.on_event(L.Event("layout", None, "ru"))
e.on_event(L.Event("key", L.Key(5), "en", 4)); e.on_event(L.Event("break"))
T(not e.skip and e.credit == 0, "a break clears the skip")
T(word(e, "ghbdtn", "en", 5) is not None, "the word after a break is decided (not skipped)")
# a manual layout change marks the next word, once
e = L.Engine(L.example_cal(), lambda ids: [9, -3, -2], LEX)
e.on_event(L.Event("layout", None, "ru"))
T(e.after_switch, "layout event arms after_switch")
d = word(e, "руддщ", "ru", 10)
ref = L.decide(L.keys_from_text("руддщ", "ru"), "ru", L.example_cal(), lambda ids: [9, -3, -2], "after_switch", False, e.exceptions, LEX)
dflt = L.decide(L.keys_from_text("руддщ", "ru"), "ru", L.example_cal(), lambda ids: [9, -3, -2], "default", False, e.exceptions, LEX)
T(d.margin == ref.margin and ref.margin != dflt.margin and not e.after_switch, "after_switch is used once")
# manual conversion: direction rule
T(L.manual_convert("а")[0] == "ru2en" and L.manual_convert("я")[0] == "ru2en" and L.manual_convert("ё")[0] == "ru2en", "a, ya, yo")
T(L.manual_convert("яa")[0] == "en2ru", "a tie goes English to Russian")
T(L.manual_convert("яяabc")[0] == "en2ru" and L.manual_convert("яяабc")[0] == "ru2en", "letter counts decide")
T(L.manual_convert("12 !") == (None, "12 !"), "no letters: no direction")

# EV-1 edges (each condition is tested alone)
fc = lambda n: [("u%d" % i, "d%d" % i) for i in range(n)]
T(L.ev1_pass([], 100_000, 20, 100), "EV-1 passes at its minimum sizes")
T(not L.ev1_pass([], 99_999, 20, 100) and not L.ev1_pass([], 100_000, 19, 100) and not L.ev1_pass([], 100_000, 20, 99), "each size limit")
T(L.ev1_pass(fc(12), 250_000, 30, 200) and not L.ev1_pass(fc(13), 250_000, 30, 200), "point estimate edge 4.8e-5")
T(L.ev1_bound(fc(12), 250_000) <= 1e-4 < L.ev1_bound(fc(30), 250_000), "bound is monotone in the number of clusters")
big = [("u1", "d1")] * 10 + fc(1)[1:]                                   # one cluster of ten: the bound is ten times larger
T(L.ev1_bound(big, 1_000_000) == L.poisson_upper(1) * 10 / 1_000_000, "cluster size multiplies the bound")
for k in range(0, 31):                                                  # the exact Poisson limit, checked by its definition
    mu = L.poisson_upper(k)
    T(abs(sum(math.exp(-mu + i * math.log(mu) - math.lgamma(i + 1)) for i in range(k + 1)) - 0.05) < 1e-9, f"Poisson limit k={k}")
T(abs(L.poisson_upper(0) - (-math.log(0.05))) < 1e-9, "rule of three, exact")

# Witten-Bell pruning: only orders 1 and 2, only counts below min_count
rows_p = [[L.BOS, 5, 6, L.EOS]] * 2 + [[L.BOS, 7, 8, L.EOS]]
pr = L.WittenBell(min_count=2).fit(rows_p)
T(pr.cnt[0][()][5] == 2 and pr.cnt[0][()][7] == 1, "order 0 is never pruned")
T((L.BOS,) in pr.cnt[1] and pr.cnt[1][(L.BOS,)] == {5: 2}, "order 1: the count of exactly min_count stays, 1 is pruned")
T((L.BOS, 7) not in pr.cnt[2] and pr.cnt[2][(L.BOS, 5)] == {6: 2}, "order 2 pruned")
T(L.WittenBell().fit(rows_p).cnt[1][(L.BOS,)] == {5: 2, 7: 1}, "min_count 1 prunes nothing")

# binary files: round trips with distinct values, and every damage is a FormatError
lp = [-1.5, -2.25, -3.125]
msb = [L.WittenBell().fit(rows[i::3]) for i in range(3)]
bb = L.lfb_pack(msb, lp)
T(L.lfb_load(bb)["log_prior"] == lp, "LFB1 log priors survive")
lex_in = {"lex_en": ["hello", "World"], "lex_ru": ["привет"], "acr_en": ["usb"], "acr_ru": ["ржд"], "exc_en2ru": ["ghbdtn"], "exc_ru2en": ["руддщ"]}
lb = L.lfl_pack(lex_in)
lt = L.lfl_load(lb)
T(all(w.casefold() in lt[n] for n, ws in lex_in.items() for w in ws) and "hello" not in lt["lex_ru"], "LFL1 round trip")
TAGS = {"lex_en": 1, "lex_ru": 2, "acr_en": 3, "acr_ru": 4, "exc_en2ru": 5, "exc_ru2en": 6}
T(L.LEX_TAGS == TAGS, "tag numbers are part of the format")


def fnv(data):                                                          # an independent FNV-1a, 64 bit
    h = 0xCBF29CE484222325
    for x in data:
        h = ((h ^ x) * 0x100000001B3) % (1 << 64)
    return h


T(all(L.lex_key(t, "слово") == fnv(bytes([0xE0 + t]) + "слово".encode()) for t in TAGS.values()), "lex_key = FNV-1a(tag byte + UTF-8)")
T(L.fnv1a64(b"") == 0xCBF29CE484222325 and L.fnv1a64(b"a") == 0xAF63DC4C8601EC8C, "FNV-1a test vectors")
for name, blob, loader in (("LFB1", bb, L.lfb_load), ("LFL1", lb, L.lfl_load), ("LFW1", tw, L.lfw_load)):
    raises(L.FormatError, lambda b=blob, f=loader: f(b"XXXX" + b[4:]), name + " wrong magic")
    raises(L.FormatError, lambda b=blob, f=loader: f(b + b"\0"), name + " trailing byte")
    raises(L.FormatError, lambda b=blob, f=loader: f(b[:-1]), name + " truncated by one byte")
    raises(L.FormatError, lambda b=blob, f=loader: f(b[:9]), name + " truncated header")
    raises(L.FormatError, lambda f=loader: f(b""), name + " empty")
_old_ctx = L.ctx_key
L.ctx_key = lambda k, c: 1                                              # force a 64-bit collision of contexts
try:
    raises(L.FormatError, lambda: L.lfb_pack(msb, lp), "LFB1 hash collision is refused")
finally:
    L.ctx_key = _old_ctx

# the replacement transaction: edges of the typed-ahead window, a word at the field start, M2 success, no silent VERIFIED
for ahead, outcome, final in (("abc", "VERIFIED", "Hello привет abc"), ("abcd", "ABORTED", "Hello ghbdtn abcd")):
    f = L.SimField("Hello ghbdtn " + ahead, M1)
    r = L.run_transaction(f, OLD, NEW, ahead)
    T((r.outcome, f.text) == (outcome, final), f"typed ahead {ahead!r}")
f = L.SimField("Hello ghbdtn a", M1)
T(L.run_transaction(f, OLD, NEW, "ab").outcome == "VERIFIED" and f.text == "Hello привет a", "the engine recorded more than the field has")
f = L.SimField("ghbdtn ", M1)
T(L.run_transaction(f, OLD, NEW).outcome == "VERIFIED" and f.text == "привет ", "a word at offset 0")
f = L.SimField("Hello ghbdtn ", M2)
r = L.run_transaction(f, OLD, NEW, "", mode="MANUAL_ONLY")
T((r.outcome, r.method, f.text) == ("VERIFIED", "M2", "Hello привет "), "M2 on the hotkey path verifies")
f = L.SimField("Hello ghbdtn  tail", M2)
f.pos = len("Hello ghbdtn ")
r = L.run_transaction(f, OLD, NEW, "", mode="MANUAL_ONLY")
T((r.outcome, f.text) == ("VERIFIED", "Hello привет  tail"), "M2 inside a text: the verification range ends at the Space, not beyond it")
f = L.SimField("Hello ghbdtn ", M1_NOROLL, {("caret", 2): "back"})
r = L.run_transaction(f, OLD, NEW, "", mode="MANUAL_ONLY")
T((r.outcome, r.incident, r.quarantine, f.text) == ("UNRECOVERED", True, True, "Hello привет "),
  "right text with a wrong caret and no rollback is not VERIFIED")
f = L.SimField("", M2); f.send([("bs", ""), ("ch", "a"), ("ch", "b")])
T((f.text, f.pos) == ("ab", 2), "the test double: backspace at 0 is a no-op, insertion moves the caret by one")

# Q-2 of plan 1.2: SendInput facts. A physically pressed modifier aborts M2 before anything is written;
# a silently dropped batch (UIPI) leaves the typed text (RESTORED); a partly delivered batch is UNRECOVERED.
f = L.SimField("Hello ghbdtn ", M2); f.modifiers = True
r = L.run_transaction(f, OLD, NEW, "", mode="MANUAL_ONLY")
T((r.outcome, r.reason, f.text, f.sent) == ("ABORTED", "modifier_down", "Hello ghbdtn ", 0), "M2 with a modifier down writes nothing")
f = L.SimField("Hello ghbdtn ", M1); f.modifiers = True
T(L.run_transaction(f, OLD, NEW).outcome == "VERIFIED", "a pressed modifier is irrelevant to M1")
f = L.SimField("Hello ghbdtn ", M2, {("event", k): "drop" for k in range(1, 2 * len(OLD) + 3)})
r = L.run_transaction(f, OLD, NEW, "", mode="MANUAL_ONLY")
T((r.outcome, r.incident, r.quarantine, f.text) == ("RESTORED", True, True, "Hello ghbdtn "), "UIPI drops the whole batch: the field is unchanged")
f = L.SimField("Hello ghbdtn ", M2, {("event", len(OLD) + 2): "drop"})
r = L.run_transaction(f, OLD, NEW, "", mode="MANUAL_ONLY")
T((r.outcome, r.incident, r.quarantine) == ("UNRECOVERED", True, True), "a partly delivered batch is UNRECOVERED and quarantined")

# R-1 and R-2 of plan 1.3. M2 deletes by count, so a user key that arrives after the read (or while it runs) makes the
# plan wrong: the last look before the first synthetic event aborts and nothing is written. The race that remains
# (a key between that look and the first event) is a field-level fact, not an event-level one, and ends UNRECOVERED.
f = L.SimField("Hello ghbdtn ", M2, {("read", 1): "user:x"})
r = L.run_transaction(f, OLD, NEW, "", mode="MANUAL_ONLY")
T((r.outcome, r.reason, f.text, f.sent, r.incident) == ("ABORTED", "typed_ahead", "Hello ghbdtn x", 0, False), "M2: a key during the read aborts before anything is sent")
f = L.SimField("Hello ghbdtn ", M2, {("event", 1): "user:x"})
r = L.run_transaction(f, OLD, NEW, "", mode="MANUAL_ONLY")
T((r.outcome, r.reason, f.sent, f.user, r.incident, r.quarantine) == ("UNRECOVERED", "verify_failed", 14, ["x"], True, True),
  "M2: a key after the last look is the residual race: UNRECOVERED, quarantine, the plan is still sent exactly once")
f = L.SimField("Hello ghbdtn ", M1, {("caret", 2): "forward"})
r = L.run_transaction(f, OLD, NEW)
T((r.outcome, r.reason, f.text, r.incident) == ("RESTORED", "verify_failed", "Hello ghbdtn ", True),
  "M1: a caret that moved forward although no user key came is a failure; the rollback restores the field")
f = L.SimField("Hello ghbdtn ", M1, {("read", 2): "user:x"})
r = L.run_transaction(f, OLD, NEW)
T((r.outcome, f.text, f.pos) == ("VERIFIED", "Hello привет x", 14), "M1: one user key may move the caret by one")
f = L.SimField("Hello ghbdtn ", M1, {("read", 2): "user:x", ("caret", 2): "forward"})
r = L.run_transaction(f, OLD, NEW)
T((r.outcome, r.reason) == ("RESTORED", "verify_failed"), "M1: one user key explains a caret one place forward, not two")
f = L.SimField("Hello ghbdtn ", M1, {("replace", 1): "spill"})
r = L.run_transaction(f, OLD, NEW)
T((r.outcome, r.reason, f.text, r.incident, r.quarantine) == ("UNRECOVERED", "verify_failed", "Hello ghbdtn?", True, True),
  "M1: damage to the Space after the range is seen by the whole-range read-back; the rollback cannot repair it")
f = L.SimField("Hello ghbdtn a", M1, {("replace", 1): "spill"})
r = L.run_transaction(f, OLD, NEW, "a")
T((r.outcome, f.text) == ("UNRECOVERED", "Hello ghbdtn?a"), "M1 with a typed-ahead key: the whole fragment is verified and rolled back")
f = L.SimField("Hello ghbdtn a", M1, {("replace", 1): "autocorrect"})
r = L.run_transaction(f, OLD, NEW, "a")
T((r.outcome, f.text) == ("RESTORED", "Hello ghbdtn a"), "M1 with a typed-ahead key: a restored fragment is RESTORED")
T(L.classify_outcome(True, "ab c", "xy c", "ab c", False) == "RESTORED" and L.classify_outcome(True, "ab c", "xy c", "ab?c", False) == "UNRECOVERED"
  and L.classify_outcome(True, "ab c", "xy c", "xy c", True) == "VERIFIED", "classification works on the whole fragment")
M2_RACE = []
for k in range(1, 15):                                                 # a user key before every synthetic event of M2
    f = L.SimField("Hello ghbdtn ", M2, {("event", k): "user:x"})
    r = L.run_transaction(f, OLD, NEW, "", mode="MANUAL_ONLY")
    T(f.sent == 14 and f.user == ["x"] and r.incident and r.quarantine and r.outcome in ("UNRECOVERED", "VERIFIED"), f"M2 race at event {k}")
    M2_RACE.append(r.outcome)
T(M2_RACE == ["UNRECOVERED"] * 14, "a user key anywhere inside the plan always ends UNRECOVERED, never a wrong VERIFIED")

# hook health: states cannot be re-armed by luck
h = L.HookHealth()
T(h.canary is True, "canary is the default")
h.raw_key(0, 0); h.check(10_000)                                      # lost
for t in (1, 2, 3, 4):
    h.raw_key(20_000 + t, t); h.hook_key(20_000 + t, t)
T(not h.ok, "matched pairs without a re-installed hook do not re-arm")
h.reinstalled()
for t in (1, 2):
    h.raw_key(30_000 + t, t); h.hook_key(30_000 + t, t)
h.tap_disabled("timeout")                                              # lost again before the re-arm finished
for t in (1, 2, 3):
    h.raw_key(40_000 + t, t); h.hook_key(40_000 + t, t)
T(not h.ok, "a second loss resets the re-arm: pairs count only after the next reinstall")
h.reinstalled()
for t in (1, 2):
    h.raw_key(50_000 + t, t); h.hook_key(50_000 + t, t)
h.reinstalled()                                                        # installed once more: the count starts again
h.raw_key(60_000, 0); h.hook_key(60_000, 0)
T(not h.ok, "reinstall resets the pair count")
for t in (1, 2):
    h.raw_key(70_000 + t, t); h.hook_key(70_000 + t, t)
T(h.ok, "three pairs after the last reinstall re-arm")

# R-3 of plan 1.3: the canary compares events, not counts. One lost key and one extra key must not cancel out.
A, B, C = ("scan", 0x1E, False), ("scan", 0x30, False), ("scan", 0x2E, False)
h = L.HookHealth()
h.raw_key(0, A); h.hook_key(3, A)                                      # healthy
h.raw_key(100, B)                                                      # the hook never reports B ...
h.hook_key(105, C)                                                     # ... and reports C, which the observer never saw
T(h.check(100 + h.CANARY_MS) and h.ok, "inside the window nothing is decided")
T(not h.check(100 + h.CANARY_MS + 1) and h.reason == "canary_missing" and h.take_gap(),
  "lost B and extra C: the counts are equal, the signatures are not; the older unmatched event names the reason")
h = L.HookHealth()
h.hook_key(0, C)                                                       # a hook key the observer never saw
T(h.check(300) and h.ok and not h.check(301) and h.reason == "canary_extra", "an extra hook key alone is a loss")
h = L.HookHealth()
h.hook_key(10, A); h.raw_key(12, A)                                    # the hook event may come first
h.raw_key(20, B); h.hook_key(22, B)
T(h.check(10_000) and h.ok and h.hook_only == [] and h.raw_only == [], "either order matches")
h.hook_key(30, C, injected=True)                                       # our own SendInput, or another program's
T(h.check(10_000) and h.ok and h.hook_only == [], "an injected event has no physical counterpart and is not compared")
h = L.HookHealth()
h.raw_key(0, A); h.raw_key(50, A); h.hook_key(55, A)                   # two physical presses, one reported
T(h.check(350) and not h.check(351) and h.reason == "canary_missing", "equal signatures are matched one to one; the second press is the unmatched one")
h = L.HookHealth(canary=False)
h.raw_key(0, A); h.hook_key(1, B)
T(h.check(10_000) and h.ok, "without a canary (macOS) nothing is compared")


print(f"OK ({CHECKS} checks, {sweep} single and double faults, {conv} fuzz conversions, {checked_undo} fuzz undos)")
