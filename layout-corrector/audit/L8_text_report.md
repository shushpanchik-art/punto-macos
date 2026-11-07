# L8 text: stale phrases, terminology, cross-references

Re-run on the final files: `reference/lfengine.py` (git blob `6c5fc74041e38623b93b5641088673450258464f`), `reference/conformance.py` (blob `1c1f761a4e7cb38a2ddac39938f8d9d11839004a`), first commit holding them `053489e504766b11b96d689c5db89eaaef276451`; specification rev 295. The first run of this report (rev 286, commit `5df564b`) gave the same verdicts; the figures below are those of the re-run. Run from `layout-corrector/audit/`.

Command: `python3 L8_scan.py`. The scanner checks forbidden phrases (cluster-adjusted bound, four modes, a gate before G4 that passes EV-1 or EV-12, fallback to the other scorer, a layout decision by KLID or the low word of the HKL, undo buffer, M2 admitted to AUTO, TBD or TODO, old version labels, a relied-on assert), every reference of the form 'section N.M', '(N.M)' and '(N.M to K.L)' against the headings, and leftovers outside the code blocks. Reviewed hits that state a rule by negating the old wording are listed in `ALLOWED` in the script.

```
headings: 128  findings: 0
```

Terminology counts in the prose (code blocks excluded): 'undo snapshot' 10 (no 'undo buffer'), 'calibration package' 17 (no 'calibration file'), 'word buffer' 7, `MANUAL_ONLY` 23 (no 'manual-only'), 'G2-proxy' 8 (no bare G2), 'conservative cluster criterion' 2 (no 'cluster-adjusted').

Limit of this lane: it is a pattern-based scan written by the author of the text. The independent reading of the whole text by a fresh agent was attempted three times and could not run (the agents stopped at the usage limit of the session before they started). It stays an open item for the external reviewer.
