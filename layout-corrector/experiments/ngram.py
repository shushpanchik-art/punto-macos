"""Witten-Bell interpolated n-gram LM over key tokens, one LM per class (generative baseline)."""
import numpy as np, collections, math, time, sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import data as dd
import harness as hs


class WB:
    def __init__(self, order, V=dd.VOCAB):
        self.n = order
        self.V = V
        self.c = [collections.defaultdict(collections.Counter) for _ in range(order)]  # c[k][ctx(len k)] -> Counter(next)
        self.tot = [collections.Counter() for _ in range(order)]

    def fit(self, rows):
        for row in rows:
            for i in range(1, len(row)):
                nxt = row[i]
                for k in range(self.n):
                    if i - k < 0:
                        break
                    ctx = tuple(row[i - k:i])
                    self.c[k][ctx][nxt] += 1
        for k in range(self.n):
            for ctx, cn in self.c[k].items():
                self.tot[k][ctx] = sum(cn.values())

    def logp(self, row):
        lp = 0.0
        for i in range(1, len(row)):
            nxt = row[i]
            p = 1.0 / self.V
            for k in range(0, self.n):
                if i - k < 0:
                    break
                ctx = tuple(row[i - k:i])
                cn = self.c[k].get(ctx)
                if cn is None:
                    break
                t = self.tot[k][ctx]
                u = len(cn)
                p = (cn.get(nxt, 0) + u * p) / (t + u)
            lp += math.log(p)
        return lp


def rows_from_X(X):
    rows = []
    for r in X:
        n = int((r != 0).sum())
        rows.append([int(v) for v in r[:n]])
    return rows


class NgramClassifier:
    def __init__(self, order=4):
        self.order = order

    def fit(self, X, y):
        rows = rows_from_X(X)
        self.lms = []
        for c in range(3):
            lm = WB(self.order)
            lm.fit([r for r, yy in zip(rows, y) if yy == c])
            self.lms.append(lm)
        cnt = np.bincount(y, minlength=3).astype(float)
        self.logprior = np.log(cnt / cnt.sum())
        return self

    def predict_proba(self, X):
        rows = rows_from_X(X)
        S = np.zeros((len(rows), 3))
        for i, r in enumerate(rows):
            for c in range(3):
                S[i, c] = self.lms[c].logp(r) + self.logprior[c]
        S -= S.max(1, keepdims=True)
        P = np.exp(S)
        return P / P.sum(1, keepdims=True)


if __name__ == "__main__":
    D = hs.get_data()
    X, y, lens, meta = dd.make_split(D, "train", 0, prefix_p=0.35, full_only=False)
    print("train", X.shape, np.bincount(y))
    mat = hs.test_material("test")
    print("test", mat["X"].shape, np.bincount(mat["y"]))
    out = {}
    for order in (3, 4, 5):
        t = time.time()
        clf = NgramClassifier(order).fit(X, y)
        tt = time.time() - t
        t = time.time()
        prob = clf.predict_proba(mat["X"])
        res = hs.evaluate(prob, mat, f"ngram-WB-{order}")
        res["train_s"] = tt; res["pred_s"] = time.time() - t
        print(hs.summarize(res), f"(fit {tt:.0f}s, pred {res['pred_s']:.0f}s)")
        out[order] = res
        if order == 4:
            # prefix accuracy curve
            pc = {}
            for n in (2, 3, 4, 5, 6, 8):
                pm = hs.prefix_material(mat, n)
                pp = clf.predict_proba(pm["X"])
                pr = hs.evaluate(pp, dict(y=pm["y"], full_len=pm["full_len"], w=pm["w"]), f"prefix{n}")
                pc[n] = dict(n=int(len(pm["y"])), acc_type=pr["acc_type"], acc_tok=pr["acc_tok"],
                             en2ru_R1e3=pr["en2ru"]["fpr0.001"]["recall_tok"], ru2en_R1e3=pr["ru2en"]["fpr0.001"]["recall_tok"])
                print("  prefix", n, pc[n])
            out["prefix4"] = pc
            tail = hs.test_material("test", tail=True)
            pt = clf.predict_proba(tail["X"])
            rt = hs.evaluate(pt, tail, "ngram4-tail")
            print("  TAIL (rank 100k-200k, noisy labels):", f"acc_type={rt['acc_type']:.4f}", rt["acc_by_len"])
            out["tail4"] = dict(acc_type=rt["acc_type"], acc_by_len=rt["acc_by_len"])
    json.dump(out, open("res_ngram.json", "w"), indent=1, default=float)
