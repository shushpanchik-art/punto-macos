#!/usr/bin/env python3
"""Runs every attack_*.py against ../../reference, prints the raw output and CLASSIFIES it.

A script that exits 0 proves nothing: the attacks print, they do not assert. So the runner fails (exit 1) on
  * a non-zero exit status or a Traceback of any script (UNEXPECTED),
  * a line that reports a silent corruption (see BAD below) unless it is the one documented residual (R-2, marked RESIDUAL),
  * a transaction-fuzz line 'VIOLATION:'.
Findings that are accepted and documented (P3 list in L9_independent_report.md) are only printed as KNOWN, never hidden.
`--selftest` is the negative control: it runs three deliberately bad scripts and requires the runner to reject each.
Usage: python3 run_all_attacks.py [--selftest] [script ...] ; the exit status is 0 only when nothing unexpected was found."""
import glob, os, re, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
BAD = [re.compile(p) for p in (r"SILENT (WRONG WORD|CORRUPTION|HALF-CONVERTED)", r"VIOLATION:", r"silent corruptions: [1-9]",
                               r"silent half-converted words: [1-9]")]
RESIDUAL = re.compile(r"caret move no hook sees \(RESIDUAL, 13\.2\)")   # the one documented residual R-2
KNOWN = [("attack_engine_fuzz.py", "KeyError", "E-2 unknown layout id raises KeyError (P3)"),
         ("attack_hookhealth.py", "H-4", "H-4 tap re-enabled without MANUAL_ONLY (P3)"),
         ("attack_privacy.py", "queue", "P-2 HookHealth queues signatures in a DENY gate (P3)")]


def classify(name, status, out):
    """Returns (unexpected: list of str, known: list of str, residual: int)."""
    bad, known, residual = [], [], 0
    if status != 0:
        bad.append(f"exit status {status}")
    if "Traceback (most recent call last)" in out:
        bad.append("Traceback")
    for line in out.splitlines():
        if any(p.search(line) for p in BAD):
            if name == "attack_caret_anchor.py" and RESIDUAL.search(line):
                residual += 1
            else:
                bad.append("unexpected finding: " + line.strip()[:160])
    for n, needle, label in KNOWN:
        if n == name and needle in out:
            known.append(label)
    return bad, known, residual


def run(path, timeout=900):
    try:
        p = subprocess.run([sys.executable, path], cwd=HERE, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout + p.stderr
    except subprocess.TimeoutExpired:
        return 124, "timeout"


def main(argv):
    if "--selftest" in argv:
        cases = {"exit1": "import sys; print('ok'); sys.exit(1)", "silent": "print('x -> VERIFIED  <== SILENT CORRUPTION')",
                 "traceback": "raise RuntimeError('boom')"}
        good = 0
        with tempfile.TemporaryDirectory() as d:
            for k, code in cases.items():
                f = os.path.join(d, f"attack_{k}.py"); open(f, "w").write(code)
                st, out = run(f)
                bad, _, _ = classify(f"attack_{k}.py", st, out)
                print(f"selftest {k}: rejected={bool(bad)}")
                good += bool(bad)
            f = os.path.join(d, "attack_clean.py"); open(f, "w").write("print('fine')")
            st, out = run(f); bad, _, _ = classify("attack_clean.py", st, out)
            print(f"selftest clean: accepted={not bad}")
            good += (not bad)
        ok = good == 4
        print("SELFTEST", "PASSED" if ok else "FAILED")
        return 0 if ok else 1
    scripts = argv or sorted(glob.glob(os.path.join(HERE, "attack_*.py")))
    failed = 0
    for path in scripts:
        name = os.path.basename(path)
        st, out = run(path)
        bad, known, residual = classify(name, st, out)
        print(f"\n## {name}\n```\n{out.rstrip()}\nexit={st}\n```")
        print(f"RUNNER {name}: {'UNEXPECTED' if bad else 'ok'}; residual lines (R-2): {residual}; known open (P3): {known or 'none'}")
        for b in bad:
            print("  UNEXPECTED:", b)
        failed += bool(bad)
    print(f"\nRUNNER SUMMARY: {len(scripts)} scripts, {failed} with unexpected results")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
