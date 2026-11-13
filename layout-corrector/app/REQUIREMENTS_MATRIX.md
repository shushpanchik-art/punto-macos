# Requirements matrix of the implementation (state of 2026-11-13)

Evidence words (16.1 of the specification): `REFERENCE_VERIFIED` = the algorithm is checked in `reference/` (conformance, vectors, L7, L9 runner); `SIM_TESTED` = the portable runtime `app/lfruntime.py` is checked against the simulated field (`app/test_runtime.py`, a test double, not an application); `NOT_STARTED`; `BLOCKED` = needs a real operating system or device that this session does not have. Nothing here is `INTEGRATION_VERIFIED` or `RELEASE_GATE_PASSED`. A row says what was run, not that the product works.

Environment of this session: a Linux container without macOS, Windows, a display, a keyboard hook, Accessibility or UI Automation, Xcode, a Windows SDK or a Swift/C# toolchain. No OS adapter can be compiled or executed here. That is the reason for every `BLOCKED` below; it is not a design decision.

## Layers

| Layer | State | Evidence |
|---|---|---|
| Engine, scorer, guards, undo, toggle, transaction (`reference/lfengine.py`) | done as reference | `REFERENCE_VERIFIED` (conformance 1,863,506 checks, `-O` identical, vectors, test_ref, L7 4/4 identical; mutation run r11 in progress, see `audit/L3/`) |
| Portable runtime (`app/lfruntime.py`): gate -> HookHealth, gap -> mode, incident -> quarantine, hotkeys, per-application state | written | `SIM_TESTED` (34 checks, python and `-O`) |
| Windows adapter (hook, Raw Input, UI Automation, `SendInput`, `RegisterHotKey`) | `NOT_STARTED` | `BLOCKED` (no Windows) |
| macOS adapter (`CGEventTap`, Accessibility, hotkey) | `NOT_STARTED` | `BLOCKED` (no macOS) |
| Models and calibration on real data (R-CAL, R-ACC) | `NOT_STARTED` | `BLOCKED` (no corpora and no acceptance data in this repository) |
| Latency and calibration on the two devices (RT-1, section 7.5) | `NOT_STARTED` | `BLOCKED` (needs the devices) |
| Support matrix of real applications (13.8, RT-13) | `NOT_STARTED` | `BLOCKED` (needs the OS and 15 applications) |

## Spikes S-1 to S-7 (13.7): each needs a real OS, none was run

| Spike | Question | State |
|---|---|---|
| S-1 | Is Raw Input the primary event source or only the canary (Windows)? | `BLOCKED`, harness not written |
| S-2 | Does `GetKeyboardLayout` for another process's thread work and does `ToUnicodeEx` accept that HKL? If not the pair stays OFF | `BLOCKED` |
| S-3 | The hotkey conflict rule; is input of an elevated window delivered to a non-elevated hook? Key auto-repeat agreement of the two sources | `BLOCKED` |
| S-4 | Write results by control class across processes (the five tests per class) | `BLOCKED` |
| S-5 | Does the hotkey API withhold the key from the application? Registration, conflict and release per release version | `BLOCKED` |
| S-6 | Key codes independent of the input source (Russian - PC); the macOS call that builds the layout fingerprint | `BLOCKED` |
| S-7 | The engineering limit of 20 UTF-16 code units per synthetic batch (M2) | `BLOCKED` |

## Requirements RT-1 to RT-27 (section 13.6): what can be said now

