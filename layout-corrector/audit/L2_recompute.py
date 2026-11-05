#!/usr/bin/env python3
"""L2: numbers of the specification recomputed from first principles and from the reference code.

Usage: python3 L2_recompute.py [spec.md]      (exit code 0 = no mismatch; prints one line per item)
Standard library only. Every item states where the spec says it (a search string that must occur in the spec), the
recomputed value and the verdict. A search string that is missing from the spec is a MISMATCH too: the claim moved or
vanished and the check must be revisited.
"""
import json, math, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "spec", "TZ_layout_correction_v3.md")
sys.path.insert(0, os.path.join(HERE, "..", "reference"))
import lfengine as L

text = open(SPEC, encoding="utf-8").read()
bad = 0


def item(name, ok, detail=""):
    global bad
    bad += 0 if ok else 1
    print(("OK       " if ok else "MISMATCH ") + name + (" :: " + str(detail) if detail else ""))


def said(s):          # the spec contains the statement
    return s in text


# 1. Parameter count of the CNN (7.1): embedding min(32,c) x 97, three convolutions 3/5/3, head 2c -> 3
def params(c):
    e = min(32, c)
    emb = 97 * e
    c1 = e * c * 3 + c
    c2 = c * c * 5 + c
    c3 = c * c * 3 + c
    head = 2 * c * 3 + 3
    return emb, c1, c2, c3, head
p = params(64)
item("CNN c=64 parameters", sum(p) == 42595 and p == (3104, 6208, 20544, 12352, 387), p)
item("   stated: layer breakdown and total", said("Embedding 3,104; conv 1: 6,208; conv 2: 20,544; conv 3: 12,352; head 387") and said("**42,595 parameters**"))
item("CNN c=32 -> 14,659", sum(params(32)) == 14659 and said("14,659"), sum(params(32)))
item("CNN c=96 -> 86,915", sum(params(96)) == 86915 and said("86,915"), sum(params(96)))
mac = 64 * 64 * 3 + 64 * 64 * 5 + 64 * 64 * 3 - 0
mac = 32 * 64 * 3 + 64 * 64 * 5 + 64 * 64 * 3
item("multiply-adds per position (c=64) = 38,912; 9-key word about 0.35 million", mac == 38912 and 0.34e6 < 9 * mac < 0.36e6 and said("38,912 multiply-adds"), (mac, 9 * mac))
item("FP32 size 170 KB (4 bytes per parameter)", abs(42595 * 4 / 1000 - 170.4) < 0.5, 42595 * 4 / 1000)
item("receptive field 1+2+4+2 = 9 (kernels 3, 5, 3)", (3 - 1) + (5 - 1) + (3 - 1) + 1 == 9 and said("Receptive field 1 + 2 + 4 + 2 = 9 keys"))

def macs(c, e):
    return e * c * 3 + c * c * 5 + c * c * 3
item("c=4: 1,584 multiply-adds per 9-key word (specified embedding), 2,880 with a 16-dimension embedding",
     9 * macs(4, 4) == 1584 and 9 * macs(4, 16) == 2880 and said("2,880 against 1,584 per 9-key word") and said("needs about 1,600 multiply-adds for a 9-key word"), (9 * macs(4, 4), 9 * macs(4, 16)))
item("16-dimension embedding vs specified: 0% (c=16), 14% (c=32), 8% (c=64), 6% (c=96) fewer",
     [round((macs(c, min(32, c)) - macs(c, 16)) / macs(c, min(32, c)) * 100) for c in (16, 32, 64, 96)] == [0, 14, 8, 6] and said("14% fewer at"), "")

# 2. Thresholds in nats
item("logit(0.999), logit(0.997), logit(0.995)", all(abs(math.log(t / (1 - t)) - v) < 5e-4 for t, v in ((0.999, 6.907), (0.997, 5.806), (0.995, 5.293))) and said("0.999 → 6.907, 0.997 → 5.806, 0.995 → 5.293 nats"))
cal = L.example_cal()
for d in ("en2ru", "ru2en"):
    got = [round(cal["lambda_nats"]["network"][d][b], 3) for b in ("3-4", "5-7", "8+")]
    item("example calibration lambdas " + d, got == [6.907, 5.806, 5.293], got)
item("buckets 3-4 / 5-7 / 8+", [L.bucket(n) for n in (3, 4, 5, 7, 8, 20)] == ["3-4", "3-4", "5-7", "5-7", "8+", "8+"])

