# L3 mutation report: lfengine.py (reference engine), mutants from line 173 (`# ==== 20.5`) to line 1497

Source: `reference/lfengine.py` of the audited commit, copied to `base/` (SHA-256 4af41c76efefbc7d48dc26c696f15822dd447d726cc02813e17fb0673c3eae5f; conformance.py ddcc300c3fca57983bbbe6c411c9bfd1368f3f11eb85e64c8d28e2f0e124e580). Baseline: `python3 conformance.py 20000` prints OK; `vectors.py` matches `vectors_out.json`; `test_ref.py` passes. Each mutant runs `timeout 150 python3 conformance.py 20000` in its own directory.

## Counts

| quantity | value |
|---|---|
| generated (all operators, before compile check) | 795 |
| did not compile (discarded) | 0 |
| valid mutants | 795 |
| run | 795 (sampled: no, all valid mutants) |
| killed (incl. timeouts) | 760 |
| of which TIMEOUT | 1 |
| survived | 35 |
| survived-but-vectors-differ (subset of survived) | 0 |
| survivors where test_ref.py also fails | 0 |
| **kill rate = killed / run** | **95.6%** (760/795) |

## Per operator

| op | kind | generated | not compiling | valid | run | killed | survived |
|---|---|---|---|---|---|---|---|
| a | comparison | 142 | 0 | 142 | 142 | 136 | 6 |
| b | boolean | 112 | 0 | 112 | 112 | 112 | 0 |
| c | integer literal | 290 | 0 | 290 | 290 | 283 | 7 |
| d | float literal | 80 | 0 | 80 | 80 | 59 | 21 |
| e | statement deletion | 105 | 0 | 105 | 105 | 104 | 1 |
| f | True/False | 66 | 0 | 66 | 66 | 66 | 0 |

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

### `Engine.on_event` (1)

| id | line | op | original | mutated | flags |
|---|---|---|---|---|---|
| L0611_e01 | 611 | e | `self._drop_snapshot()` | `pass` |  |

### `poisson_upper` (13)

| id | line | op | original | mutated | flags |
|---|---|---|---|---|---|
| L0727_d01 | 727 | d | `if not (isinstance(k, int) and not isinstance(k, bool) and k >= 0 and 0.0 < conf < 1.0):` | `if not (isinstance(k, int) and not isinstance(k, bool) and k >= 0 and (0.0*2) < conf < 1.0):` |  |
| L0727_d02 | 727 | d | `if not (isinstance(k, int) and not isinstance(k, bool) and k >= 0 and 0.0 < conf < 1.0):` | `if not (isinstance(k, int) and not isinstance(k, bool) and k >= 0 and (0.0/2) < conf < 1.0):` |  |
| L0733_d01 | 733 | d | `lo, hi = 0.0, 10.0 + 10.0 * k` | `lo, hi = (0.0*2), 10.0 + 10.0 * k` |  |
| L0733_d02 | 733 | d | `lo, hi = 0.0, 10.0 + 10.0 * k` | `lo, hi = (0.0/2), 10.0 + 10.0 * k` |  |
| L0733_d03 | 733 | d | `lo, hi = 0.0, 10.0 + 10.0 * k` | `lo, hi = 0.0, (10.0*2) + 10.0 * k` |  |
| L0733_d04 | 733 | d | `lo, hi = 0.0, 10.0 + 10.0 * k` | `lo, hi = 0.0, (10.0/2) + 10.0 * k` |  |
| L0733_d05 | 733 | d | `lo, hi = 0.0, 10.0 + 10.0 * k` | `lo, hi = 0.0, 10.0 + (10.0*2) * k` |  |
| L0733_d06 | 733 | d | `lo, hi = 0.0, 10.0 + 10.0 * k` | `lo, hi = 0.0, 10.0 + (10.0/2) * k` |  |
| L0734_a01 | 734 | a | `while cdf(hi) > 1 - conf:                      # the interval must hold the limit for every confidence` | `while cdf(hi) >= 1 - conf:                      # the interval must hold the limit for every confidence` |  |
| L0735_c01 | 735 | c | `lo, hi = hi, hi * 2` | `lo, hi = hi, hi * (2+1)` |  |
| L0736_c01 | 736 | c | `for _ in range(200):` | `for _ in range((200+1)):` |  |
| L0736_c02 | 736 | c | `for _ in range(200):` | `for _ in range((200-1)):` |  |
| L0738_a01 | 738 | a | `if cdf(mid) > 1 - conf:` | `if cdf(mid) >= 1 - conf:` |  |

### `ev1_pass` (1)

| id | line | op | original | mutated | flags |
|---|---|---|---|---|---|
| L0762_a01 | 762 | a | `and ev1_bound(false_corrections, n_negatives) <= 1e-4)` | `and ev1_bound(false_corrections, n_negatives) < 1e-4)` |  |

### `WittenBell.fit` (2)

| id | line | op | original | mutated | flags |
|---|---|---|---|---|---|
| L0797_a01 | 797 | a | `if self.min_count > 1:                              # prune BEFORE the totals are derived` | `if self.min_count >= 1:                              # prune BEFORE the totals are derived` |  |
| L0797_c02 | 797 | c | `if self.min_count > 1:                              # prune BEFORE the totals are derived` | `if self.min_count > (1-1):                              # prune BEFORE the totals are derived` |  |

### `WittenBell.logp` (2)

| id | line | op | original | mutated | flags |
|---|---|---|---|---|---|
| L0808_d01 | 808 | d | `total = 0.0` | `total = (0.0*2)` |  |
| L0808_d02 | 808 | d | `total = 0.0` | `total = (0.0/2)` |  |

### `lfb_logp` (2)

| id | line | op | original | mutated | flags |
|---|---|---|---|---|---|
| L0915_d01 | 915 | d | `total = 0.0` | `total = (0.0*2)` |  |
| L0915_d02 | 915 | d | `total = 0.0` | `total = (0.0/2)` |  |

### `lfw_forward` (3)

| id | line | op | original | mutated | flags |
|---|---|---|---|---|---|
| L1037_a01 | 1037 | a | `row.append(s if s > 0 else 0.0)` | `row.append(s if s >= 0 else 0.0)` |  |
| L1037_d01 | 1037 | d | `row.append(s if s > 0 else 0.0)` | `row.append(s if s > 0 else (0.0*2))` |  |
| L1037_d02 | 1037 | d | `row.append(s if s > 0 else 0.0)` | `row.append(s if s > 0 else (0.0/2))` |  |

## Notes on how mutants were built

- Operators were applied to code tokens only (strings, docstrings and comments are never mutated). Lines with no code tokens (comment-only, docstring, blank, import) are skipped.
- Integer and float literals are wrapped in parentheses, e.g. `2` -> `(2+1)`, `0.5` -> `(0.5*2)`, so the replacement is the whole expression, not a precedence change. Literals in slices (`[1:]`) with value 1 are skipped; values 47, 94, 95, 96, 97 are skipped.
- The `not` rule matches `not` after `if` or `elif` (the text `if not ` occurs inside `elif not `) and `not in`. Other `not` uses (e.g. `return not`, `and not`, `while not`) are not mutated, following the list in the task.
- Statement deletion covers single-line statements that are `self.<name>(...)` calls, `self.<name> = ...` assignments and `return None`. An annotated assignment `self.x: T = ...` is not of that form and was not mutated.
- Enclosing function names come from the AST ranges of def/class statements (innermost one), which is the same as scanning upward for the nearest enclosing def/class.

