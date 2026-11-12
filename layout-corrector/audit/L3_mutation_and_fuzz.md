# L3. Reference engine: mutation testing, invariants, fuzzing

Status of this report: `REFERENCE_VERIFIED` for the properties of the reference **algorithm**. It says nothing about delivery of
physical events by a real hook or Raw Input (that needs `INTEGRATION_VERIFIED`, plan v1.2 item Q-7).

## What exactly was audited

| item | value |
|---|---|
| code under test | `layout-corrector/reference/lfengine.py` |
| git blob SHA-1 | `502292ce85c50e1b40d10a8a9c8239be3defb541` |
| SHA-256 | `4af41c76efefbc7d48dc26c696f15822dd447d726cc02813e17fb0673c3eae5f` |
| tests (the oracle) | `layout-corrector/reference/conformance.py`, blob `48eee1f5373697eb3116332abb1989590462de9a`, SHA-256 `ddcc300c3fca57983bbbe6c411c9bfd1368f3f11eb85e64c8d28e2f0e124e580` |
| specification | rev 418 or later; its code blocks of section 20 are byte-identical to the files (`audit/L7_check_spec_blocks.py`, run after the last edit) |
| run | `r10`, 2026-11-12, all 795 valid mutants, no sampling; see "How r10 was run" for the two stages |

The code is the code after the independent review L9 (findings F1 to F11). The earlier run r9 (718 mutants, 684 killed, 95.3%) was on the code before
those fixes and is void; r8 and older are history. If the code changes again, r10 is void and must be run again.

How r10 was run (two stages, stated because the second is a shortcut): (1) all 795 mutants against `conformance.py` as it was after the L9 fixes
(blob before the stage-2 additions): 746 killed, 1 timeout, 48 survivors = 94.0%, **below the 95% criterion**; (2) the 48 survivors showed holes in the
tests of the new code (limit of the exception list, quarantine, read window, bookkeeping of the simulated field), a block of regression tests
(`# L9 round 3` at the end of `conformance.py`) was added, and **only the 49 mutants that had not been killed in stage 1 were run again** with the final
`conformance.py`: 13 more were killed. The added block only appends checks, so a mutant killed in stage 1 stays killed; this is an argument,
not a re-measurement. A full re-run of all 795 against the final tests was not done.

The mutants were generated from a copy of `lfengine.py` (`base/` of the run; the generated report prints the SHA-256 of that copy and it equals the value above).

## What was run

* Tool: `audit/L3/mutate.py` (standard library only), driver `audit/L3/resume_run.py` (resumable, 2 workers).
* Mutated file: `lfengine.py` from line 173 (`# ==== 20.5`) to the end (line 1496), six first-order operators: comparison swap,
  boolean swap, integer literal ±1, float literal ×2 and ÷2, statement deletion, True/False swap. All 795 compile; all were run.
* Oracle for each mutant: `conformance.py 20000` (property, negative, boundary and fault-injection tests), timeout 150 s. Survivors
  also get `vectors.py` against `vectors_out.json` and `test_ref.py`.
* Raw results: `audit/L3/results.json`; the generated listing is `audit/L3/L3_mutation_report.md`.
* Evidence for the survivors: `audit/L3/L3_equivalence_evidence.py` (output `audit/L3/L3_equivalence_evidence.json`).
* Reproduce: copy `reference/` to `base/` of an empty folder together with `mutate.py` and `resume_run.py`, run
  `python3 mutate.py gen`, then `python3 resume_run.py 480` until it prints `results.json written`, then `python3 mutate.py report`
  and `python3 L3_equivalence_evidence.py <reference dir> mutants.json results.json`.

## Result

| quantity | r10, final code |
|---|---|
| mutants generated, valid, run | 795, 795, 795 |
| killed (one of them by timeout, see below) | **760** |
| survived | 35 |
| survived and `vectors.py` output differs | 0 |
| survived and `test_ref.py` fails | 0 |
| **kill rate on all mutants** | **95.6%** (760 / 795) |
| kill rate without the timeout (killed by a failing check only) | 95.5% (759 / 795) |
| kill rate without the 16 survivors that are the same program (below) | 97.6% (760 / 779) |
| kill rate on the mutants that change behaviour (all but the 35 survivors shown to be the same program, equal up to rounding, a tie that cannot happen, redundant, or unreachable) | 100% (760 / 760) |

**The plan's criterion ("at least 95% of mutants killed") is met literally, on all mutants, with a margin of 0.6 percentage points, but only after the
stage-2 tests** (stage 1 gave 94.0%). The table of survivors below is part of the result and not an appendix.

The timeout is `L0735_c02` (`hi * 2` became `hi * (2-1)` in the `while` loop of `poisson_upper`): the loop never ends, which is a visible failure and the right verdict.

Per operator (from the generated report): comparison 142 (6 survived), boolean 112 (0), integer literal 290 (7), float literal 80 (21), statement
deletion 105 (1), True/False 66 (0). Of the 21 float-literal survivors, sixteen are `0.0*2` and `0.0/2`, which are the same number, and five change a
search bracket or a range bound (next section).

## The 35 survivors of r10

Each was run against the original on a stated set of inputs by `L3_equivalence_evidence.py` (fixed seeds); none ended as GAP. The classes:

