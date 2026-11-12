# L1 round 2 report (blind re-implementation, audit lane L1)

Input: spec_without_code.md (sha256 db13a0b3...5568, checked). Code: run_vectors.js, lfcore.js, lfstats.js, lfengine.js, lftx.js (written by the previous agent). `node run_vectors.js` gives TOTAL 317/328 (re-run by me, same result).

**Honesty statement.** The "first honest attempt" column is copied from the previous agent's log first_run_all.txt (and first_run_parts1to4.txt). I did NOT re-measure it blind: I read the existing code and the text, I did not re-implement from zero. That log was produced against the round-1 text (the spec file was modified later, 2026-11-12 00:51), so the first-attempt numbers do not measure the current text. No code change was made by me: for each failing entry the text does not give the rule (see F1 to F5), so fixing it would have meant fitting to the vector.

## (a) Table per key

| Key | Entries | First attempt (from log) | After fixes (my run) | Remark |
|---|---|---|---|---|
| render | 10 | 10 | 10 | |
| caps | 4 | 4 | 4 | |
| caps_all | 48 | 48 | 48 | |
| prefix | 1 | 1 | 1 | |
| tok25 | 1 | 1 | 1 | |
| cands | 14 | 14 | 14 | |
| guards | 8 | 8 | 8 | |
| manual | 6 | 6 | 6 | |
| priors | 6 | 6 | 6 | |
| lambdas | 6 | 6 | 6 | |
| scores | 6 | 6 | 6 | |
| decide | 13 | 13 | 13 | |
| trace_run | 6 | 6 | 6 | |
| scen | 11 | 11 | 11 | |
| trace_undo | 7 | 7 | 7 | |
| undo | 27 | 27 | 27 | |
| ev1 | 7 | 7 | 7 | |
| poisson | 6 | 6 | 6 | |
| fnv | 5 | 5 | 5 | |
| wb | 9 | 7 | 7 | FAIL: lfb_bytes, lfb_sha256_16 not derivable (F1) |
| wb_score | 1 | 1 | 1 | |
| lfw | 5 | 0 | 0 | FAIL: layout of file and toy_weights not in text (F2); nothing was computed, entries are counted as failures |
| lfl | 8 | 6 | 6 | FAIL: bytes, sha256_16 not derivable (F3) |
| cal_json | 2 | 0 | 0 | FAIL: canonical JSON form and schema field names not in text (F4) |
| modes | 14 | 14 | 14 | |
| outcome | 6 | 6 | 6 | |
| tx | 66 | 66 | 66 | |
| fingerprint | 4 | 4 | 4 | passes, but see F6 |
| hook | 21 | 11 | 21 | text rule present in 20.14 (300 ms, "too late", reported at check or arrival); the log of the first attempt predates it per the file dates, not verified |
| **Total** | **328** | **307** | **317** | 11 entries fail: 2 + 5 + 2 + 2 |

Entries wb 7/9, lfw 0/5, lfl 6/8, cal_json 0/2 are failures and stay failures. Note on tx: the JSON says 57 cases in the table in 20.12 but the generated array has 66 entries per the harness (the vectors.py list has about 66 rows); the prose "57 named cases" is a stale number (F12).

## (b) Findings

Format: ambiguity / quote (section) / assumption / confirmed by vector / proposed fix / severity.

**F1. LFB1 byte layout is not given (wb: lfb_bytes 5216, lfb_sha256_16).**
Quote (20.10): "`LFB1` stores, for each class and each order, the contexts (key, total, distinct) and the pairs (key, count) as sorted records of 64-bit FNV-1a hashes". Missing: magic, header, field widths of total, distinct, count, record counts, the order of classes and orders, where the log pi_train values go, the sort order, the ordering of ctx and pairs. With my counts (contexts 115, pairs 204 over the toy vector) a brute-force over plausible widths (key 8 bytes, total/distinct 2/4/8, count 2/4/8, 0 to 27 counters of 4 or 8 bytes, header 0 to 64) gives six different layouts that all sum to 5216 bytes, so even the size cannot identify the layout. Assumption: none made, no code. Confirmed by vector: no. Fix: "Add a table of the LFB1 file: magic, header fields with widths, the order of the 3x3 blocks, the record layout with widths and the sort order, and the position and type of log pi_train." Severity CERTAIN (a normative file format with no layout; MD-13 cannot be implemented from the text).

