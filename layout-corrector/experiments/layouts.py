"""Deterministic physical-key layout tables (Windows 'Russian' ЙЦУКЕН <-> US QWERTY).

A key is identified by a physical position index (0..46) of the 47 printable
alphanumeric-block keys. Each layout maps (key, shift) -> character.
"""

# Physical order: row0 (13) + row1 (13) + row2 (11) + row3 (10) = 47 keys
EN_UNSHIFT = "`1234567890-=" + "qwertyuiop[]\\" + "asdfghjkl;'" + "zxcvbnm,./"
EN_SHIFT   = "~!@#$%^&*()_+" + "QWERTYUIOP{}|" + 'ASDFGHJKL:"' + "ZXCVBNM<>?"
RU_UNSHIFT = "ё1234567890-=" + "йцукенгшщзхъ\\" + "фывапролджэ" + "ячсмитьбю."
RU_SHIFT   = 'Ё!"№;%:?*()_+' + "ЙЦУКЕНГШЩЗХЪ/" + "ФЫВАПРОЛДЖЭ" + "ЯЧСМИТЬБЮ,"

assert len(EN_UNSHIFT) == len(EN_SHIFT) == len(RU_UNSHIFT) == len(RU_SHIFT) == 47

LAYOUTS = {
    "en": (EN_UNSHIFT, EN_SHIFT),
    "ru": (RU_UNSHIFT, RU_SHIFT),
}

# char -> (key, shift) for each layout
CHAR2KEY = {}
for name, (u, s) in LAYOUTS.items():
    d = {}
    for k, ch in enumerate(u):
        d[ch] = (k, 0)
    for k, ch in enumerate(s):
        d[ch] = (k, 1)
    CHAR2KEY[name] = d


def to_keys(text, layout):
    """Text as displayed in `layout` -> list of (key, shift). Unknown chars -> None."""
    m = CHAR2KEY[layout]
    return [m.get(c) for c in text]


def from_keys(keys, layout):
    u, s = LAYOUTS[layout]
    out = []
    for kk in keys:
        if kk is None:
            out.append("�")
        else:
            k, sh = kk
            out.append((s if sh else u)[k])
    return "".join(out)


def convert(text, src, dst):
    """Re-render `text` typed in layout `src` as it would appear in layout `dst`."""
    keys = to_keys(text, src)
    if any(k is None for k in keys):
        return None
    return from_keys(keys, dst)


# Keys whose letter in RU layout is a PUNCTUATION char in EN layout
RU_LETTER_ON_EN_PUNCT = [i for i, (e, r) in enumerate(zip(EN_UNSHIFT, RU_UNSHIFT))
                         if (not e.isalnum()) and r.isalpha()]

if __name__ == "__main__":
    # round trip tests
    import itertools
    bad = 0
    for a, b in (("en", "ru"), ("ru", "en")):
        u, s = LAYOUTS[a]
        for ch in u + s:
            c2 = convert(ch, a, b)
            c3 = convert(c2, b, a)
            if c3 != ch:
                bad += 1
                print("round-trip FAIL", repr(ch), repr(c2), repr(c3))
    print("round-trip failures:", bad)
    print("keys where RU has a letter but EN has punctuation:",
          [(i, EN_UNSHIFT[i], RU_UNSHIFT[i]) for i in RU_LETTER_ON_EN_PUNCT])
    assert convert("ghbdtn", "en", "ru") == "привет"
    assert convert("руддщ", "ru", "en") == "hello"
    assert convert("Ghbdtn", "en", "ru") == "Привет"
    assert convert("GHBDTN", "en", "ru") == "ПРИВЕТ"
    print(convert("[jhjij", "en", "ru"), convert(";bpym", "en", "ru"), convert(",jkmit", "en", "ru"))
    print(convert("Ghbdtn?", "en", "ru"), convert("Ghbdtn&", "en", "ru"), convert("Привет,", "ru", "en"), convert("Привет?", "ru", "en"))
    # shift-layer differences between layouts (non-letter)
    diff = [(EN_SHIFT[i], RU_SHIFT[i]) for i in range(47) if not EN_SHIFT[i].isalpha() and EN_SHIFT[i] != RU_SHIFT[i]]
    print("shifted non-letter keys that differ:", diff)
    diff0 = [(EN_UNSHIFT[i], RU_UNSHIFT[i]) for i in range(47) if not EN_UNSHIFT[i].isalpha() and EN_UNSHIFT[i] != RU_UNSHIFT[i]]
    print("unshifted non-letter keys that differ:", diff0)
    print("OK")
