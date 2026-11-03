# Layout corrector (RU <-> EN): specification, reference implementation, experiments

Work product of the specification project for a Punto Switcher-style wrong-layout corrector
(a ~43k-parameter key-token classifier + a deterministic key table instead of a generative LLM).
Current state: specification **v3.1** with a tested reference engine. There are no operating-system adapters,
no real calibration or acceptance data and no device measurements yet (see `spec/CHANGELOG_v3.1.md`, "What v3.1 does not prove").

| Path | What it is |
|---|---|
| `spec/TZ_layout_correction_v3.md` | The technical specification v3.1 (English), Markdown export of the working document. The living copy is the Claude Docs artifact; this file is a snapshot (revision in `WORKLOG.md`). |
| `spec/CHANGELOG_v3.1.md` | What changed from v3 to v3.1, per finding, with the evidence level of each fix. |
| `spec/FIX_AND_AUDIT_PLAN_v3.1.md`, `AUDIT_REVIEW_*`, `OPTIMIZATION_REVIEW_*` | The findings, the plan (revision 1.3, after three external reviews) and the audit lanes. |
| `reference/lfengine.py` | Reference (oracle) implementation, standard library only, Python 3.9+. Its code is the normative text of spec sections 20.2 to 20.11 and 20.14. |
| `reference/vectors.py`, `vectors_out.json` | Golden test vectors (spec 20.12): `python3 vectors.py` regenerates them. |
| `reference/conformance.py` | Property, negative and fault-injection tests (spec 20.13). Run in `reference/`: `python3 conformance.py` and `python3 -O conformance.py` (same number of checks). |
| `reference/test_ref.py` | Behaviour tests of the key tables. `python3 test_ref.py`. |
| `audit/` | Audit reports: L3 mutation testing and fuzzing, L4 platform API cards, L6 EV-1 simulation. |
| `experiments/` | Feasibility experiments behind spec section 18 (they need wordfreq and PyTorch; result files are not included). |
| `inputs/` | The three original expert drafts the specification reworks. |
| `WORKLOG.md` | Working notes: decisions taken, audit status, what remains. |
