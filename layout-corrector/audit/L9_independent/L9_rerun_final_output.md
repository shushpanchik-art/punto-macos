# L9 re-run of all attack scripts on the final code

Commit (code under test): ba604f16173db55de69363343aedf40e9197aebf  (working tree dirty: 0 files)
lfengine.py sha256: 7d4b7f679c20b9133f74d4caecbe6c5e68427a36f74baeff3c256572684c1a62
conformance.py sha256: 074cc2847a6ce11817be13a2f69e6542099b3ef2962e7a556303c49b6b14f1f2
Python: Python 3.13.17
Date: 2026-11-12T20:59:28Z

## attack_caret_anchor.py
```
M1 + arrow key (counted)         -> ABORTED    typed_ahead  field='ghbdtn ghbdtn '  
M1 + pointer press (counted, contract 20.14) -> ABORTED    typed_ahead  field='ghbdtn ghbdtn '  
M1 + caret move no hook sees (RESIDUAL, 13.2) -> VERIFIED   ok           field='привет ghbdtn '  <== SILENT WRONG WORD (only the documented residual may print this)
M2 + caret move no hook sees (RESIDUAL, 13.2) -> VERIFIED   ok           field='привет ghbdtn '  <== SILENT WRONG WORD (only the documented residual may print this)
M2 + arrow key (counted)         -> ABORTED    typed_ahead  field='ghbdtn ghbdtn '
exit=0
```
RUNNER attack_caret_anchor.py: ok; residual lines (R-2): 2; known open (P3): none

## attack_engine_fuzz.py
```
events/steps 400000 conversions 51840 {} {}
E-2 layout id None -> on_event RAISED KeyError None | run already flushed: True
E-2 layout id 'de' -> on_event RAISED KeyError 'de' | run already flushed: True
exit=0
```
RUNNER attack_engine_fuzz.py: ok; residual lines (R-2): 0; known open (P3): ['E-2 unknown layout id raises KeyError (P3)']

## attack_engine_state.py
```
== F6: snapshot exists before the replacement has happened
   decision: CONVERT | snapshot alive before any write; undo() -> None | exception added: False | field still 'ghbdtn '
   then the transaction runs: VERIFIED -> field 'привет ' | snapshot: UndoSnapshot(<6 keys, en2ru, confirmed=True>) (the user's undo was consumed, the word is now a permanent exception, the conversion stands)
   worker error between decision and outcome: snapshot alive = True , credit = 0 (a conversion that never happened earns the run prior)
== F7: incident does not stop the engine
   outcome RESTORED quarantine flag True | engine.mode = AUTO | next word decision: None | engine.quarantined = True (a second transaction would start on a quarantined application)
== F8: layout change seen only in key.layout
   word dropped (skip = True ) snapshot alive = False after_switch = False (13.3: a layout change destroys the snapshot)
   whole next word in other layout: snapshot alive = False after_switch = False
== F9: Backspace in a dropped word
   after 9 Backspaces (field text would be empty) snapshot alive = False (a Backspace on an empty buffer is a break, except inside a dropped word)
== F10: clock
   undo with now earlier than the replacement (clock stepped back 1 h): None
   (control) a later event expires it: True
   ts_ms=0 event after a snapshot (non-monotonic input) leaves it alive: True
== F11: exception list bound
   10050 undone words -> len(exceptions) = 10000 (spec: at most 10,000, least-recently-used eviction)
exit=0
```
RUNNER attack_engine_state.py: ok; residual lines (R-2): 0; known open (P3): none

## attack_focus_switch.py
```
(a) other field, different caret
   outcome=ABORTED echo_mismatch  A(original field)='Hello ghbdtn '  B(other)='user@example.org' (was 'user@example.org')
(b1) other field, caret differs by one
   outcome=ABORTED echo_mismatch  A(original field)='Hello ghbdtn '  B(other)='Hello abcdef  ' (was 'Hello abcdef  ')
(b2) other field, same length and caret
   outcome=ABORTED gate_changed  A(original field)='Hello ghbdtn '  B(other)='Hello abcdef ' (was 'Hello abcdef ')
(c) other element is a password field
   outcome=ABORTED echo_mismatch  A(original field)='Hello ghbdtn '  B(other)='hunter2!hunter2' (was 'hunter2!hunter2')
   reads performed on the secure element: 0
exit=0
```
RUNNER attack_focus_switch.py: ok; residual lines (R-2): 0; known open (P3): none

