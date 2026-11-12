# L9 independent safety and privacy report (original review on spec rev305; status refreshed on the final code)

## Static audit on commit ae89222: six items (added 2026-11-12, code commit ba604f1)

These came from a reading of code and text, not from a runtime reproduction by the reviewer. Each was first re-checked by me on HEAD; the "reproduce" column names the command that shows the discrepancy on ae89222 (`git checkout ae89222 -- layout-corrector/reference` then run) and the test that now covers it (group A1 to A6 at the end of `conformance.py`; `python3 conformance.py` from `layout-corrector/reference`).

| # | Verdict | Evidence on ae89222 | Fix and check |
|---|---|---|---|
| 1 RESTORED at undo | **confirmed** | `run_transaction` returns RESTORED always with `quarantine=True` and `incident=True` (lfengine.py, step 7 of the transaction), but `Engine.undo_outcome` left the snapshot alive and the exception unquarantined unless the caller passed the flag, and the text of 13.3 and the F9 test (`quarantine=(oc == "UNRECOVERED")`) described a state that the real path never produces | RESTORED and UNRECOVERED imply the quarantine in `on_outcome` and `undo_outcome` (`INCIDENT_OUTCOMES`): snapshot destroyed, nothing learned, no second chord. ABORTED keeps the snapshot (retry). The test now takes the flag from the real TxResult (A1, F9, R10); vectors_out.json row "undo ended RESTORED" changed; 13.3 rewritten |
| 2 Manual selection | **confirmed**, a contract was missing | text of 13.3 said a manual conversion "follows the transaction of 13.2", but that transaction needs an empty selection (the adapter raises otherwise) and a fragment ending with the user's Space; no reference path wrote over a selection, `manual_convert` is a pure function | `run_manual_transaction` (20.14) for `selection` (exact text, no Space, no typed-ahead) and `last_word` (word ending at the caret, white space before it), M1 and M2, neighbours compared before and after, rollback as in 13.2; `Adapter.selection()`, `SimField.select`; limit 10,000. 13.3 and RT-26 rewritten. Tests A2 run both forms on both methods with 12 fault cases |
| 3 Snapshot 20 vs run 64 | **confirmed** (text) | 13.4 said "one converted word of at most 20 keys", the engine stores the whole run up to `MAX_BUF = 64` and the conformance test itself asserts `<= MAX_BUF`; the model sees only the first 20 keys (MD-5) | no code change: runs of 21 to 64 keys are decided on their first 20 keys and the whole run is undoable. 13.4 now says 64; tests A3 convert and undo 20, 21, 40 and 64 keys through the real transaction and check 65 keys = KEEP overflow with no snapshot. Residual: the decision on a 21 to 64 key word rests on 20 keys (documented in 7.3) |
| 4 Retention | **confirmed** | `Engine.undoing` held the full `UndoSnapshot` (every key) after the snapshot was dropped by a gate or mode change, a quarantine or a timeout, and was never cleared if the outcome did not arrive | the record is now a keyless copy (direction, case-folded word); it is discarded at once by gate change, mode change, quarantine and a non-VERIFIED outcome, after 1,000 ms (`UNDO_OUTCOME_MS`), and kept (still keyless) across expiry and event-stream context events so that a VERIFIED undo is still learned. Tests A4. Limit: the case-folded word stays in memory for at most 1 s in that path |
| 5 L9 runner | **confirmed** | `run_all_attacks.sh` printed `exit=$?` and always exited 0; a failing script or a printed SILENT line did not change its status | `run_all_attacks.py` classifies every script (non-zero exit, Traceback, SILENT CORRUPTION/WRONG WORD/HALF-CONVERTED, VIOLATION, non-zero counters are UNEXPECTED; the two documented R-2 lines are counted as residual; known P3 findings are printed as KNOWN) and exits 1 on any unexpected result; `--selftest` runs three deliberately bad scripts and one clean one and requires 3 rejections and 1 acceptance (PASSED). The shell script keeps the runner's status. Still true: exit 0 proves only that nothing unexpected was printed, the scripts do not assert everything |
| 6 Undo boundaries | **not confirmed** as a bug, text and test gaps | `tick` drops at `now - created > 10000` and `_count_char` at `after > 100`, so both limits are inclusive, and the old tests checked `tick` and the snapshot but not the chord; the text did not say "inclusive" | text says inclusive; tests A6 call the chord at 9,999, 10,000 and 10,001 ms and after 99, 100 and 101 keys and Spaces (Backspaces do not count) |

