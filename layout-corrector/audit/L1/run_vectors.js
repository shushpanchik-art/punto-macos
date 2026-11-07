'use strict';
// Recomputes every key of the expected JSON of spec 20.12 (read from spec_without_code.md) and compares.
// Usage: node run_vectors.js [-v]   (-v prints each failing entry)
const K = require('./lf_keys.js');
const C = require('./lf_cand.js');
const A = require('./lf_cal.js');
const S = require('./lf_stats.js');
const AD = require('./lf_adapter.js');
const SC = require('./lf_scen.js');
const M = require('./lf_more.js');
const { loadExpected } = require('./expected.js');
const E = loadExpected();
const VERBOSE = process.argv.includes('-v');
const J = (x) => JSON.stringify(x);
const rows = [];
function key(name, total, pass, note) { rows.push({ name, total, pass, note: note || '' }); }
function each(name, list, fn, note) {
  let pass = 0; const bad = [];
  list.forEach((e, i) => { let ok = false, got; try { const r = fn(e, i); ok = r === true || (r && r.ok === true); got = r && r.got; } catch (err) { got = 'EXC ' + err.message; } if (ok) pass++; else bad.push([e, got]); });
  key(name, list.length, pass, note);
  if (VERBOSE) for (const [e, g] of bad) console.log('   fail', name, J(e).slice(0, 120), '->', J(g));
}
const near = (a, b, d) => a !== null && b !== null && Number(a.toFixed(d)) === b;

// ---- part 1
each('render', E.render, ([text, lay, rendered, toks]) => { const ks = K.keysFromText(text, lay); return K.render(ks, K.other(lay)) === rendered && J(K.tokens(ks)) === J(toks); });
each('caps', E.caps, ([k, sh, caps, en, ru, tk]) => { const key = new K.Key(k, sh, caps, 'en'); return K.renderKey(key, 'en') === en && K.renderKey(key, 'ru') === ru && K.token(key) === tk; });
each('caps_all', E.caps_all, ([k, sh, caps, en, ru, tk]) => { const key = new K.Key(k, sh, caps, 'en'); return K.renderKey(key, 'en') === en && K.renderKey(key, 'ru') === ru && K.token(key) === tk; });
// prefix / tok25: the JSON holds only the output; the INPUT ('ghb' and a 25-key word) is guessed (see report)
key('prefix', 1, J(K.tokens(K.keysFromText('ghb', 'en'), false)) === J(E.prefix) ? 1 : 0, 'input "ghb" guessed from the tokens');
key('tok25', 1, K.tokens(Array.from({ length: 25 }, (_, i) => new K.Key(i, false, false, 'en'))).length === E.tok25 ? 1 : 0, 'input (25 keys) and the cut rule guessed; only the length 21 is pinned');

// ---- part 2
each('cands', E.cands, ([text, T, exp]) => { const c = C.candidate(K.keysFromText(text, K.other(T)), T); return J(c ? [c.opener, c.core, c.marks] : null) === J(exp); }, 'column 2 = TARGET layout T (undocumented)');
each('guards', E.guards, ([text, A_, exp]) => { const ks = K.keysFromText(text, A_); const c = C.candidate(ks, K.other(A_)); return (c ? C.shapeGuard(ks) : 'no_candidate') === exp; }, 'column 2 = ACTIVE layout (differs from cands); suffix list is a guess');
each('manual', E.manual, ([text, dir, out]) => { const [d, o] = C.manualConvert(text); return d === dir && o === out; });

// ---- part 3
each('priors', E.priors, ([lay, st, w, vec]) => A.W[st] === w && J(A.deploymentPrior(lay, w).map(A.r4)) === J(vec));
each('lambdas', E.lambdas, ([t, nats]) => A.r3(A.logit(t)) === nats);
each('scores', E.scores, ([z, lay, st, s]) => A.r3(A.score(z, lay, st, A.exampleCal)) === s, 'needs T=1 and class mix 38/40/22 (T is not in the text)');
each('decide', E.decide, ([text, lay, z, st, credPos, exc, act, reason, repl, margin, n]) => {
  const ks = K.keysFromText(text, lay);
  const exceptions = new Set(exc ? [(lay === 'en' ? 'en2ru' : 'ru2en') + '|' + A.fold(text)] : []);
  const d = A.decide(ks, lay, A.exampleCal, () => z, st, credPos ? 3 : 0, exceptions);
  return J([d.action, d.reason, d.replacement, d.margin === null ? null : A.r3(d.margin), d.nKeys]) === J([act, reason, repl, margin, n]);
}, 'columns 4-6 (state, credit>0, exception) undocumented');
{
  const tr = SC.traceRun('fixed');
  each('trace_run', E.trace_run, (e, i) => J(tr[i]) === J(e), 'stimulus words from the vector; scorer stub needs a 5-key rule, see report');
  const tu = SC.traceUndo('fixed');
  each('trace_undo', E.trace_undo, (e, i) => J(tu[i]) === J(e), 'event timing designed from the names');
  const sc = SC.scenarios();
  each('scen', E.scen, ([name, exp]) => J(sc[name]) === J(exp), 'event sequences designed from the names');
}

