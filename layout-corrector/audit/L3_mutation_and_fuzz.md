# L3. Reference engine: mutation testing, invariants, fuzzing

Status of this report: `REFERENCE_VERIFIED` for the properties of the reference **algorithm**. It says nothing about delivery of
physical events by a real hook or Raw Input (that needs `INTEGRATION_VERIFIED`, plan v1.2 item Q-7).

## What exactly was audited

| item | value |
|---|---|
| code under test | `layout-corrector/reference/lfengine.py` |
| git blob SHA-1 | `bb6f9b135c6bfa4f26b57dbc9e5eb6f902dedd2d` (file SHA-1 `479d687186c025085d760fc2dd7f810b6be56f4a`) |
| SHA-256 | `bf6082dc1fafafd7d076daae2d70fdc08a674d7a661be4a2bf3f79b2d62b5cae` |
| tests (the oracle) | `layout-corrector/reference/conformance.py`, blob `2a0c98132348763f51973957af016a6b697210b0`, SHA-256 `132efe38baad8f3c8e99dc7baaeea79261f1f61037f120e7cef3e19bdddab3a6` |
| first commit that holds exactly these two files | `6d7d14d` (branch `claude/layout-corrector-spec`); unchanged since (spec rev 305 was committed in `720713e`) |
| specification | rev 305; its code blocks of section 20 are byte-identical to the files (`audit/L7_check_spec_blocks.py`). Rev 293 and rev 295 were the editions of the earlier run r8 (code blob `6c5fc740...`), which is history |
| run | `r9`, 2026-11-07, all 718 valid mutants, no sampling |

If the code changes again (for example after the independent L9 review), r9 is void and must be run again.

The mutants were generated from a copy of these files (`base/` of the run; the generated report prints the SHA-256 of that copy, and it equals
the two SHA-256 values above). Earlier runs (r1 to r8) are history and are **not** evidence for the final code; r8 (708 mutants, 674 killed,
95.2%, code before F-3) is described below only because its survivors led to the real defects F-1 and F-3.

## What was run

* Tool: `audit/L3/mutate.py` (standard library only), driver `audit/L3/resume_run.py` (resumable, 2 workers).
* Mutated file: `lfengine.py` from line 173 (`# ==== 20.5`) to the end (line 1393), six first-order operators: comparison swap,
  boolean swap, integer literal ±1, float literal ×2 and ÷2, statement deletion, True/False swap. All 718 compile; all were run.
* Oracle for each mutant: `conformance.py 20000` (property, negative, boundary and fault-injection tests), timeout 150 s. Survivors
  also get `vectors.py` against `vectors_out.json` and `test_ref.py`.
* Raw results: `audit/L3/results.json`; the generated listing is `audit/L3/L3_mutation_report.md`.
* Evidence for the survivors: `audit/L3/L3_equivalence_evidence.py` (output `audit/L3/L3_equivalence_evidence.json`).
* Reproduce: copy `reference/` to `base/` of an empty folder together with `mutate.py` and `resume_run.py`, run
  `python3 mutate.py gen`, then `python3 resume_run.py 480` until it prints `results.json written`, then `python3 mutate.py report`
  and `python3 L3_equivalence_evidence.py <reference dir> mutants.json results.json`.

## Result

| quantity | r9, final code |
|---|---|
| mutants generated, valid, run | 718, 718, 718 |
| killed (one of them by timeout, see below) | **684** |
| survived | 34 |
| survived and `vectors.py` output differs | 0 |
| survived and `test_ref.py` fails | 0 |
| **kill rate on all mutants** | **95.3%** (684 / 718) |
| kill rate without the timeout (killed by a failing check only) | 95.2% (683 / 718) |
| kill rate without the 16 survivors that are the same program (below) | 97.5% (684 / 702) |
| kill rate on the mutants that change behaviour (all but the 34 survivors shown to be the same program, equal up to rounding, a tie that cannot happen or redundant) | 100% (684 / 684) |

**The plan's criterion ("at least 95% of mutants killed") is met literally, on all mutants, with a margin of 0.3 percentage
points.** The margin is thin, so the table of survivors below is part of the result and not an appendix.

The timeout is `L0678_c02` (`hi * 2` became `hi * (2-1)` in the new `while` loop of `poisson_upper`): the loop never ends, which is
a visible failure and the right verdict.

