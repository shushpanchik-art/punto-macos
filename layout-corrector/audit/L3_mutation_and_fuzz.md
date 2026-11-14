# L3. Reference engine: mutation testing, invariants, fuzzing

Status of this report: `REFERENCE_VERIFIED` for the properties of the reference **algorithm**. It says nothing about delivery of
physical events by a real hook or Raw Input (that needs `INTEGRATION_VERIFIED`, plan v1.2 item Q-7).

## What exactly was audited

| item | value |
|---|---|
| code under test | `layout-corrector/reference/lfengine.py`, git blob `aa34f7e5fe506a02ea6d6db4f4d70061c9a59e9d`, SHA-256 `e83eccdacfa3574ddd9b2d1a936057b0e4f1da916129256754d61420fbc03e30` |
| tests during the run | `conformance.py` with SHA-256 `2c0239795d96be69d82094724377037531c8c...` (the final file, including the three checks for `L1431_c01`; copied to `base/` of the run) |
| specification | rev 502; its code blocks of section 20 are byte-identical to the files (`audit/L7_check_spec_blocks.py`, 4 of 4 IDENTICAL, run after the last edit) |
| run | `r13`, 2026-11-13/14, all 991 valid mutants against the final code AND the final tests, no sampling, **one stage, one oracle** (no shortcut as in r10). It follows r12 (950 killed = 95.9%, run before the three `L1431_c01` checks; kept in this history only) |

r13 is a fresh full run on the code after the toggle, the selection contract, the P3 fixes and the U-1 change (`ahead_len`). The earlier run r10 (795 mutants) was on older
code and is void; r11 (977 mutants, same code except U-1, 91.9%: 79 survivors) was the first run on the new code and showed the test holes that the block `G` of
`conformance.py` closes; it is kept in this history only. If the code or the tests change again, r13 is void and must be run again.

The run was interrupted twice (the container paused at 81 of 991 and once more) and resumed with `resume_run.py`, which skips finished mutants; the results file holds one line per mutant.

## What was run

* Tool: `audit/L3/mutate.py` (standard library only), driver `audit/L3/resume_run.py` (resumable, 2 workers).
* Mutated file: `lfengine.py` from line 173 (`# ==== 20.5`) to the end, six first-order operators: comparison swap, boolean swap,
  integer literal ±1, float literal ×2 and ÷2, statement deletion, True/False swap. All 991 compile; all were run.
* Oracle for each mutant: `conformance.py 20000`, timeout 150 s. Survivors also get `vectors.py` against `vectors_out.json` and `test_ref.py`.
* Raw results: `audit/L3/results.json`, `audit/L3/mutants.json`; the generated listing is `audit/L3/L3_mutation_report.md`.
* Evidence for the survivors: `audit/L3/L3_equivalence_evidence.py` (output `audit/L3/L3_equivalence_evidence.json`).
* Reproduce: copy `reference/` files (`lfengine.py`, `conformance.py`, `vectors.py`, `vectors_out.json`, `test_ref.py`) to `base/` of an empty folder together with
  `mutate.py` and `resume_run.py`, run `python3 mutate.py gen`, then `python3 resume_run.py 540` until the results file has 991 lines (`python3 mutate.py report`),
  then `python3 L3_equivalence_evidence.py base mutants.json results.json --json out.json`.

## Result

| quantity | r13, final code and tests |
|---|---|
| mutants generated, valid, run | 991, 991, 991 |
| killed (one of them by timeout) | **951** |
| survived | 40 |
| survived and `vectors.py` output differs | 0 |
| survived and `test_ref.py` fails | 0 |
| **kill rate on all mutants** | **96.0%** (951 / 991) |
| kill rate without the timeout | 95.9% (950 / 991) |

**The plan's criterion ("at least 95% of mutants killed") is met literally, with a margin of 1.0 percentage point.** Per operator: comparison 193 (6 survived),
boolean 166 (0), integer literal 318 (8), float literal 80 (21), statement deletion 142 (6), True/False 92 (0).

## The 40 survivors of r13

Each was run against the original on a stated set of inputs by `L3_equivalence_evidence.py` (fixed seeds). Classes:

