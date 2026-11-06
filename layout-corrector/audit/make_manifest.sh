#!/bin/sh
# Builds layout-corrector/audit/MANIFEST.sha256: the SHA-256 of every tracked file of the audited revision
# (specification, reference engine, audit reports and scripts, the CI workflow). Run it from anywhere inside the
# repository AFTER the last change and after `git add`; check it with:  sha256sum -c layout-corrector/audit/MANIFEST.sha256
# (from the repository root). Not listed on purpose: the manifest itself, layout-corrector/WORKLOG.md and README.md
# (running notes), layout-corrector/experiments and layout-corrector/inputs (background material of the first phase).
set -eu
cd "$(git rev-parse --show-toplevel)"
git ls-files -- layout-corrector/spec layout-corrector/reference layout-corrector/audit .github/workflows/layout-corrector.yml \
  | grep -v '^layout-corrector/audit/MANIFEST.sha256$' | LC_ALL=C sort | xargs sha256sum > layout-corrector/audit/MANIFEST.sha256
wc -l layout-corrector/audit/MANIFEST.sha256
