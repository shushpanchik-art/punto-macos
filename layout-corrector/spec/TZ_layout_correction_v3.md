# Keyboard Layout Auto-Correction Model — Technical Specification v3

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

- Language pair RU ↔ EN: US QWERTY and Russian ЙЦУКЕН (Windows "Russian", macOS "Russian - PC" and "Russian"; Linux, deferred to a later release (13.7): XKB `ru`). The layout-pair table is a parameter, so further pairs can be added without changing the architecture.
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

Each keystroke event carries: physical key position `k` (one of 47 printable keys of the main block), Shift state, Caps Lock state, active layout id, and timestamp. The model input is the sequence of key tokens `1 + 2k + shift` (94 tokens) plus PAD, BOS and EOS: a vocabulary of 97.

- **Why keys.** `ghbdtn` typed on an English layout and `привет` typed on a Russian layout are the same keys. With keys as input, the two readings of a word (EN and RU) are always available and exactly aligned, and the layout tables carry no learnable burden.
- **Why not characters.** A character-based model must memorise the permutation (`g→п`) for every context, wasting capacity, and its labels `en` / `en_from_ru` differ only by an input the model never sees directly.
- **Caps Lock.** Store raw Shift and Caps separately. The effective case of a key is `shift XOR (caps AND key_is_letter_in_target_layout)`. This matters for `;` `'` `[` `]` `,` `.`: on an English layout Caps Lock does not capitalise them, but on a Russian layout it capitalises `Ж Э Х Ъ Б Ю`. The mapper must re-apply Caps per target layout.

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

- Generate layout tables from the OS (`UCKeyTranslate` on macOS, keyboard layout files on Windows, XKB on Linux) for each supported layout pair, and store them versioned. Hand-typed tables are a test oracle only.
- Verify round trips: for every key and shift state, `map(map(c, A→B), B→A) = c`, with the exceptions listed explicitly. My table check for Windows "Russian" against US QWERTY has 0 round-trip failures over all 94 key states.
- Characters with no counterpart (dead keys, combining marks, emoji, anything outside the 47 keys) make the candidate ineligible: no action.
- macOS "Russian" and "Russian - PC" differ in punctuation placement; Windows, macOS and XKB tables must not be assumed equal.

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

The native column was measured with a 16-dimension embedding, which has about 9% fewer multiply-adds than the trained models; treat it as a lower bound of 10%. The `c` = 192 row was trained for 6 epochs with the base recipe and is not strictly comparable.

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

**The requester's 0.0001 ms target.** The target is 100 ns. It is met by the stage that needs it and cannot be met by the network:

- A hash look-up costs 12 to 32 ns measured, so one to eight probes fit in 100 ns. Lexicon and exception look-ups meet the target; that is what the stage-4 row of the table gates.
- The n-gram stage needs 54 probes per candidate (two readings, nine positions, three classes) and takes 0.7 to 1.7 µs, which is 7 to 17 times over.
- The smallest network measured has 603 parameters (`c` = 4) and needs about 2,900 multiply-adds for a 9-key word. At 100 ns that is 29 billion multiply-adds per second on one core, close to the peak of a SIMD core with perfect utilisation and no overhead. A naive loop took 3.7 µs. Its type accuracy is 0.913, 5 points under the reference model.
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
- **Temperature scaling.** `p = softmax(z / T)`, with one scalar `T` fitted on the calibration data by minimum negative log-likelihood. It does not change the arg-max, so it cannot change accuracy. Fit `T` per class if the per-class reliability diagrams disagree.
- **Prior-shift correction.** `p'(c) ∝ p(c) · π_dep(c) / π_train(c)`, renormalised. `π_train` is the class mix of the training set (in the proxy experiment 0.39 EN, 0.40 RU, 0.22 OTHER). `π_dep` is the complete three-class deployment prior, a vector over (EN, RU, OTHER) that sums to 1, for the active layout `A` and the word state (section 10.2). Without this step a classifier trained on a balanced mix converts far too often in real use (section 5.5).
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

**Estimation.** These are starting points. Before release they are replaced by values measured on the real calibration set R-CAL (section 8.4), never on the locked acceptance set R-ACC. `w[default]` is, per layout, the number of wrong-layout words divided by the words typed on that layout, where a wrong-layout word is one the user converted by hotkey or kept after an automatic conversion (section 11.5). `w[after_switch]` is the same rate for the first word after a manual layout change. `w[run]` is the probability that a word is wrong-layout given that the previous one was; with a mean run length of `m` words in the data it is `1 − 1/m`. `o_lat` is the OTHER share among Latin-script words. Each estimate is reported with a cluster-bootstrap interval by user, and the stored value is the point estimate, clipped to the ranges the load check allows. An overestimated `w` raises false corrections, which EV-1 on R-ACC would expose; an underestimated `w` only costs recall. The package D5 stores the numbers `w` and `o_lat`, not free vectors, so that every vector sums to 1, and the table is versioned with the model.

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
| CA-9 | The calibration package MUST be validated when it is loaded: every threshold within 4 to 16 nats; `w` within 0.0005 to 0.5 for every state and at most 0.3 for `run`; `π_train` sums to 1 and `0 < o_lat < 1`; a temperature for every scorer kind; the model hash in the package equals the hash of the loaded model or table file. On any failure the automatic mode is off (13.5). |
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
| EV-1 | False-positive rate on correct words | Pass rule of 11.3: at least 100,000 correct words from at least 20 users and 100 documents; point estimate ≤ 4.8e-5 (at most 4 false corrections at n = 100,000) and cluster-adjusted 95% upper bound ≤ 1e-4 (precision ≥ 99.5% at π = 1%, R = 0.95) | `R-ACC`, real correct words (8.4) |
| EV-2 | False corrections on protected content (every OTHER category of section 8.3) | 0 in at least 100,000 items, each category at least 5,000; upper bound ≤ 3e-5 | Protected regression set |
| EV-3 | Precision at π = 0.3%, 1%, 3% | Reported; ≥ 99.5% at π = 1% | Derived from EV-1 and EV-4 |
| EV-4 | Recall for words of 5 or more keys at the operating point of EV-1 | ≥ 95% EN→RU and ≥ 90% RU→EN. These values are changed only at gate G2 (16.1) by a recorded decision, as set out in 11.3, and are frozen after it | `R-ACC` positives (synthetic re-layout of real sentences, 11.7) |
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
| EV-15 | Text integrity | 0 lost or duplicated characters (RT-4) | End-to-end suite |

### 11.3 How many words are enough

To prove a false-positive rate you need many correct words, because the errors are rare. With `k` observed errors the one-sided 95% Poisson upper limit on the number of true errors is 3.00, 4.74, 6.30, 7.75, 9.15 and 10.51 for `k` = 0 to 5. The table gives the number of independent correct words needed for the upper bound to stay below each target.