| class | mutants |
|---|---|
| DIFFERENTIAL (14) | `L0212_c01`, `L0212_c02`, `L0212_c04`, `L0725_e01`, `L0847_d03`, `L0847_d04`, `L0847_d05`, `L0847_d06`, `L0848_a01`, `L0849_c01`, `L0850_c01`, `L0850_c02`, `L0852_a01`, `L1151_a01` |
| GAP (1) | `L1431_c01` |
| IDENTICAL (16) | `L0267_d01`, `L0267_d02`, `L0275_d01`, `L0275_d02`, `L0280_d01`, `L0280_d02`, `L0841_d01`, `L0841_d02`, `L0847_d01`, `L0847_d02`, `L0922_d01`, `L0922_d02`, `L1029_d01`, `L1029_d02`, `L1151_d01`, `L1151_d02` |
| REDUNDANT (8) | `L0280_d03`, `L0628_e01`, `L0629_e01`, `L0686_e01`, `L0687_e01`, `L0693_e01`, `L0911_a01`, `L0911_c02` |
| TIE_IMPOSSIBLE (2) | `L0278_a01`, `L0876_a01` |

* IDENTICAL: the changed literal is the same number (`0.0*2`, `0.0/2`).
* DIFFERENTIAL: equal on a large stated set of inputs up to rounding (the normaliser of `score` cancels; the start, factor and iteration count of the `poisson_upper` search; `s >= 0` in the ReLU; the unreachable `_drop_snapshot()` of line 725).
* TIE_IMPOSSIBLE: differs only when two floats are exactly equal and the script shows that cannot happen (`L0278_a01`, `L0876_a01`).
* REDUNDANT: another statement does the same: after `UNRECOVERED` the very next statement calls `_quarantine()` (`L0628`, `L0629`, `L0686`, `L0687`, `L0693`: 10,864 random operations on two engines, the whole state compared after each); `L0280_d03` and `L0911_*` as in r10.
* GAP: none in r13 (r12 had one, `L1431_c01`, see below).

An equivalence argument is an argument, not a proof. Each can be re-checked by running `m/<id>/lfengine.py` against the tests.

## The gap that r12's evidence found, and its closure

`L1431_c01` (`ad.read(lo, start + n + 1)` read as `start + n + 2` in `run_manual_transaction`) was classified GAP, not equivalent: with the fault "stale" on the first
read the original does not accept the damaged character behind the word and ends RESTORED (M1), UNRECOVERED (M1 without ROLLBACK, M2), while the mutant ends VERIFIED. Three
checks were appended to `conformance.py` (`G: a damaged first read`); run r13 then repeated all 991 mutants against the final tests and `L1431_c01` is KILLED.

## What r11 taught (fixed by tests, not by code)

The new code had no test for: the exact 1,000 ms limit of the in-flight undo record and of the toggle, the clock that goes back, the unknown layout and the key without an id, the
100-character limit with an undo in flight, the loss of the credit by every outcome but VERIFIED, the one-character manual record, the quarantine and the closed gate of `toggle()`,
the bounded list of exceptions, the simulated field's own contract (a selection is a user event, M1 keeps it, the forward fault), the manual transaction's capability, modifier,
element, rollback and verification branches, and the fourth re-enabling of a macOS tap (sticky). Block `G` of `conformance.py` pins each; 38 of the 79 r11 survivors were killed by it.

## Invariants and fuzzing

`conformance.py` checks, on every case, the invariants of plan section L3 (I1 to I6): no key lost or duplicated by the engine,
`convert` only at `s ≥ λ` with gate ALLOW, word length at most 20 keys or reset, snapshot lifetime at most 10 s and 100
characters, no snapshot after a context break, gate change or layout change, and undo equal to the recorded keys rendered with the
recorded layout. Full-size runs on the final files (`N = 1,000,000` events per group), normal and `python -O`:

| command | output |
|---|---|
| `python3 conformance.py 1000000` | `OK (9223227 checks, 1821 single and double faults, 3402 fuzz conversions, 1105 fuzz undos)` |
| `python3 -O conformance.py 1000000` | `OK (9223227 checks, 1821 single and double faults, 3402 fuzz conversions, 1105 fuzz undos)` (the same number of checks: none disappears under `-O`) |

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
