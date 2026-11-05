#!/usr/bin/env python3
"""L5: traceability of requirement identifiers in the specification.

Usage: python3 L5_trace.py [spec.md] [out_dir]     writes L5_matrix.csv and prints the orphans (exit 1 if any).
Rules (literal, no judgement):
  * an identifier is DEFINED by a table row whose first cell is that identifier (plain or bold), or by a heading that
    starts with it; families: MD DT TR CA EV DP RT AP CT, deliverables D1..D10, spikes S-1..S-7, gates G1..G5;
  * a REFERENCE is any other occurrence, including inside a range "X-a to X-b" (or "X-a to X-b" with a dash), which
    counts as a reference to every member of the range;
  * a requirement family member is VERIFIED when it is named (alone or in a range) in a row of the test plan (15.3),
    or in the requirement-test table 13.6 (RT), or in the traceability table 19.3, or in section 20.13 (CT), or is itself a test row (RT, CT);
  * orphans: referenced but never defined; defined but referenced nowhere else; requirements with no verification.
"""
import csv, os, re, sys, collections
HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "spec", "TZ_layout_correction_v3.md")
OUT = sys.argv[2] if len(sys.argv) > 2 else HERE
lines = open(SPEC, encoding="utf-8").read().split("\n")
FAMS = ["MD", "DT", "TR", "CA", "EV", "DP", "RT", "AP", "CT"]
ID = re.compile(r"\b(?:(?:%s)-\d+|D\d{1,2}|S-\d|G\d)(?![\w-])" % "|".join(FAMS))
RANGE = re.compile(r"\b((?:%s))-(\d+) (?:to|–|-) (?:\1-)?(\d+)\b" % "|".join(FAMS))


def section_of(i):
    for j in range(i, -1, -1):
        m = re.match(r"^#{2,3} (\d+(?:\.\d+)?)\b", lines[j])
        if m:
            return m.group(1)
    return "?"


defined, refs, in_test = {}, collections.defaultdict(list), collections.defaultdict(list)
for i, l in enumerate(lines):
    sec = section_of(i)
    m = re.match(r"^(?:\|\s*\**((?:%s)-\d+|D\d{1,2})\**\s*\||- \*\*((?:%s)-\d+)\*\*)" % ("|".join(FAMS), "|".join(FAMS)), l)
    h = re.match(r"^#{2,4} ((?:%s)-\d+)\b" % "|".join(FAMS), l)
    if sec == "19.3":                    # the traceability table lists identifiers; it defines none of them
        m = h = None
    if m or h:
        d = (m.group(1) or m.group(2)) if m else h.group(1)
        defined.setdefault(d, (i + 1, sec))
    covered = set()
    for fam, a, b in RANGE.findall(l):
        for n in range(int(a), int(b) + 1):
            covered.add("%s-%d" % (fam, n))
    for x in ID.findall(l):
        if m and x == (m.group(1) or m.group(2)):
            continue
        refs[x].append((i + 1, sec))
    for x in covered:
        refs[x].append((i + 1, sec))
        if sec in ("15.3", "13.6", "19.3") or sec.startswith("20.13"):
            in_test[x].append((i + 1, sec))
    for x in ID.findall(l):
        if sec in ("15.3", "19.3") or sec.startswith("20.13") or (sec == "13.6" and x.startswith(("RT", "CT"))):
            in_test[x].append((i + 1, sec))
members = sorted(set(defined) | set(x for x in refs if x[:2] in FAMS or re.match(r"D\d", x)), key=lambda s: (re.sub(r"\d|-", "", s), int(re.sub(r"\D", "", s) or 0)))
rows, undefined, unreferenced, unverified = [], [], [], []
for x in members:
    fam = re.sub(r"[-\d]", "", x)
    d = defined.get(x)
    r = refs.get(x, [])
    is_test = fam in ("RT", "CT")
    ver = is_test or bool(in_test.get(x))
    rows.append([x, "%s (line %d)" % (d[1], d[0]) if d else "", len(r), ";".join(sorted({s for _, s in r}))[:60], "yes" if ver else "no"])
    if not d:
        undefined.append(x)
    elif not r:
        unreferenced.append(x)
    if d and fam in ("MD", "DT", "TR", "CA", "EV", "DP", "AP") and not ver:
        unverified.append(x)
with open(os.path.join(OUT, "L5_matrix.csv"), "w", newline="", encoding="utf-8") as fh:
    w = csv.writer(fh)
    w.writerow(["id", "defined_at", "references", "referenced_in_sections", "named_in_a_test_row"])
    w.writerows(rows)
cnt = collections.Counter(re.sub(r"[-\d]", "", x) for x in members)
print("members per family:", dict(cnt))
print("referenced but never defined:", undefined)
print("defined but referenced nowhere else:", unreferenced)
print("requirements (MD DT TR CA EV DP AP) not named in 15.3, 13.6 or 20.13:", len(unverified), unverified)
sys.exit(1 if (undefined or unreferenced) else 0)
