"""slowhook.py - the product-side observer measurement of S-1 (RT-16): how long after a hook stops reporting does the
product's own health logic (`HookHealth`, 13.5 row 13) declare the stream lost?

`replay` feeds recorded streams (the Raw Input observer and the hook, each a list of (ts_ms, scan, extended, direction)
on ONE clock) into the real `HookHealth` exactly as the runtime does (`raw_key`, `hook_key`, a timer tick every `tick_ms`
<= 100 ms as in `Runtime.on_tick`), and returns the time from the first physical key that the hook did not report to the
moment the loss was declared. The logic is the reference code; whether the timing figures are true on Windows is decided only by a
run of `windows/s1_s3_capture.py s1slow` with a really slowed hook. Replaying generated streams (test_slowhook.py) checks the
logic of this function, not the OS."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reference"))
import lfengine as L  # noqa: E402


def replay(raw, hook, tick_ms=100, sig=lambda e: e[1:]):
    """Returns {first_lost_ts, declared_at, detect_ms, reason}; detect_ms is None when nothing was lost or never declared."""
    if tick_ms <= 0 or tick_ms > 100:
        raise ValueError("the runtime timer runs at most every 100 ms")
    h = L.HookHealth(canary=True)
    ev = sorted([(e[0], 0, e) for e in raw] + [(e[0], 1, e) for e in hook], key=lambda x: (x[0], x[1]))
    if not raw:
        return {"first_lost_ts": None, "declared_at": None, "detect_ms": None, "reason": None}
    end = max(ev[-1][0], raw[-1][0]) + L.HookHealth.CANARY_MS + 2 * tick_ms
    t, i, declared = ev[0][0], 0, None
    tick = int(t)
    while tick <= end and declared is None:
        while i < len(ev) and ev[i][0] <= tick:
            ts, src, e = ev[i]
            (h.raw_key if src == 0 else h.hook_key)(int(ts), sig(e))
            i += 1
            if not h.ok:
                declared = max(ts, 0)
                break
        if declared is None:
            h.check(tick)
            if not h.ok:
                declared = tick
        tick += tick_ms
    # the first raw event that no hook event with the same signature accompanied
    pool = {}
    for e in hook:
        pool.setdefault(sig(e), []).append(e[0])
    lost = None
    for e in sorted(raw):
        c = pool.get(sig(e), [])
        j = next((k for k, x in enumerate(c) if abs(x - e[0]) <= L.HookHealth.CANARY_MS), None)
        if j is None:
            lost = e[0]
            break
        c.pop(j)
    if lost is None or declared is None:
        return {"first_lost_ts": lost, "declared_at": declared, "detect_ms": None, "reason": h.reason}
    return {"first_lost_ts": lost, "declared_at": declared, "detect_ms": max(0.0, declared - lost), "reason": h.reason}
