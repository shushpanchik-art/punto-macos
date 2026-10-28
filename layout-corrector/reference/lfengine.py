"""lfengine.py - reference (oracle) implementation of the deterministic parts of the layout-correction engine.

Pure Python 3.9+, standard library only. It is normative for section 20 of the specification: when this code
and prose disagree, the code and its test vectors win. The classifier is injected as a function.
Blocks between "# ==== 20.x" markers are published verbatim in the specification.
"""
# ==== 20.2 Key tables, tokens, Caps Lock, rendering ==================================================
import math
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, Tuple

EN, RU = "en", "ru"
OTHER_LAYOUT = {EN: RU, RU: EN}

# 47 physical keys, ids 0..46 in this order: number row (13), QWERTY row (13), home row (11), bottom row (10).
EN_UNSHIFT = "`1234567890-=" + "qwertyuiop[]\\" + "asdfghjkl;'" + "zxcvbnm,./"
EN_SHIFT = "~!@#$%^&*()_+" + "QWERTYUIOP{}|" + 'ASDFGHJKL:"' + "ZXCVBNM<>?"
RU_UNSHIFT = "ё1234567890-=" + "йцукенгшщзхъ\\" + "фывапролджэ" + "ячсмитьбю."
RU_SHIFT = 'Ё!"№;%:?*()_+' + "ЙЦУКЕНГШЩЗХЪ/" + "ФЫВАПРОЛДЖЭ" + "ЯЧСМИТЬБЮ,"
TABLE = {EN: (EN_UNSHIFT, EN_SHIFT), RU: (RU_UNSHIFT, RU_SHIFT)}
assert all(len(s) == 47 for pair in TABLE.values() for s in pair)

PAD, BOS, EOS, VOCAB = 0, 95, 96, 97
MAX_KEYS = 20


@dataclass(frozen=True)
class Key:
    """One printable key press: physical key id 0..46, raw Shift state, raw Caps Lock state."""
    id: int
    shift: bool = False
    caps: bool = False


def is_letter_in(layout: str, key_id: int) -> bool:
    return TABLE[layout][0][key_id].isalpha()


# Keys that are a letter in at least one layout (33 of 47). Caps Lock flips Shift on exactly these in the token.
LETTER_KEYS = frozenset(k for k in range(47) if is_letter_in(EN, k) or is_letter_in(RU, k))
assert len(LETTER_KEYS) == 33


def effective_shift(k: Key, layout: str) -> bool:
    """Case of the key as rendered in `layout`: Caps Lock flips Shift only on keys that are letters there."""
    return k.shift ^ (k.caps and is_letter_in(layout, k.id))


def render_key(k: Key, layout: str) -> str:
    return TABLE[layout][1 if effective_shift(k, layout) else 0][k.id]


def render(keys: Sequence[Key], layout: str) -> str:
    return "".join(render_key(k, layout) for k in keys)


def token(k: Key) -> int:
    """Layout-independent model token 1..94 = 1 + 2*id + effective shift."""
    s = k.shift ^ (k.caps and k.id in LETTER_KEYS)
    return 1 + 2 * k.id + int(s)


def tokens(core: Sequence[Key], complete: bool = True) -> List[int]:
    """BOS + at most 20 key tokens, + EOS only when the word is complete and was not truncated."""
    out = [BOS] + [token(k) for k in core[:MAX_KEYS]]
    if complete and len(core) <= MAX_KEYS:
        out.append(EOS)
    return out


def keys_from_text(text: str, layout: str) -> List[Key]:
    """Test helper: the key presses (Shift only, Caps Lock off) that display `text` on `layout`."""
    idx: Dict[str, Key] = {}
    for k in range(47):
        idx[TABLE[layout][0][k]] = Key(k, False)
    for k in range(47):
        idx.setdefault(TABLE[layout][1][k], Key(k, True))
    return [idx[c] for c in text]


# ==== 20.3 Word candidate (segmentation of one run) ==================================================
TRAIL_PUNCT = frozenset(".,;:!?\"')]}")
LEAD_OPEN = frozenset("([{\"'")
MAX_TRAIL = 2


@dataclass(frozen=True)
class Candidate:
    lead: Tuple[Key, ...]    # peeled leading opener, 0 or 1 key
    core: Tuple[Key, ...]    # the keys that are classified
    trail: Tuple[Key, ...]   # peeled trailing punctuation, 0..2 keys


