# Layout corrector (RU <-> EN): specification, reference implementation, experiments

Work product of the specification project for a Punto Switcher-style wrong-layout corrector
(a ~43k-parameter key-token classifier + a deterministic key table instead of a generative LLM).

| Path | What it is |
|---|---|
| `spec/TZ_layout_correction_v3.md` | The technical specification (English), Markdown export of the working document. The living copy is the Claude Docs artifact; this file is a snapshot (revision noted in `WORKLOG.md`). |
| `reference/lfengine.py` | Reference (oracle) implementation of the deterministic parts: key tables, tokens, candidate segmentation, shape guards, calibration/priors, decision policy, event machine, manual conversion, EV-1 statistic, Witten-Bell baseline, LFB1/LFL1/LFW1 formats. Standard library only, Python 3.9+. Normative for spec section 20. |
| `reference/gen_vectors.py`, `vectors.json`, `vectors.txt` | Golden test vectors generated from the oracle. Note: the vectors of the spec are being re-synchronised with the code (see `WORKLOG.md`). |
| `reference/test_engine.py`, `test_ref.py` | Property and behaviour tests. Run from `reference/`: `python3 test_engine.py && python3 test_ref.py`. |
| `reference/lfref.py` | Earlier, smaller oracle (kept for history). |
| `experiments/` | Feasibility experiments behind spec section 18 (layouts, data, n-gram baseline, CNN/GRU/Transformer, harness). They need word lists (wordfreq) and PyTorch. Result files and checkpoints are not included. |
| `inputs/` | The three original expert drafts the specification reworks. |
| `WORKLOG.md` | Working notes: decisions taken, audit status, what remains. |

Status: work in progress. See `WORKLOG.md` for open items.