// ---- part 4
each('ev1', E.ev1, ([name, pass, bound]) => { const r = M.ev1(name, true); return r !== null && r[0] === pass && r[1] === bound; }, 'inputs live in the name only; m floored at 1, n for "19 users" inferred');
each('poisson', E.poisson, (v, c) => Number(S.poissonUpper(c).toFixed(4)) === v);
each('fnv', E.fnv, ([label, hex]) => {
  if (label === '') return S.hex(S.fnv1a64([])) === hex;
  if (label === 'a' || label === 'foobar') return S.hex(S.fnv1a64(S.utf8(label))) === hex;
  if (label === 'ctx_key(2,(95,61))') return S.hex(S.ctxKey(2, [95, 61])) === hex;
  if (label === 'pair_key(2,(95,61),63)') return S.hex(S.pairKey(2, [95, 61], 63)) === hex;
  return false;
}, 'one byte per token assumed (confirmed)');
{ // lfl: only the hash keys and membership can be rebuilt; the 84 bytes of the file cannot
  const L = E.lfl; const tagOf = { hello: 'lex_en', 'привет': 'lex_ru', 'МТС': 'acr_ru' };
  let pass = 0, total = L.keys.length;
  for (const [tag, w, hex] of L.keys) if (S.hex(M.lexKey(tag, w)) === hex) pass++;
  const set = { lex_en: new Set([M.lexKey('lex_en', 'hello')].map(String)), lex_ru: new Set([M.lexKey('lex_ru', 'привет')].map(String)), acr_ru: new Set([M.lexKey('acr_ru', 'МТС')].map(String)), acr_en: new Set([M.lexKey('acr_en', 'sql')].map(String)) };
  for (const [tag, w, exp] of L.member) { total++; if ((set[tag].has(String(M.lexKey(tag, w)))) === exp) pass++; }
  total += 2; // bytes (84) and sha256_16 of the LFL1 file: NOT reproducible (format not in the text)
  key('lfl', total, pass, 'keys+membership only; bytes/sha not derivable (format and lex_key are not in the text)');
}
{ // wb_score: the logits are given IN the vector, so only score() with kind ngram is needed (T=1 again assumed)
  const z = E.wb.logits; key('wb_score', 1, A.r3(A.score(z, 'en', 'default', A.exampleCal)) === E.wb_score ? 1 : 0, 'uses the logits stored in wb; T=1 assumed');
}
{ // wb: only logits = logp_by_class + ln(class mix) can be rebuilt from the vector's own numbers; the rest (8 fields) cannot
  const mix = [38, 40, 22].map((x) => x / 100); const lg = E.wb.logp_by_class.map((x, i) => Number((x + Math.log(mix[i])).toFixed(6)));
  key('wb', 9, J(lg) === J(E.wb.logits) ? 1 : 0, 'NOT REACHED except logits=logp+ln(mix): Witten-Bell (7.7), the S-TRAIN fixture and the LFB1 layout are not in the text');
}
key('lfw', 5, 0, 'NOT REACHED: toy_weights and LFW1 header layout are not in the text');
key('cal_json', 2, 0, 'NOT REACHED: schema LFC1 / JSON serialisation of 20.5 are not in the text');

// ---- part 5
each('undo', E.undo, (e, i) => { const got = M.undoScenarios()[i]; return J(got) === J(e); }, 'column meaning of steps 1-2 guessed (true / 3 / false)');
each('modes', E.modes, ([name, caps, status, facts, mode]) => AD.engineMode(caps, status, facts) === mode);
each('outcome', E.outcome, ([began, o, n, r, okv, exp]) => AD.classifyOutcome(began, o, n, r, okv) === exp);
each('tx', E.tx, ([name, caps, text, faults, ahead, extra, outcome, reason, final, incident]) => {
  const f = new AD.SimField(text, caps, faults);
  const word = 'ghbdtn';
  const r = AD.runTransaction(f, caps, word, K.render(K.keysFromText(word, 'en'), 'ru'), ahead, extra);
  return r.outcome === outcome && r.reason === reason && r.text === final && r.incident === incident;
}, 'SimField fault semantics inferred from names and final texts');
each('fingerprint', E.fingerprint, ([name, digest, lay]) => {
  if (name === 'en' || name === 'ru') return M.fpVariant(name) === digest && AD.identifyLayout(digest) === lay;
  const v = M.fpVariant(name); const arr = Array.isArray(v) ? v : [v];
  return arr.includes(digest) && AD.identifyLayout(digest) === lay;
}, 'the two modified tables: edit rule and rotation direction guessed, digest recomputed');
{
  const hs = M.hookScenarios();
  each('hook', E.hook, (e, i) => { const g = hs[i]; const exp = [e[0], e[1], e[2], e.length > 3 ? e[3] : null]; return J(g) === J(exp); }, 'stimuli designed from the names; reason element sometimes omitted, sometimes null');
}

// ---- output
const w = Math.max(...rows.map((r) => r.name.length));
let P = 0, T = 0, keysPass = 0;
for (const r of rows) {
  const ok = r.pass === r.total; if (ok) keysPass++; P += r.pass; T += r.total;
  console.log((ok ? 'PASS ' : 'FAIL ') + r.name.padEnd(w) + ' ' + String(r.pass).padStart(3) + '/' + String(r.total).padEnd(3) + (r.note ? '  # ' + r.note : ''));
}
console.log(`TOTAL entries ${P}/${T}; keys fully passing ${keysPass}/${rows.length}`);
const missing = Object.keys(E).filter((k) => !rows.some((r) => r.name === k));
if (missing.length) console.log('JSON keys without a check: ' + missing.join(', '));