| Observed errors `k` | Upper-limit multiplier | Words for bound ≤ 1e-4 | Words for bound ≤ 3e-5 | Words for bound ≤ 1e-5 |
| --- | --- | --- | --- | --- |
| 0 | 3.00 | 29,958 | 99,858 | 299,574 |
| 1 | 4.74 | 47,439 | 158,129 | 474,387 |
| 2 | 6.30 | 62,958 | 209,860 | 629,580 |
| 3 | 7.75 | 77,537 | 258,456 | 775,366 |
| 4 | 9.15 | 91,536 | 305,118 | 915,352 |

The second draft's realistic test (5–20K words) can only demonstrate a rate near 1 in 1,000, which is 10 times too lax for this product; the third draft's 300,000 synthetic negatives are the right size, but synthetic text does not show the real rate. Words from one text are correlated, so the effective sample is smaller than the word count. The table is therefore a sizing guide only; the pass condition of EV-1 is the cluster-adjusted rule below.

For recall, a 95% interval of ±1 point needs about 1,830 positives at R = 0.95, 1,120 at R = 0.97 and 380 at R = 0.99; ±0.5 point needs 7,300, 4,470 and 1,520. Collect at least 20,000 positives per direction so that each length bucket has several thousand.

**EV-1 pass rule under clustering (normative; reference code in 20.9).** Words typed by one user in one document share vocabulary, topic and habits. One weakness, for example a surname that scores as Russian, can repeat many times, and counting each repeat as an independent error would make the bound too optimistic. A *cluster* is one pair (user, document). Let `n` be the number of correct words after the caps of 8.5, `k` the number of false corrections, `c` the number of distinct clusters that contain at least one false correction and `m` the largest number of false corrections in one cluster. EV-1 passes if and only if all four conditions hold.

1. `n` ≥ 100,000, the words come from at least 20 users and at least 100 documents, and `n` was fixed before the first evaluation (8.5).
2. `k / n` ≤ 4.8e-5. At `n` = 100,000 this allows at most 4 false corrections; at a larger `n` the allowance grows in proportion.
3. `U(c) · m / n` ≤ 1e-4, where `U(c)` is the exact one-sided 95% Poisson upper limit for `c` observed events: 2.9957, 4.7439, 6.2958, 7.7537, 9.1535 and 10.5130 for `c` = 0 to 5 (the function `poisson_upper` of 20.9 computes it for any `c`).
4. The evaluation is the one that the log of `R-ACC` records (8.4); a pass found in a repeated, tuned or extended evaluation does not count.

If every false correction sits in a different cluster, then `c` = `k`, `m` = 1 and condition 3 is the independent-words bound of the table above. If the errors bunch together, `c` falls (the errors are one problem seen several times) and `m` rises, and the bound rises with `m`: the rule assumes that every independent source of error could produce as many errors as the worst one that was observed. This is conservative on purpose, and it is a decision rule, not a confidence interval with exact coverage. A cluster bootstrap is not used as the gate because with 4 or fewer events most resamples contain none of them and the interval degenerates; it stays in the report as a diagnostic.

Worked cases, all reproduced by the code of 20.12: 4 false corrections in 4 different clusters at `n` = 100,000 give a bound of 9.15e-5 and pass. The same 4 in one document give 1.90e-4 and fail. Two clusters with 2 errors each give 1.26e-4 and fail. 0 errors at `n` = 99,999, or 0 errors from 19 users, fail on condition 1. 5 errors in 5 clusters at `n` = 150,000 give 7.01e-5 and pass.

**Freezing EV-4 and EV-5.** The provisional recall values stand unless they are changed at gate G2 (16.1) by a written decision that contains the baseline recall at the EV-1 operating point on the `R-CAL` positives. The values may be lowered only to that measured recall minus 2 points, rounded down to a whole number, and may never be raised above the provisional ones to fit a result. They are frozen when G2 is passed. A change after the first evaluation on `R-ACC` makes that `R-ACC` retired (8.4).

### 11.4 Required slices in every report

- Direction: EN→RU and RU→EN.
- Length in keys: 2, 3, 4, 5–6, 7–9, 10 or more.
- Content: ordinary word, name, brand, acronym, slang, and each OTHER category (identifier, URL, e-mail, path, number, hash, command, transliteration, key-mashing).
- Case: lower, Capitalised, ALL CAPS, mixed, Caps Lock on.
- Context: sentence start, after a word of the other language, after punctuation, mixed-language sentence.
- Mode: boundary and early detection.
- Source and user, to expose clustering.

### 11.5 Measuring the wrong-layout rate π

The false-positive budget depends on π, which is unknown (section 5.5). Estimate it in the opt-in study as `(corrections not undone + manual conversions) / words typed`, per user, with a cluster bootstrap interval, and record the distribution of wrong-layout run lengths (words typed before the user notices). The estimate feeds the priors of section 10.2 and the precision table of EV-3.

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
| EV-1 false-positive rate | Real, `R-ACC` | none | The rate of false corrections on the correct typing of the enrolled users, with the bound of 11.3 | The rate for other users, applications, topics or languages; the sample has at least 20 users |
| EV-2 protected content | Synthetic generators and packages of 8.3 | none | Code, URLs, paths, hashes and similar shapes are not converted | How often such strings occur in a real day |
| EV-3 precision | Real | Synthetic, with an assumed π | Precision if the wrong-layout rate is 0.3%, 1% or 3% | The true π of any user; it stays an assumption until `R-NAT` and dogfooding measure it |
| EV-4, EV-5, EV-6 recall | none | Synthetic re-layout of real sentences, `R-ACC` | That wrong-layout words in realistic sentences are recognised and converted | How often, where and in which words users really err; `R-NAT` is a biased check (11.5) |
| EV-7 calibration | Real and synthetic mixture | Synthetic | Reliability of the probabilities on the mixture of `R-CAL` and `R-ACC`; the mixture weights come from the assumed priors | Reliability under a different π |
| EV-8, EV-9 robustness, stress sets | Synthetic | Synthetic | Behaviour on targeted failure families | Their real-world frequency |
| EV-10 early detection | Real prefixes | Synthetic prefixes | The false-positive gate inside a word | Nothing about the user's tolerance for text changing mid-word |
| EV-11 undo rate | Real | Real | What enrolled users accept in daily use | A different population |
| EV-12 network or baseline | Real | Synthetic | Which candidate is better on the same data; any optimism of the set is shared | An absolute quality figure |
| EV-14, EV-15 | none | none | Latency, size and text integrity on the reference devices and the end-to-end suite | Other devices or applications than those listed in 13.8 |

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

**Replacement transaction.** A CONVERT verdict starts a transaction on the worker thread, with a hard deadline of 250 ms from the Space.

