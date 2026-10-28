"""vectors.py - generates the golden test vectors of section 20.12 from lfengine.py.
Run:  python vectors.py > vectors_out.json   (lfengine.py in the same directory; standard library only)."""
import sys, json, math, hashlib, struct; sys.path.insert(0, ".")
import lfengine as L
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
def dumps(v):
    return json.dumps(v, ensure_ascii=False)
def block(v):    # valid JSON, one row per line
    if isinstance(v, list) and v and isinstance(v[0], list):
        return "[\n" + ",\n".join(" " + dumps(r) for r in v) + "\n]"
    if isinstance(v, dict):
        return "{\n" + ",\n".join(" " + dumps(k) + ": " + dumps(x) for k, x in v.items()) + "\n}"
    return dumps(v)
sys.stdout.write("{\n" + ",\n".join(dumps(k) + ": " + block(v) for k, v in out.items()) + "\n}\n")