Per operator (from the generated report): comparison 125 (6 survived), boolean 96 (0), integer literal 278 (7), float literal 80
(21), statement deletion 82 (0), True/False 57 (0). Of the 21 float-literal survivors, sixteen are `0.0*2` and `0.0/2`, which are the
same number, and five change a search bracket or a range bound (next section).

## History that matters: r7 found a real defect

The run before this one (r7, 695 mutants, previous final code) killed 650 (93.5%) and left 45 survivors. Reading them showed that the
survivors around `poisson_upper` were not harmless: the tests that were written to kill them found that the function

```python
lo, hi = 0.0, 10.0 + 10.0 * k      # fixed search interval
```

returns **a wrong limit silently** when the confidence is above 0.99995 (for `k = 0` the limit is `-ln(1 - conf)`, 11.5 for
`conf = 0.99999`, and the interval ends at 10). The EV-1 rule uses only `conf = 0.95`, so no acceptance decision was ever affected, but a function with a
`conf` parameter must not be wrong without a signal. It was changed (20.9 of the specification and `lfengine.py`): the interval
doubles until it holds the limit, and `k < 0`, a non-integer `k`, `conf <= 0` or `conf >= 1` raise `ValueError`. The values for `conf = 0.95` are
unchanged (`vectors_out.json` is byte-identical), so no other file moved.

### Findings of this line

| id | finding | status |
|---|---|---|
| F-1 | `poisson_upper` wrong above `conf` 0.99995 (silent) | **fixed**; test group P15 pins `conf` 0.999, 0.99999, 0.999999 for `k` 0, 1, 2, 5, the refusals and the limits near 0 and 1 |
| F-2 | other test gaps of r7: default temperature of `log_softmax`; `pi_train_counts` with a zero count, a share exactly 0, above 1, and a share that is off by exactly the tolerance; the default `min_count` of `WittenBell`; the number of reads of a failed match in `run_transaction` (the loop of typed-ahead lengths); a caret two places forward after two keys that type nothing; the initial state of `HookHealth` | **closed** by test group P15 of `conformance.py` (each check names the line it pins) |
| F-3 (as found in r8) | `WittenBell.fit` did not check that the multiplicity of a row is at least 1. With a multiplicity of 0 the table keeps zero counts, which `logp` then treats as seen types. Section 8.3 allows 1 to 5, so the data path of the project never produces 0 | **closed** (commit `6d7d14d`, spec 20.10): `fit` validates before touching the model that there is one weight per row, each an `int` (not `bool`) from 1 to 5, counts into a separate structure and merges at the end, so a refusal leaves the model unchanged. Test group P16 pins zero, negative, fractional, float-whole, bool, above 5, string, fewer and more weights, no weights for two rows, and the unchanged model after each refusal; the two r8 survivors `L0727_a01/c02` are now redundant (`L0740_a01/c02`) |

## The 34 survivors of r9

Each was run against the original on a stated set of inputs by `L3_equivalence_evidence.py` (fixed seeds). The classes:

| class | meaning | mutants |
|---|---|---|
| IDENTICAL (16) | the changed literal is the same number: `0.0*2` and `0.0/2` equal `0.0`, so the program is the same | `L0267_d01/d02`, `L0275_d01/d02`, `L0280_d01/d02`, `L0670_d01/d02`, `L0676_d01/d02`, `L0751_d01/d02`, `L0858_d01/d02`, `L0980_d01/d02` |
| DIFFERENTIAL, rounding only (13) | original and mutant agree on a large stated set of inputs up to the rounding of the arithmetic (numbers below) | `L0212_c01/c02/c04`, `L0676_d03` to `d06`, `L0677_a01`, `L0678_c01`, `L0679_c01/c02`, `L0681_a01`, `L0980_a01` |
| TIE_IMPOSSIBLE (2) | differs only when two floats are exactly equal, and the script shows that cannot happen | `L0278_a01`, `L0705_a01` |
| REDUNDANT (3) | another check refuses the same inputs (`L0280_d03`), or the changed pruning bound cannot matter because every count is at least 1 since F-3 (`L0740_a01/c02`) | `L0280_d03`, `L0740_a01`, `L0740_c02` |

