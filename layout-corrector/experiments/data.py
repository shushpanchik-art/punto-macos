"""Word-level proxy dataset for 'intended-language from keystrokes' classification.

Classes: 0 = EN-intended, 1 = RU-intended, 2 = OTHER (code/ids/urls/translit/gibberish/numbers).
Input: sequence of (physical key, shift) tokens -- independent of the active layout.
"""
import re, os, random, hashlib, pickle, glob, sys, collections
import numpy as np
import wordfreq
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from layouts import CHAR2KEY, LAYOUTS, to_keys

PAD, BOS, EOS = 0, 95, 96
VOCAB = 97
MAXK = 20           # max key tokens kept
MAXL = MAXK + 2     # + BOS/EOS

RU_RE = re.compile(r"^[а-яё]+$")
EN_RE = re.compile(r"^[a-z]+$")


def tok(key, shift):
    return 1 + key * 2 + shift


def h(s, mod=100):
    return int(hashlib.md5(s.encode()).hexdigest(), 16) % mod


def split_of(s):
    r = h(s, 100)
    return "train" if r < 80 else ("val" if r < 90 else "test")


def load_lang(lang, regex, start, stop):
    words = wordfreq.top_n_list(lang, 900000, wordlist="large")
    out = []
    for w in words:
        if regex.match(w):
            out.append((w, wordfreq.zipf_frequency(w, lang, wordlist="large")))
    return out[start:stop]


def case_variant(w, rng):
    r = rng.random()
    if r < 0.72:
        return w
    if r < 0.92:
        return w[0].upper() + w[1:]
    if r < 0.97:
        return w.upper()
    # random mixed
    return "".join(c.upper() if rng.random() < 0.5 else c for c in w)


def encode_text(text, layout):
    """text rendered in `layout` -> key tokens (list) or None."""
    ks = to_keys(text, layout)
    if any(k is None for k in ks):
        return None
    return [tok(k, s) for k, s in ks]


def pack(seqs, with_eos):
    """seqs: list of list[int] (key tokens, may be longer than MAXK) ; with_eos: list[bool]"""
    n = len(seqs)
    X = np.zeros((n, MAXL), dtype=np.int16)
    lens = np.zeros(n, dtype=np.int16)
    for i, (s, e) in enumerate(zip(seqs, with_eos)):
        s = s[:MAXK]
        row = [BOS] + s + ([EOS] if e and len(s) <= MAXK else [])
        X[i, :len(row)] = row
        lens[i] = len(s)
    return X, lens


# ---------------------------------------------------------------- OTHER class
def harvest_identifiers(max_files=4000):
    import sysconfig
    roots = [sysconfig.get_paths()["stdlib"], sysconfig.get_paths()["purelib"]]
    files = []
    for r in roots:
        files += glob.glob(os.path.join(r, "**", "*.py"), recursive=True)
    random.Random(1).shuffle(files)
    files = files[:max_files]
    tokre = re.compile(r"[A-Za-z_][A-Za-z0-9_]{1,24}")
    cnt = collections.Counter()
    for f in files:
        try:
            txt = open(f, encoding="utf-8", errors="ignore").read()
        except Exception:
            continue
        cnt.update(tokre.findall(txt))
    return cnt


CLI = """kubectl npm npx git github gitlab docker sudo ssh scp curl wget grep sed awk chmod chown mkdir rmdir ls cd cp mv rm cat tail head
pip pip3 python python3 node yarn pnpm cargo rustc gcc make cmake brew apt apt-get yum dnf systemctl journalctl nginx redis mysql psql sqlite3
localhost iOS macOS API UUID JSON YAML HTML CSS URL URI HTTP HTTPS SSH GPU CPU RAM SSD USB HDMI PDF PNG JPG SQL ORM CRUD REST gRPC
kwargs args argv stdin stdout stderr dev prod src bin usr etc tmp var env venv pyc init config util utils lib""".split()

TLDS = ["com", "org", "net", "io", "ru", "dev", "app", "ai", "co", "info", "me", "tv"]


