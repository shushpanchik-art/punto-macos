#!/bin/sh
# Wrapper: header with SHAs, then the Python runner. The exit status is the runner's (non-zero on any unexpected result).
# Usage: sh run_all_attacks.sh > L9_rerun_final_output.md ; echo $?
cd "$(dirname "$0")" || exit 1
echo "# L9 re-run of all attack scripts on the final code"
echo
echo "Commit (code under test): $(git rev-parse HEAD)  (working tree dirty: $(git status --porcelain ../../reference | wc -l) files)"
echo "lfengine.py sha256: $(sha256sum ../../reference/lfengine.py | cut -d' ' -f1)"
echo "conformance.py sha256: $(sha256sum ../../reference/conformance.py | cut -d' ' -f1)"
echo "Python: $(python3 --version)"
echo "Date: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
python3 run_all_attacks.py "$@"
