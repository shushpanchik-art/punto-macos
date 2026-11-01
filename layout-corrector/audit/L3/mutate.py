#!/usr/bin/env python3
"""mutate.py - single-point mutation testing of base/lfengine.py (standard library only).

  python3 mutate.py gen      generate mutants from line 173 (the '# ==== 20.5' marker) to the end,
                             compile-check them, write m/<id>/ for the mutants that are run, write mutants.json
  python3 mutate.py run      baseline checks, then conformance.py 20000 in every run mutant (4 workers);
                             survivors also get vectors.py (vs vectors_out.json) and test_ref.py; writes results.json
  python3 mutate.py report   writes L3_mutation_report.md from mutants.json and results.json
"""
import ast
import concurrent.futures as cf
import io
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tokenize
import warnings

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.join(HERE, "base")
MDIR = os.path.join(HERE, "m")
META = os.path.join(HERE, "mutants.json")
RESULTS = os.path.join(HERE, "results.json")
REPORT = os.path.join(HERE, "L3_mutation_report.md")
SRC = "lfengine.py"
OTHER_FILES = ["vectors.py", "conformance.py", "vectors_out.json", "test_ref.py"]
MARKER = "# ==== 20.5"
MAX_RUN = 700
SAMPLE_SEED = 5
SKIP_INTS = {47, 94, 95, 96, 97}
TIMEOUT = 150
WORKERS = 4
CMP_SWAP = {">=": ">", ">": ">=", "<=": "<", "<": "<=", "==": "!=", "!=": "=="}
OP_NAMES = {
    "a": "comparison", "b": "boolean", "c": "integer literal", "d": "float literal",
    "e": "statement deletion", "f": "True/False",
}


# ----------------------------------------------------------------------------- source handling
def load_source():
    with open(os.path.join(BASE, SRC), encoding="utf-8", newline="") as f:
        text = f.read()
    assert "\r" not in text, "unexpected CR characters"
    lines = text.split("\n")
    assert "\n".join(lines) == text
    marks = [i for i, line in enumerate(lines) if MARKER in line]
    assert len(marks) == 1, marks
    return text, lines, marks[0] + 1  # first mutable line, 1-based


def tokens_of(text):
    return list(tokenize.generate_tokens(io.StringIO(text).readline))


def slice_spans(toks):
    """(start, end) positions of every subscript '[...]' that has a top-level ':' inside it."""
    spans, stack = [], []
    for t in toks:
        if t.type != tokenize.OP:
            continue
        s = t.string
        if s in ("(", "[", "{"):
            stack.append([t.start, False, s])
        elif s in (")", "]", "}"):
            if not stack:
                continue
            start, colon, opener = stack.pop()
            if s == "]" and colon:
                spans.append((start, t.end))
        elif s == ":" and stack:
            stack[-1][1] = True
    return spans


def in_slice(pos, spans):
    return any(a <= pos < b for a, b in spans)


def is_float(s):
    if any(ch in s for ch in "xXoObBjJ"):
        return False
    if not ("." in s or "e" in s or "E" in s):
        return False
    try:
        float(s.replace("_", ""))
    except ValueError:
        return False
    return True


def self_statements(text):
    """Single-line statements that are `self.<name>(...)`, `self.<name> = ...` or `return None`,
    keyed by line number."""
    tree = ast.parse(text)
    out = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.stmt) or node.lineno != node.end_lineno:
            continue
        ok = False
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            f = node.value.func
            ok = isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id == "self"
        elif isinstance(node, ast.Assign) and len(node.targets) == 1:
            t = node.targets[0]
            ok = isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) and t.value.id == "self"
        elif isinstance(node, ast.Return) and isinstance(node.value, ast.Constant) and node.value.value is None:
            ok = True
        if ok:
            out.setdefault(node.lineno, []).append(node)
    return out


def qualified_name_map(text):
    """Return f(line) -> qualified name of the innermost enclosing def/class ('<module>' if none)."""
    tree = ast.parse(text)
    ranges = []

    def visit(node, prefix):
        for ch in ast.iter_child_nodes(node):
            if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                q = prefix + ch.name
                ranges.append((ch.lineno, ch.end_lineno, q))
                visit(ch, q + ".")
            else:
                visit(ch, prefix)

    visit(tree, "")

    def name_for(ln):
        best = None
        for a, b, q in ranges:
            if a <= ln <= b and (best is None or (b - a) < (best[1] - best[0])):
                best = (a, b, q)
        return best[2] if best else "<module>"

    return name_for