1. **Freeze.** Count `a`, the printable keys typed after the Space so far, and note any other event since the Space. More than 3 such keys, any context break or any layout change aborts with reason `typed_ahead` or `context_break`; the verdict becomes KEEP.
2. **Gate.** Query the gate afresh. Anything but ALLOW aborts with `gate_changed`.
3. **Read and match.** Read the text before the caret through the OS text interface, with an empty selection. The last `n + 1 + a'` characters must equal the recorded run rendered on the active layout, then a Space, then the `a'` typed-ahead characters, for some `a' ≤ a` (`n` is the number of keys in the run). The range to replace is thus fixed from the content, not from remembered offsets. If the text cannot be read, or differs because the application autocorrected, autocompleted or reformatted it, abort with `echo_mismatch`.
4. **Replace** exactly the `n` characters of the run by the same keys read on the target layout (`Ghbdtn?` becomes `Привет,`; the Space the user typed is not touched). The new text has the same length as the old, so the caret and any typed-ahead characters stay where they are.
   - **M1, range replace** (preferred): one operation through the text interface, then the caret and selection are restored.
   - **M2, tagged synthetic keystrokes**: only for applications marked M2 in 13.8, and only when `a' = 0`. Send `n + 1` Backspaces, then the new text and a Space, as tagged Unicode events in one batch.
   - The clipboard is not used in the first release.
5. **Verify.** Read the range back. It must equal the new text, and the caret must be where it was expected.
6. **On any mismatch, timeout or API error after step 4 began:** make one rollback attempt (M1 writes the original text back; M2 cannot be undone safely and is only reported), show a notice, increment `replacement_incident`, and quarantine the application (gate DENY for it until restart or until the user re-enables it in the settings).
7. **Record the undo information**: the original keys with their layout id, the range and the time (13.3).

**What happens to the user's keys.** Before step 4 they pass through and are never held. With M1 a key typed during steps 3 to 5 lands after the range and is unaffected, because the replacement has the same length. With M2 a key that arrives between the first and the last synthetic event is a race the tool cannot prevent without holding keys, which it must not do; the race is detected in step 5, repaired by the rollback where possible, and otherwise counted as an incident and followed by the quarantine. This is why M2 is granted per application, after the 100,000-replacement test of RT-4, and why M1 is preferred.

**Guarantee, stated precisely.** The tool never loses or duplicates a user key, because it never holds, replays or repeats one. The only text it writes is the replacement of the recorded word, and every replacement is verified by reading it back. RT-4 measures this as silent corruption (a divergence that step 5 did not detect), which must be zero.

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
- **Manual conversion of a selection** converts key for key, with no model and no threshold. Direction: a selection with more Cyrillic than Latin letters is read as Russian-layout text and converted to the English layout, otherwise the reverse; a selection with no letters is left unchanged and the user is told. Punctuation goes through the layout table as in 5.3 (`Ghbdtn? Rfr ltkf?` becomes `Привет, Как дела,`). A character that is not on the source layout (emoji, accented letters, other scripts) is copied unchanged, and the length never changes. At most 10,000 characters. The replacement uses M1 and the verification of 13.2, and afterwards the same range is selected again; if the selection cannot be restored, the caret is placed after the text. The reference function is in section 20.8.
- **Undo window.** 10 seconds and up to 100 following characters. It is invalidated by every context break of 13.2, a manual layout change and the timeout.
- **Learned exceptions.** One undo of a word adds it (case-folded, with its direction) to a local exception list, as Rekey and KeyboardSwitcher do. Limit: 10,000 entries, least-recently-used eviction, encrypted at rest with the OS key store, with a "clear all" command and export.
- **Adaptive thresholds.** Not part of the first release (10.6).

### 13.4 Privacy and security

- All inference is local. No network call is allowed on the typing path.
- Key and text buffers live in memory only, hold at most 64 keys, and are zeroed at every word boundary and context break.
- No raw keystrokes, words or screenshots are written to logs. Optional diagnostics contain only counters and reason codes (converted, abstained, guard name, undone), are off by default and are shown to the user before they are enabled.
- The exception list never leaves the device.
- Required OS permissions (macOS Accessibility and Input Monitoring, code signing and notarisation) are part of the release checklist, because keystroke observers are commonly flagged by security software.

### 13.5 Failure behaviour

The engine is always in exactly one of three modes. **AUTO**: automatic correction and the hotkey. **MANUAL\_ONLY**: no automatic correction, the hotkey works. **OFF**: nothing is recorded. Every failure maps to one row of the table below, each row has a test (RT-12), and no failure is ever resolved by guessing.

| # | Component state | Mode | What the user sees |
| --- | --- | --- | --- |
| 1 | All components valid; the network was accepted by EV-12 | AUTO, scorer `network` | Nothing |
| 2 | The network is not shipped because EV-12 chose the baseline | AUTO, scorer `ngram` | Nothing; this is a normal configuration |
| 3 | The network file is missing, unreadable, differs from the hash in D5, or fails the load-time self-test (the reference logits of section 20.11 within 1e-3) | AUTO with scorer `ngram` when rows 4 to 6 are clear for it, otherwise MANUAL\_ONLY | A one-time notice that the basic mode is in use; a counter |
| 4 | The n-gram tables are missing or corrupt | MANUAL\_ONLY if the network is not usable either, otherwise AUTO with the network | A notice |
| 5 | The lexicon, the acronym list or the allow-lists are missing or corrupt (rows 9 to 11 of 10.4 cannot be evaluated) | MANUAL\_ONLY | A notice |
| 6 | The calibration package is missing, fails the validation of CA-9, or its model hash does not match the loaded file | AUTO with the other scorer if that one passes, otherwise MANUAL\_ONLY | A notice |
| 7 | The layout table of the active pair is missing or fails its round-trip self-test, or the active layout is unsupported (13.7) | OFF for that layout | The status icon says "layout not supported" |
| 8 | The text interface is unavailable (permission revoked, API error) or the gate cannot be established | The gate is UNKNOWN: nothing is recorded; the hotkey only shows a notice | A notice with the way to restore the permission |
| 9 | Watchdog: the p99 compute time of the decision exceeds its budget (7.5) for 100 consecutive words | MANUAL\_ONLY until restart or until the user re-enables AUTO | A notice |
| 10 | A replacement incident (13.2, step 6) | The application is quarantined (DENY) | A notice; a counter |
| 11 | An unhandled exception in the worker | The current word is KEEP; the worker restarts once; a second failure within 60 seconds gives MANUAL\_ONLY | A notice after the second failure |
| 12 | A package update fails signature or hash verification | The previous package stays active | A notice |

A notice is shown at most once per cause and per 24 hours, and never takes focus.

### 13.6 Requirements

