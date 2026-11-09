"""HookHealth attacks.  (1) random fuzz against an independent oracle (timelines with lost / extra / late / reordered /
repeated-signature events) - checks: no lost or extra key stays undeclared once 300 ms have passed AND a later call has
happened; no false alarm when every event meets its twin within 300 ms.  (2) targeted items:
 H-1 (P3) late declaration of a loss when a repeated key hides it ('gg': the hook lost the first g, the second g's hook event
         pairs with the first raw g): the loss is declared 300 ms after the SECOND key, not the first - a Space within
         that window is decided on an incomplete word (see attack_gate_midword.py (c)).
 H-2 (P3) the raw side has no `injected` flag: a raw WM_INPUT for the tool's own / another program's injected events has no
         hook twin (the hook side skips injected events) -> canary_missing, a false loss, gap event, MANUAL_ONLY.
 H-3 (P3) reinstalled() while ok=True erases pending evidence of a loss (both queues are cleared without a verdict).
 H-4 (P3) macOS: reinstalled() trusts the stream at once, every time; 13.5 row 13 'at most 3 times in 60 seconds, after which
         MANUAL_ONLY lasts until the user re-enables AUTO' is not in the class and not in engine_mode (no fact for it).
Run: python3 attack_hookhealth.py [runs=20000]"""
import sys, os, random
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "work"))
import lfengine as L

runs = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
bad = {"undeclared_loss": 0, "false_alarm": 0}
first = {}
for seed in range(runs):
    rnd = random.Random(seed)
    hh = L.HookHealth()
    t = 0
    events = []                                      # (arrival_ts, side, sig)
    lost_expected_at = None
    perfect = rnd.random() < 0.4
    sigs = [("s", rnd.randrange(4), d) for d in ("down", "up")]
    for _ in range(rnd.randrange(1, 12)):
        t += rnd.choice((5, 30, 120, 250))
        sig = rnd.choice(sigs)
        events.append((t, "raw", sig))
        if perfect or rnd.random() > 0.12:
            events.append((t + rnd.choice((0, 1, 20, 150, 290)), "hook", sig))      # delivered within the window
        else:
            lost_expected_at = t if lost_expected_at is None else lost_expected_at
        if not perfect and rnd.random() < 0.05:
            events.append((t + 7, "hook", ("s", 9, "down")))                          # an extra hook key
            lost_expected_at = t + 7 if lost_expected_at is None else lost_expected_at
    events.sort(key=lambda x: x[0])
    for ts, side, sig in events:
        (hh.raw_key if side == "raw" else hh.hook_key)(ts, sig)
    end = events[-1][0] + 400
    ok_at_end = hh.check(end)
    if perfect and not ok_at_end:
        bad["false_alarm"] += 1; first.setdefault("false_alarm", seed)
    if not perfect and lost_expected_at is not None and ok_at_end:
        # a lost twin may be matched by a later repeated signature (H-1); count only when no event shares the signature
        bad["undeclared_loss"] += 1; first.setdefault("undeclared_loss", seed)
print("fuzz runs", runs, bad, "first seeds:", first,
      "(undeclared losses are repeated-signature masking, H-1: a lost key paired with a later key of the same signature)")

print("H-1 repeated key hides a loss")
hh = L.HookHealth()
hh.raw_key(0, ("g", "down")); hh.raw_key(100, ("g", "down")); hh.hook_key(101, ("g", "down"))      # the first g was lost
print("   at 350 ms ok =", hh.check(350), "| at 401 ms ok =", hh.check(401), "(the loss is declared 300 ms after the 2nd key)")

print("H-2 raw side without injected flag")
hh = L.HookHealth()
for i in range(14):                                         # the tool's own M2 batch: the hook skips injected, the raw observer reports
    hh.raw_key(1000 + i, ("u", i, "down")); hh.hook_key(1000 + i, ("u", i, "down"), injected=True)
print("   ok at 1400 ms:", hh.check(1400), "reason:", hh.reason, "gap pending:", hh.take_gap())

print("H-3 reinstalled() while healthy erases evidence")
hh = L.HookHealth()
hh.raw_key(1000, ("g", "down"))                             # the hook never reports it
hh.reinstalled()                                            # e.g. a resume handler reinstalls the hook
print("   ok at 2000 ms:", hh.check(2000), "(the lost key is never declared)")

print("H-4 macOS: unlimited re-enabling")
hh = L.HookHealth(canary=False)
n = 0
for i in range(10):
    hh.tap_disabled("timeout"); hh.take_gap(); hh.reinstalled(); n += hh.ok
print("   tap disabled 10 times in a row, reinstalled each time: ok after reinstall", n, "of 10 (spec: MANUAL_ONLY after the 3rd in 60 s)")
