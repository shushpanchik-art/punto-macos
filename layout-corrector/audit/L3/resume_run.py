#!/usr/bin/env python3
"""Resumable driver for mutate.py: appends one JSON line per finished mutant to results.jsonl; stops submitting at a deadline."""
import json, os, sys, time, concurrent.futures as cf
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mutate as M
DEADLINE = time.time() + float(sys.argv[1] if len(sys.argv) > 1 else 480)
JL = os.path.join(M.HERE, "results.jsonl")
meta = json.load(open(M.META, encoding="utf-8"))
ids = [m["id"] for m in meta["mutants"] if m["run"]]
done = {}
if os.path.exists(JL):
    for line in open(JL, encoding="utf-8"):
        line = line.strip()
        if line:
            r = json.loads(line); done[r["id"]] = r
base_conf = M.run_conformance(M.BASE); base_vec = M.run_survivor_checks(M.BASE)
assert base_conf["status"] == "SURVIVED" and not base_vec.get("vec_differs") and base_vec.get("test_ref_rc") == 0, (base_conf, base_vec)
todo = [i for i in ids if i not in done]
print(f"done {len(done)}/{len(ids)}; todo {len(todo)}", flush=True)
def work(mid):
    if time.time() > DEADLINE: return None
    r = M.run_conformance(os.path.join(M.MDIR, mid))
    if r["status"] == "SURVIVED" and time.time() < DEADLINE + 60:
        r.update({k: v for k, v in M.run_survivor_checks(os.path.join(M.MDIR, mid)).items() if k != "id"})
    return r
with cf.ThreadPoolExecutor(max_workers=2) as ex, open(JL, "a", encoding="utf-8") as f:
    for r in ex.map(work, todo):
        if r is None: continue
        f.write(json.dumps(r, ensure_ascii=False) + "\n"); f.flush(); done[r["id"]] = r
left = [i for i in ids if i not in done]
print(f"done {len(done)}/{len(ids)}; left {len(left)}", flush=True)
if not left:
    # survivors missing the secondary checks (cut off by deadline) get them now
    for i, r in done.items():
        if r["status"] == "SURVIVED" and "vec_rc" not in r:
            r.update({k: v for k, v in M.run_survivor_checks(os.path.join(M.MDIR, i)).items() if k != "id"})
    json.dump({"baseline": {"conformance": base_conf, "vectors_test_ref": base_vec},
               "results": [done[i] for i in sorted(done)]}, open(M.RESULTS, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print("results.json written", flush=True)
