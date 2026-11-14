# L3 mutation report: lfengine.py (reference engine), mutants from line 173 (`# ==== 20.5`) to line 1788

Source: `reference/lfengine.py` of the audited commit, copied to `base/` (SHA-256 e83eccdacfa3574ddd9b2d1a936057b0e4f1da916129256754d61420fbc03e30; conformance.py 2c0239795d96be69d82094724377037531c8c5814ebc090d339fcc7e4a0b56b9). Baseline: `python3 conformance.py 20000` prints OK; `vectors.py` matches `vectors_out.json`; `test_ref.py` passes. Each mutant runs `timeout 150 python3 conformance.py 20000` in its own directory.

## Counts

| quantity | value |
|---|---|
| generated (all operators, before compile check) | 991 |
| did not compile (discarded) | 0 |
| valid mutants | 991 |
| run | 991 (sampled: no, all valid mutants) |
| killed (incl. timeouts) | 951 |
| of which TIMEOUT | 1 |
| survived | 40 |
| survived-but-vectors-differ (subset of survived) | 0 |
| survivors where test_ref.py also fails | 0 |
| **kill rate = killed / run** | **96.0%** (951/991) |

## Per operator

| op | kind | generated | not compiling | valid | run | killed | survived |
|---|---|---|---|---|---|---|---|
| a | comparison | 193 | 0 | 193 | 193 | 187 | 6 |
| b | boolean | 166 | 0 | 166 | 166 | 166 | 0 |
| c | integer literal | 318 | 0 | 318 | 318 | 311 | 7 |
| d | float literal | 80 | 0 | 80 | 80 | 59 | 21 |
| e | statement deletion | 142 | 0 | 142 | 142 | 136 | 6 |
| f | True/False | 92 | 0 | 92 | 92 | 92 | 0 |

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

### `Engine.undo_outcome` (2)

| id | line | op | original | mutated | flags |
|---|---|---|---|---|---|
| L0628_e01 | 628 | e | `self.credit = 0` | `pass` |  |
| L0629_e01 | 629 | e | `self._drop_snapshot()` | `pass` |  |

### `Engine.toggle_outcome` (2)

| id | line | op | original | mutated | flags |
|---|---|---|---|---|---|
| L0686_e01 | 686 | e | `self.credit = 0` | `pass` |  |
| L0687_e01 | 687 | e | `self.manual = None` | `pass` |  |

### `Engine._quarantine` (1)

| id | line | op | original | mutated | flags |
|---|---|---|---|---|---|
| L0693_e01 | 693 | e | `self._drop_manual()` | `pass` |  |

### `Engine.on_event` (1)

| id | line | op | original | mutated | flags |
|---|---|---|---|---|---|
| L0725_e01 | 725 | e | `self._drop_snapshot(keep_undoing=True)` | `pass` |  |

### `poisson_upper` (13)

| id | line | op | original | mutated | flags |
|---|---|---|---|---|---|
| L0841_d01 | 841 | d | `if not (isinstance(k, int) and not isinstance(k, bool) and k >= 0 and 0.0 < conf < 1.0):` | `if not (isinstance(k, int) and not isinstance(k, bool) and k >= 0 and (0.0*2) < conf < 1.0):` |  |
| L0841_d02 | 841 | d | `if not (isinstance(k, int) and not isinstance(k, bool) and k >= 0 and 0.0 < conf < 1.0):` | `if not (isinstance(k, int) and not isinstance(k, bool) and k >= 0 and (0.0/2) < conf < 1.0):` |  |
| L0847_d01 | 847 | d | `lo, hi = 0.0, 10.0 + 10.0 * k` | `lo, hi = (0.0*2), 10.0 + 10.0 * k` |  |
| L0847_d02 | 847 | d | `lo, hi = 0.0, 10.0 + 10.0 * k` | `lo, hi = (0.0/2), 10.0 + 10.0 * k` |  |
| L0847_d03 | 847 | d | `lo, hi = 0.0, 10.0 + 10.0 * k` | `lo, hi = 0.0, (10.0*2) + 10.0 * k` |  |
| L0847_d04 | 847 | d | `lo, hi = 0.0, 10.0 + 10.0 * k` | `lo, hi = 0.0, (10.0/2) + 10.0 * k` |  |
| L0847_d05 | 847 | d | `lo, hi = 0.0, 10.0 + 10.0 * k` | `lo, hi = 0.0, 10.0 + (10.0*2) * k` |  |
| L0847_d06 | 847 | d | `lo, hi = 0.0, 10.0 + 10.0 * k` | `lo, hi = 0.0, 10.0 + (10.0/2) * k` |  |
| L0848_a01 | 848 | a | `while cdf(hi) > 1 - conf:                      # the interval must hold the limit for every confidence` | `while cdf(hi) >= 1 - conf:                      # the interval must hold the limit for every confidence` |  |
| L0849_c01 | 849 | c | `lo, hi = hi, hi * 2` | `lo, hi = hi, hi * (2+1)` |  |
| L0850_c01 | 850 | c | `for _ in range(200):` | `for _ in range((200+1)):` |  |
| L0850_c02 | 850 | c | `for _ in range(200):` | `for _ in range((200-1)):` |  |
| L0852_a01 | 852 | a | `if cdf(mid) > 1 - conf:` | `if cdf(mid) >= 1 - conf:` |  |

