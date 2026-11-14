#!/usr/bin/env python3
import os, random, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import streams as S
N = 0
def T(c, w):
    global N; N += 1
    if not c: raise AssertionError(w)
e = lambda t, scan, up=0, ext=0: (t, scan, ext, up)
T(S.compare([], []) == {"events_a": 0, "events_b": 0, "matched": 0, "lost_by_b": 0, "extra_in_b": 0}, "empty")
a = [e(0, 30), e(10, 30, 1), e(100, 31), e(110, 31, 1)]
T(S.compare(a, list(a))["matched"] == 4, "equal streams")
r = S.compare(a, a[:3]); T(r["lost_by_b"] == 1 and r["extra_in_b"] == 0, "one lost")
r = S.compare(a[:3], a); T(r["extra_in_b"] == 1 and r["lost_by_b"] == 0, "one extra")
# one lost and one extra cancel in a count, never in the signature comparison
b = [e(0, 30), e(10, 30, 1), e(100, 31), e(112, 32, 1)]
r = S.compare(a, b); T(len(a) == len(b) and r["lost_by_b"] == 1 and r["extra_in_b"] == 1 and r["matched"] == 3, "lost and extra cancel in a count only")
T(S.compare([e(0, 30)], [e(300, 30)])["matched"] == 1, "300 ms apart is a pair (inclusive)")
r = S.compare([e(0, 30)], [e(301, 30)]); T(r["matched"] == 0 and r["lost_by_b"] == 1 and r["extra_in_b"] == 1, "301 ms apart is not")
T(S.compare([e(0, 30)], [e(-200, 30)])["matched"] == 1, "either may come first")
T(S.compare([e(0, 30)], [e(0, 30, 0, 1)])["matched"] == 0, "the extended flag is part of the signature")
T(S.compare([e(0, 30)], [e(0, 30, 1)])["matched"] == 0, "the direction is part of the signature")
# repeated key: a held key makes many equal signatures; an exactly missing one in the middle is found
a = [e(i * 30, 30) for i in range(50)]; b = a[:20] + a[21:]
T(S.compare(a, b)["lost_by_b"] == 1 and S.compare(a, b)["matched"] == 49, "one lost in an auto-repeat run")
b = a[:20] + [e(20 * 30 + 5, 30)] + a[20:]; r = S.compare(a, b); T(r["extra_in_b"] == 1 and r["matched"] == 50, "one extra in an auto-repeat run")
# random: a stream compared with a shuffled in-window copy matches fully; with k removed, lost == k
rnd = random.Random(5); a = [e(i * 40 + rnd.randint(0, 5), rnd.choice((30, 31, 32, 57)), rnd.randint(0, 1)) for i in range(2000)]
b = sorted([(t + rnd.randint(-20, 20), s, x, u) for (t, s, x, u) in a])
T(S.compare(a, b)["matched"] == 2000, "jitter inside the window")
drop = set(rnd.sample(range(2000), 37)); b2 = [ev for i, ev in enumerate(b) if i not in drop]
r = S.compare(a, b2); T(r["lost_by_b"] == 37 and r["extra_in_b"] == 0, "k removed events are k lost")
print(f"OK ({N} stream comparison checks)")
