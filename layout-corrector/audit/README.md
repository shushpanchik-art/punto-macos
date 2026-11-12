# Audit of specification v3.1: state of the lines

The plan is `../spec/FIX_AND_AUDIT_PLAN_v3.1.md` (lines L1 to L10). This file says, line by line, what exists in this folder and what is
**not** closed. It is written to be checked, not to reassure: the audit is **not complete** (see the last section).

Files audited: `reference/lfengine.py` (git blob `502292ce85c50e1b40d10a8a9c8239be3defb541`, SHA-256 `4af41c76...`), `reference/conformance.py` (blob
`48eee1f5373697eb3116332abb1989590462de9a`, SHA-256 `ddcc300c...`), audited after commit `b9c44f4`; specification rev 418 (the L3 run r8 was on rev 293 and
the older code, and is history; r10 is on the current files),
whose code blocks are byte-identical to the files (L7). `MANIFEST.sha256` records the SHA-256 of every file of the audited revision;
`make_manifest.sh` builds it and the workflow checks it.

| Line | What | Report and tools | Result | State |
|---|---|---|---|---|
| L1 | Blind re-implementation from the text (Node.js) | `L1/L1_report.md` (round 1), `L1/round2/` (round 2: report, TASK, input rev 411 without code blocks, JS code, outputs) | round 2: 317 of 328 vector entries; 11 fail (LFB1/LFW1/LFL1 byte layouts and the calibration JSON form exist in the spec only as the Python code of 20.10/20.5, which is normative by 20.1); 13 findings F1 to F13 | **PARTIAL**: round 2 did not re-implement from zero (it re-read and re-ran the previous code; its own honesty statement says so), so it is not a blind result; findings F5, F6, F8, F9, F11 (prose gaps, MAYBE) and F1 to F4 (layout tables) are OPEN, F12 (counts) is fixed |
| L2 | Every number of the text recomputed | `L2_numbers_report.md`, `L2_recompute.py` | 24 checks, 0 mismatches | done |
| L3 | Mutation testing, invariants, fuzzing of the reference | `L3_mutation_and_fuzz.md`, `L3/` | run r10 on the code after L9 (blob `502292ce`, SHA-256 `4af41c76...`): 795 mutants, 760 killed = **95.6%**, 35 survivors classified; the run was done in two stages (94.0% first, then tests added and only the survivors re-run; the argument is in the report) | done on these files; void if the code changes |
| L4 | Platform API facts against primary sources | `L4_platform_api_audit.md` (rev 2) | cards W1a to W14, M1 to M12 with source class; Raw Input against the low-level hook, UIPI behaviour and others stay spikes S-1 to S-7 | done as a document audit; the spikes need real systems |
| L5 | Traceability of every requirement identifier | `L5_traceability_report.md`, `L5_trace.py`, `L5_matrix.csv` | no identifier referenced but undefined, none defined but unreferenced, 0 requirements without a verifying test | done |
| L6 | EV-1 decision rule under clustering (simulation) | `L6_ev1_simulation.py`, `.json`; section 18.9 of the text | 36 cells × 10,000 runs, 0 cap violations; false acceptance at twice the limit at most 3.3%; power 86 to 88% | done (synthetic data only) |
| L7 | The repository equals the document; reproducibility | `L7_reproducibility_report.md`, `L7_check_spec_blocks.py`, `L7_run_all.sh`, the workflow | blocks byte-identical; vectors identical at ten hash seeds; same check count with `-O` | done |
| L8 | Stale phrases, terminology, cross-references | `L8_text_report.md`, `L8_scan.py` | 128 headings, 0 findings | done |
| L9 | What can corrupt the text or leak | `L9_fmea.md`, `L9_attacks.py`, `L9_independent/` (status table per finding at the top of `L9_independent_report.md`; command `sh L9_independent/run_all_attacks.sh`; the workflow does not run it) | independent review of 2026-11-09 (4 P1, 5 P2, about 13 P3): F1 to F9 and F11 fixed in code, tests (group P17), text (13.2 to 13.4, RT-22 to RT-25); the attack scripts re-run on the final code: 0 silent corruption except the documented residual R-1 (event between the last processed event and the freeze), R-2 (caret move that no hook sees), R-3 (focus move after the last look, depends on the adapter honouring RT-22); transaction fuzz 60,000 runs, engine fuzz 400,000 events, 0 violations | P3 items still open (clock stepped back / `ts_ms=0`, KeyError on an unknown layout id, HookHealth H-1 to H-4, repr of Event/Decision, tap re-enabling never reaching MANUAL_ONLY); **limits of independence**: the attack scripts come from the reviewer run, but the fixes, the adapted fuzz and the re-run were done by the same author, so the fixes had no second independent review |
| L10 | Manifest and the honest final report | `MANIFEST.sha256`, `make_manifest.sh`, `../spec/CHANGELOG_v3.1.md` | the manifest is built last | done once the manifest is committed |

## What is not closed

1. **L1 round 2** is not a blind result (see the table); a truly blind round on `L1/round2/spec_without_code_r411.md` (record its SHA-256) is still to be run, then findings F1 to F4 (layout tables), F5, F6, F8, F9, F11 are to be decided. L1-5 (fault names) is P3: the docstring of `SimField` is normative, and since rev 300 20.14 lists the names.
2. **L9**: no second independent review of the fixes F1 to F11; P3 items and residual risks R-1 to R-3 remain (13.2, G-FIELD).
3. L3, F-3 is closed (commit `6d7d14d`). 
4. Everything in "What v3.1 does not prove" in `../spec/CHANGELOG_v3.1.md`: real calibration and acceptance data, latency on the two devices,
   operating-system adapters and the spikes S-1 to S-7, the number of applications in `AUTO`, corpus hashes and licences, crash-dump policy.

Evidence level reached for every statement above is at most `REFERENCE_VERIFIED` (16.1 of the text); nothing is `INTEGRATION_VERIFIED`
or `RELEASE_GATE_PASSED`.
