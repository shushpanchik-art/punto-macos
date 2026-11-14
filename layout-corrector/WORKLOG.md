# NOTES (survives compaction) - updated 2026-10-24
- Doc project d0559940-cfe9-4955-8f32-f42924e2cdd5, body node 8b22a85e-ac20, rev 41 at start of this phase (unchanged by me so far).
- Oracle code: scratchpad/ref/lfengine.py (normative section 20 source; has candidate(), shape_guard(), score(), decide(), Engine event machine, ev1_bound, WittenBell, LFW1). test_ref.py passes (property tests).
- Doc dumps (rev 41): scratchpad/md1.md, md2.md (markdown). Experiments exp/*.py (no ckpt/results anymore).
- Audit: 20 points P0..P2 (see conversation). Plan: P0 first (1.1 nats, 1.2 hook/replay, 1.3 stage0 gate, 1.4 priors), then P1, P2, section 20.
## Progress
- [design decisions, 2026-10-24] v1: observe-only hook (never swallow/delay/replay user keys); decision point = Space ONLY (Enter/Tab = context breaks: key already delivered); tool never switches OS layout in v1;
  one candidate per word (target = other layout); mid-word layout change => word dropped; Stage 0 context gate ALLOW/DENY/UNKNOWN (default-deny, unknown app => no buffering; fresh gate query at word start before any classification);
  replacement = range-based AX / atomic SendInput + echo verification, typed-ahead handling, abort->KEEP, 1 rollback attempt, app quarantine after incident; synthetic tagging per OS;
  thresholds: lambda in nats (6.907/5.806/5.293) = logit(t); priors: full vectors, o_lat=0.25 (OTHER share of Latin-script words), w default .01/after_switch .003/run .25, run credit 3 refilled only by non-run converts (cap);
  adaptive thresholds DEFERRED (not v1); hotkey = OS hotkey API (swallows), toggle convert/undo, Esc not default; Linux not in v1; manual_convert = pure key mapping, direction by letter majority;
  EV-1: pass iff n>=1e5, users>=20, docs>=100, point<=4.8e-5, cluster bound (poisson_upper(#clusters)*max cluster size/n)<=1e-4; DT-5 lemma-disjoint only for synthetic sets; real sets R-CAL/R-ACC user-disjoint (hash of user id).
- Doc plan: 13.1 gate, 13.2 event flow, 13.5 failure table, new 13.7 platforms, 13.8 support matrix, 13.9 app layer; 5.3 segmentation; 10.1-10.3,10.6; 8.4/8.5; 11.2/11.3; new 7.8 baseline spec? ; section 20 = code+vectors; 4.4 normative statement.

## 2026-10-25 14:30 local (cycle N: the audit message is re-sent after each session-limit/compaction; do NOT redo verified work)
- Doc at rev 64+ (read: mcp__Claude_Docs__read ref node 8b22a85e-ac20 engine prose payload {kind:view,sinceRev:N}); P0 1.1-1.4, segmentation (5.3), platforms (13.7-13.9) ALREADY IN DOC (verified rev 63).
- Done in rev 64+: 8.4-8.5 rewritten (R-CAL, R-ACC, R-NAT user-disjoint sets), DT-5 find-replace, block .21263 replaced, insert after .15021 (details: check doc).
- TODO order: (a) EV-1 cluster-bound formula in 11.2/11.3 + EV-4/EV-5 status, (b) 7.7 baseline spec (Witten-Bell algorithm, table format, calibration, vectors), (c) 13.5 failure table, (d) section 20 (oracle code + golden vectors from ref/gen_vectors.py), (e) P2: adaptive thr marked deferred, dictionary priority matrix, hotkeys, evidence labels (18.1/18.6), corpora manifest, normative status 4.4, '5 parametric layers' wording (sec 2 & 7.1), (f) final consistency grep + report to user in Russian.
- Task list ids: #7 oracle, #8 verify audit, #9 P0, #10 P1, #11 P2, #12 final.
- rev70: sec 11 done (EV table->R-ACC, 11.3 cluster rule+freeze EV-4/5, 11.5 R-NAT, 11.6, new 11.7 evidence table). NEXT: 7.7 baseline, sec 20, 13.5/16.x check, P2 greps

## 2026-10-25 (cycle N+1, after compaction) — state verified at rev 75
- Doc outline at rev 75 shows DONE: 4.4 normative statement, 5.3 segmentation, 7.7 baseline spec (rev71-73), 8.4/8.5/8.9, 10.2-10.4, 10.6 deferred, 11.x EV-1 cluster rule + 11.7 evidence table, 13.1-13.9 (gate, event flow, failure table 13.5, platforms 13.7, support matrix 13.8, app layer 13.9), section 20.1..20.5 (code: key tables, word seg, shape guards, calibration).
- REMAINING: sec 20.6+ (decision policy / engine event machine / baseline Witten-Bell / LFW1 forward / vectors), final consistency grep, report. Full doc dump: tool-results/mcp-Claude_Docs-read-1792966296766.txt (rev75, JSON; d[1]['text'] has the xml).

## 2026-10-26 05:55 UTC (cycle N+2) — doc is at rev 87; READ THE DOC BEFORE ASSUMING ANYTHING
- Doc already has 20.1..20.11 (published by an earlier cycle at revs 76-83), MD-14 (LFW1 export requirement), 13.2/13.3 cool-down wording fixed by me at rev 85-87 (cool-down ends when 3 word decisions suppressed AND 10 s passed).
- I (cycle N+2) am NOW writing: 20.6 docstring fix (rows 5-12 numbering), 20.7 bullet wording, then NEW 20.12 (vectors.py + expected JSON, from ref/vectors.py -> ref/vectors_out.json) and 20.13 (conformance tests). Do not duplicate; re-read outline first.
- GitHub: branch claude/layout-corrector-spec pushed to shushpanchik-art/punto-macos (folder layout-corrector/). Sync with scratchpad/sync_to_github.sh "msg" (script copies ref/*.py + exp/*.py + NOTES). User wants regular pushes. Spec md snapshot must be re-exported via mcp__Claude_Docs__export (file cb60d609-59c2, markdown) and written to layout-corrector/spec/TZ_layout_correction_v3.md.
- gen_vectors.py was turned into vectors.py (JSON to stdout, deterministic across PYTHONHASHSEED).

## GITHUB SYNC (user request 2026-10-25: push everything regularly)
- Repo clone: /home/claude/repos/punto-macos, branch claude/layout-corrector-spec (pushed OK 2026-10-26, commit a5706d3). Folder layout-corrector/{spec,reference,experiments,inputs,WORKLOG.md,README.md}.
- To sync: re-export doc (mcp__Claude_Docs__export markdown file cb60d609-59c2; result JSON has data.bytes_b64) -> layout-corrector/spec/TZ_layout_correction_v3.md; cp scratchpad/ref/*.py,json,txt -> reference/; cp NOTES.md -> WORKLOG.md; git add/commit (trailer Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com> + Claude-Session: https://claude.ai/code/session_01VktqVyYdVPCnccLFDAY3Yk); git push. Do this after every major milestone.
- Doc 20.2-20.5 published and match lfengine.py parts (block 0 header docstring is the module preamble). REMAINING doc work: publish 20.6..20.11 code blocks + 20.12 vectors, final consistency, report in Russian.

## 2026-10-26 07:55-  (cycle N+2) IMPORTANT
- Doc is at rev ~92+: sections 20.6-20.12 ALREADY PUBLISHED in revs 76-91 (by an earlier cycle; notes were stale). I accidentally inserted a duplicate 20.6 at rev 92 and deleted it (rev 93). Cool-down wording (13.3) and MD-14 also already fixed.
- Do NOT republish 20.6-20.12. TODO: (1) verify doc code blocks == ref/lfengine.py parts (assemble from doc export, run vectors.py, diff with expected JSON in doc); (2) 20.13 conformance (conformance.py written+passes in ref/) - 7.7 refers to "conformance tests of 20.13"; (3) sync to GitHub (repo clone /home/claude/repos/punto-macos); (4) final consistency greps; (5) report to user in Russian (what audit remarks confirmed/partly/not; what remains open).
- ALWAYS re-read via sinceRev:<last rev> BEFORE any write; changed-block dump parse: python3 -I xml2md.py file.xml
- 2026-10-26 18:07 (cycle N+3): CORRECTION - lines appended by me at 18:0x were from a STALE context (rev 75). Truth: see the 05:55/07:55 entries above (doc already has 20.6-20.12). User also asked (2026-10-26) to DELEGATE SIMPLE TASKS to agents (Agent tool; qwen-coder unavailable in cloud). Pushed a5706d3 earlier contains OLD snapshot (rev 75 spec, gen_vectors.py) -> must re-sync (sync_to_github.sh).
- 2026-10-26 18:10: exported spec rev 102 -> scratchpad/spec_rev102.md (also repo spec/). Doc has 20.1-20.13. Next: delegate verification (code-vs-doc) and consistency greps to agents, then sync_to_github.sh.
- 2026-10-27 00:10 (cycle N+4): user: "поручай простые задачи агентам". GitHub linked, push works (branch pushed; remote HEAD a5706d3 = OLD snapshot, must re-sync). verify/rev102: out.json == spec_expected.json (vectors in doc match code, seed-stable). Spawning haiku agents for (a) consistency greps over spec_rev102.md, (b) assembled-code-from-doc vs ref/lfengine.py check. Then sync_to_github.sh, then final Russian report.

## 2026-10-29 00:30 (cycle N+5) — TRUE STATE
- GitHub: remote branch claude/layout-corrector-spec HEAD 36fedf3 (code+conformance synced 10-28 19:15; spec snapshot 0a56e8d from 10-28 01:08 may be stale vs doc). Push works. Repo clone /home/claude/repos/punto-macos. sync_to_github.sh exists (code only; spec must be re-exported with mcp__Claude_Docs__export).
- verify/ + agentA/agentB dirs hold earlier checks (code-from-doc == lfengine.py; vectors in doc == code output; seed-stable). scan.py = regex scan over spec md.
- User msg 10-29: "поручай простые задачи агентам" -> use Agent tool (haiku/sonnet) for mechanical checks, give precise briefs.
- NEXT: (1) read doc sinceRev:102 to get current rev; (2) agents: consistency greps + code-vs-doc; (3) re-export spec + sync; (4) FINAL REPORT in Russian (audit remarks: confirmed/partly/not; what's open). Then mark tasks 7-12 complete.

## 2026-10-29 (cycle N+5) — DONE
- Agents (haiku) ran: consistency scan (3 CERTAIN + 7 MAYBE leftovers), xref/ID/table check (clean), code-from-doc conformance (PASS, vectors == expected, seed-stable, repo copy identical modulo blank lines).
- I fixed all 10 leftovers in the doc (rev 103-117): 14.1 mid-word row, 14.1/4.1 XKB->Linux deferred, 14.3/14.5 personal vocabulary/threshold shift, 14.4 input frameworks, 1/5.5/10.5/10.7 nats notes, 2 stage-0 gate, 17.3 Esc opt-in.
- Spec snapshot rev 117 pushed: commit dd3173a on origin/claude/layout-corrector-spec (shushpanchik-art/punto-macos). Tasks 1-12 completed. Final Russian report sent to user.
- OPEN (honest): real-data calibration/acceptance (R-CAL/R-ACC) not run; latency on M1 Max / Windows not measured; OS adapters not implemented (spec + engine only); corpora exact versions/hashes fixed at download time (8.9); target-app list is proposed (16.3).

## 2026-10-30 (cycle N+6, after rate-limit gap) — TRUE STATE
- Repo origin/claude/layout-corrector-spec HEAD 7e68d46 (code: strict LFC1 calibration, UndoSnapshot, 20.14 adapter contract + SimField fault matrix (387), layout fingerprint, HookHealth, vectors v3.1) on top of 16bc251 (plan v1.1 with P-1..P-8). Doc (Claude Docs) is STILL rev 117 = v3, NOT rewritten yet.
- L3 mutation run #1 (mut_L3, 659 mutants): 541 killed, 118 survived. I added P14 boundary tests to ref/conformance.py + FormatError (replaces assert in lfb/lfl/lfw loaders). Run #2 in mut_L3_r2 (background, log run.log).
- Equivalent mutants (document in audit report): log_softmax default temp; norm in score() cancels; 0.0*2/0.0/2; poisson bisection constants/range(200); relu s>0 vs >=; counts>0 (caught by pi_train check); pi_train hi bound; ev1 bound `<=` at exact equality; SimField caret 'back' pos-1; WittenBell min_count default.
- NEXT: analyse run #2 survivors -> report; then doc rewrite (13.2/13.3/13.4/13.5/13.6/13.7/13.8/15.3/16/10.1/10.2/11.x/5.1/7.5/D5/D6), transfer code to 20.x, export, sync, then audit lanes L1,L2,L4..L9.

## 2026-10-30 23:50 (cycle N+7, after rate-limit gap; the plan review attachment cf8fc17b was ALREADY handled by plan v1.1, commit 16bc251: do NOT redo)
- Mutation run #2 had died while checking survivors; restarted in background (mut_L3_r2/run.log, then report). Needs ~10-15 min (2 cores).
- L4 DONE in main session (agents lack WebFetch permission): repo file layout-corrector/audit/L4_platform_api_audit.md (W1a..W14, M1..M12). Design consequences for the doc:
  * layout id = FINGERPRINT (94 key states via ToUnicodeEx(dwhkl=foreground HKL, flag 4 = needs Windows 10 1607+); KLID cannot be read for another thread (GetKeyboardLayoutName = calling thread only) -> KLID diagnostic only; HKL read per key event (no global notification), fingerprint cached by HKL.
  * LL hook silently removed on timeout (<=1000 ms, LowLevelHooksTimeout) -> canary: Raw Input (message-only window, RIDEV_INPUTSINK, WM_INPUT RIM_INPUTSINK=1); UIPI behaviour of Raw Input UNVERIFIED.
  * SendInput: subject to UIPI, failure invisible in return value -> verify by read-back; one call per chunk is not interspersed with other input; KEYEVENTF_UNICODE = VK_PACKET, wVk=0, wScan char.
  * UIA TextPattern: page does NOT say read-only; IValueProvider "provides a programmatic way to change the text"; SetValue whole-value replace NOT stated. IsPassword TRUE => DENY.
  * Caps Lock: own state; GetKeyState low bit; resync at word boundary (mismatch drops word).
  * macOS: listen-only tap; permissions ListenEvent / PostEvent / Accessibility separate; tapDisabledByTimeout/ByUserInput -> clear state, re-enable <=3 per 60 s then OFF; heartbeat 5 s CGEventTapIsEnabled+CGPreflightListenEventAccess; kCGEventSourceUserData 64-bit tag; Unicode string 20-unit chunk NOT documented (spike).
- New IDs I used in audit file (must appear in the doc): spikes S-1 (Raw Input vs WH_KEYBOARD_LL), S-2 (Windows layout id: GetKeyboardLayout foreground + ToUnicodeEx fingerprint), S-3 (Raw Input canary + UIPI), S-4 (M1 on Windows: edit controls/UIA cross-process), S-5 (RegisterHotKey swallow/error), S-6 (macOS permissions + keycodes on Russian-PC), S-7 (macOS tag + unicode chunk); regression test RT-15 (dead-key sequence after fingerprint); failure-table rows 14,15 = hook loss detector rows; phase P1.. in 7.5.

## 2026-10-31 08:50 (cycle N+7) DOC STATE CORRECTION
- Doc (Claude Docs) is at REV 120, NOT 117: an earlier cycle already rewrote in the doc (revs 118-120): 13.2 (capabilities sentence, steps list, M1/M2 bullets, Outcome step with VERIFIED/RESTORED/UNRECOVERED/ABORTED, undo snapshot step 7, "What happens to the user's keys", "Two guarantees" G-EVENT/G-FIELD), 13.3 (manual-conversion bullet, Undo window bullet), 13.4 (word buffer / undo snapshot / crash dumps bullets).
- New IDs promised by that text, to be defined in the doc: RT-15 (dead-key regression after fingerprint), RT-16 (delivery of real key events: hook vs Raw Input counter, 1e6 events, loss 0), RT-17 (own crash handler excludes the undo snapshot), spike S-7 (macOS tag + 20-unit chunk), invariant I1 (20.13), `Engine.on_outcome` (20.7), rule "13.7: M2 never runs automatically", reason code `modifier_down`.
- REMAINING doc work (check each by search before writing): 13.3 chord table (undo row text), 13.5 failure table (rows 3,4,6,7,10 policy; new rows hook loss/layout fingerprint), 13.6 RT-4,RT-7,RT-8 + new RT-15..RT-17, 13.7 table (Active layout fingerprint, M1/M2, hook health, caps), 13.8 status ladder UNKNOWN/MANUAL/AUTO, 13.9 AP-3 layout pair, 14.1/4.1/5.4 layouts, 10.1/10.2/10.8, 11.x G2/EV-1 wording, 15.3/15.4, 16.1/16.2, 7.5 phases, D5/D6, glossary, version v3.1, CHANGELOG, transfer code 20.x.
- 2026-10-31 doc rev 135 DONE by me this cycle: 13.5 intro+table (14 rows; row 13 hook loss, row 14 permission), 13.6 table RT-1..RT-18 (RT-15 layout fingerprint tests, RT-16 delivery 1e6 events, RT-17 crash handler, RT-18 engine_mode), 13.7 scope+table (+capabilities table, mode rule, control class x write table; spikes S-1..S-7 named), 13.8 status ladder UNKNOWN/MANUAL/AUTO, 5.1 token formula s = raw_shift XOR (caps AND k in L) + Caps bullet, 14.1 rows, 4.1, 5.4, AP-3, 10.1 temperature scalar + pi_train_counts, 10.2 Estimation (w_ship = lower end 90% interval, D5 stores w only).
- Still TODO in doc: CA-9 row text (strict LFC1), 10.8, 8.4/11.5 (w, R-NAT), 11.2 EV-1 wording + 11.3 (cluster 'conservative criterion'), 11.7, G2 rename in 16.1 (+16.2 risks, spikes S-1..S-7 in 16.1/16.2), 15.3/15.4, 7.5 (per-phase latency), D5/D6 in 15.1, glossary (19.2), 4.4 evidence statuses?, version v3.1 title, 20.x code transfer + 20.12 JSON + 20.13 + 20.14 NEW, 20.1 table, 18 EV-1 simulation (L6), CHANGELOG_v3.1.md, fix L4 report "13.5 rows 14 and 15" -> row 13.

## 2026-10-31 14:00 (cycle N+8) WARNING: in-context reads showing doc rev 117 were STALE; fresh read says REV 135 (matches the 08:50 note). ALWAYS re-read with search/sinceRev before writing.
- Second external plan review (attachment c6b24b3a) already handled: plan v1.2 = commit 589680c (Q-1..Q-9) pushed. Do NOT redo.
- Mutation run #2 (mut_L3_r2) at ~450/659 at 14:00; then report -> mut_L3_r2/L3_mutation_report.md (copy to repo audit/).
- mutation: resumable driver mut_L3_r2/resume_run.py [deadline s] appends results.jsonl (background processes die when the container idles/restarts; re-run it to resume); report via 'python3 mutate.py report' after results.json exists

## 2026-10-31 (cycle N+8) the attachment c6b24b3a (review of plan v1.1 commit 16bc251, items Q-1..Q-9) was ALREADY handled by plan v1.2 (commit 589680c). Do NOT redo.
- L4 report extended (repo audit/L4_platform_api_audit.md); plan v1.2 pushed. Doc still rev 117 (v3) at 2026-10-31 18:50: DOC REWRITE NOT STARTED yet.
- Block ids (rev 117): 13.2 'Replacement transaction.' para m477x5gessc.171176 h180ff895; 'What happens to the user's keys' .173305 hd0ff33db; 'Guarantee, stated precisely' .173922 hc8f57b2e (all rev 45). Use search payload {"kind":"search","text":...,"engine":"prose"} (read with engine prose, ref node 8b22a85e-ac20) to get ids; outline projection is too verbose.

## 2026-11-03 (cycle N+9, after two rate-limit gaps; the third external review "Проверка редакции 1.2, коммит 589680c" was ALREADY handled: plan 1.3, L4 rev 2, code R-1..R-8; it is re-sent verbatim after each gap: do NOT redo)
- Doc (Claude Docs) is at REV 261 = v3.1. Section 20 code blocks are byte-identical (blank lines ignored) to reference/: lfengine (20.2-20.11 + 20.14), vectors.py, vectors_out.json, conformance.py (3 blocks in 20.13). Check: scratchpad verify_doc.py <export.md>.
- Text updated this cycle: 13.2 (transaction, last look, whole-fragment read-back), 13.5 (modes; row 13 signature matching), 13.6 (RT-4/13/16), 13.7/13.8 (single Raw Input registrant, S-6 open, AUTO/MANUAL_ONLY/OFF counts per OS), 20.1, 20.12, 20.13, new 18.9 (L6 simulation), G2 -> "G2-proxy" everywhere (WP-3); WP-6 stands in 10.2.
- Reference: modes other than AUTO record nothing (13.5); conformance.py: 1,860,821 checks, 1,665 faults, `python3 -O` same count; test_ref.py OK.
- Mutation run r6 (692 mutants) on the final code is running in scratchpad mut_L3_r6 (resume: `bash loop.sh`); the L3 report still describes the older run and must be updated.
- spec/CHANGELOG_v3.1.md written. Remaining: finish r6 and L3 report; audit lanes L1 (blind Node re-implementation), L2 (numbers), L5 (traceability), L7 (reproducibility), L8 (stale phrases), L9 (FMEA), L10 (audit/MANIFEST.sha256 with the full commit SHA); fix findings; final report with the list of blockers that cannot be closed in the cloud.

## 2026-11-07 (after the fourth review T-1..T-4; state of the audit)
- Mutation run r8 on the final code: 708 mutants, 674 killed = 95.2% (criterion met literally). The tests added after r7 found a real defect: poisson_upper returned a wrong limit for conf > 0.99995; fixed (interval grows, domain checked), spec 20.9 and 20.13 updated, blocks byte-identical (L7). Report: audit/L3_mutation_and_fuzz.md, evidence script audit/L3/L3_equivalence_evidence.py. F-3 open: WittenBell.fit does not validate multiplicity >= 1.
- L1 (blind Node.js re-implementation): round 1 partial (292/309 entries, 25/29 keys), agent interrupted by the usage limit; report assembled from its code (audit/L1/L1_report.md). Three text gaps fixed in rev 295 (row formats of the vectors in 20.12, EV-1 bound for no error in 11.3, tok25 rule). Round 2 open (needs vectors.py and 7.7 in the input).
- Reports L2, L5, L7, L8, L9 re-run on the final files; audit/README.md lists every line and what is not closed; audit/MANIFEST.sha256 + make_manifest.sh + CI step added. The audit is NOT complete (L1 round 2, independent L9).
- Doc: rev 295. Repo spec/TZ_layout_correction_v3.md = rev 295.

## 2026-11-09
- F-3 closed (6d7d14d). L3 run r9 on the code of 6d7d14d: 718 mutants, 684 killed = 95.3%, 34 survivors classified (audit/L3). Spec rev 305 committed (720713e). tests.yml had invalid YAML (python at column 0 inside `run: |`), re-indented.
- Independent L9 and L1 round 2: agent launches stopped at the usage limit (reset 21:30 local); not done, audit not declared complete.

## 2026-11-12
- L9 F1-F9, F11 fixed (code, tests P17, TZ rev 418 = repo spec copy, L7 IDENTICAL x4). L3 r10: 795 mutants, 760 killed = 95.6%. L1 round 2 report exists but is not blind. Attack scripts re-run on the final code (0 silent corruption outside residual R-1..R-3). Local Qwen was unreachable from the cloud container (no kit, nothing on 127.0.0.1:8080), nothing was delegated. Audit NOT complete.

## 2026-11-12 (second part)
- Static audit of ae89222, six items: 1, 2, 3, 4, 5 confirmed and fixed, 6 not a bug (text and tests). Code commit ba604f1, TZ rev 454 = repo copy (L7 IDENTICAL x4). r10 is void; L1 round 2 not blind; L9 fixes not independently reviewed. See audit/L9_independent/L9_independent_report.md.

## 2026-11-13
* r11 mutation run (977 mutants, 91.9%) on the code with toggle, selection and P3 fixes: below the 95% criterion; block G of conformance.py closes 38 of its 79 holes.
* U-1 closed in the reference: `run_transaction(..., ahead_len)`, M1 only, the typed characters are read and never written (13.3, 20.14, RT-5); runtime wired; 59 new checks. Spec rev 501.
* r12 fresh full run (991 mutants, 950 killed = 95.9%); the evidence script found one GAP (L1431_c01), closed by three checks (spec rev 502, L7 4/4 IDENTICAL).
* `spikes/`: result format and decision rules of S-1..S-7 with synthetic-only tests; no spike was run (needs Windows and macOS).
* Not done and not claimed: blind L1, independent second L9 review (no independent executor), LocLLM (not available in this container), OS adapters, real applications, calibration/latency on devices.

## 2026-11-14
* r13: fresh full mutation run, final code and final tests: 991 mutants, 951 killed = 96.0%, 40 survivors, all classified, 0 GAP. r12 is history.
* Measuring programs written, not run: S-2, S-5 (Windows, ctypes), S-6, S-7 (macOS, PyObjC/ctypes); `spikes/test_measure.py` tests their logic with fake bindings. S-1, S-3, S-4: not written. No spike result exists.

## 2026-11-14 (second part)
* Found and fixed: the S-1 validator accepted 100,000 events; RT-16 requires 1,000,000 compared one by one by signature, a named physical generator, and slow-hook detection within 300 ms. S-3 now needs 100 elevated events and consistent counts.
* New: `spikes/streams.py` (signature comparison), `control_probe.py` (the five S-4 tests as one routine), `merge_s4.py`, programs `windows/s1_s3_capture.py`, `windows/s4_edit_control.py`; tests `test_streams.py`, `test_probe.py`, `test_capture.py`; S-6 logic tests added to `test_measure.py` (S-6 had none).
* Still not done and not claimed: no spike was run; S-4 UI Automation and macOS AX bindings; the product observer that measures slow-hook detection.

## 2026-11-14 (third part)
* U-2 closed in the portable runtime (`hotkey_convert`, empty selection: last token before the caret, `source="last_word"`); 11 new runtime checks (45), normal and -O.
* New `app/adapter_contract.py` (checks every adapter must pass; run against `SimDriver`) and `app/test_adapter_contract.py` (3 capability sets pass, 7 broken adapters must fail). Reference double only; no OS adapter exists.
* New `spikes/slowhook.py` (replay of recorded streams through `HookHealth`), `s1slow` mode of the capture program (compiled, not run), `backend_control.py`, UIA and AX bindings of S-4 (compiled, not run), tests `test_slowhook.py`, `test_bindings.py`.
* Found: RT-16 "within 300 ms" cannot be met by `HookHealth` (300 to about 400 ms from the first lost key). Recorded as open item RT-16-VS-HOOKHEALTH; the validator was NOT loosened; `lfengine.py` and `conformance.py` unchanged, so mutation run r13 (950 KILLED + 1 TIMEOUT, 40 SURVIVED) stays bound to the same source and test SHA.