| RT | Short | Reference | Runtime (sim) | OS level |
|---|---|---|---|---|
| RT-1 | Callback under 1 ms p99 | n/a | n/a | `BLOCKED` |
| RT-2 | Nothing stored while the gate is not ALLOW | `REFERENCE_VERIFIED` (engine) | `SIM_TESTED` incl. HookHealth queues (L9 P-2) | `BLOCKED` |
| RT-3 | Guards before the model | `REFERENCE_VERIFIED` | n/a | n/a |
| RT-4 | Every replacement follows the transaction, one outcome | `REFERENCE_VERIFIED` (1,821 faults) | `SIM_TESTED` (incident -> quarantine, exception -> incident) | `BLOCKED` (real frequency of the M2 race is measured on a device) |
| RT-5 | Undo restores the recorded keys | `REFERENCE_VERIFIED` | `SIM_TESTED` only when no key followed the replacement; **U-1 open**: the write path after further typing is not specified | `BLOCKED` |
| RT-6, RT-17 | Nothing persisted or logged; crash handler | `REFERENCE_VERIFIED` for reprs (L9 P-1) | n/a | `NOT_STARTED` (adapter and crash handler) |
| RT-7 | An error before step 4 changes nothing | `REFERENCE_VERIFIED` | `SIM_TESTED` (adapter exception = incident, no crash) | `BLOCKED` |
| RT-8 | The hook never delays or drops a key | `REFERENCE_VERIFIED` (invariant I1) | `SIM_TESTED` (runtime has no path that holds a key) | `BLOCKED` (RT-16 measurement) |
| RT-9 | Gate defaults to deny | `REFERENCE_VERIFIED` | `SIM_TESTED` (focus -> UNKNOWN) | `BLOCKED` |
| RT-10, RT-11 | Synthetic tag; hotkey registration | n/a | n/a | `BLOCKED` |
| RT-12 | Failure table of 13.5 (14 rows) | `REFERENCE_VERIFIED` for the engine rows | `SIM_TESTED` for rows 10 and 13; the other rows need the adapter | `BLOCKED` |
| RT-13 | Support matrix shipped | n/a | `SIM_TESTED` status -> mode only | `BLOCKED` |
| RT-14 | Layout change drops the word | `REFERENCE_VERIFIED` | n/a | `BLOCKED` |
| RT-15 | Layout identified by fingerprint | `REFERENCE_VERIFIED` (pure function) | n/a | `BLOCKED` (the OS call, S-2 and S-6) |
| RT-16 | 1,000,000 real key events, 0 lost, 0 extra | model only | n/a | `BLOCKED` |
| RT-18 | Mode = `engine_mode` | `REFERENCE_VERIFIED` | `SIM_TESTED` (`Runtime._mode` is that function) | n/a |
| RT-19 | One instance per session | n/a | n/a | `NOT_STARTED` |
| RT-20 | Sleep, lock, fast user switching, secure desktop | engine part `REFERENCE_VERIFIED` | `SIM_TESTED` for focus change only; lock and sleep events are the adapter's | `BLOCKED` |
| RT-21 | Remote desktop, VM, terminal window | n/a | n/a | `BLOCKED` |
| RT-22 | Adapter bound to the classified element | `REFERENCE_VERIFIED` (L9 F4) | `SIM_TESTED` (runtime passes `element()`) | `BLOCKED` |
| RT-23, RT-24, RT-25 | White-space neighbour; M2 only with no counted input; engine follows outcome | `REFERENCE_VERIFIED` | `SIM_TESTED` | `BLOCKED` |
| RT-26 | Hotkey through the manual transaction; undo bounds | `REFERENCE_VERIFIED` | `SIM_TESTED` for selection and toggle; **U-2 open**: the last-word conversion needs the word before the caret from the adapter and is not in the runtime | `BLOCKED` |
| RT-27 | Toggle only right after a VERIFIED manual conversion | `REFERENCE_VERIFIED` | `SIM_TESTED` | `BLOCKED` |

## Open items found while writing the runtime (not hidden)

* **U-1** The undo write path after the user typed further characters is not specified in 13.3 or 20.14. The runtime refuses it (`undo_unavailable`) rather than guess. The specification needs a rule (for example, the fragment is the word, the Space and the characters typed since, read back and rolled back as one) before an adapter can implement it.
* **U-2** The `last_word` manual source exists in `run_manual_transaction` but nothing supplies the word before the caret; the adapter has to.
* The state that the runtime keeps per application (support status, quarantine, incident counter) is memory only. Persistence of the support matrix and the exception list is the adapter's work (13.7).

## Next step that does not need an OS

1. Specify U-1 (13.3, 20.14) and cover it in conformance, then lift the refusal in the runtime.
2. Write the adapter contract tests as a reusable suite (`SimField` already follows `Adapter`), so that a Windows or macOS adapter can be plugged in and run against the same cases on a device.
3. Write the spike harnesses S-1 to S-7 as scripts with their measurement format, so that a person with the devices only has to run them. They stay `BLOCKED` until they run.