| ID | Requirement |
| --- | --- |
| RT-1 | The key-event callback MUST return within 1 ms (p99), MUST pass the event on unchanged and at once (observe only), and MUST NOT call the model, the accessibility API or the clipboard, allocate memory, or block. It reads the cached gate verdict (one atomic read) and nothing else from the OS. |
| RT-2 | No key MUST be stored, counted, classified or logged while the cached gate verdict is not ALLOW, and a word MUST be discarded unclassified if the fresh verdict at the decision point is not ALLOW (13.1). A test per supported OS and application class MUST demonstrate it with an instrumented build that counts stored keys, including a focus race (typing into a password field within 5 ms of focusing it) and a field whose type changes while typing. |
| RT-3 | Guards in 13.1 MUST take priority over any model output and MUST be unit-tested one by one, and the priority matrix of 10.4 MUST be tested row by row. |
| RT-4 | Every replacement MUST follow the transaction of 13.2 and MUST be verified. The end-to-end suite MUST show, in at least 100,000 automated replacements per OS across the verified applications, with typed-ahead keys and scripted bursts at three CPU load levels: 0 silent corruptions (divergences that step 5 did not detect), 0 unrepaired incidents, and at most 0.1% repaired incidents, all of them reported. |
| RT-5 | Undo MUST restore the original keys exactly and MUST be invalidated by every context break of 13.2. |
| RT-6 | No raw typed content MUST be persisted or transmitted; diagnostics MUST be opt-in and content-free. |
| RT-7 | An unhandled error before step 4 of the transaction MUST result in no action. An error after step 4 began MUST end in verification and rollback, and if that fails in an incident report and quarantine; it MUST NOT leave partial text silently. |
| RT-8 | The decision MUST be made on a worker thread. The hook MUST NOT delay, hold, swallow or replay a user key, and the tool MUST NOT inject a key except as part of a tagged replacement. |
| RT-9 | The gate MUST default to deny: ALLOW only for an element positively established as in 13.1, and only in an application on the verified list of 13.8. |
| RT-10 | Every synthetic event of the tool MUST carry the tag of 13.7, the recorder MUST ignore tagged events, and a test MUST show that the output of a replacement never re-enters the recorder. |
| RT-11 | The hotkey MUST be registered through the OS hotkey interface, MUST NOT reach the application, and a registration conflict MUST follow the fallback procedure of 13.3 and be shown to the user. |
| RT-12 | Every row of the failure table of 13.5 MUST be implemented and tested. |
| RT-13 | The release MUST ship a support matrix (13.8) in which every ALLOW application has a passing RT-4 suite on the release candidate; every other application is UNKNOWN. |
| RT-14 | A layout change inside a word MUST drop the word, and no correction MUST be made for it (13.2). |

### 13.7 Platforms, mechanisms and the first release

**Scope of the first release:** Windows 10/11 x64 and macOS 13+ (Apple Silicon and Intel). **Linux is not in the first release.** It needs its own column in the table below and its own test matrix: Wayland restricts global key capture, X11 would use XInput2 or XRecord, and IBus or fcitx engines are a different architecture. The engine (sections 5 to 12 and 20) is OS-independent; only the adapter described here is per OS.

**Integration type: a user-space background application** with a listen-only global key observer, an accessibility or UI-automation text adapter, and a hotkey registration. It is not an input method (TSF, Input Source, IBus): an input method changes which keys the application receives, which the observe-only rule of 13.2 rules out.

| Function | Windows 10/11 x64 | macOS 13+ |
| --- | --- | --- |
| Event capture | `SetWindowsHookEx(WH_KEYBOARD_LL)` on a dedicated thread with a message loop; the callback calls `CallNextHookEx` and returns | `CGEventTapCreate`, session tap, listen-only, for key down, key up, flags changed and mouse down (context breaks). Permission: Input Monitoring |
| Physical key id | Scan code and extended flag of the hook structure, mapped to the 47 ids (section 19.1) | `kCGKeyboardEventKeycode` (ANSI position codes), mapped to the 47 ids |
| Shift and Caps Lock | Shift from the tracked key state; Caps Lock toggle state from `GetKeyState(VK_CAPITAL)` | Event flags (shift, alpha-shift) |
| Active layout | `GetKeyboardLayout` of the foreground thread, low word `0x0409` (English US) or `0x0419` (Russian), sampled at every key and at Space | `TISCopyCurrentKeyboardInputSource` on the main thread, kept in a cache updated by the selected-input-source-changed notification; ids `com.apple.keylayout.US`, `.Russian`, `.RussianWin` |
| Gate and text interface | UI Automation: focused element, control type, `IsPassword`, `TextPattern` (read) around the caret, focus-changed event; Win32 edit and rich-edit controls through their messages | Accessibility API: focused element, role and subrole (`AXSecureTextField`), `AXSelectedTextRange`, `AXStringForRange`, focus-changed observer; `IsSecureEventInputEnabled()` |
| M1, range replace | Only for Win32 edit and rich-edit controls (`EM_SETSEL`, `EM_REPLACESEL`); UI Automation text ranges are read-only | Set `AXSelectedTextRange`, then `AXSelectedText`, then restore the caret |
| M2, synthetic keystrokes | `SendInput` with `KEYEVENTF_UNICODE` | `CGEventPost` with `CGEventKeyboardSetUnicodeString` |
| Synthetic tag | The tool's 32-bit magic value in `dwExtraInfo` of every `INPUT` (the hook structure shows it, and the injected flag is set as well) | The tool's 64-bit magic value in `kCGEventSourceUserData` of every event |
| Hotkey | `RegisterHotKey` | `RegisterEventHotKey` |
| Privileges and distribution | Runs unelevated, so elevated windows and the secure desktop cannot be observed or edited and resolve to UNKNOWN; signed MSIX or MSI installer | Accessibility and Input Monitoring permissions (TCC), hardened runtime, notarised package; first-run flow of 13.9 |
| Autostart | Per-user startup entry | Login item (`SMAppService`) |

Each cell has a test in the end-to-end suite. On Windows the common path is M2 with verification through UI Automation, because most modern controls do not allow range replacement; on macOS M1 is the common path. A function that cannot be provided in some application or OS version makes the gate UNKNOWN for it (13.1); it is never emulated by guessing.

### 13.8 Support matrix and verified applications

ALLOW is granted per application, identified by bundle identifier or by executable path and signature, and only for applications whose status is VERIFIED. A row becomes VERIFIED when the RT-2 and RT-4 suites pass in that application, on the release candidate, on the OS versions named in the report. Every other application is UNKNOWN. The list below is the proposed target list (open question 16.3); the evaluation report D6 fills in the status.

| Class | macOS targets | Windows targets | What the verification covers |
| --- | --- | --- | --- |
| Native editors | TextEdit, Notes, Pages | Notepad | Gate by text interface; M1 on macOS, M1 or M2 on Windows |
| Mail and office | Mail, Microsoft Word, Microsoft Outlook | Microsoft Word, Outlook, OneNote, LibreOffice Writer | Text interface readable; password and ordinary fields told apart |
| Browsers | Safari, Chrome, Firefox | Chrome, Edge, Firefox | Accessibility active; three reference pages per browser (plain textarea, rich-text editor, login form with a password field); `IsPassword` or `AXSecureTextField` reported |
| Chat and notes | Messages, Telegram, Slack, Discord, Obsidian, Notion | Telegram Desktop, Slack, Discord, Microsoft Teams, Obsidian, Notion, WhatsApp Desktop | Same as browsers for Electron applications; native chat windows by text interface |

That is 15 applications per OS. A release needs at least 10 VERIFIED per OS; with fewer, it does not ship for that OS. Always UNKNOWN or DENY, whatever the tests say: terminals, IDEs, remote-desktop and VM clients, password managers, games, editors that draw their own text without a text interface, and elevated windows.

**Fail-safe summary.** A missing permission, an unreadable element, an unlisted application, an unresolved focus change and a failed query all produce UNKNOWN, and UNKNOWN records nothing. The only way to get automatic correction in an application is a passing test in that application.

