#!/usr/bin/env python3
"""L7: the code blocks of section 20 of the specification are byte-identical to the files of ../reference.

Deterministic extraction (no judgement, no tolerance):
  * the specification is read as UTF-8, CRLF is turned into LF;
  * from the heading "## 20." on, every fenced block (a line "```lang" up to the next line "```") is one block;
    the section of a block is the last heading "### 20.n" above it;
  * lfengine.py    = the python blocks of 20.2 ... 20.11 and 20.14, in this order, joined by exactly two empty lines
                     (each block ends with a line feed; the join string is "\\n\\n");
  * vectors.py     = the only python block of 20.12;
  * vectors_out.json = the only json block of 20.12;
  * conformance.py = the python blocks of 20.13, in order, joined by exactly one empty line (the join string is "\\n").
Each result is compared with the file of the reference directory byte for byte. Exit code 0 = identical.

Usage: python3 L7_check_spec_blocks.py [spec.md] [reference_dir]
"""
import hashlib
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "spec", "TZ_layout_correction_v3.md")
REF = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "..", "reference")


def blocks_of(spec_text):
    lines = spec_text.replace("\r\n", "\n").split("\n")
    start = next(i for i, l in enumerate(lines) if l.startswith("## 20. "))
    out, sec, fence, cur = [], None, None, []
    for l in lines[start:]:
        if fence is None:
            m = re.match(r"^### (20\.\d+)\b", l)
            if m:
                sec = m.group(1)
            m = re.match(r"^```(\w*)\s*$", l)
            if m:
                fence, cur = m.group(1), []
        elif l.rstrip() == "```":
            out.append((sec, fence, "\n".join(cur) + "\n"))
            fence = None
        else:
            cur.append(l)
    return out


def main():
    with open(SPEC, encoding="utf-8", newline="") as fh:
        blocks = blocks_of(fh.read())
    engine_sections = [f"20.{n}" for n in list(range(2, 12)) + [14]]
    assembled = {
        "lfengine.py": "\n\n".join(b[2] for s in engine_sections for b in blocks if b[0] == s and b[1] == "python"),
        "vectors.py": "".join(b[2] for b in blocks if b[0] == "20.12" and b[1] == "python"),
        "vectors_out.json": "".join(b[2] for b in blocks if b[0] == "20.12" and b[1] == "json"),
        "conformance.py": "\n".join(b[2] for b in blocks if b[0] == "20.13" and b[1] == "python"),
    }
    counts = {s: sum(1 for b in blocks if b[0] == s) for s in sorted({b[0] for b in blocks if b[0]})}
    bad = 0
    for name, text in assembled.items():
        with open(os.path.join(REF, name), "rb") as fh:
            ref = fh.read()
        mine = text.encode("utf-8")
        same = mine == ref
        bad += not same
        print(f"{name:18s} {'IDENTICAL' if same else 'DIFFERENT'}  spec sha256 {hashlib.sha256(mine).hexdigest()[:16]}  "
              f"file sha256 {hashlib.sha256(ref).hexdigest()[:16]}  ({len(ref)} bytes)")
        if not same:
            a, b = text.split("\n"), ref.decode("utf-8").split("\n")
            for i, (x, y) in enumerate(zip(a, b)):
                if x != y:
                    print(f"   first difference in line {i + 1}:\n   spec: {x[:100]!r}\n   file: {y[:100]!r}")
                    break
            else:
                print(f"   one is a prefix of the other: {len(a)} lines in the spec, {len(b)} in the file")
    print("blocks per section:", counts)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
