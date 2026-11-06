#!/usr/bin/env python3
"""L3: executable evidence for the mutants that survived the mutation run.

For every survivor listed in results.json the script rebuilds the mutant from reference/lfengine.py (the line given in
mutants.json is replaced, nothing else) and decides, by running both versions, one of these classes:

  IDENTICAL         the mutated literal has the same value as the original (0.0*2 == 0.0): the program is the same.
  DEAD              the changed value is never used (every call passes the argument; the branch is never reached).
  REDUNDANT         another check of the same function gives the same verdict on every input tried (and a reason).
  DIFFERENTIAL      original and mutant give equal results on a stated set of inputs (not a proof; the set is printed).
  TIE_IMPOSSIBLE    the mutant differs only when two floats are exactly equal and the script shows that cannot happen.
  ULP_TIE           the mutant differs, at most, by one unit in the last place of the result at an exact float tie.
  SIDE_EFFECT_ONLY  every result is equal; the mutant makes one more read call on a path that aborts anyway.
  OUTSIDE_CONTRACT  the mutant differs only for inputs that the specification excludes (stated); the code does not check the precondition.
  GAP               a concrete input is found on which the mutant behaves differently: the tests had a hole.

Usage: python3 equivalence_evidence.py [reference_dir] [mutants.json] [results.json] [--json out.json]
Standard library only. Deterministic (fixed seeds). Exit code 0 when every survivor got a class."""
import copy
import importlib
import itertools
import json
import math
import os
import random
import sys
import types
from fractions import Fraction

HERE = os.path.dirname(os.path.abspath(__file__))
args = [a for a in sys.argv[1:] if not a.startswith("--")]
REF = args[0] if len(args) > 0 else os.path.join(HERE, "..", "..", "reference")
MUT = args[1] if len(args) > 1 else os.path.join(HERE, "mutants.json")
RES = args[2] if len(args) > 2 else os.path.join(HERE, "results.json")
OUT = sys.argv[sys.argv.index("--json") + 1] if "--json" in sys.argv else None

SRC = open(os.path.join(REF, "lfengine.py"), encoding="utf-8").read()
LINES = SRC.split("\n")
MUTANTS = {m["id"]: m for m in json.load(open(MUT))["mutants"]}
SURV = [r["id"] for r in json.load(open(RES))["results"] if r["status"].startswith("SURVIVED")]
_cache = {}


def load(src, name):
    mod = types.ModuleType(name)
    mod.__file__ = name + ".py"
    sys.modules[name] = mod
    exec(compile(src, name + ".py", "exec"), mod.__dict__)
    return mod


def mutant_src(mid):
    m = MUTANTS[mid]
    lines = list(LINES)
    old = lines[m["line"] - 1]
    if old.strip() != m["original"].strip():
        raise SystemExit(f"{mid}: line {m['line']} of the reference is not the line that was mutated")
    lines[m["line"] - 1] = old[: len(old) - len(old.lstrip())] + m["mutated"].strip()
    return "\n".join(lines)


def M(mid):
    if mid not in _cache:
        _cache[mid] = load(mutant_src(mid), "mut_" + mid)
    return _cache[mid]


O = load(SRC, "orig_lfengine")


def ulps(a, b):
    return abs(a - b) / math.ulp(max(abs(a), abs(b), 1e-300))


# ---------------------------------------------------------------------------------------------------- fixtures
def calpkg(counts=None, pt=None, o_lat=None):
    c = copy.deepcopy(O.example_cal())
    if counts is not None:
        c["pi_train_counts"] = counts
        c["pi_train"] = pt if pt is not None else O.pi_from_counts(counts)
    if o_lat is not None:
        c["o_lat"] = o_lat
    return c


def verdict(mod, cal):
    try:
        mod.check_calibration_package(cal)
        return "accepted"
    except mod.CalibrationError:
        return "CalibrationError"
    except Exception as e:                         # a crash is a different behaviour from a clean refusal
        return type(e).__name__


