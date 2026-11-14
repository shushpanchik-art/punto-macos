"""rt16_bounds.py - the detection time of HookHealth (RT-16, 13.5 row 13) as a GUARANTEE under stated assumptions, checked
exhaustively over every integer timer phase with the real `HookHealth` class. It never edits lfengine.py (the window is changed
only on the class attribute inside this process). Generated timelines only: nothing here is a measurement of any operating system.

Definitions. A physical key arrives at the independent observer at time 0 (the first key the hook never reports); `W` is
`HookHealth.CANARY_MS`; the runtime timer calls `check(now)` at integer times; no further key arrives (the worst case: a later
event could only declare the loss earlier). D = the time of the first `check` that finds the loss.
Assumptions (all of them unverified on a real system): A1 one monotonic integer-millisecond clock for both sources; A2 the timer
fires with a gap of at most P ms between consecutive checks, and the one that decides is late by at most L ms (scheduler delay);
A3 the observer saw the key at time 0 (its own latency is not counted).
Result (proved by the strict comparison `now - ts > W` and checked below): W + 1 <= D <= W + P + L. The upper bound is reached,
so it is the exact worst case, not a sampled figure."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reference"))
import lfengine as L  # noqa: E402


def detect(W, P, phase, late=0, horizon=None):
    """D for window W, timer period P, tick phase (0 <= phase < P, the first nominal tick at or after the key), and a scheduler delay
    `late` applied to the decisive tick only (the first nominal tick that would find the loss)."""
    old = L.HookHealth.CANARY_MS
    L.HookHealth.CANARY_MS = W
    try:
        h = L.HookHealth(canary=True)
        h.raw_key(0, ("k", 1))
        nominal = [phase + k * P for k in range(0, (W + 2 * P + late) // P + 3)]
        decisive = next(t for t in nominal if t - 0 > W)
        for t in nominal:
            at = t + late if t == decisive else t
            if h.ok and h.check(at) is False:
                return at
            if not h.ok:
                return at
        raise AssertionError("never declared")
    finally:
        L.HookHealth.CANARY_MS = old


def exhaustive(W, P, late):
    ds = [detect(W, P, ph, late) for ph in range(P)]
    return min(ds), max(ds)


def boundary(W):
    """The strict comparison: at age W the event is still healthy, at W + 1 it is lost."""
    old = L.HookHealth.CANARY_MS
    L.HookHealth.CANARY_MS = W
    try:
        a = L.HookHealth(canary=True); a.raw_key(0, ("k", 1))
        b = L.HookHealth(canary=True); b.raw_key(0, ("k", 1))
        return a.check(W) is True and b.check(W + 1) is False
    finally:
        L.HookHealth.CANARY_MS = old


if __name__ == "__main__":
    print("W    P   late  min  max  (= W+1+late .. W+P+late)  meets 300 with margin m = 300 - max")
    for W in (300, 290, 250, 200, 150):
        for P in (100, 50, 10):
            for late in (0, 10, 50):
                lo, hi = exhaustive(W, P, late)
                print(f"{W:3d} {P:4d} {late:5d} {lo:4d} {hi:4d}   {'ok' if (lo, hi) == (W + 1 + late, W + P + late) else 'FORMULA BROKEN'}   margin {300 - hi:4d}")
