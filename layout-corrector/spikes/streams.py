"""Comparison of two streams of physical key events, one by one by signature (RT-16, 13.7 row "Event-stream health").

An event is (ts_ms, scan, extended, up): the time it was seen, the scan code, the extended flag and the direction. Injected
events are not passed in (the callers drop them: the hook by LLKHF_INJECTED, the raw input observer never sees them). A pair
is two events with the same signature (scan, extended, up) seen by the two sources at most `window_ms` apart, either first;
the first unused counterpart in time order is taken. An event of the first stream without a partner is `lost_by_b` (the
second source missed it); an event of the second stream without a partner is `extra_in_b`. A count would hide one lost and
one extra event; the signature does not."""
from collections import defaultdict, deque


def compare(a, b, window_ms=300):
    """a: the reference stream (Raw Input on Windows), b: the observed stream (the hook). Returns a dict with the counts."""
    ia = defaultdict(deque)
    for ev in a:
        ia[(ev[1], ev[2], ev[3])].append(ev[0])
    ib = defaultdict(deque)
    for ev in b:
        ib[(ev[1], ev[2], ev[3])].append(ev[0])
    matched = lost = extra = 0
    for sig in set(ia) | set(ib):
        qa, qb = ia[sig], ib[sig]
        while qa and qb:
            ta, tb = qa[0], qb[0]
            if abs(ta - tb) <= window_ms:
                qa.popleft(); qb.popleft(); matched += 1
            elif ta < tb:                      # the earlier one has no partner in time
                qa.popleft(); lost += 1
            else:
                qb.popleft(); extra += 1
        lost += len(qa)
        extra += len(qb)
    return {"events_a": len(a), "events_b": len(b), "matched": matched, "lost_by_b": lost, "extra_in_b": extra}
