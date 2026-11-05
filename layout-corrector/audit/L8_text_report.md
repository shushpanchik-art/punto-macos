# L8 text: stale phrases, terminology, cross-references

Built on repository commit `5df564b859a0ee91145c74246550de4b836d8891` (parent of the commit that adds this file); specification rev 286. Run from `layout-corrector/audit/`.

Command: `python3 L8_scan.py`. The scanner checks forbidden phrases (cluster-adjusted bound, four modes, a gate before G4 that passes EV-1 or EV-12, fallback to the other scorer, a layout decision by KLID or the low word of the HKL, undo buffer, M2 admitted to AUTO, TBD or TODO, old version labels, a relied-on assert), every reference of the form 'section N.M', '(N.M)' and '(N.M to K.L)' against the headings, and leftovers outside the code blocks. Reviewed hits that state a rule by negating the old wording are listed in `ALLOWED` in the script.

```
headings: 128  findings: 0
```

Terminology counts in the prose (code blocks excluded): 'undo snapshot' 10 (no 'undo buffer'), 'calibration package' 17 (no 'calibration file'), 'word buffer' 7, `MANUAL_ONLY` 23 (no 'manual-only'), 'G2-proxy' 8 (no bare G2), 'conservative cluster criterion' 2 (no 'cluster-adjusted').

Limit of this lane: it is a pattern-based scan written by the author of the text. The independent reading of the whole text by a fresh agent was attempted three times and could not run (the agents stopped at the usage limit of the session before they started). It stays an open item for the external reviewer.