def synth_other(rng, en_words, ru_words, n):
    """Synthetic technical strings typed with EN layout keys."""
    out = []
    def w():
        return rng.choice(en_words)
    for _ in range(n):
        t = rng.random()
        if t < 0.12:   # domain / url
            s = rng.choice(["", "www.", "https://", "http://"]) + w() + rng.choice(["", "-" + w()]) + "." + rng.choice(TLDS) + rng.choice(["", "/" + w(), "/" + w() + "/" + w() + ".html"])
        elif t < 0.22:  # email
            s = w() + rng.choice([".", "_", ""]) + w() + "@" + w() + "." + rng.choice(TLDS)
        elif t < 0.32:  # snake/camel/kebab
            a, b = w(), w()
            s = rng.choice([a + "_" + b, a + b.capitalize(), a.capitalize() + b.capitalize(), a + "-" + b, a.upper() + "_" + b.upper(), "--" + a + "-" + b])
        elif t < 0.42:  # number-ish
            s = rng.choice(["%d", "%d.%d", "%d.%d.%d", "v%d.%d", "%d%%", "$%d", "#%d", "0x%x", "%d:%d", "%d-%d-%d", "%dpx", "%dkb", "%dx%d"]).replace("%x", "%x")
            nargs = s.count("%d") + s.count("%x")
            vals = tuple(rng.randrange(0, 3000) for _ in range(nargs))
            s = s.replace("%%", "\x00").replace("%x", "%d") % vals
            s = s.replace("\x00", "%")
        elif t < 0.50:  # hash / id
            s = "".join(rng.choice("0123456789abcdef") for _ in range(rng.choice([6, 7, 8, 12, 16, 32])))
        elif t < 0.58:  # path
            s = rng.choice(["/", "./", "../", "~/", "C:\\"]) + w() + rng.choice(["/", "\\"]) + w() + rng.choice(["", ".txt", ".py", ".js", ".json", ".md"])
        elif t < 0.64:  # file name + ext
            s = w() + rng.choice([".txt", ".py", ".js", ".json", ".md", ".png", ".pdf", ".exe", ".cpp"])
        elif t < 0.70:  # mixed alnum tokens
            s = w()[:rng.randrange(2, 5)] + str(rng.randrange(0, 999)) + rng.choice(["", "x", "k", "mb"])
        elif t < 0.76:  # mashing / gibberish on keyboard rows
            row = rng.choice(["qwertyuiop", "asdfghjkl", "zxcvbnm", "1234567890"])
            i = rng.randrange(0, 4)
            s = row[i:i + rng.randrange(3, 8)]
        elif t < 0.80:  # repeated chars
            c = rng.choice("abcdefghijklmnopqrstuvwxyz")
            s = c * rng.randrange(3, 8)
        else:          # transliterated russian (latin letters, EN layout)
            r = rng.choice(ru_words)
            s = translit(r)
        out.append(s)
    return out


_TR = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
               ["a", "b", "v", "g", "d", "e", "e", "zh", "z", "i", "y", "k", "l", "m", "n", "o", "p", "r", "s", "t", "u", "f", "h", "ts", "ch", "sh", "sch", "", "y", "", "e", "yu", "ya"]))


def translit(r):
    return "".join(_TR.get(c, c) for c in r)


def build_other(seed=7):
    rng = random.Random(seed)
    en = [w for w, _ in load_lang("en", EN_RE, 0, 20000)]
    ru = [w for w, _ in load_lang("ru", RU_RE, 0, 20000)]
    en_set = set(w for w, _ in load_lang("en", EN_RE, 0, 100000))
    cnt = harvest_identifiers()
    idents = []
    for t, c in cnt.items():
        low = t.lower()
        if t in en_set:       # plain English word -> belongs to EN class
            continue
        idents.append(t)
    rng.shuffle(idents)
    synth = synth_other(rng, en, ru, 120000)
    cli = CLI * 3
    items = [(s, 1.0) for s in idents[:100000]] + [(s, 1.0) for s in synth] + [(s, 2.0) for s in CLI]
    # drop anything not encodable on the EN layout
    res = []
    for s, wt in items:
        if encode_text(s, "en") is not None:
            res.append((s, wt))
    return res


def build_all(cache="data_cache.pkl"):
    if os.path.exists(cache):
        return pickle.load(open(cache, "rb"))
    en = load_lang("en", EN_RE, 0, 100000)
    ru = load_lang("ru", RU_RE, 0, 100000)
    en_tail = load_lang("en", EN_RE, 100000, 200000)
    ru_tail = load_lang("ru", RU_RE, 100000, 200000)
    other = build_other()
    D = dict(en=en, ru=ru, en_tail=en_tail, ru_tail=ru_tail, other=other)
    pickle.dump(D, open(cache, "wb"))
    return D


def mult(z):
    return int(min(5, max(1, np.floor(z - 2))))


def make_split(D, split, seed, prefix_p=0.35, full_only=False, oversample=True):
    """Return X, y, lens, meta(dict arrays: weight, is_prefix, cls)"""
    rng = random.Random(seed)
    seqs, ends, ys, wts, lens_full = [], [], [], [], []
    def add(text, layout, y, wt, m):
        for _ in range(m):
            t = case_variant(text, rng) if y < 2 else text
            ids = encode_text(t, layout)
            if ids is None:
                continue
            n = len(ids)
            if (not full_only) and n >= 3 and rng.random() < prefix_p:
                p = rng.randrange(2, n)
                seqs.append(ids[:p]); ends.append(False)
            else:
                seqs.append(ids); ends.append(True)
            ys.append(y); wts.append(wt); lens_full.append(n)
    for w, z in D["en"]:
        if split_of(w) == split:
            add(w, "en", 0, z, mult(z) if oversample else 1)
    for w, z in D["ru"]:
        if split_of(w) == split:
            add(w, "ru", 1, z, mult(z) if oversample else 1)
    for s, wt in D["other"]:
        if split_of(s) == split:
            add(s, "en", 2, 3.0, int(wt) if oversample else 1)
    X, lens = pack(seqs, ends)
    return X, np.array(ys, dtype=np.int64), lens, dict(zipf=np.array(wts), full_len=np.array(lens_full), is_prefix=np.array([not e for e in ends]))


if __name__ == "__main__":
    D = build_all()
    for k, v in D.items():
        print(k, len(v), v[:5])
    X, y, lens, meta = make_split(D, "train", 0)
    print(X.shape, np.bincount(y), meta["is_prefix"].mean())
    Xv, yv, lv, mv = make_split(D, "val", 1, full_only=True, oversample=False)
    Xt, yt, lt, mt = make_split(D, "test", 2, full_only=True, oversample=False)
    print("val", Xv.shape, np.bincount(yv), "test", Xt.shape, np.bincount(yt))