# ----------------------------------------------------------------------------- mutant generation
def gen_candidates(text, lines, first):
    toks = tokens_of(text)
    spans = slice_spans(toks)
    by_row = {}
    for t in toks:
        if t.type in (tokenize.NAME, tokenize.OP, tokenize.NUMBER):
            by_row.setdefault(t.start[0], []).append(t)

    raw = []

    def add(ln, op, c0, c1, rep, change, whole=None):
        raw.append({"line": ln, "op": op, "c0": c0, "c1": c1, "rep": rep, "change": change, "whole": whole})

    for ln in range(first, len(lines) + 1):
        src = lines[ln - 1]
        s = src.strip()
        if not s or s.startswith("#") or s.startswith(("import ", "from ")):
            continue  # blank, comment-only, import
        ct = by_row.get(ln, [])
        if not ct:
            continue  # no code tokens: docstring / string-only line
        for k, t in enumerate(ct):
            c0, c1 = t.start[1], t.end[1]
            if t.type == tokenize.OP and t.string in CMP_SWAP:
                new = CMP_SWAP[t.string]
                add(ln, "a", c0, c1, new, f"{t.string} -> {new}")
            elif t.type == tokenize.NAME:
                if t.string in ("and", "or"):
                    new = "or" if t.string == "and" else "and"
                    add(ln, "b", c0, c1, new, f"{t.string} -> {new}")
                elif t.string in ("True", "False"):
                    new = "False" if t.string == "True" else "True"
                    add(ln, "f", c0, c1, new, f"{t.string} -> {new}")
                elif t.string == "not" and k + 1 < len(ct) and ct[k + 1].start[0] == ln:
                    nxt = ct[k + 1]
                    after_if = k > 0 and ct[k - 1].type == tokenize.NAME and ct[k - 1].string in ("if", "elif")
                    before_in = nxt.type == tokenize.NAME and nxt.string == "in"
                    if after_if or before_in:
                        what = "if not" if after_if else "not in"
                        add(ln, "b", c0, nxt.start[1], "", f"remove 'not' ({what})")
            elif t.type == tokenize.NUMBER:
                if re.fullmatch(r"[0-9][0-9_]*", t.string):
                    n = int(t.string.replace("_", ""))
                    if n >= 1 and n not in SKIP_INTS and not (n == 1 and in_slice(t.start, spans)):
                        add(ln, "c", c0, c1, f"({t.string}+1)", f"{t.string} -> {t.string}+1")
                        add(ln, "c", c0, c1, f"({t.string}-1)", f"{t.string} -> {t.string}-1")
                elif is_float(t.string):
                    add(ln, "d", c0, c1, f"({t.string}*2)", f"{t.string} -> {t.string}*2")
                    add(ln, "d", c0, c1, f"({t.string}/2)", f"{t.string} -> {t.string}/2")

    for ln, nodes in self_statements(text).items():
        if ln < first:
            continue
        raw_line = lines[ln - 1].encode("utf-8")
        for node in nodes:
            before = raw_line[: node.col_offset].decode("utf-8")
            after = raw_line[node.end_col_offset:].decode("utf-8")
            if before.strip() or (after.strip() and not after.strip().startswith("#")):
                continue  # not the only statement on its line
            add(ln, "e", 0, 0, "", "delete statement (-> pass)", whole=before + "pass" + after)

    raw.sort(key=lambda c: (c["line"], c["op"]))  # stable: token order kept within (line, op)
    seq = {}
    for c in raw:
        key = (c["line"], c["op"])
        seq[key] = seq.get(key, 0) + 1
        c["id"] = f"L{c['line']:04d}_{c['op']}{seq[key]:02d}"
    return raw


def mutated(lines, c):
    src = lines[c["line"] - 1]
    if c["whole"] is not None:
        newline = c["whole"]
    else:
        newline = src[: c["c0"]] + c["rep"] + src[c["c1"]:]
    new_lines = list(lines)
    new_lines[c["line"] - 1] = newline
    return "\n".join(new_lines), newline


