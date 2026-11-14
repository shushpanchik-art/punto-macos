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
 "S-1": base("S-1", "windows", events_total=1_000_000, matched=1_000_000, lost_by_hook=0, extra_in_hook=0, hook_removed_by_os=False, generator="USB HID generator", generator_is_tool_injection=False, slow_hook_detect_ms=120),
 "S-2": base("S-2", "windows", foreign_thread_hkl_ok=True, to_unicode_ex_accepts_foreign_hkl=True, layouts_tested=2, fingerprints={"a": "x", "b": "y"}),
 "S-3": base("S-3", "windows", elevated_input_reaches_hook=True, elevated_events_raw=100, elevated_events_hook=100, autorepeat_events=1000, autorepeat_mismatches=0, conflict_reported_by_os=True),
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
T(v({**good["S-1"], "lost_by_hook": 1, "matched": 999_999}) == "REFUTED", "S-1: a lost key refutes")
T(v({**good["S-1"], "extra_in_hook": 1}) == "REFUTED", "S-1: an extra key refutes even when the counts could cancel")
T(v({**good["S-1"], "hook_removed_by_os": True}) == "REFUTED", "S-1: a hook removed by the OS refutes")
T(v({**good["S-1"], "events_total": 999_999, "matched": 999_999}) == "INCOMPLETE", "S-1: fewer than 1,000,000 events (RT-16)")
T(v({**good["S-1"], "events_total": 100_000, "matched": 100_000}) == "INCOMPLETE", "S-1: the old 100,000 is not enough")
T(v({**good["S-1"], "matched": 1}) == "INVALID", "S-1: counts that do not add up")
T(v({**good["S-1"], "generator_is_tool_injection": True}) == "INVALID", "S-1: the tool's own injection is not a generator")
T(v({**good["S-1"], "generator": " "}) == "INVALID", "S-1: the generator must be named")
T(v({**good["S-1"], "slow_hook_detect_ms": None}) == "INCOMPLETE", "S-1: the slowed hook must be measured")
T(v({**good["S-1"], "slow_hook_detect_ms": 301}) == "REFUTED", "S-1: detection after 301 ms refutes")
T(v({**good["S-1"], "slow_hook_detect_ms": 300}) == "CONFIRMED", "S-1: 300 ms is inside the limit")
T(v({**good["S-3"], "elevated_events_raw": 99, "elevated_events_hook": 99}) == "INCOMPLETE", "S-3: fewer than 100 elevated events")
T(v({**good["S-3"], "elevated_events_hook": 0, "elevated_input_reaches_hook": True}) == "INVALID", "S-3: the flag must follow from the counts")
T(v({**good["S-3"], "elevated_events_hook": 0, "elevated_input_reaches_hook": False}) == "REFUTED", "S-3: elevated input invisible: UNKNOWN there")
T(v({**good["S-3"], "conflict_reported_by_os": False}) == "REFUTED", "S-3: a taken hotkey must be reported")
T(v({**good["S-2"], "fingerprints": {"a": "x", "b": "x"}}) == "REFUTED", "S-2: equal fingerprints refute")
T(v({**good["S-2"], "to_unicode_ex_accepts_foreign_hkl": False}) == "REFUTED", "S-2: no foreign HKL: the pair stays OFF")
T(v({**good["S-3"], "autorepeat_mismatches": 2}) == "REFUTED", "S-3: auto-repeat disagreement")
T(v({**good["S-4"], "classes": [{**good["S-4"]["classes"][0], "rollback_verified": False}]}) == "INVALID", "S-4: REPLACE_RANGE without a verified rollback is invalid")
c4 = good["S-4"]["classes"][0]
T(v({**good["S-4"], "classes": [{**c4, "trials": 99}]}) == "INCOMPLETE", "S-4: fewer than 100 trials")
T(v({**good["S-4"], "classes": []}) == "INCOMPLETE", "S-4: no class")
T(v({**good["S-4"], "classes": [{**c4, "caret_kept": False}]}) == "INVALID", "S-4: REPLACE_RANGE without the caret kept")
T(v({**good["S-4"], "classes": [{**c4, "unsupported": True}]}) == "INVALID", "S-4: unsupported with a write")
T(v({**good["S-4"], "classes": [{**c4, "range_replace": False, "full_value": False, "read_only": True, "caret_kept": False, "rollback_verified": False}]}) == "CONFIRMED", "S-4: a read-only class is a result, not a failure")
T(v({**good["S-4"], "classes": [{**c4, "read_only": True}]}) == "INVALID", "S-4: read only with a successful write")
T(v({**good["S-5"], "key_reached_application": True}) == "REFUTED", "S-5: the application also got the key")
T(v({**good["S-6"], "layouts": ["U.S."]}) == "INCOMPLETE", "S-6: Russian - PC is required")
T(v({**good["S-7"], "max_units_delivered_whole": 12}) == "REFUTED", "S-7: chunks of 20 do not hold")
T(v({**good["S-7"], "tag_seen_by_tap": False}) == "REFUTED", "S-7: tag invisible")
T(v("x") == "INVALID" and v({"spike": "S-9"}) == "INVALID", "garbage")
print(f"OK ({N} spike validator checks, synthetic data only)")
