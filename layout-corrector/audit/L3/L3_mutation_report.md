# L3 mutation report: lfengine.py (reference engine), mutants from line 173 (`# ==== 20.5`) to line 1289

Source: `git show 7e68d46:layout-corrector/reference/lfengine.py`, copied to `base/`. Baseline: `python3 conformance.py 20000` prints OK; `vectors.py` matches `vectors_out.json`; `test_ref.py` passes. Each mutant runs `timeout 150 python3 conformance.py 20000` in its own directory.

## Counts

| quantity | value |
|---|---|
| generated (all operators, before compile check) | 659 |
| did not compile (discarded) | 0 |
| valid mutants | 659 |
| run | 659 (sampled: no, all valid mutants) |
| killed (incl. timeouts) | 612 |
| of which TIMEOUT | 0 |
| survived | 47 |
| survived-but-vectors-differ (subset of survived) | 0 |
| survivors where test_ref.py also fails | 0 |
| **kill rate = killed / run** | **92.9%** (612/659) |

## Per operator

| op | kind | generated | not compiling | valid | run | killed | survived |
|---|---|---|---|---|---|---|---|
| a | comparison | 107 | 0 | 107 | 107 | 99 | 8 |
| b | boolean | 84 | 0 | 84 | 84 | 84 | 0 |
| c | integer literal | 258 | 0 | 258 | 258 | 248 | 10 |
| d | float literal | 78 | 0 | 78 | 78 | 53 | 25 |
| e | statement deletion | 77 | 0 | 77 | 77 | 75 | 2 |
| f | True/False | 55 | 0 | 55 | 55 | 53 | 2 |

## Survivors by enclosing function

Flags: `VECTORS_DIFFER` = vectors.py output differs from vectors_out.json (label SURVIVED_BUT_VECTORS_DIFFER); `test_ref FAILS` = test_ref.py exits non-zero.

### `log_softmax` (2)

| id | line | op | original | mutated | flags |
|---|---|---|---|---|---|
| L0179_d01 | 179 | d | `def log_softmax(z: Sequence[float], temp: float = 1.0) -> List[float]:` | `def log_softmax(z: Sequence[float], temp: float = (1.0*2)) -> List[float]:` |  |
| L0179_d02 | 179 | d | `def log_softmax(z: Sequence[float], temp: float = 1.0) -> List[float]:` | `def log_softmax(z: Sequence[float], temp: float = (1.0/2)) -> List[float]:` |  |

### `score` (3)

| id | line | op | original | mutated | flags |
|---|---|---|---|---|---|
| L0212_c01 | 212 | c | `norm = _lse2(_lse2(lp[0], lp[1]), lp[2])` | `norm = _lse2(_lse2(lp[0], lp[(1+1)]), lp[2])` |  |
| L0212_c02 | 212 | c | `norm = _lse2(_lse2(lp[0], lp[1]), lp[2])` | `norm = _lse2(_lse2(lp[0], lp[(1-1)]), lp[2])` |  |
| L0212_c04 | 212 | c | `norm = _lse2(_lse2(lp[0], lp[1]), lp[2])` | `norm = _lse2(_lse2(lp[0], lp[1]), lp[(2-1)])` |  |

### `check_calibration_package` (13)