### 13.9 The application layer

The runtime library (D8) is not the product. The requirements below cover what the user installs and sees. They are tested by a scripted checklist on the release candidate: fresh install, upgrade from the previous version, permission revoked while running, crash, uninstall.

| ID | Area | Requirement |
| --- | --- | --- |
| AP-1 | First run and permissions | The first screen says what is observed (keystrokes in text fields, processed on the device, never stored or sent, 13.4) and asks for the OS permissions one at a time, each with a link to the right system settings pane. Until all are granted the state is OFF and the status icon names the missing permission. The user can quit from this screen |
| AP-2 | Status and control | A menu-bar or tray icon always shows one of Active, Paused, Manual only, Off. One click pauses (the gate becomes DENY, so nothing is recorded). "Pause for this application" adds it to the application list |
| AP-3 | Layout pair | Detected from the installed input sources: when exactly one supported English layout and one supported Russian layout are installed, that pair is used; otherwise the user chooses; an unsupported variant switches the tool off for it with the notice of failure row 7 |
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
| Layout variants | Tables generated per OS and variant: Windows "Russian"; macOS "Russian" and "Russian - PC"; Linux (deferred, section 13.7) XKB `ru`; US QWERTY. ISO keyboards add one key | Punctuation placement differs between variants (section 5.4). A round-trip test per variant, and a golden test of the seven punctuation keys that carry Russian letters |
| Latin layouts other than US QWERTY | Out of scope. Detected and the tool is disabled for that layout pair | Dvorak, Colemak, AZERTY and QWERTZ change the physical position of Latin letters, so key tokens trained on QWERTY positions would be wrong. Supporting them needs a per-pair canonical key table and its own training run |
| Cyrillic layouts other than ЙЦУКЕН | Out of scope (phonetic Russian, Ukrainian, Belarusian). Detected and disabled | Not a key-for-key permutation of QWERTY. The layout abstraction allows adding a pair later |
| Caps Lock and Shift | Store both raw; apply case per target layout (section 5.1) | On the Russian layout Caps Lock capitalises `ж э х ъ б ю`; on the English layout it does not capitalise `; ' [ ] , .`. Test cases for `GHBDTN`, `Ghbdtn`, `gHBDTN` |
| Dead keys, AltGr, compose | Candidate is ineligible | Not representable as one of 47 key positions |
| Layout change mid-word | Drop the word: its keys came from two layouts, so nothing is converted and nothing is replayed (sections 5.3 and 13.2) | One layout id cannot render keys typed under two layouts, so any conversion would be a guess. Traple translates at decision time; this specification does not. Verified by RT-14 |
| Active layout source | Read from the OS on every word; never inferred | A wrong layout label inverts the action |

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
| D3 | Statistical baseline: lexicon and n-gram tables | Binary tables with a build script | Meets the baseline row of the evaluation report; its size and latency are reported (section 7.5) |
| D4 | Trained network | PyTorch checkpoint, ONNX FP32 file, and an INT8 file only if section 12 requires it | Passes EV-1 to EV-15 or loses to D3 under EV-12 |
| D5 | Calibration package | One versioned JSON: temperature, class priors, deployment-prior table, threshold table by direction and length, allow-list, acronym list | Fitted on validation only (CA-1 to CA-6); hash stored with D4 |
| D6 | Evaluation report | Generated document with every slice of section 11.4, confidence intervals and the seed spread | Produced by one command; contains the manifest hashes of the data it ran on |
| D7 | Benchmark harness | C or C++ micro-benchmarks and an ONNX Runtime script | Reports p50, p95, p99 per stage on each reference device (section 7.5) |
| D8 | Runtime library | Hook, buffer, guards, replacer, undo (section 13) | RT-1 to RT-8 pass, including the end-to-end suite |
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
| End to end | At least 15 applications per OS, scripted bursts at three CPU load levels, undo and cool-down, secure fields | RT-1 to RT-8; 0 lost or duplicated characters in 100,000 replacements (RT-4, EV-15) |
| Soak | 24 hours of simulated typing | Memory flat within 2%; no watchdog trips; no leaked key content in memory dumps after a word boundary |
| Privacy | Search logs, crash dumps and the file system after a scripted session | 0 occurrences of typed content (RT-6) |

### 15.4 Requirements

| Id | Requirement |
| --- | --- |
| EV-16 | Every figure in the evaluation report MUST be reproducible from the run record by one command. |
| EV-17 | The continuous-integration gate on every change MUST run the unit, property, parity and regression levels. Acceptance and end-to-end levels run per release candidate. |
| EV-18 | The release MUST NOT ship if the model card lacks the π assumption, the known failure list or the data licences. |
| EV-19 | A bug found in the field MUST be turned into a regression test before the fix is released. |

## 16. Work plan, risks and open questions

The plan is ordered so that the cheapest evidence arrives first: a statistical baseline and the evaluation harness exist before any large network is trained, and the neural model has to earn its place (EV-12). Durations are planning estimates for one engineer plus a part-time reviewer and one data-collection coordinator; they are not measurements.

### 16.1 Phases and go/no-go gates

| Phase | Weeks | Work | Gate to leave the phase |
| --- | --- | --- | --- |
| 1. Foundations | 1–2 | Layout tables from the OS (D1); key tokeniser and segmentation; data pipeline and manifest (D2); evaluation harness with all slices of section 11.4; synthetic test sets; start recruiting users for the realistic set (section 8.5) | G1: round-trip tests pass; harness reproduces a known toy result; legal register has a licence entry for every source in use |
| 2. Baseline and first network | 3–4 | Lexicon plus n-gram baseline (D3); key-token CNN trained and calibrated (D4, D5); EV-12 comparison on the synthetic and the first real data; final values of EV-4 and EV-5 fixed from the baseline run | G2: the baseline meets EV-1 on the synthetic set; the neural model is kept or dropped by EV-12; the latency tiers of section 7.5 are measured on both reference devices |
| 3. Runtime and safety | 5–7 | Hook, buffer, guards, replacer, undo (D8); end-to-end suite on 15 applications per OS; early detection and the retroactive run fix evaluated as options (sections 10.5 and 14.2) | G3: RT-1 to RT-8 pass; 0 lost or duplicated characters in 100,000 replacements; secure-field tests pass |
| 4. Opt-in dogfooding | 8–11 | At least 20 users, at least two weeks; R-CAL and R-ACC collected from disjoint users, R-ACC locked (section 8.4); π and run lengths measured (section 11.5); priors and thresholds re-fitted on R-CAL only; hard-negative mining on training sources only | G4: EV-1 to EV-13 pass once on the locked R-ACC (section 11.3); undo rate ≤ 0.5% (EV-11) |
| 5. Release | 12–13 | Signing and notarisation; model card (D9); staged rollout and rollback demonstrated (D10); legal review of share-alike sources | G5: all gates green; one-step rollback tested; EV-18 satisfied |

