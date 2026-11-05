# L5 traceability

Built on repository commit `5df564b859a0ee91145c74246550de4b836d8891` (parent of the commit that adds this file); specification rev 286. Run from `layout-corrector/audit/`.

Command: `python3 L5_trace.py` (writes `L5_matrix.csv`). Identifier families: MD, DT, TR, CA, EV, DP, AP, RT, CT, D1 to D10.

```
members per family: {'AP': 11, 'CA': 11, 'CT': 6, 'D': 10, 'DP': 8, 'DT': 10, 'EV': 21, 'MD': 14, 'RT': 18, 'TR': 8}
referenced but never defined: []
defined but referenced nowhere else: []
requirements (MD DT TR CA EV DP AP) not named in 15.3, 13.6 or 20.13: 0 []
```

Findings of the first run and what was done: the identifiers DT-n are defined by a list, which the first version of the script did not read (script fixed); the requirements MD, TR, CA, DP, AP and EV-16 to EV-21 were not named in the test plan 15.3. A new section 19.3 of the specification maps every such requirement to a level of 15.3, a requirement test RT-n, a conformance test CT-n or an acceptance gate; the script now fails when a requirement is missing there. Result: 0 orphans in both directions.