The evidence, class by class:

* `L0212_c01/c02/c04` (the normaliser `norm` in `score`): `norm` is subtracted from both log-probabilities, so it cancels. On 20,000
  random inputs (logits in [-30, 30], random temperature, `o_lat`, class mix, word weight, both layouts) the scores differ by at most
  2.84e-14 nats (rounding).
* `L0676_d03` to `d06`, `L0678_c01`, `L0679_c01/c02`, `L0677_a01`, `L0681_a01` (search interval start, growth factor, iteration count,
  `>` against `>=` in `poisson_upper`): 396 pairs (k up to 200, conf from 0.01 to 1 − 1e-12) agree to at most 1.6e-13 relative; against a
  60-digit decimal solution on 72 pairs the original is off by at most 1.8e-14 and the mutants by at most 4.6e-15 (relative). The
  differences are the resolution of the rounded cumulative sum (a plateau of equal floats), not a different limit.
* `L0980_a01` (`s >= 0` against `s > 0` in the ReLU): differs only for `s == 0`, where both give a zero (`-0.0` at most);
  400 random small networks with weights in {-1, 0, 1} give equal logits.
* `L0278_a01`: the tie needs `abs(sum - 1.0) == 1e-9`; for a float sum near 1 the difference is a multiple of 2⁻⁵³ and 1e-9 is
  9007199.25 of those units, so it cannot happen. (The same check for the individual shares, `L0276_a01`, is **killed** since r8 by
  the test that uses a share that is off by exactly 1e-9.)
* `L0705_a01` (`<=` against `<` at exactly 1e-4 in `ev1_pass`): the bound is `U(c) · m / n` with an irrational `U(c)`; 145,200
  combinations (clusters 0 to 120, largest cluster 1 to 300, `n` next to `U · m / 1e-4`) contain no exact tie.
* `L0280_d03` (upper bound of `o_lat` 1.0 to 2.0): the values between 1 and 2 are refused by `o_lat >= 1.0` right after; the verdict is
  equal on twelve values including `inf` and `nan`.
* `L0740_a01/c02` (`min_count > 1` against `>= 1` or `> 0` in `WittenBell.fit`): since F-3 every multiplicity is an integer from 1 to 5, so every count is at least 1 and pruning below 1 removes nothing; 600 random fits are equal, and original and mutant both refuse weights outside 1 to 5.

An equivalence argument is an argument, not a proof. Each can be re-checked by running `m/<id>/lfengine.py` against the tests, and the script prints
the inputs it used.

## Invariants and fuzzing

`conformance.py` checks, on every case, the invariants of plan section L3 (I1 to I6): no key lost or duplicated by the engine,
`convert` only at `s ≥ λ` with gate ALLOW, word length at most 20 keys or reset, snapshot lifetime at most 10 s and 100
characters, no snapshot after a context break, gate change or layout change, and undo equal to the recorded keys rendered with the
recorded layout. Full-size runs on the final files (`N = 1,000,000` events per group), normal and `python -O`:

| command | output |
|---|---|
| `python3 conformance.py 1000000` | `OK (9222553 checks, 1665 single and double faults, 3303 fuzz conversions, 2274 fuzz undos)` |
| `python3 -O conformance.py 1000000` | `OK (9222553 checks, 1665 single and double faults, 3303 fuzz conversions, 2274 fuzz undos)` (the same number of checks: none disappears under `-O`) |

(Python 3.13 of the audit container; the workflow runs 3.9, 3.11 and 3.13 with `N = 200000`.)

The fault matrix of 13.2 has 57 named rows; in addition every single fault and every pair of faults of the transaction (1,665 combinations, M1 with
rollback) and the M2 sweep are executed, with the invariants "never VERIFIED with a wrong text", "never ABORTED after a change",
"UNRECOVERED always with incident and quarantine", "the user's own keys exactly once".

## Limits

* The mutants cover the engine from section 20.5 on; tables and rendering (20.2 to 20.4) are covered by the vectors and by the
  independent re-implementation (line L1).
* Operators are first-order; combinations of two defects were not generated.
* The mutation score is a property of this test suite on this code. It does not measure whether the specification is right.
* The oracle is a reference model. A real adapter is another program and needs its own regression tests (13.6, RT-1 to RT-18).
