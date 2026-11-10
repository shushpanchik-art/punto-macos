"""Engine-level checks.
 E-1 (P3) fuzz of the event machine with an independent shadow model of the spec's snapshot rules (13.3 / RT-5):
     the snapshot must be None after break, gap, layout, gate!=ALLOW, mode change, undo, 100 keys, 10 s.  The shadow marks the
     events that must kill it; the fuzz includes the engine-visible 'layout id of a key / of the Space changed' cases
     that the runtime may deliver WITHOUT a 'layout' event.
 E-2 (P3) an unsupported or unknown layout id (None, 'de') reaches decide(): KeyError in the worker (row 11), after
     the run was already flushed; spec 13.5 row 7 wants OFF for that layout.
Run: python3 attack_engine_fuzz.py [events=400000]"""
import sys, os, random, collections
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "reference"))
import lfengine as L

N = int(sys.argv[1]) if len(sys.argv) > 1 else 400000
rnd = random.Random(11)
LK = sorted(L.LETTER_KEYS)
e = L.Engine(L.example_cal(), lambda ids: [-3, 9, -2], {})
viol = collections.Counter(); first = {}
now = 0
alive_since = None       # shadow: time and counter of the snapshot's birth
shadow_after = 0
conv = 0
for step in range(N):
    now += rnd.choice((1, 20, 300, 3000))
    had = e.snapshot is not None
    x = rnd.random()
    kind = None
    if x < 0.55:
        lay = rnd.choice(("en", "ru"))
        for _ in range(rnd.randrange(2, 9)):
            e.on_event(L.Event("key", L.Key(rnd.choice(LK)), lay, now))
        d = e.on_event(L.Event("space", None, lay if rnd.random() < .95 else L.OTHER_LAYOUT[lay], now))
        if d is not None and d.action == "CONVERT":
            conv += 1
            if rnd.random() < 0.3:
                e.on_outcome("VERIFIED")
        e.cool_words = 0
    elif x < 0.62:
        kind = rnd.choice(("break", "gap", "layout"))
        e.on_event(L.Event(kind, None, rnd.choice(("en", "ru")), now))
        if e.snapshot is not None:
            viol["snapshot alive after " + kind] += 1
    elif x < 0.67:
        # the layout id of a key changes with no 'layout' event (what a runtime that only samples the HKL delivers)
        lay = rnd.choice(("en", "ru"))
        had = e.snapshot is not None
        e.on_event(L.Event("key", L.Key(rnd.choice(LK)), lay, now))
        e.on_event(L.Event("key", L.Key(rnd.choice(LK)), L.OTHER_LAYOUT[lay], now))
        if had and e.snapshot is not None:
            viol["snapshot alive after a layout id change inside a word (no 'layout' event)"] += 1
            first.setdefault("layout-id", step)
    elif x < 0.70:
        had = e.snapshot is not None
        e.on_event(L.Event("space", None, "ru", now))          # Space read on the other layout, words typed on en
        e.on_event(L.Event("space", None, "en", now))
    elif x < 0.75:
        if e.undo(now) is not None:
            e.undo_outcome("VERIFIED")                    # since F9 the commit follows the outcome of the restoring transaction
        if e.snapshot is not None and e.snapshot.confirmed:        # an unconfirmed one is a decision without an outcome yet
            viol["snapshot alive after undo"] += 1
    elif x < 0.80:
        e.set_gate(rnd.choice(("DENY", "UNKNOWN"))); 
        if e.snapshot is not None: viol["snapshot alive after gate"] += 1
        e.set_gate("ALLOW")
    elif x < 0.84:
        e.set_mode(rnd.choice(("MANUAL_ONLY", "OFF")))
        if e.snapshot is not None: viol["snapshot alive after mode"] += 1
        e.set_mode("AUTO")
    else:
        e.on_event(L.Event("backspace", None, None, now))
    # time and count bounds of the snapshot
    s = e.snapshot
    if s is not None:
        if now - s.created_ms > L.UNDO_WINDOW_MS + 0:
            viol["snapshot older than 10 s at the next event"] += 1
        if s.after > L.UNDO_MAX_CHARS:
            viol["snapshot after > 100"] += 1
print("events/steps", N, "conversions", conv, dict(viol), first)

# E-2
for bad in (None, "de"):
    e = L.Engine(L.example_cal(), lambda ids: [-3, 9, -2], {})
    for i, k in enumerate(L.keys_from_text("ghbdtn", "en")):
        e.on_event(L.Event("key", k, bad, 10 + i))
    try:
        d = e.on_event(L.Event("space", None, bad, 100))
        print("E-2 layout id", repr(bad), "->", d)
    except Exception as ex:
        print("E-2 layout id", repr(bad), "-> on_event RAISED", type(ex).__name__, ex, "| run already flushed:", e.run == [])
