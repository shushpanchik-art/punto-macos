"""Reproducible sweep behind audit/RT16_vs_HookHealth.md: for a window CANARY_MS and a timer tick, the shortest and the longest time from
the first physical key that the hook did not report to the moment HookHealth declares the loss (300 random streams, key gaps of
30 to 120 ms, random phase). It changes the class constant only inside this process; it never edits lfengine.py. Generated streams only. THIS IS A SAMPLE (300 random streams): its maxima are not bounds; the exact bounds are in rt16_bounds.py."""
import os, random, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import slowhook as S
import lfengine as L

def sweep(canary, tick, n=300, seed=1):
    old = L.HookHealth.CANARY_MS
    L.HookHealth.CANARY_MS = canary
    try:
        rnd, lo, hi = random.Random(seed), None, None
        for _ in range(n):
            t, raw = 1000 + rnd.randint(0, 99), []
            for i in range(40):
                t += rnd.randint(30, 120); raw.append((t, 30 + i % 9, 0, i % 2))
            d = S.replay(raw, raw[:rnd.randint(5, 30)], tick_ms=tick)["detect_ms"]
            if d is not None:
                lo, hi = (d if lo is None else min(lo, d)), (d if hi is None else max(hi, d))
        return lo, hi
    finally:
        L.HookHealth.CANARY_MS = old

if __name__ == "__main__":
    print("CANARY_MS  tick  min  max   (ms from the first lost key to the declaration)")
    for c in (300, 290, 250, 200):
        for tk in (100, 50, 10):
            lo, hi = sweep(c, tk)
            print(f"{c:9d} {tk:5d} {lo:4.0f} {hi:4.0f}   {'<= 300' if hi <= 300 else '> 300'}")
