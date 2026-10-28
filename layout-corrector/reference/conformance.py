"""conformance.py - property tests of section 20.13 (standard library only).
Usage: python conformance.py   (in the folder that holds lfengine.py; prints OK or raises AssertionError)"""
import sys, random, math; sys.path.insert(0, ".")
import lfengine as L

R = random.Random(1)
for _ in range(200_000):                                  # P1: tokens, rendering, candidate
    run = [L.Key(R.randrange(47), R.random() < .5, R.random() < .3) for _ in range(R.randrange(1, 12))]
    assert all(1 <= L.token(k) <= 94 for k in run)
    for lay in ("en", "ru"):
        txt = L.render(run, lay)
        assert L.render([L.Key(k.id, L.effective_shift(k, lay)) for k in run], lay) == txt
        assert L.render(L.keys_from_text(txt, lay), lay) == txt
    for tgt in ("en", "ru"):
        c = L.candidate(run, tgt)
        if c:
            assert c.lead + c.core + c.trail == tuple(run)                       # no key lost or duplicated
            assert len(c.lead) <= 1 and len(c.trail) <= 2 and len(c.core) >= 1
            assert all(L.is_letter_in(tgt, k.id) for k in c.core)                # the core is letters only

for a in ("en", "ru"):                                    # P2: every prior is a probability vector
    for st in L.STATES:
        cal = L.example_cal()
        assert abs(sum(L.deployment_prior(a, cal["w"][a][st], cal["o_lat"])) - 1) < 1e-12

cal = L.example_cal()                                     # P3: a probability stored where nats are expected is refused
bad = L.example_cal(); bad["lambda_nats"]["network"]["en2ru"]["5-7"] = 0.997
try:
    L.check_calibration_package(bad); raise SystemExit("unit mix-up not caught")
except AssertionError:
    pass

rows = [[L.BOS] + [L.token(L.Key(R.randrange(47), R.random() < .3)) for _ in range(R.randrange(2, 9))] + [L.EOS]
        for _ in range(300)]                              # P4: LFB1 round trip equals the in-memory model
ms = [L.WittenBell().fit(rows[i::3]) for i in range(3)]
pkg = L.lfb_load(L.lfb_pack(ms, [math.log(x) for x in cal["pi_train"]]))
assert max(abs(L.lfb_logp(pkg, c, r) - ms[c].logp(r)) for c in range(3) for r in rows[:100]) < 1e-12

tw = L.toy_weights()                                      # P5: LFW1 size is header + 4 bytes per parameter; three finite logits
assert len(tw) == 16 + 4 * 3 + 4 * L.lfw_size(4, 4, (3, 5, 3))
out = L.lfw_forward(L.lfw_load(tw), L.tokens(L.keys_from_text("ghbdtn", "en")))
assert len(out) == 3 and all(math.isfinite(v) for v in out)
print("OK")
