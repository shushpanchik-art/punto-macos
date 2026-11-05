#!/usr/bin/env python3
"""L8: stale phrases, forbidden wording and cross-references of the specification.

Usage: python3 L8_scan.py [spec.md]     exit code 0 = no finding outside the reviewed list.
1. FORBIDDEN: phrases that contradict a current rule (see CHANGELOG_v3.1.md). Every hit is a finding unless the line
   is in ALLOWED (a reviewed statement that names the phrase in order to forbid it or to explain why it is gone).
2. CROSS-REFERENCES: every "section N.M", "sections N.M and K.L" and "(N.M)" must point to an existing heading.
3. LEFTOVERS: TBD, TODO, FIXME, placeholders outside code.
Standard library only; code blocks are skipped for 2 and 3.
"""
import re, sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "spec", "TZ_layout_correction_v3.md")
lines = open(SPEC, encoding="utf-8").read().split("\n")

in_code, prose = False, []
for i, l in enumerate(lines):
    if l.startswith("```"):
        in_code = not in_code
        continue
    if not in_code:
        prose.append((i + 1, l))

FORBIDDEN = {
    "cluster-adjusted bound (renamed: conservative cluster criterion)": r"cluster-adjusted",
    "four engine modes (there are three)": r"\bfour (engine )?modes\b|fourth mode",
    "a gate before G4 passing EV-1 or EV-12": r"G2(-proxy)?[^.|]{0,40}\b(passes|passed|pass) EV-1\b",
    "fallback to the other scorer (a bad package is refused whole)": r"fall ?back to the (other|second) scorer",
    "layout decided by the low word of the HKL or by KLID": r"decid\w+ (by|from) (the )?(low word|KLID)",
    "undo buffer (the term is: Undo snapshot)": r"undo buffer",
    "M2 admitted to AUTO": r"M2[^.|]{0,40}(may|can|is allowed to) (be|give|reach) AUTO",
    "TBD, TODO, FIXME, to be decided": r"\bTBD\b|\bTODO\b|\bFIXME\b|to be decided",
    "old version labels": r"\bv3\.0\b|version 3\.0",
    "an assert statement relied on": r"\bassert\b(?! statement)",
}
# reviewed hits: (pattern name, substring that must be in the line). They state the rule, not the stale wording.
ALLOWED = [("an assert statement relied on", "asserts disappear under"),
           ("an assert statement relied on", "It is an exception, not an assert")]
bad = 0
for name, pat in FORBIDDEN.items():
    for no, l in [(n, x) for n, x in enumerate(lines, 1)]:
        if re.search(pat, l, re.I if "undo buffer" in pat else 0):
            if any(n == name and s in l for n, s in ALLOWED):
                continue
            bad += 1
            print("FORBIDDEN [%s] line %d: %s" % (name, no, l.strip()[:160]))

headings = set()
for no, l in prose:
    m = re.match(r"^#{2,4} (\d+(?:\.\d+)?)\b", l)
    if m:
        headings.add(m.group(1))
for no, l in prose:
    if l.startswith("|") and re.match(r"^\|[\s\d.|\-:]*$", l):
        continue
    refs = set(re.findall(r"\bsections? (\d+\.\d+)\b", l))
    for grp in re.findall(r"\bsections ((?:\d+(?:\.\d+)?(?:, | and | to )?)+)", l):
        refs |= set(re.findall(r"\d+\.\d+", grp))
    refs |= set(re.findall(r"\((\d{1,2}\.\d{1,2})(?:[,;)]| to )", l))
    for r in sorted(refs):
        major = int(r.split(".")[0])
        if 1 <= major <= 20 and r not in headings:
            # a few numbers in parentheses are values, not references (a heading with that number does not exist)
            if re.search(r"\(%s[,;)]" % re.escape(r), l) and not re.search(r"section %s|\(%s, step|\(%s\)" % (re.escape(r), re.escape(r), re.escape(r)), l):
                pass
            bad += 1
            print("XREF line %d: no heading %s :: %s" % (no, r, l.strip()[:140]))
print("headings:", len(headings), " findings:", bad)
sys.exit(1 if bad else 0)
