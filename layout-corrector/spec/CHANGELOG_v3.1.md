# Changelog v3 → v3.1

Specification: `TZ_layout_correction_v3.md` (Markdown export of the Claude Docs artifact, title "Technical Specification v3.1").
Reference code: `../reference/` (`lfengine.py` = sections 20.2 to 20.11 and 20.14, `vectors.py`, `vectors_out.json`, `conformance.py`).
Plan and findings: `FIX_AND_AUDIT_PLAN_v3.1.md` (plan revision 1.3), `AUDIT_REVIEW_v3_2026-10-29.md` (A-01 to A-08), `OPTIMIZATION_REVIEW_v3_2026-10-29.md` (O-1 to O-5).

## Evidence levels used below

| Level | Meaning |
|---|---|
| `TEXT_FIXED` | The normative prose says it. |
| `REFERENCE_VERIFIED` | The reference code and its tests prove the rule (`python3 conformance.py` and `python3 -O conformance.py`, same number of checks; `vectors.py`; `test_ref.py`). |
| `INTEGRATION_VERIFIED` | A real adapter was tested on the target OS and applications. **Not reachable in the cloud session.** |
| `RELEASE_GATE_PASSED` | The release criteria were met on real data and devices. **Not reachable in the cloud session.** |

No finding below is at `INTEGRATION_VERIFIED` or higher. v3.1 is an internally consistent, tested specification and reference engine, not a finished product.

## Findings of the first review (A-, O-)

| Finding | What changed | Where (spec / code) | Level |
|---|---|---|---|
| A-01, O-1 integrity guarantee vs M2 | Two guarantees: G-EVENT (physical events are neither lost nor duplicated) and G-FIELD (the content of the field). Four outcomes `VERIFIED`, `RESTORED`, `UNRECOVERED`, `ABORTED`. Adapter capabilities `READ_RANGE`, `REPLACE_RANGE`, `READBACK`, `ROLLBACK`, `SYNTHETIC_INPUT`. AUTO needs the first four; M2 (synthetic input) never gives AUTO, only `MANUAL_ONLY`. The transaction freezes the word, takes a last look at the user's keys before the first synthetic event, verifies the whole fragment and the caret, rolls back once (M1 only), and quarantines the application after a failure. | 13.2, 13.5, 13.6 (RT-4, RT-12, RT-18), 13.7, 20.14 | `TEXT_FIXED`, `REFERENCE_VERIFIED` (57 table rows and 1,665 single and double faults) |
| A-02, O-3 G2 used EV-1 on synthetic data | Gate renamed **G2-proxy**: synthetic sets and `R-CAL` only, never `R-ACC`; it does not pass EV-1 or EV-12. EV-1 and EV-12 are decided only at G4 on the frozen `R-ACC`. The cluster rule is named a *conservative cluster criterion* (a decision rule, not an exact confidence interval). Its behaviour under clustered errors is simulated with pre-registered scenarios and seeds. | 11.2, 11.3, 16.1, 16.2, 18.9; `audit/L6_ev1_simulation.py` | `TEXT_FIXED`, `REFERENCE_VERIFIED` (simulation: false acceptance at twice the limit at most 3.5%, power 81 to 94% at 2e-5) |
| A-03, O-2 Windows layout identified by the low word of the HKL | Layout identity is the **fingerprint**: SHA-256 of the 94 key states produced by `ToUnicodeEx` for the HKL of the foreground thread, flag 4 (no keyboard-state change, Windows 10 1607+). KLID is a diagnostic only and takes no part in the AUTO decision. An unknown fingerprint means OFF. macOS mechanism chosen by spike S-6. | 13.5 (row 7), 13.6 (RT-15), 13.7, 20.14 (`layout_fingerprint`, `identify_layout`) | `TEXT_FIXED`, `REFERENCE_VERIFIED` (fingerprints and a single-entry-change test); Windows and macOS behaviour is a spike (S-2, S-6) |
| A-04 undo snapshot lifetime vs buffer reset | The word buffer and the Undo snapshot are separate. The snapshot lives in memory only, at most 10 s and 100 characters, and is destroyed by a context break, a layout change, a gate or mode change, a gap, a failed outcome, and process exit. It never reaches logs or crash dumps (RT-17). | 13.2, 13.3, 13.4, 13.6, 20.7 (`Engine`) | `TEXT_FIXED`, `REFERENCE_VERIFIED` |
| A-05, O-4 calibration package not fully validated | Strict LFC1: every required field, both scorer kinds, all directions and buckets, finite and positive numbers, closed ranges, duplicate JSON keys refused, `pi_train_counts` as integers, `two_key_allow` as a JSON array of unique two-character case-folded strings. An invalid package is refused as a whole: no `Engine`, mode `MANUAL_ONLY`. | 10.1, 20.5 (`check_calibration_package`) | `TEXT_FIXED`, `REFERENCE_VERIFIED` (negative tests for every rule) |
| A-06 `w` is an observed rate | `w` is estimated from last-word manual conversions only, per context class, with a 90% cluster-bootstrap interval; D5 stores `w_ship`, the lower end; point estimate and upper end go to the report D6; EV-1 is computed with `w_ship`. | 10.2, 11.5 | `TEXT_FIXED` (needs real R-NAT data to produce numbers) |
| A-07 token formula and Caps Lock | `shift_bit = raw_shift XOR (caps AND key in L)`, with L the 33 keys that are letters in at least one layout; seven keys are letters only on the Russian layout; the test vectors cover Caps Lock on all of them. | 5.1, 20.2 | `TEXT_FIXED`, `REFERENCE_VERIFIED` |
| A-08 `pi_train` example differs from the explanation | `pi_train_counts` are integers; the shares are derived by code and checked with a tolerance of 1e-9; the example in 10.1 uses the same counts. | 10.1, 20.5 | `TEXT_FIXED`, `REFERENCE_VERIFIED` |
| O-5 end-to-end latency | Seven phases (event, context, decision, read, write, verify, rollback) P1 to P7, each measured on each reference device; the report template has one row per phase. | 7.5, 15.1, 15.3, 16.1 | `TEXT_FIXED` (measurement on devices pending) |