**F2. LFW1 layout and toy_weights are not given (lfw: all 5 entries).**
Quote (20.11): "The header is the magic, the channel count, the embedding width and the kernel list; the body is float32 little endian in a fixed order ... `toy_weights` uses integer arithmetic only, so every language reproduces the same file byte for byte." Missing: magic bytes, width of each header field, the kernel-list encoding, the number of convolutions, the values of the toy channel count and embedding width, and the integer formula of the toy weights. The weights cannot be derived, so the logits cannot be computed. Only hint: vectors.py reads first_floats at offset `16+12`, which suggests a 16-byte fixed header plus a 3-entry kernel list of 4 bytes, but that is a reading of the code of the generator, not a rule of the text. Same for forward details: "same-padding" for even kernels (left/right split), mean pooling denominator, and head order max then mean are given only loosely ("max and mean pooling over every position ... `[3][2*ch]`"). Assumption: none, not implemented. Confirmed: no. Fix: "Give the exact header bytes, the toy parameters and the integer recurrence of toy_weights with its first 8 values, and the padding rule for even kernel widths." Severity CERTAIN.

**F3. LFL1 byte layout is not given (lfl: bytes 84, sha256_16).**
Quote (20.10): "`LFL1` stores the stage-4 sets as sorted unique 64-bit keys per table tag." The vector has 7 keys (56 bytes), so 28 bytes are header, but magic, table tag width, counts, whether empty tables are written, the order of tables and the byte order of the key are not stated. Sort order of keys (unsigned numeric?) not stated. Also not stated: lfl_pack lower-cases (case folding) the input words, which is only visible from the membership vector ("HELLO" in lex_en true). The sentence in 7.7 says "case-folded string"; the fold function (Unicode casefold vs lower, e.g. German sharp s) is not named. Assumption: lower-case via JS toLowerCase for lex_key; confirmed by the three key hashes and membership (Latin and Cyrillic only, so the difference between casefold and lower is not tested). Fix: "Give the LFL1 header and per-table record layout and name the fold (Unicode simple lower-casing or full casefold)." Severity CERTAIN for layout, MAYBE for the fold.

**F4. Calibration package JSON serialisation (cal_json: bytes 1332, sha256_16).**
Quote (20.5): "The package is stored as JSON (D5), written by `cal_to_json`, with the sets of the allow-lists as sorted lists." Missing: key order (sorted or insertion), separators, indentation, ensure_ascii, number formatting (0.9995 vs 9.995e-1, 1.0 vs 1), the exact schema LFC1 field names (only some are quoted: pi_train_counts, o_lat, w, temperature in the vectors.py calls). `example_cal` itself is in removed code; its field names are visible only through vectors.py use (cal["w"][a][st], cal["o_lat"], cal["pi_train"], cal["temperature"]) and the thresholds lam were fitted by the previous agent from 10.3 text values. Not derivable, not implemented. Fix: "State the canonical JSON form (key order, separators, float formatting, encoding) and list the LFC1 fields with types." Severity CERTAIN.

**F5. Start-of-row context convention of the Witten-Bell model is only visible in n_pairs (wb: n_pairs).**
Quote (7.7): "the sum over every token after `BOS` of `log p(token | the two tokens before it)`" and "contexts of 0, 1 and 2 tokens". The first token after BOS has only one token before it. Two conventions give the same log-probabilities (checked by probe1.js: -35.644469 in both) but different counts: 45 pairs (a context of order 2 is counted only when two tokens precede; the first token uses the order-1 context) against 47 (padded). The vector n_pairs [45,68,91] and the LFB1 size are the only discriminators. The previous agent chose 45 and it matched; the text does not decide it. Confirmed by vector: yes (only by n_pairs). Fix: "At position i < 2 only contexts of length i are counted and used; no padding token is added; BOS is an ordinary context token." Severity MAYBE (CERTAIN for the file: it changes the number of records in LFB1).

**F6. Layout fingerprint: hash input encoding (fingerprint 4/4 pass).**
Quote (20.14): "A layout is identified by the SHA-256 of its 94 characters (key by key, without and with Shift, Caps Lock off)". Not stated: separator between characters (code uses "\n"), encoding (UTF-8), key-major order (unshifted then shifted of key 0, ...). The previous agent's code joins with "\n". Confirmed by vector (digest matches), so this rule is inferable from the vector (the previous agent had no way to read the separator from the text). Fix: "The digest input is the 94 characters in key-major order (unshifted, shifted), joined with U+000A, in UTF-8." Severity MAYBE (the digest would differ for any other separator, so it behaves like CERTAIN for conformance).

**F7. Stub scorers of the traces (trace_run, trace_undo, scen).**
Quote (20.12 prose): "the following `ntcn` is decided in the state `default` again and is KEEP (`abstain`, margin -2.707)". The stub logits of the middle words (MID = [-3, 6.5, -2]) and the table {ghbdtn: HI} are visible only in vectors.py (round 2 input), before that only the margin -2.707 in the prose. Whether the previous agent derived 6.5 from the margin (a fit) in round 1 is not provable now; now vectors.py provides it, so the stimulus is legitimate in round 2. Fix: none needed if vectors.py stays in the spec; otherwise state the stub in the prose. Severity MAYBE (resolved by the round-2 text).