Checks on the final code: `python3 conformance.py` and `-O`: OK (1,863,419 checks, 1821 faults, 638 fuzz conversions, 207 fuzz undos); `python3 conformance.py 1000000`: OK (9,223,026 checks, 3,402 fuzz conversions, 1,105 fuzz undos); `test_ref.py` OK; vectors identical under hash seeds 0 to 9; L7: all four blocks IDENTICAL on doc rev 454; `sh L9_independent/run_all_attacks.sh`: 15 scripts, 0 unexpected, exit 0; `--selftest` PASSED.

Not done or still open after these items: the toggle "immediately after a manual conversion converts back and adds the word to the exception list" (13.3 table) has no reference code; 13.7 and the capability table do not yet list `selection()` as an adapter query (it is in the 20.14 contract and in 13.3); the mutation run r10 was made on the code before these changes and is **void** (no new run was made, see the README); the independence limits above apply to these fixes too, they were made and tested by the same author.

## Status on the final code (added 2026-11-12)

Code under test: commit of the re-run header in `L9_rerun_final_output.md`; `lfengine.py` sha256 `4af41c76efefbc7d48dc26c696f15822dd447d726cc02813e17fb0673c3eae5f`, `conformance.py` sha256 `ddcc300c3fca57983bbbe6c411c9bfd1368f3f11eb85e64c8d28e2f0e124e580`; spec doc rev 418 (L7: all four code blocks IDENTICAL). The text below this section is the review as written on rev305 and is history. Where an old script caption contradicts the numbers printed (for example "the user's undo was consumed", "a second transaction would start on a quarantined application", "a conversion that never happened earns the run prior"), the printed numbers are the result and the caption is stale: after the fixes `undo()` returns None before VERIFIED, `exception added: False`, credit 0, and the next decision on a quarantined application is `None`. No stale caption was taken as a confirmed bug.

Exact commands (from the repository root, run on the commit named in the output file):
- `cd layout-corrector/reference && python3 conformance.py` and `python3 -O conformance.py`: both print `OK (1863346 checks, 1821 single and double faults, 641 fuzz conversions, 207 fuzz undos)`.
- `sh layout-corrector/audit/L9_independent/run_all_attacks.sh > layout-corrector/audit/L9_independent/L9_rerun_final_output.md`: runs all 15 scripts, 15 of 15 exit 0, raw output saved.
- The workflow `layout-corrector.yml` does **not** run these scripts (they print, they do not assert); a green CI is therefore not evidence for L9. The evidence is the conformance groups P16/P17 (which CI does run) plus the saved raw output.