## Findings of the three reviews of the plan (P-, Q-, R-)

| Finding | Change | Level |
|---|---|---|
| P-1 variant A for M2 | AUTO requires all four capabilities; M2 is `MANUAL_ONLY`. | `TEXT_FIXED`, `REFERENCE_VERIFIED` (`engine_mode` truth table, all 2^5 × 3 × 2^6 combinations) |
| P-3 fault injection | `SimField` and `run_transaction` with a fault matrix; invariants checked on every row and on an exhaustive sweep of single and double faults. | `REFERENCE_VERIFIED` |
| P-6 negative tests under `-O` | No `assert` in the reference code or in the tests; one check function `T()`; `python3 -O conformance.py` gives the same number of checks as `python3 conformance.py`. | `REFERENCE_VERIFIED` |
| P-7 four evidence levels | Defined in 16.1; used throughout. | `TEXT_FIXED` |
| Q-1 to Q-9 | KLID diagnostic only; table of control classes by write result; unified policy for a bad LFC1 package; `w_ship`; L6 scenarios; RT-16 delivery test; macOS listen-only tap; one L4 card per API. | `TEXT_FIXED` (L4 report in `audit/`) |
| R-1 M2 race between the last read and `SendInput` | A last look before the first synthetic event aborts when a user key has arrived (`ABORTED`, `typed_ahead`, nothing sent). A key after that look cannot be detected; it ends `UNRECOVERED` with quarantine, and RT-4 measures how often. | `TEXT_FIXED`, `REFERENCE_VERIFIED` (M2 race at each of the 14 events) |
| R-2 M1 read-back of the whole fragment and the exact caret | The read-back covers `new + " " + typed-ahead`; the caret is exactly `c` without user keys and between `c` and `c + k` with `k` keys; rollback and classification work on the whole fragment. Selection state is a requirement on the adapter (13.2). | `TEXT_FIXED`, `REFERENCE_VERIFIED` |
| R-3 canary compares events, not counts | Events are matched by signature (scan code, extended flag, direction) in either order within 300 ms; injected events are excluded; reasons `canary_missing` and `canary_extra`; three matched pairs after a reinstall re-arm the hook. Key auto-repeat: spike S-3 decides whether the two sources agree. | `TEXT_FIXED`, `REFERENCE_VERIFIED` |
| R-4 application matrix | D6 and the release criteria report, per OS, how many of the 15 applications are `AUTO`, `MANUAL_ONLY` and OFF. Testing 15 applications is not evidence of AUTO in 15. The minimum number for release is the product owner's decision. | `TEXT_FIXED` |
| R-5, R-6 L4 | W5e corrected to `CONFIRMED`; Apple pages added; one card per API with a source class. | `audit/L4_platform_api_audit.md` rev 2 |
| R-7, R-8 | `two_key_allow` strictness; no `assert` in the binary loaders (the loaders raise `FormatError`). | `REFERENCE_VERIFIED` |
| R-10 L6 generator | Numeric parameters and the script are fixed. | `audit/L6_ev1_simulation.py` |

### Fourth review of the work (T-1 to T-4)

