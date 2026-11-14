"""The five write tests of 13.7 ("Write results by control class") as one routine over an abstract control, so that Windows and
macOS bindings run the same protocol and the logic is tested here with fake controls.

control interface:
  readable() -> bool                      the text can be read at all
  read() -> str                           the whole text
  set_value(text) -> bool                 whole-field write (False or an exception: refused)
  select(a, b)                            set the selection / caret
  selection() -> (a, b)
  replace(a, b, text) -> bool             replace exactly [a, b) (False or an exception: refused)
Each trial starts from a known text. Result 1 (full value), 2 (a range can be replaced: only [a, b) changed), 3 (caret and
selection are where the product needs them: the caret that stood at the end of the text stands there again; a selection of the
range stays the range), 4 (read only: reading works, every write is refused), 5 (not supported: reading fails). Result 2 needs a
verified rollback: the old text written back the same way restores the whole text, every time."""
import random

BASE = "say ghbdtn now and go ghbdtn there, ok. "


def _try(f, *a):
    try:
        return f(*a)
    except Exception:
        return False


def classify(ctl, trials=100, seed=1):
    """Returns the five booleans and the counts. Never raises for a refusing control."""
    if not _try(ctl.readable):
        return {"full_value": False, "range_replace": False, "caret_kept": False, "rollback_verified": False,
                "read_only": False, "unsupported": True, "trials": 0}
    rnd = random.Random(seed)
    full = rng = caret = back = 0
    refused = 0
    for _ in range(trials):
        if _try(ctl.set_value, BASE) is False or _try(ctl.read) != BASE:
            # the control cannot even be put into the known state by a whole-field write: try the next trial anyway
            pass
        # 1. the whole value
        ok_full = _try(ctl.set_value, BASE) is not False and _try(ctl.read) == BASE
        full += ok_full
        if not ok_full:
            refused += 1
            continue
        # 2 and 3: replace a range of the same length with different text
        n = rnd.randint(1, 10)
        a = rnd.randint(0, len(BASE) - n)
        old = BASE[a:a + n]
        new = "".join(rnd.choice("абвгде") for _ in range(n))
        _try(ctl.select, len(BASE), len(BASE))
        done = _try(ctl.replace, a, a + n, new)
        expected = BASE[:a] + new + BASE[a + n:]
        ok_rng = done is not False and _try(ctl.read) == expected
        rng += ok_rng
        caret += ok_rng and _try(ctl.selection) == (len(BASE), len(BASE))
        # rollback: the old text, written back the same way
        if ok_rng:
            _try(ctl.replace, a, a + n, old)
            back += _try(ctl.read) == BASE
    r = {"full_value": full == trials, "range_replace": rng == trials, "caret_kept": rng == trials and caret == trials,
         "rollback_verified": rng == trials and back == trials, "trials": trials,
         "counts": {"full_value": full, "range_replace": rng, "caret_kept": caret, "rollback_ok": back}}
    r["read_only"] = (not r["full_value"]) and (not r["range_replace"]) and refused == trials and _try(ctl.read) is not False
    r["unsupported"] = False
    return r
