import sys; sys.path.insert(0, ".")
import lfengine as L
from cal_example import example_cal
K = L.keys_from_text
cal = example_cal(); L.check_calibration_package(cal)
# units: probability thresholds as nats
print([round(L.logit(p), 3) for p in (0.999, 0.997, 0.995, 0.9995)])
# priors sum to 1
for a in ("en", "ru"):
    for st in L.STATES:
        v = L.deployment_prior(a, cal["w"][a][st], cal["o_lat"]); assert abs(sum(v) - 1) < 1e-12
# unit mix-up is caught
bad = example_cal(); bad["lambda_nats"]["network"]["en2ru"]["5-7"] = 0.997
try: L.check_calibration_package(bad); raise SystemExit("not caught")
except AssertionError as e: print("caught:", e)
# score = logit(p'(RU)) when active EN
import math
z = [-3, 8, -2]
s = L.score(z, "en", cal, 0.01)
lp = L.log_softmax(z); pr = L.deployment_prior("en", .01, .25)
q = [math.exp(a) * b / c for a, b, c in zip(lp, pr, cal["pi_train"])]; tot = sum(q); pru = q[1] / tot
print("score", round(s, 4), "logit(p'RU)", round(L.logit(pru), 4)); assert abs(s - L.logit(pru)) < 1e-9
# decide with a stub scorer
stub = lambda ids: z
r = K("ghbdtn", "en")
d = L.decide(r, "en", cal, stub); print(d)
# engine trace
E = L.Engine(cal, stub, lexicon={"en": {"hello"}, "ru": set(), "acr_en": set(), "acr_ru": set()})
def typ(text, layout, t0, with_space=True):
    out = None
    for i, k in enumerate(K(text, layout)):
        E.on_event(L.Event("key", k, layout, t0 + i * 100))
    if with_space: out = E.on_event(L.Event("space", None, layout, t0 + len(text) * 100))
    return out
print(typ("ghbdtn", "en", 0))
print("credit", E.credit)
print(typ("ghbdtn", "en", 10000)); print("credit", E.credit)
print(typ("ghbdtn", "en", 20000)); print("credit", E.credit)
print(typ("ghbdtn", "en", 30000)); print("credit", E.credit)
print(typ("ghbdtn", "en", 40000)); print("credit", E.credit)
print("manual", L.manual_convert("Ghbdtn? Rfr ltkf?"), L.manual_convert("Привет, как дела?"), L.manual_convert("123"))
# LFB1 round trip
import random
R = random.Random(5)
rows = [[L.BOS] + [L.token(L.Key(R.randrange(47), R.random() < .3)) for _ in range(R.randrange(2, 9))] + [L.EOS] for _ in range(300)]
ms = [L.WittenBell().fit(rows[i::3]) for i in range(3)]
lp = [math.log(x) for x in cal["pi_train"]]
blob = L.lfb_pack(ms, lp); pkg = L.lfb_load(blob)
mx = max(abs(L.lfb_logp(pkg, c, r) - ms[c].logp(r)) for c in range(3) for r in rows[:100]); print("lfb size", len(blob), "max diff", mx); assert mx < 1e-12
print(hex(L.fnv1a64(b"")), hex(L.fnv1a64(b"a")), hex(L.fnv1a64(b"foobar")))
# toy network
W = L.lfw_load(L.toy_weights()); print([round(v, 6) for v in L.lfw_forward(W, L.tokens(K("ghbdtn", "en")))])
print(round(L.poisson_upper(0), 4), round(L.poisson_upper(4), 4), L.ev1_pass([("u1","d1")]*4, 100000, 20, 100), L.ev1_pass([("u%d"%i,"d1") for i in range(4)], 100000, 20, 100), L.ev1_bound([("u1","d1")]*2+[("u2","d2")]*2,100000))
print("OK")
