#!/usr/bin/env python3
"""Tests of the LOGIC of the measuring programs with fake bindings. They prove that the programs build result bodies that
spikes.py understands and that a fake system with a known behaviour gets the right verdict. They prove nothing about Windows or
macOS; a result produced here carries synthetic = true and is never evidence."""
import importlib.util
import os
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import common
import spikes as S

def load(rel):
    spec = importlib.util.spec_from_file_location(os.path.basename(rel)[:-3], os.path.join(HERE, rel))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
N = 0
def T(c, what):
    global N
    N += 1
    if not c:
        raise AssertionError(what)

# ---- the key map
T(len(common.SCAN) == 47 and common.SCAN[0] == 0x29 and common.SCAN[46] == 0x35, "scan map shape")
T(common.SCAN[:13] == [0x29, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13] and common.SCAN[13:26] == list(range(0x10, 0x1A)) + [0x1A, 0x1B, 0x2B], "number and QWERTY rows")
T(common.SCAN[26:37] == list(range(0x1E, 0x27)) + [0x27, 0x28] and common.SCAN[37:] == list(range(0x2C, 0x33)) + [0x33, 0x34, 0x35], "home and bottom rows")

# ---- S-2 with a fake Windows: two layouts built from the repository's own tables
sys.path.insert(0, os.path.join(HERE, "..", "reference"))
import lfengine as E
s2 = load("windows/s2_layout_fingerprint.py")
class FakeWin:
    def __init__(self, foreign=True, accepts=True, same=False): self.foreign, self.accepts, self.same = foreign, accepts, same
    def layouts(self): return [0x04090409, 0x04190419]
    def _entries(self, hkl):
        lay = E.EN if hkl == 0x04090409 or self.same else E.RU
        return E.table_entries(lay)
    def translate(self, hkl, scan, shift):
        if not self.accepts and hkl not in self.layouts(): return ""
        return self._entries(hkl)[2 * common.SCAN.index(scan) + shift]
    def foreground_hkl(self):
        if not self.foreign: raise RuntimeError("no")
        return 0x04190419
body = s2.measure(FakeWin())
T(body["layouts_tested"] == 2 and S.RULES["S-2"](body)[0] == "CONFIRMED", "S-2 fake: two layouts, distinct fingerprints")
T(list(body["fingerprints"].values())[0] == E.layout_fingerprint(E.table_entries(E.EN)), "S-2: the fingerprint equals layout_fingerprint of the reference")
T(S.RULES["S-2"](s2.measure(FakeWin(same=True)))[0] == "REFUTED", "S-2 fake: equal layouts refute")
T(S.RULES["S-2"](s2.measure(FakeWin(foreign=False)))[0] == "REFUTED", "S-2 fake: no foreign HKL")
T(s2.fingerprint_entries(lambda s, sh: "")[0] == "\x00", "S-2: no character is the entry NUL")

# ---- S-5 with a fake hotkey API
s5 = load("windows/s5_hotkey.py")
class FakeHot:
    def __init__(self, withheld=True, conflict=1409, release=True): self.w, self.c, self.r, self.reg = withheld, conflict, release, False
    def register(self): self.reg = True; return True
    def unregister(self): return self.r
    def register_other_thread(self): return self.c
    def run_trial(self): return (1, 0 if self.w else 1)
b = s5.measure(FakeHot(), 100); T(S.RULES["S-5"](b)[0] == "CONFIRMED", "S-5 fake: good")
T(S.RULES["S-5"](s5.measure(FakeHot(withheld=False), 100))[0] == "REFUTED", "S-5 fake: the key also reaches the application")
T(S.RULES["S-5"](s5.measure(FakeHot(conflict=0), 100))[0] == "REFUTED", "S-5 fake: no conflict error")
T(S.RULES["S-5"](s5.measure(FakeHot(release=False), 100))[0] == "REFUTED", "S-5 fake: release fails")
class NoReg(FakeHot):
    def register(self): return False
class Lost(FakeHot):
    def run_trial(self): return (0, 0)
T(S.RULES["S-5"](s5.measure(NoReg(), 100))[0] == "REFUTED", "S-5 fake: registration fails")
T(S.RULES["S-5"](s5.measure(Lost(), 100))[0] == "REFUTED", "S-5 fake: the hotkey message never comes")

