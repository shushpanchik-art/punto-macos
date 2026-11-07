# Keyboard Layout Auto-Correction Model — Technical Specification v3.1

Oct 19, 2026 · @Thomas


## 4. Scope, assumptions and conventions

The product is an on-device tool that notices a word typed on the wrong layout (Russian vs English) and replaces it with the same keys read on the other layout, as Punto Switcher does. The scope below fixes what is in the first release and what is deliberately not.

### 4.1 In scope

- Language pair RU ↔ EN: US QWERTY and Russian ЙЦУКЕН (Windows "Russian", macOS "Russian - PC" (the macOS layout "Russian" is not supported in the first release); Linux, deferred to a later release (13.7): XKB `ru`). The layout-pair table is a parameter, so further pairs can be added without changing the architecture.
- Automatic replacement of the last word when Space is typed; optional early detection inside a word (off by default).
- Manual convert hotkey, undo, learned exceptions, per-application and per-field blacklists.
- Fully local inference. No network call is allowed on the typing path.
- Training, evaluation and export pipeline with a reproducible report (sections 8 to 12 and 15).

### 4.2 Out of scope for the first release

- Any text generation, spell correction, autocomplete, transliteration or sentence rewriting.
- More than two languages, composed scripts (Korean, Chinese IME) and layouts that are not a key-for-key permutation of each other.
- System-wide operation on iOS and Android: third-party apps cannot hook another keyboard's key events there. The same model can ship inside an own keyboard or IME as a separate track, where the app itself produces the key events.

### 4.3 Assumptions (change them and the numbers change)

| Assumption | Default | Why it matters |
| --- | --- | --- |
| Primary platforms | macOS 13+ (Apple Silicon and Intel) and Windows 10/11 x64; Linux is not in the first release (13.7) | Fixes the reference devices for latency tests |
| Development hardware | Apple M1 Max, 32 GB unified memory (stated by the requester) | A model of 50 to 300K parameters trains in minutes on it; no GPU cluster and no LLM fine-tuning stack is needed |
| Typing profile | Bilingual user, mostly prose and chat, some code | Sets the share of `OTHER` tokens (assumed about 6% of tokens) |
| Wrong-layout rate π | 0.3% to 3% of words, unmeasured | Drives the false-positive budget (section 5.5) |
| Default mode | Decide when Space is typed | Safer undo, no flicker |

### 4.4 Conventions

MUST, SHOULD and MAY follow RFC 2119. Requirement ids are `<area>-<n>`: `MD` model, `DT` data, `TR` training, `CA` calibration and policy, `EV` evaluation, `DP` deployment, `RT` runtime behaviour, AP the application layer, CT conformance of the reference code. Numbers marked *measured* come from the feasibility experiments in section 18, which used public word-frequency lists as proxy data; they justify the choices but do not replace acceptance testing on real typing data. "Word" always means a word candidate as defined in section 5.3, and "p95" means the 95th percentile of at least 10,000 warm calls.

**Normative and informative text.** Normative: every requirement table (MD, DT, TR, CA, EV, DP, RT, AP, CT), the rules stated in sections 4 to 16, and section 20 (reference code, formats and test vectors). When prose and the reference code disagree, the code and its vectors win, and the prose is a defect to be fixed. Informative: sections 1 to 3 (summary, answers, prior art), 17 (review of the drafts), 18 (experiments) and 19 (appendices). Informative material justifies the normative choices; none of its numbers is a requirement unless a normative row repeats it, and each experimental figure carries an evidence grade (18.1). An option marked optional, phase 2, deferred or ablation is not part of the first release and MUST NOT be enabled by default. Terminology: a *layer with parameters* is the embedding, each convolution or the linear head; pooling has none, so the reference network has five layers with parameters.


## 5. Problem formulation

The task is binary at heart: for the word just typed, decide whether the user meant the other language, and only then apply a fixed key-position table. Everything below makes that decision well-posed.

### 5.1 Input is a key sequence, not text

Each keystroke event carries: physical key position `k` (one of 47 printable keys of the main block), raw Shift state, raw Caps Lock state, active layout id, and timestamp. The model input is the sequence of key tokens `1 + 2k + s` (94 tokens), where the shift bit is `s = raw_shift XOR (caps AND k ∈ L)` and `L` is the set of the 33 keys that are a letter in at least one of the two layouts (the Caps Lock bullet below and 20.2 define it exactly), plus PAD, BOS and EOS: a vocabulary of 97.

