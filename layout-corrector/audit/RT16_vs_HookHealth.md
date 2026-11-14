# RT-16-VS-HOOKHEALTH: requirement against implementation, and the ways to close it

Status: **open, undecided.** No normative constant and no text of the specification was changed for this note. `lfengine.py` and
`conformance.py` are unchanged (mutation run r13 stays bound to their SHA). Every figure is labelled with how it was obtained:

* **GUARANTEE** = follows from the strict comparison in `HookHealth.check` under the assumptions of section 2, and was also checked
  exhaustively over every integer timer phase with the real class (`spikes/rt16_bounds.py`, `spikes/test_rt16_bounds.py`, 75 checks).
* **SAMPLE** = a maximum seen on generated random streams (`spikes/rt16_options.py`). A sample maximum is not a bound.
* **MEASURED** = taken on a real operating system. Nothing in this note is of that kind.

## 1. What the three places say

| Place | Text | Reading |
|---|---|---|
| RT-16 | "A hook deliberately made slower than `LowLevelHooksTimeout` ... MUST be detected within 300 ms and answered as in row 13" | a bound on the DETECTION time. The start of the clock is not named |
| 13.5 row 13 | "an event without its counterpart within 300 ms is a loss" | a bound on the MATCHING window: the counterpart may arrive up to 300 ms later and still counts |
| `HookHealth` (`CANARY_MS = 300`) | `check(now)` declares the loss when `now - ts > CANARY_MS` (strict), at a timer tick or at the next event of the same side | implements row 13 literally |

One number (300 ms) is used for two things. The strict comparison is pinned in both directions (`rt16_bounds.boundary`): an event of
age W is healthy, an event of age W + 1 is lost.

## 2. The guarantee, with its assumptions

Let W = `CANARY_MS`. A1: both sources use one monotonic integer-millisecond clock. A2: the runtime timer calls `check` with a gap of at
most P ms between consecutive calls, and the call that decides is delayed by at most L ms (scheduler delay). A3: the observer saw
the first key the hook did not report at time 0 (the observer's own latency is not counted). No further key arrives (a later event can only
declare the loss earlier). D = the time of the first `check` that finds the loss.

**GUARANTEE: W + 1 <= D <= W + P + L, and both ends are reached** (every phase 0..P-1 and L in {0, 10, 50, 150} were enumerated
for W in {300, 250, 200, 150} and P in {100, 50, 10, 1}; the largest D equals W + P + L in every case).

Consequences, each exact and not sampled:

* With the current W = 300, D is at least 301 ms for every timer and every phase, so a strict "within 300 ms from the first lost key" can never be met.
* With a 100 ms tick (the stated maximum of `Runtime.on_tick`), D ranges over 301..400 ms, not "301 to 399". (An earlier version of this note said 399 and
  "201 to 294 ms, 6 ms to spare" for W = 200: those were sample maxima and were wrong as bounds. The exact worst case for W = 200, P = 100 is
  **300 ms with an ideal timer and no margin at all**, 301 ms with 1 ms of scheduler delay.)
* To meet 300 ms with a margin m you need W + P + L <= 300 - m.

| W | P (max gap) | L | D range (GUARANTEE) | meets "<= 300" | margin |
|---|---|---|---|---|---|
| 300 (now) | 100 | 0 | 301 .. 400 | no | -100 |
| 300 | 10 | 0 | 301 .. 310 | no | -10 |
| 290 | 10 | 0 | 291 .. 300 | exactly | 0 |
| 250 | 50 | 0 | 251 .. 300 | exactly | 0 |
| 200 | 100 | 0 | 201 .. 300 | exactly | 0 |
| 200 | 100 | 10 | 211 .. 310 | no | -10 |
| 200 | 50 | 10 | 211 .. 260 | yes | 40 |
| 150 | 100 | 50 | 201 .. 300 | exactly | 0 |

The full grid is printed by `python3 spikes/rt16_bounds.py`. A SAMPLE of 300 random streams (`spikes/rt16_options.py`) gave smaller
maxima for the same settings (for example 294 for W = 200, P = 100); that only shows that random phases rarely hit the worst one.

## 3. What is NOT established

* A2 is an assumption about the platform timer, not a fact. Whether a runtime timer with a gap of at most 100 ms (or 10 ms) and a small L
  is available, also under CPU load, is a **MEASURED** quantity (S-1 at the three load levels). A coarse system timer resolution on Windows (commonly
  cited as about 15.6 ms by default) was not checked here; it would make P = 10 unavailable without raising the resolution.
* A3 and the clock A1: the latency of the Raw Input observer and the skew between the two sources are not in D above.
* The skew between the observer and the hook for the SAME key under load is the quantity that decides whether a smaller W makes false losses.
  Not available until S-1 has run.

## 4. Cost of a smaller window: false loss

A smaller W turns a late counterpart into a loss, and a loss means MANUAL_ONLY until 3 matched pairs after the hook is installed again
(row 13). W must exceed the largest normal observer-to-hook skew for the same physical key (plus margin); the rule for the decision is the
99.99th percentile of the S-1 skew distribution under load. Also, a hook that answers later than the Windows default `LowLevelHooksTimeout`
(300 ms) is removed by the system anyway, while a W below it declares a loss on a hook that the system still keeps: that is the reason the
current value is 300.

## 5. Options (nothing applied)

| Option | Change | Touches |
|---|---|---|
| A. Restate RT-16 | "detected within the matching window plus one timer period and its delay (W + P + L, at most 400 ms with W = 300, P = 100, L = 0)"; name the clock start: the first physical key without a counterpart | specification text only (RT-16, S-1 rule in 13.7, the `HookHealth` glossary line); the S-1 validator limit changes in the same commit |
| B. Smaller window, margin required | choose W, P, L from section 2 so that W + P + L <= 300 - m, for example W = 200, P = 50, L <= 50 | `lfengine.py`, `conformance.py` (literals 300 and 350 in the canary tests), row 13, runtime timer period; a NEW FULL mutation run (r13 does not carry over) |
| C. Faster timer only | P = 10 with W = 300 | cannot meet 300 (D >= 301); text only |
| D. Clock start moved to the OS removal | "within 300 ms after the OS removed the hook" | needs an observable removal instant (the hook thread ends: `hook_removed_by_os` is recorded by the S-1 program); text and S-1 program |

Recommendation (not applied): if S-1 shows a normal observer-to-hook skew well below W for every load level and a runtime timer with small P and
L is available, option B with an explicit margin; otherwise option A. The numbers must come from the device.
