#!/bin/sh
# Runs every L9 attack script against ../../reference and prints raw output. Not part of CI (the scripts print, they do not assert).
# Usage: sh run_all_attacks.sh > L9_rerun_final_output.md
cd "$(dirname "$0")" || exit 1
echo "# L9 re-run of all attack scripts on the final code"
echo
echo "Commit (code under test): $(git rev-parse HEAD)"
echo "lfengine.py sha256: $(sha256sum ../../reference/lfengine.py | cut -d' ' -f1)"
echo "conformance.py sha256: $(sha256sum ../../reference/conformance.py | cut -d' ' -f1)"
echo "Python: $(python3 --version)"
echo "Date: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "Only the line marked RESIDUAL R-2 may print SILENT WRONG WORD."
for f in attack_*.py; do echo; echo "## $f"; echo '```'; timeout 600 python3 "$f" 2>&1; echo "exit=$?"; echo '```'; done