def cal_cases():
    """Packages on which the validation could behave differently; each has the reason it was chosen."""
    s = (2 ** 40 - 2) / 2 ** 40
    tie_p0 = 2.0 ** -40 + 1e-9
    n9 = 10 ** 9
    return {
        "counts all zero": calpkg([0, 0, 0], [1 / 3] * 3),
        "a zero count with a tiny positive share": calpkg([0, 5, 5], [5e-10, 0.5, 0.5]),
        "share just above one, counts 1e12:1:1": calpkg([10 ** 12, 1, 1], [1.0000000005, 1 / (10 ** 12 + 2), 1 / (10 ** 12 + 2)]),
        "share exactly zero, counts 1:1e9:1e9": calpkg([1, n9, n9], [0.0, n9 / (2 * n9 + 1), n9 / (2 * n9 + 1)]),
        "share error exactly 1e-9 (a float tie)": calpkg([1, 1, 2 ** 40 - 2], [tie_p0, 2.0 ** -40, s - 1e-10]),
        "ordinary valid package": calpkg(),
        "ordinary shares, one of them off by 5e-9": calpkg([2, 1, 1], [0.5 + 5e-9, 0.25, 0.25 - 5e-9]),
    }


# ---------------------------------------------------------------------------------------------------- classes
def c_identical(mid):
    a, b = MUTANTS[mid]["change"].split(" -> ")
    if eval(a) == eval(b):
        return "IDENTICAL", f"`{a}` and `{b}` evaluate to the same number"
    return None


def c_score_cancels(mid):
    rnd = random.Random(7)
    worst = 0.0
    n = 0
    for _ in range(20000):
        lg = [rnd.uniform(-30, 30) for _ in range(3)]
        cal = copy.deepcopy(O.example_cal())
        cal["temperature"]["network"] = rnd.uniform(0.3, 5)
        cal["o_lat"] = rnd.uniform(0.01, 0.99)
        cnt = [rnd.randint(1, 10 ** 6) for _ in range(3)]
        cal["pi_train_counts"], cal["pi_train"] = cnt, O.pi_from_counts(cnt)
        w, act = rnd.uniform(0.0005, 0.5), rnd.choice(("en", "ru"))
        a, b = O.score(lg, act, cal, w), M(mid).score(lg, act, cal, w)
        worst, n = max(worst, abs(a - b)), n + 1
    return ("DIFFERENTIAL" if worst < 1e-9 else "GAP"), (f"norm is subtracted from both log-probabilities so it cancels: score(...) on {n} random inputs "
                                                         f"(logits in [-30, 30], random T, o_lat, class mix, w, both layouts) differs by at most {worst:.2e} nats (rounding)")


def c_cal(mid):
    cases = cal_cases()
    diff = [(k, verdict(O, v), verdict(M(mid), v)) for k, v in cases.items() if verdict(O, v) != verdict(M(mid), v)]
    if mid == "L0280_d03":                         # o_lat upper bound 1.0 -> 2.0, shadowed by the "o_lat >= 1" check
        grid = [0.5, 0.999, 1.0, 1.0000001, 1.5, 2.0, 2.5, 1e9, float("inf"), float("nan"), -1.0, 0.0]
        d = [g for g in grid if verdict(O, calpkg(o_lat=g)) != verdict(M(mid), calpkg(o_lat=g))]
        return ("REDUNDANT" if not d else "GAP"), (f"o_lat in {grid}: same verdict (accepted or CalibrationError) for all, differing: {d}; "
                                                    "the values between 1 and 2 that the mutant lets through the range check are refused by `o_lat >= 1.0` right after it")
    if mid == "L0278_a01":                         # `abs(sum - 1) > 1e-9` against `>=`: the tie needs |sum-1| == 1e-9 exactly
        k = Fraction(1e-9) / Fraction(1, 2 ** 53)
        imposs = k.denominator != 1
        return ("TIE_IMPOSSIBLE" if imposs else "GAP"), ("for a float sum in [0.5, 2] the difference `sum - 1.0` is exact and a multiple of 2**-53; "
                                                         f"1e-9 is {float(k):.6f} such units, not a whole number, so `abs(sum - 1.0) == 1e-9` cannot happen")
    if diff:
        return "GAP", "; ".join(f"{k}: original {a}, mutant {b}" for k, a, b in diff)
    return "REDUNDANT", "no difference on the test packages"


