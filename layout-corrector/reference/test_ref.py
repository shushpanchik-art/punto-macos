import sys, random
sys.path.insert(0, ".")
import lfengine as L
K = L.keys_from_text
R = random.Random(1)

# property 1: tokens in range, keys <-> text round trip in both layouts
for _ in range(200000):
    n = R.randrange(1, 12)
    run = [L.Key(R.randrange(47), R.random() < .5, R.random() < .3) for _ in range(n)]
    for k in run:
        assert 1 <= L.token(k) <= 94
    for lay in ("en", "ru"):
        txt = L.render([L.Key(k.id, L.effective_shift(k, lay), False) for k in run], lay)
        assert txt == L.render(run, lay)
        back = K(txt, lay)
        assert L.render(back, lay) == txt
    # candidate never loses a key
    for tgt in ("en", "ru"):
        c = L.candidate(run, tgt)
        if c:
            assert c.lead + c.core + c.trail == tuple(run)
            assert len(c.lead) <= 1 and len(c.trail) <= 2 and len(c.core) >= 1
            assert all(L.is_letter_in(tgt, k.id) for k in c.core)

# property 2: a run whose target-layout rendering is entirely letters is never peeled (the seven letter-keys)
import wordfreq
for w in wordfreq.top_n_list("ru", 20000, wordlist="large"):
    if not all(ch in L.RU_UNSHIFT + L.RU_SHIFT for ch in w) or not w.isalpha():
        continue
    run = K(w, "ru")
    c = L.candidate(run, "ru")
    assert c is not None and c.core == tuple(run), w
for w in wordfreq.top_n_list("en", 20000, wordlist="large"):
    if not (w.isascii() and w.isalpha()):
        continue
    run = K(w, "en")
    c = L.candidate(run, "en")
    assert c is not None and c.core == tuple(run), w
# every Russian top-20k word typed on the EN layout: candidate with target RU has core == whole run
n = 0
for w in wordfreq.top_n_list("ru", 20000, wordlist="large"):
    if not (w.isalpha() and all(ch in L.RU_UNSHIFT + L.RU_SHIFT for ch in w)):
        continue
    typed = L.render(K(w, "ru"), "en")
    c = L.candidate(K(typed, "en"), "ru")
    assert c and L.render(c.core, "ru") == w
    n += 1
print("OK property tests; Russian words checked:", n)