A failed gate has a defined response. G2 failing EV-1 on the baseline means the data, not the model, is the next lever. G4 failing means the thresholds are raised and recall is reported honestly; the product ships in manual-convert plus suggestion mode until EV-1 is met.

### 16.2 Risks

| Id | Risk | Likelihood | Effect | Mitigation and trigger |
| --- | --- | --- | --- | --- |
| R1 | The real wrong-layout rate π is far from the 0.3–3% design range | Medium | Precision at fixed thresholds changes by up to 10 times | Measure π in phase 4 (section 11.5); priors are data, not code (CA-2). Trigger: π outside the range → re-fit the threshold table |
| R2 | Short words and acronyms are inherently ambiguous, so recall at a strict false-positive rate is limited | High (measured, section 18) | Missed corrections for 2–4 key words and for Russian acronyms typed on the English layout | Accept it: the manual hotkey and the run-based rule cover them; do not lower thresholds to chase recall |
| R3 | No realistic data in time | Medium | EV-1 cannot be proven | Start recruiting in phase 1; ship in suggestion mode if the set is late |
| R4 | The network does not beat the statistical baseline | Medium | Wasted training effort only | EV-12 chooses the baseline; the runtime already has it as the fall-back (section 13.5) |
| R5 | Text injection fails in some applications (lost or duplicated characters) | High | Severity-1 defects | Verification and rollback (RT-4); application blacklist; the end-to-end matrix is a gate |
| R6 | OS permissions and security software block the keystroke observer | Medium | Product unusable for a share of users | Signing, notarisation and a clear permission flow in the release checklist (section 13.4) |
| R7 | Licences of training sources block release | Medium | Data must be replaced | Licence register from phase 1; unknown licence = research only (section 8.7) |
| R8 | Latency target of the requester (100 ns) is taken as a requirement for the neural stage | Medium | Redesign pressure on a sound model | Section 7.5 explains what is and is not reachable; the table-look-up tier meets it, the network does not |
| R9 | Vocabulary drift (slang, new brands) | Certain | False-positive and miss rates rise over time | Quarterly lexicon refresh, retrain at least every 6 months (section 14.3) |
| R10 | Proxy-data numbers are mistaken for product numbers | Medium | Over-optimistic decisions | Every number from section 18 is labelled as proxy; the realistic set decides acceptance |

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

## 20. Reference implementation, formats and test vectors

### 20.1 Status, assembly and interface

**Status.** This section is normative (4.4). It is the executable form of every deterministic rule of sections 5, 7.7, 10 and 13: the key tables and tokens, segmentation, shape guards, calibration arithmetic, the priority matrix, the event machine, manual conversion, the EV-1 statistic, the baseline model and the two table formats. Where the prose of another section and this code disagree, the code and the vectors of 20.12 win, and the prose is a defect of the document that must be corrected. The classifier is injected as a function, so the same code runs with the network, with the baseline or with a stub.

**What is not here.** The operating-system adapters (event capture, layout detection, the context gate, the replacement transaction) cannot be written as portable code. Sections 13.1, 13.2, 13.7 and 13.8 specify them, and the event machine of 20.7 is the interface they drive. Training is specified in section 9. The forward pass of the network in 20.11 is a slow reference for tests; the production runtime uses a native implementation that is checked against it.

**Assembling the files.** The code blocks of 20.2 to 20.11 are consecutive parts of one Python 3.9+ module, `lfengine.py`, which uses only the standard library. Copy them in order into one file; each block starts with a marker comment `# ==== 20.n`. The vector generator of 20.12 is the second file, `vectors.py`. Run `python vectors.py > vectors_out.json` and compare the output with the expected JSON of 20.12. The property tests of 20.13 are the third file, conformance.py; python conformance.py prints OK. An implementation in another language is conformant when, for every entry of that JSON, its own function gives the same result: floats to the precision shown, hashes, token lists and byte counts exactly.

| Function or class | Part | Purpose |
| --- | --- | --- |
| `Key`, `render`, `token`, `tokens`, `keys_from_text` | 20.2 | Key tables, Caps Lock, rendering, model tokens |
| `candidate` | 20.3 | The single word candidate of a run for a target layout |
| `shape_guard` | 20.4 | URL, e-mail, dotted name, camelCase and key-walk guards |
| `score`, `deployment_prior`, `check_calibration_package`, `example_cal`, `cal_to_json`, `cal_from_json` | 20.5 | Temperature, priors, the score in nats, the calibration package |
| `decide` | 20.6 | The priority matrix of 10.4 for one run |
| `Engine` (`on_event`, `set_gate`, `undo`) | 20.7 | Buffer, run credit, resets, cool-down, decision at Space |
| `manual_convert` | 20.8 | Pure key-for-key conversion of a selection |
| `poisson_upper`, `ev1_bound`, `ev1_pass` | 20.9 | The EV-1 pass rule of 11.3 |
| `WittenBell`, `baseline_logits`, `lfb_pack`, `lfb_load`, `lfb_logp`, `lex_key`, `lfl_pack`, `lfl_load` | 20.10 | The baseline of 7.7 and the formats `LFB1`, `LFL1` |
| `lfw_pack`, `lfw_load`, `lfw_forward`, `toy_weights` | 20.11 | The format `LFW1`, a reference forward pass, deterministic toy weights |
| vectors.py (script) | 20.12 | Golden vectors for every function above, printed as one JSON document |
| conformance.py (script) | 20.13 | Property tests and the conformance checks CT-1 to CT-6 |

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
assert all(len(s) == 47 for pair in TABLE.values() for s in pair)

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


# Keys that are a letter in at least one layout (33 of 47). Caps Lock flips Shift on exactly these in the token.
LETTER_KEYS = frozenset(k for k in range(47) if is_letter_in(EN, k) or is_letter_in(RU, k))
assert len(LETTER_KEYS) == 33


def effective_shift(k: Key, layout: str) -> bool:
    """Case of the key as rendered in `layout`: Caps Lock flips Shift only on keys that are letters there."""
    return k.shift ^ (k.caps and is_letter_in(layout, k.id))


def render_key(k: Key, layout: str) -> str:
    return TABLE[layout][1 if effective_shift(k, layout) else 0][k.id]


def render(keys: Sequence[Key], layout: str) -> str:
    return "".join(render_key(k, layout) for k in keys)


def token(k: Key) -> int:
    """Layout-independent model token 1..94 = 1 + 2*id + effective shift."""
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


def check_calibration_package(cal: dict) -> None:
    """Load-time validation (CA-9). The nats range check catches the unit mix-up: a probability such as 0.995
    stored where nats are expected is far below 4.0 and is rejected."""
    for kind, tab in cal["lambda_nats"].items():
        for direction in ("en2ru", "ru2en"):
            for b in BUCKETS:
                lam = tab[direction][b]
                assert 4.0 <= lam <= 16.0, f"lambda_nats[{kind}][{direction}][{b}]={lam} outside [4, 16] nats"
    assert abs(sum(cal["pi_train"]) - 1.0) < 1e-9 and 0 < cal["o_lat"] < 1
    for a in (EN, RU):
        for st in STATES:
            assert 0.0005 <= cal["w"][a][st] <= 0.5, f"w[{a}][{st}] outside [0.0005, 0.5]"
        assert cal["w"][a]["run"] <= 0.3, "run prior above its cap 0.3"
    for kind in cal["lambda_nats"]:
        assert kind in cal["temperature"] and cal["temperature"][kind] > 0


