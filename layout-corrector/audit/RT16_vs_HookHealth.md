# RT-16-VS-HOOKHEALTH: requirement against implementation, and the ways to close it

Status: **open, undecided.** No normative constant and no text of the specification was changed for this note. `lfengine.py` and
`conformance.py` are unchanged (mutation run r13 stays bound to their SHA). The numbers below come from generated streams
(`spikes/rt16_options.py`), not from a device.

## 1. What the three places say

| Place | Text | Reading |
|---|---|---|
| RT-16 | "A hook deliberately made slower than `LowLevelHooksTimeout` ... MUST be detected within 300 ms and answered as in row 13" | a bound on the DETECTION time. The start of the clock is not named |
| 13.5 row 13 | "an event without its counterpart within 300 ms is a loss" | a bound on the MATCHING window: the counterpart may arrive up to 300 ms later and still counts |
| `HookHealth` (`CANARY_MS = 300`) | declares the loss when the oldest unmatched event is OLDER than 300 ms, at a timer tick (at most every 100 ms, `Runtime.on_tick`) or at the next event of the same side | implements row 13 literally |

The two 300 ms are one number used for two things. If the matching window is 300 ms, a loss cannot be known earlier than 300 ms after
the key, so the detection time from the first lost key is always above 300 ms: 301 ms at best, 399 ms at worst with a 100 ms tick
(pinned in `spikes/test_slowhook.py`). The S-1 validator keeps the strict limit of 300 ms and would say REFUTED for any figure from the
current code. RT-16 is not weakened by this note.

## 2. The options (detection time = from the first key the hook did not report to the declaration)

| Option | Change | Detection time (generated streams) | Meets "within 300 ms" from the first lost key | Touches |
|---|---|---|---|---|
| A. Restate RT-16 | "detected within the matching window plus one timer tick (at most 400 ms)"; clock start named: the first physical key without a counterpart | 301 to 399 ms | by redefinition, not by a faster detection | specification text only (RT-16, S-1 rule in 13.7, the glossary line of `HookHealth`) |
| B. Smaller window | `CANARY_MS` 200 and row 13 "within 200 ms", tick stays 100 ms | 201 to 294 ms | yes, with 6 ms to spare at the worst phase | `lfengine.py`, `conformance.py` (literals 300 and 350 in the canary tests), row 13, new FULL mutation run |
| B'. Window 290, tick 10 ms | `CANARY_MS` 290, runtime timer 10 ms | 291 to 300 ms | yes, with no margin (a scheduling delay breaks it) | as B, plus the runtime timer rate |
| C. Faster timer only | tick 10 ms, `CANARY_MS` 300 | 301 to 310 ms | no, never within 300 | runtime and text only |
| D. Window kept, bound moved to the OS removal | "detected within 300 ms after the OS removed the hook", clock start = the removal | needs a way to observe the removal time (the hook thread ends: `hook_removed_by_os` is already recorded) | by redefinition; measurable only if the removal instant is observable | specification text, S-1 program |

## 3. Cost of a smaller window (B, B'): false loss

A smaller window turns a late counterpart into a loss, and a loss means MANUAL_ONLY until 3 matched pairs after the hook is
installed again (row 13). The window must therefore exceed the largest normal skew between the Raw Input observer and the hook for the
SAME physical key. That skew is a quantity this repository does not have: it is the distribution measured by S-1 on a real machine,
also under CPU load (the three load levels of the end-to-end suite). Rule for the decision: the window has to be above the observed
skew at the 99.99th percentile plus a margin. Until S-1 has run, a smaller window cannot be shown safe, and the loss of a window of
300 ms against the Windows default `LowLevelHooksTimeout` of 300 ms is the reason the current value was chosen: a hook that answers
later than 300 ms is removed by the system anyway. A window below the OS timeout declares a loss on a hook that the system still keeps.

Timer bounds: the runtime timer is "at most every 100 ms"; the worst detection is `window + tick`. A tick below 10 ms costs CPU
for no gain, and a tick that is late (a busy worker) adds its lateness; B' has no room for that.

## 4. What each option does to the evidence

* A: no code, no new mutation run; the S-1 validator limit changes to the restated figure in the same commit.
* B, B': `lfengine.py` and `conformance.py` change, so the full 991-mutant run and the classification of the survivors must be
  repeated; r13 does not carry over (its SHAs name the old files). The vectors and the L7 blocks change too.
* C: runtime and text only.
* D: needs a measurable removal instant on Windows (not available here).

## 5. What I recommend and why it is not applied

If the S-1 skew data show a normal skew well below 150 ms: B (200 ms) meets the text as written. If they do not: A, with the clock
start named. Applying either now would be a guess about a number the device must supply, and the requester has not decided.
Reproduce the table: `python3 spikes/rt16_options.py`.
