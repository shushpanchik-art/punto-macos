import sys; sys.path.insert(0, ".")
import lfengine as L
from wordfreq import top_n_list, zipf_frequency
K = L.keys_from_text
def ok_word(w, lay):
    try: K(w, lay); return True
    except KeyError: return False
for lang, lay, act, tgt in (("ru","ru","en","ru"),("en","en","ru","en")):
    words = [w for w in top_n_list(lang, 20000, wordlist="large") if w.isalpha() and ok_word(w, lay)]
    n = len(words); cnt = {}; tokw = 0; guardw = 0
    for w in words:
        keys = K(w, lay)
        cand = L.candidate(keys, lay)       # target layout = the language the user meant
        if cand is None: cnt["no_candidate"] = cnt.get("no_candidate",0)+1; continue
        g = L.shape_guard(keys, act, cand.core)
        if g: cnt[g] = cnt.get(g,0)+1
    print(lang, "words", n, {k: (v, round(v/n*100,2)) for k,v in cnt.items()})
    ex = [w for w in words if (lambda c: c and L.shape_guard(K(w,lay), act, c.core))(L.candidate(K(w,lay), lay))][:25]
    print(" examples:", ex)
