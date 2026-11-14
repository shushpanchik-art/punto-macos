#!/bin/sh
# Completeness check: every tracked file in the manifest scope is listed in MANIFEST.sha256, and every listed file is still tracked and in scope.
# Exit 0 = complete. Untracked files are not covered by design (a commit is what is published): `git status --short` must be empty.
set -eu
cd "$(git rev-parse --show-toplevel)"
M=layout-corrector/audit/MANIFEST.sha256
sh layout-corrector/audit/manifest_scope.sh > /tmp/lf_scope.$$
awk '{print $2}' "$M" | LC_ALL=C sort -u > /tmp/lf_listed.$$
missing=$(LC_ALL=C comm -23 /tmp/lf_scope.$$ /tmp/lf_listed.$$)
extra=$(LC_ALL=C comm -13 /tmp/lf_scope.$$ /tmp/lf_listed.$$)
rm -f /tmp/lf_scope.$$ /tmp/lf_listed.$$
bad=0
[ -z "$missing" ] || { echo "NOT IN MANIFEST:"; echo "$missing"; bad=1; }
[ -z "$extra" ] || { echo "LISTED BUT NOT IN SCOPE OR NOT TRACKED:"; echo "$extra"; bad=1; }
for must in layout-corrector/app/lfruntime.py layout-corrector/app/lflifecycle.py layout-corrector/spikes/streams.py layout-corrector/reference/lfengine.py; do
  grep -q " $must\$" "$M" || { echo "REQUIRED FILE MISSING: $must"; bad=1; }
done
[ "$bad" = 0 ] && echo "manifest coverage complete: $(wc -l < "$M") files"
exit "$bad"
