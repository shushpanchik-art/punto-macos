#!/usr/bin/env python3
"""Tests of the spike validator with SYNTHETIC files. They prove the decision rules, not any platform fact."""
import copy
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import spikes as S

N = 0
def T(c, what):
    global N
    N += 1
    if not c:
        raise AssertionError(what)
def base(spike, os_, **kw):
    d = {"spike": spike, "os": os_, "os_build": "synthetic-build", "machine": "synthetic-machine", "tool_revision": "t0",
         "started_utc": "2026-01-01T00:00:00Z", "synthetic": False}
    d.update(kw); return d
def v(d): return S.evaluate(d)[0]

good = {
 "S-1": base("S-1", "windows", events_total=100_000, matched=100_000, raw_only=0, hook_only=0, hook_removed_by_os=False),
 "S-2": base("S-2", "windows", foreign_thread_hkl_ok=True, to_unicode_ex_accepts_foreign_hkl=True, layouts_tested=2, fingerprints={"a": "x", "b": "y"}),
 "S-3": base("S-3", "windows", elevated_input_reaches_hook=True, autorepeat_events=1000, autorepeat_mismatches=0, conflict_reported_by_os=True),
 "S-4": base("S-4", "windows", classes=[{"application": "Notepad", "control_class": "edit", "trials": 100, "full_value": True, "range_replace": True, "caret_kept": True, "rollback_verified": True, "read_only": False, "unsupported": False}]),
 "S-5": base("S-5", "windows", registered=True, key_reached_application=False, conflict_error=True, released_cleanly=True, trials=100),
 "S-6": base("S-6", "macos", layouts=["Russian - PC", "U.S."], keycodes_equal_on_all=True, fingerprint_call="UCKeyTranslate", fingerprint_distinct=True),
 "S-7": base("S-7", "macos", tag_seen_by_tap=True, own_events=1000, max_units_per_batch_tested=40, max_units_delivered_whole=20),
}
for k, d in good.items():
    T(v(d) == "CONFIRMED", f"{k}: a complete good file is CONFIRMED")
    T(v({**d, "synthetic": True}) == "INVALID", f"{k}: synthetic is never evidence")
    T(v({**d, "machine": ""}) == "INVALID", f"{k}: an unnamed machine is not evidence")
    T(v({**d, "os": "linux"}) == "INVALID", f"{k}: another OS is invalid")
    for f in [f for f in d if f not in S.COMMON][:1]:
        e = copy.deepcopy(d); del e[f]; T(v(e) == "INCOMPLETE", f"{k}: missing {f} is INCOMPLETE")
T(v({**good["S-1"], "raw_only": 1, "matched": 99_999}) == "REFUTED", "S-1: a lost key refutes")
T(v({**good["S-1"], "events_total": 5}) == "INCOMPLETE", "S-1: too few events")
T(v({**good["S-1"], "matched": 1}) == "INVALID", "S-1: counts that do not add up")
T(v({**good["S-2"], "fingerprints": {"a": "x", "b": "x"}}) == "REFUTED", "S-2: equal fingerprints refute")
T(v({**good["S-2"], "to_unicode_ex_accepts_foreign_hkl": False}) == "REFUTED", "S-2: no foreign HKL: the pair stays OFF")
T(v({**good["S-3"], "autorepeat_mismatches": 2}) == "REFUTED", "S-3: auto-repeat disagreement")
T(v({**good["S-4"], "classes": [{**good["S-4"]["classes"][0], "rollback_verified": False}]}) == "INVALID", "S-4: REPLACE_RANGE without a verified rollback is invalid")
T(v({**good["S-5"], "key_reached_application": True}) == "REFUTED", "S-5: the application also got the key")
T(v({**good["S-6"], "layouts": ["U.S."]}) == "INCOMPLETE", "S-6: Russian - PC is required")
T(v({**good["S-7"], "max_units_delivered_whole": 12}) == "REFUTED", "S-7: chunks of 20 do not hold")
T(v({**good["S-7"], "tag_seen_by_tap": False}) == "REFUTED", "S-7: tag invisible")
T(v("x") == "INVALID" and v({"spike": "S-9"}) == "INVALID", "garbage")
print(f"OK ({N} spike validator checks, synthetic data only)")
