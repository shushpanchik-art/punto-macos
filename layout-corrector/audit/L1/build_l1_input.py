#!/usr/bin/env python3
"""Builds the input of audit line L1 (blind re-implementation) from a specification export.
Keeps sections 4, 5, 6, 10, 11, 13, 19, 20 and the subsections 7.1 and 7.7. Every code block of section 20 is replaced by a marker
EXCEPT the two blocks of 20.12 (the generator vectors.py, which defines every input, and the expected JSON).
Usage: build_l1_input.py <spec.md> <out.md>"""
import re, sys, hashlib
src, out = sys.argv[1], sys.argv[2]
lines = open(src, encoding='utf-8').read().replace('\r\n', '\n').split('\n')
KEEP_SEC = {'4', '5', '6', '10', '11', '13', '19', '20'}
KEEP_SUB = {'7.1', '7.7'}
res = []; sec = None; sub = None; fence = None; buf = []; keep = True; removed = 0
head_done = False
for i, l in enumerate(lines):
    if fence is None:
        m = re.match(r'^## (\d+)\.', l)
        if m: sec, sub = m.group(1), None
        m = re.match(r'^### (\d+\.\d+)\b', l)
        if m: sub = m.group(1)
        if sec is None:                      # title block before section 1
            res.append(l); continue
        inc = sec in KEEP_SEC or (sec == '7' and (re.match(r'^## 7\.', l) or sub in KEEP_SUB))
        m = re.match(r'^```(\w*)\s*$', l)
        if m and inc:
            fence, buf = m.group(1), []; continue
        if inc: res.append(l)
    else:
        if l.rstrip() == '```':
            block = buf
            if sec == '20' and sub != '20.12':
                res.append(f"[code block of {sub} removed: {len(block)} lines]")
                removed += 1
            else:
                res.append('```' + fence); res.extend(block); res.append('```')
            fence = None
        else:
            buf.append(l)
text = '\n'.join(res) + '\n'
open(out, 'w', encoding='utf-8').write(text)
print('written', out, len(text), 'bytes; code blocks of section 20 removed:', removed)
print('sha256', hashlib.sha256(text.encode('utf-8')).hexdigest())
