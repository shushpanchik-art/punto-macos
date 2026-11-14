#!/usr/bin/env python3
"""Result format and decision rules of the platform spikes S-1 to S-7 (13.7 of the specification).

A spike is run by a person (or a CI runner) on a real operating system with a measurement program that is not part of
this repository yet. The program writes ONE JSON file per spike in the format below. `evaluate` reads such a file and
returns the verdict that the specification allows: a hypothesis of 13.7 changes only by a recorded decision, and a file
that does not name the machine, the OS build and the tool revision proves nothing. A file that says `"synthetic": true`
(test data) is never evidence.

    python3 spikes.py result.json        # prints the verdict, exit code 0 only for CONFIRMED

Verdicts: CONFIRMED (hypothesis holds on this machine), REFUTED (measured, does not hold: the fallback of 13.7 applies),
INCOMPLETE (fields missing or too few measurements), INVALID (not evidence).
Nothing here runs on this repository's CI as a spike: the validator is tested with synthetic files only.
"""
import json
import sys

COMMON = ("spike", "os", "os_build", "machine", "tool_revision", "started_utc", "synthetic")


def _num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _s1(r):                                    # RT-16: the hook against the independent Raw Input observer, one by one by signature
    need = ("events_total", "matched", "lost_by_hook", "extra_in_hook", "hook_removed_by_os", "generator",
            "generator_is_tool_injection", "slow_hook_detect_ms")
    miss = [k for k in need if k not in r]
    if miss:
        return "INCOMPLETE", [f"missing {miss}"]
    if r["generator_is_tool_injection"] is not False or not isinstance(r["generator"], str) or not r["generator"].strip():
        return "INVALID", ["the keystrokes must come from a physical generator that is not the tool's own injection, and it must be named"]
    if r["matched"] + r["lost_by_hook"] != r["events_total"] or min(r["matched"], r["lost_by_hook"], r["extra_in_hook"]) < 0:
        return "INVALID", ["counts do not add up"]
    if r["events_total"] < 1_000_000:
        return "INCOMPLETE", ["fewer than 1,000,000 physical key events (RT-16)"]
    if r["slow_hook_detect_ms"] is None:
        return "INCOMPLETE", ["the deliberately slowed hook was not measured"]
    bad = []
    if r["lost_by_hook"] or r["extra_in_hook"] or r["hook_removed_by_os"]:
        bad.append(f"lost_by_hook={r['lost_by_hook']} extra_in_hook={r['extra_in_hook']} hook_removed_by_os={r['hook_removed_by_os']}")
    if not _num(r["slow_hook_detect_ms"]) or r["slow_hook_detect_ms"] > 300:
        bad.append(f"a slowed hook was detected after {r['slow_hook_detect_ms']} ms, the limit is 300 ms")
    return ("REFUTED", bad) if bad else ("CONFIRMED", ["0 lost, 0 extra, slowed hook detected within 300 ms"])


def _s2(r):                                    # layout identity of another process's thread (Windows)
    need = ("foreign_thread_hkl_ok", "to_unicode_ex_accepts_foreign_hkl", "fingerprints", "layouts_tested")
    miss = [k for k in need if k not in r]
    if miss:
        return "INCOMPLETE", [f"missing {miss}"]
    fps = r["fingerprints"]
    if not isinstance(fps, dict) or len(fps) < 2 or len(fps) != r["layouts_tested"]:
        return "INCOMPLETE", ["fingerprints of at least two layouts, one per tested layout"]
    if len(set(fps.values())) != len(fps):
        return "REFUTED", ["two layouts share a fingerprint: the pair stays OFF"]
    ok = r["foreign_thread_hkl_ok"] and r["to_unicode_ex_accepts_foreign_hkl"]
    return ("CONFIRMED", ["foreign HKL read and accepted"]) if ok else ("REFUTED", ["the pair stays OFF (13.5 row 7)"])


def _s3(r):                                    # hotkey conflicts, elevated windows, auto-repeat agreement
    need = ("elevated_input_reaches_hook", "elevated_events_raw", "elevated_events_hook", "autorepeat_events",
            "autorepeat_mismatches", "conflict_reported_by_os")
    miss = [k for k in need if k not in r]
    if miss:
        return "INCOMPLETE", [f"missing {miss}"]
    if r["elevated_events_raw"] < 100:
        return "INCOMPLETE", ["fewer than 100 key events into an elevated window"]
    if r["autorepeat_events"] < 1_000:
        return "INCOMPLETE", ["fewer than 1,000 auto-repeat events"]
    if r["elevated_input_reaches_hook"] is not (r["elevated_events_hook"] == r["elevated_events_raw"]):
        return "INVALID", ["elevated_input_reaches_hook does not follow from the two counts"]
    bad = []
    if r["autorepeat_mismatches"]:
        bad.append(f"{r['autorepeat_mismatches']} auto-repeat mismatches between the two sources")
    if not r["conflict_reported_by_os"]:
        bad.append("a taken hotkey was not reported")
    if not r["elevated_input_reaches_hook"]:
        bad.append("elevated input is invisible to the hook: such windows are UNKNOWN (13.5)")
    return ("REFUTED", bad) if bad else ("CONFIRMED", ["all three"])


S4_CLASSES = ("full_value", "range_replace", "caret_kept", "read_only", "unsupported")