## attack_fuzz_transaction.py
```
runs 60000 {'VERIFIED': 22446, 'ABORTED': 30903, 'RESTORED': 2394, 'UNRECOVERED': 4257}
exit=0
```
RUNNER attack_fuzz_transaction.py: ok; residual lines (R-2): 0; known open (P3): none

## attack_gate_midword.py
```
(a) focus: gate UNKNOWN -> ALLOW in the middle of the word
   engine saw 'hbdtn' -> CONVERT score_above_threshold
   transaction: ABORTED echo_mismatch   field='Hello ghbdtn '   
(b) mode MANUAL_ONLY -> AUTO in the middle of the word
   engine saw 'hbdtn' -> CONVERT score_above_threshold
   transaction: ABORTED echo_mismatch   field='Hello ghbdtn '   
   HookHealth at the Space: ok=True (the loss is declared only after 300 ms)
(c) the hook lost the first key, Space within 300 ms (canary not fired yet)
   engine saw 'hbdtn' -> CONVERT score_above_threshold
   transaction: ABORTED echo_mismatch   field='Hello ghbdtn '   
silent half-converted words: 0 of 3
exit=0
```
RUNNER attack_gate_midword.py: ok; residual lines (R-2): 0; known open (P3): none

## attack_hookhealth.py
```
fuzz runs 20000 {'undeclared_loss': 0, 'false_alarm': 0} first seeds: {} (undeclared losses are repeated-signature masking, H-1: a lost key paired with a later key of the same signature)
H-1 repeated key hides a loss
   at 350 ms ok = True | at 401 ms ok = False (the loss is declared 300 ms after the 2nd key)
H-2 raw side without injected flag
   ok at 1400 ms: False reason: canary_missing gap pending: True
H-3 reinstalled() while healthy erases evidence
   ok at 2000 ms: True (the lost key is never declared)
H-4 macOS: unlimited re-enabling
   tap disabled 10 times in a row, reinstalled each time: ok after reinstall 10 of 10 (spec: MANUAL_ONLY after the 3rd in 60 s)
exit=0
```
RUNNER attack_hookhealth.py: ok; residual lines (R-2): 0; known open (P3): ['H-4 tap re-enabled without MANUAL_ONLY (P3)']

## attack_m2_arrow_midbatch.py
```
(1) word at the start of the field, ONE Left arrow before event 1
    UNRECOVERED verify_failed incident=True  field='привет  '  expected 'привет '
(2) word at the start of the field, ONE Left arrow before event 9
    UNRECOVERED verify_failed incident=True  field='ривет п'  expected 'привет '
(3) 'Hello ' in front, Left x2 before event 1 and Right x2 before event 7
    UNRECOVERED verify_failed incident=True  field='Hellonпривет '  expected 'Hello привет '
(4) control: 'Hello ' in front, ONE Left arrow before event 3
    UNRECOVERED verify_failed incident=True  field='Helloпривет t'  expected 'Hello привет '
silent corruptions: 0 of 4
exit=0
```
RUNNER attack_m2_arrow_midbatch.py: ok; residual lines (R-2): 0; known open (P3): none

## attack_neighbour_damage.py
```
damage before: RESTORED  verify_failed incident=True
   before: 'Hello, ghbdtn '
   after : 'Hello,?ghbdtn '
damage after : RESTORED  verify_failed incident=True
   before: 'Hello ghbdtn  and the rest of the sentence'
   after : 'Hello ghbdtn #and the rest of the sentence'
exit=0
```
RUNNER attack_neighbour_damage.py: ok; residual lines (R-2): 0; known open (P3): none

## attack_nonadapter_exception.py
```
M1 replace raises OSError after a partial write -> returned TxResult(outcome='RESTORED', reason='write_error', method='M1', incident=True, quarantine=True)
M2 send raises OSError in the middle of the batch -> returned TxResult(outcome='UNRECOVERED', reason='write_error', method='M2', incident=True, quarantine=True)
exit=0
```
RUNNER attack_nonadapter_exception.py: ok; residual lines (R-2): 0; known open (P3): none

