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
