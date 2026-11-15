#!/usr/bin/env python3
"""Freshness check of the requirements matrix: every `app/test_*.py` named in app/REQUIREMENTS_MATRIX.md with a check count is run and its own count must equal
the count written in the matrix. Run from anywhere; exit 1 on a mismatch. (A count in prose elsewhere is not checked.)"""
import os, re, subprocess, sys
root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
matrix = os.path.join(root, "app", "REQUIREMENTS_MATRIX.md")
if len(sys.argv) == 3 and sys.argv[1] == "--matrix":
    matrix = sys.argv[2]                     # used by the selftest below on a copy with a deliberate mismatch
text = open(matrix, encoding="utf-8").read()
bad = 0
seen = set()
for m in re.finditer(r"`app/(test_\w+\.py)`[^|]{0,12}?(\d[\d,]*) checks", text):
    name, claimed = m.group(1), int(m.group(2).replace(",", ""))
    if name in seen:
        continue
    seen.add(name)
    r = subprocess.run([sys.executable, os.path.join(root, "app", name)], capture_output=True, text=True, timeout=900)
    last = (r.stdout.strip().splitlines() or [""])[-1]
    got = re.match(r"OK \((\d+) ", last)
    ok = r.returncode == 0 and got is not None and int(got.group(1)) == claimed
    print(("ok   " if ok else "STALE"), name, "matrix:", claimed, "run:", got.group(1) if got else last[:60])
    bad += not ok
tests = {f for f in os.listdir(os.path.join(root, "app")) if f.startswith("test_") and f.endswith(".py")}
for f in sorted(tests - seen):
    print("NOT IN MATRIX WITH A COUNT:", f); bad += 1
sys.exit(1 if bad else 0)
