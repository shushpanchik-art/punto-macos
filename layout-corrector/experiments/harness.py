"""Common evaluation harness for all models (n-gram, NN).

Test material is built once. Each model supplies predict_proba(X)->(N,3).
Token weights: words weighted by corpus frequency (10**zipf, language mass normalised to 1);
OTHER items share a total mass OTHER_MASS relative to one language.
"""
import numpy as np, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import data as dd
import evalkit as ek

OTHER_MASS = 0.12   # ~5.7% of all tokens are code/ids/urls/translit (assumption, see spec)

_cache = {}


def get_data():
    if "D" not in _cache:
        _cache["D"] = dd.build_all()
    return _cache["D"]


def test_material(split="test", tail=False, seed=11):
    """Full-word test set (one sample per type, no oversampling, canonical lowercase/original case)."""
    key = (split, tail)
    if key in _cache:
        return _cache[key]
    D = get_data()
    if tail:
        D = dict(D)
        D["en"], D["ru"] = D["en_tail"], D["ru_tail"]
        # tail words are not part of train/val/test split buckets -> use all of them
        from_split = lambda s: True
    seqs, ends, ys, z, lens = [], [], [], [], []
    en_list = D["en"]; ru_list = D["ru"]
    sel = (lambda w: True) if tail else (lambda w: dd.split_of(w) == split)
    for w, zz in en_list:
        if sel(w):
            ids = dd.encode_text(w, "en")
            if ids is not None:
                seqs.append(ids); ys.append(0); z.append(zz); lens.append(len(ids))
    for w, zz in ru_list:
        if sel(w):
            ids = dd.encode_text(w, "ru")
            if ids is not None:
                seqs.append(ids); ys.append(1); z.append(zz); lens.append(len(ids))
    other_ids = []
    if not tail:
        for s, wt in D["other"]:
            if dd.split_of(s) == split:
                ids = dd.encode_text(s, "en")
                if ids is not None:
                    seqs.append(ids); ys.append(2); z.append(0.0); lens.append(len(ids))
    ys = np.array(ys); z = np.array(z); lens = np.array(lens)
    w = np.where(ys < 2, 10.0 ** z, 0.0)
    for c in (0, 1):
        m = ys == c
        w[m] = w[m] / w[m].sum()
    m = ys == 2
    if m.sum():
        w[m] = OTHER_MASS / m.sum()
    X, l2 = dd.pack(seqs, [True] * len(seqs))
    mat = dict(seqs=seqs, X=X, y=ys, full_len=lens, w=w)
    _cache[key] = mat
    return mat


def prefix_material(mat, n):
    """Prefix of n key tokens (no EOS) for words with len > n."""
    idx = [i for i, s in enumerate(mat["seqs"]) if len(s) > n]
    seqs = [mat["seqs"][i][:n] for i in idx]
    X, _ = dd.pack(seqs, [False] * len(seqs))
    idx = np.array(idx)
    return dict(X=X, y=mat["y"][idx], full_len=mat["full_len"][idx], w=mat["w"][idx], idx=idx)


def weighted_op(score, pos, neg, w, fpr_target):
    """token-weighted operating point: threshold with weighted FPR <= target (negatives weighted by w)."""
    sn = score[neg]; wn = w[neg]
    order = np.argsort(-sn)
    cw = np.cumsum(wn[order]); tot = wn.sum()
    k = np.searchsorted(cw, fpr_target * tot, side="right")
    thr = sn[order][k] if k < len(sn) else 0.0
    rec = float((w[pos] * (score[pos] > thr)).sum() / w[pos].sum())
    fpr = float((wn * (sn > thr)).sum() / tot)
    return float(thr), rec, fpr


def evaluate(prob, mat, name="", temps=None):
    """prob: (N,3). returns dict of metrics."""
    y, L, w = mat["y"], mat["full_len"], mat["w"]
    pred = prob.argmax(1)
    res = dict(name=name)
    res["acc_type"] = float((pred == y).mean())
    res["acc_tok"] = float(((pred == y) * w).sum() / w.sum())
    res["ece"] = float(ek.ece(prob, y))
    res["nll"] = float(-np.log(prob[np.arange(len(y)), y] + 1e-12).mean())
    res["acc_by_len"] = ek.acc_by_len(pred, y, L, w)
    # directional operating points (token-weighted FPR), global threshold
    for direction in ("en2ru", "ru2en"):
        score = ek.flip_scores(prob, direction)
        pos = (y == 1) if direction == "en2ru" else (y == 0)
        neg = ~pos
        ww = w.copy()
        if direction == "ru2en":
            ww = np.where(y == 2, w * 0.15, w)   # OTHER much rarer under the RU layout
        d = {}
        for tgt in (1e-2, 1e-3, 1e-4):
            thr, rec, fpr = weighted_op(score, pos, neg, ww, tgt)
            # recall by length at this global threshold
            rbl = {}
            for lo, hi in ek.LEN_BUCKETS:
                m = pos & (L >= lo) & (L <= hi)
                if m.sum():
                    rbl[f"{lo}-{hi}" if lo != hi else f"{lo}"] = float((w[m] * (score[m] > thr)).sum() / w[m].sum())
            # unweighted (type-level) FPR as well
            nt = neg.sum()
            fpr_type = float(((score[neg] > thr)).mean())
            d[f"fpr{tgt:g}"] = dict(thr=thr, recall_tok=rec, fpr_tok=fpr, fpr_type=fpr_type, n_fp_types=int((score[neg] > thr).sum()), recall_by_len=rbl)
        res[direction] = d
    return res


def summarize(res):
    s = f"{res['name']:<28} acc_type={res['acc_type']:.4f} acc_tok={res['acc_tok']:.4f} ece={res['ece']:.4f}"
    for direction in ("en2ru", "ru2en"):
        d = res[direction]["fpr0.001"]
        s += f" | {direction} R@FPR1e-3={d['recall_tok']:.3f}"
        d2 = res[direction]["fpr0.0001"]
        s += f" R@1e-4={d2['recall_tok']:.3f}"
    return s
