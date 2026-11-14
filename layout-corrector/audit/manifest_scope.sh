#!/bin/sh
# Single definition of the manifest scope. Prints, one per line, the tracked files that the MANIFEST must contain:
# every tracked file under layout-corrector/ (specification, reference engine, portable product code in app/, spikes/ and their tests, audit) and the CI
# workflow of this product, EXCEPT the explicit exclusions below. Sourced by make_manifest.sh and check_manifest_coverage.sh.
# Explicit exclusions (running notes and first-phase background material): the manifest itself, layout-corrector/WORKLOG.md, layout-corrector/README.md,
# layout-corrector/experiments/, layout-corrector/inputs/. Files of the repository outside layout-corrector/ (other projects) are not part of this product.
set -eu
cd "$(git rev-parse --show-toplevel)"
{ git ls-files -- layout-corrector .github/workflows/layout-corrector.yml; } | LC_ALL=C sort -u \
  | grep -v -e '^layout-corrector/audit/MANIFEST.sha256$' -e '^layout-corrector/WORKLOG.md$' -e '^layout-corrector/README.md$' \
            -e '^layout-corrector/experiments/' -e '^layout-corrector/inputs/'
