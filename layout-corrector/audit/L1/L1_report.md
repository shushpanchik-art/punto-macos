# L1. Blind re-implementation from the text (Node.js): report, round 1

**Status: PARTIAL. This line is not closed.** Round 1 was run on a reduced input, the agent that ran it stopped at a usage limit
before it wrote its own report, and this report was assembled afterwards from its code and its output
(`run_output.txt`, reproducible with `node run_vectors.js` in this folder). Where the report says "the agent assumed", the source is the
comment in the agent's code; each finding was re-checked against the specification text by the author of this report, who is
not independent of the specification. A second round is listed at the end.

## What was done

* Input: `spec_without_code.md` = sections 4, 5, 6, 10, 11, 13, 19 and 20 of the specification (rev 287) with **every code block of
  section 20 removed**: `lfengine.py`, `conformance.py` **and `vectors.py`**. Sections 7 (including 7.7, the baseline), 8, 9, 12 and 14 to 18 were removed as background.
  The expected JSON of 20.12 stayed.
* Task (`TASK.md`): re-implement the deterministic parts in plain JavaScript (no packages) and recompute every key of the expected JSON
  from the inputs that the JSON and the prose give; report where the text did not allow it.
* Result: `node run_vectors.js` (this folder): **292 of 309 entries, 25 of 29 keys fully matching.**

| key | entries matching / total | how the inputs were obtained |
|---|---|---|
| `render`, `caps`, `caps_all`, `manual`, `priors`, `lambdas`, `poisson`, `modes`, `outcome` | all (10, 4, 48, 6, 6, 6, 6, 14, 6) | the row holds the inputs |
| `fnv` | 5 / 5 | the hash is defined in the prose of 20.10 (`FNV-1a-64(0xC0+k ‖ context bytes)`); one byte per token was assumed and confirmed by the vector |
| `cands` | 14 / 14 | column 2 is the *target* layout; this is not documented (finding L1-1) |
| `guards` | 8 / 8 | column 2 is the *active* layout (a different meaning from `cands`); the suffix list is not printed in the prose (L1-4) |
| `scores`, `wb_score` | 6 / 6, 1 / 1 | needs temperature 1 and a class mix of 38/40/22, neither printed as a number in the prose (L1-4) |
| `decide` | 13 / 13 | columns 4 to 6 (state, run credit above 0, exception present) are not documented (L1-1) |
| `prefix`, `tok25` | 1 / 1 each | the input (`ghb`; a 25-key word) is not in the JSON; guessed from the output (L1-3) |
| `ev1` | 7 / 7 | the inputs live in the name of the case; `m` floored at 1 for no error (L1-2) |
| `trace_run`, `trace_undo`, `scen`, `undo`, `hook`, `tx`, `fingerprint` | 6, 7, 11, 17, 21, 57, 4 (all) | stimuli designed from the names of the cases and the prose of the traces; the fault names of the transaction were interpreted (L1-5). **Weaker evidence:** the stimuli were fitted to the expected output |
| `lfl` | 6 / 8 | the hash keys and the membership; the 84 bytes and the SHA of the file need the format, which was in a removed code block |
| `wb` | 1 / 9 | only `logits = logp + ln(class mix)` could be checked: the Witten-Bell algorithm is in 7.7, which was removed from the input |
| `lfw` | 0 / 5 | the toy weights and the header layout were in the removed code of 20.11 |
| `cal_json` | 0 / 2 | the schema LFC1 and the serialisation were in the removed code of 20.5 |

The four keys that do not match are **not** defects of the specification: they need exactly the sections and code that the input
left out. They are the reason why the line stays open.

## Findings

| id | finding | quote and place | assumption of the agent | proposed fix | severity | status |
|---|---|---|---|---|---|---|
| L1-1 | The meaning of the columns of the rows is described only for the keys of 20.14 | 20.12: "The keys of 20.14 are lists of cases. An entry of tx is: ..." (nothing for `render`, `cands`, `guards`, `decide`, `scores`, `undo`, ...). The second column is the target layout in `cands` and the active layout in `guards` | read from the data | a table of row formats in 20.12 | MAYBE (the generator `vectors.py` defines them, and was not in the input) | **fixed, rev 295**: the table "Row formats of the keys of 20.2 to 20.11" |
| L1-2 | The EV-1 bound for no false correction is undefined by the text | 11.3, item 3: "`U(c) · m / n` ≤ 1e-4" with `m` the largest cluster; for `c` = 0 there is no cluster | `m` floored at 1 (the vector shows 3e-05 for n = 100,000) | one sentence | CERTAIN for the text (a zero would give bound 0) | **fixed, rev 295**: 11.3 item 3 and the table |
| L1-3 | What `tokens` does for more than 20 keys is only in the code | 20.12 table: "the 20-key limit"; no sentence says that `BOS` and the first 20 keys are kept and that a truncated word gets no `EOS` | the length 21 was pinned; the rule guessed | one sentence | MAYBE | **fixed, rev 295** (row `tok25`) |
| L1-4 | The values of the fixture are not printed in the prose | 20.5: "`example_cal` is the set of starting values of 10.1 to 10.3 and the fixture of every vector below"; 10.2 gives "about 38% EN, 40% RU and 22% OTHER"; the temperature 1.0, the example lexicons and the suffix list of 20.4 ("The suffix list is the starting list of the first release") are not printed | T = 1, mix 38/40/22, lexicons from the words of the vectors, suffix list guessed | none needed: 20.1 makes the code blocks normative and they print the fixture | MAYBE | **accepted by design**; a re-implementation in another language reads the code block |
| L1-5 | The meaning of the fault names of the transaction (`partial`, `applied_error`, `autocorrect`, `ignored`, `spill`, `user:c`, `key`) is in the docstring of `SimField`, not in the prose of 20.14 | 20.12: "faults (operation:k means the k-th call of that operation)" | inferred from the names and from the final texts; all 57 rows then matched | list the fault names in the prose of 20.14 | MAYBE | **open (P3)**: the docstring is normative; a list in the prose would help |
| L1-6 | Not a finding about the text: the input did not contain `vectors.py`, 7.7 and the code of 20.2 to 20.11, so inputs had to be guessed and four keys could not be reached | `TASK.md` | | round 2 with `vectors.py` and section 7.7 included | design of the test | **open** |

No contradiction between two sentences of the text was found in this round. No rule had to be fitted to the numbers of the vectors for
the keys that carry their inputs in the row (`render`, `caps`, `caps_all`, `manual`, `priors`, `lambdas`, `poisson`, `fnv`, `modes`,
`outcome`, `scores`, `decide`, `guards`, `cands`).

## What this does and does not show

* It shows that a second program, written without the reference code, agrees with the reference on the algorithmic keys whose inputs are
  in the row, and that the prose of sections 5, 10, 13 and 20 is enough to reproduce them, apart from the points above.
* It does **not** show that the baseline model, the three binary formats and the calibration JSON can be re-implemented from the text:
  those keys were not reached because their sources were withheld.
* The seven keys with designed stimuli are weaker evidence than the rest, because the stimuli were built to produce the expected rows.

## Round 2 (open)

Input: the same file **plus `vectors.py`** (the definition of every input) **and section 7.7**; the agent re-implements `lfengine.py`
from the prose and runs the vectors from `vectors.py` translated into the same calls. Expected: the four keys above reachable; every
remaining guess becomes a finding or disappears. Stop rule: two rounds. It needs a fresh agent run; round 1 was interrupted by the
usage limit, and the line is not to be called closed until round 2 is done or the product owner accepts round 1.