def compiles(text):
    try:
        compile(text, SRC, "exec")
        return True
    except (SyntaxError, ValueError):
        return False


def stage_gen():
    text, lines, first = load_source()
    cands = gen_candidates(text, lines, first)
    kept, dropped = [], []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for c in cands:
            new_text, newline = mutated(lines, c)
            src = lines[c["line"] - 1]
            assert newline != src, c["id"]
            rec = {"id": c["id"], "line": c["line"], "op": c["op"], "change": c["change"],
                   "original": src.strip(), "mutated": newline.strip()}
            if compiles(new_text):
                kept.append((rec, new_text))
            else:
                dropped.append(rec)
    kept.sort(key=lambda p: p[0]["id"])
    sampled = len(kept) > MAX_RUN
    if sampled:
        chosen = set(r["id"] for r in random.Random(SAMPLE_SEED).sample([r for r, _ in kept], MAX_RUN))
    else:
        chosen = set(r["id"] for r, _ in kept)

    if os.path.isdir(MDIR):
        shutil.rmtree(MDIR)
    os.makedirs(MDIR)
    for rec, new_text in kept:
        if rec["id"] not in chosen:
            continue
        d = os.path.join(MDIR, rec["id"])
        os.makedirs(d)
        with open(os.path.join(d, SRC), "w", encoding="utf-8", newline="") as f:
            f.write(new_text)
        for name in OTHER_FILES:
            shutil.copy2(os.path.join(BASE, name), os.path.join(d, name))

    per_op = {}
    for c in cands:
        per_op[c["op"]] = per_op.get(c["op"], 0) + 1
    meta = {
        "source": "git show 7e68d46:layout-corrector/reference/lfengine.py (copied to base/)",
        "marker": MARKER, "first_line": first, "total_lines": len(lines),
        "sampled": sampled, "max_run": MAX_RUN, "sample_seed": SAMPLE_SEED,
        "generated": len(cands), "not_compiling": len(dropped), "valid": len(kept),
        "run": len(chosen), "per_op_generated": per_op,
        "mutants": [dict(rec, run=(rec["id"] in chosen)) for rec, _ in kept],
        "not_compiling_list": dropped,
    }
    with open(META, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=1, ensure_ascii=False)
    print(f"generated={len(cands)} not_compiling={len(dropped)} valid={len(kept)} "
          f"sampled={sampled} run={len(chosen)} per_op={per_op}")


