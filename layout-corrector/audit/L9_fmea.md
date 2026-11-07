# L9 safety and privacy review: what can corrupt the user's text, what can leak

Re-run on the final files: `reference/lfengine.py` (git blob `6c5fc74041e38623b93b5641088673450258464f`), `reference/conformance.py` (blob `1c1f761a4e7cb38a2ddac39938f8d9d11839004a`), first commit holding them `053489e504766b11b96d689c5db89eaaef276451`; specification rev 295. The first run of this report (rev 286, commit `5df564b`) gave the same verdicts; the figures below are those of the re-run. Author of this file: the author of the specification (the independent fresh-reviewer run of this lane could not be started: the agents stopped at the usage limit of the session three times). The attacks below are therefore the author's own, and the lane stays open for an external reviewer.

## A. Attacks on the replacement transaction (`L9_attacks.py`)

Part A: 60,000 random runs with 1 to 3 injected faults on M1 (with rollback), M1 without rollback and M2, four field shapes, typed-ahead keys. Invariants on every run: the outcome is in the vocabulary; VERIFIED means the text without the user's keys is exactly the expected text; ABORTED means nothing was written or sent; RESTORED means the original text; UNRECOVERED always carries incident and quarantine; every user key is in the field exactly once unless the outcome is UNRECOVERED. Result: **0 violations** (ABORTED 18,992, RESTORED 4,710, UNRECOVERED 10,935, VERIFIED 25,363).

Part B (faults that the vocabulary of `SimField` does not contain):

| Attack | Result | Class |
|---|---|---|
| B1 the application inserts text before the word between read and write | UNRECOVERED, quarantine; the text is damaged (`!Helloghbdtnn`) but the failure is reported, never silent. The residual window is the time between the last read and the write; RT-4 must measure it on real applications, as it does for M2 | P2: 13.2 names this window for M1 since rev 287; still no test of its own in `conformance.py` (a `SimField` fault that shifts the text before the range would add one) |
| B2 a harmless arrow-left (caret one place back) between read and verify | RESTORED and quarantine of the application | P2: safe but a false incident; one stray arrow key sends the application to OFF until the quarantine rule (13.5 row 10) releases it. 13.2 states that this is the conservative choice (rev 287); a caret that moved forward by at most the number of silent keys is tolerated and tested |
| B3 a key that types nothing (Shift) between write and verify | VERIFIED | none (the caret rule counts it) |
| B4, B5 old equal to new, empty word | VERIFIED, field unchanged | P3: the engine never makes such a call (candidates differ from the typed word) |
| B6 two dropped synthetic events (M2) | UNRECOVERED, quarantine | none |
| B7 partial write and failing rollback | UNRECOVERED, quarantine | none |

No P1 was found: in no run did a wrong text end as VERIFIED, and no loss of user text ended without UNRECOVERED and quarantine.

## B. The failure matrix of the plan against code and tests

Every row of the matrix in `spec/FIX_AND_AUDIT_PLAN_v3.1.md` is implemented in `run_transaction` and tested by P9 of `reference/conformance.py` (line 212: 57 table rows in `vectors.py`, 621 single and double faults for M1, 1,044 for M2) and by the closing blocks of P14 (lines 684 to 760: typed-ahead edges, modifier down, UIPI drop, partial batch, the M2 last look, the exact caret, the whole-fragment read-back). The two rows that depend on a real OS (one `SendInput` call is not interspersed; UIPI drops are invisible in the return value) are `INTEGRATION_VERIFIED` items, not testable here.

## C. FMEA

Columns: failure mode, effect, requirement (13.5 row, RT, CA), proof in this repository (test or vector), or S-n (spike, needs a device), or NONE.