def candidate(run: Sequence[Key], target: str) -> Optional[Candidate]:
    """The unique word candidate for the hypothesis 'the user meant `target`', or None.

    Punctuation is judged by what the key IS in the target layout: the seven letter-keys are letters (never
    peeled) when the target is Russian and punctuation when it is English. One leading opener and up to two
    trailing punctuation keys are peeled; every remaining key must be a letter in the target layout.
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
    core, trail = body[:len(body) - p], body[len(body) - p:]
    if not core or not all(is_letter_in(target, k.id) for k in core):
        return None
    return Candidate(lead, core, trail)


# ==== 20.4 Shape guards (no action in either direction) ===============================================
import re

DOTTED_SUFFIXES = ("com org net edu gov io ru ua by kz dev app ai co me info biz xyz tv uk de fr it es nl pl cn jp "
                   "py js ts md txt json yaml yml toml html css cpp hpp java kt go rs rb php sh sql csv xml pdf "
                   "png jpg gif svg zip tar gz log ini cfg exe dll so dylib").split()
_DOTTED = re.compile(r"^[\w-]+(\.[\w-]+)*\.(" + "|".join(DOTTED_SUFFIXES) + r")$")
_EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
ROWS = ((0, 12), (13, 25), (26, 36), (37, 46))     # first and last key id of each physical row


def keywalk(run: Sequence[Key], min_len: int = 4) -> bool:
    """True if at least `min_len` consecutive keys are neighbours on one row, all in the same direction."""
    ids = [k.id for k in run]
    for i in range(len(ids) - min_len + 1):
        w = ids[i:i + min_len]
        d = w[1] - w[0]
        if d in (1, -1) and all(w[j + 1] - w[j] == d for j in range(min_len - 1)) \
                and any(lo <= w[0] and max(w) <= hi for lo, hi in ROWS):
            return True
    return False


def shape_is_camel(core: Sequence[Key], layout: str) -> bool:
    s = render(core, layout)
    return any(s[i - 1].islower() and s[i].isupper() for i in range(1, len(s)))


def shape_guard(run: Sequence[Key], active: str, core: Sequence[Key]) -> Optional[str]:
    """Reason code of the first matching guard, else None. Texts are casefolded and read on BOTH layouts."""
    target = OTHER_LAYOUT[active]
    for text in (render(run, active).casefold(), render(run, target).casefold()):
        if "://" in text or text.startswith("www."):
            return "shape_url"
        if _EMAIL.match(text):
            return "shape_email"
        if _DOTTED.match(text):
            return "shape_dotted"
    if shape_is_camel(core, target) or shape_is_camel(core, active):
        return "shape_camel"
    if keywalk(core):
        return "shape_keywalk"
    return None


# ==== 20.5 Calibration, priors, thresholds in nats ====================================================
CLASSES = ("EN", "RU", "OTHER")
STATES = ("default", "after_switch", "run")
BUCKETS = ("3-4", "5-7", "8+")


def log_softmax(z: Sequence[float], temp: float = 1.0) -> List[float]:
    z = [v / temp for v in z]
    m = max(z)
    lse = m + math.log(sum(math.exp(v - m) for v in z))
    return [v - lse for v in z]


def _lse2(a: float, b: float) -> float:
    m = max(a, b)
    return m + math.log(math.exp(a - m) + math.exp(b - m))


def logit(p: float) -> float:
    """ln(p / (1 - p)). A threshold t on a probability is the threshold logit(t) on the score s, in nats."""
    return math.log(p / (1.0 - p))


def deployment_prior(active: str, w: float, o_lat: float) -> List[float]:
    """pi_dep over (EN, RU, OTHER), always summing to 1.
    w     = probability that the word is typed on the wrong layout (depends on the active layout and the state).
    o_lat = share of OTHER among words intended in Latin script."""
    if active == EN:   # EN or OTHER typed correctly, RU = a wrong-layout word
        return [(1 - w) * (1 - o_lat), w, (1 - w) * o_lat]
    return [w * (1 - o_lat), 1 - w, w * o_lat]  # RU typed correctly, EN or OTHER = a wrong-layout word


def score(logits: Sequence[float], active: str, cal: dict, w: float, kind: str = "network") -> float:
    """Posterior log-odds in nats that the intended text is NOT in the active layout's language
    ('Russian or not' in both directions): temperature, prior-shift correction, two-way marginal.
    Active EN: s = logit(p'(RU)). Active RU: s = logit(1 - p'(RU))."""
    lp = log_softmax(logits, cal["temperature"][kind])
    prior = deployment_prior(active, w, cal["o_lat"])
    lp = [a + math.log(b) - math.log(c) for a, b, c in zip(lp, prior, cal["pi_train"])]
    norm = _lse2(_lse2(lp[0], lp[1]), lp[2])
    lp = [v - norm for v in lp]
    ru, other = lp[1], _lse2(lp[0], lp[2])
    return ru - other if active == EN else other - ru


def bucket(n_keys: int) -> Optional[str]:
    if n_keys <= 1:
        return None
    if n_keys == 2:
        return "2"
    return "3-4" if n_keys <= 4 else ("5-7" if n_keys <= 7 else "8+")


def check_calibration_package(cal: dict) -> None:
    """Load-time validation (CA-9). The nats range check catches the unit mix-up: a probability such as 0.995
    stored where nats are expected is far below 4.0 and is rejected."""
    for kind, tab in cal["lambda_nats"].items():
        for direction in ("en2ru", "ru2en"):
            for b in BUCKETS:
                lam = tab[direction][b]
                assert 4.0 <= lam <= 16.0, f"lambda_nats[{kind}][{direction}][{b}]={lam} outside [4, 16] nats"
    assert abs(sum(cal["pi_train"]) - 1.0) < 1e-9 and 0 < cal["o_lat"] < 1
    for a in (EN, RU):
        for st in STATES:
            assert 0.0005 <= cal["w"][a][st] <= 0.5, f"w[{a}][{st}] outside [0.0005, 0.5]"
        assert cal["w"][a]["run"] <= 0.3, "run prior above its cap 0.3"
    for kind in cal["lambda_nats"]:
        assert kind in cal["temperature"] and cal["temperature"][kind] > 0


RU_ALLOW = "на не но да по из за то ты мы вы он ли ну во со до от ни же бы".split()
EN_ALLOW = "of to in is it on at as be by or an if so do go he we me my no up us".split()


def example_cal() -> dict:
    """The starting values of 10.1 to 10.3 as a calibration package. A real package is fitted (10.3), not typed."""
    thr = {d: {"3-4": logit(0.999), "5-7": logit(0.997), "8+": logit(0.995)} for d in ("en2ru", "ru2en")}
    return {
        "temperature": {"network": 1.0, "ngram": 1.0},
        "pi_train": [0.38, 0.40, 0.22],
        "o_lat": 0.25,
        "w": {a: {"default": 0.01, "after_switch": 0.003, "run": 0.25} for a in (EN, RU)},
        "lambda_nats": {"network": thr, "ngram": thr},
        "two_key_allow": {"en2ru": set(RU_ALLOW), "ru2en": set(EN_ALLOW)},
    }


import json


def cal_to_json(cal: dict) -> str:
    """Serialise a calibration package (D5). Sets become sorted lists, so equal packages give equal bytes."""
    def conv(o):
        if isinstance(o, (set, frozenset)):
            return sorted(o)
        raise TypeError(type(o))
    return json.dumps(cal, ensure_ascii=False, sort_keys=True, indent=1, default=conv)


def cal_from_json(text: str) -> dict:
    cal = json.loads(text)
    cal["two_key_allow"] = {d: set(v) for d, v in cal["two_key_allow"].items()}
    check_calibration_package(cal)
    return cal


# ==== 20.6 Decision for one run (priority matrix) =====================================================
@dataclass
class Decision:
    action: str                          # "CONVERT" or "KEEP"
    reason: str
    replacement: Optional[str] = None    # the whole run re-rendered on the target layout
    margin: Optional[float] = None       # score - lambda (nats), model decisions only
    n_keys: Optional[int] = None


def expected_echo(run: Sequence[Key], active: str) -> str:
    """The text the application should show for `run` as typed: used by the echo check before a replacement."""
    return render(run, active)


def decide(run: Sequence[Key], active: str, cal: dict, scorer: Callable[[List[int]], Sequence[float]],
           state: str = "default", run_active: bool = False, exceptions=frozenset(),
           lexicon: Optional[dict] = None, kind: str = "network") -> Decision:
    """The normative decision for the run (the keys typed since the last boundary), taken at Space.
    `state` selects the wrong-layout probability w ('default', 'after_switch', 'run');
    `run_active` enables the 2-key rule. Rows 5 to 12 of the priority matrix of 10.4, first match wins:
      5 no candidate  6 one key  7 user exception  8 shape guard  9 acronym of the active language
      10 word of the active language  11 two keys (allow-list and run)  12 score against the threshold."""
    target = OTHER_LAYOUT[active]
    lex = lexicon or {}
    direction = f"{active}2{target}"
    cand = candidate(run, target)
    if cand is None:
        return Decision("KEEP", "no_eligible_candidate")
    n = len(cand.core)
    if bucket(n) is None:
        return Decision("KEEP", "one_key", None, None, n)
    typed = render(cand.core, active).casefold()
    converted = render(cand.core, target).casefold()
    if (direction, typed) in exceptions:
        return Decision("KEEP", "user_exception", None, None, n)
    g = shape_guard(run, active, cand.core)
    if g:
        return Decision("KEEP", g, None, None, n)
    if typed in lex.get("acr_" + active, ()):
        return Decision("KEEP", "acronym", None, None, n)
    if typed in lex.get(active, ()):
        return Decision("KEEP", "lexicon_active", None, None, n)
    text = render(cand.lead + cand.core + cand.trail, target)
    b = bucket(n)
    if b == "2":
        if run_active and converted in cal["two_key_allow"][direction]:
            return Decision("CONVERT", "two_key_allow_list", text, None, n)
        return Decision("KEEP", "two_key_rule", None, None, n)
    s = score(scorer(tokens(cand.core, True)), active, cal, cal["w"][active][state], kind)
    margin = s - cal["lambda_nats"][kind][direction][b]
    if margin >= 0:
        return Decision("CONVERT", "score_above_threshold", text, margin, n)
    return Decision("KEEP", "abstain", None, margin, n)


# ==== 20.7 Event state machine: buffer, run state, boundary ==========================================
@dataclass
class Event:
    kind: str                      # key | space | backspace | break | layout
    key: Optional[Key] = None      # for kind == key
    layout: Optional[str] = None   # layout id sampled at the event (key, space)
    ts_ms: int = 0


MAX_BUF = 64
RUN_CREDIT_MAX = 3
COOLDOWN_WORDS = 3
COOLDOWN_MS = 10_000
EVIDENCE_KEEP = {"user_exception", "acronym", "lexicon_active", "abstain"}   # KEEP reasons that end a run
GATE_ALLOW, GATE_DENY, GATE_UNKNOWN = "ALLOW", "DENY", "UNKNOWN"


class Engine:
    """Consumes events in arrival order; returns a Decision at each Space that ends a non-empty run.
    The event kinds: key (a printable main-block key), space (the decision point), backspace, layout (a manual
    layout change), break (click, focus change, paste, Enter, Tab, arrows, chords, IME, sleep, lock, ...)."""

    def __init__(self, cal, scorer, lexicon=None, exceptions=frozenset(), kind="network"):
        self.cal, self.scorer, self.lexicon, self.exceptions, self.kind = cal, scorer, lexicon or {}, exceptions, kind
        self.run: List[Key] = []
        self.run_layout: Optional[str] = None
        self.overflow = False
        self.skip = False            # the rest of the current word is ignored (layout changed inside it)
        self.gate = GATE_ALLOW       # stage 0: only ALLOW lets keys in
        self.after_switch = False    # the next full word follows a manual layout change
        self.credit = 0              # run credit 0..RUN_CREDIT_MAX; > 0 selects the 'run' prior
        self.cool_words = 0
        self.cool_until_ms = 0

    def _flush(self):
        self.run, self.run_layout, self.overflow = [], None, False

    def set_gate(self, state: str):
        """Stage 0 verdict from the runtime. Anything but ALLOW discards the buffer and the run state."""
        self.gate = state
        if state != GATE_ALLOW:
            self._flush()
            self.skip, self.credit, self.after_switch = False, 0, False

    def undo(self, now_ms: int):
        """The user undid an automatic correction: run credit is lost and the cool-down starts."""
        self.credit = 0
        self.cool_words = COOLDOWN_WORDS
        self.cool_until_ms = now_ms + COOLDOWN_MS

    def on_event(self, ev: Event) -> Optional[Decision]:
        if self.gate != GATE_ALLOW:
            return None                                   # not stored, not counted, not classified
        if ev.kind == "key":
            if self.skip:
                return None
            if self.run and ev.layout != self.run_layout:
                self._flush()
                self.skip, self.credit = True, 0          # a layout change inside a word drops the word
                return None
            if not self.run:
                self.run_layout = ev.layout
            if len(self.run) < MAX_BUF:
                self.run.append(ev.key)
            else:
                self.overflow = True
            return None
        if ev.kind == "backspace":
            if self.run:
                self.run.pop()
            elif not self.skip:
                self.credit = 0                           # editing text before the word start: a break
            return None
        if ev.kind == "layout":                           # manual layout change (the tool never changes it)
            if self.run:
                self._flush()
                self.skip = True
            self.after_switch = True
            self.credit = 0
            return None
        if ev.kind == "break":
            self._flush()
            self.skip, self.credit = False, 0
            return None
        if ev.kind == "space":
            return self._boundary(ev)
        raise ValueError(ev.kind)

    def _boundary(self, ev: Event) -> Optional[Decision]:
        run, layout, overflow, skip = self.run, self.run_layout, self.overflow, self.skip
        self._flush()
        self.skip = False
        if skip or not run:
            return None
        if overflow:
            return Decision("KEEP", "overflow")
        if layout != ev.layout:
            return Decision("KEEP", "layout_changed_at_boundary")
        if self.cool_words > 0 or ev.ts_ms < self.cool_until_ms:
            self.cool_words = max(0, self.cool_words - 1)
            return Decision("KEEP", "cooldown")
        state = "run" if self.credit > 0 else ("after_switch" if self.after_switch else "default")
        d = decide(run, layout, self.cal, self.scorer, state, self.credit > 0, self.exceptions, self.lexicon, self.kind)
        self.after_switch = False
        if d.action == "CONVERT":
            # Only a conversion decided WITHOUT the run prior refills the credit: a chain of run-assisted
            # conversions can never sustain itself (feedback cap).
            self.credit = RUN_CREDIT_MAX if state != "run" else max(self.credit - 1, 0)
        elif d.reason in EVIDENCE_KEEP:
            self.credit = 0
        return d


# ==== 20.8 Manual conversion (hotkey) ================================================================
def _char_map(layout: str) -> Dict[str, Tuple[int, bool]]:
    m: Dict[str, Tuple[int, bool]] = {}
    for shift in (False, True):
        for k in range(47):
            m.setdefault(TABLE[layout][int(shift)][k], (k, shift))
    return m


_CHAR_MAP = {EN: _char_map(EN), RU: _char_map(RU)}


def manual_convert(text: str) -> Tuple[Optional[str], str]:
    """Pure key-position conversion of a selection (no punctuation peeling, no model, no thresholds).
    Direction: more Cyrillic letters than Latin letters means RU->EN, otherwise EN->RU; no letters at all means
    no direction and the text is returned unchanged. Characters that are not on the source layout (emoji,
    accented letters, other scripts) are copied unchanged; the length in code points never changes."""
    cyr = sum(1 for c in text if "а" <= c.lower() <= "я" or c in "ёЁ")
    lat = sum(1 for c in text if c.isascii() and c.isalpha())
    if cyr == 0 and lat == 0:
        return None, text
    src = RU if cyr > lat else EN
    dst = OTHER_LAYOUT[src]
    out = []
    for c in text:
        hit = _CHAR_MAP[src].get(c)
        out.append(TABLE[dst][int(hit[1])][hit[0]] if hit else c)
    return f"{src}2{dst}", "".join(out)


# ==== 20.9 Acceptance statistics (EV-1) ===============================================================
def poisson_upper(k: int, conf: float = 0.95) -> float:
    """Exact one-sided upper limit mu with P(Poisson(mu) <= k) = 1 - conf."""
    lo, hi = 0.0, 10.0 + 10.0 * k
    for _ in range(200):
        mid = (lo + hi) / 2
        cdf = sum(math.exp(-mid + i * math.log(mid) - math.lgamma(i + 1)) for i in range(k + 1)) if mid > 0 else 1.0
        if cdf > 1 - conf:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def ev1_bound(false_corrections: Sequence[Tuple[str, str]], n_negatives: int) -> float:
    """Conservative 95% upper bound on the false-correction rate under clustering.
    `false_corrections`: one (user_id, document_id) per false correction. A cluster is a distinct pair;
    bound = poisson_upper(number of clusters) * (largest cluster size) / n_negatives."""
    if not false_corrections:
        return poisson_upper(0) / n_negatives
    sizes: Dict[Tuple[str, str], int] = {}
    for key in false_corrections:
        sizes[key] = sizes.get(key, 0) + 1
    return poisson_upper(len(sizes)) * max(sizes.values()) / n_negatives


def ev1_pass(false_corrections: Sequence[Tuple[str, str]], n_negatives: int, n_users: int, n_documents: int) -> bool:
    """EV-1: n >= 100,000 correct words, >= 20 users, >= 100 documents, point estimate <= 4.8e-5 and
    cluster bound <= 1e-4. (The caps on per-user and per-document shares are applied before counting.)"""
    return (n_negatives >= 100_000 and n_users >= 20 and n_documents >= 100
            and len(false_corrections) / n_negatives <= 4.8e-5
            and ev1_bound(false_corrections, n_negatives) <= 1e-4)


# ==== 20.10 Statistical baseline: Witten-Bell trigram over key tokens, table format LFB1 =============
class WittenBell:
    """Interpolated Witten-Bell language model of order 3 over key tokens (one instance per class)."""
    ORDER = 3

    def __init__(self, vocab: int = VOCAB, min_count: int = 1):
        self.V, self.min_count = vocab, min_count
        self.cnt = [dict() for _ in range(self.ORDER)]     # cnt[k][context tuple (len k)] -> {next: count}

    def fit(self, rows: Sequence[Sequence[int]], weights: Optional[Sequence[int]] = None):
        """rows: BOS + key tokens + EOS (tokens(core, True)); weights: multiplicity of each row."""
        for r, row in enumerate(rows):
            m = 1 if weights is None else weights[r]
            for i in range(1, len(row)):
                for k in range(self.ORDER):
                    if i - k < 0:
                        break
                    d = self.cnt[k].setdefault(tuple(row[i - k:i]), {})
                    d[row[i]] = d.get(row[i], 0) + m
        if self.min_count > 1:                              # prune BEFORE the totals are derived
            for k in range(1, self.ORDER):
                for ctx in list(self.cnt[k]):
                    d = {w: c for w, c in self.cnt[k][ctx].items() if c >= self.min_count}
                    if d:
                        self.cnt[k][ctx] = d
                    else:
                        del self.cnt[k][ctx]
        return self

    def logp(self, row: Sequence[int]) -> float:
        total = 0.0
        for i in range(1, len(row)):
            p = 1.0 / self.V                                 # order -1: uniform
            for k in range(self.ORDER):                       # orders 0, 1, 2: interpolate upwards
                if i - k < 0:
                    break
                d = self.cnt[k].get(tuple(row[i - k:i]))
                if d is None:                                 # unseen context: keep the lower-order estimate
                    break
                t, u = sum(d.values()), len(d)
                p = (d.get(row[i], 0) + u * p) / (t + u)
            total += math.log(p)
        return total


def baseline_logits(models: Sequence[WittenBell], log_prior: Sequence[float], row: Sequence[int]) -> List[float]:
    """Unnormalised class log-posteriors: log p(row | class) + log pi_train(class). They enter the same
    calibration path as network logits, with kind='ngram' (own temperature and own threshold table)."""
    return [m.logp(row) + lp for m, lp in zip(models, log_prior)]


import struct

FNV_OFFSET, FNV_PRIME, MASK64 = 0xCBF29CE484222325, 0x100000001B3, (1 << 64) - 1


def fnv1a64(data: bytes) -> int:
    h = FNV_OFFSET
    for b in data:
        h = ((h ^ b) * FNV_PRIME) & MASK64
    return h


def ctx_key(k: int, ctx: Sequence[int]) -> int:
    return fnv1a64(bytes([0xC0 + k]) + bytes(ctx))


def pair_key(k: int, ctx: Sequence[int], nxt: int) -> int:
    return fnv1a64(bytes([0xD0 + k]) + bytes(ctx) + bytes([nxt]))


def lfb_pack(models: Sequence[WittenBell], log_prior: Sequence[float]) -> bytes:
    """LFB1: magic, u32 order, u32 vocab, u32 nclasses, f64 log_prior[nclasses]; then for each class and each
    order k = 0..2: u32 n_ctx, n_ctx x (u64 key, u32 total, u32 distinct), u32 n_pair, n_pair x (u64 key,
    u32 count, u32 0). Records are sorted by key; little endian. Runtime hash tables are built from them."""
    out = [b"LFB1", struct.pack("<III", WittenBell.ORDER, models[0].V, len(models)),
           struct.pack("<%dd" % len(models), *log_prior)]
    for m in models:
        for k in range(WittenBell.ORDER):
            ctxs = sorted((ctx_key(k, c), sum(d.values()), len(d)) for c, d in m.cnt[k].items())
            pairs = sorted((pair_key(k, c, w), n) for c, d in m.cnt[k].items() for w, n in d.items())
            assert len({r[0] for r in ctxs}) == len(ctxs) and len({a for a, _ in pairs}) == len(pairs), "hash collision"
            out.append(struct.pack("<I", len(ctxs)) + b"".join(struct.pack("<QII", *r) for r in ctxs))
            out.append(struct.pack("<I", len(pairs)) + b"".join(struct.pack("<QII", a, n, 0) for a, n in pairs))
    return b"".join(out)


def lfb_load(b: bytes) -> dict:
    assert b[:4] == b"LFB1"
    order, vocab, ncls = struct.unpack_from("<III", b, 4)
    log_prior = list(struct.unpack_from("<%dd" % ncls, b, 16))
    off, classes = 16 + 8 * ncls, []
    for _ in range(ncls):
        per_order = []
        for _k in range(order):
            (nc,) = struct.unpack_from("<I", b, off); off += 4
            ctx = {}
            for i in range(nc):
                key, t, u = struct.unpack_from("<QII", b, off + 16 * i)
                ctx[key] = (t, u)
            off += 16 * nc
            (npair,) = struct.unpack_from("<I", b, off); off += 4
            pair = {}
            for i in range(npair):
                key, n, _z = struct.unpack_from("<QII", b, off + 16 * i)
                pair[key] = n
            off += 16 * npair
            per_order.append((ctx, pair))
        classes.append(per_order)
    assert off == len(b), "trailing bytes"
    return {"order": order, "V": vocab, "log_prior": log_prior, "classes": classes}


def lfb_logp(pkg: dict, cls: int, row: Sequence[int]) -> float:
    """Same value as WittenBell.logp for the model that was packed (to float rounding)."""
    total = 0.0
    for i in range(1, len(row)):
        p = 1.0 / pkg["V"]
        for k in range(pkg["order"]):
            if i - k < 0:
                break
            ctx = row[i - k:i]
            st = pkg["classes"][cls][k][0].get(ctx_key(k, ctx))
            if st is None:
                break
            t, u = st
            c = pkg["classes"][cls][k][1].get(pair_key(k, ctx, row[i]), 0)
            p = (c + u * p) / (t + u)
        total += math.log(p)
    return total


# Lexicon tables (stage 4): sets of 64-bit hashes, file format LFL1.
LEX_TAGS = {"lex_en": 1, "lex_ru": 2, "acr_en": 3, "acr_ru": 4, "exc_en2ru": 5, "exc_ru2en": 6}


def lex_key(tag: int, text: str) -> int:
    """64-bit key of a case-folded string in table `tag`: FNV-1a over one tag byte and the UTF-8 bytes."""
    return fnv1a64(bytes([0xE0 + tag]) + text.casefold().encode("utf-8"))


def lfl_pack(tables: Dict[str, Sequence[str]]) -> bytes:
    """LFL1: magic, u32 ntables, then per table in tag order: u8 tag, u32 n, n x u64 sorted unique keys (LE)."""
    out = [b"LFL1", struct.pack("<I", len(tables))]
    for name in sorted(tables, key=lambda n: LEX_TAGS[n]):
        tag = LEX_TAGS[name]
        keys = sorted({lex_key(tag, w) for w in tables[name]})
        out.append(struct.pack("<BI", tag, len(keys)) + b"".join(struct.pack("<Q", k) for k in keys))
    return b"".join(out)


class HashedSet:
    """Membership by hash, a drop-in for the sets of words that `decide` takes (a hash match is a word match)."""

    def __init__(self, tag: int, keys):
        self.tag, self.keys = tag, frozenset(keys)

    def __contains__(self, text: str) -> bool:
        return lex_key(self.tag, text) in self.keys


def lfl_load(b: bytes) -> Dict[str, HashedSet]:
    assert b[:4] == b"LFL1"
    (nt,) = struct.unpack_from("<I", b, 4)
    off, res, by_tag = 8, {}, {v: k for k, v in LEX_TAGS.items()}
    for _ in range(nt):
        tag, n = struct.unpack_from("<BI", b, off)
        off += 5
        res[by_tag[tag]] = HashedSet(tag, struct.unpack_from("<%dQ" % n, b, off))
        off += 8 * n
    assert off == len(b), "trailing bytes"
    return res


# ==== 20.11 Network weight file LFW1 and reference forward pass ======================================
LFW_MAGIC = b"LFW1"


def lfw_pack(ch: int, emb_dim: int, kernels: Sequence[int], floats: Sequence[float]) -> bytes:
    """Header: magic, u32 ch, u32 emb_dim, u32 nconv, nconv x u32 kernel, then float32 little-endian in the order
    emb[97][e]; per conv: weight[ch][cin][k], bias[ch]; head weight[3][2*ch], head bias[3]."""
    head = LFW_MAGIC + struct.pack("<III", ch, emb_dim, len(kernels)) + b"".join(struct.pack("<I", k) for k in kernels)
    return head + struct.pack("<%df" % len(floats), *floats)


def lfw_size(ch: int, emb_dim: int, kernels: Sequence[int]) -> int:
    n, cin = VOCAB * emb_dim, emb_dim
    for k in kernels:
        n += ch * cin * k + ch
        cin = ch
    return n + 3 * 2 * ch + 3


def lfw_load(b: bytes) -> dict:
    assert b[:4] == LFW_MAGIC
    ch, e, nc = struct.unpack_from("<III", b, 4)
    kernels = list(struct.unpack_from("<" + "I" * nc, b, 16))
    off = 16 + 4 * nc
    assert len(b) - off == 4 * lfw_size(ch, e, kernels), "size mismatch"

    def take(n):
        nonlocal off
        v = list(struct.unpack_from("<%df" % n, b, off))
        off += 4 * n
        return v
    W = {"ch": ch, "e": e, "kernels": kernels, "emb": take(VOCAB * e), "convs": []}
    cin = e
    for k in kernels:
        W["convs"].append((take(ch * cin * k), take(ch), cin, k))
        cin = ch
    W["hw"], W["hb"] = take(3 * 2 * ch), take(3)
    return W


def lfw_forward(W: dict, ids: Sequence[int]) -> List[float]:
    """Logits (EN, RU, OTHER) for a token list at its true length (no padding). Same-padding convolutions,
    ReLU, masked max and mean pooling over all positions (BOS and EOS included), linear head."""
    ch, e, T = W["ch"], W["e"], len(ids)
    x = [[W["emb"][t * e + j] for j in range(e)] for t in ids]
    for (w, bias, cin, k) in W["convs"]:
        pad, y = k // 2, []
        for t in range(T):
            row = []
            for o in range(ch):
                s = bias[o]
                for kk in range(k):
                    u = t + kk - pad
                    if 0 <= u < T:
                        base = o * cin * k
                        for i in range(cin):
                            s += w[base + i * k + kk] * x[u][i]
                row.append(s if s > 0 else 0.0)
            y.append(row)
        x = y
    feat = [max(x[t][o] for t in range(T)) for o in range(ch)] + [sum(x[t][o] for t in range(T)) / T for o in range(ch)]
    return [W["hb"][c] + sum(W["hw"][c * 2 * ch + j] * feat[j] for j in range(2 * ch)) for c in range(3)]


def toy_weights(ch: int = 4, emb_dim: int = 4, kernels=(3, 5, 3), seed: int = 1) -> bytes:
    """Deterministic toy weights (integer arithmetic only, so every language reproduces them exactly)."""
    n = lfw_size(ch, emb_dim, kernels)
    state, floats = seed, []
    for _ in range(n):
        state = (state * 1103515245 + 12345) % (2 ** 31)
        floats.append(((state >> 16) % 33 - 16) / 32.0)       # multiples of 1/32 in [-0.5, 0.5]
    return lfw_pack(ch, emb_dim, kernels, floats)
