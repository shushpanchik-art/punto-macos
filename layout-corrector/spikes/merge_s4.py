#!/usr/bin/env python3
"""Merges the one-row S-4 files of several runs (one control class of one application each) into one S-4 result file.
All files must come from the same machine, OS build and tool revision, and none may be synthetic.
    python3 merge_s4.py out.json row1.json row2.json ...      then   python3 spikes.py out.json"""
import json
import sys


def merge(files):
    rows, head = [], None
    for f in files:
        with open(f, encoding="utf-8") as fh:
            d = json.load(fh)
        if d.get("spike") != "S-4" or d.get("synthetic") is not False:
            raise SystemExit(f"{f}: not a real S-4 file")
        key = tuple(d.get(k) for k in ("os", "os_build", "machine", "tool_revision"))
        if head is None:
            head = d
            first = key
        elif key != first:
            raise SystemExit(f"{f}: another machine, OS build or tool revision")
        rows += d["classes"]
    out = {k: v for k, v in head.items() if k != "classes"}
    out["classes"] = rows
    return out


if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    with open(sys.argv[1], "w", encoding="utf-8") as f:
        json.dump(merge(sys.argv[2:]), f, indent=1, ensure_ascii=False)