| Finding | Status | Check on the final code |
|---|---|---|
| F1 caret anchor (P1) | fixed; residual R-2 accepted | `attack_caret_anchor.py`: the counted arrow key and pointer press give ABORTED typed_ahead; the caret move that no hook sees still gives VERIFIED with a wrong word (the line is marked RESIDUAL). Conformance P17 |
| F2 M2 arrow mid-batch (P1) | fixed | `attack_m2_arrow_midbatch.py`: 0 silent corruptions of 4 (UNRECOVERED with incident); `attack_fuzz_transaction.py` 60,000 runs, 0 violations (3 only with `EVENTS_IN_MARK=1`, the residual R-1) |
| F3 word head (P1) | fixed | `attack_word_head.py`, `attack_gate_midword.py`: ABORTED echo_mismatch, field unchanged, 0 silent half-converted words; `attack_pipeline_fuzz.py` 20,000 words |
| F4 focus switch (P1) | fixed for a conforming adapter; residual R-3 | `attack_focus_switch.py`: 0 reads and 0 writes on the other element, never VERIFIED. A non-conforming adapter is not modelled |
| F5 non-AdapterError (P2) | fixed | `attack_nonadapter_exception.py`: M1 partial write gives RESTORED with incident and quarantine, M2 mid-batch gives UNRECOVERED with incident and quarantine |
| F6 neighbour damage (P2) | fixed | `attack_neighbour_damage.py`: both damages end RESTORED verify_failed with incident |
| F7 engine state at the decision (P2) | fixed | `attack_engine_state.py` F6 section, `attack_pending_state.py`: snapshot unconfirmed, undo None, credit 0 until VERIFIED |
| F8 incident does not stop the engine (P2) | fixed | `attack_engine_state.py` F7 section: next decision None, quarantined True until `release_quarantine` |
| F9 undo commits early (P2) | fixed | `attack_undo_commit.py`: ABORTED gate_changed, exception not learned, cool-down 0, snapshot alive, a second chord is possible |
| P3 F8 layout id only in a key, P3 F9 Backspaces in a dropped word | fixed | `attack_engine_state.py`: snapshot dropped in both |
| P3 F10 clock stepped back, `ts_ms=0` | **open** | `attack_engine_state.py` F10: undo still works with a stepped-back clock; a `ts_ms=0` event leaves the snapshot alive |
| P3 F11 exception list bound | fixed | 10,050 undone words give 10,000 entries (LRU) |
| P3 E-2 unknown layout id | **open** | `attack_engine_fuzz.py`: KeyError for None and 'de' after the run was flushed |
| P3 H-1 repeated key hides a loss, H-2, H-3, H-4 | **open** (not touched) | `attack_hookhealth.py` as printed: H-1 declared 300 ms late, H-3 evidence erased, H-4 tap re-enabled 10 of 10 times without MANUAL_ONLY. Fuzz: 0 false alarms, 0 undeclared losses except H-1 masking |
| P3 privacy P-1 repr | **partly fixed** | the repr of `UndoSnapshot` shows only the number of keys, direction and confirmed flag; the repr of `Decision` still contains the converted word and the repr of `Event` the physical key (open) |
| P3 privacy P-2 HookHealth queues signatures in a DENY gate | **open** | `attack_privacy.py`: scan codes of a password field are queued for up to 300 ms. The reference cannot close this: the class has no gate input |
| P3 privacy P-3 exceptions are a plain set in memory | open, requirement | bounded now; no hashing or persistence in the reference |

**R-2, stated plainly.** A caret move that neither a key nor a pointer press counted (a program, an assistive tool, remote input) before step 3 can make an identical earlier word the converted fragment and the outcome is VERIFIED with a wrong field. The reference cannot detect it: it sees only counted events and reads. It is documented in 13.2 (G-FIELD) and measured only by RT-4 on a real adapter. R-1 (an event between the last processed event and the freeze) and R-3 are the other two residuals.

**Limits of independence.** The original attacks and findings came from a separate review run. The fixes, the adapted fuzz scripts (`mark()` injects events only with `EVENTS_IN_MARK=1`; the engine fuzz was changed for the new undo semantics) and this re-run were done by the author of the code, so nothing here is a second independent review of the fixes.


Baseline: `python3 conformance.py 20000` prints OK (204771 checks). All scripts import lfengine from work/ (copy of in/).
Run any script with `python3 attack_X.py`; each prints the outcome. Nothing below is reported unless the script reproduced it.

## (a) Attack families and results

| Family | Script | Runs | Result |
|---|---|---|---|
| Transaction fuzz, cell-identity oracle, random user/silent/arrow/click/Backspace/Delete/outside edits + adapter faults, M1 and M2 | attack_fuzz_transaction.py | 60000 (25966 VERIFIED, 26235 ABORTED, 3239 RESTORED, 4560 UNRECOVERED) | 49 violations, all VERIFIED with wrong field; all reduce to F1 / F2 (caret moved without being counted); no lost or duplicated typed-ahead key found with counted keys |
| Engine fuzz with shadow model of snapshot rules | attack_engine_fuzz.py | 400000 events, 49451 conversions | 4459 snapshots alive after a layout id change inside a word without a `layout` event (F8); KeyError on unknown layout id (E-2) |
| End-to-end pipeline (Engine + transaction + field + quarantine) | attack_pipeline_fuzz.py | 20000 words | 169 mixed-script tokens (118 after gate/mode transition, 51 after break in word) = F3 |
| HookHealth fuzz vs oracle | attack_hookhealth.py | 20000 | 0 false alarms, 0 undeclared losses except repeated-signature masking (H-1) |
| Targeted: focus switch, neighbour damage, non-AdapterError, pending state, undo commit, gate mid-word, M2 arrow mid-batch, privacy | the other attack_*.py | about 40 hand-built scenarios | findings below |

Did not break: counted keys typed ahead during M1/M2 (no loss, no duplication), rollback after counted-key faults, M2 abort on typed-ahead, HookHealth false alarms, plain Caps Lock/shift case handling in the transaction.