| Item | Change | Level |
|---|---|---|
| T-1 hook health: the 300 ms window at the moment of matching | `_meet` first lets the watchdog catch up (`check(ts)`) and matches two events only when their times differ by at most `CANARY_MS`; a late counterpart gives `canary_missing` or `canary_extra` at once, with one `gap`. | `TEXT_FIXED`, `REFERENCE_VERIFIED` (both arrival orders, 300 and 301 ms, expiry by a later event of the same side, clock skew both ways, re-arming; four vectors) |
| T-2 L6 generator broke its own caps | The weights are fitted so that no user exceeds 10% and no document 2% after every normalisation; every run checks the integer word counts (no violation in 360,000 runs); the simulation calls the reference `ev1_pass`; all runs repeated; section 18.9 rewritten with the new figures (false acceptance at twice the limit at most 3.3%, bound 3.64%; power 86 to 88%). | `TEXT_FIXED`, `REFERENCE_VERIFIED` |
| T-3 L3 report on the final code | Mutation run r8 on the final code (708 mutants, none sampled): 674 killed, **95.2%**, so the plan's 95% is met literally on all mutants; the report names the full SHA-1 and SHA-256 of the audited files and the commit `053489e504766b11b96d689c5db89eaaef276451`. The 34 survivors are classified with executable evidence (16 are the same program, 13 equal up to rounding, 2 impossible ties, 1 redundant, 2 outside the contract). The earlier figure of 93.2% belonged to an old revision and is withdrawn. | `REFERENCE_VERIFIED` (`audit/L3_mutation_and_fuzz.md`, `audit/L3/`) |
| T-3 finding F-1 (from the run before r8) | `poisson_upper(k, conf)` returned a wrong limit silently for a confidence above 0.99995 (fixed search interval). EV-1 uses 0.95 only, so no decision was affected. Fixed in 20.9 and `lfengine.py` (the interval grows, the domain is checked); 13 checks added to group P15 of `conformance.py` together with the other gaps of that run. | `REFERENCE_VERIFIED` |
| T-4 evidence | `.github/workflows/layout-corrector.yml` runs the reference checks and verifies `audit/MANIFEST.sha256`; `audit/L7_check_spec_blocks.py` compares the code blocks of the specification with the reference files byte for byte; the manifest is built last by `audit/make_manifest.sh`; the historical introduction of the plan (e37c5d8, rev 117) is marked as the starting point; the reports of lines L1 to L10 are in `audit/`. | `TEXT_FIXED`, `REFERENCE_VERIFIED` |

### State of the general audit (lines L1 to L10)

`audit/README.md` lists every line with its report. Closed: L2, L3, L4 (as a document audit), L5, L6, L7, L8, L10. **Not closed:** L1 (round 1 was partial: see `audit/L1/L1_report.md`; its three text gaps were fixed in rev 295: the row formats of the vectors in 20.12, the EV-1 bound for no false correction in 11.3, the 20-key rule of `tokens`) and L9 (the attacks are the author's own, not an independent review). The audit is therefore **not complete**.

Also fixed while transferring the code into the text: engine modes other than AUTO record nothing (13.5, `Engine.on_event`, with a test and a fuzz invariant); the undo returns the recorded keys rendered with the recorded layout.

## What v3.1 does not prove

1. Real calibration and acceptance data (`R-CAL`, `R-ACC`): EV-1 and EV-12 are not decided.
2. Latency on the two reference devices.
3. Operating-system adapters: spikes S-1 to S-7, including Raw Input against the low-level hook, SendInput under UIPI, the macOS tap, and `UCKeyTranslate` against `NSEvent.characters(byApplyingModifiers:)`.
4. The real number of applications in `AUTO` per OS; M2 race window and key auto-repeat behaviour in the canary (RT-4, RT-16).
5. Corpus versions, hashes and licences (8.9), crash-dump policy on real systems (RT-17).
   Open items of the audit that are P2 and not closed in the cloud: `WittenBell.fit` does not validate a multiplicity of at least 1 (L3, F-3; a production implementation must); the attacks B1 (a key that types nothing between the write and the read-back) and B2 (stale offsets of M1) are described in 13.2 and measured by RT-4 but have no automated test of their own; two instances of the application, fast user switching and remote-desktop sessions are not yet requirement lines (L9, section P2).
6. L1 round 2 (an independent re-implementation that also sees `vectors.py` and section 7.7) and an independent review for L9.
7. The workflow `.github/workflows/layout-corrector.yml` runs `conformance.py` (normal and with `-O`), `vectors.py` at ten hash seeds against the expected JSON, `test_ref.py` and the byte-for-byte comparison of the code blocks of section 20 with `reference/`; it passed on GitHub on Python 3.9, 3.11 and 3.13 (run 41965561463, commit 5df564b). The older workflow `tests.yml` belongs to the application `punto.py` on branches main and develop and fails on the retired macOS 13 image; it is not part of this work. CI does not run the mutation test, the EV-1 simulation or the audit scripts of `audit/`. `audit/MANIFEST.sha256` records the files and hashes of the audited revision.
