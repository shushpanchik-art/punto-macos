# AP-7 / RT-19: readings that are NOT agreed (status: OPEN, waiting for the requester)

Nothing below is a decision. The code follows the first option of each item only so that it can be tested; every item can be switched by a small change.
Specification: `spec/TZ_layout_correction_v3.md` (clause texts quoted exactly).

## 1. What is a "crash" that gives MANUAL_ONLY
Clauses:
* Failure row 11 (13.5): "An unhandled exception in the worker | The current word is KEEP; the worker restarts once; a second failure within 60 seconds gives MANUAL_ONLY | A notice after the second failure".
* AP-7: "A supervisor restarts the engine after a crash; two crashes within 60 seconds give MANUAL_ONLY (failure row 11)."

Gap: row 11 counts WORKER failures (inside one process). AP-7 says "engine" and "crash" and points to row 11. The text does not say whether a process crash and a worker failure share one count.

| Option | What it means | Consequence |
| --- | --- | --- |
| A (in the code now) | Two separate 60 s windows: worker failures (in-process, `lflifecycle.Supervisor`) and engine process crashes (`lfsupervisor.ProcessSupervisor`). One of each within 60 s is NOT MANUAL_ONLY | Simple; no channel between engine and supervisor. A worker failure followed by a process crash 10 s later restarts in AUTO although two failures happened inside 60 s |
| B | One shared window counting both kinds | Needs a channel from the engine to the supervisor (exit status, pipe) that carries a worker-failure time, because counters are not persisted (RT-6, AP-5). More code and one more interface to test; matches "(failure row 11)" most literally |
| C | Row 11 is worker-only; AP-7 asks only that the supervisor restarts the engine | No process-crash count at all: a process that crashes at start would be restarted forever unless some limit exists (see 3) |

## 2. How "MANUAL_ONLY" survives a process restart, and who tells the user
* The text gives no mechanism. The code passes `--manual-only` to the restarted engine; the flag lives only in the supervisor's memory (nothing is written to disk, consistent with RT-6 and AP-5 which forbid persisting incident counters).
* Consequence: if the supervisor itself dies, the latch is lost. Alternative: no flag, the engine asks the supervisor through a channel (more code).
* The notice kind `manual_only_after_crashes` is MY name; row 11 says only "A notice after the second failure". It is not in the notice table of 13.5/AP-8 (check and register, or reuse the existing worker notice).

## 3. Extras not in the specification (each one is an added requirement; marked so in the code)
| Extra | Why it exists | Consequence if removed |
| --- | --- | --- |
| Minimum pause of 1 s between starts | Prevents a tight restart loop | Restarts as fast as the OS allows |
| Crash-loop guard: more than 5 crashes in 10 min: supervisor exits with status 70 | Prevents an endless loop with a permanently broken engine | The loop runs forever; or the guard is replaced by C above |
| After "gave up" nothing runs | Consequence of the guard: AP-2 (an icon that always shows a state) cannot be met by a process that is gone | Needs a decision: who shows "Off" after the supervisor gave up |
| Child streams are the null device | RT-6: nothing typed in any log | none (it follows RT-6) |

## 4. Autostart mechanism (clause: platform table, "Autostart | Per-user startup entry | Login item (`SMAppService`, macOS 13+)"; AP-7: "Starts at login (a setting)"; AP-6: "removes ... its login item or startup entry")
* Windows: "per-user startup entry". The code generates the per-user `Run` value. Another valid per-user entry is a shortcut in the Startup folder. The `Run` key behaviour is NOT verified against Microsoft documentation in this repository.
* macOS: the text says "Login item (`SMAppService`)". The literal reading is `SMAppService.mainApp` (the app opens at login, no property list at all). The code generates an agent property list (`SMAppService.agent`, `KeepAlive`, `RunAtLoad`): that is an extension, it adds restarting of the SUPERVISOR itself, which the text does not ask for ("a supervisor restarts the engine", not "something restarts the supervisor").
  * Option mainApp: no plist; the main executable runs `--supervisor`; nothing restarts a dead supervisor.
  * Option agent (code now): plist, launchd restarts the supervisor after a non-zero exit; registration is native (SMAppService), not possible from Python, NOT RUN.
* The "start at login" setting (AP-4) is the switch for either; `start_at_login` exists in the store (default True); registering and unregistering are not written.

