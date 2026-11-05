#!/bin/bash
# L7: the repository equals the document. Run from anywhere:  bash audit/L7_run_all.sh
set -e
cd "$(dirname "$0")"
echo "== block check: code blocks of section 20 against reference/ (byte for byte)"
python3 L7_check_spec_blocks.py
echo "== vectors.py at ten PYTHONHASHSEED values against vectors_out.json"
cd ../reference
for seed in 0 1 2 3 4 5 42 1337 2147483647 4294967295; do
  PYTHONHASHSEED=$seed python3 vectors.py | cmp - vectors_out.json && echo "seed $seed: identical"
done
echo "== conformance.py, normal and optimised (same number of checks expected)"
python3 conformance.py | tail -1
python3 -O conformance.py | tail -1
echo "== test_ref.py"
python3 test_ref.py | tail -1
echo "== static check: iteration over set or dict values in the reference without sorted()"
grep -n -E "for [a-z_, ]+ in (set\(|[a-z_.]+\.(keys|values|items)\(\))" lfengine.py | grep -v "sorted(" || echo "none found by grep (review the list above if any)"