# ---- S-7 with a fake Mac
s7 = load("macos/s7_tag_and_batch.py")
class FakeMac:
    def __init__(self, cut=None, tag=True): self.cut, self.tag, self.txt, self.n = cut, tag, "", 0
    def reset(self): self.txt = ""
    def post(self, t):
        self.txt += t if self.cut is None or len(t) <= self.cut else t[:self.cut]
        self.n += 1 if self.tag else 0
    def delivered(self): return self.txt
    def tag_count(self): return self.n
b = s7.measure(FakeMac(), 1000); T(b["max_units_delivered_whole"] == 40 and S.RULES["S-7"](b)[0] == "CONFIRMED", "S-7 fake: good")
b = s7.measure(FakeMac(cut=12), 1000); T(b["max_units_delivered_whole"] == 12 and S.RULES["S-7"](b)[0] == "REFUTED", "S-7 fake: batches above 12 are cut")
T(S.RULES["S-7"](s7.measure(FakeMac(tag=False), 1000))[0] == "REFUTED", "S-7 fake: tag unseen")

# ---- S-6 with a fake Mac: the keycodes against the reference tables
s6 = load("macos/s6_keycodes_and_fingerprint.py")
T(s6.KEYCODE[0] == 50 and s6.KEYCODE[13] == 12 and s6.KEYCODE[26] == 0 and s6.KEYCODE[37] == 6 and s6.KEYCODE[46] == 44 and len(set(s6.KEYCODE)) == 47, "S-6: the key code map (grave, q, a, z, slash)")
SUP = {"U.S.": E.layout_fingerprint(E.table_entries(E.EN)), "Russian - PC": E.layout_fingerprint(E.table_entries(E.RU))}
class FakeMac6:
    def __init__(self, names=("U.S.", "Russian - PC"), typed_wrong=False, same=False, dead=False):
        self.names, self.cur, self.tw, self.same, self.dead = names, None, typed_wrong, same, dead
    def sources(self): return list(self.names)
    def select(self, n): self.cur = n
    def _table(self): return E.EN if self.cur == "U.S." or self.same else E.RU
    def uc_char(self, kc, shift):
        if self.dead and kc == 50: return "\x00"
        return E.table_entries(self._table())[2 * s6.KEYCODE.index(kc) + shift]
    def typed_char(self, kc, shift):
        c = self.uc_char(kc, shift)
        if self.tw and self.cur == "Russian - PC" and kc == 12: return "x"
        return "" if c == "\x00" else c
b = s6.measure(FakeMac6(), SUP)
T(b["keycodes_equal_on_all"] and b["fingerprint_distinct"] and S.RULES["S-6"](b)[0] == "CONFIRMED", "S-6 fake: good")
T(b["fingerprints"]["U.S."] == SUP["U.S."] and b["fingerprints"]["Russian - PC"] == SUP["Russian - PC"], "S-6: the fingerprints are the reference engine's")
b = s6.measure(FakeMac6(typed_wrong=True), SUP); T(not b["keycodes_equal_on_all"] and S.RULES["S-6"](b)[0] == "REFUTED", "S-6 fake: a key code that depends on the source")
b = s6.measure(FakeMac6(same=True), SUP); T(not b["fingerprint_distinct"] and S.RULES["S-6"](b)[0] == "REFUTED", "S-6 fake: two sources with one fingerprint")
b = s6.measure(FakeMac6(names=("U.S.",)), SUP); T(S.RULES["S-6"](b)[0] == "INCOMPLETE", "S-6 fake: Russian - PC missing")
b = s6.measure(FakeMac6(), {"U.S.": "0" * 64, "Russian - PC": SUP["Russian - PC"]}); T(not b["matches_supported_fingerprints"] and S.RULES["S-6"](b)[0] == "REFUTED", "S-6 fake: a fingerprint other than the supported one")
b = s6.measure(FakeMac6(dead=True), SUP); T(b["keycodes_equal_on_all"] and s6.entries(lambda kc, sh: "\x00" if kc == 50 else "a")[0] == "\x00", "S-6: a dead key is the entry NUL and typed nothing agrees")

# ---- a file written by the programs without a real machine is never evidence
h = common.header("S-7", "macos", "x", synthetic=True)
T(S.evaluate({**h, **b})[0] == "INVALID", "a synthetic header is INVALID")
T(common.header("S-2", "windows", "x")["synthetic"] is False, "a header is not synthetic unless asked")
print(f"OK ({N} measuring-program logic checks, fake bindings only; no spike was run)")
