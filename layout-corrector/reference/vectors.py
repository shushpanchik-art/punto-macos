"""vectors.py - generates the golden test vectors of section 20.12 from lfengine.py.
Run:  python vectors.py > vectors_out.json   (lfengine.py in the same directory; standard library only)."""
import sys, json, math, hashlib, struct; sys.path.insert(0, ".")
import lfengine as L


def build():
    """Build every golden vector from lfengine.py. The fault-matrix rows carry hand-written predictions and
    generation FAILS when the engine disagrees: producing the vectors is itself a test (20.13)."""
    K = L.keys_from_text
    cal = L.example_cal(); L.check_calibration_package(cal)
    out = {}
    # ---- V1 render + tokens
    rows = []
    for typed, lay in [("ghbdtn","en"),("Ghbdtn","en"),("GHBDTN","en"),("[jhjij","en"),(";bpym","en"),(",jkmit","en"),("k.,k.","en"),("`","en"),("руддщ","ru"),("Руддщ,","ru")]:
        keys = K(typed, lay); other = L.OTHER_LAYOUT[lay]
        rows.append([typed, lay, L.render(keys, other), L.tokens(keys)])
    out["render"] = rows
    # caps
    caps = []
    for kid, sh, cp in [(30,False,True),(23,False,True),(36,True,True),(23,False,False)]:
        k = L.Key(kid, sh, cp); caps.append([kid, sh, cp, L.render_key(k,"en"), L.render_key(k,"ru"), L.token(k)])
    out["caps"] = caps
    out["prefix"] = L.tokens(K("ghb","en"), complete=False)
    out["tok25"] = len(L.tokens([L.Key(i%47) for i in range(25)]))
    # ---- V3 candidates
    cands = []
    for typed, lay, tgt in [("Ghbdtn?","en","ru"),("Ghbdtn?!","en","ru"),("(ghbdtn)","en","ru"),("k.,k.","en","ru"),("[jhjij","en","ru"),("руддщ,","ru","en"),("(руддщ)","ru","en"),("руддщб","ru","en"),("руддщ..","ru","en"),("ghb1","en","ru"),(",","en","ru"),('"ghbdtn"',"en","ru"),("hello,","en","ru"),("Ghbdtn,","en","ru")]:
        run = K(typed, lay); c = L.candidate(run, tgt)
        cands.append([typed, tgt, None if c is None else (L.render(c.lead,tgt), L.render(c.core,tgt), L.render(c.trail,tgt))])
    out["cands"] = cands
    # ---- V4 guards
    gs = []
    for typed, act in [("github.com","en"),("https://x.io","en"),("user@example.com","en"),("MyVariable","en"),("asdfgh","en"),("фывапр","ru"),("kubectl","en"),("ghbdtn","en")]:
        run = K(typed, act)
        cand = L.candidate(run, L.OTHER_LAYOUT[act])
        gs.append([typed, act, L.shape_guard(run, act, cand.core) if cand else "no_candidate"])
    out["guards"] = gs
    # ---- V13 priors, V14 thresholds
    pri = []
    for a in ("en","ru"):
        for st in L.STATES:
            w = cal["w"][a][st]; v = L.deployment_prior(a, w, cal["o_lat"]); pri.append([a, st, w, [round(x,4) for x in v]])
    out["priors"] = pri
    out["lambdas"] = [[t, round(L.logit(t),3)] for t in (0.9995, 0.999, 0.997, 0.995, 0.99, 0.9)]
    # ---- V5 score examples
    sc = []
    for z, a, st in [([-3,9,-2],"en","default"),([-3,9,-2],"en","run"),([-3,9,-2],"en","after_switch"),([8,-3,-2],"ru","default"),([-2,-3,8],"ru","default"),([8,-3,-2],"en","default")]:
        w = cal["w"][a][st]; sc.append([z, a, st, round(L.score(z, a, cal, w), 3)])
    out["scores"] = sc
    # ---- V6 decide with stub scorers
    def mk(z): return lambda ids: z
    dec = []
    lex = {"en": {"hello","the"}, "ru": {"привет"}, "acr_en": {"sql"}, "acr_ru": {"мтс"}}
    cases = [("ghbdtn","en",[-3,9,-2],"default",False,frozenset()),
             ("ghbdtn","en",[-3,8,-2],"default",False,frozenset()),
             ("ghbdtn","en",[-3,8,-2],"run",True,frozenset()),
             ("ghbdtn","en",[-3,9,-2],"default",False,frozenset({("en2ru","ghbdtn")})),
             ("hello","en",[-3,9,-2],"default",False,frozenset()),
             ("z","en",[-3,9,-2],"default",False,frozenset()),
             ("ye","en",[-3,9,-2],"default",False,frozenset()),
             ("ye","en",[-3,9,-2],"run",True,frozenset()),
             ("github.com","en",[-3,9,-2],"default",False,frozenset()),
             ("руддщ","ru",[9,-3,-2],"default",False,frozenset()),
             ("руддщ,","ru",[9,-3,-2],"default",False,frozenset()),
             ("привет","ru",[9,-3,-2],"default",False,frozenset()),
             ("Ghbdtn?","en",[-3,9,-2],"default",False,frozenset())]
    for typed, act, z, st, ra, ex in cases:
        run = K(typed, act)
        d = L.decide(run, act, cal, mk(z), st, ra, ex, lex)
        dec.append([typed, act, z, st, ra, bool(ex), d.action, d.reason, d.replacement, None if d.margin is None else round(d.margin,3), d.n_keys])
    out["decide"] = dec
    # ---- V7 engine traces
    def stub_by_word(table, default):
        def f(ids):
            txt = "".join(L.TABLE["en"][(t-1)%2][(t-1)//2] for t in ids if 1 <= t <= 94)
            return table.get(txt.lower(), default)
        return f
    HI, MID = [-3,9,-2], [-3,6.5,-2]
    sc1 = stub_by_word({"ghbdtn": HI}, MID)
    E = L.Engine(cal, sc1, lex)
    def word(txt, lay, t0):
        for i,k in enumerate(K(txt, lay)): E.on_event(L.Event("key", k, lay, t0+i*100))
        return E.on_event(L.Event("space", None, lay, t0+len(txt)*100+50))
    tr = []
    for txt, t0 in [("ghbdtn",0),("z",1000),("ntcn",2000),("vbh",3000),("ntcn",4000),("ntcn",5000)]:
        st = "run" if E.credit>0 else ("after_switch" if E.after_switch else "default")
        d = word(txt, "en", t0)
        tr.append([txt, st, d.action, d.reason, None if d.margin is None else round(d.margin,3), E.credit])
    out["trace_run"] = tr
    # undo + cooldown
    E = L.Engine(cal, sc1, lex)
    tr2 = []
    d = word("ghbdtn","en",0); tr2.append(["ghbdtn", d.action, d.reason, E.credit])
    E.undo(1000); tr2.append(["(undo at 1000 ms)", "", "", E.credit])
    for txt,t0 in [("ghbdtn",2000),("ghbdtn",3000),("ghbdtn",4000),("ghbdtn",5000),("ghbdtn",11500)]:
        d = word(txt,"en",t0); tr2.append([f"{txt} @{t0}", d.action, d.reason, E.credit])
    out["trace_undo"] = tr2
    # other event scenarios
    def scen(name, evs, gate=None):
        E = L.Engine(cal, sc1, lex); res = []
        for ev in evs:
            if ev == "gate:DENY": E.set_gate("DENY"); continue
            if ev == "gate:ALLOW": E.set_gate("ALLOW"); continue
            r = E.on_event(ev)
            if r is not None: res.append([r.action, r.reason])
        return [name, res]
    ks = lambda t, l="en", tl="en": [L.Event("key", k, l, i*100) for i,k in enumerate(K(t,tl))]
    sp = lambda l="en", t=9000: L.Event("space", None, l, t)
    out["scen"] = [
     scen("word + Space", ks("ghbdtn")+[sp()]),
     scen("word + Enter (break), then Space", ks("ghbdtn")+[L.Event("break")]+[sp()]),
     scen("word + Tab (break), then Space", ks("ghbdtn")+[L.Event("break")]+[sp()]),
     scen("layout changes inside the word (key layout differs)", ks("ghb")+ks("dtn","ru","en")+[sp("ru")]),
     scen("manual layout event inside the word", ks("ghb")+[L.Event("layout")]+ks("dtn")+[sp()]),
     scen("Space sampled on another layout", ks("ghbdtn")+[sp("ru")]),
     scen("gate DENY while typing (password field)", ["gate:DENY"]+ks("ghbdtn")+[sp()]),
     scen("gate DENY then ALLOW again, new word", ["gate:DENY"]+ks("ghbdtn")+[sp(), "gate:ALLOW"]+ks("ghbdtn")+[sp()]),
     scen("Backspace edits the word", ks("ghbdtnx")+[L.Event("backspace")]+[sp()]),
     scen("65 keys (overflow)", [L.Event("key", L.Key(i%33), "en", i) for i in range(65)]+[sp()]),
     scen("two Spaces", ks("ghbdtn")+[sp(),sp()]),
    ]
    # ---- V8 manual
    out["manual"] = [[t, *L.manual_convert(t)] for t in ["Ghbdtn? Rfr ltkf?","Привет, как дела?","123","ghbdtn 😀","ЁЖ ёж","Hello, Привет"]]
    # ---- V9 ev1
    out["ev1"] = [
     ["4 errors, 4 users, n=100000, 20 users, 100 docs", L.ev1_pass([("u%d"%i,"d%d"%i) for i in range(4)],100000,20,100), round(L.ev1_bound([("u%d"%i,"d%d"%i) for i in range(4)],100000),7)],
     ["4 errors in one document", L.ev1_pass([("u1","d1")]*4,100000,20,100), round(L.ev1_bound([("u1","d1")]*4,100000),7)],
     ["0 errors, n=100000", L.ev1_pass([],100000,20,100), round(L.ev1_bound([],100000),7)],
     ["0 errors, n=99999", L.ev1_pass([],99999,20,100), round(L.ev1_bound([],99999),7)],
     ["0 errors, 19 users", L.ev1_pass([],200000,19,100), round(L.ev1_bound([],200000),7)],
     ["5 errors in 5 clusters, n=150000", L.ev1_pass([("u%d"%i,"d%d"%i) for i in range(5)],150000,20,100), round(L.ev1_bound([("u%d"%i,"d%d"%i) for i in range(5)],150000),7)],
     ["2+2 errors in 2 clusters, n=100000", L.ev1_pass([("u1","d1")]*2+[("u2","d2")]*2,100000,20,100), round(L.ev1_bound([("u1","d1")]*2+[("u2","d2")]*2,100000),7)],
    ]
    out["poisson"] = [round(L.poisson_upper(k),4) for k in range(6)]
    # ---- V10 baseline toy
    def keyrow(w, lay): return L.tokens(K(w, lay))
    # train each class on key rows of its own words (RU words typed on RU layout, EN/OTHER on EN)
    trainset = {0:[keyrow(w,"en") for w in ["hello","hell","help","hero","world","word"]],
                1:[keyrow(w,"ru") for w in ["привет","привал","приказ","пригород","мир","мирно"]],
                2:[keyrow(w,"en") for w in ["kubectl","github","asdfgh","docker","nginx","vim"]]}
    ms = [L.WittenBell().fit(trainset[c]) for c in range(3)]
    lp = [math.log(x) for x in cal["pi_train"]]
    blob = L.lfb_pack(ms, lp); pkg = L.lfb_load(blob)
    test = keyrow("ghbdtn","en")
    lg = L.baseline_logits(ms, lp, test)
    out["wb"] = {"test_word_keys":"ghbdtn", "logp_by_class":[round(m.logp(test),6) for m in ms], "logits":[round(v,6) for v in lg],
                 "lfb_bytes": len(blob), "lfb_sha256_16": hashlib.sha256(blob).hexdigest()[:16],
                 "lfb_logp": [round(L.lfb_logp(pkg,c,test),6) for c in range(3)],
                 "hello_ru": round(ms[1].logp(keyrow("hello","en")),6), "hello_en": round(ms[0].logp(keyrow("hello","en")),6),
                 "n_pairs": [sum(len(d) for k in range(3) for d in m.cnt[k].values()) for m in ms]}
    out["wb_score"] = round(L.score(lg, "en", {**cal, "temperature":{"network":1.0,"ngram":1.0}}, 0.01, "ngram"), 3)
    # ---- V11 toy network
    tw = L.toy_weights(); W = L.lfw_load(tw)
    out["lfw"] = {"bytes": len(tw), "sha256_16": hashlib.sha256(tw).hexdigest()[:16],
                  "logits_ghbdtn": [round(v,6) for v in L.lfw_forward(W, L.tokens(K("ghbdtn","en")))],
                  "logits_hello": [round(v,6) for v in L.lfw_forward(W, L.tokens(K("hello","en")))],
                  "first_floats": [float(x) for x in struct.unpack_from("<4f", tw, 16+12)]}
    out["fnv"] = [[s, hex(L.fnv1a64(s.encode()))] for s in ["", "a", "foobar"]] + [["ctx_key(2,(95,61))", hex(L.ctx_key(2,(95,61)))], ["pair_key(2,(95,61),63)", hex(L.pair_key(2,(95,61),63))]]
    # ---- V12 lexicon tables and calibration package
    lexb = L.lfl_pack({"lex_en": ["Hello", "the", "World"], "lex_ru": ["привет", "мир"], "acr_en": ["SQL"], "acr_ru": ["МТС"]})
    lt = L.lfl_load(lexb)
    out["lfl"] = {"bytes": len(lexb), "sha256_16": hashlib.sha256(lexb).hexdigest()[:16],
                  "keys": [["lex_en", "hello", hex(L.lex_key(1, "hello"))], ["lex_ru", "привет", hex(L.lex_key(2, "привет"))],
                           ["acr_ru", "МТС", hex(L.lex_key(4, "МТС"))]],
                  "member": [["lex_en", "HELLO", "HELLO" in lt["lex_en"]], ["lex_en", "hi", "hi" in lt["lex_en"]],
                             ["acr_en", "sql", "sql" in lt["acr_en"]]]}
    cj = L.cal_to_json(cal)
    out["cal_json"] = {"bytes": len(cj.encode("utf-8")), "sha256_16": hashlib.sha256(cj.encode("utf-8")).hexdigest()[:16]}
    # ---- V15 Caps Lock on the letter keys of the two layouts (token formula of 20.2)
    out["caps_all"] = [[kid, sh, cp, L.render_key(L.Key(kid, sh, cp), "en"), L.render_key(L.Key(kid, sh, cp), "ru"),
                        L.token(L.Key(kid, sh, cp))]
                       for kid in (0, 5, 13, 23, 24, 25, 30, 35, 36, 44, 45, 46)
                       for sh, cp in ((False, False), (True, False), (False, True), (True, True))]
    # ---- V16 undo snapshot lifecycle (13.3, 13.4)
    def fresh(layout="en", t0=1000, word_="ghbdtn", caps=False):
        e = L.Engine(cal, (lambda ids: [-3, 9, -2]) if layout == "en" else (lambda ids: [9, -3, -2]), lex)
        for i, k in enumerate(K(word_, layout)):
            e.on_event(L.Event("key", L.Key(k.id, k.shift, caps), layout, t0 + i))
        d = e.on_event(L.Event("space", None, layout, t0 + len(word_)))
        return e, d, t0 + len(word_)
    ul = []
    e, d, ts = fresh(); ul.append(["convert", d.action, d.replacement, e.snapshot is not None])
    r = e.undo(ts + 500); ul.append(["undo after 500 ms", r, sorted(e.exceptions), e.credit, e.cool_words, e.snapshot is not None])
    ul.append(["second undo", e.undo(ts + 600)])
    e, d, ts = fresh(); ul.append(["undo at exactly 10000 ms", e.undo(ts + 10000)])
    e, d, ts = fresh(); ul.append(["undo at 10001 ms", e.undo(ts + 10001)])
    for n_after in (100, 101):
        e, d, ts = fresh()
        for i in range(n_after):
            e.on_event(L.Event("key", L.Key(i % 47), "en", ts + 10 + i))
        ul.append([f"undo after {n_after} further characters", e.undo(ts + 2000)])
    e, d, ts = fresh(caps=True); ul.append(["Caps Lock word", d.action, d.replacement, e.undo(ts + 5)])
    e, d, ts = fresh("ru", word_="руддщ"); ul.append(["ru to en", d.action, d.replacement, e.undo(ts + 5)])
    for name, act in [("break", lambda e: e.on_event(L.Event("break"))), ("layout change", lambda e: e.on_event(L.Event("layout", None, "ru"))),
                      ("gap", lambda e: e.on_event(L.Event("gap"))), ("gate DENY", lambda e: e.set_gate("DENY")),
                      ("mode MANUAL_ONLY", lambda e: e.set_mode("MANUAL_ONLY")), ("outcome RESTORED", lambda e: e.on_outcome("RESTORED")),
                      ("outcome VERIFIED", lambda e: e.on_outcome("VERIFIED")), ("backspace", lambda e: e.on_event(L.Event("backspace")))]:
        e, d, ts = fresh(); act(e); ul.append([f"after {name}", e.undo(ts + 5), e.credit])
    out["undo"] = ul
    # ---- V17 mode derivation (13.5)
    CAPS_M1 = ["READBACK", "READ_RANGE", "REPLACE_RANGE", "ROLLBACK"]
    CAPS_M2 = ["READBACK", "READ_RANGE", "SYNTHETIC_INPUT"]
    out["modes"] = [[name, caps, sup, flags, L.engine_mode(caps, sup, **flags)] for name, caps, sup, flags in [
        ("M1 with rollback", CAPS_M1, "AUTO", {}), ("M1 with rollback", CAPS_M1, "MANUAL", {}), ("M1 with rollback", CAPS_M1, "UNKNOWN", {}),
        ("M1 without rollback", CAPS_M1[:3], "AUTO", {}), ("M2 only", CAPS_M2, "AUTO", {}), ("M2 only", CAPS_M2, "MANUAL", {}),
        ("M1 with rollback", CAPS_M1, "AUTO", {"hook_ok": False}), ("M1 with rollback", CAPS_M1, "AUTO", {"models_ok": False}),
        ("M1 with rollback", CAPS_M1, "AUTO", {"watchdog_ok": False}), ("M1 with rollback", CAPS_M1, "AUTO", {"layout_ok": False}),
        ("M1 with rollback", CAPS_M1, "AUTO", {"permission_ok": False}), ("M1 with rollback", CAPS_M1, "AUTO", {"quarantined": True}),
        ("read only", ["READ_RANGE"], "AUTO", {}), ("nothing", [], "AUTO", {})]]
    # ---- V18 outcome classification
    out["outcome"] = [[a, o, n, f, v, L.classify_outcome(a, o, n, f, v)] for a, o, n, f, v in [
        (False, "x", "y", None, False), (True, "x", "y", "y", True), (True, "x", "y", "y", False), (True, "x", "y", "x", False),
        (True, "x", "y", "z", False), (True, "x", "y", None, False)]]
    # ---- V19 replacement transaction against injected faults. Expected values are hand-written; generation fails on a mismatch.
    M1 = {"READ_RANGE", "REPLACE_RANGE", "READBACK", "ROLLBACK"}; M1N = {"READ_RANGE", "REPLACE_RANGE", "READBACK"}
    M2 = {"READ_RANGE", "READBACK", "SYNTHETIC_INPUT"}
    B, C = "Hello ghbdtn ", "Hello привет "
    MAN = {"mode": "MANUAL_ONLY"}
    FM = [  # name, caps, text, faults, ahead, kwargs, outcome, reason, final text, incident
        ("m1 ok", M1, B, {}, "", {}, "VERIFIED", "ok", C, False),
        ("m1 ok with typed-ahead keys", M1, B + "ab", {}, "ab", {}, "VERIFIED", "ok", "Hello привет ab", False),
        ("m1 ok, the application has not shown the last typed-ahead key", M1, B + "a", {}, "ab", {}, "VERIFIED", "ok", "Hello привет a", False),
        ("m1 user key lands before the range is read", M1, B, {"read:1": "user:x"}, "", {}, "VERIFIED", "ok", "Hello привет x", False),
        ("m1 user key lands just before the write", M1, B, {"replace:1": "user:x"}, "", {}, "VERIFIED", "ok", "Hello привет x", False),
        ("too many typed-ahead keys", M1, B + "abcd", {}, "abcd", {}, "ABORTED", "typed_ahead", B + "abcd", False),
        ("context break", M1, B, {}, "", {"context_break": True}, "ABORTED", "context_break", B, False),
        ("layout changed", M1, B, {}, "", {"layout_changed": True}, "ABORTED", "context_break", B, False),
        ("gate turned DENY", M1, B, {"gate:1": "DENY"}, "", {}, "ABORTED", "gate_changed", B, False),
        ("gate unknown", M1, B, {"gate:1": "UNKNOWN"}, "", {}, "ABORTED", "gate_changed", B, False),
        ("gate query fails", M1, B, {"gate:1": "raise"}, "", {}, "ABORTED", "gate_changed", B, False),
        ("caret query fails", M1, B, {"caret:1": "raise"}, "", {}, "ABORTED", "adapter_error", B, False),
        ("range unreadable", M1, B, {"read:1": "none"}, "", {}, "ABORTED", "echo_mismatch", B, False),
        ("read times out", M1, B, {"read:1": "raise"}, "", {}, "ABORTED", "adapter_error", B, False),
        ("read returns stale text", M1, B, {"read:1": "stale"}, "", {}, "ABORTED", "echo_mismatch", B, False),
        ("application had autocorrected the word", M1, "Hello Ghbdtn ", {}, "", {}, "ABORTED", "echo_mismatch", "Hello Ghbdtn ", False),
        ("typed-ahead key the engine did not record", M1, B + "x", {}, "", {}, "ABORTED", "echo_mismatch", B + "x", False),
        ("partial write, rollback works", M1, B, {"replace:1": "partial"}, "", {}, "RESTORED", "write_error", B, True),
        ("write fails, nothing written", M1, B, {"replace:1": "raise"}, "", {}, "RESTORED", "write_error", B, True),
        ("write applied but reports a timeout", M1, B, {"replace:1": "applied_error"}, "", {}, "RESTORED", "write_error", B, True),
        ("application autocorrects the written text", M1, B, {"replace:1": "autocorrect"}, "", {}, "RESTORED", "verify_failed", B, True),
        ("write silently ignored", M1, B, {"replace:1": "ignored"}, "", {}, "RESTORED", "verify_failed", B, True),
        ("read-back differs", M1, B, {"read:2": "stale"}, "", {}, "RESTORED", "verify_failed", B, True),
        ("read-back times out", M1, B, {"read:2": "raise"}, "", {}, "RESTORED", "verify_failed", B, True),
        ("caret ends up before its expected place", M1, B, {"caret:2": "back"}, "", {}, "RESTORED", "verify_failed", B, True),
        ("partial write and the rollback fails", M1, B, {"replace:1": "partial", "replace:2": "raise"}, "", {}, "UNRECOVERED", "write_error", "Hello приdtn ", True),
        ("autocorrect and the rollback is ignored", M1, B, {"replace:1": "autocorrect", "replace:2": "ignored"}, "", {}, "UNRECOVERED", "verify_failed", "Hello приве? ", True),
        ("no rollback capability, partial write", M1N, B, {"replace:1": "partial"}, "", MAN, "UNRECOVERED", "write_error", "Hello приdtn ", True),
        ("no rollback capability, but the write is fine", M1N, B, {}, "", MAN, "VERIFIED", "ok", C, False),
        ("AUTO requested without the capabilities", M1N, B, {}, "", {"mode": "AUTO"}, "ABORTED", "capability", B, False),
        ("AUTO requested for synthetic input", M2, B, {}, "", {"mode": "AUTO"}, "ABORTED", "capability", B, False),
        ("mode OFF", M1, B, {}, "", {"mode": "OFF"}, "ABORTED", "mode_off", B, False),
        ("no read capability", {"REPLACE_RANGE", "ROLLBACK"}, B, {}, "", MAN, "ABORTED", "capability", B, False),
        ("m2 manual ok", M2, B, {}, "", MAN, "VERIFIED", "ok", C, False),
        ("m2 with typed-ahead keys is refused", M2, B + "a", {}, "a", MAN, "ABORTED", "typed_ahead", B + "a", False),
        ("m2 user key between synthetic events", M2, B, {"event:3": "user:x"}, "", MAN, "UNRECOVERED", "verify_failed", "Hello gпривет ", True),
        ("m2 synthetic event times out", M2, B, {"event:5": "raise"}, "", MAN, "UNRECOVERED", "write_error", "Hello ghb", True),
    ]
    tx = []
    for name, caps, text, faults, ahead, kw, outcome, reason, final, incident in FM:
        f = L.SimField(text, caps, {(k.split(":")[0], int(k.split(":")[1])): v for k, v in faults.items()})
        r = L.run_transaction(f, "ghbdtn", "привет", ahead, **kw)
        got = (r.outcome, r.reason, f.text, r.incident, r.quarantine)
        if got != (outcome, reason, final, incident, incident):
            raise AssertionError(f"fault matrix row {name!r}: engine gives {got}")
        tx.append([name, sorted(caps), text, faults, ahead, kw, outcome, reason, final, incident])
    out["tx"] = tx
    # ---- V20 layout identity
    en_e, ru_e = L.table_entries("en"), L.table_entries("ru")
    typew = list(ru_e); typew[9] = "$"
    out["fingerprint"] = [["en", L.layout_fingerprint(en_e), L.identify_layout(en_e)], ["ru", L.layout_fingerprint(ru_e), L.identify_layout(ru_e)],
                          ["ru with key 4 shifted changed to $", L.layout_fingerprint(typew), L.identify_layout(typew)],
                          ["en rotated by one entry", L.layout_fingerprint(en_e[1:] + en_e[:1]), L.identify_layout(en_e[1:] + en_e[:1])]]
    # ---- V21 hook health
    h = L.HookHealth(canary=True); hh = []
    for t in (0, 100, 200):
        h.raw_key(t); h.hook_key(t + 5)
    hh.append(["three matched keys", h.check(250), h.take_gap()])
    h.raw_key(1000); hh.append(["key unseen by the hook, at the limit", h.check(1300), h.take_gap()])
    hh.append(["key unseen by the hook, past the limit", h.check(1301), h.take_gap()])
    hh.append(["gap is reported once", h.ok, h.take_gap()])
    h.reinstalled()
    for i in range(3):
        h.raw_key(3000 + i); h.hook_key(3000 + i); hh.append([f"re-arm pair {i + 1}", h.ok, h.take_gap()])
    m = L.HookHealth(canary=False); m.tap_disabled("timeout"); hh.append(["macOS tapDisabledByTimeout", m.ok, m.take_gap(), m.reason])
    m.reinstalled(); hh.append(["macOS tap enabled again", m.ok, m.take_gap(), m.reason])
    m.tap_disabled("user_input"); hh.append(["macOS tapDisabledByUserInput", m.ok, m.take_gap(), m.reason])
    out["hook"] = hh
    return out


def dumps(v):
    return json.dumps(v, ensure_ascii=False)
def block(v):    # valid JSON, one row per line
    if isinstance(v, list) and v and isinstance(v[0], list):
        return "[\n" + ",\n".join(" " + dumps(r) for r in v) + "\n]"
    if isinstance(v, dict):
        return "{\n" + ",\n".join(" " + dumps(k) + ": " + dumps(x) for k, x in v.items()) + "\n}"
    return dumps(v)
def render(out):
    return "{\n" + ",\n".join(dumps(k) + ": " + block(v) for k, v in out.items()) + "\n}\n"


if __name__ == "__main__":
    sys.stdout.write(render(build()))