## attack_pending_state.py
```
control: word B alone (default prior)
   B decision: KEEP abstain margin -1.59
(1)+(2) A pending, B decided meanwhile, then A is ABORTED
   A: CONVERT | B: KEEP abstain | engine.credit while A has no outcome: 0
   after on_outcome(ABORTED of A): snapshot of B = None credit = 0
   B is KEEP (abstain): it did not use a run prior that A never earned (closed by 20.7 since rev 306)
(3) undo before the outcome
   undo() -> None | exception added: False | cool_words = 0
   then the transaction: VERIFIED field='привет ' (the word is converted AND an exception)
(4) a non-AdapterError between decision and outcome
   snapshot alive: True credit: 0 -> undo(): None (a conversion that never happened)
exit=0
```
RUNNER attack_pending_state.py: ok; residual lines (R-2): 0; known open (P3): none

## attack_pipeline_fuzz.py
```
words 20000 perturb True {'VERIFIED': 9157, 'undo': 1909, 'ABORTED': 2126}
exit=0
```
RUNNER attack_pipeline_fuzz.py: ok; residual lines (R-2): 0; known open (P3): none

## attack_privacy.py
```
P-1 repr(snapshot) = UndoSnapshot(<6 keys, en2ru, confirmed=False>)
    repr(decision) = Decision(action='CONVERT', reason='score_above_threshold', replacement='привет', margin=0.8931441493827936, n_keys=6)  <- contains the converted word
    repr(event)    = Event(kind='key', key=Key(id=30, shift=False, caps=False), layout='en', ts_ms=5)  <- the physical key of one keystroke
P-2 HookHealth with a password field in focus (the class has no gate input):
    raw_only queue holds 6 signatures of keys typed in a protected field: [('scan', 34, 'down'), ('scan', 35, 'down'), ('scan', 48, 'down')] ...
    even in the healthy case the first side to report is queued: [(3000, ('scan', 34, 'down'))] (stored key while the gate verdict is DENY)
P-3 exception list:
    engine.exceptions = set() (plain text; no hashing, no LRU bound, no clear)
    the set is what a persistent store would serialise; the reference has a hashed alternative (LEX_TAGS exc_en2ru) that is not used by Engine
exit=0
```
RUNNER attack_privacy.py: ok; residual lines (R-2): 0; known open (P3): ['P-2 HookHealth queues signatures in a DENY gate (P3)']

## attack_undo_commit.py
```
(a) 10 characters typed after the conversion (inside the 100-key window)
   undo text 'ghbdtn' -> restore transaction: ABORTED typed_ahead | field='Hello привет abcdefghij'
   engine: exception learned = False | cool_words = 0 | snapshot alive = True | second chord returns 'ghbdtn' (a retry is possible when the snapshot lives)
(b) the application changed the converted word (echo_mismatch)
   undo text 'ghbdtn' -> restore transaction: ABORTED echo_mismatch | field='Hello ПРивет '
   engine: exception learned = False | cool_words = 0 | snapshot alive = True | second chord returns 'ghbdtn' (a retry is possible when the snapshot lives)
(c) the gate is no longer ALLOW (focus moved to a protected element)
   undo text 'ghbdtn' -> restore transaction: ABORTED gate_changed | field='Hello привет '
   engine: exception learned = False | cool_words = 0 | snapshot alive = True | second chord returns 'ghbdtn' (a retry is possible when the snapshot lives)
exit=0
```
RUNNER attack_undo_commit.py: ok; residual lines (R-2): 0; known open (P3): none

## attack_word_head.py
```
(a) engine decision: CONVERT score_above_threshold 'ривет'
    outcome: ABORTED field: 'Hello ghbdtn ' 
(b) engine decision: CONVERT score_above_threshold 'привет'
    outcome: ABORTED field: 'Hello reghbdtn '
exit=0
```
RUNNER attack_word_head.py: ok; residual lines (R-2): 0; known open (P3): none

RUNNER SUMMARY: 15 scripts, 0 with unexpected results
