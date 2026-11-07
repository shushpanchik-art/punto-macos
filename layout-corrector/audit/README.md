# Audit of specification v3.1: state of the lines

The plan is `../spec/FIX_AND_AUDIT_PLAN_v3.1.md` (lines L1 to L10). This file says, line by line, what exists in this folder and what is
**not** closed. It is written to be checked, not to reassure: the audit is **not complete** (see the last section).

Files audited: `reference/lfengine.py` (git blob `6c5fc74041e38623b93b5641088673450258464f`), `reference/conformance.py` (blob
`1c1f761a4e7cb38a2ddac39938f8d9d11839004a`), first commit holding them `053489e504766b11b96d689c5db89eaaef276451`; specification rev 295,
whose code blocks are byte-identical to the files (L7). `MANIFEST.sha256` records the SHA-256 of every file of the audited revision;
`make_manifest.sh` builds it and the workflow checks it.

| Line | What | Report and tools | Result | State |
|---|---|---|---|---|
| L1 | Blind re-implementation from the text (Node.js) | `L1/L1_report.md`, `L1/run_vectors.js`, `L1/run_output.txt` | 292 of 309 vector entries, 25 of 29 keys; 3 text gaps fixed in rev 295, 2 accepted or open (P3) | **PARTIAL**: round 1 on a reduced input (no `vectors.py`, no 7.7), interrupted by the usage limit; round 2 open |
| L2 | Every number of the text recomputed | `L2_numbers_report.md`, `L2_recompute.py` | 24 checks, 0 mismatches | done |
| L3 | Mutation testing, invariants, fuzzing of the reference | `L3_mutation_and_fuzz.md`, `L3/` | 708 mutants, 674 killed = **95.2%** (criterion 95% met literally); one real defect found and fixed (`poisson_upper`); 34 survivors classified; F-3 open (P2) | done, with F-3 open |
| L4 | Platform API facts against primary sources | `L4_platform_api_audit.md` (rev 2) | cards W1a to W14, M1 to M12 with source class; Raw Input against the low-level hook, UIPI behaviour and others stay spikes S-1 to S-7 | done as a document audit; the spikes need real systems |
| L5 | Traceability of every requirement identifier | `L5_traceability_report.md`, `L5_trace.py`, `L5_matrix.csv` | no identifier referenced but undefined, none defined but unreferenced, 0 requirements without a verifying test | done |
| L6 | EV-1 decision rule under clustering (simulation) | `L6_ev1_simulation.py`, `.json`; section 18.9 of the text | 36 cells × 10,000 runs, 0 cap violations; false acceptance at twice the limit at most 3.3%; power 86 to 88% | done (synthetic data only) |
| L7 | The repository equals the document; reproducibility | `L7_reproducibility_report.md`, `L7_check_spec_blocks.py`, `L7_run_all.sh`, the workflow | blocks byte-identical; vectors identical at ten hash seeds; same check count with `-O` | done |
| L8 | Stale phrases, terminology, cross-references | `L8_text_report.md`, `L8_scan.py` | 128 headings, 0 findings | done |
| L9 | What can corrupt the text or leak | `L9_fmea.md`, `L9_attacks.py` | 60,000 random attacks, 0 violations; P2 list (B1 test, two instances, fast user switching, remote desktop) | done by the author of the text, **not independent** |
| L10 | Manifest and the honest final report | `MANIFEST.sha256`, `make_manifest.sh`, `../spec/CHANGELOG_v3.1.md` | the manifest is built last | done once the manifest is committed |

## What is not closed

1. **L1 round 2** (independent re-implementation with `vectors.py` and section 7.7 in the input). Round 1 is partial.
2. **L9 by an independent reviewer.** Every attack in L9 is the author's own.
3. **L3, F-3**: `WittenBell.fit` does not validate a multiplicity of at least 1 (P2).
4. Everything in "What v3.1 does not prove" in `../spec/CHANGELOG_v3.1.md`: real calibration and acceptance data, latency on the two devices,
   operating-system adapters and the spikes S-1 to S-7, the number of applications in `AUTO`, corpus hashes and licences, crash-dump policy.

Evidence level reached for every statement above is at most `REFERENCE_VERIFIED` (16.1 of the text); nothing is `INTEGRATION_VERIFIED`
or `RELEASE_GATE_PASSED`.
