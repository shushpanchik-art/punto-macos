# L3 mutation report: lfengine.py (reference engine), mutants from line 173 (`# ==== 20.5`) to line 1393

Source: `reference/lfengine.py` of the audited commit, copied to `base/` (SHA-256 bf6082dc1fafafd7d076daae2d70fdc08a674d7a661be4a2bf3f79b2d62b5cae; conformance.py 132efe38baad8f3c8e99dc7baaeea79261f1f61037f120e7cef3e19bdddab3a6). Baseline: `python3 conformance.py 20000` prints OK; `vectors.py` matches `vectors_out.json`; `test_ref.py` passes. Each mutant runs `timeout 150 python3 conformance.py 20000` in its own directory.

## Counts

| quantity | value |
|---|---|
| generated (all operators, before compile check) | 718 |
| did not compile (discarded) | 0 |
| valid mutants | 718 |
| run | 718 (sampled: no, all valid mutants) |
| killed (incl. timeouts) | 684 |
| of which TIMEOUT | 1 |
| survived | 34 |
| survived-but-vectors-differ (subset of survived) | 0 |
| survivors where test_ref.py also fails | 0 |
| **kill rate = killed / run** | **95.3%** (684/718) |

## Per operator

| op | kind | generated | not compiling | valid | run | killed | survived |
|---|---|---|---|---|---|---|---|
| a | comparison | 125 | 0 | 125 | 125 | 119 | 6 |
| b | boolean | 96 | 0 | 96 | 96 | 96 | 0 |
| c | integer literal | 278 | 0 | 278 | 278 | 271 | 7 |
| d | float literal | 80 | 0 | 80 | 80 | 59 | 21 |
| e | statement deletion | 82 | 0 | 82 | 82 | 82 | 0 |
| f | True/False | 57 | 0 | 57 | 57 | 57 | 0 |

## Survivors by enclosing function

Flags: `VECTORS_DIFFER` = vectors.py output differs from vectors_out.json (label SURVIVED_BUT_VECTORS_DIFFER); `test_ref FAILS` = test_ref.py exits non-zero.

### `score` (3)

| id | line | op | original | mutated | flags |
|---|---|---|---|---|---|
| L0212_c01 | 212 | c | `norm = _lse2(_lse2(lp[0], lp[1]), lp[2])` | `norm = _lse2(_lse2(lp[0], lp[(1+1)]), lp[2])` |  |
| L0212_c02 | 212 | c | `norm = _lse2(_lse2(lp[0], lp[1]), lp[2])` | `norm = _lse2(_lse2(lp[0], lp[(1-1)]), lp[2])` |  |
| L0212_c04 | 212 | c | `norm = _lse2(_lse2(lp[0], lp[1]), lp[2])` | `norm = _lse2(_lse2(lp[0], lp[1]), lp[(2-1)])` |  |

### `check_calibration_package` (8)

| id | line | op | original | mutated | flags |
|---|---|---|---|---|---|
| L0267_d01 | 267 | d | `_finite(cal["temperature"][kind], f"temperature[{kind}]", 0.0, 20.0, lo_open=True)` | `_finite(cal["temperature"][kind], f"temperature[{kind}]", (0.0*2), 20.0, lo_open=True)` |  |
| L0267_d02 | 267 | d | `_finite(cal["temperature"][kind], f"temperature[{kind}]", 0.0, 20.0, lo_open=True)` | `_finite(cal["temperature"][kind], f"temperature[{kind}]", (0.0/2), 20.0, lo_open=True)` |  |
| L0275_d01 | 275 | d | `_finite(p, f"pi_train[{i}]", 0.0, 1.0, lo_open=True)` | `_finite(p, f"pi_train[{i}]", (0.0*2), 1.0, lo_open=True)` |  |
| L0275_d02 | 275 | d | `_finite(p, f"pi_train[{i}]", 0.0, 1.0, lo_open=True)` | `_finite(p, f"pi_train[{i}]", (0.0/2), 1.0, lo_open=True)` |  |
| L0278_a01 | 278 | a | `if abs(sum(pt) - 1.0) > 1e-9:` | `if abs(sum(pt) - 1.0) >= 1e-9:` |  |
| L0280_d01 | 280 | d | `_finite(cal["o_lat"], "o_lat", 0.0, 1.0, lo_open=True)` | `_finite(cal["o_lat"], "o_lat", (0.0*2), 1.0, lo_open=True)` |  |
| L0280_d02 | 280 | d | `_finite(cal["o_lat"], "o_lat", 0.0, 1.0, lo_open=True)` | `_finite(cal["o_lat"], "o_lat", (0.0/2), 1.0, lo_open=True)` |  |
| L0280_d03 | 280 | d | `_finite(cal["o_lat"], "o_lat", 0.0, 1.0, lo_open=True)` | `_finite(cal["o_lat"], "o_lat", 0.0, (1.0*2), lo_open=True)` |  |

### `poisson_upper` (13)

