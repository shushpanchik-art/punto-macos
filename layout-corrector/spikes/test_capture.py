#!/usr/bin/env python3
"""Tests of the decision logic of windows/s1_s3_capture.py (finish_s1, finish_s3) with GENERATED streams. They prove that the
bodies agree with spikes.py and that lost, extra and cancelling pairs are found; they say nothing about Windows."""
import importlib.util, os, random, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import spikes as S
spec = importlib.util.spec_from_file_location("cap", os.path.join(HERE, "windows", "s1_s3_capture.py")); C = importlib.util.module_from_spec(spec); spec.loader.exec_module(C)
N = 0
def T(c, w):
    global N; N += 1
    if not c: raise AssertionError(w)
rnd = random.Random(2)
def gen(n): return [(i * 25.0 + rnd.random(), rnd.choice((30, 31, 32, 57, 28)), rnd.randint(0, 1), i % 2) for i in range(n)]
raw = gen(1_000_000)
hook = [(t + 3, s, x, u) for (t, s, x, u) in raw]
b = C.finish_s1(raw, hook, "USB HID generator", 120.0)
T(b["events_total"] == 1_000_000 and b["matched"] == 1_000_000 and S.RULES["S-1"](b)[0] == "CONFIRMED", "S-1: a faithful hook, a million events")
b = C.finish_s1(raw, hook[:-1], "g", 120.0); T(b["lost_by_hook"] == 1 and S.RULES["S-1"](b)[0] == "REFUTED", "S-1: one lost key")
h2 = list(hook); h2[500] = (h2[500][0], h2[500][1] + 1, h2[500][2], h2[500][3])
b = C.finish_s1(raw, h2, "g", 120.0); T(b["lost_by_hook"] == 1 and b["extra_in_hook"] == 1 and len(h2) == len(raw) and S.RULES["S-1"](b)[0] == "REFUTED", "S-1: one lost and one extra cancel in a count, not here")
b = C.finish_s1(raw, hook, "g"); T(b["slow_hook_detect_ms"] is None and S.RULES["S-1"](b)[0] == "INCOMPLETE", "S-1: the program never invents the slow-hook time")
b = C.finish_s1(raw[:1000], hook[:1000], "g", 100.0); T(S.RULES["S-1"](b)[0] == "INCOMPLETE", "S-1: a short run is incomplete")
b = C.finish_s1(raw, hook, "g", 100.0, hook_removed=True); T(S.RULES["S-1"](b)[0] == "REFUTED", "S-1: the hook removed by the OS")
el = gen(150); elh = [(t + 2, s, x, u) for (t, s, x, u) in el]; rp = [(i * 30.0, 30, 0, 0) for i in range(1200)]; rph = [(t + 1, s, x, u) for (t, s, x, u) in rp]
b = C.finish_s3(True, True, el, elh, rp, rph); T(S.RULES["S-3"](b)[0] == "CONFIRMED" and b["elevated_input_reaches_hook"], "S-3: all three hold")
b = C.finish_s3(True, True, el, [], rp, rph); T(not b["elevated_input_reaches_hook"] and S.RULES["S-3"](b)[0] == "REFUTED", "S-3: an elevated window the hook cannot see")
b = C.finish_s3(True, False, el, elh, rp, rph); T(b["elevated_events_raw"] == 0 and S.RULES["S-3"](b)[0] == "INCOMPLETE", "S-3: no elevated window in the foreground: not measured, never CONFIRMED")
b = C.finish_s3(True, True, el, elh, rp, rph[:-3]); T(b["autorepeat_mismatches"] == 3 and S.RULES["S-3"](b)[0] == "REFUTED", "S-3: auto-repeat mismatches")
b = C.finish_s3(False, True, el, elh, rp, rph); T(S.RULES["S-3"](b)[0] == "REFUTED", "S-3: a taken chord not reported")
b = C.finish_s3(True, True, el, elh, rp[:500], rph[:500]); T(S.RULES["S-3"](b)[0] == "INCOMPLETE", "S-3: fewer than 1,000 auto-repeat events")
print(f"OK ({N} capture decision checks, generated streams only)")
