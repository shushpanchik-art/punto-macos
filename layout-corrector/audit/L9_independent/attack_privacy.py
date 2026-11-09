"""Privacy review of the reference code against 13.4 / RT-2 / RT-6 / RT-17.  Each item prints what it found.
 P-1 (P3) default repr of UndoSnapshot / Event / Decision / TxResult-adjacent objects: one logging call or one
         `capture_locals` crash report puts the typed word in clear text (13.4 'never logged', RT-17).
 P-2 (P3) HookHealth records the signature (scan code, extended flag, direction) of EVERY physical key, with no gate input:
         keys typed into a password field are queued (and kept up to 300 ms when the hook is slow) - RT-2 'No key MUST be
         stored, counted ... while the cached gate verdict is not ALLOW', 13.4 'the only text-derived state that outlives a
         word boundary is the undo snapshot'.  Same for 'pairs'.
 P-3 (P2) the learned-exception list holds the typed words in clear text ((direction, word) tuples), is never bounded and
         is meant to be persisted (13.3, 'encrypted at rest') while RT-6 says 'No raw typed content MUST be persisted'.
         Any word the user undoes in an ALLOW field is kept for ever, e.g. a name, a code word, a password typed in a plain field.
 P-4 (info) no zeroing: the snapshot and the buffer are released by rebinding (Python); the spec asks for overwriting with
         zeros (13.4).  A native implementation must do it; nothing in the reference tests it.
Run: python3 attack_privacy.py"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "work"))
import lfengine as L

scorer = lambda ids: [-3, 9, -2]
SECRET = "ghbdtn"


def word(e, text, t0=1000):
    for i, k in enumerate(L.keys_from_text(text, "en")):
        e.on_event(L.Event("key", k, "en", t0 + i))
    return e.on_event(L.Event("space", None, "en", t0 + 50))


e = L.Engine(L.example_cal(), scorer, {})
d = word(e, SECRET)
print("P-1 repr(snapshot) =", repr(e.snapshot)[:140])
print("    repr(decision) =", repr(d)[:140], " <- contains the converted word")
ev = L.Event("key", L.keys_from_text("g", "en")[0], "en", 5)
print("    repr(event)    =", repr(ev), " <- the physical key of one keystroke")

print("P-2 HookHealth with a password field in focus (the class has no gate input):")
hh = L.HookHealth()
for i, sc in enumerate((34, 35, 48, 32, 20, 49)):                       # scan codes of 'g h b d t n', typed in a password field
    hh.raw_key(2000 + i * 20, ("scan", sc, "down"))                     # the hook is slow: it reports nothing within the window
print("    raw_only queue holds", len(hh.raw_only), "signatures of keys typed in a protected field:", [s for _, s in hh.raw_only][:3], "...")
hh2 = L.HookHealth()
hh2.raw_key(3000, ("scan", 34, "down"))
print("    even in the healthy case the first side to report is queued:", hh2.raw_only, "(stored key while the gate verdict is DENY)")

print("P-3 exception list:")
e = L.Engine(L.example_cal(), scorer, {})
d = word(e, SECRET)
e.undo(2000)
print("    engine.exceptions =", e.exceptions, "(plain text; no hashing, no LRU bound, no clear)")
e2 = L.Engine(L.example_cal(), scorer, {}, exceptions=e.exceptions)
print("    the set is what a persistent store would serialise; the reference has a hashed alternative (LEX_TAGS exc_en2ru) that is not used by Engine")