| Failure mode | Effect on text or privacy | Requirement | Proof |
|---|---|---|---|
| Focus lost before the write | Wrong field replaced | 13.2 step 1, RT-14 | P9 row "context break"; read of the range must match, so a different field gives echo_mismatch |
| Text changed between read and write (M1) | See B1 | RT-4 | P9 (read faults), B1 above: UNRECOVERED, window measured by RT-4 |
| Partial write, application error | Half a word | RT-7 | P9 'partial', 'applied_error' rows; B7 |
| Application autocorrect | Last letter changed | RT-4 | P9 'autocorrect' rows |
| Caret or selection moved | Next typing lands elsewhere | 13.2 step 5 | P9 caret faults (back, forward, forward2); selection state is a requirement on the adapter (13.2) and needs a device test |
| User key during the transaction, M1 | Key lost or duplicated | G-EVENT, 13.2 | P9 'user:x' on read and replace; P14 M1 user-key rows |
| User key during the transaction, M2 | Plan deletes by count: wrong deletion | G-EVENT, RT-4 | R-1 tests (P14, lines 721 to 760), M2 race at each of the 14 events; residual window → UNRECOVERED, RT-4 |
| UIPI drops synthetic input | Nothing written, return value ok | RT-4 | P14 line 707 block; delivery on a real system is S-3 (13.7) |
| Modifier held down | Synthetic keys misread as shortcuts | 13.7 | P14 'modifier_down' |
| Hook silently removed | Words lose their first keys | 13.5 row 13, RT-16 | P12, P14 (lines 761 to 830); RT-16 needs devices |
| Raw Input and hook disagree | Same as above, or a false alarm | 13.5 row 13 | P12 signature tests, window tests (line 806 on) |
| Permission revoked | Observation stops | 13.5 row 14 | P7 `engine_mode` truth table (permission_ok) |
| Layout changed or unrecognised | Wrong table → wrong text | 13.5 row 7, RT-15 | P11 fingerprint tests (every single entry changed → refused) |
| Password or secure field | Typed secrets observed | RT-2, RT-9, 13.1 | P10/P13 'no state under DENY or UNKNOWN'; the gate probe needs the OS (device test) |
| Secure Event Input (macOS) | Secrets observed | 13.7 | gate DENY while it is on (13.7); no reference test |
| IME composition, dead keys | Composed text mis-replaced | 13.1 guards, RT-15 | dead-key fingerprint (RT-15); IME gate on the OS: device test |
| Clipboard | Typed text copied | RT-6 | The clipboard is not used in the first release (13.4); nothing to test; a code search in D-reviews |
| Undo after the text changed | Old text restored over new | 13.3, RT-5 | P10: snapshot destroyed by break, layout change, gap, gate, mode, outcome; 10 s and 100 characters edges (P14) |
| Calibration package corrupted or stale | Wrong thresholds | CA-9, 13.5 rows 6 and 12 | P3 (every mutation refused), P14 edges |
| Model file corrupted | Wrong scores | 13.5 row 3 | P4/P5 format errors, LFB1/LFL1/LFW1 truncation and magic tests |
| Crash during a write | Half-written word | RT-7 | UNRECOVERED path and quarantine are modelled; a real crash needs a device |
| Crash dump content | Typed text in a dump | RT-17, AP-7 | S-n: needs a real crash on a device; the product's handler excludes buffer and snapshot (requirement only) |
| Logs and telemetry | Typed text leaves the machine | RT-6 | Requirement; a scripted-session search of logs is an acceptance test (15.3), not run here |
| Held key (auto-repeat) | Many events; canary counts them | 13.5 row 13 | S-3 decides how Raw Input and the hook report repeats; no reference test |
| Caps Lock out of sync | Wrong case | 13.7 | P6 Caps Lock tokens; resync at word boundary needs the OS |
| Very long word | Buffer overflow | 13.1 | P14 64 and 65 keys |
| Digits, punctuation | Wrong candidate | 13.1 guards | P1, vectors `guards` |
| Two instances of the product | Double replacement | – | NONE: no requirement states a single instance. P2 |
| Sleep, wake, fast user switching | Stale gate, stale hook | 13.5 rows 8, 13 | NONE for fast user switching (the gate is re-evaluated per event, the canary re-arms after a reinstall; no explicit requirement). P2 |
| Remote desktop, virtual machine windows | Keys observed in one place, text in another | 13.7 | gate UNKNOWN for unknown classes (RT-9); no reference test. P2 |
| Full-screen games | Keys observed, nothing to replace | 13.8 | application matrix: OFF unless proven |

Gaps (classified): P1: none. P2: B1 (the sentence in 13.2 is written; a `SimField` fault 'shift' with a test is still missing), B2 (decided in 13.2: not tolerated, conservative), two instances, fast user switching, remote desktop windows (add one requirement line each). P3: B4 and B5.

## D. Privacy review

| Content | Where it lives | Lifetime | Disk | Spec | Test |
|---|---|---|---|---|---|
| Word buffer (keys of the current word) | Memory of the worker | until the Space, a break, a gap, a mode or gate change; at most 64 keys | no | 13.1, 13.4, RT-2 | P13 fuzz (no state under DENY, UNKNOWN or outside AUTO), P14 |
| Undo snapshot | Memory | at most 10 s and 100 characters | no | 13.3, 13.4, RT-5, RT-17 | P10 and P14 |
| Exceptions list (words the user undid) | Memory, optionally persisted | session or as the privacy setting says | see 13.3 | 13.3 | P10 |
| Logs, incident records | Counters and reasons, no text | – | opt-in, content-free | RT-6, 13.5 row 10 | acceptance test 15.3 (not run here) |
| Crash reports | Stack trace and counters | – | – | AP-7, RT-17 | needs a device |
| Clipboard | not used | – | – | 13.4 | – |
| Telemetry | none by default; opt-in and content-free | – | – | RT-6 | – |

Missing in the specification: nothing that would block v3.1; the open points are the P2 lines above.
