#!/usr/bin/env python3
"""L6: behaviour of the EV-1 pass rule (sections 11.3 and 20.9) under clustered errors.

Pre-registered in layout-corrector/spec/FIX_AND_AUDIT_PLAN_v3.1.md (section "L6: предрегистрация") BEFORE the first run.
Nothing below was tuned after a result was seen. This file states the reading of the plan where the plan is short:

  * rule under test = ev1_pass() of the reference engine (lfengine.py, 20.9), imported, not re-implemented;
  * 10,000 runs per scenario; run i uses numpy default_rng(1000 + i);
  * true rate r in {2e-4, 1e-4, 5e-5, 2e-5}; users U in {20, 50, 200}; clustering in {none, moderate, strong};
  * n = 100,000 correct words; documents per user D = ceil(120 / U), so documents >= 100 for every U;
  * words per user and per document are log-normal (sigma 0.7 and 0.5) with the caps of 8.5 (user <= 10%, document <= 2%
    of the words, applied by clipping and renormalising until stable);
  * errors per document ~ Poisson(r * words * f_user * f_doc), f_* gamma distributed with mean 1:
      none      f_user = f_doc = 1
      moderate  dispersion alpha = 2 (var = mu + alpha mu^2): gamma shape 1/2 at user AND document level
      strong    alpha = 10 (shape 1/10) at document level; at user level ceil(2% of U) users are "heavy" and produce in
                expectation 50% of the errors (their factor is 0.5 U / n_heavy, the others' 0.5 U / (U - n_heavy), both
                scaled so that the word-weighted mean is 1)
  * criteria (fixed in advance):
      false acceptance: at r = 2e-4 the acceptance share is <= 5% and its Clopper-Pearson 95% upper bound <= 7%,
                        in EVERY clustering scenario and for every U;
      power:            at r = 2e-5, moderate clustering, U >= 50, n = 100,000 the acceptance share is >= 80%;
                        if not met, the smallest n of the grid with share >= 80% is reported (the grid does not change the rule);
      r = 1e-4 and r = 5e-5 are diagnostic: the shares are published, there is no criterion.
Usage: python3 L6_ev1_simulation.py [runs]   (default 10000)   writes L6_ev1_simulation.json and prints a markdown table.
"""
import json
import math
import os
import sys
import time
from functools import lru_cache

import numpy as np
from scipy.stats import beta