### `ev1_pass` (1)

| id | line | op | original | mutated | flags |
|---|---|---|---|---|---|
| L0876_a01 | 876 | a | `and ev1_bound(false_corrections, n_negatives) <= 1e-4)` | `and ev1_bound(false_corrections, n_negatives) < 1e-4)` |  |

### `WittenBell.fit` (2)

| id | line | op | original | mutated | flags |
|---|---|---|---|---|---|
| L0911_a01 | 911 | a | `if self.min_count > 1:                              # prune BEFORE the totals are derived` | `if self.min_count >= 1:                              # prune BEFORE the totals are derived` |  |
| L0911_c02 | 911 | c | `if self.min_count > 1:                              # prune BEFORE the totals are derived` | `if self.min_count > (1-1):                              # prune BEFORE the totals are derived` |  |

### `WittenBell.logp` (2)

| id | line | op | original | mutated | flags |
|---|---|---|---|---|---|
| L0922_d01 | 922 | d | `total = 0.0` | `total = (0.0*2)` |  |
| L0922_d02 | 922 | d | `total = 0.0` | `total = (0.0/2)` |  |

### `lfb_logp` (2)

| id | line | op | original | mutated | flags |
|---|---|---|---|---|---|
| L1029_d01 | 1029 | d | `total = 0.0` | `total = (0.0*2)` |  |
| L1029_d02 | 1029 | d | `total = 0.0` | `total = (0.0/2)` |  |

### `lfw_forward` (3)

| id | line | op | original | mutated | flags |
|---|---|---|---|---|---|
| L1151_a01 | 1151 | a | `row.append(s if s > 0 else 0.0)` | `row.append(s if s >= 0 else 0.0)` |  |
| L1151_d01 | 1151 | d | `row.append(s if s > 0 else 0.0)` | `row.append(s if s > 0 else (0.0*2))` |  |
| L1151_d02 | 1151 | d | `row.append(s if s > 0 else 0.0)` | `row.append(s if s > 0 else (0.0/2))` |  |

## Notes on how mutants were built

- Operators were applied to code tokens only (strings, docstrings and comments are never mutated). Lines with no code tokens (comment-only, docstring, blank, import) are skipped.
- Integer and float literals are wrapped in parentheses, e.g. `2` -> `(2+1)`, `0.5` -> `(0.5*2)`, so the replacement is the whole expression, not a precedence change. Literals in slices (`[1:]`) with value 1 are skipped; values 47, 94, 95, 96, 97 are skipped.
- The `not` rule matches `not` after `if` or `elif` (the text `if not ` occurs inside `elif not `) and `not in`. Other `not` uses (e.g. `return not`, `and not`, `while not`) are not mutated, following the list in the task.
- Statement deletion covers single-line statements that are `self.<name>(...)` calls, `self.<name> = ...` assignments and `return None`. An annotated assignment `self.x: T = ...` is not of that form and was not mutated.
- Enclosing function names come from the AST ranges of def/class statements (innermost one), which is the same as scanning upward for the nearest enclosing def/class.

