#!/bin/sh
# Builds layout-corrector/audit/MANIFEST.sha256 for the scope in manifest_scope.sh (all tracked product files, tests included; see that file for the
# explicit exclusions). Run it AFTER the last change and after `git add -A`; check with:
#   sha256sum -c layout-corrector/audit/MANIFEST.sha256      and      sh layout-corrector/audit/check_manifest_coverage.sh
# (from the repository root).
set -eu
cd "$(git rev-parse --show-toplevel)"
sh layout-corrector/audit/manifest_scope.sh | xargs sha256sum > layout-corrector/audit/MANIFEST.sha256
wc -l layout-corrector/audit/MANIFEST.sha256
