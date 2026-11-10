"""End-to-end fuzz: Engine + run_transaction + a field, with an independent oracle.
A user types words (each word entirely on one layout, no Backspace) into a SimField; the harness plays the role of the
runtime: it feeds the Engine, runs the transaction on CONVERT with the keys typed ahead, reports the outcome, and honours
a quarantine (on an incident the application goes to gate DENY, as 13.2 step 6 says).  Perturbations are inserted at
random places: break events inside a word (the caret does not move: Shift, an arrow pair), focus flicker (gate UNKNOWN for
the first keys of a word), mode flip (MANUAL_ONLY -> AUTO in the middle of a word), the undo chord, layout changes.
Oracle (independent of the engine): the number of characters in the field equals the number of keys the user typed
(no key lost or duplicated, a conversion keeps the length) and NO token of the field mixes Latin and Cyrillic letters
(every word was typed on one layout, so a mixed token is a half-converted word made by the tool).
Usage: python3 attack_pipeline_fuzz.py [words=20000] [seed=1] [perturb=1]"""
import sys, os, random, collections
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "reference"))
import lfengine as L

M1 = {L.READ_RANGE, L.REPLACE_RANGE, L.READBACK, L.ROLLBACK}
EN_L = "abcdefghijklmnopqrstuvwxyz"
RU_L = "абвгдеёжзийклмнопрстуфхцчшщъыьэюя"


def script(tok):
    s = set()
    for c in tok:
        if "a" <= c.lower() <= "z":
            s.add("lat")
        elif "а" <= c.lower() <= "я" or c in "ёЁ":
            s.add("cyr")
    return s


def run(words, seed, perturb=True, quarantine=True):
    rnd = random.Random(seed)
    e = L.Engine(L.example_cal(), lambda ids: [-3, 9, -2] if rnd.random() < 2 else None, {})   # always "wrong layout"
    f = L.SimField("", M1)
    f.pos = 0
    typed = 0
    now = 1000
    st = collections.Counter()
    first_bad = {}
    last_decision = None
    gate_state = "ALLOW"

    def ev(kind, key=None, lay=None):
        nonlocal now
        now += rnd.choice((20, 60, 150))
        return e.on_event(L.Event(kind, key, lay, now))

    carry, carry_lay = [], None
    checked = 0
    for w in range(words):
        lay = carry_lay or rnd.choice(("en", "en", "ru"))
        alpha = EN_L if lay == "en" else RU_L
        word = "".join(rnd.choice(alpha) for _ in range(rnd.randrange(3, 9)))
        keys = L.keys_from_text(word, lay)
        seen = list(carry)
        carry = []
        dark = 0
        if perturb and rnd.random() < 0.12:                       # focus flicker: the first `dark` keys are not seen by the engine
            dark = rnd.randrange(1, len(keys))
            e.set_gate("UNKNOWN")
        mode_flip_at = rnd.randrange(1, len(keys)) if perturb and rnd.random() < 0.05 else None
        break_at = rnd.randrange(1, len(keys)) if perturb and rnd.random() < 0.08 else None
        if dark or mode_flip_at:
            seen = []                                             # set_gate / set_mode empty the engine's buffer
        if mode_flip_at:
            e.set_mode("MANUAL_ONLY")
        for i, k in enumerate(keys):
            if i == dark and dark:
                e.set_gate("ALLOW")                               # the verdict arrives in the middle of the word
            if i == mode_flip_at:
                e.set_mode("AUTO")                                # the hook is trusted again in the middle of the word
            if i == break_at:
                ev("break"); seen = []                            # e.g. Shift+arrow / arrow pair: the caret is where it was
            f.type_user(L.render_key(k, lay)); typed += 1
            if i >= dark and (mode_flip_at is None or i >= mode_flip_at):
                seen.append(k)
            ev("key", k, lay)
        f.type_user(" "); typed += 1
        d = ev("space", None, lay)
        if d is not None and d.action == "CONVERT" and quarantine is not None:
            nahead = rnd.choice((0, 0, 0, 1, 2, 3, 5))
            old = L.render(seen, lay)
            ahead_keys = L.keys_from_text("".join(rnd.choice(alpha) for _ in range(nahead)), lay)
            ahead = ""
            for k in ahead_keys:
                f.type_user(L.render_key(k, lay)); typed += 1; ahead += L.render_key(k, lay)
                ev("key", k, lay)
            carry, carry_lay = list(ahead_keys), (lay if ahead_keys else None)
            old = L.render(seen, lay)
            before = f.text
            r = L.run_transaction(f, old, d.replacement, ahead, mode="AUTO")
            e.on_outcome(r.outcome)
            st[r.outcome] += 1
            if r.incident and quarantine:
                e.set_gate("DENY")                               # 13.2 step 6: quarantine
                f2 = f
                e.set_gate("ALLOW") if rnd.random() < 0.0 else None
                gate_state = "DENY"
                break
            if r.outcome == "VERIFIED" and rnd.random() < 0.2:    # the user presses the undo chord
                txt = e.undo(now + 10)
                if txt is not None:
                    st["undo"] += 1
        # oracle after every word
        toks = f.text.split(" ")
        for ti in range(checked, len(toks) - 1):
            if len(script(toks[ti])) > 1:
                cause = "gate/mode transition" if (dark or mode_flip_at) else ("break in word" if break_at else "none of the perturbations")
                st["MIXED-SCRIPT TOKEN after " + cause] += 1
                first_bad.setdefault(cause, (seed, w, toks[ti], "field tail: " + f.text[-50:]))
        checked = max(checked, len(toks) - 1)
        if len(f.text) != typed:
            st["LENGTH MISMATCH"] += 1
            first_bad.setdefault("length", (seed, w, len(f.text), typed))
            break
    return st, first_bad


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    perturb = (sys.argv[3] != "0") if len(sys.argv) > 3 else True
    tot, bad, words = collections.Counter(), {}, 0
    s = seed
    while words < n:
        st, fb = run(min(400, n - words), s, perturb)
        tot.update(st); words += 400; s += 1
        for k, v in fb.items():
            bad.setdefault(k, v)
    print("words", words, "perturb", perturb, dict(tot))
    for k, v in bad.items():
        print("  first", k, v)