# ----------------------------------------------------------------------------- running
def run_conformance(path):
    mid = os.path.basename(path)
    try:
        p = subprocess.run(["python3", "conformance.py", "20000"], cwd=path,
                           capture_output=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        return {"id": mid, "status": "TIMEOUT", "conf_rc": None, "conf_head": ""}
    out = p.stdout.decode("utf-8", "replace")
    head = out.splitlines()[0][:160] if out.strip() else ""
    ok = out.startswith("OK")
    status = "SURVIVED" if (p.returncode == 0 and ok) else "KILLED"
    return {"id": mid, "status": status, "conf_rc": p.returncode, "conf_head": head}


def run_survivor_checks(path):
    mid = os.path.basename(path)
    out = {"id": mid}
    env = dict(os.environ, PYTHONHASHSEED="0")
    try:
        p = subprocess.run(["python3", "vectors.py"], cwd=path, env=env, capture_output=True, timeout=TIMEOUT)
        with open(os.path.join(path, "vectors_out.json"), "rb") as f:
            expected = f.read()
        out["vec_rc"] = p.returncode
        out["vec_differs"] = (p.returncode != 0) or (p.stdout != expected)
    except subprocess.TimeoutExpired:
        out["vec_rc"] = "TIMEOUT"
        out["vec_differs"] = True
    try:
        q = subprocess.run(["python3", "test_ref.py"], cwd=path, capture_output=True, timeout=TIMEOUT)
        out["test_ref_rc"] = q.returncode
    except subprocess.TimeoutExpired:
        out["test_ref_rc"] = "TIMEOUT"
    return out


def stage_run():
    meta = json.load(open(META, encoding="utf-8"))
    run_ids = [m["id"] for m in meta["mutants"] if m["run"]]
    base_conf = run_conformance(BASE)
    base_vec = run_survivor_checks(BASE)
    print("baseline conformance:", base_conf, flush=True)
    print("baseline vectors/test_ref:", base_vec, flush=True)
    if base_conf["status"] != "SURVIVED":
        sys.exit("baseline conformance does not print OK - stop")
    if base_vec.get("vec_differs") or base_vec.get("test_ref_rc") != 0:
        sys.exit("baseline vectors/test_ref check fails - stop")

    paths = [os.path.join(MDIR, mid) for mid in run_ids]
    results = {}
    with cf.ProcessPoolExecutor(max_workers=WORKERS) as ex:
        done = 0
        for r in ex.map(run_conformance, paths):
            results[r["id"]] = r
            done += 1
            if done % 50 == 0 or done == len(paths):
                print(f"conformance {done}/{len(paths)}", flush=True)
        survivors = sorted(i for i, r in results.items() if r["status"] == "SURVIVED")
        print(f"survivors: {len(survivors)}; running vectors/test_ref on them", flush=True)
        for v in ex.map(run_survivor_checks, [os.path.join(MDIR, i) for i in survivors]):
            results[v["id"]].update({k: v[k] for k in v if k != "id"})

    out = {"baseline": {"conformance": base_conf, "vectors_test_ref": base_vec},
           "results": [results[i] for i in sorted(results)]}
    with open(RESULTS, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    counts = {}
    for r in results.values():
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print("status counts:", counts, flush=True)


# ----------------------------------------------------------------------------- report
def label_of(r):
    if r["status"] != "SURVIVED":
        return r["status"]
    return "SURVIVED_BUT_VECTORS_DIFFER" if r.get("vec_differs") else "SURVIVED"


def md_code(s):
    s = s.replace("|", "\\|")
    if "`" in s:
        return "`` " + s + " ``"
    return "`" + s + "`"


def stage_report():
    meta = json.load(open(META, encoding="utf-8"))
    res = {r["id"]: r for r in json.load(open(RESULTS, encoding="utf-8"))["results"]}
    base_text, _, _ = load_source()
    name_for = qualified_name_map(base_text)

    run_muts = [m for m in meta["mutants"] if m["run"]]
    assert len(run_muts) == len(res) == meta["run"]
    n_run = len(run_muts)
    n_kill = sum(1 for m in run_muts if res[m["id"]]["status"] in ("KILLED", "TIMEOUT"))
    n_timeout = sum(1 for m in run_muts if res[m["id"]]["status"] == "TIMEOUT")
    survivors = [m for m in run_muts if res[m["id"]]["status"] == "SURVIVED"]
    n_vdiff = sum(1 for m in survivors if label_of(res[m["id"]]) == "SURVIVED_BUT_VECTORS_DIFFER")
    n_tr = sum(1 for m in survivors if res[m["id"]].get("test_ref_rc") != 0)
    rate = 100.0 * n_kill / n_run

    L = []
    L.append("# L3 mutation report: lfengine.py (reference engine), mutants from line %d (`%s`) to line %d"
             % (meta["first_line"], MARKER, meta["total_lines"]))
    L.append("")
    L.append("Source: `git show 7e68d46:layout-corrector/reference/lfengine.py`, copied to `base/`. "
             "Baseline: `python3 conformance.py 20000` prints OK; `vectors.py` matches `vectors_out.json`; "
             "`test_ref.py` passes. Each mutant runs `timeout 150 python3 conformance.py 20000` in its own directory.")
    L.append("")
    L.append("## Counts")
    L.append("")
    L.append("| quantity | value |")
    L.append("|---|---|")
    L.append(f"| generated (all operators, before compile check) | {meta['generated']} |")
    L.append(f"| did not compile (discarded) | {meta['not_compiling']} |")
    L.append(f"| valid mutants | {meta['valid']} |")
    L.append(f"| run | {n_run} (sampled: {'yes, deterministic sample of %d, random.Random(%d)' % (MAX_RUN, SAMPLE_SEED) if meta['sampled'] else 'no, all valid mutants'}) |")
    L.append(f"| killed (incl. timeouts) | {n_kill} |")
    L.append(f"| of which TIMEOUT | {n_timeout} |")
    L.append(f"| survived | {len(survivors)} |")
    L.append(f"| survived-but-vectors-differ (subset of survived) | {n_vdiff} |")
    L.append(f"| survivors where test_ref.py also fails | {n_tr} |")
    L.append(f"| **kill rate = killed / run** | **{rate:.1f}%** ({n_kill}/{n_run}) |")
    L.append("")
    L.append("## Per operator")
    L.append("")
    L.append("| op | kind | generated | not compiling | valid | run | killed | survived |")
    L.append("|---|---|---|---|---|---|---|---|")
    all_ops = sorted(set(meta["per_op_generated"]))
    for op in all_ops:
        gen = meta["per_op_generated"][op]
        nc = sum(1 for d in meta["not_compiling_list"] if d["op"] == op)
        valid = sum(1 for m in meta["mutants"] if m["op"] == op)
        rn = [m for m in run_muts if m["op"] == op]
        kl = sum(1 for m in rn if res[m["id"]]["status"] in ("KILLED", "TIMEOUT"))
        sv = sum(1 for m in rn if res[m["id"]]["status"] == "SURVIVED")
        L.append(f"| {op} | {OP_NAMES[op]} | {gen} | {nc} | {valid} | {len(rn)} | {kl} | {sv} |")
    L.append("")
    L.append("## Survivors by enclosing function")
    L.append("")
    L.append("Flags: `VECTORS_DIFFER` = vectors.py output differs from vectors_out.json (label SURVIVED_BUT_VECTORS_DIFFER); "
             "`test_ref FAILS` = test_ref.py exits non-zero.")
    L.append("")
    groups = {}
    for m in survivors:
        groups.setdefault(name_for(m["line"]), []).append(m)
    order = sorted(groups, key=lambda g: min(m["line"] for m in groups[g]))
    for g in order:
        rows = sorted(groups[g], key=lambda m: (m["line"], m["id"]))
        L.append(f"### `{g}` ({len(rows)})")
        L.append("")
        L.append("| id | line | op | original | mutated | flags |")
        L.append("|---|---|---|---|---|---|")
        for m in rows:
            r = res[m["id"]]
            flags = []
            if label_of(r) == "SURVIVED_BUT_VECTORS_DIFFER":
                flags.append("VECTORS_DIFFER")
            if r.get("test_ref_rc") != 0:
                flags.append("test_ref FAILS")
            L.append(f"| {m['id']} | {m['line']} | {m['op']} | {md_code(m['original'])} | "
                     f"{md_code(m['mutated'])} | {', '.join(flags)} |")
        L.append("")
    L.append("## Notes on how mutants were built")
    L.append("")
    L.append("- Operators were applied to code tokens only (strings, docstrings and comments are never mutated). "
             "Lines with no code tokens (comment-only, docstring, blank, import) are skipped.")
    L.append("- Integer and float literals are wrapped in parentheses, e.g. `2` -> `(2+1)`, `0.5` -> `(0.5*2)`, "
             "so the replacement is the whole expression, not a precedence change. Literals in slices (`[1:]`) with value 1 are skipped; "
             "values 47, 94, 95, 96, 97 are skipped.")
    L.append("- The `not` rule matches `not` after `if` or `elif` (the text `if not ` occurs inside `elif not `) and `not in`. "
             "Other `not` uses (e.g. `return not`, `and not`, `while not`) are not mutated, following the list in the task.")
    L.append("- Statement deletion covers single-line statements that are `self.<name>(...)` calls, `self.<name> = ...` assignments "
             "and `return None`. An annotated assignment `self.x: T = ...` is not of that form and was not mutated.")
    L.append("- Enclosing function names come from the AST ranges of def/class statements (innermost one), which is the same "
             "as scanning upward for the nearest enclosing def/class.")
    L.append("")
    with open(REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    print(f"report written: {REPORT}")
    print(f"generated={meta['generated']} not_compiling={meta['not_compiling']} valid={meta['valid']} "
          f"run={n_run} killed={n_kill} timeout={n_timeout} survived={len(survivors)} "
          f"vectors_differ={n_vdiff} test_ref_fail={n_tr} kill_rate={rate:.1f}%")


def main():
    stage = sys.argv[1] if len(sys.argv) > 1 else "all"
    if stage in ("gen", "all"):
        stage_gen()
    if stage in ("run", "all"):
        stage_run()
    if stage in ("report", "all"):
        stage_report()


if __name__ == "__main__":
    main()
