"""Reference (oracle) implementation of the deterministic parts of the layout-correction engine.

Pure Python 3.9+, no dependencies. Everything here is normative for section 20 of the specification:
key tables, key tokens, Caps Lock handling, rendering, boundary handling, candidate enumeration,
calibrated scoring and the decision procedure. The classifier itself is injected as a function.
"""
import math
from dataclasses import dataclass
from typing import Callable, List, Optional, Sequence, Tuple

EN, RU = "en", "ru"
OTHER_LAYOUT = {EN: RU, RU: EN}

# ---- key tables: 47 physical keys, ids 0..46 (appendix 19.1) ------------------------------------------
EN_UNSHIFT = "`1234567890-=" + "qwertyuiop[]\\" + "asdfghjkl;'" + "zxcvbnm,./"
EN_SHIFT   = "~!@#$%^&*()_+" + "QWERTYUIOP{}|" + 'ASDFGHJKL:"' + "ZXCVBNM<>?"
RU_UNSHIFT = "ё1234567890-=" + "йцукенгшщзхъ\\" + "фывапролджэ" + "ячсмитьбю."
RU_SHIFT   = 'Ё!"№;%:?*()_+' + "ЙЦУКЕНГШЩЗХЪ/" + "ФЫВАПРОЛДЖЭ" + "ЯЧСМИТЬБЮ,"
TABLE = {EN: (EN_UNSHIFT, EN_SHIFT), RU: (RU_UNSHIFT, RU_SHIFT)}
assert all(len(x) == 47 for t in TABLE.values() for x in t)

PAD, BOS, EOS, VOCAB = 0, 95, 96, 97
MAX_KEYS = 20


@dataclass(frozen=True)
class Key:
    """One printable key event: physical key id 0..46, raw Shift state, raw Caps Lock state."""
    id: int
    shift: bool = False
    caps: bool = False


def is_letter_in(layout: str, key_id: int) -> bool:
    return TABLE[layout][0][key_id].isalpha()


LETTER_KEYS = frozenset(k for k in range(47) if is_letter_in(EN, k) or is_letter_in(RU, k))
assert len(LETTER_KEYS) == 33


def effective_shift(k: Key, layout: str) -> bool:
    """Case of the key as it is rendered in `layout`: Caps Lock flips Shift only on keys that are letters there."""
    return k.shift ^ (k.caps and is_letter_in(layout, k.id))


def render_key(k: Key, layout: str) -> str:
    return TABLE[layout][1 if effective_shift(k, layout) else 0][k.id]


def render(keys: Sequence[Key], layout: str) -> str:
    return "".join(render_key(k, layout) for k in keys)


def token(k: Key) -> int:
    """Model token of a key: layout independent. Caps Lock flips Shift on every key that is a letter in either layout."""
    s = k.shift ^ (k.caps and k.id in LETTER_KEYS)
    return 1 + 2 * k.id + int(s)


def tokens(core: Sequence[Key], complete: bool = True) -> List[int]:
    """BOS + up to 20 key tokens (+ EOS only when the word is complete and not truncated)."""
    ks = [token(k) for k in core[:MAX_KEYS]]
    out = [BOS] + ks
    if complete and len(core) <= MAX_KEYS:
        out.append(EOS)
    return out


def keys_from_text(text: str, layout: str) -> List[Key]:
    """Test helper: the key events that display `text` in `layout` (Shift only, Caps Lock off)."""
    idx = {}
    for k in range(47):
        idx[TABLE[layout][0][k]] = Key(k, False)
    for k in range(47):
        idx.setdefault(TABLE[layout][1][k], Key(k, True))
    return [idx[c] for c in text]


# ---- candidates (section 5.3) ------------------------------------------------------------------------
TRAIL_PUNCT = frozenset(".,;:!?\"')]}")
LEAD_OPEN = frozenset("([{\"'")
MAX_TRAIL = 2


@dataclass(frozen=True)
class Candidate:
    lead: Tuple[Key, ...]    # peeled leading opener (0 or 1 key)
    core: Tuple[Key, ...]    # the keys that are classified
    trail: Tuple[Key, ...]   # peeled trailing punctuation (0..2 keys)


def candidate(run: Sequence[Key], target: str) -> Optional[Candidate]:
    """The word candidate for the hypothesis 'the user meant `target`', or None if the run is not eligible.

    Punctuation is judged by what a key IS in the target layout. The seven letter-keys are therefore letters
    (never peeled) when the target is Russian, and punctuation when the target is English. One leading opener
    and up to two trailing punctuation keys are peeled; every remaining key must be a letter in the target
    layout. The result is unique, so there is exactly one candidate (or none) per hypothesis.
    """
    body = tuple(run)
    lead: Tuple[Key, ...] = ()
    if body and render_key(body[0], target) in LEAD_OPEN and not is_letter_in(target, body[0].id):
        lead, body = body[:1], body[1:]
    p = 0
    while p < min(MAX_TRAIL, len(body)):
        k = body[len(body) - 1 - p]
        if render_key(k, target) in TRAIL_PUNCT and not is_letter_in(target, k.id):
            p += 1
        else:
            break
    core = body[:len(body) - p]
    trail = body[len(body) - p:]
    if not core or not all(is_letter_in(target, k.id) for k in core):
        return None
    return Candidate(lead, tuple(core), tuple(trail))


