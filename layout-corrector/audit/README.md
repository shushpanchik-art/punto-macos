# Audit of specification v3.1: state of the lines

The plan is `../spec/FIX_AND_AUDIT_PLAN_v3.1.md` (lines L1 to L10). This file says, line by line, what exists in this folder and what is
**not** closed. It is written to be checked, not to reassure: the audit is **not complete** (see the last section).

Files audited: `reference/lfengine.py` (git blob `bb6f9b135c6bfa4f26b57dbc9e5eb6f902dedd2d`, SHA-256 `bf6082dc...`), `reference/conformance.py` (blob
`2a0c98132348763f51973957af016a6b697210b0`, SHA-256 `132efe38...`), first commit holding them `6d7d14d`; specification rev 305 (the L3 run r8 was on rev 293 and
the older code, and is history; r9 is on these files),
whose code blocks are byte-identical to the files (L7). `MANIFEST.sha256` records the SHA-256 of every file of the audited revision;
`make_manifest.sh` builds it and the workflow checks it.

| Line | What | Report and tools | Result | State |
|---|---|---|---|---|
| L1 | Blind re-implementation from the text (Node.js) | `L1/L1_report.md`, `L1/run_vectors.js`, `L1/run_output.txt` | 292 of 309 vector entries, 25 of 29 keys; 3 text gaps fixed in rev 295, 2 accepted or open (P3) | **PARTIAL**: round 1 on a reduced input (no `vectors.py`, no 7.7), interrupted by the usage limit; round 2 open |
| L2 | Every number of the text recomputed | `L2_numbers_report.md`, `L2_recompute.py` | 24 checks, 0 mismatches | done |
| L3 | Mutation testing, invariants, fuzzing of the reference | `L3_mutation_and_fuzz.md`, `L3/` | 718 mutants, 684 killed = **95.3%** (criterion 95% met literally); one real defect found and fixed (`poisson_upper`); 34 survivors classified; F-3 closed in code and tests | done on these files; void if the code changes |
| L4 | Platform API facts against primary sources | `L4_platform_api_audit.md` (rev 2) | cards W1a to W14, M1 to M12 with source class; Raw Input against the low-level hook, UIPI behaviour and others stay spikes S-1 to S-7 | done as a document audit; the spikes need real systems |
| L5 | Traceability of every requirement identifier | `L5_traceability_report.md`, `L5_trace.py`, `L5_matrix.csv` | no identifier referenced but undefined, none defined but unreferenced, 0 requirements without a verifying test | done |
| L6 | EV-1 decision rule under clustering (simulation) | `L6_ev1_simulation.py`, `.json`; section 18.9 of the text | 36 cells × 10,000 runs, 0 cap violations; false acceptance at twice the limit at most 3.3%; power 86 to 88% | done (synthetic data only) |
| L7 | The repository equals the document; reproducibility | `L7_reproducibility_report.md`, `L7_check_spec_blocks.py`, `L7_run_all.sh`, the workflow | blocks byte-identical; vectors identical at ten hash seeds; same check count with `-O` | done |
| L8 | Stale phrases, terminology, cross-references | `L8_text_report.md`, `L8_scan.py` | 128 headings, 0 findings | done |
| L9 | What can corrupt the text or leak | `L9_fmea.md`, `L9_attacks.py` | 60,000 random attacks, 0 violations; B1 and B2 now have regression tests (group P16); RT-19 to RT-21 (two instances, session switching, remote desktop) are requirements since rev 305 | author's own attacks (0 violations) **and** an independent review of 2026-11-09 (`L9_independent/`): 4 P1, 5 P2, about 13 P3, every script reproduced; **findings not yet fixed** |
| L10 | Manifest and the honest final report | `MANIFEST.sha256`, `make_manifest.sh`, `../spec/CHANGELOG_v3.1.md` | the manifest is built last | done once the manifest is committed |

## What is not closed

1. **L1 round 2** on an input rebuilt from the final specification edition (not the rev 287 file of round 1), without code blocks, with `vectors.py` and section 7.7; its SHA-256 is to be recorded. Round 1 is partial. L1-5 (fault names) is P3: the docstring of `SimField` is normative, and since rev 300 20.14 lists the names.
2. **L9 by an independent reviewer.** Every attack in L9 is the author's own.
2a. **L9 findings F1 to F9** (`L9_independent/L9_independent_report.md`): four P1 (wrong word converted after caret move; arrow key in the middle of M2; half-converted word when the gate turns ALLOW mid-word or the first key is lost; focus moved between steps 3 and 4) are open. Code, text and tests change next; r9 and the manifest must then be redone.
3. L3, F-3 is closed (commit `6d7d14d`). 
4. Everything in "What v3.1 does not prove" in `../spec/CHANGELOG_v3.1.md`: real calibration and acceptance data, latency on the two devices,
   operating-system adapters and the spikes S-1 to S-7, the number of applications in `AUTO`, corpus hashes and licences, crash-dump policy.

Evidence level reached for every statement above is at most `REFERENCE_VERIFIED` (16.1 of the text); nothing is `INTEGRATION_VERIFIED`
or `RELEASE_GATE_PASSED`.