RU_ALLOW = "на не но да по из за то ты мы вы он ли ну во со до от ни же бы".split()
EN_ALLOW = "of to in is it on at as be by or an if so do go he we me my no up us".split()


def example_cal() -> dict:
    """The starting values of 10.1 to 10.3 as a calibration package. A real package is fitted (10.3), not typed."""
    thr = {d: {"3-4": logit(0.999), "5-7": logit(0.997), "8+": logit(0.995)} for d in ("en2ru", "ru2en")}
    return {
        "temperature": {"network": 1.0, "ngram": 1.0},
        "pi_train": [0.38, 0.40, 0.22],
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


def cal_from_json(text: str) -> dict:
    cal = json.loads(text)
    cal["two_key_allow"] = {d: set(v) for d, v in cal["two_key_allow"].items()}
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
    s = score(scorer(tokens(cand.core, True)), active, cal, cal["w"][active][state], kind)
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
    kind: str                      # key | space | backspace | break | layout
    key: Optional[Key] = None      # for kind == key
    layout: Optional[str] = None   # layout id sampled at the event (key, space)
    ts_ms: int = 0


MAX_BUF = 64
RUN_CREDIT_MAX = 3
COOLDOWN_WORDS = 3
COOLDOWN_MS = 10_000
EVIDENCE_KEEP = {"user_exception", "acronym", "lexicon_active", "abstain"}   # KEEP reasons that end a run
GATE_ALLOW, GATE_DENY, GATE_UNKNOWN = "ALLOW", "DENY", "UNKNOWN"


class Engine:
    """Consumes events in arrival order; returns a Decision at each Space that ends a non-empty run.
    The event kinds: key (a printable main-block key), space (the decision point), backspace, layout (a manual
    layout change), break (click, focus change, paste, Enter, Tab, arrows, chords, IME, sleep, lock, ...)."""

    def __init__(self, cal, scorer, lexicon=None, exceptions=frozenset(), kind="network"):
        self.cal, self.scorer, self.lexicon, self.exceptions, self.kind = cal, scorer, lexicon or {}, exceptions, kind
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

    def set_gate(self, state: str):
        """Stage 0 verdict from the runtime. Anything but ALLOW discards the buffer and the run state."""
        self.gate = state
        if state != GATE_ALLOW:
            self._flush()
            self.skip, self.credit, self.after_switch = False, 0, False

    def undo(self, now_ms: int):
        """The user undid an automatic correction: run credit is lost and the cool-down starts."""
        self.credit = 0
        self.cool_words = COOLDOWN_WORDS
        self.cool_until_ms = now_ms + COOLDOWN_MS

    def on_event(self, ev: Event) -> Optional[Decision]:
        if self.gate != GATE_ALLOW:
            return None                                   # not stored, not counted, not classified
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
            return None
        if ev.kind == "layout":                           # manual layout change (the tool never changes it)
            if self.run:
                self._flush()
                self.skip = True
            self.after_switch = True
            self.credit = 0
            return None
        if ev.kind == "break":
            self._flush()
            self.skip, self.credit = False, 0
            return None
        if ev.kind == "space":
            return self._boundary(ev)
        raise ValueError(ev.kind)

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

`ev1_bound` and `ev1_pass` are the executable form of the rule of 11.3. A cluster is one (user, document) pair; the bound is the exact Poisson 95% upper limit for the number of clusters, multiplied by the size of the largest cluster and divided by the number of correct words. The per-user and per-document caps on the share of words (8.5) are applied to the data before these functions are called.

```python
# ==== 20.9 Acceptance statistics (EV-1) ===============================================================
def poisson_upper(k: int, conf: float = 0.95) -> float:
    """Exact one-sided upper limit mu with P(Poisson(mu) <= k) = 1 - conf."""
    lo, hi = 0.0, 10.0 + 10.0 * k
    for _ in range(200):
        mid = (lo + hi) / 2
        cdf = sum(math.exp(-mid + i * math.log(mid) - math.lgamma(i + 1)) for i in range(k + 1)) if mid > 0 else 1.0
        if cdf > 1 - conf:
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
            assert len({r[0] for r in ctxs}) == len(ctxs) and len({a for a, _ in pairs}) == len(pairs), "hash collision"
            out.append(struct.pack("<I", len(ctxs)) + b"".join(struct.pack("<QII", *r) for r in ctxs))
            out.append(struct.pack("<I", len(pairs)) + b"".join(struct.pack("<QII", a, n, 0) for a, n in pairs))
    return b"".join(out)


def lfb_load(b: bytes) -> dict:
    assert b[:4] == b"LFB1"
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
    assert off == len(b), "trailing bytes"
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


def lfl_load(b: bytes) -> Dict[str, HashedSet]:
    assert b[:4] == b"LFL1"
    (nt,) = struct.unpack_from("<I", b, 4)
    off, res, by_tag = 8, {}, {v: k for k, v in LEX_TAGS.items()}
    for _ in range(nt):
        tag, n = struct.unpack_from("<BI", b, off)
        off += 5
        res[by_tag[tag]] = HashedSet(tag, struct.unpack_from("<%dQ" % n, b, off))
        off += 8 * n
    assert off == len(b), "trailing bytes"
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


def lfw_load(b: bytes) -> dict:
    assert b[:4] == LFW_MAGIC
    ch, e, nc = struct.unpack_from("<III", b, 4)
    kernels = list(struct.unpack_from("<" + "I" * nc, b, 16))
    off = 16 + 4 * nc
    assert len(b) - off == 4 * lfw_size(ch, e, kernels), "size mismatch"

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

`vectors.py` imports `lfengine.py`, runs the functions of 20.2 to 20.11 on fixed inputs and prints one JSON document. The expected output is given below it. An implementation conforms when its own generator prints the same document: strings, integers, booleans, token lists, hashes and byte counts exactly; floats as printed, that is equal after rounding to the number of decimals shown. The output does not depend on the hash seed of the interpreter (CT-2). `sha256_16` is the first 16 hex digits of the SHA-256 of the file bytes.

| Key | What it pins down | Part |
| --- | --- | --- |
| `render`, `caps`, `prefix`, `tok25` | Typed keys to the text of the other layout, model tokens with and without `EOS`, Caps Lock per layout, the 20-key limit | 20.2 |
| `cands` | The single candidate: leading opener, core, trailing punctuation, the seven letter-keys, no candidate | 20.3 |
| `guards` | Reason codes of the shape guards | 20.4 |
| `priors`, `lambdas`, `scores`, `cal_json` | Prior vectors, thresholds in nats, the score, the bytes of the calibration package | 20.5 |
| `decide` | Rows 5 to 12 of the priority matrix with a stub scorer | 20.6 |
| `trace_run`, `trace_undo`, `scen` | Run credit, cool-down, boundaries, gate, layout change | 20.7 |
| `manual` | Manual conversion | 20.8 |
| `ev1`, `poisson` | The EV-1 pass rule | 20.9 |
| `wb`, `wb_score`, `fnv`, `lfl` | Baseline log-probabilities, `LFB1` and `LFL1` bytes, hash keys | 20.10 |
| `lfw` | `LFW1` toy weights and reference logits | 20.11 |

**How to read the traces.** In `trace_run` the word `ghbdtn` is converted in the state `default` and sets the run credit to 3; `z` (one key) is KEEP and leaves the credit at 3; the next three words are decided in the state `run` and lower the credit to 2, 1 and 0; the following `ntcn` is decided in the state `default` again and is KEEP (`abstain`, margin −2.707), so a chain of run-assisted conversions stops after three words. In `trace_undo` an undo at 1,000 ms makes the next words KEEP (`cooldown`) until 3 word decisions have been suppressed and 10,000 ms have passed; at 11,500 ms the same word converts again. In `scen`, Enter and Tab are context breaks and give no decision; a layout change inside a word drops the word; a Space read on another layout gives `layout_changed_at_boundary`; a closed gate stores nothing, and the first word after the gate reopens is decided normally; 65 keys give `overflow`; a second Space after a decision gives nothing.

```python
"""vectors.py - generates the golden test vectors of section 20.12 from lfengine.py.
Run:  python vectors.py > vectors_out.json   (lfengine.py in the same directory; standard library only)."""
import sys, json, math, hashlib, struct; sys.path.insert(0, ".")
import lfengine as L
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
def dumps(v):
    return json.dumps(v, ensure_ascii=False)
def block(v):    # valid JSON, one row per line
    if isinstance(v, list) and v and isinstance(v[0], list):
        return "[\n" + ",\n".join(" " + dumps(r) for r in v) + "\n]"
    if isinstance(v, dict):
        return "{\n" + ",\n".join(" " + dumps(k) + ": " + dumps(x) for k, x in v.items()) + "\n}"
    return dumps(v)
sys.stdout.write("{\n" + ",\n".join(dumps(k) + ": " + block(v) for k, v in out.items()) + "\n}\n")
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
 ["ghbdtn @11500", "CONVERT", "score_above_threshold", 3]
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
 "bytes": 1261,
 "sha256_16": "3b11d4012da7da1d"
}
}
```

### 20.13 Conformance tests

An implementation of the engine, in any language and on any platform, is conformant when it passes the six checks below. The vectors of 20.12 pin the exact values; the property tests pin the rules that no finite list of vectors can; the last two checks tie the production code to the reference.

| ID | Check |
| --- | --- |
| CT-1 | Every entry of the expected JSON of 20.12 is reproduced: strings, integers, booleans, token lists, hashes and byte counts exactly; floats equal after rounding to the number of decimals printed. |
| CT-2 | The output is deterministic. The reference generator prints byte-identical output on every run, on every Python from 3.9 upwards and for every value of `PYTHONHASHSEED`; no result depends on the iteration order of a set or a dictionary. |
| CT-3 | The property tests of `conformance.py` below pass: 200,000 random key runs (no key lost or duplicated by the candidate, core made of letters only, at most one leading and two trailing marks), priors that sum to 1, a probability stored where nats are expected is refused, the `LFB1` round trip, and the `LFW1` size rule of MD-14. |
| CT-4 | With the real lexicon of 8.9: no word of the 20,000 most frequent word forms of either language, typed on its own layout, has a core shorter than the whole run, and every Russian word of that list that uses only keys of the Russian layout, typed on the English layout, comes back from `candidate` with its whole run as core. A failure is a defect of the segmentation, not of the lexicon (the seven letter-keys, 5.3). |
| CT-5 | The runtime meets MD-12 (baseline log-probabilities within 1e-9 of the reference) and MD-14 (network logits within 1e-5 on the toy weights of 20.12 and within 1e-4 on at least 100,000 key sequences of the exported network). |
| CT-6 | A change of the code of 20.2 to 20.11 that changes any entry of 20.12 is a change of this specification: the expected output of 20.12 is updated in the same revision. |

CT-1 to CT-3 need only the files of this section. CT-4 needs the lexicon built by D3, so it belongs to the build of the tables, not to the unit tests of the engine.

```python
"""conformance.py - property tests of section 20.13 (standard library only).
Usage: python conformance.py   (in the folder that holds lfengine.py; prints OK or raises AssertionError)"""
import sys, random, math; sys.path.insert(0, ".")
import lfengine as L