_exact_cache = {}


def exact_root(k, conf):
    """The root of P(Poisson(mu) <= k) = 1 - conf in 60-digit decimal arithmetic (reference value for the rounding comparison)."""
    from decimal import Decimal, getcontext
    getcontext().prec = 60
    key = (k, conf)
    if key not in _exact_cache:
        q = Decimal(1) - Decimal(conf)                       # the float 1 - conf as the engine sees it: Decimal(conf) is exact
        fact = [Decimal(math.factorial(i)) for i in range(k + 1)]

        def cdf(mu):
            return sum((-mu).exp() * mu ** i / fact[i] for i in range(k + 1))
        lo, hi = Decimal(0), Decimal(10 + 10 * k)
        while cdf(hi) > q:
            lo, hi = hi, hi * 2
        for _ in range(200):
            mid = (lo + hi) / 2
            if cdf(mid) > q:
                lo = mid
            else:
                hi = mid
        _exact_cache[key] = (lo + hi) / 2
    return _exact_cache[key]


def c_poisson(mid):
    ks = list(range(0, 41)) + [60, 100, 200]
    confs = [0.01, 0.5, 0.9, 0.95, 0.99, 0.999, 0.99999, 0.999999, 1 - 1e-12]
    mod = M(mid)
    pairs = len(ks) * len(confs)
    rel = max((abs(O.poisson_upper(k, c) - mod.poisson_upper(k, c)) / O.poisson_upper(k, c), k, c) for k in ks for c in confs)
    n_diff = sum(1 for k in ks for c in confs if O.poisson_upper(k, c) != mod.poisson_upper(k, c))
    ex = [(k, c) for k in (0, 1, 2, 3, 5, 10, 20, 40) for c in confs]
    from decimal import Decimal
    err_o = max(abs(Decimal(O.poisson_upper(k, c)) - exact_root(k, c)) / exact_root(k, c) for k, c in ex)
    err_m = max(abs(Decimal(mod.poisson_upper(k, c)) - exact_root(k, c)) / exact_root(k, c) for k, c in ex)
    ok = rel[0] <= 1e-11 and err_m <= 1e-11
    what = {"L0676": "the start of the search interval only decides how many times it is doubled before the bisection",
            "L0677": "`>` against `>=` differs only when the computed cdf equals 1 - conf exactly (a plateau of the rounded cdf)",
            "L0678": "tripling instead of doubling changes only the bracket",
            "L0679": "199 or 201 halvings of an interval that is exhausted after about 60",
            "L0681": "`>` against `>=` differs only when the computed cdf equals 1 - conf exactly (a plateau of the rounded cdf)"}[mid[:5]]
    return ("DIFFERENTIAL" if ok else "GAP"), (f"{what}: {pairs} (k, conf) pairs (k up to 200, conf from 0.01 to 1 - 1e-12): {n_diff} differ, at most {rel[0]:.1e} relative "
                                               f"(k={rel[1]}, conf={rel[2]}); against a 60-digit root on {len(ex)} pairs the original is off by at most {float(err_o):.1e} "
                                               f"and the mutant by at most {float(err_m):.1e} (relative), the resolution of the rounded cdf")


def c_ev1(mid):
    mod = M(mid)
    P = {}
    found = 0
    tested = 0
    for kc in range(0, 121):
        P[kc] = O.poisson_upper(kc)
        for s in range(1, 301):
            n0 = P[kc] * s * 1e4
            for n in (int(n0) - 1, int(n0), int(n0) + 1, int(n0) + 2):
                if n <= 0:
                    continue
                tested += 1
                if P[kc] * s / n == 1e-4:
                    found += 1
    return ("TIE_IMPOSSIBLE" if found == 0 else "GAP"), (f"`bound <= 1e-4` against `< 1e-4` differs only when the float bound equals 1e-4 exactly; "
                                                          f"searched {tested} (clusters 0..120, largest cluster 1..300, n next to P*s/1e-4) combinations: {found} ties")