| id | line | op | original | mutated | flags |
|---|---|---|---|---|---|
| L0267_d01 | 267 | d | `_finite(cal["temperature"][kind], f"temperature[{kind}]", 0.0, 20.0, lo_open=True)` | `_finite(cal["temperature"][kind], f"temperature[{kind}]", (0.0*2), 20.0, lo_open=True)` |  |
| L0267_d02 | 267 | d | `_finite(cal["temperature"][kind], f"temperature[{kind}]", 0.0, 20.0, lo_open=True)` | `_finite(cal["temperature"][kind], f"temperature[{kind}]", (0.0/2), 20.0, lo_open=True)` |  |
| L0270_a01 | 270 | a | `isinstance(n, int) and not isinstance(n, bool) and n > 0 for n in counts)):` | `isinstance(n, int) and not isinstance(n, bool) and n >= 0 for n in counts)):` |  |
| L0275_d01 | 275 | d | `_finite(p, f"pi_train[{i}]", 0.0, 1.0, lo_open=True)` | `_finite(p, f"pi_train[{i}]", (0.0*2), 1.0, lo_open=True)` |  |
| L0275_d02 | 275 | d | `_finite(p, f"pi_train[{i}]", 0.0, 1.0, lo_open=True)` | `_finite(p, f"pi_train[{i}]", (0.0/2), 1.0, lo_open=True)` |  |
| L0275_d03 | 275 | d | `_finite(p, f"pi_train[{i}]", 0.0, 1.0, lo_open=True)` | `_finite(p, f"pi_train[{i}]", 0.0, (1.0*2), lo_open=True)` |  |
| L0275_d04 | 275 | d | `_finite(p, f"pi_train[{i}]", 0.0, 1.0, lo_open=True)` | `_finite(p, f"pi_train[{i}]", 0.0, (1.0/2), lo_open=True)` |  |
| L0275_f01 | 275 | f | `_finite(p, f"pi_train[{i}]", 0.0, 1.0, lo_open=True)` | `_finite(p, f"pi_train[{i}]", 0.0, 1.0, lo_open=False)` |  |
| L0276_a01 | 276 | a | `if abs(p - counts[i] / sum(counts)) > 1e-9:` | `if abs(p - counts[i] / sum(counts)) >= 1e-9:` |  |
| L0278_a01 | 278 | a | `if abs(sum(pt) - 1.0) > 1e-9:` | `if abs(sum(pt) - 1.0) >= 1e-9:` |  |
| L0280_d01 | 280 | d | `_finite(cal["o_lat"], "o_lat", 0.0, 1.0, lo_open=True)` | `_finite(cal["o_lat"], "o_lat", (0.0*2), 1.0, lo_open=True)` |  |
| L0280_d02 | 280 | d | `_finite(cal["o_lat"], "o_lat", 0.0, 1.0, lo_open=True)` | `_finite(cal["o_lat"], "o_lat", (0.0/2), 1.0, lo_open=True)` |  |
| L0280_d03 | 280 | d | `_finite(cal["o_lat"], "o_lat", 0.0, 1.0, lo_open=True)` | `_finite(cal["o_lat"], "o_lat", 0.0, (1.0*2), lo_open=True)` |  |

### `poisson_upper` (12)

| id | line | op | original | mutated | flags |
|---|---|---|---|---|---|
| L0663_d01 | 663 | d | `lo, hi = 0.0, 10.0 + 10.0 * k` | `lo, hi = (0.0*2), 10.0 + 10.0 * k` |  |
| L0663_d02 | 663 | d | `lo, hi = 0.0, 10.0 + 10.0 * k` | `lo, hi = (0.0/2), 10.0 + 10.0 * k` |  |
| L0663_d03 | 663 | d | `lo, hi = 0.0, 10.0 + 10.0 * k` | `lo, hi = 0.0, (10.0*2) + 10.0 * k` |  |
| L0663_d04 | 663 | d | `lo, hi = 0.0, 10.0 + 10.0 * k` | `lo, hi = 0.0, (10.0/2) + 10.0 * k` |  |
| L0663_d05 | 663 | d | `lo, hi = 0.0, 10.0 + 10.0 * k` | `lo, hi = 0.0, 10.0 + (10.0*2) * k` |  |
| L0663_d06 | 663 | d | `lo, hi = 0.0, 10.0 + 10.0 * k` | `lo, hi = 0.0, 10.0 + (10.0/2) * k` |  |
| L0664_c01 | 664 | c | `for _ in range(200):` | `for _ in range((200+1)):` |  |
| L0664_c02 | 664 | c | `for _ in range(200):` | `for _ in range((200-1)):` |  |
| L0666_a01 | 666 | a | `cdf = sum(math.exp(-mid + i * math.log(mid) - math.lgamma(i + 1)) for i in range(k + 1)) if mid > 0 else 1.0` | `cdf = sum(math.exp(-mid + i * math.log(mid) - math.lgamma(i + 1)) for i in range(k + 1)) if mid >= 0 else 1.0` |  |
| L0666_d01 | 666 | d | `cdf = sum(math.exp(-mid + i * math.log(mid) - math.lgamma(i + 1)) for i in range(k + 1)) if mid > 0 else 1.0` | `cdf = sum(math.exp(-mid + i * math.log(mid) - math.lgamma(i + 1)) for i in range(k + 1)) if mid > 0 else (1.0*2)` |  |
| L0666_d02 | 666 | d | `cdf = sum(math.exp(-mid + i * math.log(mid) - math.lgamma(i + 1)) for i in range(k + 1)) if mid > 0 else 1.0` | `cdf = sum(math.exp(-mid + i * math.log(mid) - math.lgamma(i + 1)) for i in range(k + 1)) if mid > 0 else (1.0/2)` |  |
| L0667_a01 | 667 | a | `if cdf > 1 - conf:` | `if cdf >= 1 - conf:` |  |

### `ev1_pass` (1)