**F8. HookHealth details.** The quote in 20.14 ("each event of one side must meet an event with the same signature from the other side within 300 ms, in either order; a counterpart that arrives later is too late, and the loss is declared when it arrives or at the next check, whichever comes first") fixes the pass cases; the previous agent's first run failed 10 of 21 (log), now 21/21. Residual MAYBE: the rule "the gap is reported once" (take_gap clears the flag, ok stays false until reinstalled) and "three pairs ... after the hook is installed again" counting pairs of equal signature are in prose of the table but the semantic of `h.ok` right after the 3rd pair vs after the 1st is only checked by vector rows "re-arm pair 1..3" (expected false, false, then?). Fix: add one sentence "ok stays false until the third pair is matched, and becomes true on that pair". Severity MAYBE.

**F9. SimField fault semantics are only named, not defined (tx 66/66 pass).** Quote (20.14): "partial (half is written, then an error)", "stale", "forward2", "applied_error", "autocorrect (the application changes the last character)", "spill (the Space after the range is damaged)". Half of what (the new text, rounded how), what stale text is, what character replaces the last one in autocorrect and in spill (the final texts "приdtn", "приве?", "ghbdtn?" show it) are visible only in the expected final texts. The previous agent got them from the expected "final text" column, i.e. from the vector. Confirmed by vector: yes; inferable only from the vector for: partial half rounding (3 of 6 is obvious but 6 chars of "привет" is the only case), autocorrect replacing the last character by "?", spill replacing the Space by "?", stale (returns the old text), the exact positions of the caret faults. Fix: "Define each fault as a transformation of (old text, new text): partial = first floor(n/2) characters of the new text; autocorrect = last character replaced by '?'; spill = following Space replaced by '?'; stale = the text before the write." Severity MAYBE.

**F10. Engine event rules.** Passing, but prose of 20.7 leaves open: the cool-down counter semantics ("until 3 word decisions have been suppressed and 10 s have passed" is a conjunction; the "10 s" start is the undo time) and whether a `backspace` on an empty run of a dropped word clears credit; both are in the vectors only. Not re-derived by me. Severity MAYBE.

**F11. Undo snapshot expiry boundaries.** "the expiry at exactly 10,000 ms and at 100 characters" (20.12 table) vs the prose of 13.3 (not read by me in full); the vectors fix: valid at exactly 10000 ms, invalid at 10001; valid after 100 further characters, invalid after 101. The text of 20.7 should state "inclusive". Severity MAYBE.

**F12. Stale counts in prose.** The table of 20.12 says of `tx` "the fault matrix of the replacement transaction, 57 named cases", but the generator and the expected JSON have 66 entries; `modes` says 14 cases (correct), `undo` says 17 steps while the generator has 27 entries. Quote (20.12 table, rows `tx` and `undo`). Fix: update the numbers or remove them. Severity CERTAIN (contradiction, harmless).

**F13. Contradiction of authority.** 20.1: "Where the prose of another section and this code disagree, the code and the vectors of 20.12 win". Since the code of 20.2 to 20.11 is removed from the audited text, the prose is the only rule for F1 to F5; in the full spec these layouts exist only as code, so a re-implementation in another language is possible only by reading the Python. This is exactly the issue, not a defect of the text by itself. Fix: add a layout table next to each file format in the prose. Severity MAYBE.

## (2) Provenance of the stimuli of passing keys

Inputs of every key are the inputs printed in vectors.py (20.12) or equivalently the input columns of the expected JSON. I compared the following with vectors.py line by line: render, caps, prefix, tok25, cands (14 entries, same list), guards (8), manual (6), priors (computed from cal), lambdas, scores (6), decide (13 cases, same lexicon stub), trace_run, trace_undo (same word list and times), ev1 and poisson (same cluster lists), the toy training sets of wb, the lexicon sets of lfl, and the hook, modes, outcome, tx, fingerprint rows (taken from EXP rows in lftx.js, which are the generator inputs). Not independently verified by me: scen and undo inputs in lfengine.js (I looked only at the trace stubs; the event lists were written from the JSON names and vectors.py is the same source), and the content of `example_cal` (field values rebuilt by the previous agent from 10.1 to 10.3; priors, lambdas, scores and decide pass, which pins them). Stimuli were therefore not invented; but three outputs were pinned only through the vector (F5 n_pairs, F6 separator, F9 fault results) and the tx/hook rules were adjusted after the first run (hook 11 -> 21). Rows where the input list came from the JSON itself (tx, modes, outcome, hook) cannot be "fitted" in the sense of stimuli, but the semantics of F9 can.

## (c) Keys not reached

All 29 keys were run. Not reached in the sense of "no honest result": lfw (0/5), cal_json (0/2), the byte parts of wb (2 of 9) and lfl (2 of 8). These are failures, not skipped.
