"""Evaluation helpers: 3-class metrics, directional flip decisions, calibration, rule-of-three."""
import numpy as np

CLS = ["EN", "RU", "OTHER"]
LEN_BUCKETS = [(2, 2), (3, 3), (4, 4), (5, 6), (7, 9), (10, 99)]


def softmax(z):
    z = z - z.max(1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(1, keepdims=True)


def fit_temperature(logits, y, grid=None):
    grid = grid if grid is not None else np.exp(np.linspace(np.log(0.3), np.log(5.0), 60))
    best, bt = 1e9, 1.0
    for t in grid:
        p = softmax(logits / t)
        nll = -np.log(p[np.arange(len(y)), y] + 1e-12).mean()
        if nll < best:
            best, bt = nll, t
    return bt


def ece(p, y, bins=15):
    conf = p.max(1)
    pred = p.argmax(1)
    acc = (pred == y).astype(float)
    edges = np.linspace(0, 1, bins + 1)
    e = 0.0
    for a, b in zip(edges[:-1], edges[1:]):
        m = (conf > a) & (conf <= b)
        if m.sum():
            e += m.mean() * abs(acc[m].mean() - conf[m].mean())
    return e


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    r = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - r) / d, (c + r) / d)


def acc_by_len(pred, y, full_len, weights=None):
    out = {}
    for lo, hi in LEN_BUCKETS:
        m = (full_len >= lo) & (full_len <= hi)
        if m.sum() == 0:
            continue
        ok = (pred[m] == y[m]).astype(float)
        out[f"{lo}-{hi}" if lo != hi else f"{lo}"] = dict(n=int(m.sum()), acc=float(ok.mean()),
                                                         wacc=float((ok * weights[m]).sum() / weights[m].sum()) if weights is not None else None)
    return out


def flip_scores(prob, direction):
    """direction 'en2ru' = active layout EN, flip when RU intended -> score p(RU). 'ru2en' -> p(EN)."""
    return prob[:, 1] if direction == "en2ru" else prob[:, 0]


def direction_sets(y, direction, other_weight_ru_layout=0.15):
    """positives: other-language intended; negatives: same-language intended + OTHER (weighted by plausibility under that layout)."""
    if direction == "en2ru":
        pos = (y == 1)
        neg = (y == 0) | (y == 2)
        negw = np.where(y == 2, 1.0, 1.0)
    else:
        pos = (y == 0)
        neg = (y == 1) | (y == 2)
        negw = np.where(y == 2, other_weight_ru_layout, 1.0)
    return pos, neg, negw


def operating_point(score, pos, neg, negw, fpr_target):
    """Smallest threshold with weighted FPR <= target. Returns thr, recall, fpr, n_fp."""
    s_neg = score[neg]
    w_neg = negw[neg]
    order = np.argsort(-s_neg)
    cw = np.cumsum(w_neg[order])
    tot = w_neg.sum()
    # number of allowed FP weight
    allowed = fpr_target * tot
    k = np.searchsorted(cw, allowed, side="right")  # k negatives may be above threshold
    if k >= len(s_neg):
        thr = 0.0
    elif k == 0:
        thr = s_neg[order][0] + 1e-9
    else:
        thr = s_neg[order][k - 1]  # threshold at kth negative, require score > next ; use strict greater than s_neg[order][k]
        thr = s_neg[order][k] if k < len(s_neg) else 0.0
    rec = float((score[pos] > thr).mean())
    fp = float(((s_neg > thr) * w_neg).sum())
    return float(thr), rec, fp / tot, fp


def deploy_precision(recall, fpr, pi):
    """precision at deployment where fraction pi of words are wrong-layout and (1-pi) are not."""
    tp = pi * recall
    fp = (1 - pi) * fpr
    return tp / (tp + fp) if tp + fp > 0 else float("nan")
