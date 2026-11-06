# Keyboard Layout Auto-Correction Model — Technical Specification v3.1

Oct 19, 2026 · @Thomas

## 1. Executive summary

Do not train a language model for this task. Train a classifier of about 43,000 parameters that reads physical key codes and decides one thing per word (English, Russian, or technical text), and let a fixed key table do the conversion. A model that cannot emit characters cannot answer `ghbdtn` with "как ваши дела".

**Why the 500M-parameter attempt failed.** Typed text and intended text are tied by a fixed permutation of 47 physical keys (`g→п`, `h→р`, `b→и`). The only unknown is one bit per word: convert or keep. A generative decoder spends its capacity on text that is already determined, has an open output space, is trained to continue text rather than to abstain, and was judged by fluency instead of by false corrections (section 3.1).

**Six decisions that define the specification**

1. **Classify, never generate** (MD-1). The network has three outputs and no vocabulary of words.
2. **Input is key positions, not characters** (section 5.1). Each keystroke is `(physical key, Shift)`, one of 94 tokens, so one model serves every layout pair that is a key-for-key permutation.
3. **Three classes: `EN`, `RU`, `OTHER`** (section 5.2). The action (keep or convert) comes from the active layout; "abstain" is a policy outcome, not a trained class.
4. **A cascade, not one model** (section 6). Guards, then lexicon look-ups, then an n-gram stage, then the network, then a calibrated policy. The network ships only if it beats the statistical baseline on real data (EV-12).
5. **Safety comes from calibration** (section 10). Temperature scaling, a prior-shift correction for the rarity of wrong-layout words, and thresholds of 0.995 to 0.999 (5.3 to 6.9 nats, section 10.3) that depend on word length. One-key words are never converted.
6. **Judge by false corrections per correct word**, not by accuracy (section 11). The gate is at most 4 false corrections in 100,000 correct words, which is about one wrong correction per 20,000 words typed.

**Target numbers**

| Quantity | Specified | Evidence |
| --- | --- | --- |
| Network | Embedding, 3 convolutions (kernels 3, 5, 3), pooling, linear; 64 channels; 42,595 parameters; 170 KB in FP32 | Section 7; accuracy flat from 27,000 to 148,000 parameters (section 7.3) |
| Network latency | p50 50 µs, p99 250 µs per candidate, one CPU thread | 29 to 39 µs p50 and at most 71 µs p99 measured in native C for a 9-key word on a cloud CPU (section 18.7) |
| Whole decision, one word | p50 150 µs, p99 1 ms | One network call is 29 to 39 µs; end to end is measured on the reference devices (section 7.5) |
| The requested 0.0001 ms (100 ns) | Met by hash look-ups only | 12 to 32 ns per probe measured; no network of useful accuracy fits (section 7.5) |
| Training | AdamW, learning rate 5e-3, batch 256, about 10,500 steps, no label smoothing | 133 to 140 s on two CPU threads; under-training is the main risk (section 9) |
| Compression | None by default; static INT8 only if a gate fails; no 4-bit | INT8 costs at most 0.0009 accuracy and helps speed only from 64 channels up (section 12) |
| Quality gate | At most 4 false corrections in at least 100,000 correct words from at least 20 users | Rule of three and Poisson limits, with the cluster bound of section 11.3 |
| Proxy accuracy | 0.967 over all words; 0.99 at 10 keys and more; 0.78 at 3 keys | Word lists, not real typing (section 18.1) |
| Proxy recall at a false-positive rate of 1e-4 | 5 keys and more: 1.00 EN→RU, 0.90 to 0.94 RU→EN | Section 18.6 |

**What the numbers are, and are not.** Every figure from section 18 was measured on proxy data (word lists and synthetic technical strings) on a shared 2-vCPU cloud machine. They decide the model family, the size, the depth and the recipe, because comparisons between models are fair on that data. They do not prove the product's false-positive rate. That is proved only on the realistic test set of section 8.5, and the Apple M1 Max latency is to be measured by the protocol of section 12.4.

**Honest limits.** Three- and four-letter words are ambiguous between the languages (`in` and `шт`, `her` and `рук`), so no model recovers them without context; the manual hotkey and the run-based rule cover them (sections 10.4 and 18.2). Russian acronyms typed on the English layout are the main source of missed RU→EN corrections. The real wrong-layout rate is unknown and drives the precision of the whole product (section 5.5).

**How to read this document.** Section 2 answers the seven questions of the brief. Sections 3 to 5 explain the diagnosis and the problem formulation; 6 to 12 specify the system, the model, the data, the training, the policy, the evaluation and the compression; 13 to 16 cover runtime safety, further parameters, deliverables and the work plan. Section 17 reviews the three earlier drafts, section 18 holds the experiments, section 19 the appendices and section 20 the reference implementation, formats and test vectors. Which parts are normative is stated in section 4.4.

## 2. Direct answers to the seven questions

The short answers are below; each row names the section that holds the evidence and the requirement IDs.

| # | Question | Answer | Where |
| --- | --- | --- | --- |
| 1 | Which model to train? | A small **convolutional classifier over key tokens** with three outputs (`EN`, `RU`, `OTHER`), placed behind a lexicon and trigram stage that must work alone. Not an LLM, not a pretrained model, not a sequence-to-sequence model. A hash look-up, a trigram, a bidirectional GRU, a 2-layer and a 4-layer Transformer were trained on the same data; the CNN was as accurate as the best and 2 to 14 times faster than the recurrent and attention models | 7.2, 18.6; MD-1, MD-2, MD-7 |
| 2 | What size, given a target of "0.0001 ms"? | **42,595 parameters (64 channels), 170 KB**. Permitted range 15,000 to 87,000, hard cap 100,000. Accuracy is within 0.2 points of its plateau from 27,000 parameters and flat to 148,000. The 100 ns target equals one to eight hash probes; it is met by the look-up tier and cannot be met by any network that is accurate enough (the network is about 29 µs in native C, the n-gram stage 0.7 to 1.7 µs). One millisecond per word is the right order of magnitude, because the decision runs once per word | 7.3, 7.5; MD-3, MD-9 |
| 3 | How to prepare the dataset, and are there ready-made ones? | **No ready-made wrong-layout dataset exists**, and none is needed: render correct text through the layout table to get the wrong-layout key sequence with an exact label. Sources: Wikipedia, subtitle frequency lists, Tatoeba, permissively licensed code for `OTHER` (20 to 25% of items), 0.5 to 2 million items, split by document or lemma. The dataset named in the first draft (`anzorq/kbd_lat-835k_ru-3M`) is Kabardian plus Russian Wikipedia and is excluded. The test set is real typing: at least 100,000 correct words from at least 20 users | 8; DT rules in 8.7 |
| 4 | Which training parameters? | AdamW, weight decay 0.01, **peak learning rate 5e-3**, batch 256, **about 10,500 steps** (12 passes over 223,378 rows), 3% warm-up then cosine decay to 2% of peak, gradient clipping 1.0, dropout 0.1, **no label smoothing, no mixup**, 35% of rows cut to prefixes, fresh case variants each epoch, at least 3 seeds. Under-training is the main risk: learning rate 3e-4, 2 epochs and batch 2048 each lose 1.5 to 2 points | 9; TR-1 to TR-8 |
| 5 | Which quality metrics? | **False corrections per correct word** (at most 4 in 100,000 correct words, 95% upper bound 1e-4), precision at wrong-layout rates of 0.3%, 1% and 3%, recall at that false-positive rate split by word length, calibration (ECE ≤ 0.02 per class and length bucket), robustness to typos, undo rate in use, and a comparison with the statistical baseline. Not accuracy, perplexity or BLEU | 11; EV-1 to EV-15 |
| 6 | How many layers? | **One embedding, three 1-D convolutions (kernels 3, 5, 3), one pooling operation and one linear layer**: five layers with parameters (the embedding, three convolutions and the linear head) plus a pooling operation that has none. Two, three and four convolutions gave 0.9643, 0.9639 and 0.9660, inside two seed deviations of one another | 7.1, 7.3; MD-4 |
| 7 | Quantization or compression? | **Not needed by default**: ship FP32 (170 KB, fits in cache). Static INT8 is an option: file 2.9 times smaller, call 24% faster at 64 channels (58% at 128), accuracy loss at most 0.0009. 4-bit weights survive numerically (0.1 to 0.4 points) but save under 150 KB and have no CPU speed-up; pruning and distillation have nothing to compress. Order of steps in 12.2 | 12; DP rules in 12.6 |