def shape_is_other(core: Sequence[Key], target: str) -> bool:
    """Guard 'token shape' on the target reading: a lower-case letter followed by an upper-case letter (camelCase)."""
    s = render(core, target)
    return any(s[i - 1].islower() and s[i].isupper() for i in range(1, len(s)))


# ---- calibrated scoring (section 10.1) ---------------------------------------------------------------
CLASSES = ("EN", "RU", "OTHER")


def log_softmax(z: Sequence[float], temp: float = 1.0) -> List[float]:
    z = [v / temp for v in z]
    m = max(z)
    lse = m + math.log(sum(math.exp(v - m) for v in z))
    return [v - lse for v in z]


def deployment_prior(active: str, pi_wrong: float, other_share: float) -> List[float]:
    """pi_dep over (EN, RU, OTHER) given the active layout and the probability that this word is wrong-layout."""
    if active == EN:      # RU intended = wrong layout; EN/OTHER are typed correctly
        return [(1 - pi_wrong) * (1 - other_share), pi_wrong, (1 - pi_wrong) * other_share]
    return [pi_wrong * (1 - other_share), 1 - pi_wrong, pi_wrong * other_share]


def score(logits: Sequence[float], active: str, cal: dict, pi_wrong: float, scorer_kind: str = "network") -> float:
    """Log-odds that the intended text is NOT the active layout's language ('Russian or not' in both directions)."""
    lp = log_softmax(logits, cal["temperature"][scorer_kind])
    prior = deployment_prior(active, pi_wrong, cal["other_share"])
    lp = [a + math.log(b) - math.log(c) for a, b, c in zip(lp, prior, cal["pi_train"])]
    lse = max(lp) + math.log(sum(math.exp(v - max(lp)) for v in lp))
    lp = [v - lse for v in lp]                      # renormalise
    ru, other = lp[1], _lse(lp[0], lp[2])
    return ru - other if active == EN else other - ru


def _lse(a: float, b: float) -> float:
    m = max(a, b)
    return m + math.log(math.exp(a - m) + math.exp(b - m))


def logit(p: float) -> float:
    return math.log(p / (1 - p))


def bucket(n_keys: int) -> Optional[str]:
    if n_keys <= 1:
        return None
    if n_keys == 2:
        return "2"
    if n_keys <= 4:
        return "3-4"
    if n_keys <= 7:
        return "5-7"
    return "8+"


# ---- decision (section 20.3) -------------------------------------------------------------------------
@dataclass
class Decision:
    action: str                 # "CONVERT" or "KEEP"
    reason: str
    replacement: Optional[str] = None   # full replacement text of the run in the target layout
    margin: Optional[float] = None
    n_keys: Optional[int] = None


def decide(run: Sequence[Key], active: str, cal: dict, scorer: Callable[[List[int]], Sequence[float]],
           pi_wrong: float, previous_converted: bool = False, exceptions=frozenset(),
           lexicon: Optional[dict] = None, scorer_kind: str = "network") -> Decision:
    """The normative decision for one word run (the keys typed since the last boundary), taken at Space or Tab.

    Guards that need the operating system (secure fields, application blacklist, context breaks, cool-down)
    run before this function and never reach it.
    """
    target = OTHER_LAYOUT[active]
    lexicon = lexicon or {EN: frozenset(), RU: frozenset(), "acronyms_en": frozenset(), "acronyms_ru": frozenset()}
    direction = f"{active}2{target}"
    cand = candidate(run, target)
    if cand is None:
        return Decision("KEEP", "no_eligible_candidate")
    n = len(cand.core)
    typed_core = render(cand.core, active).casefold()
    if (direction, typed_core) in exceptions:
        return Decision("KEEP", "user_exception", None, None, n)
    b = bucket(n)
    if b is None:
        return Decision("KEEP", "one_key", None, None, n)
    if shape_is_other(cand.core, target):
        return Decision("KEEP", "token_shape", None, None, n)
    text = render(cand.lead + cand.core + cand.trail, target)
    if b == "2":
        ok = (render(cand.core, target).casefold() in cal["two_key_allow"][direction] and previous_converted
              and typed_core not in lexicon[active] and typed_core not in lexicon["acronyms_" + active])
        return Decision("CONVERT", "two_key_allow_list", text, None, n) if ok else Decision("KEEP", "two_key_rule", None, None, n)
    if typed_core in lexicon["acronyms_" + active]:
        return Decision("KEEP", "acronym", None, None, n)
    s = score(scorer(tokens(cand.core, True)), active, cal, pi_wrong, scorer_kind)
    margin = s - logit(cal["thresholds"][direction][b])
    if margin >= 0:
        return Decision("CONVERT", "score_above_threshold", text, margin, n)
    return Decision("KEEP", "abstain", None, margin, n)