| id | line | op | original | mutated | flags |
|---|---|---|---|---|---|
| L0670_d01 | 670 | d | `if not (isinstance(k, int) and not isinstance(k, bool) and k >= 0 and 0.0 < conf < 1.0):` | `if not (isinstance(k, int) and not isinstance(k, bool) and k >= 0 and (0.0*2) < conf < 1.0):` |  |
| L0670_d02 | 670 | d | `if not (isinstance(k, int) and not isinstance(k, bool) and k >= 0 and 0.0 < conf < 1.0):` | `if not (isinstance(k, int) and not isinstance(k, bool) and k >= 0 and (0.0/2) < conf < 1.0):` |  |
| L0676_d01 | 676 | d | `lo, hi = 0.0, 10.0 + 10.0 * k` | `lo, hi = (0.0*2), 10.0 + 10.0 * k` |  |
| L0676_d02 | 676 | d | `lo, hi = 0.0, 10.0 + 10.0 * k` | `lo, hi = (0.0/2), 10.0 + 10.0 * k` |  |
| L0676_d03 | 676 | d | `lo, hi = 0.0, 10.0 + 10.0 * k` | `lo, hi = 0.0, (10.0*2) + 10.0 * k` |  |
| L0676_d04 | 676 | d | `lo, hi = 0.0, 10.0 + 10.0 * k` | `lo, hi = 0.0, (10.0/2) + 10.0 * k` |  |
| L0676_d05 | 676 | d | `lo, hi = 0.0, 10.0 + 10.0 * k` | `lo, hi = 0.0, 10.0 + (10.0*2) * k` |  |
| L0676_d06 | 676 | d | `lo, hi = 0.0, 10.0 + 10.0 * k` | `lo, hi = 0.0, 10.0 + (10.0/2) * k` |  |
| L0677_a01 | 677 | a | `while cdf(hi) > 1 - conf:                      # the interval must hold the limit for every confidence` | `while cdf(hi) >= 1 - conf:                      # the interval must hold the limit for every confidence` |  |
| L0678_c01 | 678 | c | `lo, hi = hi, hi * 2` | `lo, hi = hi, hi * (2+1)` |  |
| L0679_c01 | 679 | c | `for _ in range(200):` | `for _ in range((200+1)):` |  |
| L0679_c02 | 679 | c | `for _ in range(200):` | `for _ in range((200-1)):` |  |
| L0681_a01 | 681 | a | `if cdf(mid) > 1 - conf:` | `if cdf(mid) >= 1 - conf:` |  |

### `ev1_pass` (1)

| id | line | op | original | mutated | flags |
|---|---|---|---|---|---|
| L0705_a01 | 705 | a | `and ev1_bound(false_corrections, n_negatives) <= 1e-4)` | `and ev1_bound(false_corrections, n_negatives) < 1e-4)` |  |

### `WittenBell.fit` (2)

| id | line | op | original | mutated | flags |
|---|---|---|---|---|---|
| L0740_a01 | 740 | a | `if self.min_count > 1:                              # prune BEFORE the totals are derived` | `if self.min_count >= 1:                              # prune BEFORE the totals are derived` |  |
| L0740_c02 | 740 | c | `if self.min_count > 1:                              # prune BEFORE the totals are derived` | `if self.min_count > (1-1):                              # prune BEFORE the totals are derived` |  |

### `WittenBell.logp` (2)

| id | line | op | original | mutated | flags |
|---|---|---|---|---|---|
| L0751_d01 | 751 | d | `total = 0.0` | `total = (0.0*2)` |  |
| L0751_d02 | 751 | d | `total = 0.0` | `total = (0.0/2)` |  |

### `lfb_logp` (2)

| id | line | op | original | mutated | flags |
|---|---|---|---|---|---|
| L0858_d01 | 858 | d | `total = 0.0` | `total = (0.0*2)` |  |
| L0858_d02 | 858 | d | `total = 0.0` | `total = (0.0/2)` |  |

### `lfw_forward` (3)

| id | line | op | original | mutated | flags |
|---|---|---|---|---|---|
| L0980_a01 | 980 | a | `row.append(s if s > 0 else 0.0)` | `row.append(s if s >= 0 else 0.0)` |  |
| L0980_d01 | 980 | d | `row.append(s if s > 0 else 0.0)` | `row.append(s if s > 0 else (0.0*2))` |  |
| L0980_d02 | 980 | d | `row.append(s if s > 0 else 0.0)` | `row.append(s if s > 0 else (0.0/2))` |  |

## Notes on how mutants were built

- Operators were applied to code tokens only (strings, docstrings and comments are never mutated). Lines with no code tokens (comment-only, docstring, blank, import) are skipped.
- Integer and float literals are wrapped in parentheses, e.g. `2` -> `(2+1)`, `0.5` -> `(0.5*2)`, so the replacement is the whole expression, not a precedence change. Literals in slices (`[1:]`) with value 1 are skipped; values 47, 94, 95, 96, 97 are skipped.
- The `not` rule matches `not` after `if` or `elif` (the text `if not ` occurs inside `elif not `) and `not in`. Other `not` uses (e.g. `return not`, `and not`, `while not`) are not mutated, following the list in the task.
- Statement deletion covers single-line statements that are `self.<name>(...)` calls, `self.<name> = ...` assignments and `return None`. An annotated assignment `self.x: T = ...` is not of that form and was not mutated.
- Enclosing function names come from the AST ranges of def/class statements (innermost one), which is the same as scanning upward for the nearest enclosing def/class.

