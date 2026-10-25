import re, json, collections, sys
import wordfreq
sys.path.insert(0, ".")
from layouts import convert

RU_RE = re.compile(r"^[а-яё]+$")
EN_RE = re.compile(r"^[a-z]+$")

def load(lang, regex, n):
    words = wordfreq.top_n_list(lang, 600000, wordlist="large")
    out = []
    for w in words:
        if regex.match(w):
            out.append((w, wordfreq.word_frequency(w, lang, wordlist="large")))
            if len(out) >= n:
                break
    return out

N = 100000
ru = load("ru", RU_RE, N)
en = load("en", EN_RE, N)
print("loaded", len(ru), len(en), "min zipf ru/en:",
      wordfreq.zipf_frequency(ru[-1][0], "ru", wordlist="large"),
      wordfreq.zipf_frequency(en[-1][0], "en", wordlist="large"))

ru_set = {w for w, _ in ru}
en_set = {w for w, _ in en}

def bucket(L):
    if L <= 1: return "1"
    if L <= 7: return str(L)
    return "8+"

BUCKETS = ["2", "3", "4", "5", "6", "7", "8+"]

def stats(src, lex_other_sets, direction):
    """src: list of (word,freq) intended words. direction 'en2ru': word typed in RU layout shows s=convert(w,'en','ru').
    ambiguity = s is also a valid word of the displayed script (RU lexicon)."""
    res = {}
    for K in lex_other_sets:
        other = lex_other_sets[K]
        tot_t = collections.Counter(); amb_t = collections.Counter()
        tot_w = collections.Counter(); amb_w = collections.Counter()
        for w, f in src:
            L = len(w)
            if L < 2: continue
            b = bucket(L)
            s = convert(w, "en", "ru") if direction == "en2ru" else convert(w, "ru", "en")
            a = 1 if (s in other) else 0
            tot_t[b] += 1; amb_t[b] += a
            tot_w[b] += f; amb_w[b] += f * a
        res[K] = {b: dict(types=tot_t[b], amb_types=amb_t[b],
                          type_rate=amb_t[b] / max(tot_t[b], 1),
                          token_rate=amb_w[b] / max(tot_w[b], 1e-12)) for b in BUCKETS}
    return res

# Lexicon of "valid frequent words" of the displayed language at several sizes
ru_lex = {K: {w for w, _ in ru[:K]} for K in (20000, 100000)}
en_lex = {K: {w for w, _ in en[:K]} for K in (20000, 100000)}

# Source = top 20k intended words by frequency (realistic running-text vocabulary); lexicon sizes 20k / 100k
en_src = en[:20000]
ru_src = ru[:20000]
r1 = stats(en_src, ru_lex, "en2ru")
r2 = stats(ru_src, en_lex, "ru2en")

def show(title, r):
    print("\n" + title)
    for K, rows in r.items():
        print(f" displayed-language lexicon = top {K}")
        print("  len | types | ambiguous types | type-rate | token-weighted rate")
        for b in BUCKETS:
            x = rows[b]
            print(f"  {b:>3} | {x['types']:5d} | {x['amb_types']:5d} | {100*x['type_rate']:6.2f}% | {100*x['token_rate']:6.2f}%")

show("EN-intended word typed under RU layout; also valid RU word?", r1)
show("RU-intended word typed under EN layout; also valid EN word?", r2)

# Examples of ambiguous pairs by length (top by frequency)
def examples(src, other, direction, L, k=12):
    out = []
    for w, f in src:
        if len(w) != L: continue
        s = convert(w, "en", "ru") if direction == "en2ru" else convert(w, "ru", "en")
        if s in other:
            out.append((w, s))
            if len(out) >= k: break
    return out

ex = {}
for L in (2, 3, 4, 5):
    ex[f"en2ru_{L}"] = examples(en_src, ru_lex[20000], "en2ru", L)
    ex[f"ru2en_{L}"] = examples(ru_src, en_lex[20000], "ru2en", L)
for k, v in ex.items():
    print(k, v)

# Segmentation hazard: RU tokens (token-weighted) whose EN-layout rendering contains punctuation keys
PUNCT_LETTERS = set("ёхъжэбю")
tot = 0.0; any_p = 0.0; lead = 0.0; trail = 0.0; inner = 0.0
for w, f in ru_src:
    tot += f
    if any(c in PUNCT_LETTERS for c in w): any_p += f
    if w[0] in PUNCT_LETTERS: lead += f
    if w[-1] in PUNCT_LETTERS: trail += f
    if any(c in PUNCT_LETTERS for c in w[1:-1]): inner += f
print("\nRU token-weighted share (top-20k) with >=1 of ёхъжэбю:", round(100 * any_p / tot, 1), "%")
print(" ... starting with one:", round(100 * lead / tot, 1), "%  ending with one:", round(100 * trail / tot, 1), "%  inside:", round(100 * inner / tot, 1), "%")
types_any = sum(1 for w, _ in ru_src if any(c in PUNCT_LETTERS for c in w)) / len(ru_src)
print("RU type share (top-20k) with >=1:", round(100 * types_any, 1), "%")

# EN words typed in RU layout never contain punctuation, but EN apostrophe words etc. ignored here.

json.dump({"en2ru": r1, "ru2en": r2, "examples": ex,
           "seg": {"ru_tok_any": any_p / tot, "ru_tok_lead": lead / tot, "ru_tok_trail": trail / tot, "ru_tok_inner": inner / tot}},
          open("exp1_results.json", "w"), ensure_ascii=False, indent=1)
