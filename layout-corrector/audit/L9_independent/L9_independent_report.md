# L9 independent safety and privacy report (spec rev305, reference lfengine.py)

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
