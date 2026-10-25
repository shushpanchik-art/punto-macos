"""Tiny neural classifiers over key-token sequences + training/eval/export utilities."""
import sys, os, time, json, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import torch, torch.nn as nn, torch.nn.functional as F
import data as dd
import harness as hs
import evalkit as ek

torch.set_num_threads(2)
V, L = dd.VOCAB, dd.MAXL


def nparams(m):
    return sum(p.numel() for p in m.parameters())


def masked_pool(h, mask):
    # h: (B,L,C) ; mask: (B,L) float
    m = mask.unsqueeze(-1)
    mx = (h - (1 - m) * 1e4).max(1).values
    mean = (h * m).sum(1) / m.sum(1).clamp(min=1)
    return torch.cat([mx, mean], -1)


class CNN(nn.Module):
    def __init__(self, ch=64, emb=None, kernels=(3, 5, 3), dropout=0.1):
        super().__init__()
        emb = emb or min(32, ch)
        self.emb = nn.Embedding(V, emb, padding_idx=0)
        cin = emb
        self.convs = nn.ModuleList()
        for k in kernels:
            self.convs.append(nn.Conv1d(cin, ch, k, padding=k // 2))
            cin = ch
        self.drop = nn.Dropout(dropout)
        self.head = nn.Linear(2 * ch, 3)

    def forward(self, ids):
        mask = (ids != 0).float()
        x = self.emb(ids).transpose(1, 2)
        m = mask.unsqueeze(1)
        for c in self.convs:
            x = F.relu(c(x)) * m
        h = x.transpose(1, 2)
        return self.head(self.drop(masked_pool(h, mask)))


class MHA(nn.Module):
    def __init__(self, d, heads):
        super().__init__()
        self.h = heads
        self.qkv = nn.Linear(d, 3 * d)
        self.o = nn.Linear(d, d)

    def forward(self, x, mask):
        B, T, D = x.shape
        q, k, v = self.qkv(x).chunk(3, -1)
        sp = lambda t: t.view(B, T, self.h, D // self.h).transpose(1, 2)
        q, k, v = sp(q), sp(k), sp(v)
        att = (q @ k.transpose(-1, -2)) / math.sqrt(D // self.h)
        att = att + (1 - mask)[:, None, None, :] * -1e4
        att = att.softmax(-1)
        return self.o((att @ v).transpose(1, 2).reshape(B, T, D))


class Block(nn.Module):
    def __init__(self, d, heads, ff, dropout):
        super().__init__()
        self.n1, self.n2 = nn.LayerNorm(d), nn.LayerNorm(d)
        self.att = MHA(d, heads)
        self.ff = nn.Sequential(nn.Linear(d, ff), nn.GELU(), nn.Linear(ff, d))
        self.drop = nn.Dropout(dropout)

    def forward(self, x, mask):
        x = x + self.drop(self.att(self.n1(x), mask))
        return x + self.drop(self.ff(self.n2(x)))


class TinyTransformer(nn.Module):
    def __init__(self, d=64, layers=2, heads=4, dropout=0.1):
        super().__init__()
        self.emb = nn.Embedding(V, d, padding_idx=0)
        self.pos = nn.Embedding(L, d)
        self.blocks = nn.ModuleList([Block(d, heads, 2 * d, dropout) for _ in range(layers)])
        self.norm = nn.LayerNorm(d)
        self.head = nn.Linear(2 * d, 3)

    def forward(self, ids):
        mask = (ids != 0).float()
        pos = torch.arange(ids.shape[1], device=ids.device)
        x = self.emb(ids) + self.pos(pos)[None]
        for b in self.blocks:
            x = b(x, mask)
        x = self.norm(x)
        return self.head(masked_pool(x, mask))


class BiGRU(nn.Module):
    def __init__(self, hidden=64, emb=32, dropout=0.1):
        super().__init__()
        self.emb = nn.Embedding(V, emb, padding_idx=0)
        self.rnn = nn.GRU(emb, hidden, batch_first=True, bidirectional=True)
        self.drop = nn.Dropout(dropout)
        self.head = nn.Linear(4 * hidden, 3)

    def forward(self, ids):
        mask = (ids != 0).float()
        h, _ = self.rnn(self.emb(ids))
        return self.head(self.drop(masked_pool(h, mask)))


class HashBag(nn.Module):
    """fastText/CLD3-style: hashed 1..4-gram embeddings, mean pooled, linear head."""
    def __init__(self, buckets=8192, dim=16, orders=(1, 2, 3, 4), dropout=0.1):
        super().__init__()
        self.B, self.orders = buckets, orders
        self.emb = nn.Embedding(buckets * len(orders), dim)
        self.drop = nn.Dropout(dropout)
        self.head = nn.Linear(dim, 3)
        self.primes = [1, 131, 17161, 2248091]

    def forward(self, ids):
        mask = (ids != 0).long()
        feats, valids = [], []
        T = ids.shape[1]
        for oi, n in enumerate(self.orders):
            if T - n + 1 <= 0:
                continue
            h = torch.zeros(ids.shape[0], T - n + 1, dtype=torch.long)
            ok = torch.ones(ids.shape[0], T - n + 1, dtype=torch.long)
            for j in range(n):
                h = h + ids[:, j:T - n + 1 + j] * self.primes[j]
                ok = ok * mask[:, j:T - n + 1 + j]
            h = (h % self.B) + oi * self.B
            feats.append(h); valids.append(ok)
        h = torch.cat(feats, 1); ok = torch.cat(valids, 1).float()
        e = self.emb(h) * ok.unsqueeze(-1)
        pooled = e.sum(1) / ok.sum(1, keepdim=True).clamp(min=1)
        return self.head(self.drop(pooled))


def build(spec):
    kind = spec["kind"]
    if kind == "cnn":
        return CNN(spec.get("ch", 64), spec.get("emb"), tuple(spec.get("kernels", (3, 5, 3))), spec.get("dropout", 0.1))
    if kind == "tf":
        return TinyTransformer(spec.get("d", 64), spec.get("layers", 2), spec.get("heads", 4), spec.get("dropout", 0.1))
    if kind == "gru":
        return BiGRU(spec.get("hidden", 64), spec.get("emb", 32), spec.get("dropout", 0.1))
    if kind == "hash":
        return HashBag(spec.get("buckets", 8192), spec.get("dim", 16), dropout=spec.get("dropout", 0.1))
    raise ValueError(kind)


def batches(X, y, bs, rng, shuffle=True):
    n = len(y)
    lens = (X != 0).sum(1)
    idx = rng.permutation(n) if shuffle else np.arange(n)
    chunk = bs * 50
    out = []
    for s in range(0, n, chunk):
        c = idx[s:s + chunk]
        c = c[np.argsort(lens[c], kind="stable")]
        for b in range(0, len(c), bs):
            out.append(c[b:b + bs])
    if shuffle:
        rng.shuffle(out)
    return out


@torch.no_grad()
def logits_of(model, X, bs=4096):
    model.eval()
    outs = []
    for s in range(0, len(X), bs):
        xb = torch.from_numpy(X[s:s + bs].astype(np.int64))
        outs.append(model(xb).numpy())
    return np.concatenate(outs)


def log_softmax_np(z, T=1.0):
    z = z.astype(np.float64) / T
    m = z.max(1, keepdims=True)
    return z - (m + np.log(np.exp(z - m).sum(1, keepdims=True)))


def train(spec, hp, D, seed=0, verbose=True, eval_every=0):
    torch.manual_seed(seed); np.random.seed(seed)
    rng = np.random.RandomState(seed)
    model = build(spec)
    opt = torch.optim.AdamW(model.parameters(), lr=hp["lr"], weight_decay=hp.get("wd", 0.01))
    epochs, bs = hp["epochs"], hp["bs"]
    # steps per epoch (approx from a dry generation)
    Xs, ys, _, _ = dd.make_split(D, "train", seed * 1000 + 1, prefix_p=hp.get("prefix_p", 0.35))
    steps_per_epoch = math.ceil(len(ys) / bs)
    total = epochs * steps_per_epoch
    warm = max(1, int(0.03 * total))
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: min(1.0, (s + 1) / warm) * (0.5 * (1 + math.cos(math.pi * min(1.0, s / total))) * 0.98 + 0.02))
    ls = hp.get("ls", 0.0)
    step = 0
    t0 = time.time()
    hist = []
    for ep in range(epochs):
        if ep > 0:
            Xs, ys, _, _ = dd.make_split(D, "train", seed * 1000 + 1 + ep, prefix_p=hp.get("prefix_p", 0.35))
        model.train()
        tot, cnt = 0.0, 0
        for bi in batches(Xs, ys, bs, rng):
            xb = torch.from_numpy(Xs[bi].astype(np.int64))
            # trim padding
            ml = int((xb != 0).sum(1).max())
            xb = xb[:, :ml]
            yb = torch.from_numpy(ys[bi])
            loss = F.cross_entropy(model(xb), yb, label_smoothing=ls)
            opt.zero_grad(); loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step(); sched.step(); step += 1
            tot += loss.item() * len(bi); cnt += len(bi)
        hist.append(tot / cnt)
        if verbose:
            print(f"   ep{ep+1}/{epochs} loss={tot/cnt:.4f} t={time.time()-t0:.0f}s", flush=True)
    return model, dict(train_s=time.time() - t0, loss_hist=hist)


def full_eval(model, name, with_prefix=False, with_tail=False, temperature=True):
    mat = hs.test_material("test")
    val = hs.test_material("val")
    lg_val = logits_of(model, val["X"])
    T = ek.fit_temperature(lg_val, val["y"]) if temperature else 1.0
    lg = logits_of(model, mat["X"])
    res = hs.evaluate(log_softmax_np(lg), mat, name)
    res["T"] = float(T)
    cal = hs.evaluate(log_softmax_np(lg, T), mat, name + "+T")
    res["ece_T"] = cal["ece"]; res["nll_T"] = cal["nll"]
    if with_prefix:
        pc = {}
        for n in (2, 3, 4, 5, 6, 8):
            pm = hs.prefix_material(mat, n)
            pl = log_softmax_np(logits_of(model, pm["X"]), T)
            pr = hs.evaluate(pl, dict(y=pm["y"], full_len=pm["full_len"], w=pm["w"]), f"prefix{n}")
            pc[n] = dict(n=int(len(pm["y"])), acc_type=pr["acc_type"], acc_tok=pr["acc_tok"],
                         en2ru_R1e3=pr["en2ru"]["fpr0.001"]["recall_tok"], en2ru_R1e2=pr["en2ru"]["fpr0.01"]["recall_tok"],
                         ru2en_R1e3=pr["ru2en"]["fpr0.001"]["recall_tok"], ru2en_R1e2=pr["ru2en"]["fpr0.01"]["recall_tok"])
        res["prefix"] = pc
    if with_tail:
        tail = hs.test_material("test", tail=True)
        tl = log_softmax_np(logits_of(model, tail["X"]), T)
        rt = hs.evaluate(tl, tail, name + "-tail")
        res["tail_acc_type"] = rt["acc_type"]; res["tail_acc_by_len"] = rt["acc_by_len"]
    return res


def export_onnx(model, path):
    model.eval()
    dummy = torch.zeros(1, L, dtype=torch.long)
    dummy[0, :8] = torch.tensor([95, 10, 20, 30, 40, 50, 60, 96])
    torch.onnx.export(model, dummy, path, input_names=["ids"], output_names=["logits"],
                      dynamic_axes={"ids": {0: "b"}, "logits": {0: "b"}}, opset_version=17, dynamo=False)


def ort_latency(path, runs=3000, warm=300, threads=1, seq=None):
    import onnxruntime as ort
    so = ort.SessionOptions()
    so.intra_op_num_threads = threads
    so.inter_op_num_threads = 1
    so.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    sess = ort.InferenceSession(path, so, providers=["CPUExecutionProvider"])
    x = np.zeros((1, L), dtype=np.int64)
    x[0, :9] = [95, 10, 20, 30, 40, 50, 60, 70, 96]
    for _ in range(warm):
        sess.run(None, {"ids": x})
    ts = []
    for _ in range(runs):
        t = time.perf_counter()
        sess.run(None, {"ids": x})
        ts.append((time.perf_counter() - t) * 1e6)
    ts = np.array(ts)
    return dict(p50=float(np.percentile(ts, 50)), p95=float(np.percentile(ts, 95)), p99=float(np.percentile(ts, 99)))