## 5. RT-19 (one instance per user session)
Clause: "The tool MUST run as at most one instance per user session. A second start MUST exit at once (a per-session lock held by the first instance), and when the lock cannot be established the engine MUST stay OFF. ... Test: start two copies, type 1,000 words that are converted; there is exactly one replacement per word and no UNRECOVERED outcome."
* Windows backend: named mutex in the `Local\` namespace, which is per session (written, compiled only).
* POSIX backend: a file lock in a per-user directory. That is per USER, not per login session. Divergence from the clause where one user has several sessions at once; option: a per-session directory (for example the per-user temporary directory of the session), which the OS adapter would have to supply.
* The second start exits with status 0 (not an error). The text says "exit at once" only.
* Several supervisors: a second supervisor's engine exits at once with status 0, which the supervisor treats as a clean exit, so it ends too. If the first engine crashes and the second supervisor's restart wins the lock first, the first supervisor's restart ends: one instance remains in either case.
* The 1,000-word test on two real instances is NOT RUN (needs a real OS and a real hook); the portable tests check the lock, the decision and that the engine without the lock converts nothing.

## 6. AP-4 settings (portable part, `app/lfsettings.py`): my readings, not agreed
Clause AP-4: "Automatic correction on or off; hotkey (with the conflict procedure of 13.3); "Esc also undoes" per application; application list with the reason for each entry (blacklist, quarantine) and a re-enable button; exception list (view, delete one entry, clear all, export); start at login; diagnostics opt-in; update channel; reset".
* Automatic correction off = MANUAL_ONLY (reason `auto_off`), never OFF: the clause says nothing about the hotkey; MANUAL_ONLY keeps it.
* Hotkey chords: the defaults and fallback lists are copied from 13.3, where they are "proposed ... to be confirmed by the requester (16.3)": still OPEN. Chord names are ASCII (`Ctrl+Alt+Cmd+Space`); the symbols of the text are not stored. The order tried is: the user's chord, the default, the fallbacks (the text names the fallback list only). A bare key that types or edits (a letter, Space, Esc, ...) is refused as a chord because registering it would swallow typing (RT-11 "MUST NOT reach the application"): this refusal is mine.
* Update channel: the specification names the setting but no values (AP-9 mentions a staged rollout). Only the shape is checked (`[a-z][a-z0-9_-]{0,31}`), no list of channels.
* Start at login: the stored value changes only after the OS adapter's registration succeeded; without an adapter a change is refused. Nothing is registered here.
* Reset keeps the exception list (as in the matrix); "Delete all data" empties settings, exceptions and the store's own files and nothing is written back at shutdown until the user chooses something again.
* Not written (needs the user interface / OS): the screens, the view of the application list, the real hotkey registration, the "which chord is active" notice display, the real start-at-login registration.

## 7. AP-8 notifications (portable part, `app/lfnotify.py`): gaps and my readings, not agreed
Clauses: 13.5 "A notice is shown at most once per cause and per 24 hours, and never takes focus."; AP-8 "Non-blocking, never take focus, rate-limited as in 13.5; each offers one action (open settings, re-enable)"; row 10 "After UNRECOVERED the notice says that the field may differ from what was typed and that the application's own undo is the way back"; rows 8 and 14 "the way to restore the permission" / "names the permission".
* **Priorities: the specification defines none.** Nothing is invented: delivery is first come, first served. If priorities are wanted (for example an UNRECOVERED incident before a settings notice), the requester must say which order.
* "Cause": I use the notice kind, and for incidents also the outcome (restored or unrecovered), so a later UNRECOVERED incident is never hidden by a RESTORED one shown a moment ago. The text could also mean one cause per application; then an incident in another application within 24 h would show again.
* The boundary: two shows exactly 24 h apart are allowed (86,400,000 ms inclusive); closer is refused; a clock that went backwards opens no slot. The text does not say which.
* The 24 h memory lives in the process only. After a restart a notice can show again within 24 h; persisting it would add a stored timestamp (AP-5, RT-6 say nothing about it).
* The action of each kind is mine except where the text implies it: row 10 re-enable, rows 8 and 14 open settings. Rows 9 and 13 use re-enable ("until the user re-enables AUTO"); the others use open settings. AP-8 says "each offers one action": a notice without an action is refused.
* The runtime has one flag `models_ok`, so rows 3 to 6 and 12 cannot be told apart: one kind `models_unavailable`. Row 3's "one-time notice that the basic mode is in use" and row 7's icon text ("layout not supported", an icon, not a notice) are not produced.
* Kinds that are not in the table at all: `manual_only_after_crashes` (AP-7), `instance_lock_unavailable` (RT-19), the settings and store notices (`settings_not_saved`, `autostart_failed`, hotkey, `cipher_unavailable`, `file_unreadable_defaults`, `newer_file_kept`): shown through the same limit. "Re-enabled" (the user's own action) and "migrated" produce no notice.
* No wording: a notice has a text identifier; the words, their translation and the display (non-blocking, no focus) belong to the interface and are NOT RUN. A failing display is retried up to 3 times (my number) and then dropped and counted.
* The notice of an incident carries the opaque identifier of the application for the re-enable action; it is the identifier the user already sees in the application list.