| class | meaning | mutants |
|---|---|---|
| IDENTICAL (16) | the changed literal is the same number: `0.0*2` and `0.0/2` equal `0.0`, so the program is the same | `L0267_d01/d02`, `L0275_d01/d02`, `L0280_d01/d02`, `L0727_d01/d02`, `L0733_d01/d02`, `L0808_d01/d02`, `L0915_d01/d02`, `L1037_d01/d02` |
| DIFFERENTIAL (14) | original and mutant agree on a large stated set of inputs, up to the rounding of the arithmetic or because the changed state cannot be reached (numbers below) | `L0212_c01/c02/c04`, `L0733_d03` to `d06`, `L0734_a01`, `L0735_c01`, `L0736_c01/c02`, `L0738_a01`, `L1037_a01`, `L0611_e01` |
| TIE_IMPOSSIBLE (2) | differs only when two floats are exactly equal, and the script shows that cannot happen | `L0278_a01`, `L0762_a01` |
| REDUNDANT (3) | another check refuses the same inputs (`L0280_d03`), or the changed pruning bound cannot matter because every count is at least 1 since F-3 (`L0797_a01/c02`) | `L0280_d03`, `L0797_a01`, `L0797_c02` |

The evidence, class by class:

* `L0212_c01/c02/c04` (the normaliser `norm` in `score`): `norm` is subtracted from both log-probabilities, so it cancels. On 20,000 random inputs the scores differ by at most 2.84e-14 nats (rounding).
* `L0733_d03` to `d06`, `L0735_c01`, `L0736_c01/c02`, `L0734_a01`, `L0738_a01` (search interval start, growth factor, iteration count, `>` against `>=` in `poisson_upper`): the evidence script compares the original and the mutant on 396 pairs (k up to 200, conf from 0.01 to 1 - 1e-12) and against a 60-digit decimal solution; the numbers are printed in `L3_equivalence_evidence.json`. The differences are the resolution of the rounded cumulative sum (a plateau of equal floats), not a different limit.
* `L1037_a01` (`s >= 0` against `s > 0` in the ReLU): differs only for `s == 0`, where both give a zero (`-0.0` at most); 400 random small networks with weights in {-1, 0, 1} give equal logits.
* `L0611_e01` (`_drop_snapshot()` when a key of another layout arrives inside a word): reaching it needs a snapshot that has the layout of the new key while the word in progress has another layout. A word never starts while a snapshot of another layout is alive (the check just above drops it), and a snapshot is made only at a Space, after the word was flushed. 9,644 random events (keys, Spaces, breaks, Backspaces, layout changes, VERIFIED outcomes in both layouts) give 0 differences in the word, snapshot, credit, flags and decisions. This is an argument plus a differential test, not a proof; the statement could be deleted from the code, but it is kept as a defence in depth.
* `L0278_a01`: the tie needs `abs(sum - 1.0) == 1e-9`; for a float sum near 1 the difference is a multiple of 2^-53 and 1e-9 is 9007199.25 of those units, so it cannot happen.
* `L0762_a01` (`<=` against `<` at exactly 1e-4 in `ev1_pass`): the bound is `U(c) * m / n` with an irrational `U(c)`; 145,200 combinations contain no exact tie.
* `L0280_d03` (upper bound of `o_lat` 1.0 to 2.0): the values between 1 and 2 are refused by `o_lat >= 1.0` right after; the verdict is equal on twelve values including `inf` and `nan`.
* `L0797_a01/c02` (`min_count > 1` against `>= 1` or `> 0` in `WittenBell.fit`): since F-3 every multiplicity is an integer from 1 to 5, so every count is at least 1 and pruning below 1 removes nothing (600 random fits equal).

What the stage-1 survivors taught (fixed by tests, not by code): the new code of L9 had no test for the exact limit of 10,000 exceptions and its eviction order, for the
state that an incident empties (word, flags, credit, a confirmed snapshot) and that a release does not bring back, for the credit and snapshot that an UNRECOVERED undo
destroys even without the incident flag, for the drop of the snapshot by a key of another layout, for the exact window of the read in step 3, and for the counters of the simulated field.

An equivalence argument is an argument, not a proof. Each can be re-checked by running `m/<id>/lfengine.py` against the tests, and the script prints the inputs it used.

## Invariants and fuzzing

`conformance.py` checks, on every case, the invariants of plan section L3 (I1 to I6): no key lost or duplicated by the engine,
`convert` only at `s ≥ λ` with gate ALLOW, word length at most 20 keys or reset, snapshot lifetime at most 10 s and 100
characters, no snapshot after a context break, gate change or layout change, and undo equal to the recorded keys rendered with the
recorded layout. Full-size runs on the final files (`N = 1,000,000` events per group), normal and `python -O`:

| command | output |
|---|---|
| `python3 conformance.py 1000000` | `OK (9222949 checks, 1821 single and double faults, 3401 fuzz conversions, 1106 fuzz undos)` |
| `python3 -O conformance.py 1000000` | `OK (9222949 checks, 1821 single and double faults, 3401 fuzz conversions, 1106 fuzz undos)` (the same number of checks: none disappears under `-O`) |

(Python 3.13 of the audit container; the workflow runs 3.9, 3.11 and 3.13 with `N = 200000`.)

The fault matrix of 13.2 has 66 named rows; in addition every single fault and every pair of faults of the transaction (1,821 combinations, M1 with
rollback and M2) and the M2 sweep are executed, with the invariants "never VERIFIED with a wrong text", "never ABORTED after a change",
"UNRECOVERED always with incident and quarantine", "the user's own keys exactly once".

## Limits

* The mutants cover the engine from section 20.5 on; tables and rendering (20.2 to 20.4) are covered by the vectors and by the
  independent re-implementation (line L1).
* Operators are first-order; combinations of two defects were not generated.
* The mutation score is a property of this test suite on this code. It does not measure whether the specification is right.
* The oracle is a reference model. A real adapter is another program and needs its own regression tests (13.6, RT-1 to RT-25).