| id | line | op | original | mutated | flags |
|---|---|---|---|---|---|
| L0691_a01 | 691 | a | `and ev1_bound(false_corrections, n_negatives) <= 1e-4)` | `and ev1_bound(false_corrections, n_negatives) < 1e-4)` |  |

### `WittenBell.__init__` (1)

| id | line | op | original | mutated | flags |
|---|---|---|---|---|---|
| L0699_c02 | 699 | c | `def __init__(self, vocab: int = VOCAB, min_count: int = 1):` | `def __init__(self, vocab: int = VOCAB, min_count: int = (1-1)):` |  |

### `WittenBell.fit` (2)

| id | line | op | original | mutated | flags |
|---|---|---|---|---|---|
| L0713_a01 | 713 | a | `if self.min_count > 1:                              # prune BEFORE the totals are derived` | `if self.min_count >= 1:                              # prune BEFORE the totals are derived` |  |
| L0713_c02 | 713 | c | `if self.min_count > 1:                              # prune BEFORE the totals are derived` | `if self.min_count > (1-1):                              # prune BEFORE the totals are derived` |  |

### `WittenBell.logp` (2)

| id | line | op | original | mutated | flags |
|---|---|---|---|---|---|
| L0724_d01 | 724 | d | `total = 0.0` | `total = (0.0*2)` |  |
| L0724_d02 | 724 | d | `total = 0.0` | `total = (0.0/2)` |  |

### `lfb_logp` (2)

| id | line | op | original | mutated | flags |
|---|---|---|---|---|---|
| L0831_d01 | 831 | d | `total = 0.0` | `total = (0.0*2)` |  |
| L0831_d02 | 831 | d | `total = 0.0` | `total = (0.0/2)` |  |

### `lfw_forward` (3)

| id | line | op | original | mutated | flags |
|---|---|---|---|---|---|
| L0953_a01 | 953 | a | `row.append(s if s > 0 else 0.0)` | `row.append(s if s >= 0 else 0.0)` |  |
| L0953_d01 | 953 | d | `row.append(s if s > 0 else 0.0)` | `row.append(s if s > 0 else (0.0*2))` |  |
| L0953_d02 | 953 | d | `row.append(s if s > 0 else 0.0)` | `row.append(s if s > 0 else (0.0/2))` |  |

### `run_transaction` (2)

| id | line | op | original | mutated | flags |
|---|---|---|---|---|---|
| L1073_c01 | 1073 | c | `for a in range(len(ahead), -1, -1):` | `for a in range(len(ahead), -(1+1), -1):` |  |
| L1099_c01 | 1099 | c | `end = start + n + (1 if method == "M2" else 0)` | `end = start + n + ((1+1) if method == "M2" else 0)` |  |

### `SimField.caret` (1)

| id | line | op | original | mutated | flags |
|---|---|---|---|---|---|
| L1155_c01 | 1155 | c | `return self.pos - 1 if f == "back" else self.pos` | `return self.pos - (1+1) if f == "back" else self.pos` |  |

### `HookHealth.__init__` (3)

| id | line | op | original | mutated | flags |
|---|---|---|---|---|---|
| L1237_e01 | 1237 | e | `self.pairs = 0                   # matched canary/hook pairs since the hook was installed again` | `pass                   # matched canary/hook pairs since the hook was installed again` |  |
| L1238_e01 | 1238 | e | `self.reinstalled_flag = False` | `pass` |  |
| L1238_f01 | 1238 | f | `self.reinstalled_flag = False` | `self.reinstalled_flag = True` |  |

## Notes on how mutants were built

- Operators were applied to code tokens only (strings, docstrings and comments are never mutated). Lines with no code tokens (comment-only, docstring, blank, import) are skipped.
- Integer and float literals are wrapped in parentheses, e.g. `2` -> `(2+1)`, `0.5` -> `(0.5*2)`, so the replacement is the whole expression, not a precedence change. Literals in slices (`[1:]`) with value 1 are skipped; values 47, 94, 95, 96, 97 are skipped.
- The `not` rule matches `not` after `if` or `elif` (the text `if not ` occurs inside `elif not `) and `not in`. Other `not` uses (e.g. `return not`, `and not`, `while not`) are not mutated, following the list in the task.
- Statement deletion covers single-line statements that are `self.<name>(...)` calls, `self.<name> = ...` assignments and `return None`. An annotated assignment `self.x: T = ...` is not of that form and was not mutated.
- Enclosing function names come from the AST ranges of def/class statements (innermost one), which is the same as scanning upward for the nearest enclosing def/class.