def _s4(r):                                    # write results by control class (five tests per class)
    rows = r.get("classes")
    if not isinstance(rows, list) or not rows:
        return "INCOMPLETE", ["no control class measured"]
    out = []
    for row in rows:
        miss = [k for k in ("application", "control_class", "trials", *S4_CLASSES) if k not in row]
        if miss:
            return "INCOMPLETE", [f"class row missing {miss}"]
        if row["trials"] < 100:
            return "INCOMPLETE", [f"{row['application']}/{row['control_class']}: fewer than 100 trials"]
        if row["range_replace"] and not (row["caret_kept"] and row.get("rollback_verified")):
            return "INVALID", [f"{row['application']}: REPLACE_RANGE claimed without caret kept and a verified rollback"]
        if row["unsupported"] and (row["full_value"] or row["range_replace"] or row["read_only"]):
            return "INVALID", [f"{row['application']}: unsupported cannot come with any other result"]
        if row["read_only"] and (row["full_value"] or row["range_replace"]):
            return "INVALID", [f"{row['application']}: read only cannot come with a successful write"]
        cap = "REPLACE_RANGE" if row["range_replace"] else ("READ_RANGE" if row["read_only"] else "NONE")
        out.append(f"{row['application']}/{row['control_class']}: {cap}")
    return "CONFIRMED", out                    # the table of capabilities is the result, not a pass/fail


def _s5(r):                                    # does the hotkey API withhold the key from the application?
    need = ("registered", "key_reached_application", "conflict_error", "released_cleanly", "trials")
    miss = [k for k in need if k not in r]
    if miss:
        return "INCOMPLETE", [f"missing {miss}"]
    if r["trials"] < 100:
        return "INCOMPLETE", ["fewer than 100 trials"]
    bad = []
    if not r["registered"]:
        bad.append("registration failed")
    if r["key_reached_application"]:
        bad.append("the application also got the key")
    if not r["conflict_error"]:
        bad.append("a conflicting registration was not an error")
    if not r["released_cleanly"]:
        bad.append("release left the chord taken")
    return ("REFUTED", bad) if bad else ("CONFIRMED", ["registered, withheld, conflict reported, released"])


def _s6(r):                                    # key codes independent of the input source; the call for the layout fingerprint
    need = ("layouts", "keycodes_equal_on_all", "fingerprint_call", "fingerprint_distinct")
    miss = [k for k in need if k not in r]
    if miss:
        return "INCOMPLETE", [f"missing {miss}"]
    if "Russian - PC" not in r["layouts"]:
        return "INCOMPLETE", ["the Russian - PC layout must be among the tested layouts"]
    if r["fingerprint_call"] not in ("UCKeyTranslate", "characters(byApplyingModifiers:)"):
        return "INVALID", ["unknown fingerprint call"]
    if r["keycodes_equal_on_all"] and r["fingerprint_distinct"]:
        return "CONFIRMED", [f"call chosen: {r['fingerprint_call']}"]
    return "REFUTED", ["key codes depend on the input source or the fingerprints collide: no AUTO on that pair"]


def _s7(r):                                    # macOS: does the tap see the tool's own tag? the batch limit of M2
    need = ("tag_seen_by_tap", "own_events", "max_units_per_batch_tested", "max_units_delivered_whole")
    miss = [k for k in need if k not in r]
    if miss:
        return "INCOMPLETE", [f"missing {miss}"]
    if r["own_events"] < 1_000:
        return "INCOMPLETE", ["fewer than 1,000 own events"]
    bad = []
    if not r["tag_seen_by_tap"]:
        bad.append("the tap does not see the tool's tag: own events would be recorded as user keys")
    if r["max_units_delivered_whole"] < 20:
        bad.append(f"batches above {r['max_units_delivered_whole']} units are cut: M2 chunks of 20 do not hold")
    return ("REFUTED", bad) if bad else ("CONFIRMED", ["tag seen; 20-unit chunks delivered whole"])


RULES = {"S-1": _s1, "S-2": _s2, "S-3": _s3, "S-4": _s4, "S-5": _s5, "S-6": _s6, "S-7": _s7}
OS_OF = {"S-1": "windows", "S-2": "windows", "S-3": "windows", "S-4": "windows", "S-5": "both", "S-6": "macos", "S-7": "macos"}


def evaluate(r):
    """Returns (verdict, [reasons])."""
    if not isinstance(r, dict):
        return "INVALID", ["not an object"]
    miss = [k for k in COMMON if k not in r]
    if miss:
        return "INVALID", [f"missing {miss}"]
    if r["synthetic"] is not False:
        return "INVALID", ["synthetic data is not evidence"]
    if r["spike"] not in RULES:
        return "INVALID", [f"unknown spike {r['spike']!r}"]
    want = OS_OF[r["spike"]]
    if want != "both" and r["os"] != want:
        return "INVALID", [f"{r['spike']} is a {want} spike, the file says {r['os']!r}"]
    if r["os"] not in ("windows", "macos"):
        return "INVALID", ["os must be windows or macos"]
    for k in ("os_build", "machine", "tool_revision", "started_utc"):
        if not isinstance(r[k], str) or not r[k].strip():
            return "INVALID", [f"{k} must name the real machine and tool"]
    return RULES[r["spike"]](r)


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 2
    with open(argv[1], encoding="utf-8") as f:
        verdict, reasons = evaluate(json.load(f))
    print(verdict, "; ".join(reasons))
    return 0 if verdict == "CONFIRMED" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