- **Why keys.** `ghbdtn` typed on an English layout and `привет` typed on a Russian layout are the same keys. With keys as input, the two readings of a word (EN and RU) are always available and exactly aligned, and the layout tables carry no learnable burden.
- **Why not characters.** A character-based model must memorise the permutation (`g→п`) for every context, wasting capacity, and its labels `en` / `en_from_ru` differ only by an input the model never sees directly.
- **Caps Lock.** Store raw Shift and Caps separately, and apply two different rules. (1) **The token** is layout-independent and is computed by one rule for both readings: `s = raw_shift XOR (caps AND k ∈ L)`. `L` has 33 keys: the 26 letter keys of the English layout and the seven keys that are letters only on the Russian layout (the keys of `` ` `` `[` `]` `;` `'` `,` `.`, ids 0, 23, 24, 35, 36, 44, 45). With Caps Lock on, the Russian reading capitalises exactly these keys, so the token carries the case the word would have as Russian text. On the English reading these seven keys do not change with Caps Lock, so the token bit differs there from the surface shift; the training data (8.3) and the vectors of 20.12 use the same function, so the model has seen it, and a Caps Lock vector exists for each of the seven keys. (2) **Rendered text** applies Caps Lock per target layout: `raw_shift XOR (caps AND the key is a letter in that layout)`. On an English layout Caps Lock does not capitalise `;` `'` `[` `]` `,` `.`, but on a Russian layout it capitalises `Ж Э Х Ъ Б Ю`. The mapper re-applies Caps Lock per target layout (`render`, 20.2); the token is never used to render text.

### 5.2 Model output and action

The model estimates the **intended text type** from keys alone:

| Class | Meaning | Examples |
| --- | --- | --- |
| `EN` | English word, any case | `hello`, `Hello`, `HELLO`, names, brands |
| `RU` | Russian word, any case | `привет`, `Привет`, names, acronyms |
| `OTHER` | Latin-script text that is not an English word: code, identifiers, URLs, e-mails, paths, hashes, transliteration, key-mashing. Its behaviour is defined only by the table below, as a pair with the active layout | `kubectl`, `--dry-run`, `user@example.com`, `privet`, `asdfgh` |

The **action** is derived outside the model from the active layout `A`:

- `KEEP` if the active layout `A` is English and the predicted class is `EN` or `OTHER`, or if `A` is Russian and the predicted class is `RU`.
- `CONVERT` to the other layout if `A` is English and the predicted class is `RU`, or if `A` is Russian and the predicted class is not `RU` (that is `EN` or `OTHER`), and the calibrated confidence of that reading clears the length-dependent threshold (section 10). The asymmetry is deliberate. `OTHER` is Latin-script technical text by construction, so typed on a Russian layout it is a wrong-layout string, and `EN` and `OTHER` convert to the same Latin output. The decision is therefore "Russian or not" in both directions (measured in section 18.8). Russian-intended technical strings (acronyms, numbers with units, Cyrillic file names) are not in `OTHER`; they MUST be added to the protected regression set of EV-2 and are also covered by the guards of section 13.1.
- `ABSTAIN` (a policy outcome, not a trained class) if confidence is insufficient. It behaves exactly like `KEEP`.

This replaces the five classes of the earlier draft (`en`, `ru`, `en_from_ru`, `ru_from_en`, `neutral`) and the four actions of the third draft. The layout-conditioned classes duplicate information the policy already has, and `ABSTAIN` cannot be labelled in data: it is a function of confidence, so training it as a class would require arbitrary labels.

**Behaviour by content type.** A class name decides nothing alone: the outcome is the pair (active layout, content). The expected outcomes are below, with the reason codes that the reference code of section 20.6 returns. "Decided by the scorer" means the calibrated score of 10.1 against the threshold `λ` of 10.3.

| Content (intended text) | Typed on its own layout | Typed on the wrong layout | Decided by |
| --- | --- | --- | --- |
| English word: `hello` | Active English: KEEP | Active Russian, typed `руддщ`: CONVERT to `hello` when the score clears `λ` | `lexicon_active` protects correct typing; otherwise the scorer |
| Russian word: `привет` | Active Russian: KEEP | Active English, typed `ghbdtn`: CONVERT to `привет` when the score clears `λ` | The same |
| Command or identifier word: `kubectl`, `git` | Active English: KEEP | Active Russian, typed `лгиусед`: CONVERT to `kubectl` when the score clears `λ`. EN and OTHER convert to the same Latin text | The scorer; there is no separate action for OTHER |
| Transliteration: `privet`, `spasibo` | Active English: KEEP. A user who types transliteration on the English layout is never changed | Active Russian, typed `зкшмуе`: CONVERT to `privet` when the score clears `λ` | The scorer |
| URL, e-mail, file or domain name: `github.com`, `user@example.com` | KEEP | KEEP. Never converted automatically; the user converts it with the hotkey | Shape guard (`shape_url`, `shape_email`, `shape_dotted`), or `no_eligible_candidate` because `.` and `@` are not letters on the target layout |
| camelCase and key walks: `MyVariable`, `asdfgh`, `фывапр` | KEEP | KEEP | `shape_camel`, `shape_keywalk` |
| A digit, `_`, `-`, `/` or `\` inside the word | KEEP | KEEP | `no_eligible_candidate` |
| Word or acronym of the active language (lexicon or acronym list): `hello`, `SQL`, `привет`, `МТС` | KEEP, even when its other reading is a word too | Not applicable | `lexicon_active`, `acronym`. An acronym of the other language typed on the wrong layout is converted only if the scorer clears `λ`; its recall is low and that is accepted |
| One key or two keys | KEEP | KEEP, except under the 2-key rule of 10.4 | `one_key`, `two_key_rule` |
| Keys of two layouts in one word, or a layout change inside the word | Not applicable | The word is dropped: no decision (13.2) | The event machine, not the policy |

### 5.3 Decision unit and word segmentation

The only automatic **decision point** is the Space key. By the time Space is seen it is already in the document, so a conversion never has to hold a key back (13.2). Enter and Tab are not decision points: the application has already acted on them (a message sent, a form submitted), so they are context breaks. A wrong-layout word at the end of a line is therefore converted with the hotkey (13.3). Mid-word (early) decisions are an optional mode with a stricter bar (10.5).

**Segmentation hazard.** Seven keys are letters on the Russian layout but punctuation on the English layout:

| Key (EN) | `` ` `` | `[` | `]` | `;` | `'` | `,` | `.` |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Letter (RU) | ё | х | ъ | ж | э | б | ю |

In a frequency-weighted sample of the top 20,000 Russian words, **20.6% of tokens contain at least one of these seven letters**, 7.1% start with one and 4.2% end with one (section 18). Splitting English-layout text at punctuation, as the second draft's word definition does, would cut about one Russian word in five (`хорошо` is `[jhjij`, `жизнь` is `;bpym`).

**Run and candidate (normative; reference code in section 20.3).** A *run* is the printable keys of the 47-key block typed since the last Space or context break (13.2), at most 64. The seven keys above never split a run. Let `A` be the active layout and `T` the other one. The hypothesis is always "the user meant `T`", so a run has exactly one candidate, not up to three:

1. Read every key as it would be on `T`.
2. If the first key reads on `T` as one of `( [ { " '` and is not a letter on `T`, it is the leading opener (at most one).
3. From the end, peel up to two keys that read on `T` as one of `. , ; : ! ? " ' ) ] }` and are not letters on `T` (the trailing marks). Stop at the first key that is not one.
4. What is left is the core. It must be non-empty and every key in it must be a letter on `T`. Otherwise there is no candidate and the run is KEEP (`no_eligible_candidate`).
5. Only the core is classified: its key tokens are the model input (5.1). The replacement text is the whole run read on `T`, so the opener and the marks go through the layout table and are never copied: `Ghbdtn?` becomes `Привет,` and `Ghbdtn&` becomes `Привет?`.

Because punctuation is judged on `T`, one rule serves both directions. With `T` Russian the seven keys are letters and stay in the core (`[jhjij` is `хорошо`). The sentence-final period of a Russian word typed on the English layout is the key `/`, because the key `.` is the letter `ю` (`ghbdtn/` becomes `привет.`, `ghbdtn.` becomes `приветю`). With `T` English the same keys are punctuation and are peeled (`руддщб` becomes `hello,`).

Golden cases, generated by the reference code (the full set is in section 20.12):

| Typed run | Active layout | Opener | Core | Trailing marks | Result |
| --- | --- | --- | --- | --- | --- |
| `Ghbdtn?` | EN | none | `Привет` | `,` | Classify 6 keys; if CONVERT: `Привет,` |
| `Ghbdtn?!` | EN | none | `Привет` | `,!` | Classify 6 keys; if CONVERT: `Привет,!` |
| `(ghbdtn)` | EN | `(` | `привет` | `)` | Classify 6 keys; if CONVERT: `(привет)` |
| `ghbdtn/` | EN | none | `привет` | `.` | Classify 6 keys; if CONVERT: `привет.` |
| `k.,k.` | EN | none | `люблю` | none | Classify 5 keys; if CONVERT: `люблю` |
| `[jhjij` | EN | none | `хорошо` | none | Classify 6 keys; if CONVERT: `хорошо` |
| `;bpym` | EN | none | `жизнь` | none | Classify 5 keys; if CONVERT: `жизнь` |
| `Ghbdtn,` | EN | none | `Приветб` | none | Classify 7 keys; if CONVERT: `Приветб` |
| `"ghbdtn"` | EN | none | `ЭприветЭ` | none | Classify 8 keys (the quote key is the letter `Э` on `T`); the scorer is expected to keep it |
| `ghb1` | EN | none | none | none | KEEP, `no_eligible_candidate` |
| `руддщ,` | RU | none | `hello` | `?` | Classify 5 keys; if CONVERT: `hello?` |
| `(руддщ)` | RU | `(` | `hello` | `)` | Classify 5 keys; if CONVERT: `(hello)` |
| `руддщб` | RU | none | `hello` | `,` | Classify 5 keys; if CONVERT: `hello,` |
| `руддщ..` | RU | none | none | none | KEEP, `no_eligible_candidate` (the key `.` reads `/` on `T`) |
| `,` | EN | none | `б` | none | KEEP, `one_key` |

Boundary and context cases (the event machine of 13.2, section 20.7):

| Events | Outcome |
| --- | --- |
| `ghbdtn`, Space | One decision on the run `ghbdtn` |
| `ghbdtn`, Enter or Tab, then Space | Enter and Tab are context breaks: the word is not decided |
| `ghbdtn`, Space, Space | One decision; the second Space finds an empty run |
| Backspace inside the word | The last key is removed and the rest is decided at Space |
| `ghb`, manual layout change, `dtn`, Space | The word is dropped: no decision |
| `ghb` typed on one layout and `dtn` on the other | The word is dropped: no decision |
| `ghbdtn` typed, then the layout read at Space differs | KEEP, `layout_changed_at_boundary` |
| 65 or more keys, then Space | KEEP, `overflow` |
| The gate is not ALLOW while the word is typed (13.1) | No key is stored; no decision |

Shifted digit-row symbols also differ between layouts (`@ # $ ^ &` against `" № ; : ?`), so they must go through the same table.

### 5.4 The mapper is data, not code

- Generate layout tables from the OS (`UCKeyTranslate` or NSEvent.characters(byApplyingModifiers:) on macOS as spike S-6 decides, ToUnicodeEx for the layout's HKL on Windows, XKB on Linux) for each supported layout pair, and store them versioned. Hand-typed tables are a test oracle only.
- Verify round trips: for every key and shift state, `map(map(c, A→B), B→A) = c`, with the exceptions listed explicitly. My table check for Windows "Russian" against US QWERTY has 0 round-trip failures over all 94 key states.
- Characters with no counterpart (dead keys, combining marks, emoji, anything outside the 47 keys) make the candidate ineligible: no action.
- macOS "Russian" and "Russian - PC" differ in punctuation placement, so only "Russian - PC" is supported in the first release; Windows, macOS and XKB tables must not be assumed equal, and a layout is accepted only when its fingerprint equals the table (13.7).

### 5.5 Decision rule and why base rates dominate

Wrong-layout words are rare, so a classifier that is 99% accurate on balanced data produces mostly false corrections in use. With wrong-layout prior `π`, recall `R` and false-positive rate `F` on correct words, precision is:

```latex
P = \frac{\pi R}{\pi R + (1-\pi)F}
\qquad\Longrightarrow\qquad
F_{\max} = \frac{\pi R\,(1-P)}{P\,(1-\pi)}
```

Required false-positive rate for precision P at recall R = 0.95:

| Wrong-layout rate π | P = 99% | P = 99.5% | P = 99.9% |
| --- | --- | --- | --- |
| 0.3% of words | 1 in 34,600 | 1 in 69,600 | 1 in 349,000 |
| 1% | 1 in 10,300 | 1 in 20,700 | 1 in 104,000 |
| 3% | 1 in 3,400 | 1 in 6,800 | 1 in 34,000 |
| 10% | 1 in 940 | 1 in 1,900 | 1 in 9,500 |

Two consequences. First, the metric that matters is the false-positive rate on correct words at the 1e-4 to 1e-5 level, not accuracy. Second, the model's calibrated posteriors (temperature scaling first, section 10.1) must be corrected for prior shift: multiply the class probabilities by `π_deploy(y | layout, context) / π_train(y)` and renormalise before thresholding. The deployment prior comes from the active layout (a user who switched to Russian deliberately is probably typing Russian) and from the previous words of the same run.

**Wrong-layout rate is not known.** Public evidence is indirect: about 7.8% of null-result queries in the eBay study, and "more than 1%" of Russian Wikipedia queries by a rough Wikimedia estimate. This specification therefore designs for π between 0.3% and 3% and requires measuring it (section 11).


## 6. System architecture

A keystroke becomes a correction in nine stages (0 to 8), and the network is only one of them. Stage 0 runs before anything is stored.

&#91;embedded content: cascade from keystroke to replacement · 8 stages, latency budget per stage\]

Read the drawing from top to bottom. Stage 0 runs before any key is stored, and stage 3 can veto before any model runs. Stage 6 replaces stage 5 as the scorer only if it passes EV-12; their ensemble is a phase-2 option (section 7.4). Stage 7 turns the scores into CONVERT or KEEP, and only stage 8 touches the user's text. The budgets are those of section 7.5; the figures measured so far are in section 18.7.

| Stage | Output | Specified in | When it fails or is missing |
| --- | --- | --- | --- |
| 0. Context gate | A verdict for the focused element: ALLOW, DENY or UNKNOWN. Only ALLOW lets a key in | 13.1, 13.7, 13.8; RT-2, RT-9, RT-13 | Anything not positively ALLOW is UNKNOWN: nothing is recorded (default deny) |
| 1. Key-event hook | `(key, Shift, Caps, layout id)` events of an ALLOW context in a ring buffer; every key is passed on unchanged and at once | 5.1, 13.2; RT-1, RT-8 | An unhandled error leads to no action (RT-7) |
| 2. Buffer and segmentation | The run since the last Space and its single candidate (opener, core, trailing marks), decided at Space | 5.3, 13.2; RT-14 | A run without an eligible candidate gets no action |
| 3. Guards | A veto: token shape, user exception, cool-down. Secure fields, blacklisted and unknown applications are stage 0 | 13.1; RT-3 | A veto is final; no model output overrides it |
| 4. Hash look-ups | Exception, lexicon and acronym hits; the 2-key allow-list | 10.4, 12.5; DP-5 | A missing lexicon gives MANUAL\_ONLY (13.5) |
| 5. Statistical stage | Trigram log-probabilities for `EN`, `RU`, `OTHER` | 7.7, 18.6; MD-7 | Must work alone; it is the fall-back for stage 6 (13.5) |
| 6. Key-token CNN | Three logits | 7, 9, 12; MD-1 to MD-10 | Missing or invalid weights fall back to stage 5 (13.5, row 3); a load failure leads to no action (DP-8) |
| 7. Calibrated policy | `CONVERT` or `KEEP` (`ABSTAIN` behaves as `KEEP`) | 5.2, 10; CA-1 to CA-11 | A watchdog disables auto mode after 100 consecutive words over budget (13.5, row 9) |
| 8. Replacement | The transaction of 13.2: freeze, gate, match, replace, verify, record undo information | 13.2, 13.3; RT-4, RT-5, RT-7 | Any mismatch is rolled back and the application is quarantined (13.5, row 10) |


## 10. Calibration and decision policy

The classifier is trained to separate three kinds of text; the policy turns its output into a safe action. A correction is made only when the calibrated, prior-corrected probability that the user meant the other language clears a threshold that depends on word length, and every number in that chain is fitted on validation data, never on the test set.

### 10.1 From logits to an action

- **Logits** `z` (3 values: EN, RU, OTHER) from the network, or the class log-posteriors of the statistical stage (section 7.7), which enter the same path. Each scorer has its own temperature and its own threshold table, selected by `kind` (`network` or `ngram`); the two are never mixed.
- **Temperature scaling.** `p = softmax(z / T)`, with one scalar `T` per scorer kind (`network`, `ngram`), fitted on the calibration data by minimum negative log-likelihood. It does not change the arg-max, so it cannot change accuracy. The first release uses the scalar only: a temperature per class is not used, and a calibration package that carries any other shape of `T`, or a `T` that is not finite and positive, is refused whole (CA-9, 20.5). A per-class temperature is a possible later change that would need a new schema version.
- **Prior-shift correction.** `p'(c) ∝ p(c) · π_dep(c) / π_train(c)`, renormalised. `π_train` is the class mix of the training rows. The package D5 stores it as three **integer counts** `pi_train_counts` (EN, RU, OTHER) taken from the build manifest, and the runtime derives `π_train(c) = count(c) / sum(counts)` and checks the stored vector against it (20.5); a vector that does not sum to 1 within 1e-9 is refused. The mix of the proxy experiment was about 38% EN, 40% RU and 22% OTHER, a rounded figure used only as the example of 20.5, because the exact counts of that experiment cannot be recomputed here. `π_dep` is the complete three-class deployment prior, a vector over (EN, RU, OTHER) that sums to 1, for the active layout `A` and the word state (section 10.2). Without this step a classifier trained on a balanced mix converts far too often in real use (section 5.5).
- **Score.** The decision is "Russian or not" in both directions, so the score is a two-way marginal, a log-odds in nats (natural logarithm). Active layout English: `s = ln p'(RU) − ln(p'(EN) + p'(OTHER))`, which is `logit(p'(RU))`. Active layout Russian: `s = ln(p'(EN) + p'(OTHER)) − ln p'(RU)`, which is `logit(1 − p'(RU))`. Here `logit(p) = ln(p / (1 − p))`. Both are computed from log-probabilities (log-sum-exp) so that values near 1 do not saturate. Scoring the Russian-layout direction as `EN` against `RU + OTHER` instead is the symmetric reading (the target class against all others), and it cut recall by a factor of 2 to 5 at a matched false-positive rate on the rare-word tail, because English words and Latin-script technical strings cannot be told apart from keys alone and are converted by the same action (section 18.8).
- **Decision and units.** CONVERT if `s ≥ λ(kind, direction, bucket)`, where the bucket is the key-count bucket of section 10.3. **Thresholds are stored and compared in nats.** A probability threshold `t` such as 0.999 is converted once, when the table is built, by `λ = logit(t)` (0.999 → 6.907, 0.997 → 5.806, 0.995 → 5.293 nats). The runtime never compares `s` with a probability: the literal test `s ≥ 0.995` would accept a word at a posterior of only 73%, and 5.293 nats is a posterior of 99.5%. The calibration package holds nats only, and a load-time check rejects any threshold outside 4 to 16 nats (CA-9). Otherwise the outcome is ABSTAIN, which behaves as KEEP.
- **Incumbent margin (optional ablation, not in the first release).** A soft form of the dictionary rule of section 10.4: if the as-typed reading is a frequent word of the active language and the converted reading is not an equally frequent word, add a margin of 1 to 2 nats to `λ`. The first release uses the hard rule of section 10.4 instead; this margin is a phase-2 candidate evaluated as an ablation.

### 10.2 Deployment priors

The prior is a probability vector over the three classes, not a single rate. It is built from two measurable numbers: `w`, the probability that the word was typed on the wrong layout, and `o_lat`, the share of `OTHER` among words intended in Latin script. For the active layout `A` the vector over (EN, RU, OTHER) is:

| Active layout `A` | `π_dep` over (EN, RU, OTHER) | Reading |
| --- | --- | --- |
| English | `((1−w)(1−o_lat), w, (1−w)·o_lat)` | A correct word is EN or OTHER; a wrong-layout word is a Russian word typed on the English layout |
| Russian | `(w·(1−o_lat), 1−w, w·o_lat)` | A correct word is RU; a wrong-layout word is Latin-script text (EN or OTHER) typed on the Russian layout |

Starting values, with `o_lat` = 0.25 (OTHER is about 6% of all tokens when about a quarter of the tokens are Latin-script, the assumption of section 4.3):

| Word state | Layout | `w` | `π_dep` (EN, RU, OTHER) | Basis |
| --- | --- | --- | --- | --- |
| `default` | English | 1% | 0.7425, 0.0100, 0.2475 | Inside the 0.3–3% design range (section 5.5) |
| `default` | Russian | 1% | 0.0075, 0.9900, 0.0025 | Same rate |
| `after_switch` | English | 0.3% | 0.7478, 0.0030, 0.2492 | The user switched layouts by hand, so the layout is deliberate |
| `after_switch` | Russian | 0.3% | 0.0023, 0.9970, 0.0008 | Same |
| `run` | English | 25% | 0.5625, 0.2500, 0.1875 | Wrong-layout typing comes in runs of several words |
| `run` | Russian | 25% | 0.1875, 0.7500, 0.0625 | Same |

The `run` state lowers the evidence needed by 3.5 nats (the log-odds of 25% against 1%), which is why it is the part that must not be allowed to feed itself.

**Word state and its transitions.** The runtime keeps two items per typing session: the run credit `c` (an integer from 0 to 3) and the flag `after_switch`. The state is computed at the decision point (Space, section 5.3), before the policy runs: `run` if `c > 0`, else `after_switch` if the flag is set, else `default`. After the decision:

- CONVERT decided in state `default` or `after_switch`: `c := 3`.
- CONVERT decided in state `run`: `c := max(c − 1, 0)`.
- KEEP with reason `user_exception`, `acronym`, `lexicon_active` or `abstain`: `c := 0`, because the run is over.
- KEEP for any other reason (no candidate, one key, shape guard, 2-key rule, cool-down, overflow, layout changed at the boundary): `c` is unchanged.
- The flag `after_switch` is set by a manual layout change and cleared by the next decision that reaches the policy.
- Reset to `c := 0` by: a manual layout change, any context break (section 13.1), a Backspace before the start of the word, an undo of an automatic correction (which also starts the cool-down), and any stage-0 verdict other than ALLOW.

**Feedback cap.** Only a conversion made without the run prior refills the credit. A wrong automatic correction therefore raises the prior of at most the next three words, a chain of run-assisted conversions cannot renew itself (after three, the next word must clear the default threshold alone), and an undo clears the credit at once. `w` is validated at load time: 0.0005 to 0.5 for every state, and at most 0.3 for `run` (CA-9).

**Estimation.** These are starting points. Before release they are replaced by values measured on the real calibration set R-CAL (section 8.4), never on the locked acceptance set R-ACC. What R-CAL and R-NAT give is an **observed rate, a proxy for the true rate**, not the true rate itself. A *wrong-layout event* is a manual conversion of the last word by the hotkey, recorded with its mode (last word, selection or bulk; section 11.5); only last-word events count, and bulk conversions and selections do not. The denominator is the number of words typed on the same layout in the same context class (application class and layout). The proxy undercounts when the user does not notice a wrong word or converts it later by hand, it overcounts when the hotkey is pressed for another reason, and it depends on the habits of the people in the sample. `w[default]` is therefore the number of last-word events divided by the words typed on that layout, `w[after_switch]` is the same rate for the first word after a manual layout change, and `w[run]` is the probability that a word is wrong-layout given that the previous one was; with a mean run length of `m` words in the data it is `1 − 1/m`. `o_lat` is the OTHER share among Latin-script words. Each estimate is reported with a 90% cluster-bootstrap interval by user. **Which value goes into D5:** `w_ship`, the **lower end** of that interval, clipped to the ranges the load check allows, because a `w` that is too low only costs recall and a `w` that is too high raises false corrections. The point estimate and the upper end appear in the report D6, not in the package. EV-1 is evaluated with `w_ship`; the same evaluation with the point estimate and with the upper end is a stress report, not a gate (11.7). If the upper end of an interval is more than 4 times its lower end, the estimate is not used, the starting value stays, and D6 labels it "default, not estimated". The package D5 stores the numbers `w` and `o_lat`, not free vectors, so that every vector sums to 1, and the table is versioned with the model.

### 10.3 Thresholds by word length and direction

One global constant such as 0.9 is not acceptable: a 3-key word carries far less evidence than a 12-key word, and with label smoothing the maximum attainable probability is below 1 (`0.9 + 0.1/3 = 0.933` for 3 classes at smoothing 0.1), so a fixed 0.9 would mean different things for different training recipes.

| Keys `L` | Starting posterior `t` | Stored threshold `λ = ln(t / (1 − t))`, nats | Notes |
| --- | --- | --- | --- |
| 1 | Never convert | none | One key carries no language evidence |
| 2 | Only through the allow-list rule (10.4) | none | In the proxy data 30–80% of 2-letter words are valid in both languages (section 18) |
| 3–4 | 0.999 | 6.907 | 3-letter words collide in both directions; 4-letter collisions are rare |
| 5–7 | 0.997 | 5.806 | No collisions in the top-20k vocabularies, but names and acronyms still collide |
| 8 and more | 0.995 | 5.293 |  |

The table of the calibration package stores the last column only, per scorer `kind` and direction, and the runtime compares `s` with it (section 10.1).

These are only starting points. The release table is produced by a fixed procedure on the validation set at the deployment mixture:

- Per scorer, direction and length bucket, find the smallest `λ` (in nats) whose token-weighted false-positive rate on R-CAL, at the deployment mixture, is at most the bucket target. The overall target is the rate that gives precision ≥ 99.5% at π = 1% and recall 0.95, which is 1 error in 20,700 correct words (section 5.5).
- Add a safety margin of 0.5 nat for buckets with fewer than 5,000 negative calibration items.
- Freeze the table. Evaluate once on the locked acceptance set R-ACC (section 11).

### 10.4 Priority matrix and short words

At a decision point (Space, section 5.3) the runtime applies the rows below in order, and the first row that matches decides. Rows 1 to 4 belong to the event machine; rows 5 to 12 are the policy function of the reference code (section 20.6). The order is normative: it fixes what happens when the dictionary, the shape guards, the user's exceptions and the scorer disagree.

| # | Condition (first match wins) | Result | Reason code |
| --- | --- | --- | --- |
| 1 | The word was dropped: the layout changed inside it, or a stage-0 verdict other than ALLOW was seen while it was typed (13.1) | No decision | none |
| 2 | More than 64 keys since the last boundary | KEEP | `overflow` |
| 3 | The layout read at the decision point differs from the layout of the word's keys | KEEP | `layout_changed_at_boundary` |
| 4 | The cool-down after an undo is active (13.3) | KEEP | `cooldown` |
| 5 | No eligible candidate (5.3) | KEEP | `no_eligible_candidate` |
| 6 | The candidate core has 1 key | KEEP | `one_key` |
| 7 | The as-typed core (case-folded, read on the active layout, with its direction) is in the user exception list | KEEP | `user_exception` |
| 8 | A shape guard fires on either reading of the run (13.1) | KEEP | `shape_url`, `shape_email`, `shape_dotted`, `shape_camel`, `shape_keywalk` |
| 9 | The as-typed core is in the acronym list of the active language | KEEP | `acronym` |
| 10 | The as-typed core is in the lexicon of the active language | KEEP | `lexicon_active` |
| 11 | The core has 2 keys | CONVERT only under the 2-key rule below, otherwise KEEP | `two_key_allow_list`, `two_key_rule` |
| 12 | Anything else: the score `s` against `λ` (10.1) | CONVERT if `s ≥ λ`, otherwise KEEP (ABSTAIN) | `score_above_threshold`, `abstain` |

Three consequences. A word that exists in the active language is never converted automatically, even when its other reading is a word too; the user converts it by hand. This is the hard form of the incumbent idea and it trades a little recall for a smaller false-positive budget; the soft margin of 10.1 is the phase-2 alternative. Words of the *target* language are not an input to the first release: the scorer already encodes them, and feeding the target lexicon into the score would need its own calibration (an option of section 7.4). Unknown words, names and rare forms go to row 12 and are held to the length thresholds.

**Dictionaries.** The lexicon of a language is its 100,000 most frequent case-folded word forms (200,000 hashes in all, section 12.5), built by the D3 script from the sources of section 8.2 and refreshed quarterly. The acronym list of a language holds up to 5,000 entries (all-caps tokens frequent in the corpora, reviewed by hand). The exception list holds the user's own undone words (13.3). All three are tables of 64-bit hashes (DP-5).

**Two-key rule.** A 2-key word is converted only when all of the following hold: the run credit `c` is above 0, which means a previous word of the same run was converted (10.2); the converted word is in the allow-list of about 25 high-frequency function words of the target language; and rows 7 to 10 did not fire. The Russian list is `на не но да по из за то ты мы вы он ли ну во со до от ни же бы`; the English list is `of to in is it on at as be by or an if so do go he we me my no up us`. Everything else is left to the manual hotkey. This keeps 2-key mistakes out of the false-positive budget while still fixing them inside a phrase, which is where they occur.

### 10.5 Early detection (inside a word)

Off by default. It may be enabled only after the gates below pass on the realistic test set, because the tool changes text while the user is typing.

- At least `N_min` keys typed. Starting values: 4 for EN→RU and 5 for RU→EN; final values from the prefix curves (section 18.3).
- Threshold at least one step stricter than the boundary threshold for the same length (for example 0.9995, which is 7.6 nats, where the boundary threshold is 0.999).
- The decisions on the last 2 key events agree (`ConsecutiveAgreementCount` = 2), as in KeyboardSwitcher.
- Training includes prefix samples without the end-of-word token (35% of samples, section 8.3), so that the model has seen unfinished words.
- Early conversions have their own false-positive rate in the report. The gate is the same as for the boundary mode.

### 10.6 Adaptive thresholds (deferred, off in the first release)

The thresholds of 10.3 are fixed per release, and the shift `Δ` is 0. A per-user threshold shift is attractive, but it cannot be implemented unambiguously from what is known: the gain, the estimator of the undo rate, the handling of a zero rate, the update on each undo or manual conversion, the floors and the persistence and reset were never fixed, and an adaptive threshold makes the EV-1 gate hard to state, because each user would run at a different operating point. The earlier sketch, `Δ = clip(k · ln(u / u_target), −1, +2)` nats with an exponentially weighted undo rate `u`, is kept as an idea only.

The feature may enter a later release only when this document defines the complete update rule in nats on the scale of 10.1, shows by replay on R-ACC that the false-positive rate stays inside EV-1 at the upper bound of the shift, and adds the requirement to the CA table. Until then no adaptive state is stored, and the only per-user adaptation is the exception list and the cool-down (13.3).

### 10.7 Why the thresholds are so high

A convert decision is worth it when `p' ≥ C_FP / (C_FP + C_FN)`, where `C_FP` is the cost of a wrong correction and `C_FN` the cost of a missed one. A missed correction costs one hotkey press. A wrong one costs the user noticing, undoing and retyping, and, more importantly, trust: people disable the tool after a few visible errors. Taking `C_FP / C_FN` between 100 and 1000 gives probability thresholds between 0.99 and 0.999 (4.6 to 6.9 nats). This ratio is an assumption, not a measurement; the opt-in undo statistics (section 14.5) are the way to refine it.

### 10.8 Requirements

| ID | Requirement |
| --- | --- |
| CA-1 | Temperature `T` MUST be fitted on calibration data only (the synthetic validation set and R-CAL, section 8.4), stored with the model hash, and applied before the prior-shift correction. |
| CA-2 | The prior-shift correction MUST be applied with the full three-class vector of 10.2. `π_train`, `w` and `o_lat` MUST be stored in a versioned table (D5). |
| CA-3 | The threshold MUST be a table in nats by scorer kind, direction and length bucket. A single global constant MUST NOT be used, and the runtime MUST compare the score with nats only (10.1). |
| CA-4 | Calibration MUST be checked in the tail: among calibration items with `p' ≥ 0.99`, the observed precision MUST be within the 95% confidence interval of the stated probability, per direction and length bucket. ECE ≤ 0.02 per class and per length bucket. |
| CA-5 | 1-key words MUST never be converted automatically; 2-key words only through 10.4. |
| CA-6 | Thresholds, temperature and priors MUST be frozen before the locked synthetic test and R-ACC are evaluated. |
| CA-7 | If label smoothing is used in training, calibration MUST be re-fitted afterwards, and the tail check (CA-4) repeated. |
| CA-8 | Early detection MUST be off by default and MUST have its own acceptance gate. |
| CA-9 | The calibration package MUST be validated against the strict schema LFC1 (20.5) before an engine is created, and refused whole on any failure: exactly the fields of the schema, none missing, none unknown, none duplicated; both scorer kinds with a complete threshold table (both directions, all three length buckets); every threshold within 4 to 16 nats; `w` within 0.0005 to 0.5 for every state and at most 0.3 for `run`; `π_train` sums to 1 and `0 < o_lat < 1`; a scalar temperature for every scorer kind, finite and above 0 (at most 20); three positive integer class counts (pi\_train\_counts) from which pi\_train is derived and with which it agrees within 1e-9; the model hash in the package equals the hash of the loaded model or table file. A refused package never produces an engine: the mode is MANUAL\_ONLY, or the previous valid package stays active when the refusal comes from an update (13.5, rows 6 and 12). The tests of 20.13 give one negative case per rule and check the resulting mode, not only the exception. |
| CA-10 | The word-state machine of 10.2 (credit, feedback cap, resets) and the priority matrix of 10.4 MUST be implemented as specified; the reference code and traces of section 20 are the tests. |
| CA-11 | Adaptive thresholds (10.6) MUST NOT be enabled in the first release. |


## 11. Evaluation and acceptance

The product is accepted on the rate of false corrections measured on realistic text with enough correct words to prove it; accuracy is reported but never gates a release. A model that always says KEEP is 99% accurate and useless, and a model with 99.9% accuracy on a balanced set still corrupts text daily when wrong-layout words are 1% of input (section 5.5).

### 11.1 Definitions

- **Unit.** One word candidate (section 5.3) at the moment of decision.
- **Positive.** A word typed on the wrong layout that should be converted. **Negative.** Everything else: correctly typed EN and RU words and every OTHER item.
- **False-positive rate `F`.** False corrections divided by negatives. Reported token-weighted (each word counted as often as it occurs in running text) and type-weighted (each distinct word once). The token-weighted figure is the one users experience.
- **Recall `R`.** Correct conversions divided by positives, sliced by length (11.4).
- **Precision at deployment prior `π`.** `πR / (πR + (1 − π)F)`, reported for π = 0.3%, 1% and 3%.
- **Undo rate.** Undone corrections divided by corrections, in dogfooding.
- **Calibration.** Expected calibration error (ECE) per class and per length bucket, plus the tail check of CA-4.

### 11.2 Acceptance gates

| ID | Metric | Gate | Measured on |
| --- | --- | --- | --- |
| EV-1 | False-positive rate on correct words | Pass rule of 11.3: at least 100,000 correct words from at least 20 users and 100 documents; point estimate ≤ 4.8e-5 (at most 4 false corrections at n = 100,000) and conservative cluster criterion ≤ 1e-4 (a decision rule, not an exact confidence interval; 11.3) (precision ≥ 99.5% at π = 1%, R = 0.95) | `R-ACC`, real correct words (8.4); frozen, and used for this gate only at G4 (16.1) |
| EV-2 | False corrections on protected content (every OTHER category of section 8.3) | 0 in at least 100,000 items, each category at least 5,000; upper bound ≤ 3e-5 | Protected regression set |
| EV-3 | Precision at π = 0.3%, 1%, 3% | Reported; ≥ 99.5% at π = 1% | Derived from EV-1 and EV-4 |
| EV-4 | Recall for words of 5 or more keys at the operating point of EV-1 | ≥ 95% EN→RU and ≥ 90% RU→EN. These values are changed only at the proxy gate G2-proxy (16.1) by a recorded decision, as set out in 11.3, and are frozen after it | `R-ACC` positives (synthetic re-layout of real sentences, 11.7) |
| EV-5 | Recall for 3–4 keys | ≥ 60%, changed and frozen as EV-4 | `R-ACC` positives (synthetic re-layout of real sentences, 11.7) |
| EV-6 | Token-weighted recall, all lengths | Reported | `R-ACC` positives (synthetic re-layout of real sentences, 11.7) |
| EV-7 | Calibration | ECE ≤ 0.02 per class and per length bucket; tail check CA-4 passed | Fitted on `R-CAL`, checked on `R-ACC` |
| EV-8 | Robustness to key-level typos (5–8% of words) | False-positive rate unchanged within its confidence interval; recall loss ≤ 3 points | Synthetic test with noise |
| EV-9 | Stress sets | No category has a false-positive rate above 2 times the overall gate | Stress sets of section 8.4 |
| EV-10 | Early-detection mode, if enabled | Same false-positive gate, measured separately | `R-ACC`, prefix events |
| EV-11 | Undo rate in dogfooding | ≤ 0.5% of corrections over at least 10,000 corrections (upper bound) | Opt-in users |
| EV-12 | Neural model versus statistical baseline | The model ships only if, at the EV-1 operating point, token-weighted recall is at least 2 points higher (paired cluster bootstrap, 95% interval excludes 0) or the false-positive rate is at least 30% lower at equal recall. Otherwise the statistical baseline ships | `R-ACC`, both candidates frozen first (CA-6), in the same evaluation as EV-1 |
| EV-13 | Seed stability | At least 3 seeds; report mean and standard deviation; a difference smaller than the seed deviation is not a finding | `S-VAL`, `S-TEST` |
| EV-14 | Latency, size, memory | Gates of section 7.5 and section 12 | Reference devices |
| EV-15 | Text integrity | G-EVENT: 0 lost or duplicated physical key events in 1,000,000 events per OS (RT-16); G-FIELD: 0 UNRECOVERED outcomes and 0 silent divergences in 100,000 replacements per application (RT-4, 13.2) | End-to-end suite |

### 11.3 How many words are enough

To prove a false-positive rate you need many correct words, because the errors are rare. With `k` observed errors the one-sided 95% Poisson upper limit on the number of true errors is 3.00, 4.74, 6.30, 7.75, 9.15 and 10.51 for `k` = 0 to 5. The table gives the number of independent correct words needed for the upper bound to stay below each target.

| Observed errors `k` | Upper-limit multiplier | Words for bound ≤ 1e-4 | Words for bound ≤ 3e-5 | Words for bound ≤ 1e-5 |
| --- | --- | --- | --- | --- |
| 0 | 3.00 | 29,958 | 99,858 | 299,574 |
| 1 | 4.74 | 47,439 | 158,129 | 474,387 |
| 2 | 6.30 | 62,958 | 209,860 | 629,580 |
| 3 | 7.75 | 77,537 | 258,456 | 775,366 |
| 4 | 9.15 | 91,536 | 305,118 | 915,352 |

The second draft's realistic test (5–20K words) can only demonstrate a rate near 1 in 1,000, which is 10 times too lax for this product; the third draft's 300,000 synthetic negatives are the right size, but synthetic text does not show the real rate. Words from one text are correlated, so the effective sample is smaller than the word count. The table is therefore a sizing guide only; the pass condition of EV-1 is the conservative cluster criterion below.

For recall, a 95% interval of ±1 point needs about 1,830 positives at R = 0.95, 1,120 at R = 0.97 and 380 at R = 0.99; ±0.5 point needs 7,300, 4,470 and 1,520. Collect at least 20,000 positives per direction so that each length bucket has several thousand.

**EV-1 pass rule under clustering (normative; reference code in 20.9).** Words typed by one user in one document share vocabulary, topic and habits. One weakness, for example a surname that scores as Russian, can repeat many times, and counting each repeat as an independent error would make the bound too optimistic. A *cluster* is one pair (user, document). Let `n` be the number of correct words after the caps of 8.5, `k` the number of false corrections, `c` the number of distinct clusters that contain at least one false correction and `m` the largest number of false corrections in one cluster. EV-1 passes if and only if all four conditions hold.

1. `n` ≥ 100,000, the words come from at least 20 users and at least 100 documents, and `n` was fixed before the first evaluation (8.5).
2. `k / n` ≤ 4.8e-5. At `n` = 100,000 this allows at most 4 false corrections; at a larger `n` the allowance grows in proportion.
3. `U(c) · m / n` ≤ 1e-4, where `U(c)` is the exact one-sided 95% Poisson upper limit for `c` observed events: 2.9957, 4.7439, 6.2958, 7.7537, 9.1535 and 10.5130 for `c` = 0 to 5 (the function `poisson_upper` of 20.9 computes it for any `c`).
4. The evaluation is the one that the log of `R-ACC` records (8.4); a pass found in a repeated, tuned or extended evaluation does not count.

If every false correction sits in a different cluster, then `c` = `k`, `m` = 1 and condition 3 is the independent-words bound of the table above. If the errors bunch together, `c` falls (the errors are one problem seen several times) and `m` rises, and the bound rises with `m`: the rule assumes that every independent source of error could produce as many errors as the worst one that was observed. This is conservative on purpose, and it is a decision rule, not a confidence interval with exact coverage. How often it accepts a system of a given true error rate, with errors spread or bunched, is simulated in section 18.9 with pre-registered scenarios and seeds; that simulation is evidence about the rule, and not a proof of coverage. A cluster bootstrap is not used as the gate because with 4 or fewer events most resamples contain none of them and the interval degenerates; it stays in the report as a diagnostic.

Worked cases, all reproduced by the code of 20.12: 4 false corrections in 4 different clusters at `n` = 100,000 give a bound of 9.15e-5 and pass. The same 4 in one document give 1.90e-4 and fail. Two clusters with 2 errors each give 1.26e-4 and fail. 0 errors at `n` = 99,999, or 0 errors from 19 users, fail on condition 1. 5 errors in 5 clusters at `n` = 150,000 give 7.01e-5 and pass.

**Freezing EV-4 and EV-5.** The provisional recall values stand unless they are changed at gate G2-proxy (16.1) by a written decision that contains the baseline recall at the EV-1 operating point on the `R-CAL` positives. The values may be lowered only to that measured recall minus 2 points, rounded down to a whole number, and may never be raised above the provisional ones to fit a result. They are frozen when G2-proxy is passed. A change after the first evaluation on `R-ACC` makes that `R-ACC` retired (8.4).

### 11.4 Required slices in every report

- Direction: EN→RU and RU→EN.
- Length in keys: 2, 3, 4, 5–6, 7–9, 10 or more.
- Content: ordinary word, name, brand, acronym, slang, and each OTHER category (identifier, URL, e-mail, path, number, hash, command, transliteration, key-mashing).
- Case: lower, Capitalised, ALL CAPS, mixed, Caps Lock on.
- Context: sentence start, after a word of the other language, after punctuation, mixed-language sentence.
- Mode: boundary and early detection.
- Source and user, to expose clustering.

### 11.5 Measuring the wrong-layout rate π

The false-positive budget depends on π, which is unknown (section 5.5). Estimate it in the opt-in study as `(corrections not undone + manual conversions) / words typed`, per user, with a cluster bootstrap interval, and record the distribution of wrong-layout run lengths (words typed before the user notices). The estimate feeds the priors of section 10.2 (which events count, the denominator, the interval and the value that goes into D5 are fixed there) and the precision table of EV-3.

The events used for this estimate form `R-NAT` (8.4): words that the user converted by hand, and automatic corrections that were not undone. They are real errors in real contexts, so they are the only check that the synthetic positives of `R-ACC` are not misleading. Report the recall on `R-NAT` beside the recall on the `R-ACC` positives; if the `R-NAT` figure is lower by more than 10 points, the synthesis of 8.3 goes back for review. `R-NAT` never gates a release: it holds only errors that someone noticed, and it contains the tool's own hits, so a recall computed on it is biased in both directions.

### 11.6 Procedure and discipline

- Thresholds, temperature and priors are fitted on S-VAL and R-CAL only (CA-1 to CA-3, 8.4). R-ACC is evaluated at most three times, by someone who did not tune the model, and each use is logged (8.4). S-TEST and the stress sets are used for reporting and regression, never for tuning.
- Model comparisons use the same split and a paired bootstrap, not two separate point estimates.
- Report the area that matters: recall at fixed low false-positive rates (1e-3, 1e-4, 1e-5), not full-range AUC, which is dominated by easy examples.
- BLEU, ROUGE, perplexity and plain accuracy are not acceptance metrics. Accuracy is reported only as a diagnostic.

### 11.7 What each result is evidence of

The acceptance numbers do not all rest on the same kind of data. The table says, for each, what is real, what is constructed, what the result proves and what it leaves open. The model card (EV-18) repeats it.

| Result | Negatives | Positives | It shows | It does not show |
| --- | --- | --- | --- | --- |
| EV-1 false-positive rate | Real, `R-ACC` | none | The rate of false corrections on the correct typing of the enrolled users, with the conservative criterion of 11.3 | The rate for other users, applications, topics or languages; the sample has at least 20 users |
| EV-2 protected content | Synthetic generators and packages of 8.3 | none | Code, URLs, paths, hashes and similar shapes are not converted | How often such strings occur in a real day |
| EV-3 precision | Real | Synthetic, with an assumed π | Precision if the wrong-layout rate is 0.3%, 1% or 3% | The true π of any user; it stays an assumption until `R-NAT` and dogfooding measure it |
| EV-4, EV-5, EV-6 recall | none | Synthetic re-layout of real sentences, `R-ACC` | That wrong-layout words in realistic sentences are recognised and converted | How often, where and in which words users really err; `R-NAT` is a biased check (11.5) |
| EV-7 calibration | Real and synthetic mixture | Synthetic | Reliability of the probabilities on the mixture of `R-CAL` and `R-ACC`; the mixture weights come from the assumed priors | Reliability under a different π |
| EV-8, EV-9 robustness, stress sets | Synthetic | Synthetic | Behaviour on targeted failure families | Their real-world frequency |
| EV-10 early detection | Real prefixes | Synthetic prefixes | The false-positive gate inside a word | Nothing about the user's tolerance for text changing mid-word |
| EV-11 undo rate | Real | Real | What enrolled users accept in daily use | A different population |
| EV-12 network or baseline | Real | Synthetic | Which candidate is better on the same data; any optimism of the set is shared | An absolute quality figure |
| EV-14, EV-15 | none | none | Latency, size, delivery of physical key events (G-EVENT) and integrity of the field (G-FIELD) on the reference devices and in the end-to-end suite | Other devices or applications than those listed in 13.8 |

The experiments of section 18 are a different class again. They are word lists scored by form, with synthetic `OTHER` strings, and most are single runs. They justify the design and the starting values; they are not release evidence, and nothing in section 18 is a gate.


## 13. Runtime behaviour, safety and privacy

The model only proposes; a deterministic runtime decides whether to act, performs the replacement and can always undo it. Most field failures of layout switchers come from text injection, stale buffers and unsafe contexts rather than from the classifier, so every rule below is mandatory and tested end to end (section 15).

### 13.1 Stage 0 context gate and stage 3 guards

**Stage 0 runs before anything is stored.** The runtime keeps one verdict about the focused text element, the *gate verdict*. The key-event callback reads only that verdict, and a key enters the buffer only when it is ALLOW. Everything else in this section (buffer, segmentation, guards, model) happens after the gate.

| Verdict | Meaning | Effect on keys |
| --- | --- | --- |
| ALLOW | Positively established: the focused element is an ordinary editable text control, the OS text interface can read it, it is not secure, and its application is neither blacklisted nor quarantined | Keys are recorded |
| DENY | Secure field, secure-input mode, blacklisted or quarantined application, user opt-out, or the tool is paused | No key is stored, counted, classified or logged; the buffer and the run state are discarded |
| UNKNOWN | Not yet determined, or not determinable: no text interface, an application outside the verified list (13.8), a detection error, or a focus change that has not been resolved | Treated exactly as DENY |

Rules of the gate:

- **Default deny.** Only ALLOW lets a key in. Unknown applications, custom-drawn controls and any element whose role cannot be read are UNKNOWN. This is deliberate: a missed correction costs one hotkey press, a buffered password is a security defect.
- **Event-driven and cached.** The verdict is recomputed outside the key callback on every focus change, window change, application activation, secure-input change and session event (sleep, wake, lock, fast user switching, secure desktop). A focus-change notification sets the cache to UNKNOWN at once, before the new verdict exists, so the first key after a focus change is never recorded on a stale ALLOW.
- **One atomic read in the callback.** The callback makes no operating-system call (RT-1). It copies the key into the ring buffer only when the cached verdict is ALLOW.
- **Re-check at the decision point.** Before a word is classified, the worker queries the gate afresh (budget 20 ms). Anything but ALLOW discards the word unclassified and zeroes its keys. This closes the race that no notification covers, for example a page script that turns a text field into a password field while the user is typing.
- **What counts as secure (DENY).** macOS: `IsSecureEventInputEnabled()` is true (the OS then withholds the key events from the tap as well), or the element role is `AXSecureTextField`. Windows: UI Automation `IsPassword`, a Win32 edit control with `ES_PASSWORD`. Browsers: `type=password` and the autocomplete tokens `current-password`, `new-password` and `one-time-code`. Any element whose accessible name or label contains a credential word (password, passcode, PIN, CVV, card number, пароль, пин-код) is also DENY.
- **Application blacklist (DENY).** Terminals, IDEs and code editors, remote-desktop and VM clients, password managers and full-screen games by default, editable by the user. Applications are matched by bundle identifier or by executable path and signature, never by window title.
- **Browsers and Electron applications** expose the password state and the text role only when their accessibility support is active. If the element does not report both a text-editing role and "not a password", the verdict is UNKNOWN. The first release declares ALLOW only for the verified applications of 13.8, each proved by an end-to-end test, not by unit tests.
- **The mechanism of each OS** (which API gives the verdict, the layout, the text and the replacement) is fixed in 13.7, and the per-application status in 13.8.

**Stage 3 guards** run on the recorded word, after the gate and before the dictionaries and the model. They only veto, and each veto has a reason code (10.4).

| Guard | Condition | Action |
| --- | --- | --- |
| Token shape | `://` or `www.`, an e-mail address, a dotted name with a file or domain suffix, camelCase, a key walk of four neighbours on one row. Evaluated on both readings of the keys. Digits, `_`, `-`, `/`, `\`, `@` and other non-letter keys already make the candidate ineligible (5.3). The code of section 20.4 is the normative list | KEEP, reason `shape_url`, `shape_email`, `shape_dotted`, `shape_camel` or `shape_keywalk` |
| Ineligible keys | Dead keys, combining marks, emoji, any key outside the 47-key block, mixed scripts inside one candidate | No action |
| User exceptions | The word (case-folded, with its direction) was undone before, or an application opt-out applies | KEEP, reason `user_exception` |
| Cool-down | An undo just happened | No automatic correction until 3 word decisions have been suppressed and 10 seconds have passed, whichever is later, so the tool does not fight the user |

Context breaks, which empty the buffer, are listed with the other events in 13.2.

### 13.2 Event flow and replacement transaction

**Principles.**

- **Observe only.** The hook passes every event on unchanged and at once. It never blocks, delays, swallows or modifies a user key, and it never replays one. Every user key therefore reaches the application exactly once, through the operating system, in the order typed. The decision runs on a worker thread, and the callback returns within 1 ms (p99). KeyboardSwitcher uses the same pattern to stay inside the Windows low-level hook timeout, and Rekey lets the typed character land before any correction.
- **The decision point is Space only.** By the time Space is seen, it is already in the document. Enter and Tab are not decision points: the application has already acted on them (a chat message sent, a form submitted), so they are context breaks. A wrong-layout word at the end of a line is therefore converted by the hotkey (13.3), not automatically. This is an accepted cost; the alternative needs to hold Enter back, which is what the observe-only rule forbids.
- **The tool writes only the range of the word it recorded** and never touches the keys typed after it. It does not change the operating-system layout in the first release (open question 16.3).
- **Synthetic events are tagged** (13.7). The recorder ignores them, so the tool never reads its own output as user input.

**Events and their effect.**

| Event | Effect on the word buffer and the run state |
| --- | --- |
| Printable key of the 47-key block, no Ctrl, Cmd or Alt, gate ALLOW | Append `(key, Shift, Caps, layout id)`; more than 64 keys marks overflow (10.4, row 2) |
| Space | Decision point: end of the word, decision on the worker thread |
| Backspace | Remove the last key; on an empty buffer it is a context break (text before the word is being edited), except inside a dropped word, where it is ignored |
| Manual layout change inside a word | The word is dropped (its keys came from two layouts); the rest of it is ignored; `after_switch` is set; `c := 0` |
| Manual layout change between words | `after_switch` is set; `c := 0` |
| Enter, Tab | Context break |
| Arrow keys, Home, End, Page Up, Page Down, Delete, Escape, function keys, any chord with Ctrl, Cmd or Alt, the application's own undo | Context break |
| Mouse click, focus or window change, paste, drag and drop, IME composition, dead key, session event | Context break; the gate is recomputed |
| Tagged synthetic event | Ignored by the recorder; counted by the echo check below |
| This tool's hotkey (13.3) | Taken by the OS hotkey registration, so the chord does not reach the application |

A **context break** empties the word buffer, clears the drop flag (the next word starts clean) and sets `c := 0` (10.2). A word starts with the first printable key after a Space or a break. The layout id is part of every recorded key, and the rule for a layout change inside a word is the single one in the table: the word is dropped, so the raw keys of two layouts are never mixed.

**Replacement transaction.** A CONVERT verdict starts a transaction on the worker thread, with a hard deadline of 250 ms from the Space. Automatic transactions exist only in mode AUTO, which an application reaches only when its adapter has the four capabilities `READ_RANGE`, `REPLACE_RANGE`, `READBACK` and `ROLLBACK` and its support status is AUTO (13.5, 13.7, 13.8). The hotkey (13.3) runs the same transaction in mode MANUAL\_ONLY, where M2 is also allowed. The transaction works on one fragment: the word as typed, the Space that the user typed and the typed-ahead characters. That fragment is matched in step 3, verified in step 5 and rolled back in step 6, and nothing outside it is ever written. The reference model of the transaction, with its fault injection, is section 20.14.

1. **Freeze.** Count `a`, the printable keys typed after the Space so far, and note any other event since the Space. More than 3 such keys, any context break or any layout change aborts with reason `typed_ahead` or `context_break`; the verdict becomes KEEP. With M2 (which runs only with `a = 0`) any typed-ahead key aborts with `typed_ahead`, and a Shift, Ctrl, Alt or Windows key that is physically down aborts with `modifier_down` (13.7). Then take the key counter `m` (`Adapter.mark`): from this moment every user key event is counted, including a key that types nothing (Shift, an arrow, Caps Lock). An adapter that cannot count aborts with `adapter_error`.
2. **Gate.** Query the gate afresh. Anything but ALLOW, including an error of the query, aborts with `gate_changed`.
3. **Read and match.** Read the caret `c` and the text before it through the OS text interface; the selection must be empty (an adapter reports a caret only for an empty selection and raises an error otherwise, 13.7). For `a'` from `a` down to 0, read the range of `n + 1 + a'` characters that ends at `c`; the first `a'` for which it equals `old + " " + ahead[:a']` fixes the **fragment**: the word as typed, the Space the user typed and the `a'` typed-ahead characters (`n` is the number of keys in the run). The range to replace is thus fixed from the content, not from remembered offsets. If the text cannot be read, or differs because the application autocorrected, autocompleted or reformatted it, abort with `echo_mismatch`; any other error of the adapter aborts with `adapter_error`.
   - **3b. Last look (M2 only).** Immediately before the first synthetic event, read the key counter again. M2 deletes by count, so a user key that arrived since the freeze makes the plan wrong: if `keys_since(m) > 0`, abort with `typed_ahead` and send nothing. A key that arrives after this look cannot be detected in advance; it is the residual M2 race described below.
4. **Replace** exactly the `n` characters of the run by the same keys read on the target layout (`Ghbdtn?` becomes `Привет,`; the Space the user typed is not touched). The new text has the same length as the old, so the caret and any typed-ahead characters stay where they are.
   - **M1, range replace** (the only method of mode AUTO): one operation through the text interface that the application cannot interleave with user keys, then the caret and selection are restored. It needs the capability `REPLACE_RANGE` (13.7).
   - **M2, tagged synthetic keystrokes** (the hotkey only, never automatic): only when `a' = 0`. Send `n + 1` Backspaces, then the new text and a Space, as tagged Unicode events in one batch (one `SendInput` call on Windows; a sequence of posted events on macOS).
   - The clipboard is not used in the first release.
5. **Verify the whole fragment and the caret.** Read the fragment back: it must equal `new + " " + ahead[:a']`, so the Space and the typed-ahead characters are checked together with the word. Read the caret and the number `k` of user keys counted since the freeze. If `k = 0` the caret must be exactly where it was (`c`); if `k > 0` it may have moved forward by at most `k` (`c ≤ caret ≤ c + k`). A caret that moved backwards, or forward without a user key to explain it, is a failure, and so is a selection that is no longer empty. A word that is right with a wrong neighbour or a wrong caret is therefore never `VERIFIED`.
6. **Outcome.** The transaction ends in exactly one outcome, decided by what is read from the field and never by what the tool meant to write (reference function `classify_outcome`, section 20.14). It compares three texts of the whole fragment: the original, the new one and the one that is read last.
   - `VERIFIED`: step 5 passed.
   - `RESTORED`: an operation failed or step 5 failed after step 4 began, and the whole fragment holds the text the user typed. M1 makes one rollback attempt (it writes the original word back over the same `n` characters and reads the fragment again); a write that changed nothing also ends here.
   - `UNRECOVERED`: anything else, including a fragment that cannot be read and damage outside the `n` written characters (the Space, a typed-ahead key) that the rollback cannot repair. A failed M2 transaction that changed the field ends here, because M2 has no rollback.
   - `ABORTED`: steps 1 to 3 refused, nothing was written.

   Any outcome after step 4 began other than `VERIFIED` is a *replacement incident*: the tool shows one notice, increments `replacement_incident` (a counter, never text) and quarantines the application (gate DENY for it until restart or until the user re-enables it in the settings). After `UNRECOVERED` the notice says that the text in the field may differ from what was typed and that the application's own undo is the way back.
7. **Record the undo snapshot** (13.3) only for a `VERIFIED` outcome: the original keys with their layout id, in a store that is separate from the word buffer (13.4). For any other outcome the engine drops the snapshot and the run credit (`Engine.on_outcome`, 20.7).

**What happens to the user's keys.** Before step 4 they pass through and are never held. With M1 a key typed during steps 3 to 5 lands after the fragment and is unaffected, because the replacement has the same length; the key counter of step 1 explains a caret that moved forward by that key, and a key that lands inside the fragment makes the read-back of step 5 differ, so the rollback applies. M2 is a sequence of separate key events, and its races are different. On Windows one `SendInput` call inserts its events "not interspersed with other keyboard or mouse input events inserted either by the user … or by calls to keybd\_event, mouse\_event, or other calls to SendInput" (Microsoft Learn), so a user key cannot fall inside the batch. A user key can still fall between the read of step 3 and the write of step 4 (the last look of step 3b catches a key that arrived before it, but not one that arrives between that look and the first event of the batch, a window that is short but not zero), a key that is already physically down "might interfere with the events that this function generates", UIPI can block the input without the return value or `GetLastError` saying so, a partial insertion is visible only in the returned count, and the application can change focus or text meanwhile. On macOS a user key can follow any posted event. The tool cannot close these races without holding keys, which it must not do, and a failed M2 transaction can leave the field in a state with no rollback. The race that remains is not hidden: it ends in UNRECOVERED and a quarantine, never in a silent VERIFIED (the reference model puts a user key before each of the 14 events of a six-letter word and checks this, 20.13), and its real frequency, including a held key that repeats, is measured on devices (RT-4, RT-16) and not assumed to be zero. This is the reason for the rule of 13.7: **M2 never runs automatically.** It exists only for the hotkey, where the user chose the moment and has the application's own undo as the way back.

**Two guarantees, stated precisely.**

- **G-EVENT (by design).** The tool never loses, duplicates, holds, delays or replays a physical user key, because the hook only observes (RT-8). The reference model checks this property for the algorithm (invariant I1, 20.13); the delivery of real key events by the operating system is measured on devices (RT-16).
- **G-FIELD (measured, not absolute).** The only text the tool writes is the replacement of the recorded word. After an automatic replacement the whole fragment (word, Space and typed-ahead keys) holds the new text (`VERIFIED`) or the text the user typed (`RESTORED`). `UNRECOVERED` is possible only when the write and the single rollback both fail, or when the field cannot be read afterwards, or when the write damaged text outside the characters it wrote (the Space, a typed-ahead key) and the rollback cannot repair it; it is always detected or reported, it quarantines the application, and its rate in RT-4 must be 0 in 100,000 replacements per application. The specification gives no unconditional promise about application text, because an application can change its own text at any moment; it promises detection by read-back, one repair attempt, quarantine and a count.

### 13.3 Undo, exceptions and manual control

**One chord for conversion and undo,** so the user has one thing to remember. What it does depends on the situation when it is pressed:

| Situation when the chord is pressed | Effect |
| --- | --- |
| Within 10 seconds after an automatic correction, with no context break since | **Undo.** Restore the original keys exactly as recorded, rendered with the layout id recorded with them (nothing is re-derived from the converted text). Add the word, case-folded with its direction, to the exception list; start the cool-down (it ends when 3 word decisions have been suppressed and 10 seconds have passed, whichever is later); clear the run credit |
| A selection exists and the gate is ALLOW | **Manual conversion of the selection** (below) |
| No selection and the gate is ALLOW | **Manual conversion of the last word**: the last run still in the buffer, or, if the buffer is empty, the last whitespace-delimited token before the caret, read through the text interface |
| Immediately after a manual conversion | Converts back (toggle) and adds the word to the exception list |
| The gate is DENY or UNKNOWN | No action and a short notice: the tool does not read text it is not allowed to read |

- **Defaults and conflicts.** Proposed defaults, to be confirmed by the requester (16.3): Windows `Pause`, macOS `⌃⌥⌘Space`. The chord is registered through the OS hotkey interface (`RegisterHotKey` on Windows, `RegisterEventHotKey` on macOS), which keeps it from the application. If registration fails the tool tries the next chord of its fallback list (Windows `Ctrl+Alt+Pause`, `Ctrl+Alt+Space`; macOS `⌃⌥⌘L`, `⌃⌥⌘K`), tells the user which chord is active, and never binds silently to a chord the OS reports as taken. Esc is not bound by default, because it has its own meaning in many applications; "Esc also undoes" is an opt-in setting per application.
- **Manual conversion of a selection** converts key for key, with no model and no threshold. Direction: a selection with more Cyrillic than Latin letters is read as Russian-layout text and converted to the English layout, otherwise the reverse; a selection with no letters is left unchanged and the user is told. Punctuation goes through the layout table as in 5.3 (`Ghbdtn? Rfr ltkf?` becomes `Привет, Как дела,`). A character that is not on the source layout (emoji, accented letters, other scripts) is copied unchanged, and the length never changes. At most 10,000 characters. The replacement follows the transaction of 13.2 (M1 where the application has REPLACE\_RANGE; otherwise M2, typed over the selection in batches of at most 20 UTF-16 code units, an engineering limit that spike S-7 checks), with its outcomes, the quarantine rule and the verification of 13.2, and afterwards the same range is selected again; if the selection cannot be restored, the caret is placed after the text. The reference function is in section 20.8.
- **Undo window.** The undo snapshot (13.4) lives for at most 10 seconds and 100 further printable keys and Spaces, whichever comes first. It is destroyed by every context break of 13.2, a manual layout change, a gap in the event stream, a change of the gate or of the mode, the undo itself and the timeout; after that the chord no longer undoes anything.
- **Learned exceptions.** One undo of a word adds it (case-folded, with its direction) to a local exception list, as Rekey and KeyboardSwitcher do. Limit: 10,000 entries, least-recently-used eviction, encrypted at rest with the OS key store, with a "clear all" command and export.
- **Adaptive thresholds.** Not part of the first release (10.6).

### 13.4 Privacy and security

- All inference is local. No network call is allowed on the typing path.
- The **word buffer** lives in memory only, holds at most 64 keys, and is zeroed at every word boundary and context break.
- The **undo snapshot** (13.3) is the only text-derived state that outlives a word boundary. It is kept in a store that is separate from the word buffer, in memory only, for one converted word of at most 20 keys at a time. It is overwritten with zeros when it ends: at the end of the undo window (10 seconds or 100 further printable keys and Spaces), at every context break, gate change, mode change, manual layout change and gap in the event stream, at the undo itself, and at sleep, lock, logout and exit. It is never logged and never written to a file, and the product's own crash handler does not include it (RT-17).
- **Crash dumps.** The product's own crash reports contain stack traces and counters only (AP-7). Memory dumps made by the operating system or enabled by an administrator are outside the product's control; the privacy notice says so, and RT-17 tests the product's own handler.
- No raw keystrokes, words or screenshots are written to logs. Optional diagnostics contain only counters and reason codes (converted, abstained, guard name, undone), are off by default and are shown to the user before they are enabled.
- The exception list never leaves the device.
- Required OS permissions (macOS Accessibility and Input Monitoring, code signing and notarisation) are part of the release checklist, because keystroke observers are commonly flagged by security software.

### 13.5 Failure behaviour

The engine is always in exactly one of three modes, for each application separately. **AUTO**: automatic correction and the hotkey. **MANUAL\_ONLY**: no automatic correction and nothing is recorded; the hotkey works through the text interface. **OFF**: nothing is recorded and the hotkey only shows a notice. The mode is a pure function of the facts in the table below (reference function `engine_mode`, section 20.14): AUTO needs the capabilities `READ_RANGE`, `REPLACE_RANGE`, `READBACK` and `ROLLBACK` of the adapter (13.7), the support status AUTO of the application (13.8), valid models and calibration package, a complete event stream, a healthy watchdog, an identified layout, all permissions, and no quarantine. Every failure maps to one row of the table, each row has a test (RT-12), and no failure is ever resolved by guessing.

| # | Component state | Mode | What the user sees |
| --- | --- | --- | --- |
| 1 | All components valid; the network was accepted by EV-12 | AUTO, scorer `network`, in an application whose capabilities and support status allow it (otherwise MANUAL\_ONLY) | Nothing |
| 2 | The network is not shipped because EV-12 chose the baseline | AUTO, scorer `ngram`, under the same condition | Nothing; this is a normal configuration |
| 3 | The network file is missing, unreadable, differs from the hash in D5, or fails the load-time self-test (the reference logits of section 20.11 within 1e-3) | AUTO with scorer `ngram` when rows 4 to 6 are clear for it, otherwise MANUAL\_ONLY | A one-time notice that the basic mode is in use; a counter |
| 4 | The n-gram tables are missing or corrupt | MANUAL\_ONLY if the network is not usable either, otherwise AUTO with the network | A notice |
| 5 | The lexicon, the acronym list or the allow-lists are missing or corrupt (rows 9 to 11 of 10.4 cannot be evaluated) | MANUAL\_ONLY | A notice |
| 6 | The calibration package is missing, is refused by the validation of CA-9 (schema `LFC1`, 20.5), or its model hash does not match the loaded file. One package serves both scorers, so there is no fallback to the other scorer | MANUAL\_ONLY: no `Engine` is created, so nothing is classified; manual conversion needs no calibration. A failed update leaves the previous valid package active (row 12) | A notice |
| 7 | The layout of the active pair is not identified: its fingerprint (13.7) matches no supported table, the table of the pair is missing or fails its round-trip self-test, the input source is not a keyboard layout, or the layout cannot be read | OFF for that layout, and for the pair until a supported layout is active again | The status icon says "layout not supported" |
| 8 | The text interface is unavailable (permission revoked, API error) or the gate cannot be established | The gate is UNKNOWN: nothing is recorded; the hotkey only shows a notice | A notice with the way to restore the permission |
| 9 | Watchdog: the p99 compute time of the decision exceeds its budget (7.5) for 100 consecutive words | MANUAL\_ONLY until restart or until the user re-enables AUTO | A notice |
| 10 | A replacement incident: the outcome of 13.2 is RESTORED or UNRECOVERED | The application is quarantined (OFF for it, automatic and manual) until restart or until the user re-enables it | A notice; a counter. After UNRECOVERED the notice says that the field may differ from what was typed and that the application's own undo is the way back |
| 11 | An unhandled exception in the worker | The current word is KEEP; the worker restarts once; a second failure within 60 seconds gives MANUAL\_ONLY | A notice after the second failure |
| 12 | A package update fails signature or hash verification | The previous package stays active | A notice |
| 13 | The event stream is incomplete. Windows: the hook was removed or is not installed, or it lost or invented a key. The independent Raw Input observer compares the signature (scan code, extended flag, direction) of every physical key event with the event that the hook reported; either may come first, tagged and other injected events are not compared, and an event without its counterpart within 300 ms is a loss, and a counterpart that comes later does not undo it even if the watchdog timer has not run yet (canary\_missing: a key the hook did not report; canary\_extra: a hook key the observer did not see), even when the two counts are equal. macOS: the tap was disabled (`tapDisabledByTimeout`, `tapDisabledByUserInput`) or a poll finds it disabled | The word buffer, the run state and the undo snapshot are discarded (the engine receives a gap event); MANUAL\_ONLY until the stream is trusted again: Windows after the hook is installed again and 3 pairs of Raw Input and hook events with equal signatures; macOS after the tap is enabled again, at most 3 times in 60 seconds, after which MANUAL\_ONLY lasts until the user re-enables AUTO | A notice |
| 14 | A permission needed to observe keys is missing or is revoked while the tool runs (macOS Input Monitoring; the hook cannot be installed on Windows) | OFF: nothing is recorded | A notice that names the permission and the way to restore it |

A notice is shown at most once per cause and per 24 hours, and never takes focus.

### 13.6 Requirements

| ID | Requirement |
| --- | --- |
| RT-1 | The key-event callback MUST return within 1 ms (p99), MUST pass the event on unchanged and at once (observe only), and MUST NOT call the model, the accessibility API or the clipboard, compute a layout fingerprint, allocate memory, or block. Besides the key it reads only constant-time, non-blocking state: the cached gate verdict (one atomic read) and the cached layout. On Windows it reads the HKL of the foreground thread (`GetForegroundWindow`, `GetWindowThreadProcessId`, `GetKeyboardLayout`) and looks it up in a cache keyed by the HKL value; an HKL without a cache entry is an unidentified layout (the key is not recorded) and the worker thread identifies it (13.7). On macOS the layout cache is updated by the input-source notification. |
| RT-2 | No key MUST be stored, counted, classified or logged while the cached gate verdict is not ALLOW, and a word MUST be discarded unclassified if the fresh verdict at the decision point is not ALLOW (13.1). A test per supported OS and application class MUST demonstrate it with an instrumented build that counts stored keys, including a focus race (typing into a password field within 5 ms of focusing it) and a field whose type changes while typing. |
| RT-3 | Guards in 13.1 MUST take priority over any model output and MUST be unit-tested one by one, and the priority matrix of 10.4 MUST be tested row by row. |
| RT-4 | Every replacement MUST follow the transaction of 13.2 and end in exactly one of its outcomes. **Automatic mode:** at least 100,000 automated replacements per OS across the applications with status AUTO (13.8), with typed-ahead keys, a selection made before the replacement, scripted bursts at three CPU load levels and the fault injection of RT-12, with the field read by an independent reader after each one: 0 UNRECOVERED, 0 silent corruptions (a divergence that step 5 did not detect), and at most 0.1% RESTORED, all reported. **Manual mode:** at least 10,000 replacements per application with status MANUAL (13.8), with the method that application uses (M1 or M2): 0 UNRECOVERED and 0 silent corruptions (the 95% upper bound of the rate is then 3.0e-4); otherwise the application stays UNKNOWN. For M2 the report also gives, per application, how many user keys the test injected between the last look of step 3b and the first synthetic event, how many held-key repeats were present, and the outcome of each (the expected one is UNRECOVERED with a quarantine, never a silent VERIFIED), so that the width of the residual race of 13.2 is a measured number and not an assumption. The reference model of the transaction and its fault matrix are in section 20.14. |
| RT-5 | Undo MUST restore the original keys exactly, rendered with the layout recorded with them, MUST add the word to the exception list, and MUST be invalidated by every context break of 13.2. The undo snapshot MUST end at 10 seconds, at 100 further printable keys and Spaces, at a gap in the event stream, at a change of the gate, the mode or the layout, at sleep, lock, logout and exit, and at the undo itself (13.3, 13.4); each is a test. |
| RT-6 | No raw typed content MUST be persisted or transmitted; diagnostics MUST be opt-in and content-free. |
| RT-7 | An unhandled error before step 4 of the transaction MUST result in no action. An error after step 4 began MUST end in the outcome RESTORED or UNRECOVERED of 13.2 with the notice, the incident counter and the quarantine; it MUST NOT leave partial text without a report. No outcome other than VERIFIED is ever silent. |
| RT-8 | The decision MUST be made on a worker thread. The hook MUST NOT delay, hold, swallow or replay a user key, and the tool MUST NOT inject a key except as part of a tagged replacement in MANUAL\_ONLY mode. |
| RT-9 | The gate MUST default to deny: ALLOW only for an element positively established as in 13.1, and only in an application whose status in 13.8 is MANUAL or AUTO. |
| RT-10 | Every synthetic event of the tool MUST carry the tag of 13.7, the recorder MUST ignore tagged events, and a test MUST show that the output of a replacement never re-enters the recorder. |
| RT-11 | The hotkey MUST be registered through the OS hotkey interface, MUST NOT reach the application, and a registration conflict MUST follow the fallback procedure of 13.3 and be shown to the user. |
| RT-12 | Every row of the failure table of 13.5 (14 rows) MUST be implemented and tested, and every cell of the fault matrix of section 20.14 MUST have a test with its expected outcome and safe state. |
| RT-13 | The release MUST ship a support matrix (13.8) in which every application with status AUTO has a passing automatic suite of RT-4 and every application with status MANUAL a passing manual suite on the release candidate; every other application is UNKNOWN. The release report states, for every OS, how many of the tested applications reached AUTO, how many MANUAL\_ONLY and how many OFF; testing the applications of 13.8 is not a claim that AUTO works in all of them, and the user-facing description of the product states the AUTO coverage actually measured. |
| RT-14 | A layout change inside a word MUST drop the word, and no correction MUST be made for it (13.2). |
| RT-15 | A layout MUST be identified by its fingerprint (13.7), computed on the worker thread with the call that leaves the keyboard state unchanged, and re-identified whenever the HKL of the foreground thread changes. Tests: (a) the fingerprints of the supported layouts equal the tables of 19.1; (b) other layouts of the same language (Russian - Mnemonic, Russian (Typewriter), United States-International) are not identified and give row 7 of 13.5; (c) the key-state array is built by the tool (Shift as needed, Caps Lock and all other modifiers off), the virtual key and the scan code are taken for the same HKL, and a negative return value is recorded as the entry `\x00`; (d) after the 94 calls of a fingerprint, a dead-key sequence typed by the user (for example `'` then `a` on United States-International) still gives `á` and the keyboard state is unchanged. |
| RT-16 | Delivery of real key events MUST be measured on every OS: a generator of physical keystrokes that is not the tool's own injection sends at least 1,000,000 key events, and the events seen by the hook (Windows) or tap (macOS) and, on Windows, by the independent Raw Input observer, MUST show 0 lost and 0 extra events, compared one by one by signature (scan code, extended flag, direction) and not only by count, because one lost and one extra event cancel in a count. A hook deliberately made slower than `LowLevelHooksTimeout`, and a tap disabled by the system, MUST be detected within 300 ms and answered as in row 13 of 13.5. The reference model proves this property only for the algorithm (invariant I1 and the HookHealth tests of 20.13). |
| RT-17 | The product's own crash handler MUST NOT contain the word buffer or the undo snapshot. A test crashes the process while a snapshot is alive, using a marker string that was typed, and searches the report and every dump the product wrote: 0 occurrences. Dumps made by the operating system or an administrator are outside the product (13.4). |
| RT-18 | The mode of an application MUST be the value of `engine_mode` (20.14) for the facts of 13.5. The mode AUTO MUST NOT be reachable for an application whose adapter lacks any of `READ_RANGE`, `REPLACE_RANGE`, `READBACK`, `ROLLBACK`, whatever its status in 13.8 says, and M2 MUST NOT run automatically. A test enumerates all combinations of the five capabilities, the three statuses and the health facts against the reference function. |

### 13.7 Platforms, mechanisms and the first release

**Scope of the first release:** Windows 10 version 1607 or newer, x64 (the layout fingerprint needs the `ToUnicodeEx` flag that leaves the keyboard state unchanged, documented from this version), and macOS 13+ (Apple Silicon and Intel). **Linux is not in the first release.** It needs its own column in the table below and its own test matrix: Wayland restricts global key capture, X11 would use XInput2 or XRecord, and IBus or fcitx engines are a different architecture. The engine (sections 5 to 12 and 20) is OS-independent; only the adapter described here is per OS. A cell that names a spike (S-1 to S-7, 16.1) is a hypothesis until the spike has a result, and the feature it supports stays off until then. The sources of the API statements, with quotes, are in the audit report `audit/L4_platform_api_audit.md` of the repository.

**Integration type: a user-space background application** with a listen-only global key observer, an accessibility or UI-automation text adapter, and a hotkey registration. It is not an input method (TSF, Input Source, IBus): an input method changes which keys the application receives, which the observe-only rule of 13.2 rules out.

| Function | Windows 10 (1607+) and 11, x64 | macOS 13+ |
| --- | --- | --- |
| Event capture | `SetWindowsHookEx(WH_KEYBOARD_LL)` on a dedicated thread that has a message loop. The callback copies the event to a queue, calls `CallNextHookEx` and returns, far inside `LowLevelHooksTimeout` (at most 1000 ms; from Windows 7 a slower hook is removed silently). Events with `LLKHF_INJECTED` or `LLKHF_LOWER_IL_INJECTED` are not user keys: ours carry the tag, any other injected event is not recorded and is a context break. Whether Raw Input becomes the primary source is decided by spike S-1 | `CGEventTapCreate` with the **session** tap location (`kCGSessionEventTap`) and the **listen-only** option (`kCGEventTapOptionListenOnly`), for key down, key up, flags changed and mouse down (context breaks). Never an active (default) tap and never the HID location (root only). Permission: Input Monitoring |
| Event-stream health | An independent observer: a message-only window registered with `RegisterRawInputDevices` for the keyboard with `RIDEV_INPUTSINK` (the window handle is required), which gets `WM_INPUT` for physical keys also in the background (`RIM_INPUTSINK`) and passes every `WM_INPUT` to `DefWindowProc`. Every physical key event is compared with the event of the hook by signature (scan code, extended flag, direction); either may come first, and injected events are not compared. An event without its counterpart within 300 ms (a counterpart that arrives later does not count, even if the watchdog timer has not run yet), either a key the hook did not report or a hook key the observer never saw, means that the hook lost the stream: row 13 of 13.5 (reasons canary\_missing and canary\_extra, HookHealth of 20.14). Comparing counts would not do, because one lost and one extra event cancel. The hook is installed again and trusted after 3 pairs with equal signatures. This process registers the keyboard class in this one window only: Microsoft states that only one window per raw input device class may be registered to receive raw input within a process (confirmed in the audit report, card W5e), so no other component of the product registers Raw Input. If the registration fails, the mode is at most MANUAL\_ONLY. Spike S-3 measures the conflict rule and whether input of an elevated window is delivered | `tapDisabledByTimeout` and `tapDisabledByUserInput` arrive in the callback as out-of-band events. The handler discards buffer, run state and undo snapshot (a gap event) and calls `CGEventTapEnable(tap, true)`, at most 3 times in 60 seconds. A timer every 5 seconds checks `CGEventTapIsEnabled` and `CGPreflightListenEventAccess`; a failure is the same loss. Access can be revoked while the trust API still answers yes, so an inconclusive poll creates and releases a listen-only test tap |
| Physical key id | Scan code and extended flag of `KBDLLHOOKSTRUCT`, mapped to the 47 ids (section 19.1) | `kCGKeyboardEventKeycode`, mapped to the 47 ids. That these codes do not depend on the input source is checked on the Russian - PC layout by spike S-6 |
| Shift and Caps Lock | Shift from the tracked key state. Caps Lock is the tool's own state: read once with the low-order bit of `GetKeyState(VK_CAPITAL)` at start, at every focus change and after resume, and flipped at every Caps Lock key-down the hook sees; `GetKeyState` follows the thread's message queue, not the hardware, so a mismatch with it at a word boundary drops the word | Event flags (shift, alpha-shift) |
| Active layout and its identification | The HKL of the foreground thread is read for every key (`GetKeyboardLayout`). The language id in its low word names a language, never a layout, and `GetKeyboardLayoutName` answers only for the calling thread, so neither decides. The layout is **identified by its fingerprint**, computed on the worker thread the first time an HKL is seen: for each of the 94 key states (47 keys, Shift off and on; Caps Lock and every other modifier off) one call of `ToUnicodeEx` with the virtual key and scan code of that HKL, a key-state array built by the tool, `dwhkl` = the HKL and `wFlags` = 4 ("keyboard state is not changed"); a negative result is a dead key and gives the entry `\x00`. The fingerprint is the SHA-256 of the 94 entries joined by line feeds (`layout_fingerprint`, 20.14) and is compared with the fingerprints of the supported tables (`identify_layout`). No match: row 7 of 13.5. The result is cached by HKL value. That `GetKeyboardLayout` works for another process's thread, and that `ToUnicodeEx` accepts that HKL, are not documented: spike S-2; if either fails the layout is not identified and the pair stays OFF. KLID values (`00000409`, `00000419`) are for diagnostics only and take no part in any decision: the mode follows from the fingerprint alone | A cache updated by the selected-input-source notification (`TISCopyCurrentKeyboardInputSource` on the main thread). The source must be a keyboard layout; an input method or any other source gives OFF for the pair. A layout is supported only when its fingerprint (94 entries; the mechanism is selected by spike S-6, see below: from `UCKeyTranslate`, or from `NSEvent.characters(byApplyingModifiers:)` if spike S-6 shows that `UCKeyTranslate` must be replaced; Shift off and on; dead keys give `\x00`) equals the table of 19.1. The ids `com.apple.keylayout.US` and `.RussianWin` ("Russian - PC") are only a pre-filter and never grant support. The macOS layout "Russian" has a different punctuation table and is **not supported** in the first release |
| Gate and text interface | UI Automation: focused element, control type, `IsPassword` (TRUE: DENY), `TextPattern` to read the text around the caret (the pattern is for reading; a change of text is another pattern), focus-changed event; Win32 edit and rich-edit controls through their messages | Accessibility API: focused element, role and subrole (`AXSecureTextField` is examined as both), `AXSelectedTextRange`, `AXStringForRange`, focus-changed observer. `IsSecureEventInputEnabled()` is a **global** signal: while any process has secure event input on, the OS stops passing keyboard events to event taps (Apple technical note TN2150), so every application is DENY. It does not say which field is secure, and its absence does not prove that a field is not secure |
| M1, range replace (capability `REPLACE_RANGE`) | Win32 edit and rich-edit controls: `EM_SETSEL` and `EM_REPLACESEL` (the replacement can be made undoable), read-back with `EM_GETTEXTRANGE` or `WM_GETTEXT`, rollback with the same messages; their behaviour across processes is checked by spike S-4. UI Automation `ValuePattern.SetValue` "sets the value of the element" and needs an enabled, not read-only element; it is **not** a range replacement by itself (table below) | Set `AXSelectedTextRange`, then `AXSelectedText`, then restore the caret: three calls, and the API gives no atomicity against user keys. `REPLACE_RANGE` is declared for a control class only when its RT-4 suite passes with concurrent typing |
| M2, synthetic keystrokes (hotkey only, never automatic) | One `SendInput` call with `KEYEVENTF_UNICODE` events (a `VK_PACKET` keystroke, `wVk` = 0, the character in `wScan`). Within one call the events are not interspersed with other input. Not guaranteed: that all events are inserted (the return value is the count), that an elevated window accepts them (UIPI blocks them without saying so), that pressed keys do not interfere (Shift, Ctrl, Alt or a Windows key down aborts with `modifier_down`) | `CGEventPost` with `CGEventKeyboardSetUnicodeString`, at most 20 UTF-16 code units per event (an engineering limit, spike S-7). The events are separate, so a user key can fall between them |
| Synthetic tag | The tool's 32-bit magic value in `dwExtraInfo` of every `INPUT` (the hook structure carries `dwExtraInfo`, and the injected flag is set as well) | The tool's 64-bit magic value in `kCGEventSourceUserData` (a documented 64-bit field). Whether the tap callback sees it for the tool's own events is checked by spike S-7 |
| Hotkey | `RegisterHotKey`; registration can fail when the combination is taken, and `WM_HOTKEY` is posted to the registering thread. The page does not say that the key is withheld from the application: spike S-5 | `RegisterEventHotKey`; needs the declaration from a named SDK and a test of registration, conflict and release on each release version (spike S-5) |
| Privileges and distribution | Runs unelevated, so elevated windows and the secure desktop cannot be observed or edited and resolve to UNKNOWN; signed MSIX or MSI installer | Input Monitoring (observing), Post Event (M2), Accessibility (AX text interface): three permissions, requested one by one (AP-1); hardened runtime, notarised package; first-run flow of 13.9 |
| Autostart | Per-user startup entry | Login item (`SMAppService`, macOS 13+) |

Each cell has a test in the end-to-end suite. The caret query reports the position of an empty selection and fails with an error when the selection is not empty; the reference model has the position only, so what real controls do with a selection is covered by the integration tests of RT-4. The mechanism of the macOS fingerprint is not fixed here but selected by spike S-6: Apple's page on UCKeyTranslate is reported to advise against its use in applications and to name NSEvent.characters(byApplyingModifiers:) as the alternative (status UNVERIFIED in the audit report, card M7), while that method translates the characters of an existing key event with other modifiers (card M7b), so S-6 must show for each candidate that all 94 characters of the layout of the pair, and not only of the active input source, can be obtained. A function that cannot be provided in some application or OS version makes the gate UNKNOWN for it (13.1) or lowers its mode (13.5); it is never emulated by guessing. On macOS M1 is the usual path and the automatic one. On Windows automatic correction is expected to be possible in few applications at first (classic edit controls, and the control classes that pass the table below); most modern controls will be MANUAL until a range replacement with a verified rollback is shown for them, and the evaluation report D6 says so openly, with the number of applications per OS in each of the modes AUTO, MANUAL\_ONLY and OFF. The 15 applications of 13.8 are the test set and not a promise that AUTO works in all of them.

**Capabilities.** An adapter declares, per control class, which of five capabilities it has. The mode of an application follows from them (reference function `engine_mode`, section 20.14).

| Capability | Meaning |
| --- | --- |
| `READ_RANGE` | The text of a character range of the focused element can be read |
| `REPLACE_RANGE` | A range can be replaced by one adapter operation (M1) with the caret and selection kept. Whether the application can interleave a user key with it is measured by RT-4, not assumed |
| `READBACK` | The whole fragment, the caret and the selection can be read again after the write |
| `ROLLBACK` | The original text can be written back by the same operation as the replacement |
| `SYNTHETIC_INPUT` | Tagged synthetic keystrokes can be sent (M2) |

**Mode rule.** AUTO needs `READ_RANGE`, `REPLACE_RANGE`, `READBACK` and `ROLLBACK` and the support status AUTO (13.8). M2 never gives AUTO: it has no rollback and a user key can follow any of its events. An application with `SYNTHETIC_INPUT` and `READ_RANGE` but without `REPLACE_RANGE` is MANUAL\_ONLY at best; an application that can write by neither method is OFF.

**Write results by control class (spike S-4, and the evidence of the support matrix).** Each control class of each verified application is tested for five results, and only some of them grant a capability.

| Result of the test | Meaning | Capability |
| --- | --- | --- |
| 1. The full value can be set | For example `ValuePattern.SetValue` succeeds | None by itself: a whole-field write can lose the caret, the selection and the formatting |
| 2. A range can be replaced | An operation replaces exactly the recorded range and nothing else | `REPLACE_RANGE`, only together with result 3 and a rollback verified by test |
| 3. Caret and selection are kept | After the replacement the caret and the selection are where they must be | Needed for result 2 |
| 4. Read only | The text can be read, a write is refused or not supported | `READ_RANGE`; MANUAL through M2 only if the manual suite of RT-4 passes, otherwise UNKNOWN |
| 5. Not supported | No text interface | None: UNKNOWN |

### 13.8 Support matrix and verified applications

The status is granted per application, identified by bundle identifier or by executable path and signature, never by window title. There are three statuses. **UNKNOWN** (the default): nothing is recorded, and the hotkey only shows a notice. **MANUAL**: the gate, the text interface and the replacement work in that application and its manual suite of RT-4 passed; the hotkey converts, and nothing is corrected automatically. **AUTO**: additionally the adapter has the four capabilities `READ_RANGE`, `REPLACE_RANGE`, `READBACK` and `ROLLBACK` for that control class (13.7) and its automatic suite of RT-4 passed. A status is set on the release candidate and names the OS versions of the report. It can never exceed what the capabilities allow (`engine_mode`, 20.14): an application whose only write method is M2 is at most MANUAL. A quarantine (13.5, row 10) takes the application to OFF until the user re-enables it. The list below is the proposed target list (open question 16.3); the evaluation report D6 fills in the status of each row.

| Class | macOS targets | Windows targets | What the verification covers |
| --- | --- | --- | --- |
| Native editors | TextEdit, Notes, Pages | Notepad | Gate by text interface; M1 on macOS (the usual AUTO path); on Windows M1 in Win32 edit controls and M2 for the hotkey elsewhere |
| Mail and office | Mail, Microsoft Word, Microsoft Outlook | Microsoft Word, Outlook, OneNote, LibreOffice Writer | Text interface readable; password and ordinary fields told apart |
| Browsers | Safari, Chrome, Firefox | Chrome, Edge, Firefox | Accessibility active; three reference pages per browser (plain textarea, rich-text editor, login form with a password field); `IsPassword` or `AXSecureTextField` reported |
| Chat and notes | Messages, Telegram, Slack, Discord, Obsidian, Notion | Telegram Desktop, Slack, Discord, Microsoft Teams, Obsidian, Notion, WhatsApp Desktop | Same as browsers for Electron applications; native chat windows by text interface |

That is 15 applications per OS. A release needs at least 10 applications with status MANUAL or AUTO per OS; with fewer, it does not ship for that OS. For every OS the report gives next to it the number of applications with status AUTO (mode AUTO), with status MANUAL (mode MANUAL\_ONLY) and UNKNOWN or quarantined (mode OFF). The number with status AUTO is not promised: on Windows it may be small at first (13.7), and the product description states the figure that was measured. Always UNKNOWN or OFF, whatever the tests say: terminals, IDEs, remote-desktop and VM clients, password managers, games, editors that draw their own text without a text interface, and elevated windows.

**Fail-safe summary.** A missing permission, an unreadable element, an unlisted application, an unresolved focus change and a failed query all produce UNKNOWN, and UNKNOWN records nothing. The only way to get the hotkey in an application is a passing manual suite there, and the only way to get automatic correction is a passing automatic suite there with an adapter that has all four capabilities.

### 13.9 The application layer

The runtime library (D8) is not the product. The requirements below cover what the user installs and sees. They are tested by a scripted checklist on the release candidate: fresh install, upgrade from the previous version, permission revoked while running, crash, uninstall.

| ID | Area | Requirement |
| --- | --- | --- |
| AP-1 | First run and permissions | The first screen says what is observed (keystrokes in text fields, processed on the device, never stored or sent, 13.4) and asks for the OS permissions one at a time, each with a link to the right system settings pane. Until all are granted the state is OFF and the status icon names the missing permission. The user can quit from this screen |
| AP-2 | Status and control | A menu-bar or tray icon always shows one of Active, Paused, Manual only, Off. One click pauses (the gate becomes DENY, so nothing is recorded). "Pause for this application" adds it to the application list |
| AP-3 | Layout pair | Detected from the installed input sources, where supported means that the fingerprint equals the table (13.7): when exactly one supported English layout and one supported Russian layout are installed, that pair is used; otherwise the user chooses; an unsupported variant switches the tool off for it with the notice of failure row 7 |
| AP-4 | Settings | Automatic correction on or off; hotkey (with the conflict procedure of 13.3); "Esc also undoes" per application; application list with the reason for each entry (blacklist, quarantine) and a re-enable button; exception list (view, delete one entry, clear all, export); start at login; diagnostics opt-in; update channel; reset |
| AP-5 | Storage and migration | Settings and the exception list live per user in the OS's application-data directory as one versioned file with a `schema_version`. A newer version migrates an older file forward after making a backup copy; an unreadable file is renamed and replaced by defaults with a notice. "Reset" restores defaults; "Delete all data" removes settings, exceptions and diagnostics. The exception list is encrypted with the OS key store (13.3) |
| AP-6 | Install and uninstall | A signed installer or package, per user and without elevation where the OS allows. The uninstaller removes the application, its login item or startup entry and, on request, all user data, and leaves no hook or helper process running |
| AP-7 | Autostart and crash recovery | Starts at login (a setting). A supervisor restarts the engine after a crash; two crashes within 60 seconds give MANUAL\_ONLY (failure row 11). Crash reports contain no typed content and are sent only with opt-in |
| AP-8 | Notifications | Non-blocking, never take focus, rate-limited as in 13.5; each offers one action (open settings, re-enable) |
| AP-9 | Updates | Application, model, lexicon and calibration package are signed and versioned (DP-7). A new package is switched in only at restart or when no word is in progress; staged rollout; one-step rollback; a failed verification keeps the previous package (failure row 12) |
| AP-10 | Accessibility of the tool's own interface | The settings, the notices and the status icon work with VoiceOver and NVDA, and a correction is not announced twice (14.4) |
| AP-11 | Diagnostics | Counters only (corrections, undos, manual conversions, reason codes, incidents). They are shown to the user before the opt-in and can be exported by the user |


## 19. Appendices

### 19.1 Physical key map (ANSI US layout and Russian ЙЦУКЕН)

The map is the single source of truth for the mapper (section 5.4) and for the key tokens (section 5.1). It was generated from the tables used in the feasibility experiments, and a round-trip test (text to keys to text, both layouts) passed with zero failures. A key id is the position in the order below, 0 to 46. A key token is `1 + 2·id + shift`, so tokens run from 1 to 94; `PAD` = 0, `BOS` = 95, `EOS` = 96, vocabulary size 97.

| Id | EN | EN with Shift | RU | RU with Shift | Note |
| --- | --- | --- | --- | --- | --- |
| 0 | \` | \~ | ё | Ё | letter-key; grave accent |
| 1 | 1 | ! | 1 | ! | same |
| 2 | 2 | @ | 2 | " | Shift differs |
| 3 | 3 | # | 3 | № | Shift differs |
| 4 | 4 | $ | 4 | ; | Shift differs |
| 5 | 5 | % | 5 | % | same |
| 6 | 6 | ^ | 6 | : | Shift differs |
| 7 | 7 | & | 7 | ? | Shift differs |
| 8 | 8 | \* | 8 | \* | same |
| 9 | 9 | ( | 9 | ( | same |
| 10 | 0 | ) | 0 | ) | same |
| 11 | - | \_ | - | \_ | same |
| 12 | = | + | = | + | same |
| 13 | q | Q | й | Й |  |
| 14 | w | W | ц | Ц |  |
| 15 | e | E | у | У |  |
| 16 | r | R | к | К |  |
| 17 | t | T | е | Е |  |
| 18 | y | Y | н | Н |  |
| 19 | u | U | г | Г |  |
| 20 | i | I | ш | Ш |  |
| 21 | o | O | щ | Щ |  |
| 22 | p | P | з | З |  |
| 23 | \[ | { | х | Х | letter-key |
| 24 | \] | } | ъ | Ъ | letter-key |
| 25 | \\ | \| | \\ | / | Shift differs; EN pipe |
| 26 | a | A | ф | Ф |  |
| 27 | s | S | ы | Ы |  |
| 28 | d | D | в | В |  |
| 29 | f | F | а | А |  |
| 30 | g | G | п | П |  |
| 31 | h | H | р | Р |  |
| 32 | j | J | о | О |  |
| 33 | k | K | л | Л |  |
| 34 | l | L | д | Д |  |
| 35 | ; | : | ж | Ж | letter-key |
| 36 | ' | " | э | Э | letter-key |
| 37 | z | Z | я | Я |  |
| 38 | x | X | ч | Ч |  |
| 39 | c | C | с | С |  |
| 40 | v | V | м | М |  |
| 41 | b | B | и | И |  |
| 42 | n | N | т | Т |  |
| 43 | m | M | ь | Ь |  |
| 44 | , | < | б | Б | letter-key |
| 45 | . | > | ю | Ю | letter-key |
| 46 | / | ? | . | , | Both states differ |

**Facts derived from the table, used elsewhere in this specification**

- **Letter-keys.** Seven keys produce a Russian letter and an English punctuation mark: ids 0, 23, 24, 35, 36, 44, 45 (ё х ъ ж э б ю against \` \[ \] ; ' , .). Segmentation and candidate enumeration in section 5.3 depend on this.
- **Digit row.** Unshifted digits and the symbols `! % * ( ) - = _ +` are identical in both layouts. Shifted `@ # $ ^ &` on the English layout are `" № ; : ?` on the Russian one, so a Shift-digit symbol is evidence about the layout only for these five keys.
- **Punctuation that moves.** English `/` is Russian `.`; English `?` is Russian `,`; English `|` is Russian `/`. A sentence ending typed on the wrong layout therefore changes its punctuation, which the mapper handles and the classifier never sees as text.
- **Not on the map.** Keys outside these 47 (the extra key of ISO keyboards, the numeric pad, AltGr and other secondary layers, other layouts such as Ukrainian or the Russian typewriter variant) are outside the first release (section 4.2). A new layout enters as a new row-set with the same key ids and its own round-trip test (section 14.1).

### 19.2 Glossary

| Term | Meaning in this specification |
| --- | --- |
| ABSTAIN | The policy outcome "leave the text as typed". It is not a trained class (section 5.2) |
| Base rate (π) | Share of words that really were typed on the wrong layout in a given deployment. It is far below 50%, and it sets the precision of every threshold (section 5.5) |
| Calibration | The property that a predicted probability of 0.99 is right 99% of the time. Measured by ECE and fixed by temperature scaling (section 10.1) |
| Cluster bootstrap | Confidence intervals computed by resampling users or documents instead of single words, because words from one writer are not independent (section 11.3) |
| ECE | Expected calibration error: the weighted gap between confidence and accuracy over confidence bins |
| False correction (FC) | A correct word that the product rewrote. The headline error of this task (section 11.1) |
| Key token | One integer for a physical key and its Shift state. The model input; independent of the active layout |
| Kill criterion | A written rule that drops the neural network if it does not beat the statistical baseline at the same false-correction rate (EV-12) |
| Layout | A mapping from physical keys to characters. Here: ANSI US English and Russian ЙЦУКЕН |
| Letter-key | A key that is a letter on the Russian layout and punctuation on the English layout (section 19.1) |
| Mapper | The deterministic table that converts a key sequence into text in the target layout. It never generates new text (section 5.4) |
| ONNX Runtime (ORT) | The inference engine used for the neural network on CPU. Supports static INT8 quantization |
| OTHER | The third class: code, identifiers, URLs, numbers, transliteration, key-mash. It stops the network from forcing every string into EN or RU |
| Prior shift | A change in class proportions between training data and deployment. Corrected by multiplying class probabilities by π\_deploy / π\_train (section 10.2) |
| PTQ, QAT, QDQ | Post-training quantization; quantization-aware training; the quantize-dequantize operator format used by static INT8 in ORT |
| Rule of three | If no failures appear in n independent trials, the 95% upper bound on the failure rate is about 3/n. It sets the test size (section 11.3) |
| Temperature scaling | Dividing logits by a single scalar fitted on validation data so that probabilities are calibrated (section 10.1) |
| Witten-Bell smoothing | An n-gram back-off method that gives unseen continuations a probability proportional to how many distinct continuations a context has. The baseline's smoothing |
| Word candidate | A run of keys that may be one word, after segmentation on keys (section 5.3). The unit that is classified and corrected |
| Wrong-layout word | A word typed with the layout of the other language, for example `ghbdtn` for привет |
| p50, p95, p99 | Percentiles of latency over warm, repeated calls (section 4.4) |
| Capability | One of READ\_RANGE, REPLACE\_RANGE, READBACK, ROLLBACK, SYNTHETIC\_INPUT: what an OS adapter can do in one control class. The mode of an application is derived from them (section 13.7, reference function engine\_mode) |
| Evidence level | TEXT\_FIXED, REFERENCE\_VERIFIED, INTEGRATION\_VERIFIED or RELEASE\_GATE\_PASSED: what a statement of readiness rests on (section 16.1) |
| G-EVENT, G-FIELD | The two integrity guarantees of section 13.2: no physical key is lost, duplicated, held or replayed (by design); the field after a replacement holds the new text or the original text, and the outcome UNRECOVERED is reported and measured |
| Layout fingerprint | SHA-256 of the 94 characters that a layout gives for the 47 keys with Shift off and on. The only way a layout counts as supported (section 13.7) |
| Outcome of a replacement | VERIFIED (new text read back), RESTORED (original text read back after a failure), UNRECOVERED (anything else, including an unreadable range) or ABORTED (nothing was written); section 13.2 |
| Quarantine | The state of an application after a replacement incident: its gate is DENY until restart or until the user re-enables it (section 13.5, row 10) |
| Support status | UNKNOWN, MANUAL or AUTO: the result of the test suite of one application (section 13.8). It can never exceed what the capabilities allow |
| w\_ship | The lower end of the 90% cluster-bootstrap interval of the observed wrong-layout rate; the value of w stored in D5 (section 10.2) |

### 19.3 References

The links below were opened during the work. Prior-art projects are linked where they appear in section 3.2.

**Data and sources**

- [anzorq/kbd\_lat-835k\_ru-3M dataset card](https://huggingface.co/datasets/anzorq/kbd_lat-835k_ru-3M): Kabardian in Latin script plus Russian Wikipedia lines, licence "unknown" (sections 8.2 and 17).
- [wordfreq on PyPI](https://pypi.org/project/wordfreq/): multi-source word-frequency lists used for the proxy experiments.
- [FrequencyWords](https://github.com/hermitdave/FrequencyWords): OpenSubtitles-based frequency lists.
- [Tatoeba](https://tatoeba.org/): short parallel sentences.
- [Wikimedia dumps](https://dumps.wikimedia.org/): Wikipedia text for vocabulary and sentences.

**Prior art cited in sections 3 and 17**

- [KeyboardSwitcher](https://github.com/kertser/KeyboardSwitcher): LSTM with ONNX Runtime, outputs N/A, en, he, ru.
- [Rekey](https://github.com/rstqDev/rekey): hashed word table, character-trigram fallback, self-reported results on 54,000 words.

**Runtime and compression**

- [ONNX Runtime: quantize models](https://onnxruntime.ai/docs/performance/model-optimizations/quantization.html): static and dynamic quantization, QDQ and QOperator formats, x86-64 warnings.
- [Core ML Tools: optimization overview](https://apple.github.io/coremltools/docs-guides/source/opt-overview.html): palettisation, quantization and pruning, without numeric speed-ups.
- [arXiv 2606.22283](https://arxiv.org/pdf/2606.22283): direct-dispatch measurement of Apple Neural Engine call overhead.

**Methods**

- Guo, Pleiss, Sun, Weinberger (2017). [On Calibration of Modern Neural Networks](https://arxiv.org/abs/1706.04599): temperature scaling.
- Saerens, Latinne, Decaestecker (2002). Adjusting the outputs of a classifier to new a priori probabilities. Neural Computation 14(1): the prior-shift correction.
- Hanley, Lippman-Hill (1983). If nothing goes wrong, is everything all right? JAMA 249(13): the rule of three.
- Witten, Bell (1991). The zero-frequency problem. IEEE Transactions on Information Theory 37(4): the baseline's smoothing.
- Kim (2014). [Convolutional Neural Networks for Sentence Classification](https://arxiv.org/abs/1408.5882) and Zhang, Zhao, LeCun (2015). [Character-level Convolutional Networks for Text Classification](https://arxiv.org/abs/1509.01626): the architecture family.
- Joulin, Grave, Bojanowski, Mikolov (2016). [Bag of Tricks for Efficient Text Classification](https://arxiv.org/abs/1607.01759): hashed n-gram bag baseline.
- Jacob et al. (2018). [Quantization and Training of Neural Networks for Efficient Integer-Arithmetic-Only Inference](https://arxiv.org/abs/1712.05877): INT8 scheme.
- Müller, Kornblith, Hinton (2019). [When Does Label Smoothing Help?](https://arxiv.org/abs/1906.02629): effect of smoothing on calibration.
- Loshchilov, Hutter (2019). [Decoupled Weight Decay Regularization](https://arxiv.org/abs/1711.05101): AdamW.
- [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119): MUST, SHOULD, MAY.

### 19.4 Benchmark source and commands for the Apple M1 Max

The two programs below produced the native figures of section 18.7. They are short on purpose, so that anyone can read them and run them on a reference device. They are naive: no SIMD intrinsics, no blocking, random weights, one thread. They give an upper bound on what an optimised kernel needs and a first latency tier for the M1 Max. They are not the release benchmark (D7), which must use the trained files (section 12.4).

```
# Build. Apple clang from the Xcode command-line tools. NEON is part of the arm64 baseline, so no flag
# is needed; adding -mcpu=apple-m1 was NOT tested here, so compare both builds.
# On x86-64 Linux add -march=native: the figures of section 18.7 used it, and without it the same
# loop took about twice as long on the cloud CPU (68 against 36 microseconds, 64 channels, 9 keys).
clang -O3 -o cnn_bench cnn_bench.c
clang -O3 -o ngram_bench ngram_bench.c

# Network forward pass. Arguments: positions L, channels c, embedding dimension e.
# The trained model uses e = 32 at 64 channels; section 18.7 used e = 16, a lower bound.
./cnn_bench 9 64 32
./cnn_bench 22 64 32
./cnn_bench 9 32 32
./cnn_bench 9 128 32

# Hash-table probes for the statistical stage. Argument: number of table entries.
./ngram_bench 54000
./ngram_bench 540000
./ngram_bench 5400000
```

Run each command at least three times at different times of day, on mains power with low-power mode off, and report all three p50 values. Record the chip, the macOS version, the compiler version and the flags in the run record (section 15.2). The programs print one line each: parameters, multiply-adds, then p50, p95 and p99 over 20,000 timed calls after 2,000 warm-up calls. The embedding table has 64 rows instead of the specified 97; this does not change the cost of the forward pass.

**`cnn_bench.c`**

```c
// Naive float32 char-CNN forward (embedding -> 3 conv1d (k=3,5,3) -> ReLU -> max+mean pool -> linear), single thread.
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <math.h>
static double now_us(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return t.tv_sec*1e6+t.tv_nsec/1e3;}
static float frand(void){return (float)rand()/RAND_MAX-0.5f;}
static void conv(const float*in,int L,int cin,const float*w,const float*b,int K,int cout,float*out){
  int pad=K/2;
  for(int t=0;t<L;t++){
    float*o=out+t*cout; for(int j=0;j<cout;j++)o[j]=b[j];
    for(int k=0;k<K;k++){int s=t+k-pad; if(s<0||s>=L)continue; const float*x=in+s*cin; const float*wk=w+k*cin*cout;
      for(int i=0;i<cin;i++){float xv=x[i]; const float*wi=wk+i*cout; for(int j=0;j<cout;j++)o[j]+=xv*wi[j];}}
    for(int j=0;j<cout;j++)if(o[j]<0)o[j]=0;
  }
}
int cmp(const void*a,const void*b){double x=*(double*)a,y=*(double*)b;return (x>y)-(x<y);}
int main(int argc,char**argv){
  int L=atoi(argv[1]),c=atoi(argv[2]),e=atoi(argv[3]); int V=64,iters=20000;
  float*emb=malloc(V*e*4);for(int i=0;i<V*e;i++)emb[i]=frand();
  float*w1=malloc(3*e*c*4),*w2=malloc(5*c*c*4),*w3=malloc(3*c*c*4),*b=calloc(c,4),*wo=malloc(2*c*4);
  for(int i=0;i<3*e*c;i++)w1[i]=frand()*.1f;for(int i=0;i<5*c*c;i++)w2[i]=frand()*.1f;for(int i=0;i<3*c*c;i++)w3[i]=frand()*.1f;for(int i=0;i<2*c;i++)wo[i]=frand();
  float*x0=malloc(L*e*4),*h1=malloc(L*c*4),*h2=malloc(L*c*4),*h3=malloc(L*c*4);
  int ids[512];for(int i=0;i<L;i++)ids[i]=1+rand()%(V-1);
  long params=V*e+3*e*c+5*c*c+3*c*c+3*c+2*c+1; double macs=(double)L*(3*e*c+5*c*c+3*c*c);
  double*lat=malloc(iters*8); volatile float sink=0;
  for(int it=-2000;it<iters;it++){
    double t0=now_us();
    for(int t=0;t<L;t++)memcpy(x0+t*e,emb+ids[t]*e,e*4);
    conv(x0,L,e,w1,b,3,c,h1);conv(h1,L,c,w2,b,5,c,h2);conv(h2,L,c,w3,b,3,c,h3);
    float mx[512],mean[512];for(int j=0;j<c;j++){mx[j]=-1e30f;mean[j]=0;}
    for(int t=0;t<L;t++)for(int j=0;j<c;j++){float v=h3[t*c+j];if(v>mx[j])mx[j]=v;mean[j]+=v;}
    float z=0;for(int j=0;j<c;j++)z+=mx[j]*wo[j]+mean[j]/L*wo[c+j]; sink+=z;
    double t1=now_us(); if(it>=0)lat[it]=t1-t0; {int q=(it+2000)&7; ids[q]=1+(unsigned)(ids[q]*7+it+2000)%(V-1);}
  }
  qsort(lat,iters,8,cmp);
  printf("L=%3d c=%3d e=%2d params=%7ld MACs=%8.2fM  p50=%8.1f us  p95=%8.1f us  p99=%8.1f us\n",L,c,e,params,macs/1e6,lat[iters/2],lat[(int)(iters*.95)],lat[(int)(iters*.99)]);
  return 0;
}
```

**`ngram_bench.c`**

```c
// Worst-case-ish micro-benchmark of the statistical stage: open-addressing hash table of n-gram entries (16 B/slot),
// random access pattern (every lookup is an independent cache-unfriendly probe).
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <time.h>
static double now_us(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return t.tv_sec*1e6+t.tv_nsec/1e3;}
typedef struct{uint64_t key;float lp;float bow;}slot;
static uint64_t mix(uint64_t x){x^=x>>33;x*=0xff51afd7ed558ccdULL;x^=x>>33;x*=0xc4ceb9fe1a85ec53ULL;x^=x>>33;return x;}
int cmp(const void*a,const void*b){double x=*(double*)a,y=*(double*)b;return (x>y)-(x<y);}
int main(int argc,char**argv){
  size_t entries=argc>1?atol(argv[1]):540000; size_t nslots=1; while(nslots<entries*2)nslots<<=1;
  slot*tab=calloc(nslots,sizeof(slot)); uint64_t*keys=malloc(entries*8);
  for(size_t i=0;i<entries;i++){uint64_t k=mix(i*2654435761ULL+12345)|1; keys[i]=k; size_t h=mix(k)&(nslots-1); while(tab[h].key)h=(h+1)&(nslots-1); tab[h].key=k;tab[h].lp=-2.0f;tab[h].bow=-0.5f;}
  int T=20000, positions=9, lookups_per_pos=3, renderings=2; double*lat=malloc(T*8); volatile float sink=0; uint64_t rng=88172645463325252ULL;
  for(int it=-2000;it<T;it++){
    uint64_t q[64]; int nq=positions*lookups_per_pos*renderings;
    for(int i=0;i<nq;i++){rng^=rng<<13;rng^=rng>>7;rng^=rng<<17; q[i]=(i%3==2&&(rng&1))? (rng|1) /*miss*/ : keys[rng%entries];}
    double t0=now_us(); float s=0;
    for(int i=0;i<nq;i++){size_t h=mix(q[i])&(nslots-1); while(tab[h].key && tab[h].key!=q[i])h=(h+1)&(nslots-1); s+= tab[h].key? tab[h].lp : tab[h].bow;}
    double t1=now_us(); sink+=s; if(it>=0)lat[it]=t1-t0;
  }
  qsort(lat,T,8,cmp);
  printf("table: %zu entries, %zu slots x16B = %.1f MB; %d lookups per token (2 renderings x %d positions x %d): p50=%.2f us p95=%.2f us p99=%.2f us\n",entries,nslots,nslots*16/1e6,positions*lookups_per_pos*renderings,positions,lookups_per_pos,lat[T/2],lat[(int)(T*.95)],lat[(int)(T*.99)]);
  return 0;
}
```

### 19.3 Traceability: how each requirement is verified

Every requirement identifier of this document is verified by at least one level of the test plan (15.3), by a requirement test of 13.6, by a conformance test of 20.13, or by an acceptance gate of 11.2. The table is checked by the script `audit/L5_trace.py`, which reads this document and fails when an identifier is used but not defined, defined but never used, or missing here. A requirement test (RT-1 to RT-18) or a conformance test (CT-1 to CT-6) is its own verification and is not listed.

| Requirement | Verified by |
| --- | --- |
| MD-1, MD-4, MD-5 | Unit and Property levels (output shape, parameter count of the model built from 7.1, token bounds), CT-1 |
| MD-2, MD-7 | Acceptance level: EV-12 on R-ACC; the baseline vectors of CT-1 |
| MD-3, MD-9, MD-10 | Performance and Latency by phase levels; EV-14, EV-21 |
| MD-6 | Property and Model parity levels (padded and unpadded logits agree within 1e-5) |
| MD-8 | Acceptance level: the per-length slices of 11.4, EV-4 to EV-6; model card D9 |
| MD-11 to MD-14 | CT-1, CT-5 and the Independent implementation level |
| DT-1, DT-9 | Unit level: D2 rebuilds an identical manifest from a seed (15.1); EV-16 |
| DT-2 | Property level (no character enters the model), CT-1 |
| DT-3, DT-10 | Licence register check of D2 and of the release package D10; EV-18 |
| DT-4 | Regression level: stress sets, EV-2, EV-9 |
| DT-5 to DT-8 | Unit level on the pipeline and the harness (disjoint splits, hash rule, role tag, log of locked-set use); Acceptance level (11.6) |
| TR-1 to TR-8 | Regression and Acceptance levels: run record and seeds (EV-13, EV-16); the step grid and the size grid of 9.4 |
| CA-1 to CA-4, CA-7 | Policy level; EV-7 |
| CA-5, CA-9, CA-10, CA-11 | CT-3 (the property, negative and fault-injection tests of `conformance.py`) |
| CA-6 | Acceptance level: the freeze is logged before R-ACC is read (11.6) |
| CA-8 | EV-10 |
| DP-1, DP-2, DP-4 | Model parity and Performance levels; EV-14 |
| DP-3 | Performance level (the written measurement on a reference device) |
| DP-5 | CT-1 and CT-3 (64-bit lexicon keys, formats LFB1 and LFL1) |
| DP-6 | Soak and Performance levels; RT-8 |
| DP-7, DP-8 | End to end level; RT-12 (failure table); CT-3 (a bad package or table is refused) |
| AP-1 to AP-9, AP-11 | End to end level; AP-5 and AP-11 also the Privacy level |
| AP-10 | End to end level with VoiceOver and NVDA |
| EV-1 to EV-13 | Acceptance level (each is itself a gate of 11.2) |
| EV-14 | Performance level |
| EV-15 | Fault injection and End to end levels; RT-4 |
| EV-16 | Acceptance level: one command produces the report D6 |
| EV-17 | The continuous-integration gate (unit, property, parity and regression levels) |
| EV-18 | Release checklist: model card D9 and release package D10 |
| EV-19 | Regression level |
| EV-20 | Review of every report D6: each statement of readiness names its evidence level |
| EV-21 | Latency by phase level |


## 20. Reference implementation, formats and test vectors

### 20.1 Status, assembly and interface

**Status.** This section is normative (4.4). It is the executable form of every deterministic rule of sections 5, 7.7, 10 and 13: the key tables and tokens, segmentation, shape guards, calibration arithmetic, the priority matrix, the event machine, manual conversion, the EV-1 statistic, the baseline model, the two table formats and, in 20.14, the adapter contract, the mode of the engine, the replacement transaction, the identification of a layout and the check that the stream of key events is complete. Where the prose of another section and this code disagree, the code and the vectors of 20.12 win, and the prose is a defect of the document that must be corrected. The classifier is injected as a function, so the same code runs with the network, with the baseline or with a stub.

**What is not here.** The operating-system adapters themselves (event capture, layout detection, the context gate, the text interface of each application) cannot be written as portable code. Sections 13.1, 13.2, 13.7 and 13.8 specify them; the event machine of 20.7 and the contract of 20.14 (`Adapter`, `run_transaction`, `HookHealth`) are the interface they drive, and the algorithm of the replacement transaction is part of this reference. What the reference proves is the algorithm (evidence level REFERENCE\_VERIFIED, 16.1); what a real application does is proved only by the integration tests RT-1 to RT-18 on the real operating systems. Training is specified in section 9. The forward pass of the network in 20.11 is a slow reference for tests; the production runtime uses a native implementation that is checked against it.

**Assembling the files.** The code blocks of 20.2 to 20.11 and the code block of 20.14 are consecutive parts of one Python 3.9+ module, `lfengine.py`, which uses only the standard library. Copy them into one file in the order 20.2, 20.3, and so on up to 20.11, then 20.14 (20.12 and 20.13 hold other files and are skipped), with exactly two empty lines between one block and the next; each block starts with a marker comment `# ==== 20.n`. The vector generator of 20.12 is the second file, `vectors.py`. Run `python vectors.py > vectors_out.json` and compare the output with the expected JSON of 20.12. The property, negative and fault-injection tests of 20.13 are the third file, `conformance.py`; it is printed in three code blocks, which are written into the file one after the other with exactly one empty line between one part and the next. All files are UTF-8 with LF line ends; a file is the reference file when it is identical to it byte for byte. `python conformance.py` prints OK, and so does `python -O conformance.py`: neither the engine nor the tests rely on the `assert` statement, so no check disappears when Python is run optimised. An implementation in another language is conformant when, for every entry of that JSON, its own function gives the same result: floats to the precision shown, hashes, token lists and byte counts exactly.

| Function or class | Part | Purpose |
| --- | --- | --- |
| `Key`, `render`, `token`, `tokens`, `keys_from_text` | 20.2 | Key tables, Caps Lock, rendering, model tokens |
| `candidate` | 20.3 | The single word candidate of a run for a target layout |
| `shape_guard` | 20.4 | URL, e-mail, dotted name, camelCase and key-walk guards |
| `score`, `deployment_prior`, `check_calibration_package`, `example_cal`, `cal_to_json`, `cal_from_json` | 20.5 | Temperature, priors, the score in nats, the calibration package |
| `decide` | 20.6 | The priority matrix of 10.4 for one run |
| `Engine` (`on_event`, `set_gate`, `set_mode`, `on_outcome`, `undo`, `tick`) | 20.7 | Buffer, run credit, resets, cool-down, decision at Space, the undo snapshot; only the mode `AUTO` records and decides |
| `manual_convert` | 20.8 | Pure key-for-key conversion of a selection |
| `poisson_upper`, `ev1_bound`, `ev1_pass` | 20.9 | The EV-1 pass rule of 11.3 |
| `WittenBell`, `baseline_logits`, `lfb_pack`, `lfb_load`, `lfb_logp`, `lex_key`, `lfl_pack`, `lfl_load` | 20.10 | The baseline of 7.7 and the formats `LFB1`, `LFL1` |
| `lfw_pack`, `lfw_load`, `lfw_forward`, `toy_weights` | 20.11 | The format `LFW1`, a reference forward pass, deterministic toy weights |
| `Adapter`, `SimField`, `AdapterError`, `engine_mode`, `classify_outcome`, `run_transaction`, `layout_fingerprint`, `identify_layout`, `HookHealth` | 20.14 | The adapter contract and its test double with fault injection, the mode of the engine, the replacement transaction and its outcome, the identity of a layout, the check that the key stream is complete |
| vectors.py (script) | 20.12 | Golden vectors for every function above, printed as one JSON document |
| conformance.py (script) | 20.13 | Property, negative and fault-injection tests and the conformance checks CT-1 to CT-6 |

**Order of implementation.** (1) Key tables, tokens and rendering (20.2), checked against the first vectors. (2) Candidate and shape guards (20.3, 20.4). (3) Calibration arithmetic and the priority matrix (20.5, 20.6) with a stub scorer. (4) The event machine (20.7) against the traces of 20.12. (5) The baseline tables of 7.7 and the EV-12 harness, so the baseline works alone before any network exists. (6) Network training (section 9) and export to `LFW1`. (7) The operating-system adapters of 13.7, macOS first, driving the event machine. (8) The application layer of 13.9. (9) The end-to-end suite of 15.3 and the acceptance run of section 11.

### 20.2 Key tables, tokens, Caps Lock, rendering

[code block of 20.2 removed: 88 lines]

### 20.3 Word candidate (segmentation of one run)

A *run* is the printable keys of the 47-key block typed since the last boundary. For the hypothesis "the user meant the other layout" the function returns the one candidate or `None`. Punctuation is judged by what the key is in the target layout, so the seven letter-keys (`ё х ъ ж э б ю`) are letters, never separators, when the target is Russian. The rules of 5.3 and the golden cases of 20.12 follow from this code.

[code block of 20.3 removed: 35 lines]

### 20.4 Shape guards

Guards veto any action, in both directions, when either reading of the run looks like a URL, an e-mail address, a dotted file or domain name, a camelCase identifier or a walk along one keyboard row. The suffix list is the starting list of the first release and is extended by D3 from the sources of 8.9.

[code block of 20.4 removed: 43 lines]

### 20.5 Calibration, priors, thresholds in nats, the calibration package

`score` is the whole chain of 10.1: temperature, prior-shift correction with the full vector of 10.2, then the two-way log-odds "Russian or not". Thresholds are stored and compared in nats; `check_calibration_package` is the load-time validation of CA-9 and rejects a probability stored where nats are expected. `example_cal` is the set of starting values of 10.1 to 10.3 and the fixture of every vector below; a real package is fitted (10.3), not typed. The package is stored as JSON (D5), written by `cal_to_json`, with the sets of the allow-lists as sorted lists.

[code block of 20.5 removed: 206 lines]

### 20.6 Decision for one run (the priority matrix of 10.4)

`decide` is the normative form of the priority matrix of 10.4. It takes the keys typed since the last boundary, the active layout, the calibration package and an injected scorer (a function from a token list to three logits: the network, the baseline or a stub), and returns a `Decision`. The first matching rule wins, in this order: no candidate, one key, user exception, shape guard, acronym of the active language, word of the active language, two keys, score against the threshold. Every KEEP carries a reason string; the reasons are the vocabulary of the vectors in 20.12. `margin` is the score minus the threshold, in nats, and is set only for model decisions.

[code block of 20.6 removed: 57 lines]

### 20.7 Event state machine: buffer, run state, boundary

The event machine is the interface that the operating-system adapters of 13.2 drive; it contains no platform code. It consumes events in arrival order and returns a `Decision` only at a Space that ends a non-empty run. Its rules, which the traces of 20.12 pin down:

- **Gate.** Any gate verdict other than ALLOW (13.1) discards the buffer and the run state, and while it lasts every event is ignored: nothing is stored, counted or classified.
- **Run.** Keys are appended with the layout id sampled at each key. Up to 64 keys are kept; a longer word is marked `overflow` and is KEEP. A key whose layout differs from the layout of the first key drops the whole word (all later keys are ignored until the next Space) and clears the run credit (5.3).
- **Boundary.** At Space the run is taken and cleared. No decision if the word was dropped or empty. KEEP `overflow`; KEEP `layout_changed_at_boundary` if the layout at Space differs from the run's; KEEP `cooldown` while the cool-down after an undo lasts (until 3 word decisions have been suppressed and 10 s have passed); otherwise `decide`.
- **Prior state** (10.2). `run` if the run credit is above 0, else `after_switch` if a manual layout change preceded the word, else `default`.
- **Run credit** (feedback cap, 10.2). A CONVERT decided without the run prior sets the credit to 3; a CONVERT decided with it lowers the credit by 1, so a chain of run-assisted conversions cannot sustain itself. A KEEP for evidence (`user_exception`, `acronym`, `lexicon_active`, `abstain`) clears the credit. Undo clears it and starts the cool-down.
- **Other events.** `backspace` removes the last key of the run (and clears the credit if the run is empty and the word was not dropped). `layout` (a manual change; the tool never changes the layout itself) drops the current word, sets the `after_switch` flag and clears the credit. `break` (click, focus change, paste, Enter, Tab, arrows, chords, input-method activity, sleep, lock) empties the buffer and clears the credit.

[code block of 20.7 removed: 195 lines]

### 20.8 Manual conversion (hotkey)

Manual conversion (13.3) is a pure key-position mapping of the selected text: no peeling of punctuation, no model, no thresholds. The direction is decided by majority of letters: more Cyrillic letters than Latin ones means Russian to English, otherwise English to Russian; a selection with no letters at all gets no direction and is returned unchanged. Characters that are not on the source layout (emoji, accented letters, other scripts) are copied unchanged, so the length in code points never changes and the original selection can always be restored from the result.

[code block of 20.8 removed: 28 lines]

### 20.9 Acceptance statistics (EV-1)

`ev1_bound` and `ev1_pass` are the executable form of the rule of 11.3. A cluster is one (user, document) pair; the bound is the exact Poisson 95% upper limit for the number of clusters, multiplied by the size of the largest cluster and divided by the number of correct words. The per-user and per-document caps on the share of words (8.5) are applied to the data before these functions are called.

[code block of 20.9 removed: 32 lines]

### 20.10 Statistical baseline (Witten-Bell over key tokens) and the table formats LFB1 and LFL1

This block is the normative form of 7.7. `WittenBell.fit` counts contexts of 0, 1 and 2 tokens over the rows of `S-TRAIN` (each row is `BOS`, key tokens, `EOS` or a prefix without `EOS`; a row may carry a multiplicity). `WittenBell.logp` returns the sum of the log-probabilities of every token after `BOS`, with no length normalisation. `baseline_logits` adds the class prior and returns three logits that enter `score` (20.5) with `kind="ngram"`.

`LFB1` stores, for each class and each order, the contexts (key, total, distinct) and the pairs (key, count) as sorted records of 64-bit FNV-1a hashes; a context hash is `FNV-1a-64(0xC0+k ‖ context bytes)` and a pair hash is `FNV-1a-64(0xD0+k ‖ context bytes ‖ next token)`. Two different contexts or pairs of one class and order could in theory share a 64-bit key, so lfb\_pack fails the build if they do. `LFL1` stores the stage-4 sets as sorted unique 64-bit keys per table tag. `lfb_logp` over a loaded file equals `WittenBell.logp` of the packed model to float rounding (MD-12).

[code block of 20.10 removed: 197 lines]

### 20.11 Network weight file LFW1 and the reference forward pass

`LFW1` is the portable weight file that the trainer exports next to the ONNX file of DP-1 (MD-14). The header is the magic, the channel count, the embedding width and the kernel list; the body is float32 little endian in a fixed order: the embedding table `[97][e]`, then for each convolution its weight `[ch][cin][k]` and bias `[ch]`, then the head weight `[3][2*ch]` and bias `[3]`. `lfw_forward` is deliberately slow and simple (same-padding convolutions, ReLU, max and mean pooling over every position, `BOS` and `EOS` included, true length without padding); it exists to check a native implementation, which MUST agree with it on the toy weights of `toy_weights` to 1e-5 and on the exported weights of the trained network to 1e-4 per logit (MD-14). `toy_weights` uses integer arithmetic only, so every language reproduces the same file byte for byte.

[code block of 20.11 removed: 75 lines]

### 20.12 Golden test vectors

`vectors.py` imports `lfengine.py`, runs the functions of 20.2 to 20.11 and 20.14 on fixed inputs and prints one JSON document. The expected output is given below it. An implementation conforms when its own generator prints the same document: strings, integers, booleans, token lists, hashes and byte counts exactly; floats as printed, that is equal after rounding to the number of decimals shown. The output does not depend on the hash seed of the interpreter (CT-2). `sha256_16` is the first 16 hex digits of the SHA-256 of the file bytes.

| Key | What it pins down | Part |
| --- | --- | --- |
| `render`, `caps`, `prefix`, `tok25` | Typed keys to the text of the other layout, model tokens with and without `EOS`, Caps Lock per layout, the 20-key limit | 20.2 |
| `caps_all` | Twelve keys in every combination of Shift and Caps Lock (48 entries): the character on each layout and the token | 20.2 |
| `cands` | The single candidate: leading opener, core, trailing punctuation, the seven letter-keys, no candidate | 20.3 |
| `guards` | Reason codes of the shape guards | 20.4 |
| `priors`, `lambdas`, `scores`, `cal_json` | Prior vectors, thresholds in nats, the score, the bytes of the calibration package | 20.5 |
| `decide` | Rows 5 to 12 of the priority matrix with a stub scorer | 20.6 |
| `trace_run`, `trace_undo`, `scen` | Run credit, cool-down, boundaries, gate, layout change | 20.7 |
| `undo` | The undo snapshot (17 steps): its content, the expiry at exactly 10,000 ms and at 100 characters, one snapshot only, Caps Lock, and every event that destroys it | 20.7 |
| `manual` | Manual conversion | 20.8 |
| `ev1`, `poisson` | The EV-1 pass rule | 20.9 |
| `wb`, `wb_score`, `fnv`, `lfl` | Baseline log-probabilities, `LFB1` and `LFL1` bytes, hash keys | 20.10 |
| `lfw` | `LFW1` toy weights and reference logits | 20.11 |
| `modes`, `outcome` | The facts and the mode they give (`engine_mode`, 14 cases) and the classification of the outcome of a replacement (6 cases) | 20.14 |
| `tx` | The fault matrix of the replacement transaction, 57 named cases: capabilities, field text, injected faults, typed-ahead keys, the expected outcome, reason, final text and incident flag | 20.14 |
| `fingerprint` | The fingerprints of the two supported layouts and of changed tables, and the layout each one identifies (4 cases) | 20.14 |
| `hook` | The model of the stream check (17 steps): whether the stream is trusted, whether a gap was reported, and why | 20.14 |

**How to read the traces.** In `trace_run` the word `ghbdtn` is converted in the state `default` and sets the run credit to 3; `z` (one key) is KEEP and leaves the credit at 3; the next three words are decided in the state `run` and lower the credit to 2, 1 and 0; the following `ntcn` is decided in the state `default` again and is KEEP (`abstain`, margin −2.707), so a chain of run-assisted conversions stops after three words. In `trace_undo` an undo at 1,000 ms makes the next words KEEP (`cooldown`) until 3 word decisions have been suppressed and 10,000 ms have passed; at 11,500 ms the same word is still KEEP, now with the reason user\_exception: the undo put the pair on the exception list (13.3), and only the cool-down has ended. In `scen`, Enter and Tab are context breaks and give no decision; a layout change inside a word drops the word; a Space read on another layout gives `layout_changed_at_boundary`; a closed gate stores nothing, and the first word after the gate reopens is decided normally; 65 keys give `overflow`; a second Space after a decision gives nothing. The keys of 20.14 are lists of cases. An entry of tx is: name, capabilities, field text, faults (operation:k means the k-th call of that operation), typed-ahead keys, extra arguments, outcome, reason, final text of the field, incident flag. An entry of modes is: name, capabilities, support status, health facts that are false, mode. An entry of fingerprint is: name, digest, the layout identified (null: not supported). An entry of hook is: name, whether the stream is trusted, whether a gap was reported, and the reason when there is one.

[code block of 20.12 removed: 344 lines]

Expected output of `python vectors.py` (`vectors_out.json`, 7,030 bytes with a final newline):

```json
{
"render": [
 ["ghbdtn", "en", "привет", [95, 61, 63, 83, 57, 35, 85, 96]],
 ["Ghbdtn", "en", "Привет", [95, 62, 63, 83, 57, 35, 85, 96]],
 ["GHBDTN", "en", "ПРИВЕТ", [95, 62, 64, 84, 58, 36, 86, 96]],
 ["[jhjij", "en", "хорошо", [95, 47, 65, 63, 65, 41, 65, 96]],
 [";bpym", "en", "жизнь", [95, 71, 83, 45, 37, 87, 96]],
 [",jkmit", "en", "больше", [95, 89, 65, 67, 87, 41, 35, 96]],
 ["k.,k.", "en", "люблю", [95, 67, 91, 89, 67, 91, 96]],
 ["`", "en", "ё", [95, 1, 96]],
 ["руддщ", "ru", "hello", [95, 63, 31, 69, 69, 43, 96]],
 ["Руддщ,", "ru", "Hello?", [95, 64, 31, 69, 69, 43, 94, 96]]
],
"caps": [
 [30, false, true, "G", "П", 62],
 [23, false, true, "[", "Х", 48],
 [36, true, true, "\"", "э", 73],
 [23, false, false, "[", "х", 47]
],
"prefix": [95, 61, 63, 83],
"tok25": 21,
"cands": [
 ["Ghbdtn?", "ru", ["", "Привет", ","]],
 ["Ghbdtn?!", "ru", ["", "Привет", ",!"]],
 ["(ghbdtn)", "ru", ["(", "привет", ")"]],
 ["k.,k.", "ru", ["", "люблю", ""]],
 ["[jhjij", "ru", ["", "хорошо", ""]],
 ["руддщ,", "en", ["", "hello", "?"]],
 ["(руддщ)", "en", ["(", "hello", ")"]],
 ["руддщб", "en", ["", "hello", ","]],
 ["руддщ..", "en", null],
 ["ghb1", "ru", null],
 [",", "ru", ["", "б", ""]],
 ["\"ghbdtn\"", "ru", ["", "ЭприветЭ", ""]],
 ["hello,", "ru", ["", "руддщб", ""]],
 ["Ghbdtn,", "ru", ["", "Приветб", ""]]
],
"guards": [
 ["github.com", "en", "shape_dotted"],
 ["https://x.io", "en", "no_candidate"],
 ["user@example.com", "en", "no_candidate"],
 ["MyVariable", "en", "shape_camel"],
 ["asdfgh", "en", "shape_keywalk"],
 ["фывапр", "ru", "shape_keywalk"],
 ["kubectl", "en", null],
 ["ghbdtn", "en", null]
],
"priors": [
 ["en", "default", 0.01, [0.7425, 0.01, 0.2475]],
 ["en", "after_switch", 0.003, [0.7478, 0.003, 0.2492]],
 ["en", "run", 0.25, [0.5625, 0.25, 0.1875]],
 ["ru", "default", 0.01, [0.0075, 0.99, 0.0025]],
 ["ru", "after_switch", 0.003, [0.0023, 0.997, 0.0008]],
 ["ru", "run", 0.25, [0.1875, 0.75, 0.0625]]
],
"lambdas": [
 [0.9995, 7.6],
 [0.999, 6.907],
 [0.997, 5.806],
 [0.995, 5.293],
 [0.99, 4.595],
 [0.9, 2.197]
],
"scores": [
 [[-3, 9, -2], "en", "default", 6.699],
 [[-3, 9, -2], "en", "run", 10.196],
 [[-3, 9, -2], "en", "after_switch", 5.488],
 [[8, -3, -2], "ru", "default", 6.169],
 [[-2, -3, 8], "ru", "default", 5.617],
 [[8, -3, -2], "en", "default", -15.359]
],
"decide": [
 ["ghbdtn", "en", [-3, 9, -2], "default", false, false, "CONVERT", "score_above_threshold", "привет", 0.893, 6],
 ["ghbdtn", "en", [-3, 8, -2], "default", false, false, "KEEP", "abstain", null, -0.107, 6],
 ["ghbdtn", "en", [-3, 8, -2], "run", true, false, "CONVERT", "score_above_threshold", "привет", 3.39, 6],
 ["ghbdtn", "en", [-3, 9, -2], "default", false, true, "KEEP", "user_exception", null, null, 6],
 ["hello", "en", [-3, 9, -2], "default", false, false, "KEEP", "lexicon_active", null, null, 5],
 ["z", "en", [-3, 9, -2], "default", false, false, "KEEP", "one_key", null, null, 1],
 ["ye", "en", [-3, 9, -2], "default", false, false, "KEEP", "two_key_rule", null, null, 2],
 ["ye", "en", [-3, 9, -2], "run", true, false, "CONVERT", "two_key_allow_list", "ну", null, 2],
 ["github.com", "en", [-3, 9, -2], "default", false, false, "KEEP", "shape_dotted", null, null, 10],
 ["руддщ", "ru", [9, -3, -2], "default", false, false, "CONVERT", "score_above_threshold", "hello", 1.362, 5],
 ["руддщ,", "ru", [9, -3, -2], "default", false, false, "CONVERT", "score_above_threshold", "hello?", 1.362, 5],
 ["привет", "ru", [9, -3, -2], "default", false, false, "KEEP", "lexicon_active", null, null, 6],
 ["Ghbdtn?", "en", [-3, 9, -2], "default", false, false, "CONVERT", "score_above_threshold", "Привет,", 0.893, 6]
],
"trace_run": [
 ["ghbdtn", "default", "CONVERT", "score_above_threshold", 0.893, 3],
 ["z", "run", "KEEP", "one_key", null, 3],
 ["ntcn", "run", "CONVERT", "score_above_threshold", 0.789, 2],
 ["vbh", "run", "CONVERT", "score_above_threshold", 0.789, 1],
 ["ntcn", "run", "CONVERT", "score_above_threshold", 0.789, 0],
 ["ntcn", "default", "KEEP", "abstain", -2.707, 0]
],
"trace_undo": [
 ["ghbdtn", "CONVERT", "score_above_threshold", 3],
 ["(undo at 1000 ms)", "", "", 0],
 ["ghbdtn @2000", "KEEP", "cooldown", 0],
 ["ghbdtn @3000", "KEEP", "cooldown", 0],
 ["ghbdtn @4000", "KEEP", "cooldown", 0],
 ["ghbdtn @5000", "KEEP", "cooldown", 0],
 ["ghbdtn @11500", "KEEP", "user_exception", 0]
],
"scen": [
 ["word + Space", [["CONVERT", "score_above_threshold"]]],
 ["word + Enter (break), then Space", []],
 ["word + Tab (break), then Space", []],
 ["layout changes inside the word (key layout differs)", []],
 ["manual layout event inside the word", []],
 ["Space sampled on another layout", [["KEEP", "layout_changed_at_boundary"]]],
 ["gate DENY while typing (password field)", []],
 ["gate DENY then ALLOW again, new word", [["CONVERT", "score_above_threshold"]]],
 ["Backspace edits the word", [["CONVERT", "score_above_threshold"]]],
 ["65 keys (overflow)", [["KEEP", "overflow"]]],
 ["two Spaces", [["CONVERT", "score_above_threshold"]]]
],
"manual": [
 ["Ghbdtn? Rfr ltkf?", "en2ru", "Привет, Как дела,"],
 ["Привет, как дела?", "ru2en", "Ghbdtn? rfr ltkf&"],
 ["123", null, "123"],
 ["ghbdtn 😀", "en2ru", "привет 😀"],
 ["ЁЖ ёж", "ru2en", "~: `;"],
 ["Hello, Привет", "ru2en", "Hello? Ghbdtn"]
],
"ev1": [
 ["4 errors, 4 users, n=100000, 20 users, 100 docs", true, 9.15e-05],
 ["4 errors in one document", false, 0.0001898],
 ["0 errors, n=100000", true, 3e-05],
 ["0 errors, n=99999", false, 3e-05],
 ["0 errors, 19 users", false, 1.5e-05],
 ["5 errors in 5 clusters, n=150000", true, 7.01e-05],
 ["2+2 errors in 2 clusters, n=100000", false, 0.0001259]
],
"poisson": [2.9957, 4.7439, 6.2958, 7.7537, 9.1535, 10.513],
"wb": {
 "test_word_keys": "ghbdtn",
 "logp_by_class": [-35.644469, -3.291324, -24.057021],
 "logits": [-36.612053, -4.207615, -25.571149],
 "lfb_bytes": 5216,
 "lfb_sha256_16": "1adf64096abc09a8",
 "lfb_logp": [-35.644469, -3.291324, -24.057021],
 "hello_ru": -27.44711,
 "hello_en": -3.270012,
 "n_pairs": [45, 68, 91]
},
"wb_score": 17.557,
"lfw": {
 "bytes": 2440,
 "sha256_16": "0fd995cb611e1201",
 "logits_ghbdtn": [-0.005081, -0.254659, -0.122052],
 "logits_hello": [-0.011607, -0.263225, -0.101561],
 "first_floats": [-0.25, 0.0, -0.03125, 0.28125]
},
"fnv": [
 ["", "0xcbf29ce484222325"],
 ["a", "0xaf63dc4c8601ec8c"],
 ["foobar", "0x85944171f73967e8"],
 ["ctx_key(2,(95,61))", "0x6add0b1c24d36c09"],
 ["pair_key(2,(95,61),63)", "0x53edd75759f89572"]
],
"lfl": {
 "bytes": 84,
 "sha256_16": "c737f8710843f069",
 "keys": [["lex_en", "hello", "0x1f466cfcfe5bb68c"], ["lex_ru", "привет", "0x5ac2513bb852af1f"], ["acr_ru", "МТС", "0x3a1b89f4ad0b309e"]],
 "member": [["lex_en", "HELLO", true], ["lex_en", "hi", false], ["acr_en", "sql", true]]
},
"cal_json": {
 "bytes": 1332,
 "sha256_16": "bc05f74d7a47562d"
},
"caps_all": [
 [0, false, false, "`", "ё", 1],
 [0, true, false, "~", "Ё", 2],
 [0, false, true, "`", "Ё", 2],
 [0, true, true, "~", "ё", 1],
 [5, false, false, "5", "5", 11],
 [5, true, false, "%", "%", 12],
 [5, false, true, "5", "5", 11],
 [5, true, true, "%", "%", 12],
 [13, false, false, "q", "й", 27],
 [13, true, false, "Q", "Й", 28],
 [13, false, true, "Q", "Й", 28],
 [13, true, true, "q", "й", 27],
 [23, false, false, "[", "х", 47],
 [23, true, false, "{", "Х", 48],
 [23, false, true, "[", "Х", 48],
 [23, true, true, "{", "х", 47],
 [24, false, false, "]", "ъ", 49],
 [24, true, false, "}", "Ъ", 50],
 [24, false, true, "]", "Ъ", 50],
 [24, true, true, "}", "ъ", 49],
 [25, false, false, "\\", "\\", 51],
 [25, true, false, "|", "/", 52],
 [25, false, true, "\\", "\\", 51],
 [25, true, true, "|", "/", 52],
 [30, false, false, "g", "п", 61],
 [30, true, false, "G", "П", 62],
 [30, false, true, "G", "П", 62],
 [30, true, true, "g", "п", 61],
 [35, false, false, ";", "ж", 71],
 [35, true, false, ":", "Ж", 72],
 [35, false, true, ";", "Ж", 72],
 [35, true, true, ":", "ж", 71],
 [36, false, false, "'", "э", 73],
 [36, true, false, "\"", "Э", 74],
 [36, false, true, "'", "Э", 74],
 [36, true, true, "\"", "э", 73],
 [44, false, false, ",", "б", 89],
 [44, true, false, "<", "Б", 90],
 [44, false, true, ",", "Б", 90],
 [44, true, true, "<", "б", 89],
 [45, false, false, ".", "ю", 91],
 [45, true, false, ">", "Ю", 92],
 [45, false, true, ".", "Ю", 92],
 [45, true, true, ">", "ю", 91],
 [46, false, false, "/", ".", 93],
 [46, true, false, "?", ",", 94],
 [46, false, true, "/", ".", 93],
 [46, true, true, "?", ",", 94]
],
"undo": [
 ["convert", "CONVERT", "привет", true],
 ["undo after 500 ms", "ghbdtn", [["en2ru", "ghbdtn"]], 0, 3, false],
 ["second undo", null],
 ["undo at exactly 10000 ms", "ghbdtn"],
 ["undo at 10001 ms", null],
 ["undo after 100 further characters", "ghbdtn"],
 ["undo after 101 further characters", null],
 ["Caps Lock word", "CONVERT", "ПРИВЕТ", "GHBDTN"],
 ["ru to en", "CONVERT", "hello", "руддщ"],
 ["after break", null, 0],
 ["after layout change", null, 0],
 ["after gap", null, 0],
 ["after gate DENY", null, 0],
 ["after mode MANUAL_ONLY", null, 0],
 ["after outcome RESTORED", null, 0],
 ["after outcome VERIFIED", "ghbdtn", 0],
 ["after backspace", null, 0]
],
"modes": [
 ["M1 with rollback", ["READBACK", "READ_RANGE", "REPLACE_RANGE", "ROLLBACK"], "AUTO", {}, "AUTO"],
 ["M1 with rollback", ["READBACK", "READ_RANGE", "REPLACE_RANGE", "ROLLBACK"], "MANUAL", {}, "MANUAL_ONLY"],
 ["M1 with rollback", ["READBACK", "READ_RANGE", "REPLACE_RANGE", "ROLLBACK"], "UNKNOWN", {}, "OFF"],
 ["M1 without rollback", ["READBACK", "READ_RANGE", "REPLACE_RANGE"], "AUTO", {}, "MANUAL_ONLY"],
 ["M2 only", ["READBACK", "READ_RANGE", "SYNTHETIC_INPUT"], "AUTO", {}, "MANUAL_ONLY"],
 ["M2 only", ["READBACK", "READ_RANGE", "SYNTHETIC_INPUT"], "MANUAL", {}, "MANUAL_ONLY"],
 ["M1 with rollback", ["READBACK", "READ_RANGE", "REPLACE_RANGE", "ROLLBACK"], "AUTO", {"hook_ok": false}, "MANUAL_ONLY"],
 ["M1 with rollback", ["READBACK", "READ_RANGE", "REPLACE_RANGE", "ROLLBACK"], "AUTO", {"models_ok": false}, "MANUAL_ONLY"],
 ["M1 with rollback", ["READBACK", "READ_RANGE", "REPLACE_RANGE", "ROLLBACK"], "AUTO", {"watchdog_ok": false}, "MANUAL_ONLY"],
 ["M1 with rollback", ["READBACK", "READ_RANGE", "REPLACE_RANGE", "ROLLBACK"], "AUTO", {"layout_ok": false}, "OFF"],
 ["M1 with rollback", ["READBACK", "READ_RANGE", "REPLACE_RANGE", "ROLLBACK"], "AUTO", {"permission_ok": false}, "OFF"],
 ["M1 with rollback", ["READBACK", "READ_RANGE", "REPLACE_RANGE", "ROLLBACK"], "AUTO", {"quarantined": true}, "OFF"],
 ["read only", ["READ_RANGE"], "AUTO", {}, "OFF"],
 ["nothing", [], "AUTO", {}, "OFF"]
],
"outcome": [
 [false, "x", "y", null, false, "ABORTED"],
 [true, "x", "y", "y", true, "VERIFIED"],
 [true, "x", "y", "y", false, "UNRECOVERED"],
 [true, "x", "y", "x", false, "RESTORED"],
 [true, "x", "y", "z", false, "UNRECOVERED"],
 [true, "x", "y", null, false, "UNRECOVERED"]
],
"tx": [
 ["m1 ok", ["READBACK", "READ_RANGE", "REPLACE_RANGE", "ROLLBACK"], "Hello ghbdtn ", {}, "", {}, "VERIFIED", "ok", "Hello привет ", false],
 ["m1 ok with typed-ahead keys", ["READBACK", "READ_RANGE", "REPLACE_RANGE", "ROLLBACK"], "Hello ghbdtn ab", {}, "ab", {}, "VERIFIED", "ok", "Hello привет ab", false],
 ["m1 ok, the application has not shown the last typed-ahead key", ["READBACK", "READ_RANGE", "REPLACE_RANGE", "ROLLBACK"], "Hello ghbdtn a", {}, "ab", {}, "VERIFIED", "ok", "Hello привет a", false],
 ["m1 user key lands before the range is read", ["READBACK", "READ_RANGE", "REPLACE_RANGE", "ROLLBACK"], "Hello ghbdtn ", {"read:1": "user:x"}, "", {}, "VERIFIED", "ok", "Hello привет x", false],
 ["m1 user key lands just before the write", ["READBACK", "READ_RANGE", "REPLACE_RANGE", "ROLLBACK"], "Hello ghbdtn ", {"replace:1": "user:x"}, "", {}, "VERIFIED", "ok", "Hello привет x", false],
 ["too many typed-ahead keys", ["READBACK", "READ_RANGE", "REPLACE_RANGE", "ROLLBACK"], "Hello ghbdtn abcd", {}, "abcd", {}, "ABORTED", "typed_ahead", "Hello ghbdtn abcd", false],
 ["context break", ["READBACK", "READ_RANGE", "REPLACE_RANGE", "ROLLBACK"], "Hello ghbdtn ", {}, "", {"context_break": true}, "ABORTED", "context_break", "Hello ghbdtn ", false],
 ["layout changed", ["READBACK", "READ_RANGE", "REPLACE_RANGE", "ROLLBACK"], "Hello ghbdtn ", {}, "", {"layout_changed": true}, "ABORTED", "context_break", "Hello ghbdtn ", false],
 ["gate turned DENY", ["READBACK", "READ_RANGE", "REPLACE_RANGE", "ROLLBACK"], "Hello ghbdtn ", {"gate:1": "DENY"}, "", {}, "ABORTED", "gate_changed", "Hello ghbdtn ", false],
 ["gate unknown", ["READBACK", "READ_RANGE", "REPLACE_RANGE", "ROLLBACK"], "Hello ghbdtn ", {"gate:1": "UNKNOWN"}, "", {}, "ABORTED", "gate_changed", "Hello ghbdtn ", false],
 ["gate query fails", ["READBACK", "READ_RANGE", "REPLACE_RANGE", "ROLLBACK"], "Hello ghbdtn ", {"gate:1": "raise"}, "", {}, "ABORTED", "gate_changed", "Hello ghbdtn ", false],
 ["caret query fails", ["READBACK", "READ_RANGE", "REPLACE_RANGE", "ROLLBACK"], "Hello ghbdtn ", {"caret:1": "raise"}, "", {}, "ABORTED", "adapter_error", "Hello ghbdtn ", false],
 ["range unreadable", ["READBACK", "READ_RANGE", "REPLACE_RANGE", "ROLLBACK"], "Hello ghbdtn ", {"read:1": "none"}, "", {}, "ABORTED", "echo_mismatch", "Hello ghbdtn ", false],
 ["read times out", ["READBACK", "READ_RANGE", "REPLACE_RANGE", "ROLLBACK"], "Hello ghbdtn ", {"read:1": "raise"}, "", {}, "ABORTED", "adapter_error", "Hello ghbdtn ", false],
 ["read returns stale text", ["READBACK", "READ_RANGE", "REPLACE_RANGE", "ROLLBACK"], "Hello ghbdtn ", {"read:1": "stale"}, "", {}, "ABORTED", "echo_mismatch", "Hello ghbdtn ", false],
 ["application had autocorrected the word", ["READBACK", "READ_RANGE", "REPLACE_RANGE", "ROLLBACK"], "Hello Ghbdtn ", {}, "", {}, "ABORTED", "echo_mismatch", "Hello Ghbdtn ", false],
 ["typed-ahead key the engine did not record", ["READBACK", "READ_RANGE", "REPLACE_RANGE", "ROLLBACK"], "Hello ghbdtn x", {}, "", {}, "ABORTED", "echo_mismatch", "Hello ghbdtn x", false],
 ["partial write, rollback works", ["READBACK", "READ_RANGE", "REPLACE_RANGE", "ROLLBACK"], "Hello ghbdtn ", {"replace:1": "partial"}, "", {}, "RESTORED", "write_error", "Hello ghbdtn ", true],
 ["write fails, nothing written", ["READBACK", "READ_RANGE", "REPLACE_RANGE", "ROLLBACK"], "Hello ghbdtn ", {"replace:1": "raise"}, "", {}, "RESTORED", "write_error", "Hello ghbdtn ", true],
 ["write applied but reports a timeout", ["READBACK", "READ_RANGE", "REPLACE_RANGE", "ROLLBACK"], "Hello ghbdtn ", {"replace:1": "applied_error"}, "", {}, "RESTORED", "write_error", "Hello ghbdtn ", true],
 ["application autocorrects the written text", ["READBACK", "READ_RANGE", "REPLACE_RANGE", "ROLLBACK"], "Hello ghbdtn ", {"replace:1": "autocorrect"}, "", {}, "RESTORED", "verify_failed", "Hello ghbdtn ", true],
 ["write silently ignored", ["READBACK", "READ_RANGE", "REPLACE_RANGE", "ROLLBACK"], "Hello ghbdtn ", {"replace:1": "ignored"}, "", {}, "RESTORED", "verify_failed", "Hello ghbdtn ", true],
 ["read-back differs", ["READBACK", "READ_RANGE", "REPLACE_RANGE", "ROLLBACK"], "Hello ghbdtn ", {"read:2": "stale"}, "", {}, "RESTORED", "verify_failed", "Hello ghbdtn ", true],
 ["read-back times out", ["READBACK", "READ_RANGE", "REPLACE_RANGE", "ROLLBACK"], "Hello ghbdtn ", {"read:2": "raise"}, "", {}, "RESTORED", "verify_failed", "Hello ghbdtn ", true],
 ["caret ends up before its expected place", ["READBACK", "READ_RANGE", "REPLACE_RANGE", "ROLLBACK"], "Hello ghbdtn ", {"caret:2": "back"}, "", {}, "RESTORED", "verify_failed", "Hello ghbdtn ", true],
 ["partial write and the rollback fails", ["READBACK", "READ_RANGE", "REPLACE_RANGE", "ROLLBACK"], "Hello ghbdtn ", {"replace:1": "partial", "replace:2": "raise"}, "", {}, "UNRECOVERED", "write_error", "Hello приdtn ", true],
 ["autocorrect and the rollback is ignored", ["READBACK", "READ_RANGE", "REPLACE_RANGE", "ROLLBACK"], "Hello ghbdtn ", {"replace:1": "autocorrect", "replace:2": "ignored"}, "", {}, "UNRECOVERED", "verify_failed", "Hello приве? ", true],
 ["no rollback capability, partial write", ["READBACK", "READ_RANGE", "REPLACE_RANGE"], "Hello ghbdtn ", {"replace:1": "partial"}, "", {"mode": "MANUAL_ONLY"}, "UNRECOVERED", "write_error", "Hello приdtn ", true],
 ["no rollback capability, but the write is fine", ["READBACK", "READ_RANGE", "REPLACE_RANGE"], "Hello ghbdtn ", {}, "", {"mode": "MANUAL_ONLY"}, "VERIFIED", "ok", "Hello привет ", false],
 ["AUTO requested without the capabilities", ["READBACK", "READ_RANGE", "REPLACE_RANGE"], "Hello ghbdtn ", {}, "", {"mode": "AUTO"}, "ABORTED", "capability", "Hello ghbdtn ", false],
 ["AUTO requested for synthetic input", ["READBACK", "READ_RANGE", "SYNTHETIC_INPUT"], "Hello ghbdtn ", {}, "", {"mode": "AUTO"}, "ABORTED", "capability", "Hello ghbdtn ", false],
 ["mode OFF", ["READBACK", "READ_RANGE", "REPLACE_RANGE", "ROLLBACK"], "Hello ghbdtn ", {}, "", {"mode": "OFF"}, "ABORTED", "mode_off", "Hello ghbdtn ", false],
 ["no read capability", ["REPLACE_RANGE", "ROLLBACK"], "Hello ghbdtn ", {}, "", {"mode": "MANUAL_ONLY"}, "ABORTED", "capability", "Hello ghbdtn ", false],
 ["m2 manual ok", ["READBACK", "READ_RANGE", "SYNTHETIC_INPUT"], "Hello ghbdtn ", {}, "", {"mode": "MANUAL_ONLY"}, "VERIFIED", "ok", "Hello привет ", false],
 ["m2 with typed-ahead keys is refused", ["READBACK", "READ_RANGE", "SYNTHETIC_INPUT"], "Hello ghbdtn a", {}, "a", {"mode": "MANUAL_ONLY"}, "ABORTED", "typed_ahead", "Hello ghbdtn a", false],
 ["m2 user key between synthetic events", ["READBACK", "READ_RANGE", "SYNTHETIC_INPUT"], "Hello ghbdtn ", {"event:3": "user:x"}, "", {"mode": "MANUAL_ONLY"}, "UNRECOVERED", "verify_failed", "Hello gпривет ", true],
 ["m2 synthetic event times out", ["READBACK", "READ_RANGE", "SYNTHETIC_INPUT"], "Hello ghbdtn ", {"event:5": "raise"}, "", {"mode": "MANUAL_ONLY"}, "UNRECOVERED", "write_error", "Hello ghb", true],
 ["m2 user key while the range is read: nothing is sent", ["READBACK", "READ_RANGE", "SYNTHETIC_INPUT"], "Hello ghbdtn ", {"read:1": "user:x"}, "", {"mode": "MANUAL_ONLY"}, "ABORTED", "typed_ahead", "Hello ghbdtn x", false],
 ["m2 user key before the first synthetic event: the race that stays", ["READBACK", "READ_RANGE", "SYNTHETIC_INPUT"], "Hello ghbdtn ", {"event:1": "user:x"}, "", {"mode": "MANUAL_ONLY"}, "UNRECOVERED", "verify_failed", "Hello gпривет ", true],
 ["m1 caret forward although no user key came", ["READBACK", "READ_RANGE", "REPLACE_RANGE", "ROLLBACK"], "Hello ghbdtn ", {"caret:2": "forward"}, "", {}, "RESTORED", "verify_failed", "Hello ghbdtn ", true],
 ["m1 one user key during the read-back moves the caret by one", ["READBACK", "READ_RANGE", "REPLACE_RANGE", "ROLLBACK"], "Hello ghbdtn ", {"read:2": "user:x"}, "", {}, "VERIFIED", "ok", "Hello привет x", false],
 ["m1 one user key does not explain a caret two forward", ["READBACK", "READ_RANGE", "REPLACE_RANGE", "ROLLBACK"], "Hello ghbdtn ", {"read:2": "user:x", "caret:2": "forward"}, "", {}, "RESTORED", "verify_failed", "Hello ghbdtn x", true],
 ["m1 write damages the Space after the range", ["READBACK", "READ_RANGE", "REPLACE_RANGE", "ROLLBACK"], "Hello ghbdtn ", {"replace:1": "spill"}, "", {}, "UNRECOVERED", "verify_failed", "Hello ghbdtn?", true],
 ["m1 write damages the Space, a typed-ahead key follows", ["READBACK", "READ_RANGE", "REPLACE_RANGE", "ROLLBACK"], "Hello ghbdtn a", {"replace:1": "spill"}, "a", {}, "UNRECOVERED", "verify_failed", "Hello ghbdtn?a", true],
 ["m1 autocorrect with a typed-ahead key, the rollback restores the fragment", ["READBACK", "READ_RANGE", "REPLACE_RANGE", "ROLLBACK"], "Hello ghbdtn a", {"replace:1": "autocorrect"}, "a", {}, "RESTORED", "verify_failed", "Hello ghbdtn a", true],
 ["m1 a key that types nothing during the read-back is allowed", ["READBACK", "READ_RANGE", "REPLACE_RANGE", "ROLLBACK"], "Hello ghbdtn ", {"read:2": "key"}, "", {}, "VERIFIED", "ok", "Hello привет ", false],
 ["m1 one key may explain a caret one place forward", ["READBACK", "READ_RANGE", "REPLACE_RANGE", "ROLLBACK"], "Hello ghbdtn ", {"read:2": "key", "caret:2": "forward"}, "", {}, "VERIFIED", "ok", "Hello привет ", false],
 ["m1 one key does not explain a caret behind its place", ["READBACK", "READ_RANGE", "REPLACE_RANGE", "ROLLBACK"], "Hello ghbdtn ", {"read:2": "key", "caret:2": "back"}, "", {}, "RESTORED", "verify_failed", "Hello ghbdtn ", true],
 ["m1 one typed key and a caret one place back is still inside the window", ["READBACK", "READ_RANGE", "REPLACE_RANGE", "ROLLBACK"], "Hello ghbdtn ", {"read:2": "user:x", "caret:2": "back"}, "", {}, "VERIFIED", "ok", "Hello привет x", false],
 ["m2 a key that types nothing while the range is read: nothing is sent", ["READBACK", "READ_RANGE", "SYNTHETIC_INPUT"], "Hello ghbdtn ", {"read:1": "key"}, "", {"mode": "MANUAL_ONLY"}, "ABORTED", "typed_ahead", "Hello ghbdtn ", false],
 ["m2 a key that types nothing between synthetic events", ["READBACK", "READ_RANGE", "SYNTHETIC_INPUT"], "Hello ghbdtn ", {"event:3": "key"}, "", {"mode": "MANUAL_ONLY"}, "VERIFIED", "ok", "Hello привет ", false],
 ["m1 a key during the write explains a caret one place forward", ["READBACK", "READ_RANGE", "REPLACE_RANGE", "ROLLBACK"], "Hello ghbdtn ", {"replace:1": "key", "caret:2": "forward"}, "", {}, "VERIFIED", "ok", "Hello привет ", false],
 ["m1 a key during the write does not explain a caret two places forward", ["READBACK", "READ_RANGE", "REPLACE_RANGE", "ROLLBACK"], "Hello ghbdtn ", {"replace:1": "key", "caret:2": "forward2"}, "", {}, "RESTORED", "verify_failed", "Hello ghbdtn ", true],
 ["m1 a key during the read-back does not explain a caret two places forward", ["READBACK", "READ_RANGE", "REPLACE_RANGE", "ROLLBACK"], "Hello ghbdtn ", {"read:2": "key", "caret:2": "forward2"}, "", {}, "RESTORED", "verify_failed", "Hello ghbdtn ", true],
 ["m2 a key between synthetic events explains a caret one place forward", ["READBACK", "READ_RANGE", "SYNTHETIC_INPUT"], "Hello ghbdtn ", {"event:3": "key", "caret:2": "forward"}, "", {"mode": "MANUAL_ONLY"}, "VERIFIED", "ok", "Hello привет ", false],
 ["m2 a key between synthetic events does not explain a caret two places forward", ["READBACK", "READ_RANGE", "SYNTHETIC_INPUT"], "Hello ghbdtn ", {"event:3": "key", "caret:2": "forward2"}, "", {"mode": "MANUAL_ONLY"}, "UNRECOVERED", "verify_failed", "Hello привет ", true],
 ["m2 the synthetic events are not user keys: a caret ahead without any user key fails", ["READBACK", "READ_RANGE", "SYNTHETIC_INPUT"], "Hello ghbdtn ", {"caret:2": "forward"}, "", {"mode": "MANUAL_ONLY"}, "UNRECOVERED", "verify_failed", "Hello привет ", true]
],
"fingerprint": [
 ["en", "7b35aa964f372005ccef6558a1049dce2a550d772939090e3dba51302c0f3078", "en"],
 ["ru", "3aced72548d6d46da951f06cdbed60aac96487c338ad7b805e95402eb37204de", "ru"],
 ["ru with key 4 shifted changed to $", "c0371738c40a32a661d8b0a3da53bc364be0581704823335df93214890cf1672", null],
 ["en rotated by one entry", "4c79352a3890de1b18fa6b4afa394f39e39ae60e1577ba7ec923c96d3c79f778", null]
],
"hook": [
 ["three matched keys", true, false],
 ["key unseen by the hook, at the limit", true, false],
 ["key unseen by the hook, past the limit", false, true, "canary_missing"],
 ["gap is reported once", false, false],
 ["re-arm pair 1", false, false],
 ["re-arm pair 2", false, false],
 ["re-arm pair 3", true, false],
 ["lost b and extra c cancel as counts, at the limit", true, false, null],
 ["lost b and extra c cancel as counts, past the limit", false, true, "canary_missing"],
 ["extra hook key alone, at the limit", true, false, null],
 ["extra hook key alone, past the limit", false, true, "canary_extra"],
 ["hook event first, injected event ignored", true, false, null],
 ["two physical presses, one reported, at the limit of the unmatched press", true, false, null],
 ["two physical presses, one reported, past the limit of the unmatched press", false, true, "canary_missing"],
 ["counterpart exactly at the limit, the watchdog has not run", true, false, null],
 ["hook event one ms too late, the watchdog has not run", false, true, "canary_missing"],
 ["raw event one ms too late, the watchdog has not run", false, true, "canary_extra"],
 ["a later event of the same side shows that the first has expired", false, true, "canary_missing"],
 ["macOS tapDisabledByTimeout", false, true, "tap_timeout"],
 ["macOS tap enabled again", true, false, null],
 ["macOS tapDisabledByUserInput", false, true, "tap_user_input"]
]
}
```

### 20.13 Conformance tests

An implementation of the engine, in any language and on any platform, is conformant when it passes the six checks below. The vectors of 20.12 pin the exact values; the property tests pin the rules that no finite list of vectors can; the last two checks tie the production code to the reference.

| ID | Check |
| --- | --- |
| CT-1 | Every entry of the expected JSON of 20.12 is reproduced: strings, integers, booleans, token lists, hashes and byte counts exactly; floats equal after rounding to the number of decimals printed. |
| CT-2 | The output is deterministic. The reference generator prints byte-identical output on every run, on every Python from 3.9 upwards and for every value of `PYTHONHASHSEED`; no result depends on the iteration order of a set or a dictionary. |
| CT-3 | The property tests of `conformance.py` below pass, under both python and python -O (no test uses the assert statement, so none disappears when Python is optimised): 200,000 random key runs (no key lost or duplicated by the candidate, core made of letters only, at most one leading and two trailing marks), priors that sum to 1, a probability stored where nats are expected is refused, the `LFB1` round trip, and the `LFW1` size rule of MD-14; the negative tests of the calibration package and of the three binary formats (every damaged file is refused); the engine tests (modes, undo snapshot, gap in the event stream, and an event fuzz of 200,000 events, 1,000,000 in the audit run, that checks the invariants of 13.5); the fault matrix of the replacement transaction (57 named cases and 1,665 single and paired faults, 13.2); the tests of the stream check (20.14); and every threshold of the specification, tested on both sides of its edge (part 3, P14). |
| CT-4 | With the real lexicon of 8.9: no word of the 20,000 most frequent word forms of either language, typed on its own layout, has a core shorter than the whole run, and every Russian word of that list that uses only keys of the Russian layout, typed on the English layout, comes back from `candidate` with its whole run as core. A failure is a defect of the segmentation, not of the lexicon (the seven letter-keys, 5.3). |
| CT-5 | The runtime meets MD-12 (baseline log-probabilities within 1e-9 of the reference) and MD-14 (network logits within 1e-5 on the toy weights of 20.12 and within 1e-4 on at least 100,000 key sequences of the exported network). |
| CT-6 | A change of the code of 20.2 to 20.11 or 20.14 that changes any entry of 20.12 is a change of this specification: the expected output of 20.12 is updated in the same revision. |

CT-1 to CT-3 need only the files of this section. CT-4 needs the lexicon built by D3, so it belongs to the build of the tables, not to the unit tests of the engine.

**`conformance.py`, part 1 of 3 (P1 to P6: tokens, priors, the calibration package, the binary formats, Caps Lock).** The three parts are one file: write them into `conformance.py` one after the other, in this order, with one empty line between them.

[code block of 20.13 removed: 173 lines]

**`conformance.py`, part 2 of 3 (P7 to P13: modes, outcomes, the fault matrix of the replacement transaction, the engine, layout identity, hook health, the event fuzz).**

[code block of 20.13 removed: 317 lines]

**`conformance.py`, part 3 of 3 (P14: every threshold and format rule is tested on both sides of its edge; the closing line).**

[code block of 20.13 removed: 347 lines]

### 20.14 Adapter contract, engine mode, replacement transaction, layout identity, hook health

`lfengine.py` ends with the part below. It is the executable form of the replacement transaction (13.2), the adapter capabilities and the support matrix (13.7, 13.8), the mode of the engine (13.5), the identification of a layout by its characters (13.7) and the check that the stream of key events is complete (13.5, row 13). The OS adapters are written against `Adapter`; the engine of 20.7 is written against `engine_mode`, `run_transaction` and `HookHealth`. Nothing here calls an operating-system API, so the part runs, and is tested, in the cloud. What it proves is the algorithm (evidence level REFERENCE\_VERIFIED, 16.1); what a real application does is proved only by the integration tests RT-1 to RT-18 on the real operating systems.

| Function or class | What it fixes |
| --- | --- |
| `engine_mode` | A pure function of facts. `AUTO` needs all four capabilities of `AUTO_REQUIRES` (read a range, replace a range in one operation, read it back with the caret, write the original back), the status `AUTO` in the support matrix, usable models, a healthy hook and a healthy watchdog. An application whose only way to write is synthetic keystrokes (M2) is `MANUAL_ONLY` at best: the support matrix can never grant more than the capabilities allow. `OFF` when the application is quarantined, a permission is missing, the layout is not supported, the support status is `UNKNOWN`, or nothing can write at all. The engine of 20.7 records and decides only in `AUTO`: in `MANUAL_ONLY` and in `OFF` it stores no key (13.5). |
| `classify_outcome` | `ABORTED` (nothing was written), `VERIFIED` (the whole range holds the new text and the caret is where it must be), `RESTORED` (the range holds exactly what the user typed), `UNRECOVERED` (anything else, including a range that cannot be read). The classification uses observations only, never the intention of the code. |
| `run_transaction` | The steps of 13.2: freeze, gate, read and match, the last look of M2, replace, verify, outcome. The range that is read, verified and rolled back is always the whole fragment: the word, the Space and the typed-ahead keys (at most 3). M2 is refused when any key is typed ahead or a modifier key is down. For M2 the last look comes after the match and before the first synthetic event: a user key counted since the freeze means `ABORTED` (`typed_ahead`) and nothing is written. After the write the whole fragment must read back as the new word, the Space and the typed-ahead keys, and the caret must be exactly where it was (no user key seen) or at most as many positions further as user keys were seen; a caret that moved backwards is a failure. One rollback only, and only for M1. Any failure after step 4 began is a `replacement_incident` and puts the application in quarantine. The one race that remains for M2 (a key that arrives after the last look) is not hidden: the text is classified from what is in the field, usually `UNRECOVERED`, and its frequency is measured by RT-4. This is why M2 is never `AUTO`. |
| `Adapter`, `SimField`, `AdapterError` | The contract that an OS adapter implements (`gate`, `caret`, `read`, `replace`, `send`, `modifier_down`, `mark`, `keys_since`) and the test double with fault injection that stands in for it. `SimField` injects a failure at the n-th call of an operation: a gate that changes, a caret that moves, a read that returns nothing or stale text, a write that raises, is partial, is ignored, is changed by autocorrection, damages the Space after the range, or meets a user key (a character or a key that types nothing). Every fault row of 13.5 and every step of 13.2 has at least one scenario in `conformance.py` (20.13). |
| `layout_fingerprint`, `identify_layout` | A layout is identified by the SHA-256 of its 94 characters (key by key, without and with Shift, Caps Lock off), never by the language id or the layout name. A layout that does not read exactly as the supported English or Russian layout is `OFF` for that layout. |
| `HookHealth` | The completeness of the stream of key events. On Windows an independent Raw Input observer reports every physical key event with a signature (scan code, extended flag, press or release); each event of one side must meet an event with the same signature from the other side within 300 ms, in either order; a counterpart that arrives later is too late, and the loss is declared when it arrives or at the next check, whichever comes first, even if the watchdog timer has not run yet. A raw key that the hook never reports is `canary_missing`; a hook key that the observer never saw is `canary_extra`; events that the hook marks as injected are not compared. Equal counts prove nothing, because one lost and one extra event cancel each other. After a loss the engine receives one `gap` event and the mode is `MANUAL_ONLY` until three pairs with equal signatures are seen after the hook is installed again. On macOS the loss is a tap that the system disabled (timeout or user input) or a poll that finds the tap disabled; no canary exists there. |

[code block of 20.14 removed: 396 lines]