**Further parameters to consider** (the brief's last request). The ones that change results most are listed here; the full set is in sections 13 and 14.

| Parameter | Why it matters | Where |
| --- | --- | --- |
| Seven keys that are letters in Russian but punctuation in English (`` ` `` `[` `]` `;` `'` `,` `.`) | Splitting words at punctuation cuts about one Russian word in five (20.6% of tokens measured) | 5.3 |
| Wrong-layout rate π (0.3% to 3%, unmeasured) | Sets precision; a model trained on a balanced mix would over-correct many times over | 5.5, 10.2, 11.5 |
| Length-dependent thresholds, direction-dependent | 3-key words collide across languages; 12-key words do not | 10.3, 10.4 |
| Language-pair scope and layout variants | Dvorak, Colemak, AZERTY and phonetic Russian are out of scope; Windows and macOS Russian differ in punctuation | 14.1 |
| Caps Lock, Shift, dead keys, layout switch mid-word | The same key sequence has different case on each layout | 14.1, 14.2 |
| Stage 0 gate: secure fields and unknown applications, before any buffering. Guards: code editors, URLs, identifiers | A correction in a password or a command is a severity-1 defect | 13.1 |
| Replacement protocol, undo, cool-down, rollback | Lost or duplicated characters are worse than a missed correction | 13.2, 13.3 |
| Privacy and data licences | Keystrokes are sensitive; several text sources have unclear licences | 8.7, 8.8, 13.4 |
| Drift and adaptation | Slang and brands change; thresholds are fixed per release and only the exception list adapts per user | 10.6, 14.3, 14.5 |
| Reproducibility and determinism | Differences below the seed spread are not findings | 9.1, 15.2 |

## 3. Why the 500M LLM failed, and what prior art shows

The 500M model hallucinated "как ваши дела" because it was asked to generate text for a task whose correct output is already fixed by the keyboard. The fix is architectural, not a matter of tuning: the model must never emit characters.

### 3.1 Root causes of the failed attempt

1. **Wrong problem class.** Typed text and intended text are related by a fixed permutation of physical keys (`g→п`, `h→р`, `b→и`, ...). The only unknown is one bit per word: convert or keep. A generative decoder spends its capacity, and its risk, on producing text that is already known.
2. **Training objective rewards fluency.** Next-token cross-entropy turns the network into a language model. Nothing in the loss penalises extra tokens after the correct answer, so a prompt that looks like the start of a phrase gets a fluent continuation.
3. **Capacity far above task entropy.** 500M parameters for a 1-bit-per-word decision memorise the corpus and its phrases. Hallucinated stock phrases are the visible symptom.
4. **Unbounded output space, no abstention.** A decoder has no built-in way to say "leave this alone". Confidence is a by-product of sampling, not a calibrated quantity.
5. **Cost.** A dense 500M model needs about 1 GFLOP per generated token (2 FLOPs per parameter). That is orders of magnitude above the 0.1 to 5 ms budget of a keystroke tool, before any text injection.

**Design consequence.** The network outputs a vector of logits over a small fixed set of classes. The replacement string is produced only by a deterministic key-position table. Hallucination is then impossible by construction, not merely unlikely.

A large LLM can still be useful offline: to draft synthetic chat-style sentences, to flag label noise, or as a distillation teacher. It must never run inside the keystroke path.

### 3.2 What existing projects do

Every claim below comes from the project's own README or article; none is an independent benchmark.

| Project | Approach | Facts worth reusing |
| --- | --- | --- |
| [Punto Switcher](https://habr.com/en/post/132851) (Yandex, closed source) | Dictionaries of letter combinations that are impossible in a language (per a Habr analysis) | Negative n-gram constraints are cheap and strong; user exception list |
| [xneur](https://habr.com/en/post/132851) (Linux) | Cascade: user rules and regexes, then spell-checker, then lists of impossible 2- and 3-letter combinations | Cheap checks first; 3-letter lists are 10 to 15 times smaller than 2-letter lists and are checked first |
| [KeyboardSwitcher](https://github.com/kertser/KeyboardSwitcher) | LSTM trained in PyTorch, run through ONNX Runtime; outputs N/A, en, he, ru | Confidence at minimum length 0.99, at full length 0.70; two consecutive agreeing decisions; top-1 vs top-2 margin 0.05; Esc-undo; learned exceptions; adaptive thresholds; correction runs on a worker thread so the hook returns at once |
| [Rekey](https://github.com/rstqDev/rekey) | Hook, buffer, detector, engine, injector. Hashed word table from OpenSubtitles frequency lists, character-trigram fallback | Layouts described by physical key position; "overwhelming evidence" required to rewrite a valid word; digits, symbols and acronyms refused; gibberish left as typed; 4.6 MB for ten language pairs; self-reported 99.0% and 99.5% on EN-RU with 0.00% false positives over 54,000 words |
| [RSwitcher](https://github.com/andrewchuev/rswitcher) | Bigram and trigram log-probabilities, normalised by word length, smoothed with interpolated Kneser-Ney | Word lists of 3,000 EN and 5,000 RU words for words of 4+ letters; separate short-word lists; 1-letter words on an allow-list; trailing punctuation trimmed before scoring; camelCase and snake\_case guarded |
| [Traple](https://github.com/spendolas/traple) (macOS) | Trigram plus word-list scoring on word terminators | Buffers raw (keycode, shift) pairs and translates them at decision time, so a mid-word layout change cannot corrupt the buffer; per-app blacklist |
| [Punto for macOS](https://github.com/rshagiev/punto-switcher) (open source) | Manual conversion, Accessibility API replacement | "A missed conversion is better than deleting or pasting into the wrong text field" |
| [Wikimedia search](<https://www.mediawiki.org/wiki/User:TJones_(WMF)/Notes/Implementation_Design_and_Parameter_Optimization_for_Wrong_Keyboard_Detection_and_Suggestion>) | TextCat n-gram language ID on layout-transliterated models | Minimum 3 to 4 characters; languages within 2% of the best score are "too ambiguous"; all-caps excluded; rare surnames collide with wrong-layout words |
| [eBay, EMNLP 2014](https://aclanthology.org/D14-1068/) | Token classifier on character 5-gram LM scores, token shape and dictionaries | Keyboard-layout errors in about 7.8% of null-result queries; short tokens are the hardest (`ваз` maps to `dfp`, `муки` to `verb`); token-level and sequence models did not differ significantly |
| [CLD3 / small feed-forward nets](https://arxiv.org/abs/1708.00214) and [fastText LID](https://fasttext.cc/docs/en/language-identification.html) | Hashed character n-gram embeddings feeding a small network | 302 to 800 KB language-ID models; the compressed fastText model is 917 kB for 176 languages |

### 3.3 Lessons adopted in this specification

- **Statistics and dictionaries are the proven core** of every shipping tool; a small neural network is an arbiter for the cases they cannot settle.
- **Decide at the word boundary** by default; allow early detection only with a high bar and two agreeing decisions.
- **Work on physical keys, not characters.** Rekey, Traple and keytypo all do; it makes the mapper exact and the two readings of a word available at once.
- **Thresholds depend on word length** and are tuned on data, not set to one constant.
- **Guards, undo and learned exceptions** matter as much as the classifier, and must be tested end to end.
- **Self-reported accuracy is not evidence.** This specification requires its own realistic test set (section 11).

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

## 7. Model specification

The network answers one question per word candidate: which of three kinds of text did the user mean (English, Russian, or Latin-script text that is not an English word, whose handling depends on the active layout, section 5.2). It is a small convolutional classifier over key tokens. The numbers below come from the feasibility experiments of section 18 (proxy data) and decide the family, the size and the depth; the real acceptance is on the realistic test set (section 8.5).

### 7.1 Specified model

| Item | Specification | Reason |
| --- | --- | --- |
| Task | Three-way classification: `EN`, `RU`, `OTHER` (section 5.2) | One decision per word; no generation, so no hallucination |
| Input | Up to 20 key tokens of one word candidate, preceded by `BOS` and followed by `EOS` when the word is complete. Vocabulary 97 (section 5.1). Longer candidates keep their first 20 keys and no `EOS` | Words of 20 or more keys are 0.1% of types and are easy (10-key-and-longer accuracy is 0.99) |
| Embedding | `min(32, c)` dimensions, padding index 0 | A key token has no structure to learn beyond identity and Shift |
| Backbone | Three 1-D convolutions with kernel sizes 3, 5, 3, `c` channels each, same padding, ReLU, padded positions masked to zero | Local key patterns (the same information as 3-grams to 5-grams) with order preserved. Receptive field 1 + 2 + 4 + 2 = 9 keys per position |
| Pooling | Masked max and masked mean over positions, concatenated (`2c` values) | Fixed-size summary for words of any length; masking makes the result independent of padding (MD-6) |
| Head | Dropout 0.1 (training only), then one linear layer `2c` → 3 | Logits only; no softmax in the model. Temperature and priors are applied outside (section 10.1) |
| Reference size | `c` = 64: **42,595 parameters**, 170 KB in FP32, 38,912 multiply-adds per position (about 0.35 million for a 9-key word) | Section 7.3 |
| Permitted range | `c` = 32 (14,659 parameters) to `c` = 96 (86,915); hard cap 100,000 parameters | Section 7.3 |
| Parameter count of the reference model | Embedding 3,104; conv 1: 6,208; conv 2: 20,544; conv 3: 12,352; head 387 | Sums to 42,595 |

Layers, as asked in the brief: one embedding, three convolutional layers, one pooling operation and one linear layer, which is five layers with parameters (the embedding, three convolutions and the linear head) and one pooling operation without parameters. Section 7.3 shows that two or four convolutions give the same accuracy within noise.

### 7.2 Why a convolutional network on keys

Six model families were trained on the same data with the same recipe (section 18.6). Latency is the ONNX Runtime call on one thread of the cloud CPU, padded input of 22 positions.

| Family | Parameters | Type accuracy (test) | Latency p50 | Verdict |
| --- | --- | --- | --- | --- |
| Witten-Bell trigram per class (statistical stage) | 91,232 table entries | 0.9576 | 0.7 to 1.3 µs native, one candidate | Stage 5 of the cascade and the fallback (section 6) |
| Key-token CNN, 64 channels | 42,595 | 0.9639 | 63 µs | **Chosen** |
| Bidirectional GRU, 64 units | 41,507 | 0.9636 | 122 to 151 µs | Same accuracy at twice the latency; recurrent loops are the harder case for INT8 and for hand-written kernels |
| Transformer, 64 dimensions, 2 layers | 75,075 | 0.9592 | 330 µs | Five times slower and 0.5 points less accurate |
| Transformer, 128 dimensions, 4 layers | 546,179 | 0.9605 | 876 µs | Thirteen times the parameters, no gain |
| Transformer, 256 dimensions, 4 layers (the first draft's size, untrained) | 2,140,931 | not trained | 2,016 µs (random weights) | Rejected on latency alone: 32 times the CNN |
| Hashed n-gram bag (fastText style), 2,048 buckets | 131,123 | 0.9414 | 57 µs | 2.2 points less accurate: loses key order inside a word |
| Generative LLM, 500 million parameters | 500,000,000 | not applicable | not applicable | Hallucinates by construction (section 3.1) |

What the comparison says is simple: sequences of at most 22 tokens do not need attention or recurrence, and the cheaper operator is also the more accurate one here. The CNN also quantizes with the standard static INT8 recipe and runs as three loops in any language (section 12).

### 7.3 Size and depth

| Channels `c` | Parameters | FP32 size | Type accuracy | Accuracy at 3 / 4 keys | Native C latency p50, 9 keys |
| --- | --- | --- | --- | --- | --- |
| 4 | 603 | 6 KB | 0.9132 | 0.754 / 0.869 | 3.7 µs |
| 16 | 4,515 | 21 KB | 0.9471 | 0.772 / 0.910 | 4.4 µs |
| 32 | 14,659 | 60 KB | 0.9595 | 0.800 / 0.911 | 8.9 µs |
| 48 | 26,579 | 107 KB | 0.9627 | 0.790 / 0.913 | 16.6 µs |
| **64** | **42,595** | **170 KB** | **0.9639** | 0.784 / 0.923 | 28.9 µs |
| 96 | 86,915 | 343 KB | 0.9644 | 0.789 / 0.916 | 59.0 µs |
| 128 | 147,619 | 580 KB | 0.9640 | 0.794 / 0.919 | 105.3 µs |
| 192 | 318,179 | 1,246 KB | 0.9672 | 0.789 / 0.930 | 220.5 µs |

The native column was measured with a 16-dimension embedding for every `c`. Against the specified embedding of `min(32, c)` dimensions it has the same number of multiply-adds at `c` = 16, 14% fewer at `c` = 32, 8% fewer at `c` = 64, 6% fewer at `c` = 96, and more at `c` = 4 (2,880 against 1,584 per 9-key word). The column is a proxy for the reference size within about 10%, not a bound. The `c` = 192 row was trained for 6 epochs with the base recipe and is not strictly comparable.

**Reading the table.** Accuracy rises steeply up to about 15,000 parameters, is within 0.2 points of its plateau at 27,000 (`c` = 48), and is flat from 43,000 to 148,000. The seed spread of the reference model is 0.001 (three seeds: 0.9639, 0.9652, 0.9659), so differences below 0.002 are not findings. Accuracy at 3 keys stays at 0.78 to 0.80 at every size: three-letter words are ambiguous between languages, not hard for a small model (section 18.2), so capacity cannot fix them.

**Selection rule.** Take the smallest size within 0.2 points (two seed deviations) of the plateau, which is `c` = 48, then add one step as insurance, because real typing has more names, slang and typos than the proxy words. This gives `c` = 64. The step costs 12 µs and 63 KB, which is nothing against a budget of 100 µs and 400 KB, while a 0.5-point shortfall on real data would be visible.

**Depth.** Two convolutions of kernel 5 (34,339 parameters) reached 0.9643; three convolutions of 3, 5, 3 reached 0.9639 and 0.9636 with 3, 3, 3 (34,403); four convolutions of 3, 5, 7, 3 (71,331) reached 0.9660. All are inside two seed deviations of each other (section 18.5). The specification fixes three layers because they are the configuration that was measured most widely, not because more or fewer are worse.

### 7.4 What is left out, and optional additions

| Candidate | Status | Reason |
| --- | --- | --- |
| Left context as network input (the third draft carries 64 characters) | Left out | Context is a prior on the answer, not evidence in the word. It enters through the deployment prior of section 10.2. Adding the previous word's flag to the head is an ablation for phase 2; it has not been measured |
| Lexicon features as inputs (as-typed reading known, converted reading known, frequency bucket) | Optional, phase 2 | The most likely accuracy gain for 3- and 4-key words, at the price of coupling the network to the lexicon version. Not measured; evaluate against the plain cascade |
| Ensemble of network and statistical stage | Optional, phase 2 | Evaluate agreement as a gate. Not measured |
| Character-level input | Rejected | The model would have to learn the key permutation (section 5.1) |
| Separate `ABSTAIN` class | Rejected | No labelling procedure exists (section 5.2) |
| Mixup | Rejected | Mixed key embeddings are not strings; no evidence of benefit (section 17.2) |
| On-device weight updates | Rejected | Risk of a drifting classifier (section 14.5) |
| Pretrained language model or distillation | Rejected for the typing path | Allowed offline to review labels (DT-6) |

### 7.5 Latency, size and memory gates

The gates apply to each reference device (section 12.3) and are measured by the protocol of section 12.4. Percentiles are over at least 20,000 warm calls. The "measured" column is from the cloud CPU and is a proxy until the reference devices are measured.

| Stage | p50 | p95 | p99 | Measured on proxy hardware |
| --- | --- | --- | --- | --- |
| Key-event callback (RT-1) |  |  | 1 ms | Not a model stage; reads the cached gate verdict and copies the event to a ring buffer |
| Stage 4: one hash look-up (exception list, lexicon, acronym list) | 100 ns | 150 ns | 250 ns | 12 to 32 ns per random probe in tables of 2 MB to 270 MB (section 18.7) |
| Stage 5: statistical stage, one candidate, both readings, up to 9 positions | 5 µs | 10 µs | 20 µs | 0.7 µs (2 MB table), 1.3 µs (34 MB), 1.7 µs (270 MB) |
| Stage 6: network forward pass, `c` = 64, FP32, one thread | 50 µs | 100 µs | 250 µs | 29 to 39 µs p50 and at most 71 µs p99 native at 9 keys; 72 / 109 / 154 µs at 22 keys; ONNX Runtime from Python 53 to 70 µs p50 |
| Whole decision, stages 2 to 7, one candidate | 150 µs | 500 µs | 1 ms | Not yet assembled; one network call at 9 keys is 29 to 39 µs |
| Boundary key to corrected text (stage 8 included) |  | 50 ms | 150 ms | Depends on the accessibility API, measured in the end-to-end suite |
| Model file, FP32 |  |  | 400 KB | 170 KB |
| Resident memory of the engine |  |  | 30 MB | Not yet measured |
| CPU share while typing at 5 words per second |  |  | 0.5% of one core | 5 words per second at 150 µs is 0.08% |

The decision runs once per word, about every 0.2 to 0.5 seconds of typing, and not once per key (except in the optional early mode of section 10.5). One millisecond is therefore the correct order of magnitude for a budget, and nothing in the product gets better by being faster than that.

**End-to-end latency by phase.** The time from the Space to a corrected field is the sum of the phases below. The product gates the sum (the row "Boundary key to corrected text" above), but every phase is measured and reported on its own, per device, per application and per method (reports D6 and D7), so that nobody optimises a stage that is not the bottleneck. The network is not shrunk, quantised or replaced by a more complex model until the report shows that phase P3 holds the largest share of the end-to-end p95; the proxy figures suggest the opposite, since a network call costs microseconds and an operating-system call costs milliseconds, and the report either confirms that or contradicts it.

| Phase | What it covers | Budget | Reported as |
| --- | --- | --- | --- |
| P1 | The key event from the OS callback to the queued event (13.2, RT-1) | 1 ms at p99 | Per OS; with and without the hook-health observer of 13.7 |
| P2 | The fresh gate query at the decision point (13.1) | 20 ms at p99 | Per application class |
| P3 | The decision, stages 2 to 7, one candidate | The rows of the table above | Per scorer kind and key-length bucket |
| P4 | Read and match: caret and range read through the text interface (13.2, step 3) | P4 + P5 + P6 within the row "Boundary key to corrected text" | Per application and method |
| P5 | Write: the replacement, M1 as one operation or M2 as one batch | Idem | Per application and method |
| P6 | Verify: read-back of the whole fragment and the caret (13.2, step 5) | Idem | Per application and method |
| P7 | Rollback: the second write and read, on failure only | Not in the sum; its share is reported with the failure rate | Per application and method |

The end-to-end time is P2 + P3 + P4 + P5 + P6 and must meet the 50 ms p95 and 150 ms p99 of the row above; the hard deadline of the transaction is 250 ms (13.2). A phase that exceeds its budget in some application lowers that application's status (13.8), because a slow replacement is a replacement the user can type into.

**The requester's 0.0001 ms target.** The target is 100 ns. It is met by the stage that needs it and cannot be met by the network:

- A hash look-up costs 12 to 32 ns measured, so one to eight probes fit in 100 ns. Lexicon and exception look-ups meet the target; that is what the stage-4 row of the table gates.
- The n-gram stage needs 54 probes per candidate (two readings, nine positions, three classes) and takes 0.7 to 1.7 µs, which is 7 to 17 times over.
- The smallest network measured has 603 parameters (`c` = 4) and needs about 1,600 multiply-adds for a 9-key word (2,900 for the 16-dimension embedding of the native measurement in 7.3, which is the variant that took 3.7 µs). At 100 ns that is 16 billion multiply-adds per second on one core (29 billion for the measured variant), a large share of the peak of a SIMD core with perfect utilisation and no overhead. A naive loop took 3.7 µs. Its type accuracy is 0.913, 5 points under the reference model.
- The reference network needs about 350,000 multiply-adds per candidate. At the peak rate of one Apple performance core (about 100 billion floating-point operations per second) the floor is 7 µs, and measured loops are at 29 µs.

The specification therefore sets the budget where it is useful (section 7.5, table above) and states plainly that no model of acceptable accuracy runs in 100 ns. The two earlier drafts that called the target impossible or unrealistic were right; they did not give the numbers.

### 7.6 Requirements

| ID | Requirement |
| --- | --- |
| MD-1 | The model MUST be a classifier over key tokens with exactly three outputs (`EN`, `RU`, `OTHER`). It MUST NOT produce text. |
| MD-2 | The first release MUST use the CNN of 7.1. Another family MAY replace it only if, in the protocol of section 18.6 with at least three seeds, it gains at least 0.5 points of type accuracy or lowers the false-positive rate by at least 30% at equal recall, and still meets 7.5. |
| MD-3 | The model MUST have at most 100,000 parameters and at most 400 KB in FP32. The reference is 64 channels; the permitted range is 32 to 96. |
| MD-4 | The backbone MUST be three convolutions (kernels 3, 5, 3). A change of depth MUST be backed by a measurement with at least three seeds (section 18.5). |
| MD-5 | The input MUST be at most 20 key tokens plus `BOS` and `EOS`; longer candidates keep the first 20 keys without `EOS`. |
| MD-6 | Padding MUST NOT change the output: logits for a sequence padded to 22 and for the same sequence at its true length MUST agree within 1e-5. This test MUST run in continuous integration. |
| MD-7 | A statistical stage (stages 4 and 5) MUST exist and MUST work alone. The network ships only if it passes EV-12. |
| MD-8 | The model card MUST report accuracy per key length (2, 3, 4, 5 to 6, 7 to 9, 10 and more) and per class, with seed spread. |
| MD-9 | The latency, size and memory gates of 7.5 MUST be met on every reference device. |
| MD-10 | The runtime SHOULD run the network at the true length of the candidate instead of the padded length of 22; the measured cost grows about linearly with length (section 18.7). |
| MD-14 | The trainer MUST export the weights in the format LFW1 of 20.11 in addition to the ONNX file of DP-1. The native runtime and the ONNX file MUST reproduce the reference forward pass of 20.11 within 1e-5 per logit on the toy weights of 20.12 and within 1e-4 per logit on at least 100,000 key sequences of the exported network. The size of an LFW1 file MUST equal 16 + 4 × (number of convolutions) + 4 × (parameter count) bytes. |

### 7.7 The statistical baseline (stages 4 and 5)

The baseline can become the shipped scorer (EV-12), so it is specified end to end here: what goes in, what is counted, which formula turns counts into a score, how the score is calibrated, and in which files it is stored. The reference code is 20.10 and the test vectors are in 20.12. Stage 4 only vetoes or allows; it never converts a word by itself. Stage 5 produces three logits that enter the calibration path of 10.1 like the network's logits.

| Item | Specification |
| --- | --- |
| Input | The token row of the network (MD-5, 20.2): `BOS`, the keys of the candidate core as tokens 1 to 94 (at most 20), and `EOS` only if the word is complete and was not truncated. An early-detection prefix has no `EOS`. The input is keys, not text, and not either reading of the word. |
| Classes | `EN`, `RU`, `OTHER`, as in 5.2. One model per class. |
| Training rows | The rows of `S-TRAIN` exactly as the network sees them (8.3): one count per row, full words and the 35% prefix rows without `EOS`, case variants included. There is no separate corpus, so the baseline and the network cannot differ by data. |
| Model | Interpolated Witten–Bell, order 3: contexts of 0, 1 and 2 tokens, vocabulary 97, base distribution uniform at 1/97. |
| Probability | For token `w` after context `h` at order `k`: `p_k(w \| h) = (c(h,w) + u(h) · p_{k−1}(w \| h')) / (t(h) + u(h))`, where `h'` is `h` without its oldest token, `c` the count, `t(h)` the sum of `c(h, ·)` and `u(h)` the number of distinct tokens seen after `h`. If `t(h)` is 0 (unseen context) then `p_k = p_{k−1}`. The estimate is never 0, so no logarithm of 0 occurs. |
| Row score | `log p(row \| class)`, the sum over every token after `BOS` (including `EOS` when present) of `log p(token \| the two tokens before it)`. **No length normalisation.** The three classes are scored on the same row, so its length cancels in the posterior; dividing by the length would flatten the confidence and break the meaning of the thresholds. |
| Class logits | `z_c = log p(row \| c) + log π_train(c)`, with `π_train` the share of each class in the training rows, stored in the file. |
| Pruning | None in the first release: every count is kept. In the proxy experiment the three tables held about 91,000 entries (18.6), far below the size gate of 12.5. A pruned table is a new release and must repeat the EV-12 comparison. |
| Calibration | `kind = ngram` in the path of 10.1: its own temperature (negative log-likelihood on `S-VAL`, then on `R-CAL`, CA-1) and its own threshold table `λ` per direction and bucket, by the procedure of 10.3 on `R-CAL`. The independence assumed between tokens is false, so the raw posterior is expected to be over-confident and the fitted `T` above 1; this is checked, not assumed. |
| Stage 4 tables | The lexicon, acronym and allow-list tables of 10.4, built by D3 from the sources of 8.9. A key is `FNV-1a-64(tag ‖ UTF-8 bytes of the case-folded string)` with the tag byte `0xE0 + t` and `t` = 1 lexicon EN, 2 lexicon RU, 3 acronyms EN, 4 acronyms RU, 5 user exceptions EN→RU, 6 user exceptions RU→EN. A hash match counts as a word match (DP-5 keeps 64 bits so that false matches are negligible). |
| Files | `LFB1` for the three n-gram models and `LFL1` for the stage-4 tables; layouts in 20.10. Both are little endian, written by D3 with a build script, and listed with their SHA-256 in the model package (D5). |
| Cost | Up to 21 positions, three orders and three classes, each with one context probe and one pair probe of 12 to 32 ns; measured 0.7 to 1.7 µs per candidate (18.7). |

**What a match does.** The matrix of 10.4 is the whole rule. A word of the active language (row 10), an acronym (row 9), a user exception (row 7) and a shape guard (row 8) each end in KEEP before any score is computed. A 2-key word is decided by the allow-list alone (row 11). Every other word is scored. The lexicon of the target language is not consulted in the first release.

**Order of building (D3).** (1) Read the manifest of 8.9 and verify every hash. (2) Build the rows of `S-TRAIN` with the pipeline of 8.3 and the run seed. (3) Count, per class, the contexts and the pairs of orders 0, 1 and 2. (4) Write `LFB1`. (5) Build the lexicon, acronym and allow-list tables and write `LFL1`. (6) Fit `T` and `λ` (10.1, 10.3) and write the calibration package. (7) Run the conformance tests of 20.12. Steps 1 to 5 are deterministic: the same manifest and seed give the same bytes.

| ID | Requirement |
| --- | --- |
| MD-11 | The baseline MUST be exactly the model of this section: Witten–Bell, order 3, over the token rows of 20.2, trained on the rows of `S-TRAIN`, with no length normalisation and no pruning in the first release. |
| MD-12 | The runtime log-probabilities MUST equal those of the reference code (20.10) on the vectors of 20.12 within 1e-9, and the class logits MUST enter the calibration path with `kind = ngram`. |
| MD-13 | The tables MUST be stored and checked in the formats `LFB1` and `LFL1` of 20.10; a table whose magic, size or SHA-256 does not match MUST be treated as missing (13.5, rows 4 and 5). |

## 8. Data

The classifier needs correctly typed text in both languages, labelled by language, plus a large and varied set of things that must never be touched. No public dataset of real wrong-layout typing turned up in my search, so wrong-layout data is synthesised exactly, and the effort goes into making the source text realistic.

### 8.1 Key property: no corruption step for the classifier

The model sees key sequences and predicts the intended language (section 5.1). A Russian word typed on a Russian layout and the same word typed by mistake on an English layout produce the **same key sequence and the same label**. Training pairs are therefore just `(keys of correctly typed text, language)`. Synthetic wrong-layout events are needed only for end-to-end tests, for the decision policy, and for any component that sees the active layout.

### 8.2 Sources

| Source | Use | Licence and status |
| --- | --- | --- |
| [Wikipedia RU/EN dumps](https://huggingface.co/datasets/wikimedia/wikipedia) (snapshot 20231101: 1.95M RU and 6.41M EN articles) | Vocabulary, names, formal text | CC BY-SA 3.0 and GFDL. Encyclopedic register: train only; never the sole test source |
| [FrequencyWords](https://github.com/hermitdave/FrequencyWords) (OpenSubtitles 2016/2018 lists) | Conversational word frequencies, slang | Code MIT, content CC BY-SA 4.0 per its README. Word lists, no sentences |
| `wordfreq` Python package (multi-source frequency lists) | Frequency-weighted word sampling, used in the section 18 experiments | Check the data licence before release use |
| Tatoeba sentences | Short everyday RU and EN sentences | Mostly CC BY 2.0 FR; verify per sentence set |
| OpenSubtitles / OPUS text | Dialogue style | Terms restrictive and unclear; use derived frequency lists only unless counsel clears it |
| Web-crawl corpora (CC-100, OSCAR, Common Crawl derivatives) | Scale, slang, code-switching | Per-document licences unclear; filtered subsets after legal review |
| Permissively licensed code and package registries | Identifiers, CLI commands, package names, file names (`OTHER`) | Keep only permissive licences; strip secrets and tokens |
| Wikidata labels, Wikipedia titles | Person, place and brand names in both scripts | CC0 (Wikidata); titles under Wikipedia terms |
| Hunspell `ru_RU`, `en_US` dictionaries | Spelling coverage, lexicon tests | Licences differ (MPL, LGPL, GPL): check each |
| Opt-in real typing (own corpus) | Realistic test set, hard negatives | Informed consent, anonymisation, local processing (section 8.8) |

The table lists source classes. The exact artefacts of the first release, how each is pinned and cleaned, which are mandatory and what replaces one that is unavailable are in 8.9; the licence of each is checked separately (DT-10).

**Excluded: `anzorq/kbd_lat-835k_ru-3M`.** The first draft used it as 835K English plus 3M Russian sentences. I checked the dataset card: it holds 3,835,531 rows in one `text` column, described as "Kbd latin script: 835k lines from a scraped pile" and "ru: 3M lines from Wiki (OPUS)". `kbd` is the ISO 639-3 code for Kabardian, not "keyboard", so the Latin part is Kabardian, not English. Its licence is listed as "unknown". The Russian part duplicates better-documented sources. It must not be used.

### 8.3 Synthesis pipeline

1. **Collect and clean.** Deduplicate (exact plus MinHash near-duplicates), drop broken encodings, remove personal data and secrets, record source id, licence and retrieval date, and assign every item a `split_group` (document id, or lemma for word lists).
2. **Encode as typed.** Render each text through the layout of its own language into `(key, shift)` events, keeping punctuation, digits and case.
3. **Case variants.** Lower case 72%, Capitalised 20%, ALL CAPS 5%, random mixed 3%. Without ALL CAPS the model never sees `GHBDTN`.
4. **Weight by frequency, not uniformly.** Sample a word type with multiplicity `clip(floor(zipf - 2), 1, 5)` so frequent words dominate but rare ones are still seen. Keep running-text frequency for evaluation weights.
5. **Mixed-language text.** Russian sentences with Latin brands and technical terms, and English sentences with Russian names. Labels are per word; the key sequence of each word comes from the layout of its own language.
6. **`OTHER` content**, about 20 to 25% of training items: identifiers (snake\_case, camelCase, flags), URLs, e-mails, paths, file names, versions, numbers with units, hashes, UUID fragments, shell commands (`kubectl`, `git`, `ls`), acronyms typed in Latin, transliteration (`privet`, `spasibo`) with noise, key-mashing (`asdfgh`), repeated characters, random password-like strings.
7. **Key-level noise** on at most 5 to 8% of words, label unchanged: adjacent-key substitution, deletion, duplication, transposition. The task is to decide the language, not to repair typos.
8. **Prefixes for early detection.** 35% of samples are cut to a random prefix of 2 or more keys with no end-of-word token (section 10.5).
9. **Hard-negative mining.** After a first model, run it over held-out parts of the training sources, collect confident mistakes and add them with their true labels. The test sets are never mined.

### 8.4 Splits

| Set | Kind | Role | Built from | May be used for |
| --- | --- | --- | --- | --- |
| `S-TRAIN` | Synthetic | Fitting the network and the statistical stage | 80% of the `split_group`s of the sources of 8.2 | Training only |
| `S-VAL` | Synthetic | Early stopping, checkpoint choice, first fit of temperature and thresholds | 10%, by `split_group` and lemma, stratified by class and word length | Tuning |
| `S-TEST` | Synthetic, locked | Regression and ablations | 10%, by `split_group` and lemma | Reporting; never tuning |
| `R-CAL` | Real, opt-in users | Real calibration: `w`, `o_lat`, final temperature, final threshold table (10.2, 10.3) | Participants assigned by the rule below | Fitting calibration; never the network weights |
| `R-ACC` | Real, opt-in users, locked | Release acceptance: EV-1 and the gates that name it (11.2) | Participants assigned by the rule below | At most 3 evaluations, no tuning, ever |
| `R-NAT` | Real, natural wrong-layout events | `w`, run lengths, a recall check (11.5) | Words converted by hand or left after an automatic correction, from `R-CAL` participants | Estimation and reporting; too small to gate |
| Stress sets | Synthetic, locked | Targeted failures, EV-2 and EV-9 | Short ambiguous words, acronyms, names, transliteration, code and URLs, mixed language, ALL CAPS, Caps Lock, typos, unseen domain | Reporting |

Split by document and by lemma, not by word form: Russian inflections of one lemma in both train and test inflate accuracy. The proxy experiment in section 18 splits by word form only, so its numbers are optimistic.

**Assignment of real data.** Every participant gets a pseudonymous id at enrolment. The participant belongs to `R-CAL` if `int(SHA-256(salt ‖ id)) mod 100 < 35` and to `R-ACC` otherwise; the salt is drawn once per study and stored apart from the data. Enrolment continues until `R-ACC` has at least 20 users and `R-CAL` at least 10 (plan for 40 enrolments to cover drop-outs). The assignment depends on the id only, never on what the user typed, and all documents of a user stay in the user's set.

**Disjointness differs for synthetic and real data.**

- `S-VAL`, `S-TEST` and the stress sets are disjoint from `S-TRAIN` by `split_group` and by lemma, which removes the inflection leak of the proxy experiment.
- `R-CAL` and `R-ACC` are disjoint from each other and from every training source by user, by document and by source. Nothing a participant wrote enters a training source, and the sources are fixed in the manifest (8.9) before enrolment starts.
- `R-CAL` and `R-ACC` are deliberately **not** lemma-disjoint from training. Removing every word whose lemma occurs in training would delete the frequent words, which decide the false-positive rate of running text, and would turn the set into a rare-word test. The report states the overlap instead: the share of `R-ACC` tokens, and of types, whose word form also occurs in `S-TRAIN`. The resulting optimism is the same for every candidate model, so comparisons (EV-12) stay fair.

**What each set may estimate.**

- The wrong-layout probabilities `w`, the share `o_lat` and the run lengths (10.2): `R-CAL` and `R-NAT` only.
- Temperature and threshold table (10.1, 10.3): a first fit on `S-VAL`, the final fit on `R-CAL` (CA-1). The weights of the network are never trained on `R-CAL` or `R-ACC`.
- The release decision (EV-1 to EV-12): `R-ACC` only, with the package frozen by CA-6.

**Use limit of `R-ACC`.** At most 3 evaluations, each logged with date, candidate hash and operator. After the third, or after any evaluation that was followed by a change of the model, the thresholds, the priors or the lexicon, `R-ACC` is retired: a new one is collected from new users and the retired set joins `R-CAL`. A change that only repairs the evaluation harness does not retire it.

### 8.5 Realistic test set protocol

- **Enrolment.** At least 35 bilingual users, with at least 20 in `R-ACC` and 10 in `R-CAL` (8.4), for at least two weeks each: chat, e-mail, documents and some code. A *document* is one continuous composition (a message thread, an e-mail, a file, a note); `R-ACC` needs at least 100. Anonymise at capture: hash identifiers, remove names, numbers, addresses, keys and credentials. Secure fields are never captured (13.1).
- **Negatives** are real, correctly typed words, every `OTHER` item included. `R-ACC`: at least 100,000 words (rule of three, 11.3). `R-CAL`: at least 50,000. No user may supply more than 10% and no document more than 2% of the words of a set; the excess is dropped at random, with a logged seed, before any model is run.
- **Positives** are real sentences in which 1 to 5 consecutive words are re-rendered on the wrong layout, with realistic placement after a layout switch: at least 20,000 per direction in `R-ACC` and 10,000 in `R-CAL`. They are synthetic by construction. They measure whether the policy converts wrong-layout words correctly, not how often users really err; that is the job of `R-NAT` (11.5).
- **Fixed sample.** The number of words is fixed before the first evaluation and is not extended after it; more data after a look is a new `R-ACC` (8.4).
- Publish the length, class, user and source distribution with the report, and the evidence table of 11.7.

### 8.6 Volume

Train on 0.5 to 2 million items to start, after deduplication, and extend only if the learning curve says so (section 18.4 reports the measured curve). Millions of near-duplicate synthetic items add nothing; the number of distinct words, names and sources is what counts.

### 8.7 Requirements

- **DT-1** The data pipeline MUST be deterministic given a seed and a layout-table version, and MUST write a manifest (source, licence, hash, filters, split ids).
- **DT-2** The classifier input MUST be key tokens; no character-level text may enter the model (section 5.1).
- **DT-3** Every source MUST have a licence entry before inclusion in a release dataset. Unknown licence means research use only.
- **DT-4** `OTHER` MUST cover at least the categories listed in 8.3, step 6, each with its own stress set and its own false-positive rate in the report.
- **DT-5** `S-VAL`, `S-TEST` and the stress sets MUST be disjoint from `S-TRAIN` by `split_group` and by lemma. `R-CAL` and `R-ACC` MUST be disjoint from each other and from every training source by user, document and source; they are not lemma-disjoint, and the report MUST state their word-form overlap with `S-TRAIN` (8.4). `R-ACC` MUST NOT be used for tuning.
- **DT-6** Text generated by an LLM MAY be used for training augmentation after filtering and deduplication, and MUST NOT appear in any test set.
- **DT-7** Real participants MUST be assigned to `R-CAL` or `R-ACC` by the hash rule of 8.4, before any of their data is looked at. `R-ACC` MUST be evaluated at most 3 times and retired as stated in 8.4.
- **DT-8** Each set MUST be used only for the purposes in the table of 8.4. The harness MUST tag every run with the role of the set and MUST refuse to write a threshold, temperature or prior fitted on `R-ACC`.
- **DT-9** The manifest MUST name, for every artefact of 8.9, its exact path or identifier, version or date, SHA-256, licence and retrieval date. D2 MUST fail with a non-zero exit when an artefact is missing or its hash differs; a replaced source is a new manifest version and every report is re-run.
- **DT-10** The licence check is a release gate separate from the technical download. Every source has a `licence_status` (`cleared`, `research_only` or `blocked`) signed by a named reviewer; a release dataset contains only `cleared` sources.

### 8.8 Privacy

- Raw keystrokes MUST NOT be written to disk or sent anywhere without explicit opt-in consent. Fields marked secure or password MUST be excluded from processing, not only from logging.
- Collected evaluation data MUST be anonymised and deletable on request.
- Training text from the web MUST be scanned for secrets (API keys, tokens, private keys) before use.

### 8.9 First-release source manifest

The table fixes what the data pipeline D2 reads in the first release. Commit identifiers, shard hashes and export dates cannot be known before the first retrieval, so D2 records them on that first run; every later build verifies them and fails on any difference (DT-9). Paths are as the sources publish them, and D2 also fails if one does not resolve. **M** marks a mandatory source, **O** an optional one; a release needs all M rows.

| Id | Artefact | Pinned by D2 | Cleaning and selection | Role, status, if unavailable |
| --- | --- | --- | --- | --- |
| C1 | `wikimedia/wikipedia` on Hugging Face, configurations `20231101.ru` and `20231101.en` | Dataset revision and the SHA-256 of every shard | Strip markup, headings, lists, tables and references. Split sentences at `.`, `?` or `!` followed by a capital letter. Keep 3 to 30 words. Exact and MinHash de-duplication (5-word shingles, Jaccard 0.8). At most 200,000 sentences per language, drawn with the run seed | Words, names, formal register. **M**. If unavailable: a dump of another date, recorded as a new manifest version |
| C2 | `wordfreq` from PyPI, the version used in the section 18 experiments ("large" lists) | Package version and the SHA-256 of the wheel | Words written only with a–z, or only with а–я and ё; the 100,000 most frequent per language | Frequency weights, the lexicons of 10.4, the proxy experiments. **M** |
| C3 | FrequencyWords, `content/2018/ru/ru_full.txt` and `content/2018/en/en_full.txt` | Repository commit and the SHA-256 of both files | Letters of one script only, count of at least 5 | Conversational frequencies and slang. **O**. If unavailable: C2 alone |
| C4 | Tatoeba per-language sentence exports for Russian and English (downloads page) | Export date and SHA-256 | At least 2 words, one script per sentence unless mixed by design | Short everyday sentences. **O** |
| C5 | Code identifiers: the CPython 3.12 standard library and 500 PyPI packages under MIT, BSD or Apache-2.0 licences, the list stored in the manifest | Exact versions and the SHA-256 of each source archive | Split with the Python tokenizer and a regular expression for flags, paths and URLs. Drop bare lowercase dictionary words (indistinguishable from rare words, 18.1). Scan for secrets and drop every hit | `OTHER` content. **M**. A substitute needs permissive licences |
| C6 | The synthetic `OTHER` generators of 8.3, step 6 | Hash of the script and the seed | As in 8.3 | `OTHER` content. **M** |
| C7 | Wikidata labels (`ru`, `en`) of persons, places and organisations | Dump date and SHA-256 | Labels of 2 to 40 characters in one script, the 50,000 with most sitelinks per language | Names. **O** |
| C8 | Hunspell `ru_RU` and `en_US` dictionaries | Version and SHA-256 | None | Lexicon tests only, never training. **O** |

**Rules.** Every artefact has a licence entry before use (DT-3), and the licence status is signed off separately from the technical download (DT-10). Where a source is replaced, the manifest version changes, the data are rebuilt from the seed and every report is regenerated; numbers from two manifest versions are never mixed in one table.

## 9. Training recipe

The network has 15,000 to 90,000 parameters and is trained from scratch in plain PyTorch. The recipe below was chosen by the ablations of section 18.5 on proxy data. The numbers that matter most are the learning rate and the number of optimizer steps; the usual regularisers do nothing here, and the one that the earlier drafts asked for (label smoothing) hurts.

### 9.1 Recipe

| Item | Value | Evidence (section 18.5) |
| --- | --- | --- |
| Loss | Cross-entropy over three classes, unweighted | Class balance comes from the sampling multiplicities of section 8.3 and is corrected at inference by the prior shift (CA-2). Class weights in the loss would double-count it |
| Optimizer | AdamW, betas (0.9, 0.999), weight decay 0.01 | Weight decay 0, 0.01 and 0.1 gave 0.9638, 0.9639 and 0.9635 |
| Peak learning rate | **5e-3** | Accuracy rose monotonically from 3e-4 (0.9488) to 1e-2 (0.9686) at fixed steps. 5e-3 was confirmed with three seeds (0.9677 ± 0.0007) |
| Schedule | Linear warm-up over 3% of the steps, then cosine decay to 2% of the peak | Used in every run; not ablated |
| Batch size | **256** | 128: 0.9674 at twice the time; 512: 0.9639; 2048: 0.9525 (too few steps) |
| Optimizer steps | **About 10,500** (12 passes over 223,378 rows) | Accuracy depends on the number of steps, section 9.3 |
| Gradient clipping | Global norm 1.0 | Used in every run; not ablated |
| Dropout | 0.1, before the linear head only | 0, 0.1 and 0.3 gave 0.9649, 0.9639 and 0.9638: no effect |
| Label smoothing | **0** | 0.05 and 0.1 gave the same accuracy and a worse log-likelihood after calibration (0.1076 and 0.1137 against 0.0993) |
| Mixup | Not used | Mixed key embeddings are not strings (section 17.2); no evidence of benefit |
| Prefix rows | 35% of rows cut to a random prefix of 2 or more keys without `EOS` | Costs 0.2 to 0.3 points on whole words and buys 2 to 7 points on 2- to 5-key prefixes. Set to 0 if early detection (section 10.5) is dropped |
| Augmentation | Fresh case variants and prefix cuts every epoch (72% lower, 20% Capitalised, 5% UPPER, 3% mixed) | The training set is regenerated per epoch from the same word types |
| Key-level typos | 5% to 8% of rows (section 8.3) | **Not exercised in the proxy experiments**; tested in phase 2 through EV-8 |
| Initialisation | PyTorch defaults | Not ablated |
| Batching | Rows sorted by length inside chunks of 50 batches, batches shuffled, padding trimmed to the longest row | Speed only: masked pooling makes the output independent of padding (MD-6) |
| Seeds | At least 3 for every reported number; seed 0 for development | Seed deviation of type accuracy 0.0007 to 0.0010 |
| Cost | 133 to 140 s for 64 channels and 81 to 84 s for 32 channels on the 2-vCPU Xeon, two threads | Cost is set by steps times batch size, not by corpus size |

### 9.2 What did not matter, and what did

- **Under-training is the main risk.** Learning rate 3e-4, 2 epochs and batch 2048 each cost 1.5 to 2 points. The three drafts' recipes (section 17.1) all sit on the slow side of the grid: 0.9624, 0.9597 and 0.9602 against 0.9677.
- **Regularisers can be fixed and forgotten.** Weight decay, dropout, kernel layout and a fourth convolution moved accuracy by less than two seed deviations. They are not tuned.
- **Label smoothing is unnecessary and harmful for this pipeline.** It does not improve accuracy. It shifts the probabilities so that the fitted temperature drops to 0.61 to 0.74 (it has to undo the smoothing) and the log-likelihood after calibration is worse. The decision policy relies on probabilities in the 0.995 to 0.9999 range (section 10.3), which smoothing caps (0.9333 at 0.1 for three classes) until the temperature repairs them. If a team uses it anyway, CA-7 applies.
- **Data beats model size.** Halving the training set costs 0.9 points (section 18.4); halving the channels from 64 to 32 costs 0.15 points with this recipe. Spend effort on distinct words, names and sources (section 8.6) before training longer or wider.

### 9.3 Steps, not epochs

On the proxy data the accuracy of the reference model is a function of the number of optimizer steps and saturates at about 7,000 to 10,000 steps. Rows are 223,378 per epoch.

| Optimizer steps | Setting (learning rate 2e-3 unless stated) | Type accuracy |
| --- | --- | --- |
| 870 | Batch 512, 2 epochs | 0.9509 |
| 880 | Batch 2048, 8 epochs | 0.9525 |
| 1,750 | Batch 512, 4 epochs | 0.9599 |
| 3,500 | Batch 512, 8 epochs (base recipe) | 0.9639 |
| 7,000 | Batch 512, 16 epochs | 0.9668 |
| 10,500 | Batch 256, 12 epochs, learning rate 5e-3 (chosen) | 0.9677 |
| 14,000 | Batch 128, 8 epochs | 0.9674 |

The consequence for real data is practical. With a corpus of 0.5 to 2 million rows (section 8.6) one pass at batch 256 is already 2,000 to 8,000 steps, so 2 to 5 passes are enough. Specify the budget as steps (TR-3) and let the number of passes follow from the corpus size. A lower learning rate cannot be bought back with steps: the first draft's recipe (2e-4) used 35,000 steps and still reached only 0.9624.

### 9.4 Tuning protocol on real data

1. **Fix** weight decay 0.01, dropout 0.1, kernels 3, 5, 3, no label smoothing, 35% prefix rows, schedule and clipping as in 9.1.
2. **Learning rate.** Train the 64-channel model at 3e-3, 5e-3, 1e-2 and 2e-2 with batch 256 and 10,000 steps, one seed. The best rate on the proxy data was at the top of the grid, so the search must bracket it.
3. **Batch and steps.** At the best rate: batch 128, 256, 512 and 8,000, 12,000, 20,000 steps. Stop when the gain is below the tie width.
4. **Size.** Train 32, 48 and 64 channels with three seeds each and apply the selection rule of section 7.3.
5. **Confirm** the final setting with at least 3 further seeds and report mean and standard deviation (EV-13).

The metric for steps 2 to 4 is the validation negative log-likelihood after temperature scaling (it is smooth and seed-stable), checked against validation recall at a fixed false-positive rate. **Tie width:** a difference of less than 0.002 in type accuracy or less than 0.003 in log-likelihood (two seed deviations: 0.0010 and 0.0015) is a tie, and ties are resolved towards the cheaper setting. The test sets are never used in this loop.

### 9.5 Checkpoint selection

- **Use the last checkpoint** of the schedule. The cosine decay ends at 2% of the peak rate, so the last epoch is the best-converged one; every experiment of section 18 used it. Do not select an epoch by validation accuracy: it is too coarse at the 1e-4 level that matters.
- If a different schedule is introduced, select by validation log-likelihood after temperature scaling, then confirm that the tail calibration check (CA-4) passes. Never select by a test-set figure.
- Of several seeds, release the one with the median validation log-likelihood, not the best: the best of several is optimistic, and the spread is part of the report.
- Fit the temperature, the threshold table and the priors after the checkpoint is frozen (CA-1 to CA-3), and store them with the checkpoint hash (D5).

### 9.6 Hardware and tooling

The whole model trains in minutes on one laptop. The requester's Apple M1 Max with 32 GB is more than enough; no GPU, no cluster and no half-precision tricks are needed.

- **Framework:** PyTorch on the CPU. The Apple GPU (MPS) is allowed, but a 43,000-parameter convolution on a batch of 256 rows is too small for it to help, and MPS kernels are not bit-reproducible, so section 15.2 requires a parity check if it is used.
- **Unsloth** (mentioned in the brief) is a library for fine-tuning large language models with low-rank adapters and quantized weights. It is not applicable: there is no pretrained model to adapt, and the network is smaller than one LoRA adapter of a language model.
- **Local LLM on the same machine:** useful offline for drafting synthetic chat sentences and for reviewing doubtful labels (DT-6), never as a component of the classifier and never in a test set.
- **Export:** `torch.onnx.export`, opset 17, dynamic batch axis; parity check DP-1.

### 9.7 Requirements

| ID | Requirement |
| --- | --- |
| TR-1 | Training MUST be seeded, and every run MUST write a run record (section 15.2). Headline numbers MUST come from at least 3 seeds (EV-13). |
| TR-2 | The starting recipe is that of 9.1. A change MUST be justified by a measurement with at least 3 seeds and a difference above the tie width of 9.4. |
| TR-3 | The training budget MUST be stated in optimizer steps, at least 8,000 at batch 256, and MUST be re-checked on real data by the step grid of 9.4. |
| TR-4 | The loss MUST be unweighted cross-entropy. Label smoothing and mixup MUST NOT be used unless a measurement shows a gain after temperature scaling; if used, CA-7 applies. |
| TR-5 | Augmentation (case, prefixes, key-level typos) MUST be regenerated each epoch from the same word types, and prefix rows MUST be switched off if early detection is out of the product. |
| TR-6 | Model selection MUST use validation data only. The test sets MUST NOT be used for any choice, and every use of a locked set MUST be logged (section 11.6). |
| TR-7 | Hard-negative mining (section 8.3, step 10) MUST draw on held-out parts of training sources and MUST add the true label; mined items MUST NOT enter any test set. |
| TR-8 | The recipe MUST be run with the 32-channel and 64-channel models so that the size rule of section 7.3 can be re-applied on real data. |

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

## 12. Compression and deployment

The network specified in section 7 has 15,000 to 90,000 parameters and weighs 60 to 350 KB in FP32, so compression is a measurement, not a plan: the default is to ship FP32 and to compress only when a written gate of section 7.5 fails. The earlier drafts required mixed INT4/INT8 for a 1 to 5 million parameter model; that was a fix for a model that is 50 times larger than needed.

### 12.1 What was measured

All figures are from the feasibility experiments (section 18.7) on a 2-vCPU Intel Xeon at 2.1 GHz, ONNX Runtime 1.29 with one thread, and the proxy data of section 18.1. Latency is the ONNX Runtime call from Python including its call overhead; the native C figures of section 7.5 are lower.

| Variant | Model | Size on disk | Type accuracy | Latency p50 (p95) |
| --- | --- | --- | --- | --- |
| FP32 | c16 (4.5K params) | 20.8 KB | 0.9471 | 33.7 µs (66.6) |
| FP32 | c32 (14.7K) | 60.4 KB | 0.9595 | 43.0 µs (76.4) |
| FP32 | c64 (42.6K) | 169.6 KB | 0.9639 | 69.6 µs (152.7) |
| FP32 | c128 (147.6K) | 579.8 KB | 0.9640 | 140.7 µs (262.8) |
| Static INT8 (QDQ) | c16 | 19.9 KB | 0.9466 | 33.3 µs (62.0) |
| Static INT8 (QDQ) | c32 | 30.6 KB | 0.9589 | 41.3 µs (75.6) |
| Static INT8 (QDQ) | c64 | 59.4 KB | 0.9630 | 53.2 µs (117.5) |
| Static INT8 (QDQ) | c128 | 165.0 KB | 0.9634 | 59.6 µs (101.1) |

Static INT8 (per-channel weights, uint8 activations, calibrated on the validation set) costs at most 0.0009 of type accuracy at every size. It makes the file 2.9 times smaller for c64 and 3.5 times for c128, and it speeds up the call only from c64 upward (24% for c64, 58% for c128). Below c64 the call is dominated by fixed overhead and INT8 changes nothing.

Weight-only compression was measured by simulating symmetric per-channel quantization of the weights (simulation only: it shows the numeric damage, not a speed-up):

| Weight bits | c16 | c32 | c64 | c128 |
| --- | --- | --- | --- | --- |
| 32 (reference) | 0.9471 | 0.9595 | 0.9639 | 0.9640 |
| 8 | 0.9471 | 0.9595 | 0.9638 | 0.9641 |
| 6 | 0.9454 | 0.9601 | 0.9640 | 0.9640 |
| 5 | 0.9471 | 0.9593 | 0.9633 | 0.9638 |
| 4 | 0.9428 | 0.9573 | 0.9624 | 0.9628 |
| 3 | 0.8543 | 0.9338 | 0.9472 | 0.9532 |

The network tolerates 4-bit weights (a loss of 0.1 to 0.4 points, growing as the model shrinks) and breaks at 3 bits (1.1 to 9.3 points). That is a fact about robustness; it does not make 4 bits useful. For c64 it would save about 150 KB on a 170 KB file and no CPU kernel in ONNX Runtime executes 4-bit convolutions faster. Recall at a fixed false-positive rate moved by up to 4 points between variants in the same table, which is the noise level of the token-weighted metric (section 18.5), so every compressed variant must be re-checked at the EV-1 operating point rather than judged on accuracy alone.

### 12.2 Decision procedure

Apply the steps in order and stop at the first one that passes all gates of section 7.5.

1. **FP32 ONNX, 64 channels (default).** 170 KB, fits in the L2 cache of every reference device.
2. **Fewer channels.** Move to 48, then 32 channels. This reduces size, latency and memory together and was measured to cost at most 0.45 points of type accuracy at 32 channels (section 18.6). It is the cheapest lever and is tried before any numeric trick.
3. **Static INT8 QDQ.** Only for models of 96 channels or more, or when the size gate fails. Calibrate on validation data, refit the temperature and the threshold table afterwards (CA-1, CA-3), and re-measure the EV-1 operating point.
4. **Quantization-aware training.** Only if step 3 loses more than 0.3 points of type accuracy. Not expected from the measurements above.
5. **Anything below 8 bits, pruning, distillation:** not used (table below).

| Technique | Verdict | Reason |
| --- | --- | --- |
| FP16 weights | Not used | No CPU speed-up, saves 85 KB on c64 |
| Static INT8 (QDQ) | Optional | Measured: no accuracy cost, 24% to 58% faster from c64 up, nothing below |
| Dynamic INT8 | Not used | ONNX Runtime documents dynamic quantization as the choice for recurrent and Transformer models and static quantization for convolutional ones ([ONNX Runtime documentation](https://onnxruntime.ai/docs/performance/model-optimizations/quantization.html)) |
| 4-bit weights, palettisation | Not used | Numerically safe (table above) but saves under 150 KB and has no CPU kernel benefit; Apple's [optimisation overview](https://apple.github.io/coremltools/docs-guides/source/opt-overview.html) gives no speed-up numbers and notes some backends decompress to FP16 |
| Pruning, sparsity | Not used | A 43K-parameter dense model gains nothing from sparse storage |
| Knowledge distillation from a large model | Not used for compression | Nothing to compress. A large model may still be used offline to review labels (DT-6) |
| Apple Neural Engine through Core ML | Not used by default | One direct-dispatch measurement reports about 190 µs per call, almost all of it dispatch overhead ([arXiv 2606.22283](https://arxiv.org/pdf/2606.22283)), which is more than the whole c64 call on the CPU. Re-measure on the target Mac before any change |
| Hash tables for lexicon and n-grams | Used, with 64-bit keys | A 32-bit key table of 200,000 words returns a false "known word" for about 5 in 100,000 random strings, as large as the whole false-positive budget (EV-1) |

### 12.3 Runtimes

| Runtime | Role | Notes |
| --- | --- | --- |
| ONNX Runtime, CPU provider, one intra-op thread, sequential execution | Reference runtime for the network | The fixed cost of a call was 19 µs for a 1,555-parameter model in the measurements above (Python call included), so tiny models do not get faster than that through ONNX Runtime |
| Hand-written FP32 forward pass in the host language (C, C++, Rust, Swift) | Allowed | Three convolutions and a linear layer. A naive loop took 8.9 µs (c32) and 28.9 µs (c64) for a 9-key word on the Xeon (section 7.5). Avoids shipping a runtime of several megabytes. Requires the parity test of 12.5 |
| Core ML | Optional on macOS | Only if measured faster than the CPU path on the reference Mac; see the table above |
| PyTorch, MPS | Training and export only | Not shipped |

Reference devices for every gate: the requester's Apple M1 Max, one x86-64 laptop-class CPU with AVX2 (for example a 4-core Intel Core i5 or AMD Ryzen 5), and one low-end device (a dual-core laptop of about 2015). Numbers in this specification from the 2-vCPU Xeon are proxies and do not replace measurements on these three.

### 12.4 Measurement protocol

The protocol is mandatory for every latency number that is reported or gated.

- Single thread, warm process, at least 2,000 warm-up calls and at least 20,000 timed calls per configuration, monotonic nanosecond clock, nothing else running (training, indexing, browsers). Report p50, p95, p99 and the maximum.
- Report per key length (3, 5, 9, 15 and 20 keys) and for the token-weighted length mix of section 18.2, not for one length.
- Report four layers separately: (i) network forward pass only; (ii) segmentation, tokenisation and table look-ups; (iii) the whole decision, from the boundary key to a CONVERT or KEEP verdict; (iv) the key-event callback (RT-1).
- Report cold-start model load time, resident memory after one hour of simulated typing, and the size of every file in the package.
- Run with the real model files of the release candidate, not with random weights, and with the CPU in its normal power state. Record the device, OS version, compiler flags and runtime version in the run record (section 15.2).
- Latency of text replacement (accessibility API, clipboard) is measured separately in the end-to-end suite and is not part of the model budget.

### 12.5 Size and packaging budget

| Component | Budget | Measured on proxy data |
| --- | --- | --- |
| Network, FP32 | At most 400 KB | c64: 170 KB (ONNX file) |
| Statistical stage: n-gram tables | At most 8 MB | Trigram, three classes: 91,232 entries, about 4 MB in a plain 16-byte-slot hash table, under 1 MB packed |
| Lexicon and exception tables | At most 4 MB | 200,000 words as 64-bit hashes: 1.6 MB |
| Whole package (model, tables, calibration package D5, manifests) | At most 10 MB | Not yet assembled |
| Resident memory of the engine | At most 30 MB | Not yet measured |
| Start-up (load and warm-up) | At most 100 ms | Not yet measured |

### 12.6 Requirements

| ID | Requirement |
| --- | --- |
| DP-1 | The network MUST be exported as ONNX (opset 17 or higher) with dynamic batch and sequence axes, and a parity test MUST show a maximum absolute logit difference of at most 1e-3 between PyTorch FP32 and the deployed file on at least 100,000 key sequences. |
| DP-2 | FP32 is the default. Static INT8 MAY be shipped only after the measurements of 12.4 on all reference devices, a refit of temperature and thresholds, a type-accuracy loss of at most 0.3 points, and a re-measured EV-1 operating point that still passes. |
| DP-3 | Weights below 8 bits MUST NOT be shipped unless a written measurement on a reference device shows at least 20% lower latency or at least 20% lower memory than the best 8-bit or FP32 variant. |
| DP-4 | Latency, memory and size MUST be measured by the protocol of 12.4 on all three reference devices and MUST meet section 7.5 at the stated percentiles before release. |
| DP-5 | Lexicon and n-gram hash tables MUST use keys of at least 64 bits. |
| DP-6 | No memory allocation and no model loading MAY occur on the typing path; the engine loads at start-up and runs on one worker thread (RT-8). |
| DP-7 | The package MUST be signed and versioned, MUST carry the hash of the calibration package (D5), and MUST support one-step rollback (section 14.5). |
| DP-8 | A model or table that fails to load MUST lead to no action (section 13.5). |

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
   - **M1, range replace** (the only method of mode AUTO): one operation through the text interface that the application cannot interleave with user keys, then the caret and selection are restored. The range is addressed by the offsets read in step 3. If the application changes the text before the range between that read and the write (an autocomplete or a collaborative edit), the write lands at stale offsets: step 5 detects it, the rollback writes at the same stale offsets, and the outcome is UNRECOVERED with a quarantine, never a silent VERIFIED. This window is short but not zero, and RT-4 measures it per application, as it does for M2. A caret move or a key that types nothing (an arrow key) between the write and the read-back also fails step 5 and costs a quarantine; that is the conservative choice (attacks B1 and B2 of the audit report L9). M1 itself needs the capability `REPLACE_RANGE` (13.7).
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

## 14. Additional parameters to account for

The seven questions in the brief cover the model; the parameters below decide whether it works in a real product. Each one has a specified default, and each is tested or measured, not assumed.

### 14.1 Layouts and keys

| Parameter | Specified default | Why it matters and how it is verified |
| --- | --- | --- |
| Layout variants | Tables generated per OS and variant: Windows "Russian"; macOS "Russian - PC" only (the macOS layout "Russian" is not supported in the first release); Linux (deferred, section 13.7) XKB `ru`; US QWERTY. ISO keyboards add one key | Punctuation placement differs between variants (section 5.4). A round-trip test per variant, and a golden test of the seven punctuation keys that carry Russian letters. A variant is identified by its fingerprint, not by its name (13.7, RT-15); a variant that matches no table is detected and the tool is OFF for it |
| Latin layouts other than US QWERTY | Out of scope. Detected and the tool is disabled for that layout pair | Dvorak, Colemak, AZERTY and QWERTZ change the physical position of Latin letters, so key tokens trained on QWERTY positions would be wrong. Supporting them needs a per-pair canonical key table and its own training run |
| Cyrillic layouts other than ЙЦУКЕН | Out of scope (phonetic Russian, Ukrainian, Belarusian). Detected and disabled | Not a key-for-key permutation of QWERTY. The layout abstraction allows adding a pair later |
| Caps Lock and Shift | Store both raw; the token bit is raw Shift XOR (Caps Lock AND key in the 33-key set L), and the case of rendered text is applied per target layout (sections 5.1 and 20.2) | On the Russian layout Caps Lock capitalises `ж э х ъ б ю`; on the English layout it does not capitalise `; ' [ ] , .`. Test cases for `GHBDTN`, `Ghbdtn`, `gHBDTN` |
| Dead keys, AltGr, compose | Candidate is ineligible | Not representable as one of 47 key positions |
| Layout change mid-word | Drop the word: its keys came from two layouts, so nothing is converted and nothing is replayed (sections 5.3 and 13.2) | One layout id cannot render keys typed under two layouts, so any conversion would be a guess. Traple translates at decision time; this specification does not. Verified by RT-14 |
| Active layout source | Windows: the HKL of the foreground thread on every key; macOS: the input-source cache; identified by fingerprint in both cases (13.7); never inferred | A wrong layout label inverts the action |

### 14.2 Typing behaviour

| Parameter | Specified default | Why it matters and how it is verified |
| --- | --- | --- |
| Typing bursts and key repeat | Sustained 12 keys/s with bursts above 20 keys/s; no dropped or reordered keys | A fast typist starts the next word before the replacement ends. Stress test with scripted bursts at 3 CPU load levels |
| Backspace and in-word edits | Backspace pops the last key from the buffer; a backspace on an empty buffer flushes it | Stale buffers cause replacement of the wrong text |
| Key-level typos | 5–8% of training words carry one adjacent-key substitution, deletion, duplication or transposition; the label never changes | The task is to find the language, not to repair the word. Robustness gate in section 11 |
| Early detection (inside a word) | Off by default; enabled only after section 10.5 gates pass | Mid-word replacement changes text under the user's hands |
| Retroactive run fix | Optional, default off: after one confident conversion, also convert up to 5 preceding words typed on the same layout without a switch | Short words (`да`, `вы`, `не`) cannot be decided alone but are obvious inside a run. Needs a multi-word undo; evaluate in phase 3 |
| Word length mix | Report token-weighted length shares (section 18) | Short words dominate running text; any metric that ignores them overstates quality |

### 14.3 Language and content

| Parameter | Specified default | Why it matters and how it is verified |
| --- | --- | --- |
| Code-switching | Decision per word; prior from the active layout and the previous words of the run | Russian text with English terms and the reverse is normal for the target user. Mixed-language stress set |
| Names, brands, acronyms | Lexicon plus the user's local exception list (words the user undid, 13.3) | `мтс` and `vnc` are the same keys; only context or the user's vocabulary separates them |
| Transliteration (`privet`) | Class OTHER. Typed on the English layout: KEEP (correct input). Typed on the Russian layout: converted to Latin like any Latin-script text (5.2) | The share in real typing is unknown; measure it in the realistic set and add a class only if it exceeds 0.5% of words |
| Slang and new words | Lexicon refresh every quarter; retrain at least every 6 months | Vocabulary drifts; a stale lexicon raises both error rates |
| Further language pairs (UA, BY, KZ, DE) | Out of scope; table and training data are parameters | Each pair needs its own data, thresholds and acceptance test |

### 14.4 Applications and operating systems

| Parameter | Specified default | Why it matters and how it is verified |
| --- | --- | --- |
| Input frameworks | Windows 10/11 and macOS 13+ only for the first release: a listen-only key observer plus an accessibility text adapter, not an input method (section 13.7). Linux is deferred | For the deferred Linux port, Wayland restricts global key capture; "replace the selection" is the fallback. Platform table in section 13.7 |
| App classes | Browsers, Electron apps, Office suites, chat clients, notes. Terminals, IDEs, remote desktops, games excluded | Replacement APIs differ per app. Test matrix of at least 15 applications per OS |
| Screen readers | No change announced twice; test with VoiceOver and NVDA | A silent text replacement can be invisible or noisy for assistive technology |
| Session events | Sleep, wake, lock screen, fast user switching, UAC or secure desktop flush the buffer | Stale buffers survive these events otherwise |
| Power and CPU | At most 0.5% of one core during typing at 5 words/s on the reference laptop | Battery and fan noise are user-visible |

### 14.5 Adaptation, operations and law

| Parameter | Specified default | Why it matters and how it is verified |
| --- | --- | --- |
| Per-user adaptation | The local exception list and the cool-down (13.3). The bounded threshold shift of 10.6 is deferred and off in the first release; no on-device training of weights | Personalisation without the risk of a drifting classifier |
| Field quality signal | Opt-in counters: corrections, undos, manual conversions by length and direction. Target undo rate ≤ 0.5% of corrections | An undo is a proxy for a false positive. It under-counts, because not every user notices or undoes |
| Model and lexicon updates | Signed, versioned packages; one-step rollback; staged rollout | A bad model is a visible regression in text the user wrote |
| Visual feedback | Optional non-blocking hint when the tool abstains; never changes text | Gives users a path to manual conversion without risk |
| Data and model licences | Licence register per source; legal review of share-alike sources before release | Unknown or restrictive licences (for example the dataset excluded in section 8.2) block release |
| Personal data law | Opt-in consent, anonymisation and deletion for any collected typing data | Keystroke data is sensitive personal data in most jurisdictions |

## 15. Deliverables, reproducibility and test plan

A model without its data manifest, calibration tables and test evidence cannot be released or audited, so the deliverables below are part of the acceptance, not extras.

### 15.1 Deliverables

| Id | Deliverable | Format | Accepted when |
| --- | --- | --- | --- |
| D1 | Layout tables for every supported OS and variant, generated from the OS, with the round-trip test | Versioned JSON plus test code | 0 round-trip failures over all 94 key states per variant; golden test of the seven letter-keys passes (section 14.1) |
| D2 | Data pipeline and manifest | Code, config and a manifest (source, licence, hash, filters, split ids) | A clean checkout rebuilds the identical manifest from a seed (DT rules, section 8.7) |
| D3 | Statistical baseline: lexicon, acronym list and n-gram tables | Binary tables with a build script | Meets the baseline row of the evaluation report; its size and latency are reported (section 7.5) |
| D4 | Trained network | PyTorch checkpoint, ONNX FP32 file, and an INT8 file only if section 12 requires it | Passes EV-1 to EV-15 or loses to D3 under EV-12 |
| D5 | Calibration package | One JSON of the strict schema LFC1 (20.5): a scalar temperature per scorer kind, the integer class counts pi\_train\_counts with the pi\_train derived from them, o\_lat, w per word state (the value w\_ship of 10.2), the threshold table in nats for both scorer kinds, both directions and all length buckets, the two-key allow-lists, the model hash; no other field | Fitted on validation only (CA-1 to CA-6); refused whole by the load check of CA-9 on any defect; hash stored with D4 |
| D6 | Evaluation report | Generated document with every slice of section 11.4, confidence intervals and the seed spread | Produced by one command; contains the manifest hashes of the data it ran on, the latency of phases P1 to P7 (7.5) per device, application and method, the support matrix with the status of every application (13.8), the interval of w with the stored w\_ship and the sensitivity report (10.2), and the evidence level of each requirement (16.1) |
| D7 | Benchmark harness | C or C++ micro-benchmarks and an ONNX Runtime script | Reports p50, p95, p99 per stage on each reference device (section 7.5) |
| D8 | Runtime library | Hook, buffer, guards, replacer, undo (section 13) | RT-1 to RT-18 pass, including the end-to-end suite |
| D9 | Model card | Two pages | Intended use, data sources and licences, known failures (acronyms, names, short words), π assumptions, limits of the proxy numbers |
| D10 | Release package | Signed, versioned bundle of D3, D4, D5 and the lexicon, with a rollback path | Staged rollout and one-step rollback demonstrated (section 14.5) |

### 15.2 Reproducibility

- **Determinism.** Every random choice (data sampling, augmentation, initialisation, shuffling) MUST be driven by one seed recorded in the run record. GPU or MPS kernels that are not deterministic MUST be listed in the report, and the headline numbers MUST come from at least three seeds (EV-13).
- **Environment.** Python and package versions MUST be pinned in a lock file; the ONNX opset, the ONNX Runtime version and the C compiler flags used for benchmarks are part of the run record.
- **Run record.** Each training run writes one file: git commit, data manifest hash, hyperparameters, seed, wall-clock time, device, checkpoint hash, validation metrics, and the calibration package hash.
- **Re-run tolerance.** A repeated run with the same seed on the same device MUST give the same checkpoint hash on CPU, and validation NLL within 0.002 on MPS. A different seed that moves recall at the EV-1 operating point by more than the measured seed spread (section 18.5) is treated as a defect in the recipe, not noise.
- **No hidden state.** Thresholds, priors and the temperature MUST NOT be hard-coded in code; they are read from D5.

### 15.3 Test plan

| Level | What is tested | Pass criterion |
| --- | --- | --- |
| Unit | Layout tables, key tokeniser, segmentation, candidate enumeration, case handling with Caps Lock, each guard of 13.1 | All golden cases pass; every guard has at least one positive and one negative test |
| Property | Mapper round trip on random key sequences; tokens always inside 0 to 96; punctuation peeling never loses a key; segmentation of a Russian word typed on the English layout never splits on the seven letter-keys | 1,000,000 random cases per property, 0 failures |
| Model parity | ONNX against PyTorch FP32; INT8 against FP32 if used | Maximum absolute logit difference ≤ 1e-3 for FP32; for INT8, the EV-1 operating point is re-measured and the gates still pass |
| Policy | Temperature, prior shift, threshold table | Unit tests with known logits; the table reproduces the false-positive targets on validation |
| Regression | Frozen stress sets (section 8.4) and the protected regression set | No category above 2 times the gate (EV-9); 0 corrections of protected content (EV-2) |
| Acceptance | Locked R-ACC (section 8.4) | EV-1 to EV-13, evaluated once per release candidate (section 11.6) |
| Performance | Latency, memory, CPU share on each reference device | Section 7.5 gates; EV-14 |
| Latency by phase | Phases P1 to P7 of 7.5 on each reference device, per application and method | p50, p95 and p99 of every phase in D6; the sum meets 7.5; EV-21 |
| Fault injection | Each phase of the replacement transaction (13.2) against the simulated field of 20.14: loss of focus, gate change, application autocorrect, partial write, timeout, read-back mismatch, a user key between read and write, hook loss, revoked permission; single and double faults | The expected outcome and mode of every case (20.13); the invariants of 20.13 hold in 1,000,000 random event sequences; each case that a real application can produce also has an end-to-end test (RT-4, RT-16) |
| Platform spikes | S-1 to S-7 of 13.7 on the real operating systems | One filed report per spike with measurements; a hypothesis of 13.7 changes only by a recorded decision |
| Independent implementation | The tables, prose and vectors of this document implemented again, by someone who has not read the code of section 20 | Every normative vector reproduced (all of them, not a share); each difference is a defect of the text |
| End to end | At least 15 applications per OS, scripted bursts at three CPU load levels, undo and cool-down, secure fields | RT-1 to RT-18; in every AUTO application 0 UNRECOVERED outcomes and 0 silent divergences in 100,000 replacements (RT-4, EV-15); 0 lost or duplicated key events in 1,000,000 (RT-16) |
| Soak | 24 hours of simulated typing | Memory flat within 2%; no watchdog trips; no leaked key content in memory dumps after a word boundary |
| Privacy | Search logs, crash dumps and the file system after a scripted session | 0 occurrences of typed content (RT-6) |

### 15.4 Requirements

| Id | Requirement |
| --- | --- |
| EV-16 | Every figure in the evaluation report MUST be reproducible from the run record by one command. |
| EV-17 | The continuous-integration gate on every change MUST run the unit, property, parity and regression levels. Acceptance and end-to-end levels run per release candidate. |
| EV-18 | The release MUST NOT ship if the model card lacks the π assumption, the known failure list or the data licences. |
| EV-19 | A bug found in the field MUST be turned into a regression test before the fix is released. |
| EV-20 | Every statement of readiness in a report or an audit MUST name its evidence level (TEXT\_FIXED, REFERENCE\_VERIFIED, INTEGRATION\_VERIFIED or RELEASE\_GATE\_PASSED, 16.1). A level is never inferred from a lower one, and a proxy result is never reported as acceptance (11.7). |
| EV-21 | The latency of phases P1 to P7 (7.5) MUST be measured and reported separately per device, application and method, and an optimisation of the network MUST be preceded by that report. |

## 16. Work plan, risks and open questions

The plan is ordered so that the cheapest evidence arrives first: a statistical baseline and the evaluation harness exist before any large network is trained, and the neural model has to earn its place (EV-12). Durations are planning estimates for one engineer plus a part-time reviewer and one data-collection coordinator; they are not measurements.

### 16.1 Phases and go/no-go gates

| Phase | Weeks | Work | Gate to leave the phase |
| --- | --- | --- | --- |
| 1. Foundations | 1–2 | Layout tables from the OS (D1); key tokeniser and segmentation; data pipeline and manifest (D2); evaluation harness with all slices of section 11.4; synthetic test sets; start recruiting users for the realistic set (section 8.5); platform spikes S-1, S-2, S-3 and S-6 of 13.7 (how keys are observed and which layout is active) | G1: round-trip tests pass; harness reproduces a known toy result; legal register has a licence entry for every source in use; each of the spikes S-1, S-2, S-3 and S-6 has a filed report, and every mechanism choice of 13.7 that a spike can change is confirmed or replaced by a recorded decision |
| 2. Baseline and first network | 3–4 | Lexicon plus n-gram baseline (D3); key-token CNN trained and calibrated (D4, D5); EV-12 comparison on the synthetic and the first real data; final values of EV-4 and EV-5 fixed from the baseline run | G2-proxy, a proxy gate: on the synthetic sets and on R-CAL (never on R-ACC) the baseline reaches its false-positive target at its operating point, and the neural model is kept or dropped by a provisional EV-12 comparison on the same data. G2-proxy does not pass EV-1 or EV-12: those two are decided only at G4 on the frozen R-ACC; the latency tiers of section 7.5 are measured on both reference devices, phase by phase (P1 to P7) |
| 3. Runtime and safety | 5–7 | Hook, buffer, guards, replacer, undo (D8); end-to-end suite on 15 applications per OS; early detection and the retroactive run fix evaluated as options (sections 10.5 and 14.2) | G3: RT-1 to RT-18 pass; in every application with status AUTO, 0 UNRECOVERED outcomes and 0 silent divergences in 100,000 replacements (RT-4); 0 lost or duplicated key events in 1,000,000 (RT-16); secure-field tests pass; spikes S-4, S-5 and S-7 have a filed report |
| 4. Opt-in dogfooding | 8–11 | At least 20 users, at least two weeks; R-CAL and R-ACC collected from disjoint users, R-ACC locked (section 8.4); π and run lengths measured (section 11.5); priors and thresholds re-fitted on R-CAL only; hard-negative mining on training sources only | G4: EV-1 to EV-13 pass once on the locked R-ACC (section 11.3); EV-1 and EV-12 are decided here and nowhere earlier; undo rate ≤ 0.5% (EV-11) |
| 5. Release | 12–13 | Signing and notarisation; model card (D9); staged rollout and rollback demonstrated (D10); legal review of share-alike sources | G5: all gates green; one-step rollback tested; EV-18 satisfied |

A failed gate has a defined response. G2-proxy failing its target on the baseline means the data, not the model, is the next lever. G4 failing means the thresholds are raised and recall is reported honestly; the product ships in manual-convert plus suggestion mode until EV-1 is met. A pass at G2-proxy means only that the design is worth continuing. The statement "EV-1 passed" is valid for one event, the G4 evaluation recorded in the R-ACC log (8.4).

**Evidence levels.** A statement that a requirement is met always names one of four levels. `TEXT_FIXED`: the rule is stated in this document. `REFERENCE_VERIFIED`: the reference code of section 20, its vectors and conformance tests check it, reproducibly. `INTEGRATION_VERIFIED`: an adapter was tested on the target operating system and application. `RELEASE_GATE_PASSED`: the acceptance requirement was met on real data and on the reference devices. The reference code can show that its algorithm loses no event it is given; it cannot show that a real hook delivers every physical key, which is `INTEGRATION_VERIFIED` through RT-16. A higher level is never inferred from a lower one, and a described test is not an executed test.

### 16.2 Risks

| Id | Risk | Likelihood | Effect | Mitigation and trigger |
| --- | --- | --- | --- | --- |
| R1 | The real wrong-layout rate π is far from the 0.3–3% design range | Medium | Precision at fixed thresholds changes by up to 10 times | Measure π in phase 4 (section 11.5); priors are data, not code (CA-2). Trigger: π outside the range → re-fit the threshold table |
| R2 | Short words and acronyms are inherently ambiguous, so recall at a strict false-positive rate is limited | High (measured, section 18) | Missed corrections for 2–4 key words and for Russian acronyms typed on the English layout | Accept it: the manual hotkey and the run-based rule cover them; do not lower thresholds to chase recall |
| R3 | No realistic data in time | Medium | EV-1 cannot be proven | Start recruiting in phase 1; ship in suggestion mode if the set is late |
| R4 | The network does not beat the statistical baseline | Medium | Wasted training effort only | EV-12 chooses the baseline; the runtime already has it as the fall-back (section 13.5) |
| R5 | A replacement leaves the field wrong (partial text, lost or duplicated characters, text changed by the application) | High | Severity-1 defects | AUTO only with M1 and a verified rollback, M2 only on the hotkey (13.7); read-back, the outcomes VERIFIED, RESTORED and UNRECOVERED, and quarantine (13.2); application blacklist; the end-to-end matrix is a gate (RT-4) |
| R6 | OS permissions and security software block the keystroke observer | Medium | Product unusable for a share of users | Signing, notarisation and a clear permission flow in the release checklist (section 13.4) |
| R7 | Licences of training sources block release | Medium | Data must be replaced | Licence register from phase 1; unknown licence = research only (section 8.7) |
| R8 | Latency target of the requester (100 ns) is taken as a requirement for the neural stage | Medium | Redesign pressure on a sound model | Section 7.5 explains what is and is not reachable; the table-look-up tier meets it, the network does not |
| R9 | Vocabulary drift (slang, new brands) | Certain | False-positive and miss rates rise over time | Quarterly lexicon refresh, retrain at least every 6 months (section 14.3) |
| R10 | Proxy-data numbers are mistaken for product numbers | Medium | Over-optimistic decisions | Every number from section 18 is labelled as proxy; the realistic set decides acceptance |
| R11 | A Windows layout of the same language but another key table is taken for a supported one | Medium | Wrong conversions for users of a variant layout | The layout is identified by the fingerprint of its 94 key states, never by language id or name; no match is OFF for the pair (13.7, 13.5 row 7); spike S-2; RT-15 |
| R12 | The key observer is removed or disabled without notice (Windows hook timeout, macOS tap disabled) | Medium | The engine works on a stream with missing keys and may convert a partial word | An independent observer on Windows, handling of the disable events and a heartbeat on macOS; a gap discards the word and lowers the mode (13.7, 13.5 row 13); spikes S-1 and S-3; RT-16 |
| R13 | Few Windows applications offer a range replacement with a verified rollback | High | Automatic correction on Windows is available in few applications at first | Say so in D6; the other applications are MANUAL (13.8); spike S-4; a Text Services Framework prototype is a separate experiment (section 17), not a dependency of this release |
| R14 | The integrity guarantee is read as unconditional | Medium | Loss of trust after an UNRECOVERED incident | Two guarantees stated separately (13.2): G-EVENT by design, G-FIELD as a measured property with a stated exposure; UNRECOVERED is reported and quarantines the application; RT-4 per application |
| R15 | A proxy gate is read as acceptance (EV-1 on synthetic data) | Medium | A release decision on evidence that cannot carry it | G2-proxy is a proxy gate; EV-1 and EV-12 are decided only at G4 on the frozen R-ACC (16.1, 11.7); EV-20 requires the evidence level in every report |

### 16.3 Open questions for the requester

Each question has a default that the specification uses until it is answered.

| Question | Default used | What changes if the answer differs |
| --- | --- | --- |
| Which platforms ship first? | macOS (Apple Silicon and Intel) and Windows 10/11 | Reference devices, replacement methods, test matrix |
| Is RU→EN as important as EN→RU? | Equal weight, separate thresholds | The measured recall of RU→EN is lower (section 18); a different weight changes the operating point |
| How many visible false corrections per user per month are acceptable? | About one per 20,000 words, about one every two days for a heavy typist writing 10,000 words a day (EV-1) | The false-positive gate and therefore recall |
| Is mid-word (early) detection wanted? | No, off by default | Prefix training and a separate gate (section 10.5) |
| Which applications must work? | Browsers, Electron apps, Office suites, chat, notes | The end-to-end matrix |
| Can typing data be collected with consent? | Yes, 20 or more users | Without it EV-1 cannot be proven and the product ships in suggestion mode |
| Is an own keyboard (iOS, Android) planned? | No, separate track | Key events come from the keyboard itself; the same model can be reused (section 4.2) |
| Is the 500M model to be kept for anything? | No | It stays out of the typing path; it could label data offline, with every label reviewed |

## 17. Review of the three source specifications

The three drafts agree on the core decision (classify, never generate) and disagree on most numbers; this section records what each one got right, where each one is wrong or unsafe, and what this document uses instead. Naming: the **first draft** is `attachment.txt`; the **second draft** is `TZ_layout_correction_v2.md`; the **third draft** is the `.docx`, which calls itself "Version 2.0" in its own header and is therefore easy to confuse with the second.

### 17.1 Decision by decision

| Topic | First draft | Second draft | Third draft | This specification and why |
| --- | --- | --- | --- | --- |
| Model family | Ensemble of multi-scale CNN and 4-layer Transformer | Statistical stage first, small CNN as arbiter, 4×256 Transformer kept only for comparison | Baseline first, then tiny CNN; GRU and 1–2 layer Transformer as experiments | Key-token CNN behind a statistical stage, with a kill criterion (EV-12). Reasons: §7, §18 |
| Size | 1–5M parameters | 0.1–0.3M | 50–300K, hard cap 500K | See §7.3 |
| Output | "9 classes", only 5 listed | 5 classes (en, ru, en\_from\_ru, ru\_from\_en, neutral) | 4 actions (KEEP, CONVERT\_TO\_RU, CONVERT\_TO\_EN, ABSTAIN) | 3 classes by intended language; the action is derived from the active layout and a threshold (§5.2) |
| Input | 20 characters | 20 characters with boundary markers | Target token ≤ 64 characters plus up to 64 characters of left context | Key tokens of one word candidate (§5.1); context enters as a prior (§10.2), left context is an ablation |
| Word boundary | Not defined | Punctuation and symbol categories split words | Last token; boundary events | Key-level segmentation that never splits on the seven letter-keys (§5.3) |
| Datasets | Lists `anzorq/kbd_lat-835k_ru-3M` as 835K English plus 3M Russian sentences | Correctly identifies it as Kabardian and excludes it | Notes "license unknown"; allows it as a research candidate | Excluded (§8.2) |
| Regularisation | Label smoothing 0.1, mixup | Smoothing 0.05–0.1 with temperature scaling; mixup optional | No smoothing, no mixup | No mixup; smoothing tested (§9); temperature scaling mandatory (CA-1) |
| Recipe | lr 2e-4, batch 128, 20 epochs | lr 1e-3, batch 512–1024, 3–10 epochs | lr 3e-4, batch 256, ≤ 15 epochs | Measured on one grid (§9, §18.5) |
| Threshold | 0.9 constant, with a length-dependent idea in §7.1 | Table by length, 0.97 down to 0.86 | 0.999 / 0.997 / 0.99 by length | Table by direction and length, fitted on validation at the deployment mixture (§10.3) |
| Latency | Pipeline < 50 ms | Statistical ≤ 50 µs, pipeline ≤ 5 ms p95 | Model p95 ≤ 1 ms, end to end p95 ≤ 50 ms | Tiered budgets, measured (§7.5) |
| Requester's 0.0001 ms | Not discussed | "Impossible" | "Not realistic" | Reachable only by table look-ups; reasons and numbers in §7.5 |
| Main metric | Accuracy ≥ 99% | Precision ≥ 99.5% | False-positive rate ≤ 0.01% | False corrections per correct word, with the count of words needed to prove it (§11) |
| Realistic test set | None (synthetic 500K) | 5–20K words | ≥ 300K synthetic negatives plus 30–50K real errors | ≥ 100K real correct words from ≥ 20 users, 20K positives per direction (§8.5) |
| Quantization | Mixed INT4/INT8 mandatory, 14–20 MB | Measure first, INT4 optional | Measure first, INT4 benchmark only | FP32 by default; static INT8 only if a gate fails; no INT4 (§12) |
| Base rate of wrong-layout words | Not considered | Not considered | Mentioned as an open question | Central design input (§5.5) |

### 17.2 Defects found and how they are handled

**First draft**

- Says nine classes and lists five. The five also mix language with action (`en` and `en_from_ru` differ only in an input the model never sees).
- INT4 for 1–5M parameters is 0.5–2.5 MB, not "\~14 MB". 14 MB corresponds to about 7M parameters in FP16 or 28M in INT4, so either the model or the number is wrong.
- Dataset misread: the card describes Kabardian in Latin script plus Russian Wikipedia lines (§8.2), not English and Russian sentences.
- Label smoothing 0.1 with a fixed 0.9 threshold: with three classes the best reachable probability is about 0.933, and the meaning of 0.9 changes with the recipe (§10.3).
- Mixup on character embeddings creates inputs that are not strings; no evidence that it helps this task is given.
- The claim that an LSTM "generalises worse on code" is unsupported. KeyboardSwitcher's own README reports its protective rules, not such a comparison.

**Second draft**

- Segments words with Unicode punctuation and symbol categories on typed text. On an English layout, seven keys (`` ` `` `[` `]` `;` `'` `,` `.`) are the letters ё х ъ ж э б ю, so this rule cuts about one Russian word in five (§5.3, measured 20.6% of frequency-weighted tokens).
- Realistic test of 5–20K words cannot show a false-positive rate better than about 1 in 1,000 (§11.3). At 40 words per minute that is a false correction every 25 minutes.
- The "5–30% Core ML speed-up" for 4-bit palettisation is not stated on the cited Apple page, which gives no numbers; the cited Apple LLM article reports a 2× decoding speed-up for a 16 GB language model, which is a different workload. Treated as unverified (§12).
- Keeps layout-conditioned classes, so the label depends on an input the model does not see.

**Third draft**

- Trains ABSTAIN as a class. There is no labelling procedure for it: a word is ambiguous only relative to a model and a threshold. It is a policy outcome here (§5.2).
- Context of up to 64 + 64 characters is carried by default. Cost grows with length and the gain is untested; here it is an ablation (§7.4).
- Does not mention the seven letter-keys, prior shift, or temperature scaling as mandatory.
- Treats the Kabardian dataset as a possible research source without noticing what it contains.
- Its ABSTAIN-versus-KEEP semantics and its guard table are good and are kept (§13.1).

### 17.3 What was kept

- **All three:** a fixed key-position table converts; the network never generates (§5, §13).
- **First draft:** a threshold that depends on length; undo (Esc only as a per-application opt-in, 13.3); learned exceptions.
- **Second draft:** statistical stage first, a written criterion for dropping the network (EV-12), temperature scaling, the idea of an `OTHER` class outside the language pair, the rule-of-three argument for test size.
- **Third draft:** baseline-first order, guard table, secure-field handling, false-positive rate as the headline, `ABSTAIN` semantics, a locked test set that is used once.

### 17.4 Source claims that were checked

| Claim in a draft | Result |
| --- | --- |
| `anzorq/kbd_lat-835k_ru-3M` holds English and Russian sentences | False. 3,835,531 rows in one `text` column: "Kbd latin script: 835k lines from a scraped pile" and "ru: 3M lines from Wiki (OPUS)"; licence "unknown" ([dataset card](https://huggingface.co/datasets/anzorq/kbd_lat-835k_ru-3M)) |
| KeyboardSwitcher is an LSTM run with ONNX Runtime | Confirmed, with 4 outputs (N/A, en, he, ru) ([README](https://github.com/kertser/KeyboardSwitcher)). Its ">99% accuracy" is the author's figure on an unspecified test set |
| Rekey reports 99.0% and 99.5% with 0.00% false positives | Confirmed as the author's claim on 54,000 words; the table does not say which figure is which ([README](https://github.com/rstqDev/rekey)) |
| Dynamic quantization suits RNN and Transformer models, static suits CNNs | Confirmed in the [ONNX Runtime documentation](https://onnxruntime.ai/docs/performance/model-optimizations/quantization.html), which also warns about slow S8S8 QOperator on x86-64 and saturation on AVX2 |
| Palettisation speed-up depends on hardware | Confirmed; the [Core ML Tools page](https://apple.github.io/coremltools/docs-guides/source/opt-overview.html) gives no numeric speed-ups and says some backends fully decompress weights and so match float16 latency |
| Neural Engine speeds up very small models | Not supported. A direct-dispatch measurement on M1 reports about 190 µs per call, 98% of it dispatch overhead, for a tiny graph ([arXiv 2606.22283](https://arxiv.org/pdf/2606.22283)); this is not a Core ML measurement and must be re-measured on the target device (§12) |
| A label-smoothing target of 0.92 for 5 classes at 0.1 | Correct: 0.9 + 0.1/5 |

## 18. Feasibility experiments

Every number marked *measured* in sections 7, 9, 10, 12 and 14 comes from the experiments below. They used public word-frequency lists in place of real typing, so they are enough to choose the model family, size, depth and training recipe, and they are not enough to accept the product (section 11).

### 18.1 Setup and limits

| Item | Setting |
| --- | --- |
| Words | `wordfreq` "large" lists: the 100,000 most frequent English words written with a–z and the 100,000 most frequent Russian words written with а–я and ё. Ranks 100,000 to 200,000 of each list form a rare-word "tail" set (names, foreign words, typos), used for testing only; its labels are noisy |
| `OTHER` class | 60,101 strings: 30,000 identifiers harvested from the Python standard library and installed packages (bare lowercase words excluded, because they cannot be told from rare words); 30,000 synthetic strings (URLs, e-mails, snake\_case, camelCase and kebab-case, version numbers, percentages, hex values, hashes, paths, file names, mixed letters and digits, key-mashing, repeated letters, transliterated Russian); 101 command names and acronyms at double weight |
| Input | Key tokens (section 5.1) of the word as typed on its own layout: English words and `OTHER` strings on the English layout, Russian words on the Russian layout. Up to 20 keys, `BOS`, and `EOS` when the word is complete |
| Split | MD5 of the string modulo 100: 80% train, 10% validation, 10% test. One word form never crosses a split; inflections of one lemma can |
| Types | Train: 79,896 EN, 80,121 RU, 48,169 `OTHER`. Validation: 10,062 / 10,109 / 5,939. Test: 10,042 / 9,770 / 5,993 |
| Training rows | 223,378 per epoch, drawn afresh every epoch: a word is repeated `clip(floor(zipf − 2), 1, 5)` times (zipf = log10 of occurrences per billion words); case variants 72% lower, 20% Capitalised, 5% UPPER, 3% random mix; 35% of rows cut to a prefix without `EOS` |
| Metrics | Type accuracy: every test word once, canonical case. Token-weighted figures: weight 10^zipf, normalised per language, with `OTHER` carrying a total weight of 0.12 of one language (about 5.7% of tokens, an assumption). Recall at a fixed false-positive rate: threshold fitted on validation, applied to test. Temperature fitted on validation |
| Training | PyTorch 2.14.1 on CPU, AdamW, cosine schedule with 3% warm-up, gradient clipping at 1.0; recipe of section 9 unless a row says otherwise |
| Hardware | 2-vCPU Intel Xeon at 2.10 GHz, one thread per measurement, ONNX Runtime 1.29.0 |
| Seeds | Seeds 0 to 2 for the reference model (3 seeds), 0 to 1 for the 32-channel model; every other row is a single run. Seed deviation of the reference model: 0.0010 in type accuracy |

**Limits that bias these numbers.**

- The split is by word form, not by lemma, so Russian inflections of one lemma sit on both sides and absolute accuracy is optimistic (section 8.4). Comparisons between models and sizes are fair; the absolute level is not.
- Word lists are not typing: there are no typos, no sentence context, no mixed-language text, and no real wrong-layout text, because none is available to download (section 8.2).
- Token-weighted recall at a fixed false-positive rate is noisy. A few very frequent short words dominate the weights, and the false-positive rate realised on the test set differed from its validation target by a factor of 0.1 to 10. Differences below about 4 points in that metric are not findings; type accuracy (seed deviation 0.001) ranks the models.
- The tail set has noisy labels (names, foreign words and typos sit in both lists), so its figures are comparative, not absolute.
- The CPU is a shared cloud virtual machine. Repeated latency runs of the same model differed by up to ±20%. The figures are proxies for the reference devices (section 12.3).

### 18.2 Ambiguity of short words

Whether a key sequence is a word in both languages is a property of the languages and not of any model, so it caps what any classifier can reach. For the top 20,000 words of one language, the table counts those whose keys, read on the other layout, spell a word of the other language's top-20,000 or top-100,000 list (token share = share of running text, weighted by word frequency).

| Keys | English words | Also a Russian word, 20k list | Also a Russian word, 100k list | Russian words | Also an English word, 20k list | Also an English word, 100k list |
| --- | --- | --- | --- | --- | --- | --- |
| 2 | 423 | 125 types (29.6%), 21.2% of tokens | 254 (60.0%), 52.9% | 241 | 125 (51.9%), 31.8% | 193 (80.1%), 91.5% |
| 3 | 981 | 10 (1.0%), 1.1% | 57 (5.8%), 1.7% | 602 | 10 (1.7%), 0.15% | 129 (21.4%), 22.0% |
| 4 | 1,870 | 5 (0.27%), 0.58% | 6 (0.32%), 0.58% | 1,258 | 5 (0.40%), 0.46% | 16 (1.3%), 0.77% |
| 5 or more | 16,700 | 0 | 0 | 17,868 | 0 | 0 |

Examples: `in` and `шт`, `at` and `фе`, `he` and `ру` at 2 keys; `her` and `рук`, `eat` and `уфе`, `tim` and `ешь` at 3; `here` and `руку`, `keys` and `луны`, `verb` and `муки` at 4. In the opposite direction `из`, `за`, `то`, `мы`, `ты`, `да` are `bp`, `pf`, `nj`, `vs`, `ns`, `lf`.

The 20k column is the realistic one for ordinary text; a 100k list contains abbreviations and names, so its 2-key row says that almost any two letters are "a word" somewhere. Three facts follow.

- **No collision at 5 keys or more** in either direction, even against a 100,000-word list. The whole hard region is 2 to 4 keys.
- **2 keys cannot be settled by any model.** 30% to 52% of the common 2-key words of one language are also common words of the other. This is why section 10.4 converts them only by allow-list.
- **3 keys collide for 1% to 2% of common words** (20k lists) and for 6% to 21% against the 100k lists. The 3-key test words of section 18.6 reach down to rank 100,000, so the 100k column applies to them: the reference CNN classifies 8.3% of English and 28.6% of Russian 3-key test words as the other language, close to the collision rates of 5.8% and 21.4%. Capacity does not repair a collision, which is why 3-key accuracy is 0.75 to 0.80 at every model size.

### 18.3 Prefix curves (early detection)

A decision inside a word has fewer keys to use. The table gives the recall at a validation-fitted threshold for the "Russian or not" score of section 10.1, for words longer than the prefix, as `recall at target 1e-3 / recall at target 1e-4`. The reference CNN (64 channels, base recipe of section 18.5) and the Witten-Bell trigram baseline are compared on the same test prefixes.

| Keys typed | EN→RU, CNN | EN→RU, trigram | RU→EN, CNN | RU→EN, trigram |
| --- | --- | --- | --- | --- |
| 3 | 0.860 / 0.724 | 0.918 / 0.361 | 0.909 / 0.744 | 0.885 / 0.701 |
| 4 | 0.967 / 0.850 | 0.990 / 0.948 | 0.959 / 0.791 | 0.980 / 0.769 |
| 5 | 0.986 / 0.932 | 0.999 / 0.929 | 0.998 / 0.970 | 0.999 / 0.975 |
| 6 | 0.997 / 0.993 | 0.9999 / 0.989 | 0.999 / 0.993 | 1.0000 / 0.994 |
| 8 | 0.9998 / 0.999 | 0.9999 / 0.9999 | 0.9998 / 0.9998 | 1.0000 / 1.0000 |

- From 6 keys on, recall at 1e-4 is at least 0.989 in both directions and for both models, so a mid-word decision at 6 keys loses almost nothing against the decision at the boundary of a longer word.
- At 4 keys recall at 1e-4 is 0.77 to 0.95 and at 5 keys 0.93 to 0.98, in both directions. This is the basis of the starting `N_min` of 4 keys (EN→RU) and 5 keys (RU→EN) in section 10.5.
- The trigram is as good as the CNN, and at 4 keys better, on short prefixes. The CNN is clearly better only at 3 keys and 1e-4 in EN→RU (0.72 against 0.36).
- The false-positive rate realised on the test set was within a factor of 3 of its target in 27 of the 40 cells, 4 to 8.5 times above it in 4 cells (all CNN; the worst is RU→EN, 5 keys, 1e-3) and below a third of it in 9 cells (3 of them zero). A threshold chosen on proxy validation data therefore cannot be carried over; EV-10 measures early mode on realistic data.

### 18.4 Learning curve

The reference CNN (64 channels, base recipe) was trained on random fractions of the training word types; validation, test and recipe were unchanged. One run per row.

| Share of training types | Training types (EN + RU + `OTHER`) | Rows per epoch | Type accuracy | NLL after temperature scaling |
| --- | --- | --- | --- | --- |
| 5% | 10,177 | 10,863 | 0.8650 | 0.367 |
| 10% | 20,698 | 22,211 | 0.9247 | 0.214 |
| 25% | 51,847 | 55,622 | 0.9462 | 0.153 |
| 50% | 104,515 | 112,186 | 0.9551 | 0.126 |
| 100% | 208,186 | 223,378 | 0.9639 (3-seed mean 0.9650) | 0.099 |

Each doubling of the data added 0.9 points at the top of the curve (0.9462 → 0.9551 → 0.9639) and the curve had not flattened. Enlarging the model from 48 to 128 channels, by contrast, added 0.1 point (section 7.3). On this task **data, not capacity, is the limit**, so the volume rule of section 8.6 applies: use every distinct word form that can be obtained, and extend the corpus while the learning curve of the real data keeps rising. Part of the gain is inflections of test lemmas entering the training set (section 18.1), so the slope is partly optimistic.

### 18.5 Training recipe and ablations

Every row trains the reference CNN (64 channels) with the base recipe (learning rate 2e-3, batch 512, 8 epochs, weight decay 0.01, dropout 0.1, no label smoothing, 35% prefix rows, cosine schedule) and changes one factor. Three seeds of the base recipe give a type accuracy of 0.9650 ± 0.0010 and a negative log-likelihood after temperature scaling of 0.0977 ± 0.0015, so a difference below 0.002 is not a finding (EV-13).

| Factor | Setting | Type accuracy | NLL after temperature | Remark |
| --- | --- | --- | --- | --- |
| Learning rate | 3e-4 | 0.9488 | 0.1505 | Under-trained |
|  | 1e-3 | 0.9597 | 0.1140 |  |
|  | 2e-3 (base) | 0.9639 | 0.0993 | Seeds 0 to 2: 0.9639, 0.9659, 0.9652 |
|  | 3e-3 | 0.9661 | 0.0918 |  |
|  | 1e-2 | 0.9686 | 0.0887 | Top of the grid; the optimum was not bracketed |
| Batch size | 128 | 0.9674 | 0.0868 | About twice the time of batch 512 |
|  | 2048 | 0.9525 | 0.1343 | Too few steps |
| Epochs | 2 | 0.9509 | 0.1409 |  |
|  | 4 | 0.9599 | 0.1153 |  |
|  | 16 | 0.9668 | 0.0890 |  |
| Weight decay | 0 | 0.9638 | 0.0995 | No effect |
|  | 0.1 | 0.9635 | 0.1004 | No effect |
| Dropout | 0 | 0.9649 | 0.0976 | No effect |
|  | 0.3 | 0.9638 | 0.1008 | No effect |
| Label smoothing | 0.05 | 0.9657 | 0.1076 | Fitted temperature 0.74 |
|  | 0.1 | 0.9637 | 0.1137 | Fitted temperature 0.61 |
| Share of prefix rows | 0 | 0.9673 | 0.0923 | Accuracy on 3-key prefixes 0.813 instead of 0.852 |
|  | 0.6 | 0.9624 | 0.1072 |  |
| Kernels and depth | 3, 3, 3 (34,403 parameters) | 0.9636 | 0.1012 |  |
|  | 5, 5 (34,339) | 0.9643 | 0.1018 |  |
|  | 3, 5, 7, 3 (71,331) | 0.9660 | 0.0927 |  |
| Draft recipes | First draft: 2e-4, batch 128, smoothing 0.1, 20 epochs | 0.9624 | 0.1183 | About 29 minutes on this CPU; fitted temperature 0.64 |
|  | Second draft: 1e-3, batch 512, 8 epochs | 0.9597 | 0.1140 | Inside the draft's ranges |
|  | Third draft: 3e-4, batch 256, 15 epochs | 0.9602 | 0.1123 |  |
| **Chosen** | **5e-3, batch 256, 12 epochs** | **0.9677 ± 0.0007** (3 seeds) | **0.0872 ± 0.0004** | About 2 to 3 minutes on this CPU |

- **Under-training is the main risk.** Learning rate 3e-4, 2 epochs and batch 2048 each cost 1.5 to 2 points. All three draft recipes sit on the slow side of the grid and lose 0.5 to 0.8 points to the chosen one.
- **Accuracy rose with the learning rate up to 1e-2** and with fewer samples per step. The chosen recipe (5e-3, batch 256, 12 epochs) is inside the grid, was confirmed with three seeds, and is within 0.1 point of the best single run (1e-2: 0.9686). Phase 2 repeats the search on real data over 3e-3, 5e-3, 1e-2 and 2e-2.
- **Weight decay, dropout, kernel layout and depth do not matter** here: every row is inside two seed deviations of the base (a fourth convolution adds 0.1 point). They are fixed at 0.01, 0.1 and 3, 5, 3 and are not tuned.
- **Label smoothing does not help.** Accuracy is unchanged (0.9657 and 0.9637), and after temperature scaling the NLL is worse (0.1076 and 0.1137 against 0.0993). The fitted temperature drops below 1 because it has to undo the smoothing. It is not used (CA-7).
- **Prefix rows trade full-word accuracy for early decisions.** The 35% share costs 0.2 to 0.3 points on complete words (0.9650 over three seeds against 0.9673 without prefixes) and buys 2 to 7 points on 2- to 5-key prefixes (accuracy 0.789, 0.852, 0.877, 0.894 at 2, 3, 4, 5 keys, against 0.715, 0.813, 0.848, 0.876). If early detection is dropped from the product, set the share to 0.
- **Better training narrows the size gap.** With the chosen recipe the 32-channel model (14,659 parameters) reaches 0.9662 (two seeds) against 0.9677 for 64 channels; with the base recipe the gap was 0.44 point (0.9595 against 0.9639). The conservative choice of 64 channels (section 7.3) therefore costs little and can be revisited on real data.

### 18.6 Architectures, size and the statistical baseline

All models use the same data and, unless noted, the base recipe. Type accuracy on the test words by number of keys (counts: 142, 975, 1,490, 5,761, 9,097 and 8,336 words); the last column is the rare-word tail set.

| Model | Parameters | All | 2 keys | 3 keys | 4 keys | 5–6 keys | 7–9 keys | 10+ keys | Tail |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Witten-Bell trigram per class | 91,232 entries | 0.9576 | 0.528 | 0.741 | 0.914 | 0.959 | 0.969 | 0.985 | 0.9671 |
| CNN, 64 channels (reference) | 42,595 | 0.9639 | 0.528 | 0.784 | 0.923 | 0.960 | 0.975 | 0.991 | 0.9799 |
| CNN, 64 channels, chosen recipe (seed 0) | 42,595 | 0.9671 | 0.606 | 0.787 | 0.931 | 0.961 | 0.978 | 0.994 | 0.9789 |
| CNN, 32 channels, chosen recipe (seed 0) | 14,659 | 0.9672 | 0.585 | 0.794 | 0.930 | 0.965 | 0.976 | 0.993 | 0.9789 |
| Bidirectional GRU, 64 units | 41,507 | 0.9636 | 0.563 | 0.782 | 0.916 | 0.960 | 0.973 | 0.992 | 0.9770 |
| Transformer, 64 dimensions, 2 layers | 75,075 | 0.9592 | 0.592 | 0.789 | 0.922 | 0.944 | 0.971 | 0.990 | 0.9759 |
| Hashed n-gram bag | 131,123 | 0.9414 | 0.500 | 0.755 | 0.919 | 0.953 | 0.964 | 0.942 | 0.9780 |
| CNN, 4 channels | 603 | 0.9132 | 0.521 | 0.754 | 0.869 | 0.899 | 0.941 | 0.926 | 0.9677 |

- From 5 keys up, every model except the 603-parameter CNN and the hashed bag is within 2 points of the others. The differences are at 3 keys (CNN 0.784 against trigram 0.741) and at 10 keys and more (0.991 against 0.985).
- The 2-key column is 142 words and is a coin flip for every model (section 18.2).
- Size, base recipe: 603 parameters 0.9132, 4,515 0.9471, 14,659 0.9595, 26,579 0.9627, 42,595 0.9639, 86,915 0.9644, 147,619 0.9640. The curve is steep to about 15,000 parameters and flat from 27,000 (section 7.3).
- The 5-to-6-key bucket of the transformer (0.944) is the only cell where a larger model is clearly worse; it was trained for 8 epochs like the others and its fitted temperature is 1.20, which marks over-confidence.

A decision is not an accuracy, so the same models were scored as the product would use them: the "Russian or not" score of section 10.1, thresholds fitted on validation at a token-weighted false-positive rate of 1e-3 or 1e-4, recall measured on test. The values are means over the seeds listed.

| Model | EN→RU, 3–4 keys, 1e-3 | EN→RU, 3–4 keys, 1e-4 | EN→RU, 5+ keys, 1e-4 | RU→EN, 3–4 keys, 1e-4 | RU→EN, 5+ keys, 1e-4 |
| --- | --- | --- | --- | --- | --- |
| CNN 64, base recipe (3 seeds) | 0.948 | 0.848 | 0.999 | 0.640 | 0.905 |
| CNN 64, chosen recipe (2 seeds) | 0.949 | 0.888 | 1.000 | 0.633 | 0.940 |
| CNN 32, base recipe | 0.911 | 0.797 | 0.998 | 0.478 | 0.859 |
| CNN 4, base recipe | 0.811 | 0.645 | 0.745 | 0.510 | 0.682 |
| BiGRU 64 | 0.941 | 0.862 | 0.999 | 0.747 | 0.922 |
| Transformer 64, 2 layers | 0.778 | 0.778 | 0.997 | 0.620 | 0.847 |
| Witten-Bell trigram | 0.963 | 0.777 | 1.000 | 0.614 | 0.893 |
| Witten-Bell 4-gram | 0.970 | 0.837 | 1.000 | 0.532 | 0.936 |

At 5 keys and more the statistical baseline is as good as the network at 1e-3 and within 0.01 to 0.05 of it at 1e-4. On the rare-word tail (types, noisy labels) the CNN keeps a lead at 1e-4 for RU→EN with 5 keys and more: 0.95 to 0.98 against 0.91 for the trigram. At 3 to 4 keys and 1e-4 the CNN is 1 to 11 points ahead of the trigram in EN→RU. Most of these gaps are inside the 4-point noise of the metric (section 18.1), and the false-positive rates realised on test differed between rows. **The proxy data therefore cannot decide EV-12.** They show that the statistical stage alone is already close to the network, which is why MD-7 requires it to work alone and EV-12 makes the network earn its place on realistic data.

### 18.7 Latency and the 100 ns question

Two kinds of measurement were made on the 2-vCPU Xeon (2.10 GHz, a shared cloud virtual machine, one thread). **Native**: a deliberately naive single-threaded FP32 forward pass in C (embedding, three convolutions of kernel 3, 5, 3, ReLU, max and mean pooling, linear head; gcc 13.3, `-O3 -march=native`; random weights; 16-dimension embedding; 20,000 timed calls per row; no SIMD intrinsics, no blocking). **ONNX Runtime** 1.29 called from Python, one intra-op thread, sequential execution, padded input of 22 positions, the trained model exported at opset 17, so the figure includes the Python call.

**Native C, one candidate.** Each cell is the range of the p50 over three runs (one run shared the machine with a training job, which is why the ranges are wide); the last column is the largest p99 seen.

| Channels | Parameters (16-dim embedding) | Multiply-adds, 9 positions | p50, 9 positions | p50, 22 positions | Largest p99, 9 positions |
| --- | --- | --- | --- | --- | --- |
| 4 | 1,365 | 0.002 M | 1.8 to 3.7 µs | not run | 5.7 µs |
| 16 | 3,921 | 0.03 M | 3.7 to 5.9 µs | 9.6 to 11.3 µs | 13.4 µs |
| 32 | 10,913 | 0.09 M | 8.5 to 12.1 µs | 22.7 to 33.4 µs | 34 µs |
| 64 | 37,185 | 0.32 M | 28.9 to 39.3 µs | 56.8 to 72.0 µs | 71 µs |
| 128 | 138,881 | 1.23 M | 105 to 114 µs | 275 to 300 µs | 364 µs |
| 192 | 306,113 | 2.74 M | 221 to 245 µs | not run | 557 µs |

Cost grows about linearly with the number of multiply-adds (c = 64 to c = 128 is 3.8 times the work and 2.9 to 3.9 times the time). It also grows with the sequence length, by 1.4 to 2.5 times from 9 to 22 positions, so a runtime that skips the padding (MD-10) gains up to a factor of 2 on typical words, which have 5 to 9 keys.

**ONNX Runtime from Python, p50, padded to 22.** Trained models unless marked.

| Model | Parameters | p50 | Remark |
| --- | --- | --- | --- |
| CNN, 4 channels | 603 | 26 µs | The floor: a 1,555-parameter model (8 channels) took 19 µs |
| CNN, 16 channels | 4,515 | 23 µs |  |
| CNN, 32 channels | 14,659 | 26 to 31 µs |  |
| CNN, 48 channels | 26,579 | 38 µs |  |
| CNN, 64 channels | 42,595 | 50 to 63 µs | Range over repeated exports of the same architecture |
| CNN, 96 channels | 86,915 | 76 µs |  |
| CNN, 128 channels | 147,619 | 103 µs |  |
| CNN, 192 channels | 318,179 | 212 µs |  |
| CNN, 256 channels | 554,275 | 446 µs | Random weights |
| Hashed n-gram bag | 131,123 | 57 µs |  |
| Bidirectional GRU, 64 units | 41,507 | 122 to 151 µs |  |
| Bidirectional GRU, 128 units | 129,059 | 219 µs | Random weights |
| Transformer, 64 dimensions, 2 layers | 75,075 | 330 µs |  |
| Transformer, 96 dimensions, 2 layers | 161,763 | 332 µs | Random weights |
| Transformer, 128 dimensions, 2 layers | 281,219 | 415 µs | Random weights |
| Transformer, 128 dimensions, 4 layers | 546,179 | 846 to 876 µs |  |
| Transformer, 256 dimensions, 4 layers (first draft's size) | 2,140,931 | 2,016 µs | Random weights; p99 2,833 µs |

**Hash-table probes.** One scoring of one candidate by the statistical stage is 54 probes (two readings, nine positions, three classes), into an open-addressing table with 16-byte slots, five probes in six hitting an existing entry and one in six missing.

| Entries | Table size | 54 probes, p50 (p95, p99) | Per probe |
| --- | --- | --- | --- |
| 54,000 | 2.1 MB | 0.66 µs (0.82, 0.91) | 12 ns |
| 540,000 | 33.6 MB | 0.91 to 1.28 µs (1.19 to 1.65, 1.39 to 1.87) | 17 to 24 ns |
| 5,400,000 | 268 MB | 1.72 µs (2.09, 2.31) | 32 ns |

The trigram of section 18.6 has 91,232 entries, so it sits between the first two rows: about 1 µs per candidate.

**What this says about 100 ns (0.0001 ms).**

- A single hash probe is 12 to 32 ns. One to eight probes fit into 100 ns. A look-up of a word in a lexicon or exception list meets the requester's number.
- The statistical stage takes 0.7 to 1.7 µs per candidate (7 to 17 times over) because it makes 54 probes; the number can be cut by scoring one reading first, but not by 10 times without changing what the stage computes.
- The smallest network, with 603 parameters and a type accuracy of 0.913, needs 2 to 4 µs natively and 19 to 26 µs through ONNX Runtime: 20 to 260 times over. The reference network needs 29 to 39 µs natively.
- Even at the arithmetic limit the reference network cannot reach 100 ns: 0.35 million multiply-adds are 0.7 million operations, which take 7 µs at 100 billion operations per second (about one Apple performance core with perfect vectorisation).

**Limits.** The ranges show a run-to-run variation of up to ±30% on a shared virtual machine. The loops are not optimised, so a vectorised kernel may be 3 to 10 times faster; that is untested here. Nothing was measured on the requester's Apple M1 Max, because it could not be reached from the environment that ran these experiments. The protocol of section 12.4 and the benchmark of D7 exist to replace these proxies; appendix 19.4 gives the source and the commands for the M1 Max.

### 18.8 Which score decides on a Russian layout

The action rule of section 5.2 is asymmetric on purpose, and the experiment below is why. On a Russian layout there are two ways to score "the user meant Latin text":

- **V1, the symmetric reading.** The English class against the rest, `log p'(EN) − log(p'(RU) + p'(OTHER))`. Converting a string that the network calls `OTHER` counts as a false positive.
- **V2, "Russian or not" (the specification).** `log(p'(EN) + p'(OTHER)) − log p'(RU)`. A string that the network calls `EN` or `OTHER` is converted; the only false positives are Russian words scored as not Russian.

Both were scored on the same checkpoints (single seeds, base recipe, 5 or more keys), with the threshold fitted on validation at a token-weighted false-positive rate of 1e-4 and recall measured on the test words (English words are the positives; Russian words the negatives, and under V1 also the `OTHER` strings at weight 0.15).

| Model | V1 recall | V1 realised false-positive rate | V2 recall | V2 realised false-positive rate |
| --- | --- | --- | --- | --- |
| Witten-Bell trigram | 0.006 | 1.1e-4 | 0.864 | 0 |
| CNN, 16 channels | 0.094 | 4e-5 | 0.797 | 0 |
| CNN, 32 channels | 0.223 | 1.2e-4 | 0.825 | 0 |
| CNN, 64 channels | 0.359 | 1.1e-4 | 0.815 | 0 |
| CNN, 128 channels | 0.552 | 7e-5 | 0.885 | 0 |

On the rare-word tail (ranks 100,000 to 200,000; 86,839 English and 94,648 Russian word types; type-level rates), at the 1e-4 target:

| Model | V1 recall at false-positive rate | V2 recall at false-positive rate | Ratio |
| --- | --- | --- | --- |
| CNN, 32 channels | 0.175 at 3e-5 | 0.903 at 6e-5 | 5.2 |
| CNN, 64 channels | 0.301 at 3e-5 | 0.910 at 4e-5 | 3.0 |
| CNN, 128 channels | 0.450 at 3e-5 | 0.934 at 3e-5 | 2.1 |

- V2 recovers two to five times more of the wrong-layout English words at the same false-positive rate, and it makes the statistical stage as good as the network on this direction. Under V1 the trigram, a generative model of the three classes, cannot separate English words from technical strings at all (recall 0.006): the two classes are made of the same letters.
- The reason is the action, not the model. An English word and a Latin technical string typed on a Russian layout convert to the same output, so deciding between them is wasted effort and a source of misses. At the V2 thresholds 94% to 97% (99% or more at the 1e-3 thresholds) of the `OTHER` strings of 5 or more keys are converted, which is the intended behaviour: nobody means Cyrillic gibberish.
- **What V2 risks, and what the experiment cannot show.** The false positives of V2 are Russian-intended strings that the network does not recognise as Russian: acronyms, abbreviations, numbers with units, Cyrillic file names, rare names. The negatives of this experiment are dictionary words only, so the measured false-positive rate of V2 is optimistic for those strings. Section 5.2 therefore requires them in the protected regression set (EV-2), and the guards of section 13.1 apply on both readings.
- Realised false-positive rates differed from their 1e-4 targets by a factor of 0 to 10 in single cells (section 18.1), so the ratios above are indications, not estimates. The direction of the result was the same for every model and every size, and for both the test words and the tail.

### 18.9 The EV-1 rule under clustered errors (simulation L6)

**Question.** EV-1 (11.3, 20.9) accepts a system when the point estimate of the false-positive rate is at most 4.8e-5 and the 95% upper bound, computed over error clusters, is at most 1e-4. Errors are not independent: a few users and a few documents produce most of them. Does the rule still refuse a system whose true rate is twice the limit when the errors cluster, and does it still accept a good system with the planned data size?

**Method.** The test is a simulation with synthetic errors; it uses no real text and says nothing about the network. The criteria, the scenarios and the number of runs were written down before the first run (`spec/FIX_AND_AUDIT_PLAN_v3.1.md`, section L6) and the script `audit/L6_ev1_simulation.py` was changed once after a result was seen, and only in its generator of the weights: the first version clipped the documents at 2% and then renormalised by the sum, which could push documents above 2% and users above 10% again (an external review found this), so that generator was replaced and every run was repeated; the results of the first version were discarded, and the criteria and the scenarios were not touched. The script imports `ev1_pass` of 20.9, so the rule under test is the reference rule and not a copy. Each scenario has 10,000 runs, the run *i* uses the generator `numpy.random.default_rng(1000 + i)`, and the number of correct words is n = 100,000. Per user there are D = ceil(120 / U) documents, so there are at least 100 documents. The number of words per user and per document is log-normal (sigma 0.7 and 0.5) with the caps of 8.5 (one user at most 10% of the words, one document at most 2%), enforced by clipping and then adding the missing mass only to documents that still have room, repeated until the total is 1; every run checks the caps again on the integer word counts (over all 360,000 runs the largest user share is 10.000% and the largest document share 2.000%, with no violation). The errors of a document are Poisson with the mean r · words · f\_user · f\_doc, where the factors f are gamma distributed with mean 1: *none* means f = 1; *moderate* means a dispersion of 2 (variance = mean + 2 · mean²) at both levels; *strong* means a dispersion of 10 at the document level and ceil(2% of U) heavy users who produce half of the expected errors. The true rate r is 2e-4, 1e-4, 5e-5 or 2e-5, and the number of users U is 20, 50 or 200.

**Criteria, fixed in advance.** *False acceptance:* at r = 2e-4 the share of accepted runs is at most 5% and its Clopper-Pearson 95% upper bound at most 7%, for every U and every kind of clustering. *Power:* at r = 2e-5, moderate clustering, U of 50 or more and n = 100,000, the share of accepted runs is at least 80%; if it were not, the smallest n of the grid that reaches 80% would be reported, and the rule would stay as it is. The rates 1e-4 and 5e-5 are diagnostic: their shares are published and there is no criterion, because the point estimate edge of the rule is 4.8e-5 and a system that sits on it is accepted about half of the time by construction.

| True rate | Users | none | moderate | strong |
| --- | --- | --- | --- | --- |
| 2e-4 | 20 | 0.0% | 1.0% | 2.1% |
| 2e-4 | 50 | 0.0% | 0.2% | 3.3% |
| 2e-4 | 200 | 0.0% | 0.1% | 2.3% |
| 1e-4 | 20 | 3.0% | 10.3% | 15.1% |
| 1e-4 | 50 | 2.9% | 7.7% | 18.9% |
| 1e-4 | 200 | 2.8% | 4.9% | 17.8% |
| 5e-5 | 20 | 42.9% | 42.8% | 43.8% |
| 5e-5 | 50 | 43.6% | 41.0% | 48.8% |
| 5e-5 | 200 | 43.0% | 40.3% | 48.9% |
| 2e-5 | 20 | 93.6% | 86.3% | 79.6% |
| 2e-5 | 50 | 94.3% | 86.2% | 80.9% |
| 2e-5 | 200 | 94.1% | 88.4% | 80.5% |

Share of accepted runs in each scenario (10,000 runs each).

**Result.** The false-acceptance criterion is met: at twice the limit the largest share of accepted runs is 3.3% (strong clustering, 50 users) with an upper bound of 3.64%. The power criterion is met: with moderate clustering and 50 or 200 users the share is 86.2% and 88.4%; with strong clustering it is 80.9% and 80.5%. With 20 users and strong clustering it is 79.6%, which is outside the criterion (U of 50 or more) and is the reason the minimum of 20 users in EV-1 is a minimum and not a target. A system that sits exactly at the limit of 1e-4 is accepted in 3% to 19% of the runs, depending on the clustering, and a system at 5e-5 in about 40% to 49%.

**What this does and does not show.** It shows that the rule, with the data sizes of 11.3, does not accept a system at twice the limit more than a few times in a hundred even when the errors cluster strongly, and that it accepts a system at 2e-5 in most runs. It does not show that the real errors of the real system follow any of these distributions, that the corpus R-ACC has the cluster structure assumed here, or that the network passes EV-1; those are measured only by EV-1 itself on R-ACC (16.1). If a later change makes a larger n necessary, the false-acceptance criterion is run again for the new n before the rule is used with it. The results are in `audit/L6_ev1_simulation.json`; the script is run with `python3 L6_ev1_simulation.py` (about 5 minutes).

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

```python
"""lfengine.py - reference (oracle) implementation of the deterministic parts of the layout-correction engine.

Pure Python 3.9+, standard library only. It is normative for section 20 of the specification: when this code
and prose disagree, the code and its test vectors win. The classifier is injected as a function.
Blocks between "# ==== 20.x" markers are published verbatim in the specification.
"""
# ==== 20.2 Key tables, tokens, Caps Lock, rendering ==================================================
import math
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, Tuple

EN, RU = "en", "ru"
OTHER_LAYOUT = {EN: RU, RU: EN}

# 47 physical keys, ids 0..46 in this order: number row (13), QWERTY row (13), home row (11), bottom row (10).
EN_UNSHIFT = "`1234567890-=" + "qwertyuiop[]\\" + "asdfghjkl;'" + "zxcvbnm,./"
EN_SHIFT = "~!@#$%^&*()_+" + "QWERTYUIOP{}|" + 'ASDFGHJKL:"' + "ZXCVBNM<>?"
RU_UNSHIFT = "ё1234567890-=" + "йцукенгшщзхъ\\" + "фывапролджэ" + "ячсмитьбю."
RU_SHIFT = 'Ё!"№;%:?*()_+' + "ЙЦУКЕНГШЩЗХЪ/" + "ФЫВАПРОЛДЖЭ" + "ЯЧСМИТЬБЮ,"
TABLE = {EN: (EN_UNSHIFT, EN_SHIFT), RU: (RU_UNSHIFT, RU_SHIFT)}
if not all(len(s) == 47 for pair in TABLE.values() for s in pair):   # explicit raise: asserts vanish under python -O
    raise RuntimeError("key tables must have 47 entries")

PAD, BOS, EOS, VOCAB = 0, 95, 96, 97
MAX_KEYS = 20


@dataclass(frozen=True)
class Key:
    """One printable key press: physical key id 0..46, raw Shift state, raw Caps Lock state."""
    id: int
    shift: bool = False
    caps: bool = False


def is_letter_in(layout: str, key_id: int) -> bool:
    return TABLE[layout][0][key_id].isalpha()


# L = the keys that are a letter in at least one of the two layouts (33 of 47: 26 Latin letters, plus the seven
# keys ` [ ] ; ' , . that are letters only in Russian). The model token applies Caps Lock to exactly the keys of L.
LETTER_KEYS = frozenset(k for k in range(47) if is_letter_in(EN, k) or is_letter_in(RU, k))
if len(LETTER_KEYS) != 33:
    raise RuntimeError("the letter-key set must have 33 members")


def effective_shift(k: Key, layout: str) -> bool:
    """Case of the key as rendered in `layout`: Caps Lock flips Shift only on keys that are letters there."""
    return k.shift ^ (k.caps and is_letter_in(layout, k.id))


def render_key(k: Key, layout: str) -> str:
    return TABLE[layout][1 if effective_shift(k, layout) else 0][k.id]


def render(keys: Sequence[Key], layout: str) -> str:
    return "".join(render_key(k, layout) for k in keys)


def token(k: Key) -> int:
    """Model token 1..94 = 1 + 2*id + shift_bit, with  shift_bit = raw_shift XOR (caps AND id in L),  L = LETTER_KEYS.
    The token must not depend on the layout that happened to be active, because the same physical key states are
    read as English or as Russian by the same network. Caps Lock therefore acts on every key that is a letter in
    EITHER layout. For the 26 Latin letters this equals the effective shift of both layouts. For the seven keys
    ` [ ] ; ' , . (letters only in Russian) it equals the effective shift of the Russian layout, which is the layout
    in which a wrong-layout Russian word is meant; on the English layout the rendered character is unchanged by
    Caps Lock (20.2 `render`), and only the token carries the flip. The target-dependent case of the converted text is
    produced by `render`, never by `token`."""
    s = k.shift ^ (k.caps and k.id in LETTER_KEYS)
    return 1 + 2 * k.id + int(s)


def tokens(core: Sequence[Key], complete: bool = True) -> List[int]:
    """BOS + at most 20 key tokens, + EOS only when the word is complete and was not truncated."""
    out = [BOS] + [token(k) for k in core[:MAX_KEYS]]
    if complete and len(core) <= MAX_KEYS:
        out.append(EOS)
    return out


def keys_from_text(text: str, layout: str) -> List[Key]:
    """Test helper: the key presses (Shift only, Caps Lock off) that display `text` on `layout`."""
    idx: Dict[str, Key] = {}
    for k in range(47):
        idx[TABLE[layout][0][k]] = Key(k, False)
    for k in range(47):
        idx.setdefault(TABLE[layout][1][k], Key(k, True))
    return [idx[c] for c in text]
```

### 20.3 Word candidate (segmentation of one run)

A *run* is the printable keys of the 47-key block typed since the last boundary. For the hypothesis "the user meant the other layout" the function returns the one candidate or `None`. Punctuation is judged by what the key is in the target layout, so the seven letter-keys (`ё х ъ ж э б ю`) are letters, never separators, when the target is Russian. The rules of 5.3 and the golden cases of 20.12 follow from this code.

```python
# ==== 20.3 Word candidate (segmentation of one run) ==================================================
TRAIL_PUNCT = frozenset(".,;:!?\"')]}")
LEAD_OPEN = frozenset("([{\"'")
MAX_TRAIL = 2


@dataclass(frozen=True)
class Candidate:
    lead: Tuple[Key, ...]    # peeled leading opener, 0 or 1 key
    core: Tuple[Key, ...]    # the keys that are classified
    trail: Tuple[Key, ...]   # peeled trailing punctuation, 0..2 keys


def candidate(run: Sequence[Key], target: str) -> Optional[Candidate]:
    """The unique word candidate for the hypothesis 'the user meant `target`', or None.

    Punctuation is judged by what the key IS in the target layout: the seven letter-keys are letters (never
    peeled) when the target is Russian and punctuation when it is English. One leading opener and up to two
    trailing punctuation keys are peeled; every remaining key must be a letter in the target layout.
    """
    body = tuple(run)
    lead: Tuple[Key, ...] = ()
    if body and render_key(body[0], target) in LEAD_OPEN and not is_letter_in(target, body[0].id):
        lead, body = body[:1], body[1:]
    p = 0
    while p < min(MAX_TRAIL, len(body)):
        k = body[len(body) - 1 - p]
        if render_key(k, target) in TRAIL_PUNCT and not is_letter_in(target, k.id):
            p += 1
        else:
            break
    core, trail = body[:len(body) - p], body[len(body) - p:]
    if not core or not all(is_letter_in(target, k.id) for k in core):
        return None
    return Candidate(lead, core, trail)
```

### 20.4 Shape guards

Guards veto any action, in both directions, when either reading of the run looks like a URL, an e-mail address, a dotted file or domain name, a camelCase identifier or a walk along one keyboard row. The suffix list is the starting list of the first release and is extended by D3 from the sources of 8.9.

```python
# ==== 20.4 Shape guards (no action in either direction) ===============================================
import re

DOTTED_SUFFIXES = ("com org net edu gov io ru ua by kz dev app ai co me info biz xyz tv uk de fr it es nl pl cn jp "
                   "py js ts md txt json yaml yml toml html css cpp hpp java kt go rs rb php sh sql csv xml pdf "
                   "png jpg gif svg zip tar gz log ini cfg exe dll so dylib").split()
_DOTTED = re.compile(r"^[\w-]+(\.[\w-]+)*\.(" + "|".join(DOTTED_SUFFIXES) + r")$")
_EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
ROWS = ((0, 12), (13, 25), (26, 36), (37, 46))     # first and last key id of each physical row


def keywalk(run: Sequence[Key], min_len: int = 4) -> bool:
    """True if at least `min_len` consecutive keys are neighbours on one row, all in the same direction."""
    ids = [k.id for k in run]
    for i in range(len(ids) - min_len + 1):
        w = ids[i:i + min_len]
        d = w[1] - w[0]
        if d in (1, -1) and all(w[j + 1] - w[j] == d for j in range(min_len - 1)) \
                and any(lo <= w[0] and max(w) <= hi for lo, hi in ROWS):
            return True
    return False


def shape_is_camel(core: Sequence[Key], layout: str) -> bool:
    s = render(core, layout)
    return any(s[i - 1].islower() and s[i].isupper() for i in range(1, len(s)))


def shape_guard(run: Sequence[Key], active: str, core: Sequence[Key]) -> Optional[str]:
    """Reason code of the first matching guard, else None. Texts are casefolded and read on BOTH layouts."""
    target = OTHER_LAYOUT[active]
    for text in (render(run, active).casefold(), render(run, target).casefold()):
        if "://" in text or text.startswith("www."):
            return "shape_url"
        if _EMAIL.match(text):
            return "shape_email"
        if _DOTTED.match(text):
            return "shape_dotted"
    if shape_is_camel(core, target) or shape_is_camel(core, active):
        return "shape_camel"
    if keywalk(core):
        return "shape_keywalk"
    return None
```

### 20.5 Calibration, priors, thresholds in nats, the calibration package

`score` is the whole chain of 10.1: temperature, prior-shift correction with the full vector of 10.2, then the two-way log-odds "Russian or not". Thresholds are stored and compared in nats; `check_calibration_package` is the load-time validation of CA-9 and rejects a probability stored where nats are expected. `example_cal` is the set of starting values of 10.1 to 10.3 and the fixture of every vector below; a real package is fitted (10.3), not typed. The package is stored as JSON (D5), written by `cal_to_json`, with the sets of the allow-lists as sorted lists.

```python
# ==== 20.5 Calibration, priors, thresholds in nats ====================================================
CLASSES = ("EN", "RU", "OTHER")
STATES = ("default", "after_switch", "run")
BUCKETS = ("3-4", "5-7", "8+")


def log_softmax(z: Sequence[float], temp: float = 1.0) -> List[float]:
    z = [v / temp for v in z]
    m = max(z)
    lse = m + math.log(sum(math.exp(v - m) for v in z))
    return [v - lse for v in z]


def _lse2(a: float, b: float) -> float:
    m = max(a, b)
    return m + math.log(math.exp(a - m) + math.exp(b - m))


def logit(p: float) -> float:
    """ln(p / (1 - p)). A threshold t on a probability is the threshold logit(t) on the score s, in nats."""
    return math.log(p / (1.0 - p))


def deployment_prior(active: str, w: float, o_lat: float) -> List[float]:
    """pi_dep over (EN, RU, OTHER), always summing to 1.
    w     = probability that the word is typed on the wrong layout (depends on the active layout and the state).
    o_lat = share of OTHER among words intended in Latin script."""
    if active == EN:   # EN or OTHER typed correctly, RU = a wrong-layout word
        return [(1 - w) * (1 - o_lat), w, (1 - w) * o_lat]
    return [w * (1 - o_lat), 1 - w, w * o_lat]  # RU typed correctly, EN or OTHER = a wrong-layout word


def score(logits: Sequence[float], active: str, cal: dict, w: float, kind: str = "network") -> float:
    """Posterior log-odds in nats that the intended text is NOT in the active layout's language
    ('Russian or not' in both directions): temperature, prior-shift correction, two-way marginal.
    Active EN: s = logit(p'(RU)). Active RU: s = logit(1 - p'(RU))."""
    lp = log_softmax(logits, cal["temperature"][kind])
    prior = deployment_prior(active, w, cal["o_lat"])
    lp = [a + math.log(b) - math.log(c) for a, b, c in zip(lp, prior, cal["pi_train"])]
    norm = _lse2(_lse2(lp[0], lp[1]), lp[2])
    lp = [v - norm for v in lp]
    ru, other = lp[1], _lse2(lp[0], lp[2])
    return ru - other if active == EN else other - ru


def bucket(n_keys: int) -> Optional[str]:
    if n_keys <= 1:
        return None
    if n_keys == 2:
        return "2"
    return "3-4" if n_keys <= 4 else ("5-7" if n_keys <= 7 else "8+")


KINDS = ("network", "ngram")             # the two scorers that can be selected at run time (13.5, row 3)
DIRECTIONS = ("en2ru", "ru2en")
CAL_SCHEMA = "LFC1"
CAL_KEYS = frozenset(("schema", "temperature", "pi_train", "pi_train_counts", "o_lat", "w", "lambda_nats",
                      "two_key_allow"))


class CalibrationError(ValueError):
    """A calibration package that MUST NOT be activated (CA-9). The runtime reacts with row 6 of the failure table
    of 13.5. It is an exception, not an assert: asserts disappear under `python -O`, and a validation that can be
    optimised away is not a validation."""


def _finite(x, what: str, lo: float = None, hi: float = None, lo_open: bool = False) -> float:
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x):
        raise CalibrationError(f"{what}: not a finite number: {x!r}")
    if lo is not None and (x <= lo if lo_open else x < lo):
        raise CalibrationError(f"{what}={x} below its lower bound {lo}")
    if hi is not None and x > hi:
        raise CalibrationError(f"{what}={x} above its upper bound {hi}")
    return float(x)


def _exact_keys(d, names, what: str) -> None:
    if not isinstance(d, dict):
        raise CalibrationError(f"{what}: not an object")
    missing, extra = set(names) - set(d), set(d) - set(names)
    if missing or extra:
        raise CalibrationError(f"{what}: missing {sorted(missing)} unknown {sorted(extra)}")


def check_calibration_package(cal: dict) -> None:
    """Strict, exhaustive load-time validation of a calibration package (CA-9, D5). Every table the runtime can
    read must be present and sane BEFORE the package is activated, so that no missing entry is first discovered
    while a word is being classified. The nats range of the thresholds also catches the unit mix-up: a probability
    such as 0.995 stored where nats are expected is far below 4.0 and is refused."""
    _exact_keys(cal, CAL_KEYS, "package")
    if cal["schema"] != CAL_SCHEMA:
        raise CalibrationError(f"schema {cal['schema']!r} is not {CAL_SCHEMA!r}")
    _exact_keys(cal["temperature"], KINDS, "temperature")                 # scalar T per scorer, both scorers
    for kind in KINDS:
        _finite(cal["temperature"][kind], f"temperature[{kind}]", 0.0, 20.0, lo_open=True)
    counts, pt = cal["pi_train_counts"], cal["pi_train"]                  # exact class mix of the training rows
    if not (isinstance(counts, list) and len(counts) == 3 and all(
            isinstance(n, int) and not isinstance(n, bool) and n > 0 for n in counts)):
        raise CalibrationError("pi_train_counts: exactly three positive integers (EN, RU, OTHER)")
    if not (isinstance(pt, list) and len(pt) == 3):
        raise CalibrationError("pi_train: exactly three values")
    for i, p in enumerate(pt):
        _finite(p, f"pi_train[{i}]", 0.0, 1.0, lo_open=True)
        if abs(p - counts[i] / sum(counts)) > 1e-9:
            raise CalibrationError(f"pi_train[{i}] is not pi_train_counts[{i}] / sum(counts)")
    if abs(sum(pt) - 1.0) > 1e-9:
        raise CalibrationError("pi_train does not sum to 1")
    _finite(cal["o_lat"], "o_lat", 0.0, 1.0, lo_open=True)
    if cal["o_lat"] >= 1.0:
        raise CalibrationError("o_lat must be below 1")
    _exact_keys(cal["w"], (EN, RU), "w")
    for a in (EN, RU):
        _exact_keys(cal["w"][a], STATES, f"w[{a}]")
        for st in STATES:
            _finite(cal["w"][a][st], f"w[{a}][{st}]", 0.0005, 0.5)
        if cal["w"][a]["run"] > 0.3:
            raise CalibrationError(f"w[{a}][run] above its cap 0.3")
    _exact_keys(cal["lambda_nats"], KINDS, "lambda_nats")                 # both scorers, every direction, every bucket
    for kind in KINDS:
        _exact_keys(cal["lambda_nats"][kind], DIRECTIONS, f"lambda_nats[{kind}]")
        for d in DIRECTIONS:
            _exact_keys(cal["lambda_nats"][kind][d], BUCKETS, f"lambda_nats[{kind}][{d}]")
            for b in BUCKETS:
                _finite(cal["lambda_nats"][kind][d][b], f"lambda_nats[{kind}][{d}][{b}] (nats)", 4.0, 16.0)
    _exact_keys(cal["two_key_allow"], DIRECTIONS, "two_key_allow")
    for d in DIRECTIONS:
        words = cal["two_key_allow"][d]
        if not (isinstance(words, (set, frozenset)) and words):
            raise CalibrationError(f"two_key_allow[{d}]: a non-empty set of words")
        for x in words:         # a word is compared with the case-folded rendering of exactly two keys (20.6)
            if not (isinstance(x, str) and len(x) == 2 and x == x.casefold() and not any(ch.isspace() for ch in x)):
                raise CalibrationError(f"two_key_allow[{d}]: {x!r} is not a case-folded word of two characters")


RU_ALLOW = "на не но да по из за то ты мы вы он ли ну во со до от ни же бы".split()
EN_ALLOW = "of to in is it on at as be by or an if so do go he we me my no up us".split()


def pi_from_counts(counts: Sequence[int]) -> List[float]:
    """The class mix of the training rows as exact fractions of integer row counts (EN, RU, OTHER)."""
    total = sum(counts)
    return [n / total for n in counts]


def example_cal() -> dict:
    """A package with the starting values of 10.1 to 10.3, for tests and vectors. It is an EXAMPLE: the class counts
    are round illustrative numbers, not the proxy mix. A real package is fitted (10.3), and D5 records the exact
    integer row counts of the S-TRAIN run it was fitted for."""
    thr = {d: {"3-4": logit(0.999), "5-7": logit(0.997), "8+": logit(0.995)} for d in DIRECTIONS}
    counts = [38000, 40000, 22000]
    return {
        "schema": CAL_SCHEMA,
        "temperature": {"network": 1.0, "ngram": 1.0},
        "pi_train_counts": counts,
        "pi_train": pi_from_counts(counts),
        "o_lat": 0.25,
        "w": {a: {"default": 0.01, "after_switch": 0.003, "run": 0.25} for a in (EN, RU)},
        "lambda_nats": {"network": thr, "ngram": thr},
        "two_key_allow": {"en2ru": set(RU_ALLOW), "ru2en": set(EN_ALLOW)},
    }


import json


def cal_to_json(cal: dict) -> str:
    """Serialise a calibration package (D5). Sets become sorted lists, so equal packages give equal bytes."""
    def conv(o):
        if isinstance(o, (set, frozenset)):
            return sorted(o)
        raise TypeError(type(o))
    return json.dumps(cal, ensure_ascii=False, sort_keys=True, indent=1, default=conv)


def _no_constant(name: str):
    raise CalibrationError(f"JSON constant {name} is not allowed")


def _no_duplicates(pairs):
    d = {}
    for k, v in pairs:
        if k in d:
            raise CalibrationError(f"duplicate key {k!r}")
        d[k] = v
    return d


def cal_from_json(text: str) -> dict:
    """Parse and validate a package. NaN, Infinity, duplicate keys, a wrong shape and every failed check of
    `check_calibration_package` raise CalibrationError; nothing else may escape."""
    try:
        cal = json.loads(text, parse_constant=_no_constant, object_pairs_hook=_no_duplicates)
    except json.JSONDecodeError as e:
        raise CalibrationError(f"not valid JSON: {e}") from None
    if not isinstance(cal, dict) or not isinstance(cal.get("two_key_allow"), dict):
        raise CalibrationError("package: not an object with a two_key_allow object")
    allow = {}
    for d, v in cal["two_key_allow"].items():           # a JSON array of strings; a bare string would be split into letters
        if not (isinstance(v, list) and all(isinstance(x, str) for x in v)):
            raise CalibrationError(f"two_key_allow[{d}]: must be an array of strings")
        if len(set(v)) != len(v):
            raise CalibrationError(f"two_key_allow[{d}]: duplicate words")
        allow[d] = set(v)
    cal["two_key_allow"] = allow
    check_calibration_package(cal)
    return cal
```

### 20.6 Decision for one run (the priority matrix of 10.4)

`decide` is the normative form of the priority matrix of 10.4. It takes the keys typed since the last boundary, the active layout, the calibration package and an injected scorer (a function from a token list to three logits: the network, the baseline or a stub), and returns a `Decision`. The first matching rule wins, in this order: no candidate, one key, user exception, shape guard, acronym of the active language, word of the active language, two keys, score against the threshold. Every KEEP carries a reason string; the reasons are the vocabulary of the vectors in 20.12. `margin` is the score minus the threshold, in nats, and is set only for model decisions.

```python
# ==== 20.6 Decision for one run (priority matrix) =====================================================
@dataclass
class Decision:
    action: str                          # "CONVERT" or "KEEP"
    reason: str
    replacement: Optional[str] = None    # the whole run re-rendered on the target layout
    margin: Optional[float] = None       # score - lambda (nats), model decisions only
    n_keys: Optional[int] = None


def expected_echo(run: Sequence[Key], active: str) -> str:
    """The text the application should show for `run` as typed: used by the echo check before a replacement."""
    return render(run, active)


def decide(run: Sequence[Key], active: str, cal: dict, scorer: Callable[[List[int]], Sequence[float]],
           state: str = "default", run_active: bool = False, exceptions=frozenset(),
           lexicon: Optional[dict] = None, kind: str = "network") -> Decision:
    """The normative decision for the run (the keys typed since the last boundary), taken at Space.
    `state` selects the wrong-layout probability w ('default', 'after_switch', 'run');
    `run_active` enables the 2-key rule. Rows 5 to 12 of the priority matrix of 10.4, first match wins:
      5 no candidate  6 one key  7 user exception  8 shape guard  9 acronym of the active language
      10 word of the active language  11 two keys (allow-list and run)  12 score against the threshold."""
    target = OTHER_LAYOUT[active]
    lex = lexicon or {}
    direction = f"{active}2{target}"
    cand = candidate(run, target)
    if cand is None:
        return Decision("KEEP", "no_eligible_candidate")
    n = len(cand.core)
    if bucket(n) is None:
        return Decision("KEEP", "one_key", None, None, n)
    typed = render(cand.core, active).casefold()
    converted = render(cand.core, target).casefold()
    if (direction, typed) in exceptions:
        return Decision("KEEP", "user_exception", None, None, n)
    g = shape_guard(run, active, cand.core)
    if g:
        return Decision("KEEP", g, None, None, n)
    if typed in lex.get("acr_" + active, ()):
        return Decision("KEEP", "acronym", None, None, n)
    if typed in lex.get(active, ()):
        return Decision("KEEP", "lexicon_active", None, None, n)
    text = render(cand.lead + cand.core + cand.trail, target)
    b = bucket(n)
    if b == "2":
        if run_active and converted in cal["two_key_allow"][direction]:
            return Decision("CONVERT", "two_key_allow_list", text, None, n)
        return Decision("KEEP", "two_key_rule", None, None, n)
    logits = list(scorer(tokens(cand.core, True)))
    if len(logits) != 3 or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in logits):
        return Decision("KEEP", "scorer_invalid", None, None, n)          # fail closed: never convert on NaN or Inf
    s = score(logits, active, cal, cal["w"][active][state], kind)
    margin = s - cal["lambda_nats"][kind][direction][b]
    if margin >= 0:
        return Decision("CONVERT", "score_above_threshold", text, margin, n)
    return Decision("KEEP", "abstain", None, margin, n)
```

### 20.7 Event state machine: buffer, run state, boundary

The event machine is the interface that the operating-system adapters of 13.2 drive; it contains no platform code. It consumes events in arrival order and returns a `Decision` only at a Space that ends a non-empty run. Its rules, which the traces of 20.12 pin down:

- **Gate.** Any gate verdict other than ALLOW (13.1) discards the buffer and the run state, and while it lasts every event is ignored: nothing is stored, counted or classified.
- **Run.** Keys are appended with the layout id sampled at each key. Up to 64 keys are kept; a longer word is marked `overflow` and is KEEP. A key whose layout differs from the layout of the first key drops the whole word (all later keys are ignored until the next Space) and clears the run credit (5.3).
- **Boundary.** At Space the run is taken and cleared. No decision if the word was dropped or empty. KEEP `overflow`; KEEP `layout_changed_at_boundary` if the layout at Space differs from the run's; KEEP `cooldown` while the cool-down after an undo lasts (until 3 word decisions have been suppressed and 10 s have passed); otherwise `decide`.
- **Prior state** (10.2). `run` if the run credit is above 0, else `after_switch` if a manual layout change preceded the word, else `default`.
- **Run credit** (feedback cap, 10.2). A CONVERT decided without the run prior sets the credit to 3; a CONVERT decided with it lowers the credit by 1, so a chain of run-assisted conversions cannot sustain itself. A KEEP for evidence (`user_exception`, `acronym`, `lexicon_active`, `abstain`) clears the credit. Undo clears it and starts the cool-down.
- **Other events.** `backspace` removes the last key of the run (and clears the credit if the run is empty and the word was not dropped). `layout` (a manual change; the tool never changes the layout itself) drops the current word, sets the `after_switch` flag and clears the credit. `break` (click, focus change, paste, Enter, Tab, arrows, chords, input-method activity, sleep, lock) empties the buffer and clears the credit.

```python
# ==== 20.7 Event state machine: buffer, run state, boundary ==========================================
@dataclass
class Event:
    kind: str                      # key | space | backspace | break | layout | gap
    key: Optional[Key] = None      # for kind == key
    layout: Optional[str] = None   # layout id sampled at the event (key, space)
    ts_ms: int = 0


MAX_BUF = 64
RUN_CREDIT_MAX = 3
COOLDOWN_WORDS = 3
COOLDOWN_MS = 10_000
EVIDENCE_KEEP = {"user_exception", "acronym", "lexicon_active", "abstain", "scorer_invalid"}   # KEEP reasons that end a run
GATE_ALLOW, GATE_DENY, GATE_UNKNOWN = "ALLOW", "DENY", "UNKNOWN"
OUTCOMES = ("VERIFIED", "RESTORED", "UNRECOVERED", "ABORTED")   # 20.14
UNDO_WINDOW_MS = 10_000        # 13.3: the undo snapshot lives 10 s ...
UNDO_MAX_CHARS = 100           # ... or until 100 further printable keys and Spaces, whichever comes first


@dataclass
class UndoSnapshot:
    """The only text-derived state that outlives a word boundary (13.3, 13.4): the keys of ONE converted word.
    Memory only. It is never logged, never written to a crash dump or to storage, and a native implementation
    overwrites the key array with zeros before it lets go of it."""
    keys: Tuple[Key, ...]       # the whole run as typed, with Shift and Caps Lock
    layout: str                 # the layout id recorded with the keys
    direction: str              # 'en2ru' or 'ru2en'
    typed: str                  # the case-folded core as typed: the key of the exception list
    created_ms: int
    after: int = 0              # printable keys and Spaces typed since the replacement


class Engine:
    """Consumes events in arrival order; returns a Decision at each Space that ends a non-empty run.
    The event kinds: key (a printable main-block key), space (the decision point), backspace, layout (a manual
    layout change), break (click, focus change, paste, Enter, Tab, arrows, chords, IME, sleep, lock, ...)."""

    def __init__(self, cal, scorer, lexicon=None, exceptions=frozenset(), kind="network"):
        check_calibration_package(cal)                    # fail closed at activation, never during classification
        if kind not in KINDS:
            raise CalibrationError(f"unknown scorer kind {kind!r}")
        self.cal, self.scorer, self.lexicon, self.kind = cal, scorer, lexicon or {}, kind
        self.exceptions = set(exceptions)                 # grows by one entry per undo (13.3)
        self.snapshot: Optional[UndoSnapshot] = None      # separate from the word buffer (13.4)
        self.mode = "AUTO"                                # AUTO | MANUAL_ONLY | OFF, derived by engine_mode (20.14)
        self.run: List[Key] = []
        self.run_layout: Optional[str] = None
        self.overflow = False
        self.skip = False            # the rest of the current word is ignored (layout changed inside it)
        self.gate = GATE_ALLOW       # stage 0: only ALLOW lets keys in
        self.after_switch = False    # the next full word follows a manual layout change
        self.credit = 0              # run credit 0..RUN_CREDIT_MAX; > 0 selects the 'run' prior
        self.cool_words = 0
        self.cool_until_ms = 0

    def _flush(self):
        self.run, self.run_layout, self.overflow = [], None, False

    def _drop_snapshot(self):
        self.snapshot = None

    def set_mode(self, mode: str):
        """Mode from `engine_mode` (20.14). Only AUTO records and classifies; MANUAL_ONLY and OFF record nothing (13.5).
        Any change of mode empties the buffer and destroys the snapshot and the run credit."""
        if mode not in ("AUTO", "MANUAL_ONLY", "OFF"):
            raise ValueError(mode)
        if mode != self.mode:
            self._flush()
            self.skip, self.credit, self.after_switch = False, 0, False
            self._drop_snapshot()
        self.mode = mode

    def tick(self, now_ms: int):
        """Clock input of the runtime timer: the snapshot expires 10 s after the replacement."""
        s = self.snapshot
        if s is not None and now_ms - s.created_ms > UNDO_WINDOW_MS:
            self._drop_snapshot()

    def _count_char(self):
        s = self.snapshot
        if s is not None:
            s.after += 1
            if s.after > UNDO_MAX_CHARS:
                self._drop_snapshot()

    def set_gate(self, state: str):
        """Stage 0 verdict from the runtime. Anything but ALLOW discards the buffer, the run state and the snapshot."""
        self.gate = state
        if state != GATE_ALLOW:
            self._flush()
            self.skip, self.credit, self.after_switch = False, 0, False
            self._drop_snapshot()

    def undo(self, now_ms: int) -> Optional[str]:
        """The undo chord (13.3). Returns the text to restore: the recorded keys rendered with the layout recorded
        with them, never re-derived from the converted text. None when no snapshot is alive (nothing happens).
        The word joins the exception list, the run credit is lost, the cool-down starts, the snapshot is destroyed."""
        self.tick(now_ms)
        s = self.snapshot
        if s is None:
            return None
        self.exceptions.add((s.direction, s.typed))
        self.credit = 0
        self.cool_words = COOLDOWN_WORDS
        self.cool_until_ms = now_ms + COOLDOWN_MS
        self._drop_snapshot()
        return render(s.keys, s.layout)

    def on_event(self, ev: Event) -> Optional[Decision]:
        if self.gate != GATE_ALLOW or self.mode != "AUTO":
            return None                                   # not stored, not counted, not classified
        if ev.ts_ms:
            self.tick(ev.ts_ms)
        if ev.kind in ("key", "space"):
            self._count_char()                            # characters typed after a replacement age the snapshot
        if ev.kind == "key":
            if self.skip:
                return None
            if self.run and ev.layout != self.run_layout:
                self._flush()
                self.skip, self.credit = True, 0          # a layout change inside a word drops the word
                return None
            if not self.run:
                self.run_layout = ev.layout
            if len(self.run) < MAX_BUF:
                self.run.append(ev.key)
            else:
                self.overflow = True
            return None
        if ev.kind == "backspace":
            if self.run:
                self.run.pop()
            elif not self.skip:
                self.credit = 0                           # editing text before the word start: a break
                self._drop_snapshot()
            return None
        if ev.kind == "layout":                           # manual layout change (the tool never changes it)
            if self.run:
                self._flush()
                self.skip = True
            self.after_switch = True
            self.credit = 0
            self._drop_snapshot()
            return None
        if ev.kind == "break":
            self._flush()
            self.skip, self.credit = False, 0
            self._drop_snapshot()
            return None
        if ev.kind == "gap":                              # the event stream was interrupted (13.5, hook health)
            self._flush()
            self.skip, self.credit = True, 0              # the rest of the current word is unknown: ignore it
            self._drop_snapshot()
            return None
        if ev.kind == "space":
            return self._boundary(ev)
        raise ValueError(ev.kind)

    def on_outcome(self, outcome: str):
        """Result of the replacement transaction for the last CONVERT (20.14). Only a VERIFIED replacement keeps its
        undo snapshot and the run credit it earned; any other outcome means the text is the original text."""
        if outcome not in OUTCOMES:
            raise ValueError(outcome)
        if outcome != "VERIFIED":
            self.credit = 0
            self._drop_snapshot()

    def _boundary(self, ev: Event) -> Optional[Decision]:
        run, layout, overflow, skip = self.run, self.run_layout, self.overflow, self.skip
        self._flush()
        self.skip = False
        if skip or not run:
            return None
        if overflow:
            return Decision("KEEP", "overflow")
        if layout != ev.layout:
            return Decision("KEEP", "layout_changed_at_boundary")
        if self.cool_words > 0 or ev.ts_ms < self.cool_until_ms:
            self.cool_words = max(0, self.cool_words - 1)
            return Decision("KEEP", "cooldown")
        state = "run" if self.credit > 0 else ("after_switch" if self.after_switch else "default")
        d = decide(run, layout, self.cal, self.scorer, state, self.credit > 0, self.exceptions, self.lexicon, self.kind)
        self.after_switch = False
        if d.action == "CONVERT":
            # Only a conversion decided WITHOUT the run prior refills the credit: a chain of run-assisted
            # conversions can never sustain itself (feedback cap).
            self.credit = RUN_CREDIT_MAX if state != "run" else max(self.credit - 1, 0)
            target = OTHER_LAYOUT[layout]
            core = candidate(run, target).core
            self.snapshot = UndoSnapshot(tuple(run), layout, f"{layout}2{target}", render(core, layout).casefold(),
                                         ev.ts_ms)    # one snapshot: an older one is replaced
        elif d.reason in EVIDENCE_KEEP:
            self.credit = 0
        return d
```

### 20.8 Manual conversion (hotkey)

Manual conversion (13.3) is a pure key-position mapping of the selected text: no peeling of punctuation, no model, no thresholds. The direction is decided by majority of letters: more Cyrillic letters than Latin ones means Russian to English, otherwise English to Russian; a selection with no letters at all gets no direction and is returned unchanged. Characters that are not on the source layout (emoji, accented letters, other scripts) are copied unchanged, so the length in code points never changes and the original selection can always be restored from the result.

```python
# ==== 20.8 Manual conversion (hotkey) ================================================================
def _char_map(layout: str) -> Dict[str, Tuple[int, bool]]:
    m: Dict[str, Tuple[int, bool]] = {}
    for shift in (False, True):
        for k in range(47):
            m.setdefault(TABLE[layout][int(shift)][k], (k, shift))
    return m


_CHAR_MAP = {EN: _char_map(EN), RU: _char_map(RU)}


def manual_convert(text: str) -> Tuple[Optional[str], str]:
    """Pure key-position conversion of a selection (no punctuation peeling, no model, no thresholds).
    Direction: more Cyrillic letters than Latin letters means RU->EN, otherwise EN->RU; no letters at all means
    no direction and the text is returned unchanged. Characters that are not on the source layout (emoji,
    accented letters, other scripts) are copied unchanged; the length in code points never changes."""
    cyr = sum(1 for c in text if "а" <= c.lower() <= "я" or c in "ёЁ")
    lat = sum(1 for c in text if c.isascii() and c.isalpha())
    if cyr == 0 and lat == 0:
        return None, text
    src = RU if cyr > lat else EN
    dst = OTHER_LAYOUT[src]
    out = []
    for c in text:
        hit = _CHAR_MAP[src].get(c)
        out.append(TABLE[dst][int(hit[1])][hit[0]] if hit else c)
    return f"{src}2{dst}", "".join(out)
```

### 20.9 Acceptance statistics (EV-1)

`ev1_bound` and `ev1_pass` are the executable form of the rule of 11.3. A cluster is one (user, document) pair; the bound is the exact Poisson 95% upper limit for the number of clusters, multiplied by the size of the largest cluster and divided by the number of correct words. The per-user and per-document caps on the share of words (8.5) are applied to the data before these functions are called. `poisson_upper(k, conf)` is defined for an integer `k` of at least 0 and `0 < conf < 1` and raises `ValueError` for anything else; the search interval grows until it holds the limit, so that every confidence gives the exact limit (the first version of the function used a fixed interval and returned a wrong limit silently for a confidence above 0.99995; the mutation run of audit line L3 found it). The EV-1 rule uses only `conf = 0.95`.

```python
# ==== 20.9 Acceptance statistics (EV-1) ===============================================================
def poisson_upper(k: int, conf: float = 0.95) -> float:
    """Exact one-sided upper limit mu with P(Poisson(mu) <= k) = 1 - conf, for k >= 0 and 0 < conf < 1."""
    if not (isinstance(k, int) and not isinstance(k, bool) and k >= 0 and 0.0 < conf < 1.0):
        raise ValueError("poisson_upper needs an integer k >= 0 and 0 < conf < 1")

    def cdf(mu: float) -> float:
        return sum(math.exp(-mu + i * math.log(mu) - math.lgamma(i + 1)) for i in range(k + 1))

    lo, hi = 0.0, 10.0 + 10.0 * k
    while cdf(hi) > 1 - conf:                      # the interval must hold the limit for every confidence
        lo, hi = hi, hi * 2
    for _ in range(200):
        mid = (lo + hi) / 2
        if cdf(mid) > 1 - conf:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def ev1_bound(false_corrections: Sequence[Tuple[str, str]], n_negatives: int) -> float:
    """Conservative 95% upper bound on the false-correction rate under clustering.
    `false_corrections`: one (user_id, document_id) per false correction. A cluster is a distinct pair;
    bound = poisson_upper(number of clusters) * (largest cluster size) / n_negatives."""
    if not false_corrections:
        return poisson_upper(0) / n_negatives
    sizes: Dict[Tuple[str, str], int] = {}
    for key in false_corrections:
        sizes[key] = sizes.get(key, 0) + 1
    return poisson_upper(len(sizes)) * max(sizes.values()) / n_negatives


def ev1_pass(false_corrections: Sequence[Tuple[str, str]], n_negatives: int, n_users: int, n_documents: int) -> bool:
    """EV-1: n >= 100,000 correct words, >= 20 users, >= 100 documents, point estimate <= 4.8e-5 and
    cluster bound <= 1e-4. (The caps on per-user and per-document shares are applied before counting.)"""
    return (n_negatives >= 100_000 and n_users >= 20 and n_documents >= 100
            and len(false_corrections) / n_negatives <= 4.8e-5
            and ev1_bound(false_corrections, n_negatives) <= 1e-4)
```

### 20.10 Statistical baseline (Witten-Bell over key tokens) and the table formats LFB1 and LFL1

This block is the normative form of 7.7. `WittenBell.fit` counts contexts of 0, 1 and 2 tokens over the rows of `S-TRAIN` (each row is `BOS`, key tokens, `EOS` or a prefix without `EOS`; a row may carry a multiplicity). `WittenBell.logp` returns the sum of the log-probabilities of every token after `BOS`, with no length normalisation. `baseline_logits` adds the class prior and returns three logits that enter `score` (20.5) with `kind="ngram"`.

`LFB1` stores, for each class and each order, the contexts (key, total, distinct) and the pairs (key, count) as sorted records of 64-bit FNV-1a hashes; a context hash is `FNV-1a-64(0xC0+k ‖ context bytes)` and a pair hash is `FNV-1a-64(0xD0+k ‖ context bytes ‖ next token)`. Two different contexts or pairs of one class and order could in theory share a 64-bit key, so lfb\_pack fails the build if they do. `LFL1` stores the stage-4 sets as sorted unique 64-bit keys per table tag. `lfb_logp` over a loaded file equals `WittenBell.logp` of the packed model to float rounding (MD-12).

```python
# ==== 20.10 Statistical baseline: Witten-Bell trigram over key tokens, table format LFB1 =============
class WittenBell:
    """Interpolated Witten-Bell language model of order 3 over key tokens (one instance per class)."""
    ORDER = 3

    def __init__(self, vocab: int = VOCAB, min_count: int = 1):
        self.V, self.min_count = vocab, min_count
        self.cnt = [dict() for _ in range(self.ORDER)]     # cnt[k][context tuple (len k)] -> {next: count}

    def fit(self, rows: Sequence[Sequence[int]], weights: Optional[Sequence[int]] = None):
        """rows: BOS + key tokens + EOS (tokens(core, True)); weights: multiplicity of each row."""
        for r, row in enumerate(rows):
            m = 1 if weights is None else weights[r]
            for i in range(1, len(row)):
                for k in range(self.ORDER):
                    if i - k < 0:
                        break
                    d = self.cnt[k].setdefault(tuple(row[i - k:i]), {})
                    d[row[i]] = d.get(row[i], 0) + m
        if self.min_count > 1:                              # prune BEFORE the totals are derived
            for k in range(1, self.ORDER):
                for ctx in list(self.cnt[k]):
                    d = {w: c for w, c in self.cnt[k][ctx].items() if c >= self.min_count}
                    if d:
                        self.cnt[k][ctx] = d
                    else:
                        del self.cnt[k][ctx]
        return self

    def logp(self, row: Sequence[int]) -> float:
        total = 0.0
        for i in range(1, len(row)):
            p = 1.0 / self.V                                 # order -1: uniform
            for k in range(self.ORDER):                       # orders 0, 1, 2: interpolate upwards
                if i - k < 0:
                    break
                d = self.cnt[k].get(tuple(row[i - k:i]))
                if d is None:                                 # unseen context: keep the lower-order estimate
                    break
                t, u = sum(d.values()), len(d)
                p = (d.get(row[i], 0) + u * p) / (t + u)
            total += math.log(p)
        return total


def baseline_logits(models: Sequence[WittenBell], log_prior: Sequence[float], row: Sequence[int]) -> List[float]:
    """Unnormalised class log-posteriors: log p(row | class) + log pi_train(class). They enter the same
    calibration path as network logits, with kind='ngram' (own temperature and own threshold table)."""
    return [m.logp(row) + lp for m, lp in zip(models, log_prior)]


import struct
import functools


class FormatError(ValueError):
    """A binary table file (LFB1, LFL1, LFW1) is damaged, truncated, has a wrong magic or trailing bytes. The runtime
    reacts with row 6 of the failure table (13.5) exactly as for a refused calibration package."""


def _format_guard(fn):
    """struct.error and IndexError of a truncated file become FormatError: a loader raises one exception type."""
    @functools.wraps(fn)
    def wrapper(b):
        try:
            return fn(b)
        except (struct.error, IndexError, KeyError) as e:
            raise FormatError(f"{fn.__name__}: {e}") from None
    return wrapper


FNV_OFFSET, FNV_PRIME, MASK64 = 0xCBF29CE484222325, 0x100000001B3, (1 << 64) - 1


def fnv1a64(data: bytes) -> int:
    h = FNV_OFFSET
    for b in data:
        h = ((h ^ b) * FNV_PRIME) & MASK64
    return h


def ctx_key(k: int, ctx: Sequence[int]) -> int:
    return fnv1a64(bytes([0xC0 + k]) + bytes(ctx))


def pair_key(k: int, ctx: Sequence[int], nxt: int) -> int:
    return fnv1a64(bytes([0xD0 + k]) + bytes(ctx) + bytes([nxt]))


def lfb_pack(models: Sequence[WittenBell], log_prior: Sequence[float]) -> bytes:
    """LFB1: magic, u32 order, u32 vocab, u32 nclasses, f64 log_prior[nclasses]; then for each class and each
    order k = 0..2: u32 n_ctx, n_ctx x (u64 key, u32 total, u32 distinct), u32 n_pair, n_pair x (u64 key,
    u32 count, u32 0). Records are sorted by key; little endian. Runtime hash tables are built from them."""
    out = [b"LFB1", struct.pack("<III", WittenBell.ORDER, models[0].V, len(models)),
           struct.pack("<%dd" % len(models), *log_prior)]
    for m in models:
        for k in range(WittenBell.ORDER):
            ctxs = sorted((ctx_key(k, c), sum(d.values()), len(d)) for c, d in m.cnt[k].items())
            pairs = sorted((pair_key(k, c, w), n) for c, d in m.cnt[k].items() for w, n in d.items())
            if len({r[0] for r in ctxs}) != len(ctxs) or len({a for a, _ in pairs}) != len(pairs):
                raise FormatError("hash collision: two contexts or pairs share a 64-bit key")
            out.append(struct.pack("<I", len(ctxs)) + b"".join(struct.pack("<QII", *r) for r in ctxs))
            out.append(struct.pack("<I", len(pairs)) + b"".join(struct.pack("<QII", a, n, 0) for a, n in pairs))
    return b"".join(out)


@_format_guard
def lfb_load(b: bytes) -> dict:
    if b[:4] != b"LFB1":
        raise FormatError("not an LFB1 file")
    order, vocab, ncls = struct.unpack_from("<III", b, 4)
    log_prior = list(struct.unpack_from("<%dd" % ncls, b, 16))
    off, classes = 16 + 8 * ncls, []
    for _ in range(ncls):
        per_order = []
        for _k in range(order):
            (nc,) = struct.unpack_from("<I", b, off); off += 4
            ctx = {}
            for i in range(nc):
                key, t, u = struct.unpack_from("<QII", b, off + 16 * i)
                ctx[key] = (t, u)
            off += 16 * nc
            (npair,) = struct.unpack_from("<I", b, off); off += 4
            pair = {}
            for i in range(npair):
                key, n, _z = struct.unpack_from("<QII", b, off + 16 * i)
                pair[key] = n
            off += 16 * npair
            per_order.append((ctx, pair))
        classes.append(per_order)
    if off != len(b):
        raise FormatError("trailing bytes")
    return {"order": order, "V": vocab, "log_prior": log_prior, "classes": classes}


def lfb_logp(pkg: dict, cls: int, row: Sequence[int]) -> float:
    """Same value as WittenBell.logp for the model that was packed (to float rounding)."""
    total = 0.0
    for i in range(1, len(row)):
        p = 1.0 / pkg["V"]
        for k in range(pkg["order"]):
            if i - k < 0:
                break
            ctx = row[i - k:i]
            st = pkg["classes"][cls][k][0].get(ctx_key(k, ctx))
            if st is None:
                break
            t, u = st
            c = pkg["classes"][cls][k][1].get(pair_key(k, ctx, row[i]), 0)
            p = (c + u * p) / (t + u)
        total += math.log(p)
    return total


# Lexicon tables (stage 4): sets of 64-bit hashes, file format LFL1.
LEX_TAGS = {"lex_en": 1, "lex_ru": 2, "acr_en": 3, "acr_ru": 4, "exc_en2ru": 5, "exc_ru2en": 6}


def lex_key(tag: int, text: str) -> int:
    """64-bit key of a case-folded string in table `tag`: FNV-1a over one tag byte and the UTF-8 bytes."""
    return fnv1a64(bytes([0xE0 + tag]) + text.casefold().encode("utf-8"))


def lfl_pack(tables: Dict[str, Sequence[str]]) -> bytes:
    """LFL1: magic, u32 ntables, then per table in tag order: u8 tag, u32 n, n x u64 sorted unique keys (LE)."""
    out = [b"LFL1", struct.pack("<I", len(tables))]
    for name in sorted(tables, key=lambda n: LEX_TAGS[n]):
        tag = LEX_TAGS[name]
        keys = sorted({lex_key(tag, w) for w in tables[name]})
        out.append(struct.pack("<BI", tag, len(keys)) + b"".join(struct.pack("<Q", k) for k in keys))
    return b"".join(out)


class HashedSet:
    """Membership by hash, a drop-in for the sets of words that `decide` takes (a hash match is a word match)."""

    def __init__(self, tag: int, keys):
        self.tag, self.keys = tag, frozenset(keys)

    def __contains__(self, text: str) -> bool:
        return lex_key(self.tag, text) in self.keys


@_format_guard
def lfl_load(b: bytes) -> Dict[str, HashedSet]:
    if b[:4] != b"LFL1":
        raise FormatError("not an LFL1 file")
    (nt,) = struct.unpack_from("<I", b, 4)
    off, res, by_tag = 8, {}, {v: k for k, v in LEX_TAGS.items()}
    for _ in range(nt):
        tag, n = struct.unpack_from("<BI", b, off)
        off += 5
        res[by_tag[tag]] = HashedSet(tag, struct.unpack_from("<%dQ" % n, b, off))
        off += 8 * n
    if off != len(b):
        raise FormatError("trailing bytes")
    return res
```

### 20.11 Network weight file LFW1 and the reference forward pass

`LFW1` is the portable weight file that the trainer exports next to the ONNX file of DP-1 (MD-14). The header is the magic, the channel count, the embedding width and the kernel list; the body is float32 little endian in a fixed order: the embedding table `[97][e]`, then for each convolution its weight `[ch][cin][k]` and bias `[ch]`, then the head weight `[3][2*ch]` and bias `[3]`. `lfw_forward` is deliberately slow and simple (same-padding convolutions, ReLU, max and mean pooling over every position, `BOS` and `EOS` included, true length without padding); it exists to check a native implementation, which MUST agree with it on the toy weights of `toy_weights` to 1e-5 and on the exported weights of the trained network to 1e-4 per logit (MD-14). `toy_weights` uses integer arithmetic only, so every language reproduces the same file byte for byte.

```python
# ==== 20.11 Network weight file LFW1 and reference forward pass ======================================
LFW_MAGIC = b"LFW1"


def lfw_pack(ch: int, emb_dim: int, kernels: Sequence[int], floats: Sequence[float]) -> bytes:
    """Header: magic, u32 ch, u32 emb_dim, u32 nconv, nconv x u32 kernel, then float32 little-endian in the order
    emb[97][e]; per conv: weight[ch][cin][k], bias[ch]; head weight[3][2*ch], head bias[3]."""
    head = LFW_MAGIC + struct.pack("<III", ch, emb_dim, len(kernels)) + b"".join(struct.pack("<I", k) for k in kernels)
    return head + struct.pack("<%df" % len(floats), *floats)


def lfw_size(ch: int, emb_dim: int, kernels: Sequence[int]) -> int:
    n, cin = VOCAB * emb_dim, emb_dim
    for k in kernels:
        n += ch * cin * k + ch
        cin = ch
    return n + 3 * 2 * ch + 3


@_format_guard
def lfw_load(b: bytes) -> dict:
    if b[:4] != LFW_MAGIC:
        raise FormatError("not an LFW1 file")
    ch, e, nc = struct.unpack_from("<III", b, 4)
    kernels = list(struct.unpack_from("<" + "I" * nc, b, 16))
    off = 16 + 4 * nc
    if len(b) - off != 4 * lfw_size(ch, e, kernels):
        raise FormatError("size mismatch")

    def take(n):
        nonlocal off
        v = list(struct.unpack_from("<%df" % n, b, off))
        off += 4 * n
        return v
    W = {"ch": ch, "e": e, "kernels": kernels, "emb": take(VOCAB * e), "convs": []}
    cin = e
    for k in kernels:
        W["convs"].append((take(ch * cin * k), take(ch), cin, k))
        cin = ch
    W["hw"], W["hb"] = take(3 * 2 * ch), take(3)
    return W


def lfw_forward(W: dict, ids: Sequence[int]) -> List[float]:
    """Logits (EN, RU, OTHER) for a token list at its true length (no padding). Same-padding convolutions,
    ReLU, masked max and mean pooling over all positions (BOS and EOS included), linear head."""
    ch, e, T = W["ch"], W["e"], len(ids)
    x = [[W["emb"][t * e + j] for j in range(e)] for t in ids]
    for (w, bias, cin, k) in W["convs"]:
        pad, y = k // 2, []
        for t in range(T):
            row = []
            for o in range(ch):
                s = bias[o]
                for kk in range(k):
                    u = t + kk - pad
                    if 0 <= u < T:
                        base = o * cin * k
                        for i in range(cin):
                            s += w[base + i * k + kk] * x[u][i]
                row.append(s if s > 0 else 0.0)
            y.append(row)
        x = y
    feat = [max(x[t][o] for t in range(T)) for o in range(ch)] + [sum(x[t][o] for t in range(T)) / T for o in range(ch)]
    return [W["hb"][c] + sum(W["hw"][c * 2 * ch + j] * feat[j] for j in range(2 * ch)) for c in range(3)]


def toy_weights(ch: int = 4, emb_dim: int = 4, kernels=(3, 5, 3), seed: int = 1) -> bytes:
    """Deterministic toy weights (integer arithmetic only, so every language reproduces them exactly)."""
    n = lfw_size(ch, emb_dim, kernels)
    state, floats = seed, []
    for _ in range(n):
        state = (state * 1103515245 + 12345) % (2 ** 31)
        floats.append(((state >> 16) % 33 - 16) / 32.0)       # multiples of 1/32 in [-0.5, 0.5]
    return lfw_pack(ch, emb_dim, kernels, floats)
```

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

```python
"""vectors.py - generates the golden test vectors of section 20.12 from lfengine.py.
Run:  python vectors.py > vectors_out.json   (lfengine.py in the same directory; standard library only)."""
import sys, json, math, hashlib, struct; sys.path.insert(0, ".")
import lfengine as L


def build():
    """Build every golden vector from lfengine.py. The fault-matrix rows carry hand-written predictions and
    generation FAILS when the engine disagrees: producing the vectors is itself a test (20.13)."""
    K = L.keys_from_text
    cal = L.example_cal(); L.check_calibration_package(cal)
    out = {}
    # ---- V1 render + tokens
    rows = []
    for typed, lay in [("ghbdtn","en"),("Ghbdtn","en"),("GHBDTN","en"),("[jhjij","en"),(";bpym","en"),(",jkmit","en"),("k.,k.","en"),("`","en"),("руддщ","ru"),("Руддщ,","ru")]:
        keys = K(typed, lay); other = L.OTHER_LAYOUT[lay]
        rows.append([typed, lay, L.render(keys, other), L.tokens(keys)])
    out["render"] = rows
    # caps
    caps = []
    for kid, sh, cp in [(30,False,True),(23,False,True),(36,True,True),(23,False,False)]:
        k = L.Key(kid, sh, cp); caps.append([kid, sh, cp, L.render_key(k,"en"), L.render_key(k,"ru"), L.token(k)])
    out["caps"] = caps
    out["prefix"] = L.tokens(K("ghb","en"), complete=False)
    out["tok25"] = len(L.tokens([L.Key(i%47) for i in range(25)]))
    # ---- V3 candidates
    cands = []
    for typed, lay, tgt in [("Ghbdtn?","en","ru"),("Ghbdtn?!","en","ru"),("(ghbdtn)","en","ru"),("k.,k.","en","ru"),("[jhjij","en","ru"),("руддщ,","ru","en"),("(руддщ)","ru","en"),("руддщб","ru","en"),("руддщ..","ru","en"),("ghb1","en","ru"),(",","en","ru"),('"ghbdtn"',"en","ru"),("hello,","en","ru"),("Ghbdtn,","en","ru")]:
        run = K(typed, lay); c = L.candidate(run, tgt)
        cands.append([typed, tgt, None if c is None else (L.render(c.lead,tgt), L.render(c.core,tgt), L.render(c.trail,tgt))])
    out["cands"] = cands
    # ---- V4 guards
    gs = []
    for typed, act in [("github.com","en"),("https://x.io","en"),("user@example.com","en"),("MyVariable","en"),("asdfgh","en"),("фывапр","ru"),("kubectl","en"),("ghbdtn","en")]:
        run = K(typed, act)
        cand = L.candidate(run, L.OTHER_LAYOUT[act])
        gs.append([typed, act, L.shape_guard(run, act, cand.core) if cand else "no_candidate"])
    out["guards"] = gs
    # ---- V13 priors, V14 thresholds
    pri = []
    for a in ("en","ru"):
        for st in L.STATES:
            w = cal["w"][a][st]; v = L.deployment_prior(a, w, cal["o_lat"]); pri.append([a, st, w, [round(x,4) for x in v]])
    out["priors"] = pri
    out["lambdas"] = [[t, round(L.logit(t),3)] for t in (0.9995, 0.999, 0.997, 0.995, 0.99, 0.9)]
    # ---- V5 score examples
    sc = []
    for z, a, st in [([-3,9,-2],"en","default"),([-3,9,-2],"en","run"),([-3,9,-2],"en","after_switch"),([8,-3,-2],"ru","default"),([-2,-3,8],"ru","default"),([8,-3,-2],"en","default")]:
        w = cal["w"][a][st]; sc.append([z, a, st, round(L.score(z, a, cal, w), 3)])
    out["scores"] = sc
    # ---- V6 decide with stub scorers
    def mk(z): return lambda ids: z
    dec = []
    lex = {"en": {"hello","the"}, "ru": {"привет"}, "acr_en": {"sql"}, "acr_ru": {"мтс"}}
    cases = [("ghbdtn","en",[-3,9,-2],"default",False,frozenset()),
             ("ghbdtn","en",[-3,8,-2],"default",False,frozenset()),
             ("ghbdtn","en",[-3,8,-2],"run",True,frozenset()),
             ("ghbdtn","en",[-3,9,-2],"default",False,frozenset({("en2ru","ghbdtn")})),
             ("hello","en",[-3,9,-2],"default",False,frozenset()),
             ("z","en",[-3,9,-2],"default",False,frozenset()),
             ("ye","en",[-3,9,-2],"default",False,frozenset()),
             ("ye","en",[-3,9,-2],"run",True,frozenset()),
             ("github.com","en",[-3,9,-2],"default",False,frozenset()),
             ("руддщ","ru",[9,-3,-2],"default",False,frozenset()),
             ("руддщ,","ru",[9,-3,-2],"default",False,frozenset()),
             ("привет","ru",[9,-3,-2],"default",False,frozenset()),
             ("Ghbdtn?","en",[-3,9,-2],"default",False,frozenset())]
    for typed, act, z, st, ra, ex in cases:
        run = K(typed, act)
        d = L.decide(run, act, cal, mk(z), st, ra, ex, lex)
        dec.append([typed, act, z, st, ra, bool(ex), d.action, d.reason, d.replacement, None if d.margin is None else round(d.margin,3), d.n_keys])
    out["decide"] = dec
    # ---- V7 engine traces
    def stub_by_word(table, default):
        def f(ids):
            txt = "".join(L.TABLE["en"][(t-1)%2][(t-1)//2] for t in ids if 1 <= t <= 94)
            return table.get(txt.lower(), default)
        return f
    HI, MID = [-3,9,-2], [-3,6.5,-2]
    sc1 = stub_by_word({"ghbdtn": HI}, MID)
    E = L.Engine(cal, sc1, lex)
    def word(txt, lay, t0):
        for i,k in enumerate(K(txt, lay)): E.on_event(L.Event("key", k, lay, t0+i*100))
        return E.on_event(L.Event("space", None, lay, t0+len(txt)*100+50))
    tr = []
    for txt, t0 in [("ghbdtn",0),("z",1000),("ntcn",2000),("vbh",3000),("ntcn",4000),("ntcn",5000)]:
        st = "run" if E.credit>0 else ("after_switch" if E.after_switch else "default")
        d = word(txt, "en", t0)
        tr.append([txt, st, d.action, d.reason, None if d.margin is None else round(d.margin,3), E.credit])
    out["trace_run"] = tr
    # undo + cooldown
    E = L.Engine(cal, sc1, lex)
    tr2 = []
    d = word("ghbdtn","en",0); tr2.append(["ghbdtn", d.action, d.reason, E.credit])
    E.undo(1000); tr2.append(["(undo at 1000 ms)", "", "", E.credit])
    for txt,t0 in [("ghbdtn",2000),("ghbdtn",3000),("ghbdtn",4000),("ghbdtn",5000),("ghbdtn",11500)]:
        d = word(txt,"en",t0); tr2.append([f"{txt} @{t0}", d.action, d.reason, E.credit])
    out["trace_undo"] = tr2
    # other event scenarios
    def scen(name, evs, gate=None):
        E = L.Engine(cal, sc1, lex); res = []
        for ev in evs:
            if ev == "gate:DENY": E.set_gate("DENY"); continue
            if ev == "gate:ALLOW": E.set_gate("ALLOW"); continue
            r = E.on_event(ev)
            if r is not None: res.append([r.action, r.reason])
        return [name, res]
    ks = lambda t, l="en", tl="en": [L.Event("key", k, l, i*100) for i,k in enumerate(K(t,tl))]
    sp = lambda l="en", t=9000: L.Event("space", None, l, t)
    out["scen"] = [
     scen("word + Space", ks("ghbdtn")+[sp()]),
     scen("word + Enter (break), then Space", ks("ghbdtn")+[L.Event("break")]+[sp()]),
     scen("word + Tab (break), then Space", ks("ghbdtn")+[L.Event("break")]+[sp()]),
     scen("layout changes inside the word (key layout differs)", ks("ghb")+ks("dtn","ru","en")+[sp("ru")]),
     scen("manual layout event inside the word", ks("ghb")+[L.Event("layout")]+ks("dtn")+[sp()]),
     scen("Space sampled on another layout", ks("ghbdtn")+[sp("ru")]),
     scen("gate DENY while typing (password field)", ["gate:DENY"]+ks("ghbdtn")+[sp()]),
     scen("gate DENY then ALLOW again, new word", ["gate:DENY"]+ks("ghbdtn")+[sp(), "gate:ALLOW"]+ks("ghbdtn")+[sp()]),
     scen("Backspace edits the word", ks("ghbdtnx")+[L.Event("backspace")]+[sp()]),
     scen("65 keys (overflow)", [L.Event("key", L.Key(i%33), "en", i) for i in range(65)]+[sp()]),
     scen("two Spaces", ks("ghbdtn")+[sp(),sp()]),
    ]
    # ---- V8 manual
    out["manual"] = [[t, *L.manual_convert(t)] for t in ["Ghbdtn? Rfr ltkf?","Привет, как дела?","123","ghbdtn 😀","ЁЖ ёж","Hello, Привет"]]
    # ---- V9 ev1
    out["ev1"] = [
     ["4 errors, 4 users, n=100000, 20 users, 100 docs", L.ev1_pass([("u%d"%i,"d%d"%i) for i in range(4)],100000,20,100), round(L.ev1_bound([("u%d"%i,"d%d"%i) for i in range(4)],100000),7)],
     ["4 errors in one document", L.ev1_pass([("u1","d1")]*4,100000,20,100), round(L.ev1_bound([("u1","d1")]*4,100000),7)],
     ["0 errors, n=100000", L.ev1_pass([],100000,20,100), round(L.ev1_bound([],100000),7)],
     ["0 errors, n=99999", L.ev1_pass([],99999,20,100), round(L.ev1_bound([],99999),7)],
     ["0 errors, 19 users", L.ev1_pass([],200000,19,100), round(L.ev1_bound([],200000),7)],
     ["5 errors in 5 clusters, n=150000", L.ev1_pass([("u%d"%i,"d%d"%i) for i in range(5)],150000,20,100), round(L.ev1_bound([("u%d"%i,"d%d"%i) for i in range(5)],150000),7)],
     ["2+2 errors in 2 clusters, n=100000", L.ev1_pass([("u1","d1")]*2+[("u2","d2")]*2,100000,20,100), round(L.ev1_bound([("u1","d1")]*2+[("u2","d2")]*2,100000),7)],
    ]
    out["poisson"] = [round(L.poisson_upper(k),4) for k in range(6)]
    # ---- V10 baseline toy
    def keyrow(w, lay): return L.tokens(K(w, lay))
    # train each class on key rows of its own words (RU words typed on RU layout, EN/OTHER on EN)
    trainset = {0:[keyrow(w,"en") for w in ["hello","hell","help","hero","world","word"]],
                1:[keyrow(w,"ru") for w in ["привет","привал","приказ","пригород","мир","мирно"]],
                2:[keyrow(w,"en") for w in ["kubectl","github","asdfgh","docker","nginx","vim"]]}
    ms = [L.WittenBell().fit(trainset[c]) for c in range(3)]
    lp = [math.log(x) for x in cal["pi_train"]]
    blob = L.lfb_pack(ms, lp); pkg = L.lfb_load(blob)
    test = keyrow("ghbdtn","en")
    lg = L.baseline_logits(ms, lp, test)
    out["wb"] = {"test_word_keys":"ghbdtn", "logp_by_class":[round(m.logp(test),6) for m in ms], "logits":[round(v,6) for v in lg],
                 "lfb_bytes": len(blob), "lfb_sha256_16": hashlib.sha256(blob).hexdigest()[:16],
                 "lfb_logp": [round(L.lfb_logp(pkg,c,test),6) for c in range(3)],
                 "hello_ru": round(ms[1].logp(keyrow("hello","en")),6), "hello_en": round(ms[0].logp(keyrow("hello","en")),6),
                 "n_pairs": [sum(len(d) for k in range(3) for d in m.cnt[k].values()) for m in ms]}
    out["wb_score"] = round(L.score(lg, "en", {**cal, "temperature":{"network":1.0,"ngram":1.0}}, 0.01, "ngram"), 3)
    # ---- V11 toy network
    tw = L.toy_weights(); W = L.lfw_load(tw)
    out["lfw"] = {"bytes": len(tw), "sha256_16": hashlib.sha256(tw).hexdigest()[:16],
                  "logits_ghbdtn": [round(v,6) for v in L.lfw_forward(W, L.tokens(K("ghbdtn","en")))],
                  "logits_hello": [round(v,6) for v in L.lfw_forward(W, L.tokens(K("hello","en")))],
                  "first_floats": [float(x) for x in struct.unpack_from("<4f", tw, 16+12)]}
    out["fnv"] = [[s, hex(L.fnv1a64(s.encode()))] for s in ["", "a", "foobar"]] + [["ctx_key(2,(95,61))", hex(L.ctx_key(2,(95,61)))], ["pair_key(2,(95,61),63)", hex(L.pair_key(2,(95,61),63))]]
    # ---- V12 lexicon tables and calibration package
    lexb = L.lfl_pack({"lex_en": ["Hello", "the", "World"], "lex_ru": ["привет", "мир"], "acr_en": ["SQL"], "acr_ru": ["МТС"]})
    lt = L.lfl_load(lexb)
    out["lfl"] = {"bytes": len(lexb), "sha256_16": hashlib.sha256(lexb).hexdigest()[:16],
                  "keys": [["lex_en", "hello", hex(L.lex_key(1, "hello"))], ["lex_ru", "привет", hex(L.lex_key(2, "привет"))],
                           ["acr_ru", "МТС", hex(L.lex_key(4, "МТС"))]],
                  "member": [["lex_en", "HELLO", "HELLO" in lt["lex_en"]], ["lex_en", "hi", "hi" in lt["lex_en"]],
                             ["acr_en", "sql", "sql" in lt["acr_en"]]]}
    cj = L.cal_to_json(cal)
    out["cal_json"] = {"bytes": len(cj.encode("utf-8")), "sha256_16": hashlib.sha256(cj.encode("utf-8")).hexdigest()[:16]}
    # ---- V15 Caps Lock on the letter keys of the two layouts (token formula of 20.2)
    out["caps_all"] = [[kid, sh, cp, L.render_key(L.Key(kid, sh, cp), "en"), L.render_key(L.Key(kid, sh, cp), "ru"),
                        L.token(L.Key(kid, sh, cp))]
                       for kid in (0, 5, 13, 23, 24, 25, 30, 35, 36, 44, 45, 46)
                       for sh, cp in ((False, False), (True, False), (False, True), (True, True))]
    # ---- V16 undo snapshot lifecycle (13.3, 13.4)
    def fresh(layout="en", t0=1000, word_="ghbdtn", caps=False):
        e = L.Engine(cal, (lambda ids: [-3, 9, -2]) if layout == "en" else (lambda ids: [9, -3, -2]), lex)
        for i, k in enumerate(K(word_, layout)):
            e.on_event(L.Event("key", L.Key(k.id, k.shift, caps), layout, t0 + i))
        d = e.on_event(L.Event("space", None, layout, t0 + len(word_)))
        return e, d, t0 + len(word_)
    ul = []
    e, d, ts = fresh(); ul.append(["convert", d.action, d.replacement, e.snapshot is not None])
    r = e.undo(ts + 500); ul.append(["undo after 500 ms", r, sorted(e.exceptions), e.credit, e.cool_words, e.snapshot is not None])
    ul.append(["second undo", e.undo(ts + 600)])
    e, d, ts = fresh(); ul.append(["undo at exactly 10000 ms", e.undo(ts + 10000)])
    e, d, ts = fresh(); ul.append(["undo at 10001 ms", e.undo(ts + 10001)])
    for n_after in (100, 101):
        e, d, ts = fresh()
        for i in range(n_after):
            e.on_event(L.Event("key", L.Key(i % 47), "en", ts + 10 + i))
        ul.append([f"undo after {n_after} further characters", e.undo(ts + 2000)])
    e, d, ts = fresh(caps=True); ul.append(["Caps Lock word", d.action, d.replacement, e.undo(ts + 5)])
    e, d, ts = fresh("ru", word_="руддщ"); ul.append(["ru to en", d.action, d.replacement, e.undo(ts + 5)])
    for name, act in [("break", lambda e: e.on_event(L.Event("break"))), ("layout change", lambda e: e.on_event(L.Event("layout", None, "ru"))),
                      ("gap", lambda e: e.on_event(L.Event("gap"))), ("gate DENY", lambda e: e.set_gate("DENY")),
                      ("mode MANUAL_ONLY", lambda e: e.set_mode("MANUAL_ONLY")), ("outcome RESTORED", lambda e: e.on_outcome("RESTORED")),
                      ("outcome VERIFIED", lambda e: e.on_outcome("VERIFIED")), ("backspace", lambda e: e.on_event(L.Event("backspace")))]:
        e, d, ts = fresh(); act(e); ul.append([f"after {name}", e.undo(ts + 5), e.credit])
    out["undo"] = ul
    # ---- V17 mode derivation (13.5)
    CAPS_M1 = ["READBACK", "READ_RANGE", "REPLACE_RANGE", "ROLLBACK"]
    CAPS_M2 = ["READBACK", "READ_RANGE", "SYNTHETIC_INPUT"]
    out["modes"] = [[name, caps, sup, flags, L.engine_mode(caps, sup, **flags)] for name, caps, sup, flags in [
        ("M1 with rollback", CAPS_M1, "AUTO", {}), ("M1 with rollback", CAPS_M1, "MANUAL", {}), ("M1 with rollback", CAPS_M1, "UNKNOWN", {}),
        ("M1 without rollback", CAPS_M1[:3], "AUTO", {}), ("M2 only", CAPS_M2, "AUTO", {}), ("M2 only", CAPS_M2, "MANUAL", {}),
        ("M1 with rollback", CAPS_M1, "AUTO", {"hook_ok": False}), ("M1 with rollback", CAPS_M1, "AUTO", {"models_ok": False}),
        ("M1 with rollback", CAPS_M1, "AUTO", {"watchdog_ok": False}), ("M1 with rollback", CAPS_M1, "AUTO", {"layout_ok": False}),
        ("M1 with rollback", CAPS_M1, "AUTO", {"permission_ok": False}), ("M1 with rollback", CAPS_M1, "AUTO", {"quarantined": True}),
        ("read only", ["READ_RANGE"], "AUTO", {}), ("nothing", [], "AUTO", {})]]
    # ---- V18 outcome classification
    out["outcome"] = [[a, o, n, f, v, L.classify_outcome(a, o, n, f, v)] for a, o, n, f, v in [
        (False, "x", "y", None, False), (True, "x", "y", "y", True), (True, "x", "y", "y", False), (True, "x", "y", "x", False),
        (True, "x", "y", "z", False), (True, "x", "y", None, False)]]
    # ---- V19 replacement transaction against injected faults. Expected values are hand-written; generation fails on a mismatch.
    M1 = {"READ_RANGE", "REPLACE_RANGE", "READBACK", "ROLLBACK"}; M1N = {"READ_RANGE", "REPLACE_RANGE", "READBACK"}
    M2 = {"READ_RANGE", "READBACK", "SYNTHETIC_INPUT"}
    B, C = "Hello ghbdtn ", "Hello привет "
    MAN = {"mode": "MANUAL_ONLY"}
    FM = [  # name, caps, text, faults, ahead, kwargs, outcome, reason, final text, incident
        ("m1 ok", M1, B, {}, "", {}, "VERIFIED", "ok", C, False),
        ("m1 ok with typed-ahead keys", M1, B + "ab", {}, "ab", {}, "VERIFIED", "ok", "Hello привет ab", False),
        ("m1 ok, the application has not shown the last typed-ahead key", M1, B + "a", {}, "ab", {}, "VERIFIED", "ok", "Hello привет a", False),
        ("m1 user key lands before the range is read", M1, B, {"read:1": "user:x"}, "", {}, "VERIFIED", "ok", "Hello привет x", False),
        ("m1 user key lands just before the write", M1, B, {"replace:1": "user:x"}, "", {}, "VERIFIED", "ok", "Hello привет x", False),
        ("too many typed-ahead keys", M1, B + "abcd", {}, "abcd", {}, "ABORTED", "typed_ahead", B + "abcd", False),
        ("context break", M1, B, {}, "", {"context_break": True}, "ABORTED", "context_break", B, False),
        ("layout changed", M1, B, {}, "", {"layout_changed": True}, "ABORTED", "context_break", B, False),
        ("gate turned DENY", M1, B, {"gate:1": "DENY"}, "", {}, "ABORTED", "gate_changed", B, False),
        ("gate unknown", M1, B, {"gate:1": "UNKNOWN"}, "", {}, "ABORTED", "gate_changed", B, False),
        ("gate query fails", M1, B, {"gate:1": "raise"}, "", {}, "ABORTED", "gate_changed", B, False),
        ("caret query fails", M1, B, {"caret:1": "raise"}, "", {}, "ABORTED", "adapter_error", B, False),
        ("range unreadable", M1, B, {"read:1": "none"}, "", {}, "ABORTED", "echo_mismatch", B, False),
        ("read times out", M1, B, {"read:1": "raise"}, "", {}, "ABORTED", "adapter_error", B, False),
        ("read returns stale text", M1, B, {"read:1": "stale"}, "", {}, "ABORTED", "echo_mismatch", B, False),
        ("application had autocorrected the word", M1, "Hello Ghbdtn ", {}, "", {}, "ABORTED", "echo_mismatch", "Hello Ghbdtn ", False),
        ("typed-ahead key the engine did not record", M1, B + "x", {}, "", {}, "ABORTED", "echo_mismatch", B + "x", False),
        ("partial write, rollback works", M1, B, {"replace:1": "partial"}, "", {}, "RESTORED", "write_error", B, True),
        ("write fails, nothing written", M1, B, {"replace:1": "raise"}, "", {}, "RESTORED", "write_error", B, True),
        ("write applied but reports a timeout", M1, B, {"replace:1": "applied_error"}, "", {}, "RESTORED", "write_error", B, True),
        ("application autocorrects the written text", M1, B, {"replace:1": "autocorrect"}, "", {}, "RESTORED", "verify_failed", B, True),
        ("write silently ignored", M1, B, {"replace:1": "ignored"}, "", {}, "RESTORED", "verify_failed", B, True),
        ("read-back differs", M1, B, {"read:2": "stale"}, "", {}, "RESTORED", "verify_failed", B, True),
        ("read-back times out", M1, B, {"read:2": "raise"}, "", {}, "RESTORED", "verify_failed", B, True),
        ("caret ends up before its expected place", M1, B, {"caret:2": "back"}, "", {}, "RESTORED", "verify_failed", B, True),
        ("partial write and the rollback fails", M1, B, {"replace:1": "partial", "replace:2": "raise"}, "", {}, "UNRECOVERED", "write_error", "Hello приdtn ", True),
        ("autocorrect and the rollback is ignored", M1, B, {"replace:1": "autocorrect", "replace:2": "ignored"}, "", {}, "UNRECOVERED", "verify_failed", "Hello приве? ", True),
        ("no rollback capability, partial write", M1N, B, {"replace:1": "partial"}, "", MAN, "UNRECOVERED", "write_error", "Hello приdtn ", True),
        ("no rollback capability, but the write is fine", M1N, B, {}, "", MAN, "VERIFIED", "ok", C, False),
        ("AUTO requested without the capabilities", M1N, B, {}, "", {"mode": "AUTO"}, "ABORTED", "capability", B, False),
        ("AUTO requested for synthetic input", M2, B, {}, "", {"mode": "AUTO"}, "ABORTED", "capability", B, False),
        ("mode OFF", M1, B, {}, "", {"mode": "OFF"}, "ABORTED", "mode_off", B, False),
        ("no read capability", {"REPLACE_RANGE", "ROLLBACK"}, B, {}, "", MAN, "ABORTED", "capability", B, False),
        ("m2 manual ok", M2, B, {}, "", MAN, "VERIFIED", "ok", C, False),
        ("m2 with typed-ahead keys is refused", M2, B + "a", {}, "a", MAN, "ABORTED", "typed_ahead", B + "a", False),
        ("m2 user key between synthetic events", M2, B, {"event:3": "user:x"}, "", MAN, "UNRECOVERED", "verify_failed", "Hello gпривет ", True),
        ("m2 synthetic event times out", M2, B, {"event:5": "raise"}, "", MAN, "UNRECOVERED", "write_error", "Hello ghb", True),
        ("m2 user key while the range is read: nothing is sent", M2, B, {"read:1": "user:x"}, "", MAN, "ABORTED", "typed_ahead", B + "x", False),
        ("m2 user key before the first synthetic event: the race that stays", M2, B, {"event:1": "user:x"}, "", MAN, "UNRECOVERED", "verify_failed", "Hello gпривет ", True),
        ("m1 caret forward although no user key came", M1, B, {"caret:2": "forward"}, "", {}, "RESTORED", "verify_failed", B, True),
        ("m1 one user key during the read-back moves the caret by one", M1, B, {"read:2": "user:x"}, "", {}, "VERIFIED", "ok", "Hello привет x", False),
        ("m1 one user key does not explain a caret two forward", M1, B, {"read:2": "user:x", "caret:2": "forward"}, "", {}, "RESTORED", "verify_failed", B + "x", True),
        ("m1 write damages the Space after the range", M1, B, {"replace:1": "spill"}, "", {}, "UNRECOVERED", "verify_failed", "Hello ghbdtn?", True),
        ("m1 write damages the Space, a typed-ahead key follows", M1, B + "a", {"replace:1": "spill"}, "a", {}, "UNRECOVERED", "verify_failed", "Hello ghbdtn?a", True),
        ("m1 autocorrect with a typed-ahead key, the rollback restores the fragment", M1, B + "a", {"replace:1": "autocorrect"}, "a", {}, "RESTORED", "verify_failed", B + "a", True),
        ("m1 a key that types nothing during the read-back is allowed", M1, B, {"read:2": "key"}, "", {}, "VERIFIED", "ok", C, False),
        ("m1 one key may explain a caret one place forward", M1, B, {"read:2": "key", "caret:2": "forward"}, "", {}, "VERIFIED", "ok", C, False),
        ("m1 one key does not explain a caret behind its place", M1, B, {"read:2": "key", "caret:2": "back"}, "", {}, "RESTORED", "verify_failed", B, True),
        ("m1 one typed key and a caret one place back is still inside the window", M1, B, {"read:2": "user:x", "caret:2": "back"}, "", {}, "VERIFIED", "ok", "Hello привет x", False),
        ("m2 a key that types nothing while the range is read: nothing is sent", M2, B, {"read:1": "key"}, "", MAN, "ABORTED", "typed_ahead", B, False),
        ("m2 a key that types nothing between synthetic events", M2, B, {"event:3": "key"}, "", MAN, "VERIFIED", "ok", C, False),
        ("m1 a key during the write explains a caret one place forward", M1, B, {"replace:1": "key", "caret:2": "forward"}, "", {}, "VERIFIED", "ok", C, False),
        ("m1 a key during the write does not explain a caret two places forward", M1, B, {"replace:1": "key", "caret:2": "forward2"}, "", {}, "RESTORED", "verify_failed", B, True),
        ("m1 a key during the read-back does not explain a caret two places forward", M1, B, {"read:2": "key", "caret:2": "forward2"}, "", {}, "RESTORED", "verify_failed", B, True),
        ("m2 a key between synthetic events explains a caret one place forward", M2, B, {"event:3": "key", "caret:2": "forward"}, "", MAN, "VERIFIED", "ok", C, False),
        ("m2 a key between synthetic events does not explain a caret two places forward", M2, B, {"event:3": "key", "caret:2": "forward2"}, "", MAN, "UNRECOVERED", "verify_failed", C, True),
        ("m2 the synthetic events are not user keys: a caret ahead without any user key fails", M2, B, {"caret:2": "forward"}, "", MAN, "UNRECOVERED", "verify_failed", C, True),
    ]
    tx = []
    for name, caps, text, faults, ahead, kw, outcome, reason, final, incident in FM:
        f = L.SimField(text, caps, {(k.split(":")[0], int(k.split(":")[1])): v for k, v in faults.items()})
        r = L.run_transaction(f, "ghbdtn", "привет", ahead, **kw)
        got = (r.outcome, r.reason, f.text, r.incident, r.quarantine)
        if got != (outcome, reason, final, incident, incident):
            raise AssertionError(f"fault matrix row {name!r}: engine gives {got}")
        tx.append([name, sorted(caps), text, faults, ahead, kw, outcome, reason, final, incident])
    out["tx"] = tx
    # ---- V20 layout identity
    en_e, ru_e = L.table_entries("en"), L.table_entries("ru")
    typew = list(ru_e); typew[9] = "$"
    out["fingerprint"] = [["en", L.layout_fingerprint(en_e), L.identify_layout(en_e)], ["ru", L.layout_fingerprint(ru_e), L.identify_layout(ru_e)],
                          ["ru with key 4 shifted changed to $", L.layout_fingerprint(typew), L.identify_layout(typew)],
                          ["en rotated by one entry", L.layout_fingerprint(en_e[1:] + en_e[:1]), L.identify_layout(en_e[1:] + en_e[:1])]]
    # ---- V21 hook health
    h = L.HookHealth(canary=True); hh = []
    for t in (0, 100, 200):
        h.raw_key(t, "s%d" % t); h.hook_key(t + 5, "s%d" % t)
    hh.append(["three matched keys", h.check(250), h.take_gap()])
    h.raw_key(1000, "k"); hh.append(["key unseen by the hook, at the limit", h.check(1300), h.take_gap()])
    hh.append(["key unseen by the hook, past the limit", h.check(1301), h.take_gap(), h.reason])
    hh.append(["gap is reported once", h.ok, h.take_gap()])
    h.reinstalled()
    for i in range(3):
        h.raw_key(3000 + i, i); h.hook_key(3000 + i, i); hh.append([f"re-arm pair {i + 1}", h.ok, h.take_gap()])
    c = L.HookHealth(); c.raw_key(0, "a"); c.hook_key(3, "a"); c.raw_key(100, "b"); c.hook_key(105, "c")
    hh.append(["lost b and extra c cancel as counts, at the limit", c.check(400), c.take_gap(), c.reason])
    hh.append(["lost b and extra c cancel as counts, past the limit", c.check(401), c.take_gap(), c.reason])
    c = L.HookHealth(); c.hook_key(0, "c")
    hh.append(["extra hook key alone, at the limit", c.check(300), c.take_gap(), c.reason])
    hh.append(["extra hook key alone, past the limit", c.check(301), c.take_gap(), c.reason])
    c = L.HookHealth(); c.hook_key(10, "a"); c.raw_key(12, "a"); c.hook_key(30, "c", injected=True)
    hh.append(["hook event first, injected event ignored", c.check(10_000), c.take_gap(), c.reason])
    c = L.HookHealth(); c.raw_key(0, "a"); c.raw_key(50, "a"); c.hook_key(55, "a")
    hh.append(["two physical presses, one reported, at the limit of the unmatched press", c.check(350), c.take_gap(), c.reason])
    hh.append(["two physical presses, one reported, past the limit of the unmatched press", c.check(351), c.take_gap(), c.reason])
    c = L.HookHealth(); c.raw_key(0, "a"); c.hook_key(300, "a")
    hh.append(["counterpart exactly at the limit, the watchdog has not run", c.ok, c.take_gap(), c.reason])
    c = L.HookHealth(); c.raw_key(0, "a"); c.hook_key(301, "a")
    hh.append(["hook event one ms too late, the watchdog has not run", c.ok, c.take_gap(), c.reason])
    c = L.HookHealth(); c.hook_key(0, "a"); c.raw_key(301, "a")
    hh.append(["raw event one ms too late, the watchdog has not run", c.ok, c.take_gap(), c.reason])
    c = L.HookHealth(); c.raw_key(0, "a"); c.raw_key(301, "b")
    hh.append(["a later event of the same side shows that the first has expired", c.ok, c.take_gap(), c.reason])
    m = L.HookHealth(canary=False); m.tap_disabled("timeout"); hh.append(["macOS tapDisabledByTimeout", m.ok, m.take_gap(), m.reason])
    m.reinstalled(); hh.append(["macOS tap enabled again", m.ok, m.take_gap(), m.reason])
    m.tap_disabled("user_input"); hh.append(["macOS tapDisabledByUserInput", m.ok, m.take_gap(), m.reason])
    out["hook"] = hh
    return out


def dumps(v):
    return json.dumps(v, ensure_ascii=False)
def block(v):    # valid JSON, one row per line
    if isinstance(v, list) and v and isinstance(v[0], list):
        return "[\n" + ",\n".join(" " + dumps(r) for r in v) + "\n]"
    if isinstance(v, dict):
        return "{\n" + ",\n".join(" " + dumps(k) + ": " + dumps(x) for k, x in v.items()) + "\n}"
    return dumps(v)
def render(out):
    return "{\n" + ",\n".join(dumps(k) + ": " + block(v) for k, v in out.items()) + "\n}\n"


if __name__ == "__main__":
    sys.stdout.write(render(build()))
```

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

```python
"""conformance.py - property, negative and fault-injection tests of section 20.13 (standard library only).
Usage:  python conformance.py [N]      N = number of fuzz events (default 200000; the audit runs 1000000)
Run it in the folder that holds lfengine.py. It prints OK, or raises AssertionError. It also works under
`python -O`, because it never uses the assert statement (asserts disappear when optimised)."""
import sys, random, math, itertools, copy, json; sys.path.insert(0, ".")
import lfengine as L

N = int(sys.argv[1]) if len(sys.argv) > 1 else 200_000
R = random.Random(1)
CHECKS = 0


def T(cond, what=""):
    """The one check function: a failed condition always raises, with or without -O."""
    global CHECKS
    CHECKS += 1
    if not cond:
        raise AssertionError(what or "check failed")


def raises(exc, fn, what):
    global CHECKS
    CHECKS += 1
    try:
        fn()
    except exc:
        return
    except Exception as e:                                # a wrong exception type is also a failure
        raise AssertionError(f"{what}: raised {type(e).__name__}, expected {exc.__name__}")
    raise AssertionError(f"{what}: nothing was raised")


# ---- P1 tokens, rendering, candidate -------------------------------------------------------------------
for _ in range(N):
    run = [L.Key(R.randrange(47), R.random() < .5, R.random() < .3) for _ in range(R.randrange(1, 12))]
    T(all(1 <= L.token(k) <= 94 for k in run), "token range")
    for lay in ("en", "ru"):
        txt = L.render(run, lay)
        T(L.render([L.Key(k.id, L.effective_shift(k, lay)) for k in run], lay) == txt, "effective shift")
        T(L.render(L.keys_from_text(txt, lay), lay) == txt, "round trip")
    for tgt in ("en", "ru"):
        c = L.candidate(run, tgt)
        if c:
            T(c.lead + c.core + c.trail == tuple(run), "a key was lost or duplicated by segmentation")
            T(len(c.lead) <= 1 and len(c.trail) <= 2 and len(c.core) >= 1, "peel limits")
            T(all(L.is_letter_in(tgt, k.id) for k in c.core), "the core is letters only")

# ---- P2 every prior is a probability vector ------------------------------------------------------------
for a in ("en", "ru"):
    for st in L.STATES:
        cal = L.example_cal()
        T(abs(sum(L.deployment_prior(a, cal["w"][a][st], cal["o_lat"])) - 1) < 1e-12, "prior sums to 1")

# ---- P3 calibration package: every mutation is refused with CalibrationError, and the engine does not start ----
ok_cal = L.example_cal()
L.check_calibration_package(ok_cal)
T(L.pi_from_counts(ok_cal["pi_train_counts"]) == ok_cal["pi_train"], "pi_train is derived from the counts")


def mutated(path, value):
    c = copy.deepcopy(ok_cal)
    cur = c
    for p in path[:-1]:
        cur = cur[p]
    if value is DELETE:
        del cur[path[-1]]
    else:
        cur[path[-1]] = value
    return c


DELETE = object()
nan, inf = float("nan"), float("inf")
BAD = {
    "unit mix-up (a probability stored as nats)": (["lambda_nats", "network", "en2ru", "5-7"], 0.997),
    "network table missing": (["lambda_nats", "network"], DELETE),
    "ngram table missing": (["lambda_nats", "ngram"], DELETE),
    "direction missing": (["lambda_nats", "network", "ru2en"], DELETE),
    "bucket missing": (["lambda_nats", "ngram", "en2ru", "8+"], DELETE),
    "bucket is a string": (["lambda_nats", "network", "en2ru", "3-4"], "6.9"),
    "bucket is NaN": (["lambda_nats", "network", "en2ru", "3-4"], nan),
    "bucket is +Inf": (["lambda_nats", "network", "en2ru", "3-4"], inf),
    "bucket is a bool": (["lambda_nats", "network", "en2ru", "3-4"], True),
    "table is a list": (["lambda_nats", "network", "en2ru"], [6.9, 5.8, 5.3]),
    "T is NaN": (["temperature", "network"], nan),
    "T is +Inf": (["temperature", "network"], inf),
    "T is -Inf": (["temperature", "ngram"], -inf),
    "T is zero": (["temperature", "network"], 0.0),
    "T is negative": (["temperature", "ngram"], -1.0),
    "T is too large": (["temperature", "network"], 99.0),
    "T of one scorer missing": (["temperature", "ngram"], DELETE),
    "T is a per-class list": (["temperature", "network"], [1.0, 1.0, 1.0]),
    "pi_train too short": (["pi_train"], [0.5, 0.5]),
    "pi_train has a zero": (["pi_train"], [0.5, 0.5, 0.0]),
    "pi_train has a negative": (["pi_train"], [0.6, 0.5, -0.1]),
    "pi_train is not normalised": (["pi_train"], [0.39, 0.40, 0.22]),
    "pi_train differs from its counts": (["pi_train"], [0.40, 0.38, 0.22]),
    "counts have a zero": (["pi_train_counts"], [38000, 40000, 0]),
    "counts are floats": (["pi_train_counts"], [38000.0, 40000.0, 22000.0]),
    "counts too short": (["pi_train_counts"], [38000, 40000]),
    "o_lat is 1": (["o_lat"], 1.0),
    "o_lat is NaN": (["o_lat"], nan),
    "w[en] missing a state": (["w", "en", "run"], DELETE),
    "w is zero": (["w", "ru", "default"], 0.0),
    "w[run] above its cap": (["w", "en", "run"], 0.4),
    "two-key list missing": (["two_key_allow", "ru2en"], DELETE),
    "two-key list empty": (["two_key_allow", "en2ru"], set()),
    "two-key word of three letters": (["two_key_allow", "en2ru"], {"на", "она"}),
    "two-key word of one letter": (["two_key_allow", "en2ru"], {"на", "н"}),
    "two-key word not case-folded": (["two_key_allow", "en2ru"], {"На"}),
    "two-key word with a space": (["two_key_allow", "en2ru"], {"н "}),
    "two-key list is a list, not a set": (["two_key_allow", "en2ru"], ["на"]),
    "two-key list is a string": (["two_key_allow", "en2ru"], "на не"),
    "wrong schema": (["schema"], "LFC0"),
    "unknown field": (["extra"], 1),
    "field missing": (["o_lat"], DELETE),
}
for what, (path, value) in BAD.items():
    bad = mutated(path, value)
    raises(L.CalibrationError, lambda b=bad: L.check_calibration_package(b), what)
    raises(L.CalibrationError, lambda b=bad: L.Engine(b, lambda ids: [0, 0, 0]), "engine must not start: " + what)
raises(L.CalibrationError, lambda: L.check_calibration_package(None), "package is None")
raises(L.CalibrationError, lambda: L.check_calibration_package([]), "package is a list")
raises(L.CalibrationError, lambda: L.Engine(ok_cal, lambda ids: [0, 0, 0], kind="forest"), "unknown scorer kind")
good_json = L.cal_to_json(ok_cal)
T(L.cal_to_json(L.cal_from_json(good_json)) == good_json, "JSON round trip")
for what, text in {
    "NaN": good_json.replace('"network": 1.0', '"network": NaN', 1),
    "Infinity": good_json.replace('"network": 1.0', '"network": Infinity', 1),
    "duplicate key": good_json.replace('"o_lat"', '"o_lat": 0.25, "o_lat"', 1),
    "not JSON": "{",
    "not an object": "[1]",
    "allow list of numbers": good_json.replace('"на"', "5", 1),
    "allow list is a string": json.dumps({**json.loads(good_json), "two_key_allow": {**json.loads(good_json)["two_key_allow"], "en2ru": "на не но"}}, ensure_ascii=False),
    "allow list is null": json.dumps({**json.loads(good_json), "two_key_allow": {**json.loads(good_json)["two_key_allow"], "en2ru": None}}, ensure_ascii=False),
    "allow list has a duplicate": json.dumps({**json.loads(good_json), "two_key_allow": {**json.loads(good_json)["two_key_allow"], "en2ru": ["на", "на"]}}, ensure_ascii=False),
    "allow list of one-letter words": json.dumps({**json.loads(good_json), "two_key_allow": {**json.loads(good_json)["two_key_allow"], "en2ru": ["н", "а"]}}, ensure_ascii=False),
    "allow list is empty": json.dumps({**json.loads(good_json), "two_key_allow": {**json.loads(good_json)["two_key_allow"], "en2ru": []}}, ensure_ascii=False),
}.items():
    raises(L.CalibrationError, lambda t=text: L.cal_from_json(t), "JSON: " + what)
# the runtime reaction: a refused package gives a defined mode, never a half-activated engine
T(L.engine_mode({L.READ_RANGE, L.REPLACE_RANGE, L.READBACK, L.ROLLBACK}, "AUTO", models_ok=False) == "MANUAL_ONLY",
  "refused package: MANUAL_ONLY")

# ---- P4 LFB1 round trip equals the in-memory model -----------------------------------------------------
cal = L.example_cal()
rows = [[L.BOS] + [L.token(L.Key(R.randrange(47), R.random() < .3)) for _ in range(R.randrange(2, 9))] + [L.EOS]
        for _ in range(300)]
ms = [L.WittenBell().fit(rows[i::3]) for i in range(3)]
pkg = L.lfb_load(L.lfb_pack(ms, [math.log(x) for x in cal["pi_train"]]))
T(max(abs(L.lfb_logp(pkg, c, r) - ms[c].logp(r)) for c in range(3) for r in rows[:100]) < 1e-12, "LFB1 round trip")

# ---- P5 LFW1: size is header + 4 bytes per parameter; three finite logits -------------------------------
tw = L.toy_weights()
T(len(tw) == 16 + 4 * 3 + 4 * L.lfw_size(4, 4, (3, 5, 3)), "LFW1 size")
out = L.lfw_forward(L.lfw_load(tw), L.tokens(L.keys_from_text("ghbdtn", "en")))
T(len(out) == 3 and all(math.isfinite(v) for v in out), "LFW1 forward")

# ---- P6 Caps Lock: the token formula, key by key ---------------------------------------------------------
RU_ONLY = (0, 23, 24, 35, 36, 44, 45)                       # ` [ ] ; ' , .  (letters only in Russian)
T(sorted(set(L.LETTER_KEYS) - {k for k in range(47) if L.TABLE["en"][0][k].isalpha()}) == sorted(RU_ONLY), "L")
for kid in range(47):
    for sh, cp in itertools.product((False, True), repeat=2):
        k = L.Key(kid, sh, cp)
        expect = 1 + 2 * kid + int(sh ^ (cp and kid in L.LETTER_KEYS))
        T(L.token(k) == expect, f"token formula key {kid} shift {sh} caps {cp}")
        if L.TABLE["en"][0][kid].isalpha():                  # Latin letters: the token equals the shift of BOTH layouts
            T(bool((L.token(k) - 1) & 1) == L.effective_shift(k, "en") == L.effective_shift(k, "ru"), "latin letter")
        if kid in RU_ONLY:                                   # seven keys: the token carries the flip, English rendering does not
            T(bool((L.token(k) - 1) & 1) == L.effective_shift(k, "ru"), "ru-only letter follows the Russian layout")
            T(L.render_key(k, "en") == L.TABLE["en"][int(sh)][kid], "Caps Lock does not change the English character")
        if kid not in L.LETTER_KEYS:                         # digits, - = \ / : Caps Lock never reaches the token
            T(L.token(k) == 1 + 2 * kid + int(sh), "non-letter key")
```

**`conformance.py`, part 2 of 3 (P7 to P13: modes, outcomes, the fault matrix of the replacement transaction, the engine, layout identity, hook health, the event fuzz).**

```python
# ---- P7 engine_mode: the whole truth table, plus the invariants that matter -------------------------------
CAPS = sorted(L.CAPABILITIES)
for r in range(len(CAPS) + 1):
    for caps in itertools.combinations(CAPS, r):
        for support in L.SUPPORT_STATUS:
            for flags in itertools.product((True, False), repeat=6):
                kw = dict(zip(("models_ok", "layout_ok", "permission_ok", "hook_ok", "watchdog_ok", "quarantined"), flags))
                m = L.engine_mode(caps, support, **kw)
                fs = frozenset(caps)
                if m == "AUTO":
                    T(L.AUTO_REQUIRES <= fs and support == "AUTO" and kw["models_ok"] and kw["hook_ok"]
                      and kw["watchdog_ok"] and kw["layout_ok"] and kw["permission_ok"] and not kw["quarantined"],
                      f"AUTO granted wrongly: {caps} {support} {kw}")
                if L.SYNTHETIC_INPUT in fs and not L.AUTO_REQUIRES <= fs:
                    T(m != "AUTO", "synthetic input without rollback must never be AUTO")
                if support == "UNKNOWN" or kw["quarantined"] or not kw["permission_ok"] or not kw["layout_ok"]:
                    T(m == "OFF", "unknown, quarantined, no permission or unsupported layout is OFF")
                if m != "OFF" and not kw["hook_ok"]:
                    T(m == "MANUAL_ONLY", "a lost hook can never leave AUTO active")
raises(ValueError, lambda: L.engine_mode({"TELEPATHY"}, "AUTO"), "unknown capability")
raises(ValueError, lambda: L.engine_mode(set(), "MAYBE"), "unknown status")
M1 = {L.READ_RANGE, L.REPLACE_RANGE, L.READBACK, L.ROLLBACK}
M1_NOROLL = {L.READ_RANGE, L.REPLACE_RANGE, L.READBACK}
M2 = {L.READ_RANGE, L.READBACK, L.SYNTHETIC_INPUT}
T(L.engine_mode(M1, "AUTO") == "AUTO" and L.engine_mode(M1_NOROLL, "AUTO") == "MANUAL_ONLY"
  and L.engine_mode(M2, "AUTO") == "MANUAL_ONLY" and L.engine_mode(M2, "MANUAL") == "MANUAL_ONLY"
  and L.engine_mode(M1, "MANUAL") == "MANUAL_ONLY" and L.engine_mode(M1, "UNKNOWN") == "OFF"
  and L.engine_mode({L.READ_RANGE}, "AUTO") == "OFF", "mode examples")

# ---- P8 outcome classification --------------------------------------------------------------------------
T(L.classify_outcome(False, "a", "b", None, False) == "ABORTED", "not started")
T(L.classify_outcome(True, "a", "b", "b", True) == "VERIFIED", "verified")
T(L.classify_outcome(True, "a", "b", "b", False) == "UNRECOVERED", "new text without a passed verification is not VERIFIED")
T(L.classify_outcome(True, "a", "b", "a", False) == "RESTORED", "restored")
T(L.classify_outcome(True, "a", "b", "c", False) == "UNRECOVERED", "other text")
T(L.classify_outcome(True, "a", "b", None, False) == "UNRECOVERED", "unreadable range")

# ---- P9 the replacement transaction against injected faults (the matrix of 13.2) ------------------------------
import os, vectors
V = vectors.build()                                                   # fails by itself when a hand-written prediction is wrong
if os.path.exists("vectors_out.json"):
    with open("vectors_out.json", encoding="utf-8") as fh:
        T(json.load(fh) == json.loads(vectors.render(V)), "vectors_out.json is not what vectors.py generates")
BASE, OLD, NEW = "Hello ghbdtn ", "ghbdtn", "привет"
T(len(V["tx"]) == 57, "fault matrix size")
for name, caps, text, faults, ahead, kw, outcome, reason, final, incident in V["tx"]:
    f = L.SimField(text, caps, {(k.split(":")[0], int(k.split(":")[1])): v for k, v in faults.items()})
    res = L.run_transaction(f, OLD, NEW, ahead, **kw)
    T((res.outcome, res.reason, f.text, res.incident, res.quarantine) == (outcome, reason, final, incident, incident), name)
    T(res.outcome in L.OUTCOMES, "outcome vocabulary")
    # invariants of every row (the safety matrix of 13.2):
    T(res.outcome != "VERIFIED" or f.text[6:12] == NEW, f"{name}: VERIFIED text")
    T(res.outcome != "RESTORED" or f.text[6:12] == OLD, f"{name}: RESTORED text")
    T(res.outcome != "ABORTED" or f.text.replace("x", "") == text.replace("x", ""), f"{name}: ABORTED must not change the field")
    T(res.incident == (res.outcome in ("RESTORED", "UNRECOVERED")), f"{name}: an incident only after the write began")
    T(f.user == [c for c in f.user if c == "x"], f"{name}: only the scripted user keys")
    if res.method == "M2" and res.outcome == "UNRECOVERED":          # the event-level guarantee holds, the field one does not
        T(f.sent == (14 if reason == "verify_failed" else 4) and f.user == ["x"] * len(f.user),
          f"{name}: G-EVENT: synthetic events are exactly those of the plan, user keys exactly once")

# Every fault of one phase, applied to every step, never ends in a silent VERIFIED with wrong text, and never
# crashes (an exhaustive sweep over single faults and pairs of faults, M1 with rollback).
FAULT_SLOTS = [("gate", 1, ["DENY", "raise"]), ("caret", 1, ["raise", "back", "forward"]), ("caret", 2, ["raise", "back", "forward", "forward2"]),
               ("read", 1, ["none", "stale", "raise", "user:x", "key"]), ("read", 2, ["none", "stale", "raise", "user:x", "key"]),
               ("read", 3, ["none", "stale", "raise"]),
               ("replace", 1, ["raise", "partial", "applied_error", "autocorrect", "ignored", "spill", "user:x", "key"]),
               ("replace", 2, ["raise", "partial", "applied_error", "autocorrect", "ignored", "spill", "user:x"])]
sweep = 0
for combo in itertools.chain(([s] for s in FAULT_SLOTS), itertools.combinations(FAULT_SLOTS, 2)):
    for picks in itertools.product(*[[(op, k, v) for v in vs] for op, k, vs in combo]):
        faults = {(op, k): v for op, k, v in picks}
        f = L.SimField(BASE, M1, faults)
        res = L.run_transaction(f, OLD, NEW)
        sweep += 1
        body = f.text.replace("x", "")
        T(res.outcome in L.OUTCOMES, "vocabulary")
        T(res.outcome != "VERIFIED" or body == "Hello привет ", f"sweep VERIFIED with wrong text {faults}")
        T(res.outcome != "RESTORED" or body == BASE, f"sweep RESTORED with wrong text {faults}")
        T(res.outcome != "ABORTED" or body == BASE, f"sweep ABORTED changed the field {faults}")
        T(res.outcome != "UNRECOVERED" or (res.incident and res.quarantine), f"sweep UNRECOVERED without incident {faults}")
        T(f.user == ["x"] * len(f.user), "user keys are exactly the scripted ones")
        T(body.count("привет") + body.count("ghbdtn") <= 1 or res.outcome == "UNRECOVERED", f"sweep duplicated text {faults}")
M1_SWEEP = sweep

# The same sweep for M2 (the hotkey path): events 1 to 14 are the plan (7 Backspace, 6 characters, the Space).
# Invariants: a user key seen before the first event means nothing is sent; whatever is written, the user's own
# keys are never lost or duplicated by the plan (G-EVENT) and a wrong text is never VERIFIED.
M2_SLOTS = [("gate", 1, ["DENY", "raise"]), ("caret", 1, ["raise", "back", "forward"]), ("caret", 2, ["raise", "back", "forward", "forward2"]),
            ("read", 1, ["none", "stale", "raise", "user:x", "key"]), ("read", 2, ["none", "stale", "raise", "user:x", "key"]),
            ("read", 3, ["none", "stale", "raise"])] + [("event", k, ["raise", "user:x", "drop", "key"]) for k in range(1, 15)]
for combo in itertools.chain(([s] for s in M2_SLOTS), itertools.combinations(M2_SLOTS[:6] + M2_SLOTS[6:9] + M2_SLOTS[-3:], 2)):
    for picks in itertools.product(*[[(op, k, v) for v in vs] for op, k, vs in combo]):
        faults = {(op, k): v for op, k, v in picks}
        f = L.SimField(BASE, M2, faults)
        res = L.run_transaction(f, OLD, NEW, "", mode="MANUAL_ONLY")
        sweep += 1
        body = f.text.replace("x", "")
        T(res.outcome in L.OUTCOMES, "M2 vocabulary")
        T(res.outcome != "VERIFIED" or body == "Hello привет ", f"M2 sweep VERIFIED with wrong text {faults}")
        T(res.outcome != "ABORTED" or (f.sent == 0 and body == BASE), f"M2 sweep ABORTED wrote something {faults}")
        T(res.outcome != "UNRECOVERED" or (res.incident and res.quarantine), f"M2 sweep UNRECOVERED without incident {faults}")
        T(f.sent in (0, 14) or any(k == "event" for (k, _) in faults) or res.outcome == "UNRECOVERED", f"M2 sweep partial plan {faults}")
        T(f.user == ["x"] * len(f.user), "M2 user keys are exactly the scripted ones")
        if faults.get(("read", 1)) in ("user:x", "key"):         # the key came before the first event: nothing may be sent
            T(f.sent == 0 and res.outcome == "ABORTED", f"M2 sweep: key before the write {faults}")
T((M1_SWEEP, sweep) == (621, 1665), f"sweep size {M1_SWEEP} / {sweep}")

# ---- P10 engine: undo snapshot lifecycle, modes, outcomes, stream gap ---------------------------------------
scorer = lambda ids: [-3, 9, -2]
LEX = {"en": {"hello"}, "ru": {"привет"}}


def feed(e, text, lay, t0, then_space=True):
    d = None
    for i, k in enumerate(L.keys_from_text(text, lay)):
        e.on_event(L.Event("key", k, lay, t0 + i))
    if then_space:
        d = e.on_event(L.Event("space", None, lay, t0 + len(text)))
    return d


e = L.Engine(L.example_cal(), scorer, LEX)
d = feed(e, "ghbdtn", "en", 1000)
T(d.action == "CONVERT" and e.snapshot is not None, "convert makes one snapshot")
T(e.snapshot.layout == "en" and e.snapshot.direction == "en2ru" and e.snapshot.typed == "ghbdtn", "snapshot content")
T(e.undo(2000) == "ghbdtn", "undo returns the typed text")
T(("en2ru", "ghbdtn") in e.exceptions and e.credit == 0 and e.cool_words == 3 and e.snapshot is None,
  "undo: exception, credit, cool-down, snapshot destroyed")
T(e.undo(2100) is None, "a second undo does nothing")
d = feed(e, "ghbdtn", "en", 3000)
T(d.action == "KEEP" and d.reason == "cooldown", "cool-down suppresses the correction")
# caps lock keys are restored exactly
e = L.Engine(L.example_cal(), scorer, LEX)
for i, k in enumerate(L.keys_from_text("ghbdtn", "en")):
    e.on_event(L.Event("key", L.Key(k.id, False, True), "en", i))
d = e.on_event(L.Event("space", None, "en", 10))
T(d.action == "CONVERT" and e.undo(20) == "GHBDTN", "undo with Caps Lock restores the typed capitals")
# russian to english
e = L.Engine(L.example_cal(), lambda ids: [9, -3, -2], LEX)
d = feed(e, "руддщ", "ru", 0)
T(d.action == "CONVERT" and d.replacement == "hello" and e.undo(5) == "руддщ", "ru2en undo")
# expiry: 10 s and 100 characters
for dt, alive in ((10_000, True), (10_001, False)):
    e = L.Engine(L.example_cal(), scorer, LEX); feed(e, "ghbdtn", "en", 1000)
    e.tick(1006 + dt)
    T((e.snapshot is not None) == alive, f"expiry at {dt} ms")
for n_after, alive in ((100, True), (101, False)):
    e = L.Engine(L.example_cal(), scorer, LEX); feed(e, "ghbdtn", "en", 1000)
    for i in range(n_after):
        e.on_event(L.Event("key", L.Key(i % 47), "en", 1010 + i))
    T((e.snapshot is not None) == alive, f"{n_after} characters after the replacement")
# everything that must destroy it
for what, act in {
    "break": lambda e: e.on_event(L.Event("break")),
    "layout change": lambda e: e.on_event(L.Event("layout", None, "ru")),
    "gap": lambda e: e.on_event(L.Event("gap")),
    "gate DENY": lambda e: e.set_gate("DENY"),
    "gate UNKNOWN": lambda e: e.set_gate("UNKNOWN"),
    "mode MANUAL_ONLY": lambda e: e.set_mode("MANUAL_ONLY"),
    "mode OFF": lambda e: e.set_mode("OFF"),
    "backspace before the word": lambda e: e.on_event(L.Event("backspace")),
    "outcome RESTORED": lambda e: e.on_outcome("RESTORED"),
    "outcome UNRECOVERED": lambda e: e.on_outcome("UNRECOVERED"),
    "outcome ABORTED": lambda e: e.on_outcome("ABORTED"),
}.items():
    e = L.Engine(L.example_cal(), scorer, LEX); feed(e, "ghbdtn", "en", 1000)
    T(e.snapshot is not None, "setup " + what)
    act(e)
    T(e.snapshot is None and e.undo(1100) is None, "the snapshot must not survive: " + what)
e = L.Engine(L.example_cal(), scorer, LEX); feed(e, "ghbdtn", "en", 1000)
e.on_outcome("VERIFIED")
T(e.snapshot is not None and e.credit == 3, "a verified replacement keeps snapshot and credit")
e.on_event(L.Event("space", None, "en", 1500))                       # an empty run: nothing happens, the snapshot lives on
T(e.snapshot is not None, "a Space with no word keeps the snapshot")
feed(e, "ytdtyj", "en", 1600)                                         # a second conversion replaces the first snapshot
T(e.snapshot is None or e.snapshot.typed != "ghbdtn", "one snapshot only")
raises(ValueError, lambda: e.on_outcome("MAYBE"), "outcome vocabulary")
# modes
e = L.Engine(L.example_cal(), scorer, LEX); e.set_mode("MANUAL_ONLY")
T(feed(e, "ghbdtn", "en", 0) is None and e.snapshot is None, "MANUAL_ONLY never decides")
e.on_event(L.Event("key", L.Key(5), "en", 0))
T(e.run == [] and e.snapshot is None, "MANUAL_ONLY records nothing (13.5)")
e.set_mode("OFF"); e.on_event(L.Event("key", L.Key(5), "en", 0))
T(e.run == [], "OFF records nothing")
e.set_mode("AUTO")
T(feed(e, "ghbdtn", "en", 0).action == "CONVERT", "AUTO decides again")
# a gap drops the interrupted word, whatever follows
e = L.Engine(L.example_cal(), scorer, LEX)
for k in L.keys_from_text("ghb", "en"):
    e.on_event(L.Event("key", k, "en", 0))
e.on_event(L.Event("gap"))
for k in L.keys_from_text("dtn", "en"):
    e.on_event(L.Event("key", k, "en", 1))
T(e.on_event(L.Event("space", None, "en", 2)) is None, "the tail of an interrupted word is ignored")
T(feed(e, "ghbdtn", "en", 10).action == "CONVERT", "the next word is decided normally")
# scorer fails closed
for bad in ([nan, 0, 0], [inf, 0, 0], [1, 2], "abc", [None, 1, 2]):
    e = L.Engine(L.example_cal(), lambda ids, b=bad: b, LEX)
    dd = feed(e, "ghbdtn", "en", 0)
    T(dd.action == "KEEP" and dd.reason == "scorer_invalid", f"scorer output {bad!r} fails closed")

# ---- P11 layout identity ---------------------------------------------------------------------------------
en_e, ru_e = L.table_entries("en"), L.table_entries("ru")
T(L.identify_layout(en_e) == "en" and L.identify_layout(ru_e) == "ru", "supported layouts are recognised")
T(len(set(L.SUPPORTED_FINGERPRINTS)) == 2, "two distinct fingerprints")
for lay, ent in (("en", en_e), ("ru", ru_e)):
    for i in range(94):                                               # any single wrong entry means: not supported
        alt = list(ent); alt[i] = "\x00" if ent[i] != "\x00" else "a"
        T(L.identify_layout(alt) is None, f"{lay} entry {i} changed")
        alt[i] = ent[i] + "́"
        T(L.identify_layout(alt) is None, f"{lay} entry {i} gets a combining mark")
T(L.identify_layout(en_e[1:] + en_e[:1]) is None, "rotated table")
swap = list(ru_e); swap[2 * 0], swap[2 * 0 + 1] = swap[1], swap[0]
T(L.identify_layout(swap) is None, "shift states swapped")
# a Russian layout that differs from the supported one in the punctuation row (the typewriter style)
typew = list(ru_e); typew[2 * 4 + 1] = "$"
T(L.identify_layout(typew) is None, "another Russian variant is not supported")
raises(ValueError, lambda: L.layout_fingerprint(en_e[:-1]), "93 entries")
raises(ValueError, lambda: L.layout_fingerprint(en_e[:-1] + ["a\nb"]), "an entry with a line feed")
T(L.layout_fingerprint(en_e) == "7b35aa964f372005ccef6558a1049dce2a550d772939090e3dba51302c0f3078", "fingerprint en is stable")
T(L.layout_fingerprint(ru_e) == "3aced72548d6d46da951f06cdbed60aac96487c338ad7b805e95402eb37204de", "fingerprint ru is stable")

# ---- P12 hook health -------------------------------------------------------------------------------------
h = L.HookHealth(canary=True)
for t in (0, 100, 200):
    h.raw_key(t, ("a", t)); h.hook_key(t + 5, ("a", t))
T(h.check(250) and h.ok and not h.take_gap(), "healthy stream")
h.raw_key(1000, "x")                                                  # the hook does not see this key
T(h.check(1000 + L.HookHealth.CANARY_MS) and h.ok, "exactly at the limit is still healthy")
T(not h.check(1000 + L.HookHealth.CANARY_MS + 1) and h.take_gap() and not h.take_gap(), "canary loses the hook, one gap")
T(h.reason == "canary_missing", "a physical key the hook never reported")
T(L.engine_mode(M1, "AUTO", hook_ok=h.ok) == "MANUAL_ONLY", "a lost hook limits the mode")
for t in (2000, 2100, 2200, 2300):                                    # keys typed while the hook is still not installed again
    h.raw_key(t, t); h.check(t + 10)
T(not h.ok, "still lost")
h.reinstalled()
for i in range(L.HookHealth.REARM_PAIRS - 1):
    h.raw_key(3000 + i, i); h.hook_key(3000 + i, i)
T(not h.ok, "re-arm needs the full number of pairs")
h.raw_key(3100, 9); h.hook_key(3100, 9)
T(h.ok and h.reason is None, "re-armed after three matched pairs")
m = L.HookHealth(canary=False)                                        # macOS
T(m.ok, "mac healthy")
m.tap_disabled("timeout")
T(not m.ok and m.take_gap() and m.reason == "tap_timeout", "tapDisabledByTimeout")
m.reinstalled()
T(m.ok, "tap enabled again")
m.tap_disabled("user_input"); T(not m.ok and m.reason == "tap_user_input", "tapDisabledByUserInput")
m.reinstalled(); m.poll(False); T(not m.ok and m.reason == "poll", "poll finds the tap disabled")
raises(ValueError, lambda: m.tap_disabled("other"), "unknown reason")
e = L.Engine(L.example_cal(), scorer, LEX)                            # the runtime sends the gap to the engine
for k in L.keys_from_text("ghb", "en"):
    e.on_event(L.Event("key", k, "en", 0))
h2 = L.HookHealth(canary=False); h2.tap_disabled("timeout")
if h2.take_gap():
    e.on_event(L.Event("gap"))
T(e.run == [] and e.skip, "the runtime delivers the gap")

# ---- P13 fuzz: invariants of the event state machine --------------------------------------------------------
fz = random.Random(7)
LK = sorted(L.LETTER_KEYS)
conv = checked_undo = 0
for rnd in range(max(1, N // 20_000)):
    e = L.Engine(L.example_cal(), lambda ids: [fz.uniform(-4, 4), fz.uniform(0, 14), fz.uniform(-4, 4)], LEX)
    now = 0
    for step in range(20_000):
        now += fz.choice((1, 5, 50, 700, 4000))
        x = fz.random()
        evs = []
        if x < .45:                                                     # a whole word on one layout, usually ended by Space
            lay = fz.choice(("en", "ru"))
            evs = [L.Event("key", L.Key(fz.choice(LK), fz.random() < .2, fz.random() < .05), lay, now) for _ in range(fz.randrange(2, 9))]
            if fz.random() < .8:
                evs.append(L.Event("space", None, lay if fz.random() < .95 else L.OTHER_LAYOUT[lay], now))
        elif x < .55:
            evs = [L.Event("key", L.Key(fz.randrange(47), fz.random() < .3), fz.choice(("en", "ru")), now)]
        elif x < .65:
            evs = [L.Event("space", None, fz.choice(("en", "ru")), now)]
        elif x < .72:
            evs = [L.Event("backspace", None, None, now)]
        elif x < .78:
            evs = [L.Event(fz.choice(("break", "gap")), None, None, now)]
        elif x < .80:
            evs = [L.Event("layout", None, fz.choice(("en", "ru")), now)]
        elif x < .90:
            ops = [lambda: e.set_gate(fz.choice(("ALLOW", "ALLOW", "ALLOW", "ALLOW", "ALLOW", "DENY", "UNKNOWN"))),
                   lambda: e.set_mode(fz.choice(("AUTO", "AUTO", "AUTO", "AUTO", "AUTO", "MANUAL_ONLY", "OFF"))),
                   lambda: e.on_outcome(fz.choice(L.OUTCOMES)),
                   lambda: e.tick(now)]
            fz.choice(ops)()
        else:
            evs = [L.Event("space", None, "en", now)]
        for ev in evs:
            d = e.on_event(ev)
            if d is not None and d.action == "CONVERT":
                conv += 1
                T(e.gate == "ALLOW" and e.mode == "AUTO", "CONVERT outside AUTO or gate ALLOW")
                T(e.snapshot is not None and len(d.replacement) == len(e.snapshot.keys), "a key was lost or duplicated")
                T(len(e.snapshot.keys) <= L.MAX_BUF, "snapshot size")
            if ev.kind in ("break", "layout", "gap"):
                T(e.snapshot is None and e.run == [], f"{ev.kind} must leave no buffer and no snapshot")
        T(len(e.run) <= L.MAX_BUF, "buffer bound")
        T(e.gate == "ALLOW" or (e.run == [] and e.snapshot is None), "no state under DENY or UNKNOWN")
        T(e.mode == "AUTO" or (e.run == [] and e.snapshot is None), "no state outside AUTO (13.5)")
        s = e.snapshot
        if s is not None:
            T(s.after <= L.UNDO_MAX_CHARS, "snapshot character bound")
            if fz.random() < .3:
                e.tick(now)
                if e.snapshot is not None:
                    T(now - e.snapshot.created_ms <= L.UNDO_WINDOW_MS, "snapshot age bound after tick")
                    keys, lay = e.snapshot.keys, e.snapshot.layout
                    txt = e.undo(now)
                    T(txt == L.render(keys, lay) and e.snapshot is None,
                      "undo returns the recorded keys rendered with the recorded layout")
                    checked_undo += 1
T(conv > N // 4000 and checked_undo > N // 20000, f"fuzz coverage: {conv} conversions, {checked_undo} undos")
```

**`conformance.py`, part 3 of 3 (P14: every threshold and format rule is tested on both sides of its edge; the closing line).**

```python
# ---- P14 boundaries, defaults and format errors: every threshold is tested on both sides of its edge ---------
# (written against the survivors of the mutation run, audit line L3: a constant that nothing pins is a defect)
T([L.bucket(n) for n in (0, 1, 2, 3, 4, 5, 7, 8, 20)] == [None, None, "2", "3-4", "3-4", "5-7", "5-7", "8+", "8+"], "bucket edges")


def accepts(path, value):
    try:
        L.check_calibration_package(mutated(path, value))
        return True
    except L.CalibrationError:
        return False


# closed and open bounds of every numeric field of the calibration package
T(accepts(["temperature", "network"], 20.0) and accepts(["temperature", "network"], 15.0) and accepts(["temperature", "ngram"], 1e-9),
  "T: 1e-9, 15 and 20 are valid")
T(not accepts(["temperature", "network"], 20.001) and not accepts(["temperature", "ngram"], 21.0), "T above 20 is refused")
T(accepts(["o_lat"], 0.6) and accepts(["o_lat"], 0.999999) and accepts(["o_lat"], 1e-9), "o_lat valid values")
T(not accepts(["o_lat"], 0.0) and not accepts(["o_lat"], 1.0) and not accepts(["o_lat"], -0.1), "o_lat 0 and 1 are refused")
T(not accepts(["o_lat"], 1.5) and not accepts(["o_lat"], 2.0), "o_lat above 1 is refused")


def accepts_counts(counts):
    c = copy.deepcopy(ok_cal)
    c["pi_train_counts"] = counts
    c["pi_train"] = L.pi_from_counts(counts)
    try:
        L.check_calibration_package(c)
        return True
    except L.CalibrationError:
        return False


T(accepts_counts([60000, 30000, 10000]) and accepts_counts([1, 1, 1]) and accepts_counts([98, 1, 1]),
  "a class share above one half is a valid training mix")
T(accepts(["w", "en", "default"], 0.0005) and not accepts(["w", "en", "default"], 0.0004), "w lower edge is closed")
T(accepts(["w", "ru", "after_switch"], 0.5) and not accepts(["w", "ru", "after_switch"], 0.51), "w upper edge is closed")
T(accepts(["w", "en", "run"], 0.3) and not accepts(["w", "en", "run"], 0.3000001), "w[run] cap is 0.3, inclusive")
T(accepts(["lambda_nats", "network", "en2ru", "3-4"], 4.0) and not accepts(["lambda_nats", "network", "en2ru", "3-4"], 3.99),
  "lambda lower edge 4 nats is closed")
T(accepts(["lambda_nats", "ngram", "ru2en", "8+"], 16.0) and accepts(["lambda_nats", "ngram", "ru2en", "8+"], 9.0)
  and not accepts(["lambda_nats", "ngram", "ru2en", "8+"], 16.01), "lambda upper edge 16 nats is closed")
raises(L.CalibrationError, lambda: L.check_calibration_package(mutated(["pi_train"], ok_cal["pi_train"] + [1e-12])), "pi_train too long")
p0, p1, p2 = ok_cal["pi_train"]
T(not accepts(["pi_train"], [p0 + 1.5e-9, p1 - 1.5e-9, p2]), "pi_train element 1.5e-9 off its count is refused")
T(accepts(["pi_train"], [p0 + 0.8e-9, p1 - 0.8e-9, p2]), "pi_train element 0.8e-9 off its count is accepted")
T(not accepts(["pi_train"], [p0 + 0.4e-9, p1 + 0.4e-9, p2 + 0.4e-9]), "pi_train sum 1.2e-9 off 1 is refused")
T(accepts(["pi_train"], [p0 + 0.3e-9, p1 + 0.3e-9, p2 + 0.3e-9]), "pi_train sum 0.9e-9 off 1 is accepted")

# defaults of decide(): the two-key rule is closed unless a run is active
KEYS2 = L.keys_from_text("yf", "en")                                   # 'на' on the Russian layout, in the allow list
cal0 = L.example_cal()
T(L.decide(KEYS2, "en", cal0, scorer).reason == "two_key_rule", "two keys without a run: kept")
T(L.decide(KEYS2, "en", cal0, scorer, run_active=True).reason == "two_key_allow_list", "two keys inside a run: converted")
# the scorer sees BOS ... EOS
seen = []
L.decide(L.keys_from_text("ghbdtn", "en"), "en", cal0, lambda ids: seen.append(list(ids)) or [-3, 9, -2])
T(seen and seen[0][0] == L.BOS and seen[0][-1] == L.EOS and len(seen[0]) == 8, "the scorer input is BOS, 6 key tokens, EOS")
# a margin of exactly zero converts (the rule is s >= lambda)
G = L.keys_from_text("ghbdtn", "en")
s_exact = L.score([-3, 9, -2], "en", cal0, cal0["w"]["en"]["default"], "network")
cal_edge = copy.deepcopy(cal0); cal_edge["lambda_nats"]["network"]["en2ru"]["5-7"] = s_exact
T(L.decide(G, "en", cal_edge, scorer).action == "CONVERT" and L.decide(G, "en", cal_edge, scorer).margin == 0.0, "margin 0 converts")
cal_edge["lambda_nats"]["network"]["en2ru"]["5-7"] = s_exact + 1e-9
T(L.decide(G, "en", cal_edge, scorer).action == "KEEP", "margin -1e-9 abstains")


def word(e, text, lay, ts):
    for k in L.keys_from_text(text, lay):
        e.on_event(L.Event("key", k, lay, ts))
    return e.on_event(L.Event("space", None, lay, ts))


# buffer bound: 64 keys are decided, the 65th makes the word an overflow
e = L.Engine(L.example_cal(), scorer, LEX)
for _ in range(64):
    e.on_event(L.Event("key", L.Key(11), "en", 0))
T(len(e.run) == 64 and not e.overflow and e.on_event(L.Event("space", None, "en", 1)).reason != "overflow", "64 keys")
for _ in range(65):
    e.on_event(L.Event("key", L.Key(11), "en", 2))
T(len(e.run) == 64 and e.overflow and e.on_event(L.Event("space", None, "en", 3)).reason == "overflow", "65 keys")
# the lexicon is used when it is given
e = L.Engine(L.example_cal(), scorer, LEX)
T(word(e, "hello", "en", 0).reason == "lexicon_active", "the lexicon of the engine is consulted")
# evidence for the active language ends the run credit
e = L.Engine(L.example_cal(), scorer, LEX)
T(word(e, "ghbdtn", "en", 0).action == "CONVERT" and e.credit == 3, "credit after a conversion")
T(word(e, "hello", "en", 10).reason == "lexicon_active" and e.credit == 0, "a word of the active language resets the credit")
# two keys: the allow list opens only while the run credit lives
e = L.Engine(L.example_cal(), scorer, LEX)
T(word(e, "yf", "en", 0).reason == "two_key_rule", "no credit: two keys are kept")
word(e, "ghbdtn", "en", 10)
T(word(e, "yf", "en", 20).reason == "two_key_allow_list", "credit: two keys are converted")
# cool-down: three words and 10 s, each edge
e = L.Engine(L.example_cal(), scorer, LEX)
T(word(e, "ghbdtn", "en", 1000).action == "CONVERT" and e.undo(2000) == "ghbdtn", "setup cool-down")
T([word(e, "ytdtyj", "en", 20_000 + 100 * i).reason for i in range(3)] == ["cooldown"] * 3, "three words are suppressed")
T(word(e, "ytdtyj", "en", 20_300).action == "CONVERT", "the fourth word is decided")
for ts, reason in ((11_999, "cooldown"), (12_000, "score_above_threshold")):
    e = L.Engine(L.example_cal(), scorer, LEX)
    word(e, "ghbdtn", "en", 1000); e.undo(2000); e.cool_words = 0
    T(word(e, "ytdtyj", "en", ts).reason == reason, f"cool-down time edge at {ts} ms")
# the clock of every event expires the snapshot
for dt, alive in ((10_000, True), (10_001, False)):
    e = L.Engine(L.example_cal(), scorer, LEX); word(e, "ghbdtn", "en", 1000)
    e.on_event(L.Event("key", L.Key(5), "en", 1000 + dt))
    T((e.snapshot is not None) == alive, f"snapshot age {dt} ms seen by an ordinary event")
# a layout change inside a word, and the tail that follows
e = L.Engine(L.example_cal(), scorer, LEX)
for k in L.keys_from_text("gh", "en"):
    e.on_event(L.Event("key", k, "en", 0))
e.on_event(L.Event("key", L.Key(3), "ru", 1))
T(e.run == [] and e.skip, "a layout change inside a word empties the buffer and skips the rest")
for k in L.keys_from_text("bdtn", "en"):
    e.on_event(L.Event("key", k, "en", 2))
T(e.run == [], "the tail of a dropped word is not recorded")
T(e.on_event(L.Event("space", None, "en", 3)) is None and not e.skip, "the Space ends the skipped word")
e.on_event(L.Event("layout", None, "ru"))
e.on_event(L.Event("key", L.Key(5), "en", 4)); e.on_event(L.Event("break"))
T(not e.skip and e.credit == 0, "a break clears the skip")
T(word(e, "ghbdtn", "en", 5) is not None, "the word after a break is decided (not skipped)")
# a manual layout change marks the next word, once
e = L.Engine(L.example_cal(), lambda ids: [9, -3, -2], LEX)
e.on_event(L.Event("layout", None, "ru"))
T(e.after_switch, "layout event arms after_switch")
d = word(e, "руддщ", "ru", 10)
ref = L.decide(L.keys_from_text("руддщ", "ru"), "ru", L.example_cal(), lambda ids: [9, -3, -2], "after_switch", False, e.exceptions, LEX)
dflt = L.decide(L.keys_from_text("руддщ", "ru"), "ru", L.example_cal(), lambda ids: [9, -3, -2], "default", False, e.exceptions, LEX)
T(d.margin == ref.margin and ref.margin != dflt.margin and not e.after_switch, "after_switch is used once")
# manual conversion: direction rule
T(L.manual_convert("а")[0] == "ru2en" and L.manual_convert("я")[0] == "ru2en" and L.manual_convert("ё")[0] == "ru2en", "a, ya, yo")
T(L.manual_convert("яa")[0] == "en2ru", "a tie goes English to Russian")
T(L.manual_convert("яяabc")[0] == "en2ru" and L.manual_convert("яяабc")[0] == "ru2en", "letter counts decide")
T(L.manual_convert("12 !") == (None, "12 !"), "no letters: no direction")

# EV-1 edges (each condition is tested alone)
fc = lambda n: [("u%d" % i, "d%d" % i) for i in range(n)]
T(L.ev1_pass([], 100_000, 20, 100), "EV-1 passes at its minimum sizes")
T(not L.ev1_pass([], 99_999, 20, 100) and not L.ev1_pass([], 100_000, 19, 100) and not L.ev1_pass([], 100_000, 20, 99), "each size limit")
T(L.ev1_pass(fc(12), 250_000, 30, 200) and not L.ev1_pass(fc(13), 250_000, 30, 200), "point estimate edge 4.8e-5")
T(L.ev1_bound(fc(12), 250_000) <= 1e-4 < L.ev1_bound(fc(30), 250_000), "bound is monotone in the number of clusters")
big = [("u1", "d1")] * 10 + fc(1)[1:]                                   # one cluster of ten: the bound is ten times larger
T(L.ev1_bound(big, 1_000_000) == L.poisson_upper(1) * 10 / 1_000_000, "cluster size multiplies the bound")
for k in range(0, 31):                                                  # the exact Poisson limit, checked by its definition
    mu = L.poisson_upper(k)
    T(abs(sum(math.exp(-mu + i * math.log(mu) - math.lgamma(i + 1)) for i in range(k + 1)) - 0.05) < 1e-9, f"Poisson limit k={k}")
T(abs(L.poisson_upper(0) - (-math.log(0.05))) < 1e-9, "rule of three, exact")

# Witten-Bell pruning: only orders 1 and 2, only counts below min_count
rows_p = [[L.BOS, 5, 6, L.EOS]] * 2 + [[L.BOS, 7, 8, L.EOS]]
pr = L.WittenBell(min_count=2).fit(rows_p)
T(pr.cnt[0][()][5] == 2 and pr.cnt[0][()][7] == 1, "order 0 is never pruned")
T((L.BOS,) in pr.cnt[1] and pr.cnt[1][(L.BOS,)] == {5: 2}, "order 1: the count of exactly min_count stays, 1 is pruned")
T((L.BOS, 7) not in pr.cnt[2] and pr.cnt[2][(L.BOS, 5)] == {6: 2}, "order 2 pruned")
T(L.WittenBell().fit(rows_p).cnt[1][(L.BOS,)] == {5: 2, 7: 1}, "min_count 1 prunes nothing")

# binary files: round trips with distinct values, and every damage is a FormatError
lp = [-1.5, -2.25, -3.125]
msb = [L.WittenBell().fit(rows[i::3]) for i in range(3)]
bb = L.lfb_pack(msb, lp)
T(L.lfb_load(bb)["log_prior"] == lp, "LFB1 log priors survive")
lex_in = {"lex_en": ["hello", "World"], "lex_ru": ["привет"], "acr_en": ["usb"], "acr_ru": ["ржд"], "exc_en2ru": ["ghbdtn"], "exc_ru2en": ["руддщ"]}
lb = L.lfl_pack(lex_in)
lt = L.lfl_load(lb)
T(all(w.casefold() in lt[n] for n, ws in lex_in.items() for w in ws) and "hello" not in lt["lex_ru"], "LFL1 round trip")
TAGS = {"lex_en": 1, "lex_ru": 2, "acr_en": 3, "acr_ru": 4, "exc_en2ru": 5, "exc_ru2en": 6}
T(L.LEX_TAGS == TAGS, "tag numbers are part of the format")


def fnv(data):                                                          # an independent FNV-1a, 64 bit
    h = 0xCBF29CE484222325
    for x in data:
        h = ((h ^ x) * 0x100000001B3) % (1 << 64)
    return h


T(all(L.lex_key(t, "слово") == fnv(bytes([0xE0 + t]) + "слово".encode()) for t in TAGS.values()), "lex_key = FNV-1a(tag byte + UTF-8)")
T(L.fnv1a64(b"") == 0xCBF29CE484222325 and L.fnv1a64(b"a") == 0xAF63DC4C8601EC8C, "FNV-1a test vectors")
for name, blob, loader in (("LFB1", bb, L.lfb_load), ("LFL1", lb, L.lfl_load), ("LFW1", tw, L.lfw_load)):
    raises(L.FormatError, lambda b=blob, f=loader: f(b"XXXX" + b[4:]), name + " wrong magic")
    raises(L.FormatError, lambda b=blob, f=loader: f(b + b"\0"), name + " trailing byte")
    raises(L.FormatError, lambda b=blob, f=loader: f(b[:-1]), name + " truncated by one byte")
    raises(L.FormatError, lambda b=blob, f=loader: f(b[:9]), name + " truncated header")
    raises(L.FormatError, lambda f=loader: f(b""), name + " empty")
_old_ctx = L.ctx_key
L.ctx_key = lambda k, c: 1                                              # force a 64-bit collision of contexts
try:
    raises(L.FormatError, lambda: L.lfb_pack(msb, lp), "LFB1 hash collision is refused")
finally:
    L.ctx_key = _old_ctx

# the replacement transaction: edges of the typed-ahead window, a word at the field start, M2 success, no silent VERIFIED
for ahead, outcome, final in (("abc", "VERIFIED", "Hello привет abc"), ("abcd", "ABORTED", "Hello ghbdtn abcd")):
    f = L.SimField("Hello ghbdtn " + ahead, M1)
    r = L.run_transaction(f, OLD, NEW, ahead)
    T((r.outcome, f.text) == (outcome, final), f"typed ahead {ahead!r}")
f = L.SimField("Hello ghbdtn a", M1)
T(L.run_transaction(f, OLD, NEW, "ab").outcome == "VERIFIED" and f.text == "Hello привет a", "the engine recorded more than the field has")
f = L.SimField("ghbdtn ", M1)
T(L.run_transaction(f, OLD, NEW).outcome == "VERIFIED" and f.text == "привет ", "a word at offset 0")
f = L.SimField("Hello ghbdtn ", M2)
r = L.run_transaction(f, OLD, NEW, "", mode="MANUAL_ONLY")
T((r.outcome, r.method, f.text) == ("VERIFIED", "M2", "Hello привет "), "M2 on the hotkey path verifies")
f = L.SimField("Hello ghbdtn  tail", M2)
f.pos = len("Hello ghbdtn ")
r = L.run_transaction(f, OLD, NEW, "", mode="MANUAL_ONLY")
T((r.outcome, f.text) == ("VERIFIED", "Hello привет  tail"), "M2 inside a text: the verification range ends at the Space, not beyond it")
f = L.SimField("Hello ghbdtn ", M1_NOROLL, {("caret", 2): "back"})
r = L.run_transaction(f, OLD, NEW, "", mode="MANUAL_ONLY")
T((r.outcome, r.incident, r.quarantine, f.text) == ("UNRECOVERED", True, True, "Hello привет "),
  "right text with a wrong caret and no rollback is not VERIFIED")
f = L.SimField("", M2); f.send([("bs", ""), ("ch", "a"), ("ch", "b")])
T((f.text, f.pos) == ("ab", 2), "the test double: backspace at 0 is a no-op, insertion moves the caret by one")

# Q-2 of plan 1.2: SendInput facts. A physically pressed modifier aborts M2 before anything is written;
# a silently dropped batch (UIPI) leaves the typed text (RESTORED); a partly delivered batch is UNRECOVERED.
f = L.SimField("Hello ghbdtn ", M2); f.modifiers = True
r = L.run_transaction(f, OLD, NEW, "", mode="MANUAL_ONLY")
T((r.outcome, r.reason, f.text, f.sent) == ("ABORTED", "modifier_down", "Hello ghbdtn ", 0), "M2 with a modifier down writes nothing")
f = L.SimField("Hello ghbdtn ", M1); f.modifiers = True
T(L.run_transaction(f, OLD, NEW).outcome == "VERIFIED", "a pressed modifier is irrelevant to M1")
f = L.SimField("Hello ghbdtn ", M2, {("event", k): "drop" for k in range(1, 2 * len(OLD) + 3)})
r = L.run_transaction(f, OLD, NEW, "", mode="MANUAL_ONLY")
T((r.outcome, r.incident, r.quarantine, f.text) == ("RESTORED", True, True, "Hello ghbdtn "), "UIPI drops the whole batch: the field is unchanged")
f = L.SimField("Hello ghbdtn ", M2, {("event", len(OLD) + 2): "drop"})
r = L.run_transaction(f, OLD, NEW, "", mode="MANUAL_ONLY")
T((r.outcome, r.incident, r.quarantine) == ("UNRECOVERED", True, True), "a partly delivered batch is UNRECOVERED and quarantined")

# R-1 and R-2 of plan 1.3. M2 deletes by count, so a user key that arrives after the read (or while it runs) makes the
# plan wrong: the last look before the first synthetic event aborts and nothing is written. The race that remains
# (a key between that look and the first event) is a field-level fact, not an event-level one, and ends UNRECOVERED.
f = L.SimField("Hello ghbdtn ", M2, {("read", 1): "user:x"})
r = L.run_transaction(f, OLD, NEW, "", mode="MANUAL_ONLY")
T((r.outcome, r.reason, f.text, f.sent, r.incident) == ("ABORTED", "typed_ahead", "Hello ghbdtn x", 0, False), "M2: a key during the read aborts before anything is sent")
f = L.SimField("Hello ghbdtn ", M2, {("event", 1): "user:x"})
r = L.run_transaction(f, OLD, NEW, "", mode="MANUAL_ONLY")
T((r.outcome, r.reason, f.sent, f.user, r.incident, r.quarantine) == ("UNRECOVERED", "verify_failed", 14, ["x"], True, True),
  "M2: a key after the last look is the residual race: UNRECOVERED, quarantine, the plan is still sent exactly once")
f = L.SimField("Hello ghbdtn ", M1, {("caret", 2): "forward"})
r = L.run_transaction(f, OLD, NEW)
T((r.outcome, r.reason, f.text, r.incident) == ("RESTORED", "verify_failed", "Hello ghbdtn ", True),
  "M1: a caret that moved forward although no user key came is a failure; the rollback restores the field")
f = L.SimField("Hello ghbdtn ", M1, {("read", 2): "user:x"})
r = L.run_transaction(f, OLD, NEW)
T((r.outcome, f.text, f.pos) == ("VERIFIED", "Hello привет x", 14), "M1: one user key may move the caret by one")
f = L.SimField("Hello ghbdtn ", M1, {("read", 2): "user:x", ("caret", 2): "forward"})
r = L.run_transaction(f, OLD, NEW)
T((r.outcome, r.reason) == ("RESTORED", "verify_failed"), "M1: one user key explains a caret one place forward, not two")
f = L.SimField("Hello ghbdtn ", M1, {("replace", 1): "spill"})
r = L.run_transaction(f, OLD, NEW)
T((r.outcome, r.reason, f.text, r.incident, r.quarantine) == ("UNRECOVERED", "verify_failed", "Hello ghbdtn?", True, True),
  "M1: damage to the Space after the range is seen by the whole-range read-back; the rollback cannot repair it")
f = L.SimField("Hello ghbdtn a", M1, {("replace", 1): "spill"})
r = L.run_transaction(f, OLD, NEW, "a")
T((r.outcome, f.text) == ("UNRECOVERED", "Hello ghbdtn?a"), "M1 with a typed-ahead key: the whole fragment is verified and rolled back")
f = L.SimField("Hello ghbdtn a", M1, {("replace", 1): "autocorrect"})
r = L.run_transaction(f, OLD, NEW, "a")
T((r.outcome, f.text) == ("RESTORED", "Hello ghbdtn a"), "M1 with a typed-ahead key: a restored fragment is RESTORED")
T(L.classify_outcome(True, "ab c", "xy c", "ab c", False) == "RESTORED" and L.classify_outcome(True, "ab c", "xy c", "ab?c", False) == "UNRECOVERED"
  and L.classify_outcome(True, "ab c", "xy c", "xy c", True) == "VERIFIED", "classification works on the whole fragment")
M2_RACE = []
for k in range(1, 15):                                                 # a user key before every synthetic event of M2
    f = L.SimField("Hello ghbdtn ", M2, {("event", k): "user:x"})
    r = L.run_transaction(f, OLD, NEW, "", mode="MANUAL_ONLY")
    T(f.sent == 14 and f.user == ["x"] and r.incident and r.quarantine and r.outcome in ("UNRECOVERED", "VERIFIED"), f"M2 race at event {k}")
    M2_RACE.append(r.outcome)
T(M2_RACE == ["UNRECOVERED"] * 14, "a user key anywhere inside the plan always ends UNRECOVERED, never a wrong VERIFIED")

# hook health: states cannot be re-armed by luck
h = L.HookHealth()
T(h.canary is True, "canary is the default")
h.raw_key(0, 0); h.check(10_000)                                      # lost
for t in (1, 2, 3, 4):
    h.raw_key(20_000 + t, t); h.hook_key(20_000 + t, t)
T(not h.ok, "matched pairs without a re-installed hook do not re-arm")
h.reinstalled()
for t in (1, 2):
    h.raw_key(30_000 + t, t); h.hook_key(30_000 + t, t)
h.tap_disabled("timeout")                                              # lost again before the re-arm finished
for t in (1, 2, 3):
    h.raw_key(40_000 + t, t); h.hook_key(40_000 + t, t)
T(not h.ok, "a second loss resets the re-arm: pairs count only after the next reinstall")
h.reinstalled()
for t in (1, 2):
    h.raw_key(50_000 + t, t); h.hook_key(50_000 + t, t)
h.reinstalled()                                                        # installed once more: the count starts again
h.raw_key(60_000, 0); h.hook_key(60_000, 0)
T(not h.ok, "reinstall resets the pair count")
for t in (1, 2):
    h.raw_key(70_000 + t, t); h.hook_key(70_000 + t, t)
T(h.ok, "three pairs after the last reinstall re-arm")

# R-3 of plan 1.3: the canary compares events, not counts. One lost key and one extra key must not cancel out.
A, B, C = ("scan", 0x1E, False), ("scan", 0x30, False), ("scan", 0x2E, False)
h = L.HookHealth()
h.raw_key(0, A); h.hook_key(3, A)                                      # healthy
h.raw_key(100, B)                                                      # the hook never reports B ...
h.hook_key(105, C)                                                     # ... and reports C, which the observer never saw
T(h.check(100 + h.CANARY_MS) and h.ok, "inside the window nothing is decided")
T(not h.check(100 + h.CANARY_MS + 1) and h.reason == "canary_missing" and h.take_gap(),
  "lost B and extra C: the counts are equal, the signatures are not; the older unmatched event names the reason")
h = L.HookHealth()
h.hook_key(0, C)                                                       # a hook key the observer never saw
T(h.check(300) and h.ok and not h.check(301) and h.reason == "canary_extra", "an extra hook key alone is a loss")
h = L.HookHealth()
h.hook_key(10, A); h.raw_key(12, A)                                    # the hook event may come first
h.raw_key(20, B); h.hook_key(22, B)
T(h.check(10_000) and h.ok and h.hook_only == [] and h.raw_only == [], "either order matches")
h.hook_key(30, C, injected=True)                                       # our own SendInput, or another program's
T(h.check(10_000) and h.ok and h.hook_only == [], "an injected event has no physical counterpart and is not compared")
h = L.HookHealth()
h.raw_key(0, A); h.raw_key(50, A); h.hook_key(55, A)                   # two physical presses, one reported
T(h.check(350) and not h.check(351) and h.reason == "canary_missing", "equal signatures are matched one to one; the second press is the unmatched one")
# Review of the code, P1: the watchdog timer may be late. A counterpart that arrives later than CANARY_MS must not
# hide the loss, whatever the order of arrival and whether or not check() has run in between.
M = L.HookHealth.CANARY_MS
h = L.HookHealth()
h.raw_key(0, A); h.hook_key(M, A)
T(h.ok and h.raw_only == [] and h.hook_only == [] and not h.take_gap(), "a counterpart exactly CANARY_MS later still meets the event")
h = L.HookHealth()
h.raw_key(0, A); h.hook_key(M + 1, A)
T(not h.ok and h.reason == "canary_missing" and h.take_gap() and not h.take_gap(), "raw first, hook one ms too late: lost at once, one gap")
h = L.HookHealth()
h.hook_key(0, A); h.raw_key(M + 1, A)
T(not h.ok and h.reason == "canary_extra" and h.take_gap(), "hook first, raw one ms too late: lost at once")
h = L.HookHealth()
h.raw_key(0, A); h.raw_key(M, B)
T(h.ok and h.raw_only == [(0, A), (M, B)], "a later event exactly CANARY_MS after the first does not expire it")
h = L.HookHealth()
h.raw_key(0, A); h.raw_key(M + 1, B)
T(not h.ok and h.reason == "canary_missing", "any later event of the same side shows that the first has expired")
h = L.HookHealth()
h.hook_key(1000, A); h.raw_key(600, A)                                 # the clocks disagree by 400 ms: not a pair
T(h.ok and h.raw_only == [(600, A)] and h.hook_only == [(1000, A)], "events more than CANARY_MS apart in either direction do not meet")
T(not h.check(M + 601) and h.reason == "canary_missing", "and the older one expires")
h = L.HookHealth()
h.raw_key(0, A); h.hook_key(M + 1, A)                                  # lost by a late counterpart ...
h.reinstalled()
for i in range(L.HookHealth.REARM_PAIRS):
    h.raw_key(5000 + i, ("scan", i)); h.hook_key(5000 + i, ("scan", i))
T(h.ok and h.reason is None, "... and re-armed in the normal way")
h = L.HookHealth(canary=False)
h.raw_key(0, A); h.hook_key(1, B)
T(h.check(10_000) and h.ok, "without a canary (macOS) nothing is compared")


# ---- P15 gaps that the mutation run on the final code showed (audit/L3_mutation_and_fuzz.md) ------------------
# Each check names the changed line that no earlier check could tell from the original.
zq = [0.0, 1.0, 3.0]
T(L.log_softmax(zq) == L.log_softmax(zq, 1.0) and abs(sum(math.exp(v) for v in L.log_softmax(zq)) - 1.0) < 1e-12,
  "log_softmax: the default temperature is 1")


def counts_refused(counts, shares):
    c = copy.deepcopy(ok_cal)
    c["pi_train_counts"], c["pi_train"] = counts, shares
    try:
        L.check_calibration_package(c)
    except L.CalibrationError:
        return True
    return False


n9 = 10 ** 9
T(counts_refused([0, 0, 0], [1 / 3] * 3), "counts 0, 0, 0 are a CalibrationError and not a division by zero")
T(counts_refused([0, 5, 5], [5e-10, 0.5, 0.5]), "a zero count is refused although its share is inside the tolerance of 1e-9")
T(counts_refused([10 ** 12, 1, 1], [1.0000000005, 1 / (10 ** 12 + 2), 1 / (10 ** 12 + 2)]),
  "a share above 1 is refused although it is inside the tolerance")
T(counts_refused([1, n9, n9], [0.0, n9 / (2 * n9 + 1), n9 / (2 * n9 + 1)]), "a share of 0 is refused although it is inside the tolerance")
T(not counts_refused([1, 1, 2 ** 40 - 2], [2.0 ** -40 + 1e-9, 2.0 ** -40, (2 ** 40 - 2) / 2 ** 40 - 1e-10]),
  "a share that differs by exactly 1e-9 is accepted: the tolerance is closed")
for conf in (0.999, 0.99999, 0.999999):                                  # the search interval is long enough for a high confidence
    for k in (0, 1, 2, 5):
        mu = L.poisson_upper(k, conf)
        T(abs(sum(math.exp(-mu + i * math.log(mu) - math.lgamma(i + 1)) for i in range(k + 1)) - (1 - conf)) < 1e-12,
          f"Poisson limit k={k} conf={conf}")
for bad_k, bad_conf in ((-1, 0.95), (0, 0.0), (0, 1.0), (0, 1.5), (0, -0.5), (0, float("nan")), (True, 0.95), (0.5, 0.95)):
    raises(ValueError, lambda: L.poisson_upper(bad_k, bad_conf), f"poisson_upper({bad_k!r}, {bad_conf!r}) is refused")
T(abs(L.poisson_upper(0, 1e-6) - 1e-6) < 1e-9, "a very low confidence gives a limit near zero")
T(abs(L.poisson_upper(0, 1 - 1e-12) + math.log(1 - (1 - 1e-12))) < 1e-9, "a confidence above 1 - 1e-5 needs the interval to grow")
T(L.WittenBell().min_count == 1, "Witten-Bell: the default min_count is 1")
fz = L.SimField(BASE, M1, {("read", 1): "none", ("read", 2): "raise"})     # a failed match reads the field once and aborts
rz = L.run_transaction(fz, OLD, NEW)
T((rz.outcome, rz.reason, fz.text, fz.count["read"]) == ("ABORTED", "echo_mismatch", BASE, 1), "a failed match makes one read and nothing else")
fz = L.SimField(BASE, M1, {("read", 1): "key", ("read", 2): "key", ("caret", 2): "forward2"})
rz = L.run_transaction(fz, OLD, NEW)
T((rz.outcome, rz.reason, fz.text) == ("VERIFIED", "ok", "Hello привет "), "two keys that type nothing explain a caret two places forward")
hz = L.HookHealth()
T(hz.pairs == 0 and hz.reinstalled_flag is False and hz.ok and hz.reason is None, "the canary starts armed, with no pairs counted")


print(f"OK ({CHECKS} checks, {sweep} single and double faults, {conv} fuzz conversions, {checked_undo} fuzz undos)")
```

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

```python
# ==== 20.14 Adapter contract: capabilities, modes, replacement transaction, layout identity, hook health =====
import hashlib

READ_RANGE, REPLACE_RANGE, READBACK = "READ_RANGE", "REPLACE_RANGE", "READBACK"
ROLLBACK, SYNTHETIC_INPUT = "ROLLBACK", "SYNTHETIC_INPUT"
CAPABILITIES = frozenset({READ_RANGE, REPLACE_RANGE, READBACK, ROLLBACK, SYNTHETIC_INPUT})
# READ_RANGE      the text of a character range of the focused element can be read.
# REPLACE_RANGE   a range can be replaced in ONE operation (M1) that the application cannot interleave with user keys.
# READBACK        the range can be read again after the write, and the caret position is available.
# ROLLBACK        the original range can be written back by one more such single operation.
# SYNTHETIC_INPUT tagged synthetic keystrokes can be sent (M2); each one is a separate event that user keys can follow.
AUTO_REQUIRES = frozenset({READ_RANGE, REPLACE_RANGE, READBACK, ROLLBACK})
SUPPORT_STATUS = ("UNKNOWN", "MANUAL", "AUTO")      # the support matrix of 13.8: a test result per application


def engine_mode(caps, support: str, *, models_ok: bool = True, layout_ok: bool = True, permission_ok: bool = True,
                hook_ok: bool = True, watchdog_ok: bool = True, quarantined: bool = False) -> str:
    """The mode of the engine for one application, a pure function of facts (13.5). The support matrix can never
    grant more than the capabilities allow: AUTO needs all four capabilities of AUTO_REQUIRES AND the status AUTO.
    M2 alone (SYNTHETIC_INPUT without REPLACE_RANGE and ROLLBACK) is MANUAL_ONLY at best."""
    caps = frozenset(caps)
    if not caps <= CAPABILITIES:
        raise ValueError(f"unknown capability {sorted(caps - CAPABILITIES)}")
    if support not in SUPPORT_STATUS:
        raise ValueError(f"unknown support status {support!r}")
    if quarantined or not permission_ok or not layout_ok or support == "UNKNOWN":
        return "OFF"
    if REPLACE_RANGE not in caps and SYNTHETIC_INPUT not in caps:
        return "OFF"                                     # nothing can write: not even the hotkey
    if support == "AUTO" and AUTO_REQUIRES <= caps and models_ok and hook_ok and watchdog_ok:
        return "AUTO"
    return "MANUAL_ONLY"


def classify_outcome(started: bool, original: str, new: str, final: Optional[str], verified: bool) -> str:
    """The outcome of a replacement, from observations only. `original`, `new` and `final` are texts of the WHOLE
    range that the transaction reads (the word, the Space and the typed-ahead keys), `final` as last read (None when
    it could not be read); `verified` is the result of the step-5 check (content and caret)."""
    if not started:
        return "ABORTED"                                 # nothing was written
    if verified and final == new:
        return "VERIFIED"
    if final == original:
        return "RESTORED"                                # the field holds the text the user typed
    return "UNRECOVERED"                                 # anything else, including an unreadable range


class AdapterError(Exception):
    """An adapter call failed: timeout, API error, revoked permission, vanished element."""


class Adapter:
    """What the engine needs from an OS adapter (13.7). Offsets are code-point positions in the focused element."""
    caps: frozenset = frozenset()

    def gate(self) -> str: raise NotImplementedError                                    # ALLOW | DENY | UNKNOWN
    def caret(self) -> int: raise NotImplementedError
    def read(self, start: int, end: int) -> Optional[str]: raise NotImplementedError    # None: not readable
    def replace(self, start: int, end: int, text: str) -> None: raise NotImplementedError   # M1, one operation
    def send(self, events: Sequence[Tuple[str, str]]) -> None: raise NotImplementedError    # M2: ("bs","") / ("ch",c)
    def modifier_down(self) -> bool: raise NotImplementedError   # M2 only: Shift, Ctrl, Alt or a Windows key is physically down
    def mark(self) -> int: raise NotImplementedError  # an opaque token: "from now on, count the user's key events"
    def keys_since(self, mark: int) -> int: raise NotImplementedError   # user key events seen since that token


@dataclass
class TxResult:
    outcome: str                  # VERIFIED | RESTORED | UNRECOVERED | ABORTED
    reason: str
    method: str = ""              # M1 | M2
    incident: bool = False        # counts as a replacement_incident (13.2, step 6)
    quarantine: bool = False      # the application goes to DENY until restart or re-enable


TYPED_AHEAD_MAX = 3


def run_transaction(ad: Adapter, old: str, new: str, ahead: str = "", *, mode: str = "AUTO",
                    context_break: bool = False, layout_changed: bool = False) -> TxResult:
    """The replacement transaction of 13.2 for the word `old` (as typed; the user's Space is already in the field),
    replaced by `new` of the same length. `ahead`: the characters typed after the Space that the engine recorded.
    The range that is read, verified and rolled back is always the whole fragment: word, Space, typed-ahead keys."""
    n = len(old)
    if len(new) != n:
        raise ValueError("a replacement keeps the length")
    if mode not in ("AUTO", "MANUAL_ONLY"):
        return TxResult("ABORTED", "mode_off")
    if mode == "AUTO" and not AUTO_REQUIRES <= ad.caps:
        return TxResult("ABORTED", "capability")        # defence in depth: a mode can never exceed the capabilities
    method = "M1" if REPLACE_RANGE in ad.caps else ("M2" if SYNTHETIC_INPUT in ad.caps else "")
    if not method or READ_RANGE not in ad.caps:
        return TxResult("ABORTED", "capability", method)
    # 1 freeze
    if context_break or layout_changed:
        return TxResult("ABORTED", "context_break", method)
    if len(ahead) > TYPED_AHEAD_MAX or (method == "M2" and ahead):
        return TxResult("ABORTED", "typed_ahead", method)
    if method == "M2" and ad.modifier_down():            # SendInput: pressed keys "might interfere" (13.7)
        return TxResult("ABORTED", "modifier_down", method)
    try:
        m = ad.mark()                                    # every user key from here on is counted (13.2, steps 3 to 5)
    except AdapterError:
        return TxResult("ABORTED", "adapter_error", method)
    # 2 gate
    try:
        g = ad.gate()
    except AdapterError:
        g = GATE_UNKNOWN
    if g != GATE_ALLOW:
        return TxResult("ABORTED", "gate_changed", method)
    # 3 read and match: the range comes from the content, never from remembered offsets
    try:
        c = ad.caret()
        found = None
        for a in range(len(ahead), -1, -1):
            start = c - (n + 1 + a)
            if start < 0:
                continue
            t = ad.read(start, start + n + 1 + a)
            if t is not None and t == old + " " + ahead[:a]:
                found = (start, a)
                break
    except AdapterError:
        return TxResult("ABORTED", "adapter_error", method)
    if found is None:
        return TxResult("ABORTED", "echo_mismatch", method)
    start, a = found
    end = start + n + 1 + a
    before, after = old + " " + ahead[:a], new + " " + ahead[:a]
    # 3b the last look before the first write. M2 is a sequence of events that user keys can enter, and it
    # deletes by count, so a key that arrived since the freeze makes the plan wrong: nothing is written.
    if method == "M2":
        try:
            if ad.keys_since(m) > 0:
                return TxResult("ABORTED", "typed_ahead", method)
        except AdapterError:
            return TxResult("ABORTED", "adapter_error", method)
    # 4 replace
    failed = False
    try:
        if method == "M1":
            ad.replace(start, start + n, new)
        else:
            ad.send([("bs", "")] * (n + 1) + [("ch", ch) for ch in new] + [("ch", " ")])
    except AdapterError:
        failed = True
    # 5 verify the whole range and the caret. Without user keys the caret is exactly where it was; with k user
    # keys it may have moved forward by at most k. Backwards, or any other change of the range, is a failure.
    ok = False
    if not failed:
        try:
            got = ad.read(start, end)
            cur = ad.caret()
            k = ad.keys_since(m)
            ok = got == after and (cur == c if k == 0 else c <= cur <= c + k)
        except AdapterError:
            ok = False
    if ok:
        return TxResult("VERIFIED", "ok", method)
    # 6 mismatch, timeout or error after step 4 began: one rollback attempt (M1 only), then classify what is there
    final: Optional[str] = None
    try:
        if method == "M1" and ROLLBACK in ad.caps:
            ad.replace(start, start + n, old)
        final = ad.read(start, end)
    except AdapterError:
        try:
            final = ad.read(start, end)
        except AdapterError:
            final = None
    outcome = classify_outcome(True, before, after, final, False)
    return TxResult(outcome, "write_error" if failed else "verify_failed", method, True, True)


class SimField(Adapter):
    """In-memory text field with fault injection, the test double of the replacement transaction.
    `faults` maps (operation, k) to a fault name, k = the 1-based number of the call of that operation:
      gate: 'DENY' | 'UNKNOWN' | 'raise'      caret: 'back' | 'forward' | 'forward2' | 'raise'      read: 'none' | 'stale' | 'raise' | 'user:<c>' | 'key'
      replace: 'raise' (nothing written) | 'partial' (half written, then error) | 'applied_error' (written, then error)
               | 'autocorrect' (the application changes the last character) | 'ignored' (silently not written)
               | 'spill' (the character after the range, the Space, is damaged as well)
               | 'user:<c>' (the user types <c> just before the write) | 'key' (a key that types nothing: Shift, an arrow)
      event k (M2 only): 'raise' | 'key' | 'user:<c>' (the user types <c> just before synthetic event k; a documented
               impossibility inside one SendInput call on Windows, possible between CGEventPost calls on macOS)
               | 'drop' (event k is silently not delivered: UIPI, or a partial insertion).
      modifiers: True when a modifier key is physically down."""

    def __init__(self, text: str, caps, faults=None, gate: str = GATE_ALLOW):
        self.text, self.pos = text, len(text)
        self.caps, self.faults, self._gate = frozenset(caps), dict(faults or {}), gate
        self.count: Dict[str, int] = {}
        self.user: List[str] = []         # every character the user typed, in order (evidence for G-EVENT)
        self.sent = 0                     # synthetic events delivered
        self.silent = 0                   # user key events that typed no character (Shift, arrows)
        self.modifiers = False            # a modifier key is physically down

    def _hit(self, op: str) -> Optional[str]:
        k = self.count[op] = self.count.get(op, 0) + 1
        return self.faults.get((op, k))

    def type_user(self, ch: str):
        self.text = self.text[:self.pos] + ch + self.text[self.pos:]
        self.pos += 1
        self.user.append(ch)

    def gate(self) -> str:
        f = self._hit("gate")
        if f == "raise":
            raise AdapterError("gate")
        return f or self._gate

    def caret(self) -> int:
        f = self._hit("caret")
        if f == "raise":
            raise AdapterError("caret")
        return {"back": -1, "forward": 1, "forward2": 2}.get(f, 0) + self.pos

    def read(self, start: int, end: int) -> Optional[str]:
        f = self._hit("read")
        if f and f.startswith("user:"):
            self.type_user(f[5:])
        if f == "key":
            self.silent += 1
        if f == "raise":
            raise AdapterError("timeout")
        if f == "none":
            return None
        t = self.text[start:end]
        return t[:-1] + "?" if f == "stale" and t else t

    def replace(self, start: int, end: int, text: str) -> None:
        f = self._hit("replace")
        if f and f.startswith("user:"):
            self.type_user(f[5:])
        if f == "key":
            self.silent += 1
        if f == "raise":
            raise AdapterError("timeout")
        if f == "ignored":
            return
        w = text[:len(text) // 2] + self.text[start + len(text) // 2:end] if f == "partial" else text
        if f == "autocorrect":
            w = text[:-1] + "?"
        tail = self.text[end:]
        if f == "spill" and tail:
            tail = "?" + tail[1:]
        self.text = self.text[:start] + w + tail
        if f in ("partial", "applied_error"):
            raise AdapterError("timeout")

    def modifier_down(self) -> bool:
        return self.modifiers

    def mark(self) -> int:
        return len(self.user) + self.silent

    def keys_since(self, mark: int) -> int:
        return len(self.user) + self.silent - mark

    def send(self, events: Sequence[Tuple[str, str]]) -> None:
        for k, (kind, ch) in enumerate(events, 1):
            f = self.faults.get(("event", k))
            if f and f.startswith("user:"):
                self.type_user(f[5:])
            if f == "key":
                self.silent += 1
            if f == "raise":
                raise AdapterError("timeout")
            if f == "drop":
                continue
            if kind == "bs":
                if self.pos > 0:
                    self.text, self.pos = self.text[:self.pos - 1] + self.text[self.pos:], self.pos - 1
            else:
                self.text, self.pos = self.text[:self.pos] + ch + self.text[self.pos:], self.pos + 1
            self.sent += 1


def table_entries(layout: str) -> List[str]:
    """The 94 character entries of a layout: entry 2*id + shift is the character of key `id` without or with Shift."""
    return [TABLE[layout][s][k] for k in range(47) for s in (0, 1)]


def layout_fingerprint(entries: Sequence[str]) -> str:
    """SHA-256 over the 94 entries, joined by LF (an entry never contains LF). An OS adapter fills the entries from
    the layout it is asked about: Windows ToUnicodeEx with the flag that leaves the keyboard state unchanged, Caps
    Lock and all other modifiers off; on macOS the call chosen by spike S-6 (13.7). A dead key or a key without a character is "\\x00"."""
    if len(entries) != 94 or any((not isinstance(e, str)) or "\n" in e for e in entries):
        raise ValueError("a layout fingerprint needs 94 entries without line feeds")
    return hashlib.sha256("\n".join(entries).encode("utf-8")).hexdigest()


SUPPORTED_FINGERPRINTS = {layout_fingerprint(table_entries(lay)): lay for lay in (EN, RU)}


def identify_layout(entries: Sequence[str]) -> Optional[str]:
    """'en' or 'ru' when the layout reads exactly as the supported US English or Russian layout, else None (13.5 row 7:
    OFF for that layout). The language id or the layout name is never enough on its own."""
    return SUPPORTED_FINGERPRINTS.get(layout_fingerprint(entries))


class HookHealth:
    """Is the key-event stream complete? (13.5 row 13) An incomplete stream means a word can be missing its first
    keys, so the engine must treat it as a break (Event 'gap') and the mode drops to MANUAL_ONLY until re-armed.
    Windows: an independent Raw Input observer is the canary. Both sides report every physical key event with a
    signature `sig` (any hashable value that identifies the event: scan code, extended flag, press or release).
    An event of one side must meet an event with the SAME signature from the other side within CANARY_MS, in either
    order; matching counts are not enough, because one lost and one extra event would cancel each other. A raw key
    the hook never reports is "canary_missing" (the OS removed a slow hook silently); a hook key the observer never
    saw is "canary_extra" (the observer or the stream is not what the engine thinks it is). Events the hook marks as
    injected (the engine's own SendInput, other programs) have no physical counterpart and are not compared.
    `ts` is the arrival time in ms on one monotonic clock of the runtime, the same for both sources. Two events
    meet only when their times differ by at most CANARY_MS; an event that arrives later than that finds its
    counterpart already expired, so the loss is declared at once, even if the watchdog timer has not run yet
    (`raw_key`, `hook_key` and `check` can each declare it; the runtime calls `take_gap` after each of them).
    After the hook is installed again, REARM_PAIRS matched pairs are required. macOS: tapDisabledByTimeout and
    tapDisabledByUserInput, or a poll that finds the tap disabled, mark the loss; after the tap is enabled again
    the stream is trusted at once (no canary exists) and the engine's gap event discards the interrupted word."""
    CANARY_MS = 300
    REARM_PAIRS = 3

    def __init__(self, canary: bool = True):
        self.canary = canary
        self.ok = True
        self.reason: Optional[str] = None
        self.raw_only: List[Tuple[int, object]] = []     # (time, sig) of physical keys the hook has not reported yet
        self.hook_only: List[Tuple[int, object]] = []    # (time, sig) of hook keys the observer has not reported yet
        self.pairs = 0                                   # matched pairs since the hook was installed again
        self.reinstalled_flag = False
        self.gap_pending = False

    def _lose(self, reason: str):
        if self.ok:
            self.gap_pending = True
        self.ok, self.reason = False, reason
        self.pairs, self.reinstalled_flag = 0, False
        self.raw_only.clear()
        self.hook_only.clear()

    def _meet(self, mine: List[Tuple[int, object]], other: List[Tuple[int, object]], ts: int, sig):
        self.check(ts)                                   # the watchdog may be late: a waiting event that is already
        #                                                  older than CANARY_MS at this moment is a loss now, it is
        #                                                  never matched by a late counterpart
        for i, (t, s) in enumerate(other):
            if s == sig and abs(ts - t) <= self.CANARY_MS:   # the oldest event of the other side with this signature
                del other[i]
                if not self.ok and self.reinstalled_flag:
                    self.pairs += 1
                    if self.pairs >= self.REARM_PAIRS:
                        self.ok, self.reason = True, None
                return
        mine.append((ts, sig))

    def raw_key(self, ts: int, sig):
        """The independent observer saw a physical key event (Windows only)."""
        if self.canary:
            self._meet(self.raw_only, self.hook_only, ts, sig)

    def hook_key(self, ts: int, sig, injected: bool = False):
        """The hook saw a key event; `injected` is the hook's own flag for synthetic events."""
        if self.canary and not injected:
            self._meet(self.hook_only, self.raw_only, ts, sig)

    def check(self, now_ms: int) -> bool:
        """Called by the runtime timer; returns the current health."""
        if self.canary:
            waiting = [(q[0][0], r) for q, r in ((self.raw_only, "canary_missing"), (self.hook_only, "canary_extra")) if q]
            if waiting:
                ts, reason = min(waiting, key=lambda w: w[0])
                if now_ms - ts > self.CANARY_MS:
                    self._lose(reason)
        return self.ok

    def tap_disabled(self, reason: str):
        if reason not in ("timeout", "user_input"):
            raise ValueError(reason)
        self._lose("tap_" + reason)

    def poll(self, enabled: bool):
        if not enabled:
            self._lose("poll")

    def reinstalled(self):
        """The runtime installed the hook again (Windows) or enabled the tap again (macOS)."""
        self.raw_only.clear()
        self.hook_only.clear()
        self.pairs = 0
        if self.canary:
            self.reinstalled_flag = True
        else:
            self.ok, self.reason = True, None

    def take_gap(self) -> bool:
        """True once per loss: the runtime then sends Event('gap') to the engine."""
        g, self.gap_pending = self.gap_pending, False
        return g
```