def c_wb(mid):
    mod = M(mid)
    rnd = random.Random(11)
    diff = n = 0
    zero_diff = 0
    for _ in range(300):
        rows = [[O.BOS] + [rnd.randint(1, 6) for _ in range(rnd.randint(1, 6))] + [O.EOS] for _ in range(rnd.randint(1, 8))]
        for w in (None, [rnd.randint(1, 5) for _ in rows]):
            a, b = O.WittenBell().fit(rows, w), mod.WittenBell().fit(rows, w)
            n += 1
            if a.cnt != b.cnt or abs(a.logp(rows[0]) - b.logp(rows[0])) > 1e-12:
                diff += 1
        wz = [rnd.randint(0, 2) for _ in rows]
        a, b = O.WittenBell().fit(rows, wz), mod.WittenBell().fit(rows, wz)
        zero_diff += a.cnt != b.cnt
    if diff:
        return "GAP", f"{diff} of {n} fits with multiplicities 1 to 5 differ"
    return "OUTSIDE_CONTRACT", (f"with the default min_count = 1 the original keeps every count and the mutant prunes counts below 1; the two differ only when a row has multiplicity 0 "
                                f"(zero counts stay in the table of the original): {n} random fits with multiplicities 1 to 5 are equal, {zero_diff} of 300 fits with some multiplicity 0 differ. "
                                f"Section 8.3 gives a multiplicity of 1 to 5; `fit` does not validate it (finding F-3 of this report)")


def c_relu(mid):
    mod = M(mid)
    rnd = random.Random(5)
    ch, e, k = 3, 2, 3
    n = diff = 0
    for _ in range(400):
        ids = [rnd.randint(0, 3) for _ in range(rnd.randint(1, 6))]
        rv = lambda cnt: [rnd.choice((-1.0, 0.0, 0.0, 1.0)) for _ in range(cnt)]
        W = {"ch": ch, "e": e, "emb": rv(4 * e), "convs": [(rv(ch * e * k), rv(ch), e, k), (rv(ch * ch * k), rv(ch), ch, k)],
             "hw": rv(3 * 2 * ch), "hb": rv(3)}
        a, b = O.lfw_forward(W, ids), mod.lfw_forward(W, ids)
        n += 1
        diff += a != b
    return ("DIFFERENTIAL" if diff == 0 else "GAP"), (f"s >= 0 against s > 0 differs only for s == 0 (both give 0.0) or s == -0.0 (a signed zero); "
                                                      f"{n} random small networks with weights in {{-1, 0, 1}} (many exact zeros) give equal logits")


GROUPS = [c_identical]


def classify(mid):
    r = c_identical(mid) if MUTANTS[mid]["op"] == "d" else None
    if r:
        return r
    ln = MUTANTS[mid]["line"]
    for line_range, f in ((range(212, 213), c_score_cancels), (range(267, 281), c_cal), (range(676, 682), c_poisson),
                          (range(705, 706), c_ev1), (range(727, 728), c_wb), (range(967, 968), c_relu)):
        if ln in line_range:
            r = f(mid)
            if r:
                return r
    return "UNCLASSIFIED", "no rule"


if __name__ == "__main__":
    rows = []
    for mid in SURV:
        cls, why = classify(mid)
        rows.append({"id": mid, "line": MUTANTS[mid]["line"], "change": MUTANTS[mid]["change"], "class": cls, "evidence": why})
    cnt = {}
    for r in rows:
        cnt[r["class"]] = cnt.get(r["class"], 0) + 1
    for r in rows:
        print(f"{r['id']:10s} {r['class']:17s} {r['evidence']}")
    print()
    print("survivors:", len(rows), " by class:", json.dumps(cnt, sort_keys=True))
    if OUT:
        json.dump({"survivors": len(rows), "classes": cnt, "rows": rows}, open(OUT, "w"), indent=1, ensure_ascii=False)
    sys.exit(0 if "UNCLASSIFIED" not in cnt else 1)
