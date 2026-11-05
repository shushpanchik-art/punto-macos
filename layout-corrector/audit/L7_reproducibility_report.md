# L7 reproducibility

Built on repository commit `5df564b859a0ee91145c74246550de4b836d8891` (parent of the commit that adds this file); specification rev 286. Run from `layout-corrector/audit/`.

Command: `bash L7_run_all.sh`. Extraction is deterministic (see the docstring of `L7_check_spec_blocks.py`): LF line ends, fenced blocks from the heading of section 20, `lfengine.py` = the blocks of 20.2 to 20.11 and 20.14 joined by two empty lines, `conformance.py` = the three blocks of 20.13 joined by nothing, the rest one block each. The same check runs in CI (`.github/workflows/layout-corrector.yml`).

```
== block check: code blocks of section 20 against reference/ (byte for byte)
lfengine.py        IDENTICAL  spec sha256 8799db30c4d45c48  file sha256 8799db30c4d45c48  (65211 bytes)
vectors.py         IDENTICAL  spec sha256 c5f791852a0a7f1a  file sha256 c5f791852a0a7f1a  (27933 bytes)
vectors_out.json   IDENTICAL  spec sha256 a31e225c8fcc36fb  file sha256 a31e225c8fcc36fb  (24674 bytes)
conformance.py     IDENTICAL  spec sha256 1ad2c9d3ac6dee19  file sha256 1ad2c9d3ac6dee19  (54586 bytes)
blocks per section: {'20.10': 1, '20.11': 1, '20.12': 2, '20.13': 3, '20.14': 1, '20.2': 1, '20.3': 1, '20.4': 1, '20.5': 1, '20.6': 1, '20.7': 1, '20.8': 1, '20.9': 1}
== vectors.py at ten PYTHONHASHSEED values against vectors_out.json
seed 0: identical
seed 1: identical
seed 2: identical
seed 3: identical
seed 4: identical
seed 5: identical
seed 42: identical
seed 1337: identical
seed 2147483647: identical
seed 4294967295: identical
== conformance.py, normal and optimised (same number of checks expected)
OK (1860829 checks, 1665 single and double faults, 627 fuzz conversions, 414 fuzz undos)
OK (1860829 checks, 1665 single and double faults, 627 fuzz conversions, 414 fuzz undos)
== test_ref.py
OK property tests; Russian words checked: 19653
== static check: iteration over set or dict values in the reference without sorted()
none found by grep (review the list above if any)
```

Result: byte-identical; the expected JSON is identical at ten values of PYTHONHASHSEED; `conformance.py` gives the same number of checks with and without `-O`.
