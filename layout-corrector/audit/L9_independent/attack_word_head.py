"""F3: the transaction never looks at the character in front of the fragment.  If the engine's run is only the TAIL of the
word in the field, the tail is converted and the result is VERIFIED, leaving a half-converted word.  Two ways to get a tail:
 (a) the first key of the word was lost by the hook / tap (macOS has no canary; Windows canary needs up to 300 ms),
 (b) a context break inside a word (click or arrow into the middle of a word, paste, ...): 13.2 'A word starts with the
     first printable key after a Space or a break'.
Run: python3 attack_word_head.py"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "work"))
import lfengine as L

M1 = {L.READ_RANGE, L.REPLACE_RANGE, L.READBACK, L.ROLLBACK}
scorer = lambda ids: [-3, 9, -2]          # as in conformance.py: strongly Russian


def typed(e, text, lay="en", t=1000):
    for i, k in enumerate(L.keys_from_text(text, lay)):
        e.on_event(L.Event("key", k, lay, t + i))
    return e.on_event(L.Event("space", None, lay, t + len(text)))


def pipeline(field_text, engine_events, label):
    e = L.Engine(L.example_cal(), scorer, {})
    for ev in engine_events(e):
        pass
    return e


# (a) physical typing "ghbdtn" + Space; the hook lost the first key
e = L.Engine(L.example_cal(), scorer, {})
d = typed(e, "hbdtn")                     # what the engine saw
field = L.SimField("Hello ghbdtn ", M1)  # what the application shows
print("(a) engine decision:", d.action, d.reason, repr(d.replacement))
r = L.run_transaction(field, "hbdtn", d.replacement) if d.action == "CONVERT" else None
print("    outcome:", r and r.outcome, "field:", repr(field.text), " <== 'g' + converted tail, reported VERIFIED" if r and r.outcome == "VERIFIED" else "")

# (b) the user typed "re" (correct layout), clicked/arrowed (break), then "ghbdtn" meant as one word "reghbdtn"
e = L.Engine(L.example_cal(), scorer, {})
typed_re = [L.Event("key", k, "en", 10 + i) for i, k in enumerate(L.keys_from_text("re", "en"))]
for ev in typed_re:
    e.on_event(ev)
e.on_event(L.Event("break", None, None, 20))
d = typed(e, "ghbdtn", t=30)
field = L.SimField("Hello reghbdtn ", M1)
print("(b) engine decision:", d.action, d.reason, repr(d.replacement))
r = L.run_transaction(field, "ghbdtn", d.replacement)
print("    outcome:", r.outcome, "field:", repr(field.text))