## (b) Findings

### F1 (P1) Caret read at step 3 is the only anchor
Spec 13.2: nothing outside the fragment is written; the key counter of step 1 detects user keys. Code: if the caret moves between freeze and caret read (arrow key, or mouse click which is never counted) onto an identical earlier word, the earlier word is converted, outcome VERIFIED.
Script attack_caret_anchor.py. Output: `M1 + arrow key -> VERIFIED ok field='привет ghbdtn '` (also mouse M1, M2). Why: wrong word silently changed. Regression: for each variant `T(not(res.outcome=="VERIFIED" and field!="ghbdtn привет "), "caret moved before read: never VERIFIED with wrong word")`; fix: re-read caret after the read and compare with the count and the mark, ABORT on any mismatch.

### F2 (P1) M2 arrow key between synthetic events (also Home/End)
Spec 13.2: the remaining race ends in UNRECOVERED and quarantine, never silent VERIFIED. The reference test's fault key does not move the caret; a real arrow does. Script attack_m2_arrow_midbatch.py. Output: `(1) VERIFIED ok incident=False field='привет  ' expected 'привет '`; `(3) VERIFIED field='Hellonпривет '`. Regression: add a SimField fault `arrow` (moves caret) before each of 14 events; `T(outcome!="VERIFIED" or field==expected, ...)`. Fix: step 5 must require caret exactly at start+len(new)+tail and compare the whole fragment, not accept c<=caret<=c+k.

### F3 (P1) Tail of a word converted (word head missing)
Spec 13.2: a word starts with the first printable key after Space or a break; 13.1: gate verdict UNKNOWN->ALLOW mid-word. Cases: gate UNKNOWN->ALLOW mid-word, MANUAL_ONLY->AUTO mid-word, first key lost by the hook (canary needs 300 ms), click/arrow into a word. The transaction matches only old+" " before the caret and never inspects the character before the fragment. Scripts attack_gate_midword.py, attack_word_head.py. Output: `VERIFIED ok field='Hello gривет '`; `field: 'Hello reпривет '`; 3 of 3 half-converted; pipeline fuzz 169 hits. Regression: `T(not(res.outcome=="VERIFIED" and field_has_mixed_script_token), ...)`; fix: the engine must discard a run that did not start at a boundary (mark run "headless" on gate/mode transition and on any break), and the transaction must read one character before the fragment and require a boundary.

### F4 (P1) Focus moves between step 3 and step 4; the adapter has no element identity
Spec 13.2 promises nothing outside the fragment is written; 20.14 contract has no element id. Script attack_focus_switch.py. Output: (a) other field `user@eghbdtn.org` destroyed, UNRECOVERED; (b2) same length and caret in another field -> `VERIFIED ok`, other field `Hello привет `; (c) secure element read twice (privacy: password field content read, `hunterghbdtner2` written). Regression: SimField with element switch fault; `T(other_field_unchanged and secure_reads==0, ...)`. Fix: adapters return an element token with every read, write and readback; transaction aborts on change; gate recheck right before step 4 and the write call receives the token.

### F5 (P2) Non-AdapterError escapes run_transaction
Spec RT-7: any error after step 4 began ends in RESTORED or UNRECOVERED with notice, incident, quarantine. Code catches only AdapterError. Script attack_nonadapter_exception.py. Output: `RAISED OSError; field now 'Hello приdtn '`, `field now 'Hello п'`, no TxResult, no incident. Regression: adapter raising OSError/RuntimeError after write begins; `T(isinstance(res,TxResult) and res.outcome in("RESTORED","UNRECOVERED"), ...)`. Fix: catch Exception after step 4, rollback, report.

### F6 (P2) Damage outside the fragment is invisible to step 5
Spec RT-4 counts silent corruption of neighbours. Script attack_neighbour_damage.py. Output: `before 'Hello, ghbdtn ' -> after 'Hello,?привет '` VERIFIED; tail `#and the rest...` VERIFIED. Fix: read one character before and a bounded tail after, compare. (Applies only when the application touches neighbours; P2 hardening.)

### F7 (P2) Engine state is created at the decision, not at VERIFIED
Spec 13.2 step 7: snapshot only for VERIFIED. Scripts attack_engine_state.py (F6 section) and attack_pending_state.py. Output: undo before the outcome returns 'ghbdtn' and adds a permanent exception while the field then becomes 'привет '; run credit (prior 0.25) earned by A applies to B, B's conversion `ghbdtn непривет` after A is ABORTED; after non-AdapterError snapshot and credit stay alive. Fix: carry a transaction id in decision and on_outcome; create snapshot and credit in on_outcome(VERIFIED) only.

