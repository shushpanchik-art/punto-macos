import sys, os, json, time, copy
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, torch
import nn as N, harness as hs, data as dd

OUT = "results.jsonl"
done = set()
if os.path.exists(OUT):
    for line in open(OUT):
        done.add(json.loads(line)["name"])

D = hs.get_data()
BASE_HP = dict(lr=2e-3, bs=512, epochs=8, wd=0.01, ls=0.0, prefix_p=0.35)
os.makedirs("ckpt", exist_ok=True)


def run(name, spec, hp_over=None, seed=0, data=None, tail=False, latency=True, save=False):
    if name in done:
        print("skip", name, flush=True)
        return
    hp = dict(BASE_HP); hp.update(hp_over or {})
    print(f"=== {name} spec={spec} hp={hp} seed={seed}", flush=True)
    model, info = N.train(spec, hp, data or D, seed=seed, verbose=False)
    res = N.full_eval(model, name, with_prefix=True, with_tail=tail)
    rec = dict(name=name, spec=spec, hp=hp, seed=seed, params=N.nparams(model), train_s=info["train_s"], loss_hist=info["loss_hist"], eval=res)
    if latency:
        try:
            path = f"ckpt/{name}.onnx"
            N.export_onnx(model, path)
            rec["latency_us"] = N.ort_latency(path, runs=1500, warm=200)
            rec["onnx_kb"] = os.path.getsize(path) / 1024
        except Exception as e:
            rec["latency_err"] = repr(e)
    if save:
        torch.save(model.state_dict(), f"ckpt/{name}.pt")
    open(OUT, "a").write(json.dumps(rec, default=float) + "\n")
    print(hs.summarize(res), f"| params={rec['params']} train={info['train_s']:.0f}s lat={rec.get('latency_us')}", flush=True)
    done.add(name)


# ---- Stage 1: architecture comparison at ~40-130K params
run("cnn_c64", dict(kind="cnn", ch=64), tail=True, save=True)
run("gru_h64", dict(kind="gru", hidden=64), tail=True)
run("tf_d64_l2", dict(kind="tf", d=64, layers=2), tail=True)
run("hash_b2048_d16", dict(kind="hash", buckets=2048, dim=16), tail=True)

# ---- Stage 2: CNN size sweep
for ch in (4, 8, 16, 24, 32, 48, 96, 128):
    run(f"cnn_c{ch}", dict(kind="cnn", ch=ch), tail=True, save=(ch in (16, 32, 128)))

# ---- Stage 3: hyper-parameter ablations on cnn_c64
for lr in (3e-4, 1e-3, 3e-3, 1e-2):
    run(f"abl_lr{lr:g}", dict(kind="cnn", ch=64), dict(lr=lr))
run("abl_bs128", dict(kind="cnn", ch=64), dict(bs=128))
run("abl_bs2048", dict(kind="cnn", ch=64), dict(bs=2048))
run("abl_v1recipe_lr2e-4_bs128_ls0.1_ep20", dict(kind="cnn", ch=64), dict(lr=2e-4, bs=128, ls=0.1, epochs=20))
run("abl_v3recipe_lr3e-4_bs256_ep15", dict(kind="cnn", ch=64), dict(lr=3e-4, bs=256, epochs=15))
for ls in (0.05, 0.1):
    run(f"abl_ls{ls:g}", dict(kind="cnn", ch=64), dict(ls=ls))
run("abl_noprefix", dict(kind="cnn", ch=64), dict(prefix_p=0.0))
run("abl_prefix0.6", dict(kind="cnn", ch=64), dict(prefix_p=0.6))
for ep in (2, 4, 16):
    run(f"abl_ep{ep}", dict(kind="cnn", ch=64), dict(epochs=ep))
run("abl_wd0", dict(kind="cnn", ch=64), dict(wd=0.0))
run("abl_wd0.1", dict(kind="cnn", ch=64), dict(wd=0.1))
run("abl_drop0", dict(kind="cnn", ch=64, dropout=0.0))
run("abl_drop0.3", dict(kind="cnn", ch=64, dropout=0.3))
run("abl_k3_3_3", dict(kind="cnn", ch=64, kernels=(3, 3, 3)))
run("abl_k3_5_7_3_layers4", dict(kind="cnn", ch=64, kernels=(3, 5, 7, 3)))
run("abl_k5_5", dict(kind="cnn", ch=64, kernels=(5, 5)))
for sd in (1, 2):
    run(f"seed{sd}_cnn_c64", dict(kind="cnn", ch=64), seed=sd)

# ---- Stage 4: training-data scaling (fraction of training word types)
for frac in (0.05, 0.1, 0.25, 0.5):
    lim = int(80 * frac)
    Dsub = {k: v for k, v in D.items()}
    Dsub["en"] = [(w, z) for w, z in D["en"] if dd.split_of(w) != "train" or dd.h(w, 100) < lim]
    Dsub["ru"] = [(w, z) for w, z in D["ru"] if dd.split_of(w) != "train" or dd.h(w, 100) < lim]
    Dsub["other"] = [(s, wt) for s, wt in D["other"] if dd.split_of(s) != "train" or dd.h(s, 100) < lim]
    run(f"data_frac{frac:g}", dict(kind="cnn", ch=64), data=Dsub, latency=False)

# ---- Stage 5: bigger models
run("cnn_c192", dict(kind="cnn", ch=192), dict(epochs=6), tail=True, save=True)
run("tf_d128_l4", dict(kind="tf", d=128, layers=4), dict(epochs=4), tail=True)

# ---- Stage 6: latency-only for untrained heavy configs (random weights)
lat = {}
if "latency_only" not in done:
    for nm, spec in [("tf_d96_l2", dict(kind="tf", d=96, layers=2)), ("tf_d128_l2", dict(kind="tf", d=128, layers=2)),
                     ("tf_d128_l4", dict(kind="tf", d=128, layers=4)), ("tf_d256_l4_v1spec", dict(kind="tf", d=256, layers=4, heads=8)),
                     ("cnn_c256", dict(kind="cnn", ch=256)), ("gru_h128", dict(kind="gru", hidden=128))]:
        m = N.build(spec)
        p = f"ckpt/lat_{nm}.onnx"
        N.export_onnx(m, p)
        lat[nm] = dict(params=N.nparams(m), onnx_kb=os.path.getsize(p) / 1024, **N.ort_latency(p, runs=800, warm=100))
        print("latency-only", nm, lat[nm], flush=True)
    open(OUT, "a").write(json.dumps(dict(name="latency_only", lat=lat)) + "\n")
print("SUITE DONE", flush=True)
