# Requirements matrix of the implementation (state of 2026-11-13)

Evidence words (16.1 of the specification): `REFERENCE_VERIFIED` = the algorithm is checked in `reference/` (conformance, vectors, L7, L9 runner); `SIM_TESTED` = the portable runtime `app/lfruntime.py` is checked against the simulated field (`app/test_runtime.py`, a test double, not an application); `NOT_STARTED`; `BLOCKED` = needs a real operating system or device that this session does not have. Nothing here is `INTEGRATION_VERIFIED` or `RELEASE_GATE_PASSED`. A row says what was run, not that the product works.

Environment of this session: a Linux container without macOS, Windows, a display, a keyboard hook, Accessibility or UI Automation, Xcode, a Windows SDK or a Swift/C# toolchain. No OS adapter can be compiled or executed here. That is the reason for every `BLOCKED` below; it is not a design decision.

## Layers

| Layer | State | Evidence |
|---|---|---|
| Engine, scorer, guards, undo, toggle, transaction (`reference/lfengine.py`) | done as reference | `REFERENCE_VERIFIED` (conformance 1,863,620 checks, `-O` identical, vectors, test_ref, L7 4/4 identical; mutation run r13 on the final code and tests: 950 KILLED + 1 TIMEOUT of 991, 40 SURVIVED, 0 GAP, see `audit/L3/`; bound to the SHA of `lfengine.py` and `conformance.py`) |
| Portable runtime (`app/lfruntime.py`): gate -> HookHealth, gap -> mode, incident -> quarantine, hotkeys, per-application state | written | `SIM_TESTED` (59 checks, python and `-O`; U-2 closed) |
| Windows adapter (hook, Raw Input, UI Automation, `SendInput`, `RegisterHotKey`) | `NOT_STARTED` | `BLOCKED` (no Windows) |
| macOS adapter (`CGEventTap`, Accessibility, hotkey) | `NOT_STARTED` | `BLOCKED` (no macOS) |
| Models and calibration on real data (R-CAL, R-ACC) | `NOT_STARTED` | `BLOCKED` (no corpora and no acceptance data in this repository) |
| Latency and calibration on the two devices (RT-1, section 7.5) | `NOT_STARTED` | `BLOCKED` (needs the devices) |
| Support matrix of real applications (13.8, RT-13) | `NOT_STARTED` | `BLOCKED` (needs the OS and 15 applications) |

## Spikes S-1 to S-7 (13.7): each needs a real OS, none was run

For all seven the JSON result format and the decision rule (CONFIRMED / REFUTED / INCOMPLETE / INVALID, synthetic data never evidence) are in `spikes/spikes.py` and tested by `spikes/test_spikes.py`. The measuring programs are written (compiled, never run on their OS) and no spike was run: every row stays `BLOCKED`.

