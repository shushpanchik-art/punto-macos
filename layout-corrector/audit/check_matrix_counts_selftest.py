#!/usr/bin/env python3
"""The matrix check must REJECT a deliberate mismatch. Works on a temporary copy; the real matrix is never changed. Exit 0 only if the clean copy passes and the
corrupted copy fails."""
import os, re, subprocess, sys, tempfile
here = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(here, "..", "app", "REQUIREMENTS_MATRIX.md"), encoding="utf-8").read()
m = re.search(r"`app/test_status\.py`[^|]{0,12}?(\d+) checks", src)
assert m, "pattern not found in the matrix"
bad = src[:m.start(1)] + str(int(m.group(1)) + 1) + src[m.end(1):]
d = tempfile.mkdtemp(prefix="lfmx_")
p_ok, p_bad = os.path.join(d, "ok.md"), os.path.join(d, "bad.md")
open(p_ok, "w", encoding="utf-8").write(src); open(p_bad, "w", encoding="utf-8").write(bad)
run = lambda p: subprocess.run([sys.executable, os.path.join(here, "check_matrix_counts.py"), "--matrix", p], capture_output=True, text=True)
r1, r2 = run(p_ok), run(p_bad)
assert r1.returncode == 0, "the clean copy must pass: " + r1.stdout[-300:]
assert r2.returncode == 1 and "STALE test_status.py" in r2.stdout, "the corrupted copy must be rejected: " + r2.stdout[-300:]
print("OK matrix check rejects a deliberate mismatch (status 31 -> 32) and accepts the real matrix")