sys.path.insert(0, os.environ.get("LF_REFERENCE", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reference")))
import lfengine as E  # noqa: E402

RUNS = int(sys.argv[1]) if len(sys.argv) > 1 else 10_000
RATES = (2e-4, 1e-4, 5e-5, 2e-5)
USERS = (20, 50, 200)
CLUSTERING = ("none", "moderate", "strong")
N = 100_000
N_GRID = (100_000, 150_000, 200_000, 300_000, 500_000)


@lru_cache(maxsize=None)
def _pu(c: int) -> float:
    return E.poisson_upper(c)


def accepts(sizes, n, users, docs) -> bool:
    """ev1_pass of the reference engine with a cached Poisson limit: same arithmetic, faster. Cross-checked below."""
    k = sum(sizes)
    if not (n >= 100_000 and users >= 20 and docs >= 100):
        return False
    if k / n > 4.8e-5:
        return False
    bound = (_pu(0) / n) if k == 0 else _pu(len(sizes)) * max(sizes) / n
    return bound <= 1e-4


def capped_weights(rng, count, sigma, cap):
    w = rng.lognormal(0.0, sigma, count)
    w /= w.sum()
    for _ in range(100):
        over = w > cap
        if not over.any():
            break
        excess = (w[over] - cap).sum()
        w[over] = cap
        under = ~over
        w[under] += excess * w[under] / w[under].sum()
    return w


def one_run(i, rate, users, mode, n):
    rng = np.random.default_rng(1000 + i)
    d_per_user = math.ceil(120 / users)
    wu = capped_weights(rng, users, 0.7, 0.10)
    wd = np.empty((users, d_per_user))
    for u in range(users):
        wd[u] = wu[u] * capped_weights(rng, d_per_user, 0.5, 1.0)
    # the document cap of 8.5 (2% of all words) on the product
    wd = np.minimum(wd, 0.02)
    wd /= wd.sum()
    exact = wd * n
    words = np.floor(exact).astype(np.int64)
    words[words < 1] = 1
    deficit = n - int(words.sum())          # largest-remainder apportionment: n is exactly n, not a little less
    if deficit > 0:
        order = np.argsort(-(exact - np.floor(exact)), axis=None)[:deficit]
        words.flat[order] += 1
    n_eff = int(words.sum())
    lam = rate * words.astype(float)
    if mode == "moderate":
        fu = rng.gamma(0.5, 2.0, users)
        fd = rng.gamma(0.5, 2.0, words.shape)
    elif mode == "strong":
        heavy = max(1, math.ceil(0.02 * users))
        fu = np.full(users, 0.5 * users / (users - heavy))
        fu[:heavy] = 0.5 * users / heavy
        uw = words.sum(axis=1) / n_eff
        fu = fu / float((fu * uw).sum())
        fd = rng.gamma(0.1, 10.0, words.shape)
    else:
        fu = np.ones(users)
        fd = np.ones(words.shape)
    lam = lam * fu[:, None] * fd
    errors = rng.poisson(lam)
    sizes = [int(x) for x in errors[errors > 0]]
    return accepts(sizes, n_eff, users, users * d_per_user), sizes, n_eff, users * d_per_user


def cp(k, n, conf=0.95):
    a = (1 - conf) / 2
    lo = 0.0 if k == 0 else beta.ppf(a, k, n - k + 1)
    hi = 1.0 if k == n else beta.ppf(1 - a, k + 1, n - k)
    return float(lo), float(hi)


def crosscheck():
    """The cached rule equals ev1_pass of the engine on 2,000 random cases."""
    rng = np.random.default_rng(7)
    for _ in range(2000):
        k = int(rng.integers(0, 8))
        fc = [(f"u{int(rng.integers(0, 4))}", f"d{int(rng.integers(0, 3))}") for _ in range(k)]
        sizes = {}
        for key in fc:
            sizes[key] = sizes.get(key, 0) + 1
        n = int(rng.choice([99_999, 100_000, 150_000, 300_000]))
        users = int(rng.choice([19, 20, 50]))
        docs = int(rng.choice([99, 100, 150]))
        assert E.ev1_pass(fc, n, users, docs) == accepts(list(sizes.values()), n, users, docs), (fc, n, users, docs)


def main():
    crosscheck()
    t0 = time.time()
    out = {"runs": RUNS, "n": N, "scenarios": [], "power_n_grid": []}
    for rate in RATES:
        for users in USERS:
            for mode in CLUSTERING:
                acc = 0
                kmean = 0.0
                for i in range(RUNS):
                    ok, sizes, _, _ = one_run(i, rate, users, mode, N)
                    acc += ok
                    kmean += sum(sizes)
                lo, hi = cp(acc, RUNS)
                out["scenarios"].append({"rate": rate, "users": users, "clustering": mode, "accepted": acc, "share": acc / RUNS,
                                         "cp_lo": lo, "cp_hi": hi, "mean_errors": kmean / RUNS})
    # criteria, evaluated exactly as pre-registered
    fa = [s for s in out["scenarios"] if s["rate"] == 2e-4]
    out["false_acceptance_ok"] = all(s["share"] <= 0.05 and s["cp_hi"] <= 0.07 for s in fa)
    pw = [s for s in out["scenarios"] if s["rate"] == 2e-5 and s["clustering"] == "moderate" and s["users"] >= 50]
    out["power_ok"] = all(s["share"] >= 0.80 for s in pw)
    if not out["power_ok"]:
        for users in (50, 200):
            for n in N_GRID:
                acc = sum(one_run(i, 2e-5, users, "moderate", n)[0] for i in range(RUNS))
                lo, hi = cp(acc, RUNS)
                out["power_n_grid"].append({"users": users, "n": n, "share": acc / RUNS, "cp_lo": lo, "cp_hi": hi})
    out["seconds"] = round(time.time() - t0, 1)
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "L6_ev1_simulation.json"), "w") as f:
        json.dump(out, f, indent=1)
    print("| true rate | users | clustering | mean errors | acceptance share | 95% CP interval |")
    print("|---|---|---|---|---|---|")
    for s in out["scenarios"]:
        print(f"| {s['rate']:.0e} | {s['users']} | {s['clustering']} | {s['mean_errors']:.1f} | {100*s['share']:.2f}% | "
              f"{100*s['cp_lo']:.2f}% to {100*s['cp_hi']:.2f}% |")
    print(f"\nfalse acceptance criterion (r = 2e-4, share <= 5%, CP upper <= 7%, all scenarios): {out['false_acceptance_ok']}")
    print(f"power criterion (r = 2e-5, moderate, users >= 50, n = 100,000, share >= 80%): {out['power_ok']}")
    for g in out["power_n_grid"]:
        print(f"  n = {g['n']:>7} users = {g['users']:>3}: share {100*g['share']:.2f}% ({100*g['cp_lo']:.2f} to {100*g['cp_hi']:.2f})")
    print(f"runs per scenario {RUNS}, {out['seconds']} s")


if __name__ == "__main__":
    main()
