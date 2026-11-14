"""Shared parts of the measuring programs: the 47 physical keys with their set-1 scan codes (ANSI), the result header and the
writer. Nothing here touches an operating system."""
import datetime
import json
import os
import platform
import subprocess
import sys

# key id 0..46 in the order of 19.1 (number row, QWERTY row, home row, bottom row) and the scan code of each (set 1, ANSI keyboard)
SCAN = ([0x29] + list(range(0x02, 0x0C)) + [0x0C, 0x0D]                      # ` 1..9 0 - =
        + list(range(0x10, 0x1A)) + [0x1A, 0x1B, 0x2B]                        # q..p [ ] \
        + list(range(0x1E, 0x27)) + [0x27, 0x28]                              # a..l ; '
        + list(range(0x2C, 0x33)) + [0x33, 0x34, 0x35])                       # z..m , . /
assert len(SCAN) == 47 and len(set(SCAN)) == 47


def tool_revision():
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        return subprocess.check_output(["git", "-C", here, "rev-parse", "--short", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return os.environ.get("SPIKE_TOOL_REVISION", "")      # empty: the validator then refuses the file, on purpose


def header(spike, os_name, os_build, synthetic=False):
    return {"spike": spike, "os": os_name, "os_build": os_build, "machine": platform.node(), "tool_revision": tool_revision(),
            "started_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "synthetic": synthetic}


def write(result, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=1, ensure_ascii=False)
    print("wrote", path)


def main_out(argv, default):
    return argv[1] if len(argv) > 1 else default
