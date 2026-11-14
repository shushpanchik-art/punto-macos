import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rt16_bounds as B, lfengine as L
CHECKS = 0
def T(c, w):
    global CHECKS
    CHECKS += 1
    if not c: raise AssertionError(w)
for W in (300, 290, 250, 200, 150, 1, 2):
    T(B.boundary(W), f"strict comparison: age {W} healthy, age {W + 1} lost")
for W in (300, 250, 200, 150):
    for P in (100, 50, 10, 1):
        for late in (0, 10, 50, 150):
            lo, hi = B.exhaustive(W, P, late)
            T((lo, hi) == (W + 1 + late, W + P + late), f"W={W} P={P} late={late}: {lo} {hi}")
T(L.HookHealth.CANARY_MS == 300, "the class constant is restored after every run (nothing normative was changed)")
# the current code can never meet a strict 300 ms; the figures that do meet it have NO margin
T(B.exhaustive(300, 100, 0)[0] > 300 and B.exhaustive(300, 1, 0)[0] > 300, "W = 300: every phase and every timer period is above 300 ms")
T(B.exhaustive(200, 100, 0)[1] == 300 and B.exhaustive(200, 100, 1)[1] == 301, "W = 200, P = 100: exactly 300 ms with an ideal timer, 301 ms with 1 ms of scheduler delay")
T(B.exhaustive(290, 10, 0)[1] == 300 and B.exhaustive(250, 50, 0)[1] == 300, "W = 290 / P = 10 and W = 250 / P = 50: exactly 300 ms, no margin")
print(f"OK ({CHECKS} RT-16 bound checks, exhaustive over timer phases, generated timelines only)")
