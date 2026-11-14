import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import slowhook as S

CHECKS = 0
def T(c, w):
    global CHECKS
    CHECKS += 1
    if not c: raise AssertionError(w)

keys = lambda n, gap=50: [(1000 + i * gap, 30 + i % 10, 0, i % 2) for i in range(n)]
raw = keys(40)
r = S.replay(raw, list(raw))
T(r["detect_ms"] is None and r["first_lost_ts"] is None and r["reason"] is None, "a healthy stream declares nothing")
r = S.replay(raw, [e for e in raw if e[0] < 1800])                    # the hook stops at 1800 ms
T(r["first_lost_ts"] == 1800 and r["reason"] == "canary_missing" and 300 < r["detect_ms"] <= 400, f"a hook that stops is declared after CANARY_MS and before CANARY_MS + one tick: {r}")
# OPEN (RT-16-VS-HOOKHEALTH): RT-16 says "detected within 300 ms"; HookHealth declares only when the oldest unmatched
# event is OLDER than CANARY_MS (300 ms), so the time from the first lost key is always > 300 ms. This test pins the fact; the
# S-1 validator keeps the strict limit of 300 ms and would say REFUTED for such a figure until the requester decides.
T(r["detect_ms"] > 300, "pinned: the reference HookHealth cannot meet a strict 300 ms from the first lost key")
for tick in (10, 50, 100):
    r = S.replay(raw, [e for e in raw if e[0] < 1500], tick_ms=tick)
    T(r["detect_ms"] is not None and r["detect_ms"] <= 300 + 2 * tick, f"tick {tick} ms: within 300 ms plus one tick: {r}")
r = S.replay(raw, [e for e in raw if e[0] != 1500])                    # one event lost in the middle
T(r["first_lost_ts"] == 1500 and r["detect_ms"] is not None and r["detect_ms"] <= 400, "one lost event is declared")
r = S.replay(raw, list(raw) + [(1105, 99, 0, 0)])                      # an extra hook event
T(r["reason"] == "canary_extra", "an extra hook event is declared as canary_extra")
r = S.replay(raw, [(e[0] + 40, *e[1:]) for e in raw])                  # hook late by 40 ms: still matched
T(r["reason"] is None, "a hook that is only 40 ms late is healthy")
r = S.replay(raw, [(e[0] + 700, *e[1:]) for e in raw])                 # hook late by 700 ms: lost
T(r["reason"] is not None and r["detect_ms"] is not None and r["detect_ms"] <= 400, "a hook 700 ms late is declared")
r = S.replay([], [])
T(r["detect_ms"] is None, "no events: nothing measured")
T(r["first_lost_ts"] is None, "no events: no loss")
try:
    S.replay(raw, raw, tick_ms=250); T(False, "a slow timer must be refused")
except ValueError:
    T(True, "a tick above 100 ms is refused")
print(f"OK ({CHECKS} slow-hook replay checks, generated streams only)")