# 3. EV-1, Poisson
item("4 false corrections in 100,000 is below 4.8e-5, 5 is above", 4 / 1e5 <= 4.8e-5 < 5 / 1e5 and said("at most 4 false corrections at n = 100,000"))
item("rule of three: 3.0e-4 for 10,000 transactions with 0 events", abs(L.poisson_upper(0) / 10000 - 3.0e-4) < 1e-6 and said("the 95% upper bound of the rate is then 3.0e-4"), L.poisson_upper(0) / 10000)
for k in range(0, 13):                          # the 95% upper limit is the mean at which P(X <= k) = 0.05
    mu = L.poisson_upper(k)
    cdf = sum(math.exp(-mu + i * math.log(mu) - math.lgamma(i + 1)) for i in range(k + 1))
    if abs(cdf - 0.05) > 1e-9:
        item("Poisson 95% limit k=%d" % k, False, cdf)
        break
else:
    item("Poisson 95% upper limit for k = 0..12 (by definition of the cdf)", True)
item("EV-1 minimum sizes accepted, one below refused", L.ev1_pass([], 100_000, 20, 100) and not L.ev1_pass([], 99_999, 20, 100) and not L.ev1_pass([], 100_000, 19, 100) and not L.ev1_pass([], 100_000, 20, 99))
item("EV-1 point estimate edge: 12 events of 250,000 pass, 13 fail (4.8e-5 x 250,000 = 12)", L.ev1_pass([("u%d" % i, "d%d" % i) for i in range(12)], 250_000, 30, 200) and not L.ev1_pass([("u%d" % i, "d%d" % i) for i in range(13)], 250_000, 30, 200))

# 4. Sizes and counts
item("47 keys, 94 key states, token ids, vocabulary 97", len(L.TABLE["en"][0]) == 47 and (L.PAD, L.BOS, L.EOS) == (0, 95, 96) and 1 + 2 * 46 + 1 == 94 and said("vocabulary size 97"), (L.PAD, L.BOS, L.EOS))
item("buffer 64, word 20 keys, undo 10 s and 100 characters, canary 300 ms, re-arm 3 pairs",
     (L.MAX_BUF, L.UNDO_WINDOW_MS, L.UNDO_MAX_CHARS, L.HookHealth.CANARY_MS, L.HookHealth.REARM_PAIRS) == (64, 10_000, 100, 300, 3),
     (L.MAX_BUF, L.UNDO_WINDOW_MS, L.UNDO_MAX_CHARS, L.HookHealth.CANARY_MS, L.HookHealth.REARM_PAIRS))
item("LFC1 example: pi_train shares equal their counts", all(abs(a - b / sum(cal["pi_train_counts"])) < 1e-9 for a, b in zip(cal["pi_train"], cal["pi_train_counts"])) and abs(sum(cal["pi_train"]) - 1) < 1e-9, cal["pi_train"])
for lay in ("en", "ru"):
    w = cal["w"][lay]
    item("w values in the allowed ranges (" + lay + ")", 0.0005 <= w["default"] <= 0.5 and 0.0005 <= w["after_switch"] <= 0.5 and 0 < w["run"] <= 0.3 + 1e-12, w)

# 5. Section 18.9 against the raw simulation results
sim = json.load(open(os.path.join(HERE, "L6_ev1_simulation.json")))
item("simulation: 36 scenario-cells x 10,000 runs, 360,000 runs checked, 0 cap violations", sim["runs"] == 10000 and sim["runs_checked"] == 360000 and sim["cap_violations"] == 0 and len(sim["scenarios"]) == 36)
S = {(s["rate"], s["users"], s["clustering"]): s for s in sim["scenarios"]}
worst = max((s for s in sim["scenarios"] if s["rate"] == 2e-4), key=lambda s: s["share"])
item("18.9 worst false acceptance 3.3% (strong, 50 users) with upper bound 3.64%", (worst["users"], worst["clustering"]) == (50, "strong") and round(worst["share"] * 100, 1) == 3.3 and round(worst["cp_hi"] * 100, 2) == 3.64, (worst["share"], worst["cp_hi"]))
item("criteria met: false acceptance <= 5% / 7%, power >= 80%", all(s["share"] <= 0.05 and s["cp_hi"] <= 0.07 for s in sim["scenarios"] if s["rate"] == 2e-4) and all(S[(2e-5, u, "moderate")]["share"] >= 0.8 for u in (50, 200)) and sim["false_acceptance_ok"] and sim["power_ok"])
rows = re.findall(r"^\| (2e-4|1e-4|5e-5|2e-5) \| (20|50|200) \| ([\d.]+)% \| ([\d.]+)% \| ([\d.]+)% \|$", text, re.M)
ok = len(rows) == 12
for r, u, a, b, c in rows:
    for kind, val in zip(("none", "moderate", "strong"), (a, b, c)):
        ok &= abs(S[(float(r), int(u), kind)]["share"] * 100 - float(val)) < 0.051
item("18.9 table: all 36 shares equal the JSON (rounded to 0.1%)", ok, "%d rows" % len(rows))

print("MISMATCHES:", bad)
sys.exit(1 if bad else 0)
