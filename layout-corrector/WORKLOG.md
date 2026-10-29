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