### F8 (P2) Incident does not stop the engine
Spec 13.2 step 6 / RT-7 quarantine. attack_engine_state.py F7: after RESTORED/UNRECOVERED `engine.mode=AUTO` and the next word is CONVERT at once; quarantine is only a flag in TxResult. Fix: engine consumes the flag and switches the gate to DENY for the app.

### F9 (P2) Undo commits side effects before the restoring transaction
Spec 13.3 window 10 s / 100 keys; the transaction can restore only 3 typed-ahead keys. Script attack_undo_commit.py. Output: with 10 characters typed, ABORTED typed_ahead, field `Hello привет abcdefghij`, but exception learned, cool-down 3 words, snapshot dropped, second chord returns None. Also echo_mismatch and gate_changed cases. Fix: commit only on VERIFIED undo, keep the snapshot on ABORTED, align the key window with what can be restored.

### P3 hardening (reproduced)
- attack_engine_state.py F8: layout change carried only in a key's layout id leaves snapshot alive. F9: 9 Backspaces in a dropped word leave snapshot alive. F10: undo with a stepped-back clock still works; ts_ms=0 event does not expire. F11: exception list unbounded (10050 entries; spec max 10000 LRU).
- attack_engine_fuzz.py E-2: unknown layout id (None, 'de') raises KeyError in the worker after the run was flushed.
- attack_hookhealth.py H-1 loss hidden by a repeated key is declared 300 ms after the second key (Space in the window passes); H-2 raw side without injected flag only reports later; H-3 reinstalled() while healthy erases evidence of a lost key; H-4 macOS tap disabled 10 times in a row, reinstalled each time, never MANUAL_ONLY (spec: after the 3rd in 60 s).
- Privacy, attack_privacy.py: P-1 default repr of UndoSnapshot/Event/Decision contains the converted word and physical keys (RT-17 'never logged': one log line or crash dump leaks); P-2 HookHealth queues signatures (scan codes) of every key, including in a DENY (password) gate, up to 300 ms, no gate input; P-3 exceptions are plain-text words in a set (no hash, no bound). Fix: `__repr__` returning a redacted form, gate input to HookHealth, hashed exception store.
- Exception messages and quarantine/incident records in the reference carry reason codes only; no typed text found there.

Regression tests are described per finding in the style `T(cond, "what")`; each uses the scenario function of its script (all scripts are importable-free standalone, copy the setup into conformance.py).

## (c) Requirement gaps the code cannot show

- Two instances: RT-19 "at most one instance per user session ... Two instances would classify the same word twice and write twice". Reference has no lock; a real build could double-convert (corrupts text). Also a lock per session, not per machine.
- Session switching: RT-20 "Sleep, wake, lock, fast user switching and a secure desktop MUST each empty the word buffer and the undo snapshot"; the Engine has no session event other than generic break; test with a snapshot alive across the event (see P3 F8 for the analogous layout-only path).
- Remote desktop / VM: RT-21 "never ALLOW unless in the support matrix"; keys taken in one place, text in another; no code, depends on window class detection.
- IME composition and dead keys: line 1051 "IME composition, dead key ... Context break"; the adapter contract has no composition-state capability; a replacement during composition corrupts the pre-edit string.
- Secure fields: 13.1 DENY "No key is stored, counted, classified or logged"; HookHealth (P-2) and F4(c) show the reference breaks it at two places; real adapters must also not read the element value in the gate path.
- Clipboard: 13.7 "The clipboard is not used in the first release" and RT-1 forbids it in the callback; a real M1 fallback via clipboard would overwrite the user's clipboard and race with paste.
- Selections: step 3 requires empty selection; the contract has a caret but F1 shows no selection/element identity guarantee between steps.

## (d) Not examined

Real OS adapters (UIA, AX, AT-SPI, SendInput, event tap), threading and callback timing of the real hook (reference is single threaded; timing faults modelled only by step boundaries), the model/training sections (6 to 12, 14 beyond skim), persistence code (exception store, config), installer and update paths, and any behaviour of real applications (autocorrect, collaborative editors) beyond the SimField faults.