R = random.Random(1)
for _ in range(200_000):                                  # P1: tokens, rendering, candidate
    run = [L.Key(R.randrange(47), R.random() < .5, R.random() < .3) for _ in range(R.randrange(1, 12))]
    assert all(1 <= L.token(k) <= 94 for k in run)
    for lay in ("en", "ru"):
        txt = L.render(run, lay)
        assert L.render([L.Key(k.id, L.effective_shift(k, lay)) for k in run], lay) == txt
        assert L.render(L.keys_from_text(txt, lay), lay) == txt
    for tgt in ("en", "ru"):
        c = L.candidate(run, tgt)
        if c:
            assert c.lead + c.core + c.trail == tuple(run)                       # no key lost or duplicated
            assert len(c.lead) <= 1 and len(c.trail) <= 2 and len(c.core) >= 1
            assert all(L.is_letter_in(tgt, k.id) for k in c.core)                # the core is letters only

for a in ("en", "ru"):                                    # P2: every prior is a probability vector
    for st in L.STATES:
        cal = L.example_cal()
        assert abs(sum(L.deployment_prior(a, cal["w"][a][st], cal["o_lat"])) - 1) < 1e-12

cal = L.example_cal()                                     # P3: a probability stored where nats are expected is refused
bad = L.example_cal(); bad["lambda_nats"]["network"]["en2ru"]["5-7"] = 0.997
try:
    L.check_calibration_package(bad); raise SystemExit("unit mix-up not caught")
except AssertionError:
    pass

rows = [[L.BOS] + [L.token(L.Key(R.randrange(47), R.random() < .3)) for _ in range(R.randrange(2, 9))] + [L.EOS]
        for _ in range(300)]                              # P4: LFB1 round trip equals the in-memory model
ms = [L.WittenBell().fit(rows[i::3]) for i in range(3)]
pkg = L.lfb_load(L.lfb_pack(ms, [math.log(x) for x in cal["pi_train"]]))
assert max(abs(L.lfb_logp(pkg, c, r) - ms[c].logp(r)) for c in range(3) for r in rows[:100]) < 1e-12

tw = L.toy_weights()                                      # P5: LFW1 size is header + 4 bytes per parameter; three finite logits
assert len(tw) == 16 + 4 * 3 + 4 * L.lfw_size(4, 4, (3, 5, 3))
out = L.lfw_forward(L.lfw_load(tw), L.tokens(L.keys_from_text("ghbdtn", "en")))
assert len(out) == 3 and all(math.isfinite(v) for v in out)
print("OK")
```
