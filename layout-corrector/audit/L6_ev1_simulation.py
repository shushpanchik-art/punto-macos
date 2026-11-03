#!/usr/bin/env python3
"""L6: behaviour of the EV-1 pass rule (sections 11.3 and 20.9) under clustered errors.

Pre-registered in layout-corrector/spec/FIX_AND_AUDIT_PLAN_v3.1.md (section "L6: предрегистрация") BEFORE the first run.
Nothing below was tuned after a result was seen. This file states the reading of the plan where the plan is short:

  * rule under test = ev1_pass() of the reference engine (lfengine.py, 20.9), imported and CALLED on every run (the only
    change is that poisson_upper, a pure function, is memoised; its values are compared with the original below);
  * 10,000 runs per scenario; run i uses numpy default_rng(1000 + i);
  * true rate r in {2e-4, 1e-4, 5e-5, 2e-5}; users U in {20, 50, 200}; clustering in {none, moderate, strong};
  * n = 100,000 correct words; documents per user D = ceil(120 / U), so documents >= 100 for every U;
  * words per user and per document are log-normal (sigma 0.7 and 0.5) with the caps of 8.5 (user <= 10%, document <= 2%
    of the words). The caps are enforced by fit_caps(): clip, then give the missing mass only to documents that still
    have room (room = distance to the document cap and the document's share of the user's room), repeated until the
    total is 1. Every run then checks, on the INTEGER word counts, that no user has more than 10% and no document more
    than 2% of the words, and the maxima are written to the result file;
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
Deviation log. Run 1 (commit 63c258d) clipped the documents at 2% and then renormalised by the sum, which can push
a document above 2% and a user above 10% again (found by an external review, 2026-11-03: in 10,000 seeds the document cap
was exceeded in 8,910 to 10,000 runs and the user cap in about 25% of the runs at 20 users). That generator was replaced;
all runs below were repeated and the old result file was overwritten. Criteria and scenarios are unchanged. Run 1 also
used its own copy of the rule (cross-checked on 2,000 random cases); this version calls ev1_pass itself.
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


DOC_CAP, USER_CAP = 0.02, 0.10
_poisson_upper_original = E.poisson_upper
E.poisson_upper = lru_cache(maxsize=None)(_poisson_upper_original)       # pure function: the same values, computed once


def lognormal_weights(rng, count, sigma):
    w = rng.lognormal(0.0, sigma, count)
    return w / w.sum()


def fit_caps(w, doc_cap=DOC_CAP, user_cap=USER_CAP):
    """w: users x documents, sums to 1. Returns weights that sum to 1 with every document <= doc_cap and every user
    <= user_cap (continuous check at the end); raises when the caps cannot be met."""
    users, docs = w.shape
    if users * docs * doc_cap < 1.0 or users * user_cap < 1.0:
        raise RuntimeError("the caps cannot be met for this shape")
    w = w / w.sum()
    for _ in range(100_000):
        w = np.minimum(w, doc_cap)
        us = w.sum(axis=1)
        w = w * np.minimum(1.0, user_cap / us)[:, None]
        deficit = 1.0 - float(w.sum())
        if deficit <= 1e-14:
            break
        room = np.maximum(np.minimum(doc_cap - w, ((user_cap - w.sum(axis=1)) / docs)[:, None]), 0.0)
        total = float(room.sum())
        if total <= 0.0:
            raise RuntimeError("no room left")
        w = w + room * min(1.0, deficit / total)
    else:
        raise RuntimeError("fit_caps did not converge")
    if not (abs(float(w.sum()) - 1.0) < 1e-9 and float(w.max()) <= doc_cap * (1 + 1e-12)
            and float(w.sum(axis=1).max()) <= user_cap * (1 + 1e-12)):
        raise RuntimeError("fit_caps broke a cap")
    return w


def apportion(w, n):
    """Integer word counts of every document: largest remainder, never above the caps in words, every document >= 1."""
    exact = w * n
    words = np.maximum(np.floor(exact).astype(np.int64), 1)
    doc_max, user_max = int(DOC_CAP * n), int(USER_CAP * n)
    deficit = n - int(words.sum())
    if deficit > 0:
        user_sum = words.sum(axis=1)
        for flat in np.argsort(-(exact - np.floor(exact)), axis=None, kind="stable"):
            u = int(flat) // words.shape[1]
            if words.flat[flat] + 1 <= doc_max and user_sum[u] + 1 <= user_max:
                words.flat[flat] += 1
                user_sum[u] += 1
                deficit -= 1
                if deficit == 0:
                    break
    if deficit != 0:
        raise RuntimeError("apportionment failed")
    return words


def one_run(i, rate, users, mode, n):
    rng = np.random.default_rng(1000 + i)
    d_per_user = math.ceil(120 / users)
    wu = lognormal_weights(rng, users, 0.7)
    split = np.stack([lognormal_weights(rng, d_per_user, 0.5) for _ in range(users)])
    wd = fit_caps(wu[:, None] * split)
    words = apportion(wd, n)
    n_eff = int(words.sum())
    shares = (float(words.sum(axis=1).max()) / n_eff, float(words.max()) / n_eff)
    if shares[0] > USER_CAP or shares[1] > DOC_CAP:
        raise RuntimeError(f"cap violated in words: user {shares[0]}, document {shares[1]}")
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
    fc = [(f"u{u}", f"d{d}") for u, d in zip(*np.nonzero(errors)) for _ in range(int(errors[u, d]))]
    sizes = [int(x) for x in errors[errors > 0]]
    return E.ev1_pass(fc, n_eff, users, users * d_per_user), sizes, n_eff, shares


def cp(k, n, conf=0.95):
    a = (1 - conf) / 2
    lo = 0.0 if k == 0 else beta.ppf(a, k, n - k + 1)
    hi = 1.0 if k == n else beta.ppf(1 - a, k + 1, n - k)
    return float(lo), float(hi)


def crosscheck():
    """The memoised Poisson limit equals the original function (the rule itself is not re-implemented)."""
    for k in range(0, 40):
        assert E.poisson_upper(k) == _poisson_upper_original(k), k


def main():
    crosscheck()
    t0 = time.time()
    out = {"runs": RUNS, "n": N, "scenarios": [], "power_n_grid": [], "max_user_share": 0.0, "max_doc_share": 0.0,
           "runs_checked": 0, "cap_violations": 0}
    for rate in RATES:
        for users in USERS:
            for mode in CLUSTERING:
                acc = 0
                kmean = 0.0
                for i in range(RUNS):
                    ok, sizes, _, shares = one_run(i, rate, users, mode, N)
                    out["max_user_share"] = max(out["max_user_share"], shares[0])
                    out["max_doc_share"] = max(out["max_doc_share"], shares[1])
                    out["runs_checked"] += 1
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
    print(f"caps checked on integer word counts in {out['runs_checked']} runs: largest user share {100*out['max_user_share']:.3f}%, "
          f"largest document share {100*out['max_doc_share']:.3f}%, violations {out['cap_violations']}")
    print(f"runs per scenario {RUNS}, {out['seconds']} s")


if __name__ == "__main__":
    main()