| Spike | Question | State |
|---|---|---|
| S-1 | RT-16: does the hook lose or invent key events against the independent Raw Input observer, compared by signature, in 1,000,000 physical events? Slowed hook detected within 300 ms? | `BLOCKED`. Measuring program written (`spikes/windows/s1_s3_capture.py s1`), NOT run on Windows; logic tested only with generated streams / fake controls (`spikes/test_capture.py, test_streams.py`). The real measurement is `BLOCKED` (needs Windows: 1,000,000 physical key events from a physical generator, as RT-16 requires; the slow-hook detection time comes from the product's observer, which does not exist yet, so the program leaves it null). Slow-hook timing: `spikes/slowhook.py` replays recorded streams through the real `HookHealth` (`windows/s1_s3_capture.py s1slow`, compiled only, `test_slowhook.py` generated streams). See RT-16-VS-HOOKHEALTH. |
| S-2 | Does `GetKeyboardLayout` for another process's thread work and does `ToUnicodeEx` accept that HKL? If not the pair stays OFF | `BLOCKED`. Measuring program written (`spikes/windows/s2_layout_fingerprint.py`), NOT run on Windows; logic tested only with a fake binding (`spikes/test_measure.py`). The real measurement is `BLOCKED` (needs Windows). |
| S-3 | The hotkey conflict rule; is input of an elevated window delivered to a non-elevated hook? Key auto-repeat agreement of the two sources | `BLOCKED`. Measuring program written (`spikes/windows/s1_s3_capture.py s3`), NOT run on Windows; logic tested only with generated streams / fake controls (`spikes/test_capture.py`). The real measurement is `BLOCKED` (needs Windows, an elevated window and a physical generator). |
| S-4 | Write results by control class across processes (the five tests per class) | `BLOCKED`. Measuring program written (`spikes/windows/s4_edit_control.py + control_probe.py + merge_s4.py`), NOT run on Windows; logic tested only with generated streams / fake controls (`spikes/test_probe.py`). The real measurement is `BLOCKED` (needs Windows, the applications of the support matrix; bindings written: classic Edit/RichEdit, UI Automation (`windows/s4_uia_control.py`) and macOS AX (`macos/s4_ax_control.py`) over `backend_control.py`; logic tested with fake backends (`test_bindings.py`), the UIA and AX backends are compiled only, never imported or run). |
| S-5 | Does the hotkey API withhold the key from the application? Registration, conflict and release per release version | `BLOCKED`. Measuring program written (`spikes/windows/s5_hotkey.py`), NOT run on Windows; logic tested only with a fake binding (`spikes/test_measure.py`). The real measurement is `BLOCKED` (needs Windows). |
| S-6 | Key codes independent of the input source (Russian - PC); the macOS call that builds the layout fingerprint | `BLOCKED`. Measuring program written (`spikes/macos/s6_keycodes_and_fingerprint.py`), NOT run on macOS; logic tested only with a fake binding (`spikes/test_measure.py`). The real measurement is `BLOCKED` (needs macOS). |
| S-7 | The engineering limit of 20 UTF-16 code units per synthetic batch (M2) | `BLOCKED`. Measuring program written (`spikes/macos/s7_tag_and_batch.py`), NOT run on macOS; logic tested only with a fake binding (`spikes/test_measure.py`). The real measurement is `BLOCKED` (needs macOS). |

## Requirements RT-1 to RT-27 (section 13.6): what can be said now

| RT | Short | Reference | Runtime (sim) | OS level |
|---|---|---|---|---|
| RT-1 | Callback under 1 ms p99 | n/a | n/a | `BLOCKED` |
| RT-2 | Nothing stored while the gate is not ALLOW | `REFERENCE_VERIFIED` (engine) | `SIM_TESTED` incl. HookHealth queues (L9 P-2) | `BLOCKED` |
| RT-3 | Guards before the model | `REFERENCE_VERIFIED` | n/a | n/a |
| RT-4 | Every replacement follows the transaction, one outcome | `REFERENCE_VERIFIED` (1,821 faults) | `SIM_TESTED` (incident -> quarantine, exception -> incident) | `BLOCKED` (real frequency of the M2 race is measured on a device) |
| RT-5 | Undo restores the recorded keys | `REFERENCE_VERIFIED` | `SIM_TESTED` (also after further typing: U-1 closed, `ahead_len`, M1 only) | `BLOCKED` |
| RT-6, RT-17 | Nothing persisted or logged; crash handler | `REFERENCE_VERIFIED` for reprs (L9 P-1); the portable store (`app/lfstore.py`, 28 checks) keeps no typed text, no quarantine, no incident counter | `SIM_TESTED` (store) | `NOT_STARTED` (adapter and crash handler) |
| AP-4, AP-5 | Settings and exception list: one versioned file, migration with a backup, unreadable file renamed and replaced by defaults, newer file never written, exception list through a cipher, order kept, view/delete/clear/export, Reset, Delete all data | `TEXT_FIXED` | `SIM_TESTED` (`app/lfstore.py`, `app/test_store.py`, 31 checks; the application list with reasons, the blacklist, the safe re-enable and the Esc opt-in in `app/lfruntime.py`, `app/test_apps.py`, 794 checks; `TestOnlyCipher` is refused for a real store; temporary files, a test cipher that is NOT encryption) | the OS key store (DPAPI, Keychain), the application-data directory, the settings screen (user interface) and the wiring of the Esc key: not written; `BLOCKED` on a device. Two readings of mine for the requester: Reset keeps the exceptions; a newer file is kept untouched and not migrated down |
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
| RT-26 | Hotkey through the manual transaction; undo bounds | `REFERENCE_VERIFIED` | `SIM_TESTED` for selection and toggle; the last-word conversion (U-2, closed in the runtime: the token before the caret is read through the adapter, 45 runtime checks) is `SIM_TESTED` only | `BLOCKED` |
| RT-27 | Toggle only right after a VERIFIED manual conversion | `REFERENCE_VERIFIED` | `SIM_TESTED` | `BLOCKED` |

## Open items found while writing the runtime (not hidden)

* **U-1** (closed in the reference, rev 501) The undo after further typing runs `run_transaction(..., ahead_len=snapshot.after)`: the typed characters are read, never written, only M1. Covered by conformance group U-1 and `test_runtime.py`; the adapter must still show it on a real application.
* **U-2** (closed in the portable runtime, `SIM_TESTED`) `hotkey_convert` with an empty selection reads the last whitespace-delimited token before the caret through `Adapter.read` and converts it with `source="last_word"`. The "last run still in the buffer" shortcut of 13.3 is not used (the field text gives the same word). A real adapter must still pass RT-26 on a device: `BLOCKED`.
* **RT-16-VS-HOOKHEALTH** (open, needs the requester; options, false-loss cost and bounds: `audit/RT16_vs_HookHealth.md`) RT-16 says a slowed hook must be "detected within 300 ms"; `HookHealth` declares a loss only when the oldest unmatched event is older than 300 ms, so detection is always between 300 and about 400 ms after the first lost key (pinned in `spikes/test_slowhook.py`). The S-1 validator keeps the strict 300 ms and would say REFUTED. Either the requirement is restated (for example "300 ms of silence plus one timer tick") or `CANARY_MS` is lowered; that changes `lfengine.py` and needs a new full mutation run. Not decided here.
* The state that the runtime keeps per application (support status, quarantine, incident counter) is memory only. Persistence of the support matrix and the exception list is the adapter's work (13.7).

## Next step that does not need an OS

1. (done) U-1.
2. Write the adapter contract tests as a reusable suite (`SimField` already follows `Adapter`), so that a Windows or macOS adapter can be plugged in and run against the same cases on a device.
3. (format done; programs for S-1 to S-7 written in Python, ctypes and PyObjC, none run) Still to write: the S-4 UI Automation and macOS AX bindings, and the product's own observer that measures the slow-hook detection of S-1. All stay `BLOCKED` until they run on devices.
