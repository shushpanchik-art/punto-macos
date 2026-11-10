"""F-E (P2): Engine.undo() commits its side effects (exception list, cool-down, snapshot destroyed) BEFORE the restoring
transaction has run, and the outcome of that transaction is never reported back.  And the spec window (100 further keys)
is wider than what the transaction can restore (typed-ahead <= 3).
13.3: the chord within 10 s / 100 keys is an Undo: 'Restore the original keys exactly ... Add the word ... to the exception list; start the
cool-down'.  An undo that could not restore anything (ABORTED typed_ahead / echo_mismatch / gate_changed) still:
  - learns the word as a permanent exception (the user never asked for that: nothing happened),
  - starts the cool-down (3 words and 10 s without automatic correction),
  - destroys the snapshot, so a second press of the chord cannot retry (it falls through to 'manual conversion').
Variants: (a) 10 characters typed after the conversion (inside the 100-key window of 13.3);  (b) the application
autocorrects the converted word (echo_mismatch);  (c) the gate changed.
After the fix (undo_outcome): nothing is committed for ABORTED or RESTORED and the chord can be pressed again.
Run: python3 attack_undo_commit.py"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "reference"))
import lfengine as L

M1 = {L.READ_RANGE, L.REPLACE_RANGE, L.READBACK, L.ROLLBACK}
scorer = lambda ids: [-3, 9, -2]


def converted(field_after):
    e = L.Engine(L.example_cal(), scorer, {})
    for i, k in enumerate(L.keys_from_text("ghbdtn", "en")):
        e.on_event(L.Event("key", k, "en", 1000 + i))
    d = e.on_event(L.Event("space", None, "en", 1100))
    f = L.SimField("Hello ghbdtn ", M1)
    r = L.run_transaction(f, "ghbdtn", d.replacement)
    e.on_outcome(r.outcome, r.quarantine)
    return e, f, d


for label, setup in (("(a) 10 characters typed after the conversion (inside the 100-key window)", "ahead"),
                     ("(b) the application changed the converted word (echo_mismatch)", "echo"),
                     ("(c) the gate is no longer ALLOW (focus moved to a protected element)", "gate")):
    e, f, d = converted(None)
    ahead = ""
    if setup == "ahead":
        for i, ch in enumerate("abcdefghij"):
            f.type_user(ch); ahead += ch
            e.on_event(L.Event("key", L.keys_from_text(ch, "en")[0], "en", 1200 + i))
    if setup == "echo":
        f.text = "Hello ПРивет "
    if setup == "gate":
        f._gate = "DENY"
    txt = e.undo(1500)                                         # the chord: the engine answers at once
    r = L.run_transaction(f, d.replacement, txt, ahead, mode="AUTO")      # the restore transaction
    e.undo_outcome(r.outcome, r.quarantine)                    # the outcome of the RESTORE transaction (20.7, since rev 306)
    print(label)
    print("   undo text %r -> restore transaction: %s %s | field=%r" % (txt, r.outcome, r.reason, f.text))
    print("   engine: exception learned =", ("en2ru", "ghbdtn") in e.exceptions, "| cool_words =", e.cool_words,
          "| snapshot alive =", e.snapshot is not None, "| second chord returns", repr(e.undo(1600)), "(a retry is possible when the snapshot lives)")
