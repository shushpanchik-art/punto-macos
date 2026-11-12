'use strict';
const fs = require('fs');
const path = require('path');
const C = require('./lfcore.js');
const S = require('./lfstats.js');
let E = null, X = null;
try { E = require('./lfengine.js'); } catch (e) { E = null; }
try { X = require('./lftx.js'); } catch (e) { X = null; if (process.env.DEBUG) console.error(e); }
const EXP = JSON.parse(fs.readFileSync(path.join(__dirname, 'expected.json'), 'utf8'));

const rnd = (x, d) => (x === null || x === undefined ? x : Number(x.toFixed(d)));
function eq(a, b) {
  if (typeof a === 'number' && typeof b === 'number') return Math.abs(a - b) <= 1e-12 * Math.max(1, Math.abs(b));
  if (Array.isArray(a) && Array.isArray(b)) return a.length === b.length && a.every((x, i) => eq(x, b[i]));
  if (a && b && typeof a === 'object' && typeof b === 'object') {
    const ka = Object.keys(a).sort(), kb = Object.keys(b).sort();
    return ka.length === kb.length && ka.every((k, i) => k === kb[i] && eq(a[k], b[k]));
  }
  return a === b;
}
const K = C.keysFromText;
const cal = C.exampleCal();
const results = {};   // key -> {total, pass, notes[]}
function check(key, label, got, exp) {
  const r = results[key] || (results[key] = { total: 0, pass: 0, fails: [] });
  r.total++;
  let ok = false;
  try { ok = eq(got, exp); } catch (e) { ok = false; }
  if (ok) r.pass++; else r.fails.push(`${label}: got ${JSON.stringify(got)} expected ${JSON.stringify(exp)}`);
}
function guard(key, fn) { try { fn(); } catch (e) { const r = results[key] || (results[key] = { total: 0, pass: 0, fails: [] }); r.fails.push('EXCEPTION ' + (e && e.stack ? e.stack.split('\n').slice(0, 3).join(' | ') : e)); if (!r.total) r.total = EXP[key] ? (Array.isArray(EXP[key]) ? EXP[key].length : Object.keys(EXP[key]).length) : 1; } }
const lab = (r) => JSON.stringify(r[0]).slice(0, 60);

// ---------- part 1 ----------
guard('render', () => {
  EXP.render.forEach((row) => {
    const [typed, lay] = row; const keys = K(typed, lay);
    check('render', typed, [typed, lay, C.render(keys, C.OTHER_LAYOUT[lay]), C.tokens(keys)], row);
  });
});
guard('caps', () => {
  EXP.caps.forEach((row) => { const [kid, sh, cp] = row; const k = new C.Key(kid, sh, cp);
    check('caps', lab(row), [kid, sh, cp, C.renderKey(k, 'en'), C.renderKey(k, 'ru'), C.token(k)], row); });
});
guard('caps_all', () => {
  EXP.caps_all.forEach((row) => { const [kid, sh, cp] = row; const k = new C.Key(kid, sh, cp);
    check('caps_all', lab(row), [kid, sh, cp, C.renderKey(k, 'en'), C.renderKey(k, 'ru'), C.token(k)], row); });
});
guard('prefix', () => check('prefix', 'prefix', C.tokens(K('ghb', 'en'), false), EXP.prefix));
guard('tok25', () => check('tok25', 'tok25', C.tokens(Array.from({ length: 25 }, (_, i) => new C.Key(i % 47))).length, EXP.tok25));

// ---------- part 2 ----------
guard('cands', () => {
  const inputs = [['Ghbdtn?', 'en', 'ru'], ['Ghbdtn?!', 'en', 'ru'], ['(ghbdtn)', 'en', 'ru'], ['k.,k.', 'en', 'ru'], ['[jhjij', 'en', 'ru'], ['руддщ,', 'ru', 'en'], ['(руддщ)', 'ru', 'en'], ['руддщб', 'ru', 'en'], ['руддщ..', 'ru', 'en'], ['ghb1', 'en', 'ru'], [',', 'en', 'ru'], ['"ghbdtn"', 'en', 'ru'], ['hello,', 'en', 'ru'], ['Ghbdtn,', 'en', 'ru']];
  inputs.forEach(([typed, lay, tgt], i) => {
    const c = C.candidate(K(typed, lay), tgt);
    check('cands', typed, [typed, tgt, c === null ? null : [C.render(c.lead, tgt), C.render(c.core, tgt), C.render(c.trail, tgt)]], EXP.cands[i]);
  });
});
guard('guards', () => {
  const inputs = [['github.com', 'en'], ['https://x.io', 'en'], ['user@example.com', 'en'], ['MyVariable', 'en'], ['asdfgh', 'en'], ['фывапр', 'ru'], ['kubectl', 'en'], ['ghbdtn', 'en']];
  inputs.forEach(([typed, act], i) => {
    const run = K(typed, act); const cand = C.candidate(run, C.OTHER_LAYOUT[act]);
    check('guards', typed, [typed, act, cand ? C.shapeGuard(run, act, cand.core) : 'no_candidate'], EXP.guards[i]);
  });
});
guard('manual', () => {
  ['Ghbdtn? Rfr ltkf?', 'Привет, как дела?', '123', 'ghbdtn 😀', 'ЁЖ ёж', 'Hello, Привет'].forEach((t, i) => {
    check('manual', t, [t, ...C.manualConvert(t)], EXP.manual[i]);
  });
});

// ---------- part 3 ----------
guard('priors', () => {
  let i = 0;
  for (const a of ['en', 'ru']) for (const st of C.STATES) {
    const w = cal.w[a][st]; const v = C.deploymentPrior(a, w, cal.o_lat);
    check('priors', a + st, [a, st, w, v.map((x) => rnd(x, 4))], EXP.priors[i++]);
  }
});
guard('lambdas', () => [0.9995, 0.999, 0.997, 0.995, 0.99, 0.9].forEach((t, i) => check('lambdas', String(t), [t, rnd(C.logit(t), 3)], EXP.lambdas[i])));
guard('scores', () => {
  const inp = [[[-3, 9, -2], 'en', 'default'], [[-3, 9, -2], 'en', 'run'], [[-3, 9, -2], 'en', 'after_switch'], [[8, -3, -2], 'ru', 'default'], [[-2, -3, 8], 'ru', 'default'], [[8, -3, -2], 'en', 'default']];
  inp.forEach(([z, a, st], i) => check('scores', JSON.stringify(z) + a + st, [z, a, st, rnd(C.score(z, a, cal, cal.w[a][st]), 3)], EXP.scores[i]));
});
guard('decide', () => {
  const lex = { en: new Set(['hello', 'the']), ru: new Set(['привет']), acr_en: new Set(['sql']), acr_ru: new Set(['мтс']) };
  const cases = [['ghbdtn', 'en', [-3, 9, -2], 'default', false, []], ['ghbdtn', 'en', [-3, 8, -2], 'default', false, []], ['ghbdtn', 'en', [-3, 8, -2], 'run', true, []], ['ghbdtn', 'en', [-3, 9, -2], 'default', false, [['en2ru', 'ghbdtn']]], ['hello', 'en', [-3, 9, -2], 'default', false, []], ['z', 'en', [-3, 9, -2], 'default', false, []], ['ye', 'en', [-3, 9, -2], 'default', false, []], ['ye', 'en', [-3, 9, -2], 'run', true, []], ['github.com', 'en', [-3, 9, -2], 'default', false, []], ['руддщ', 'ru', [9, -3, -2], 'default', false, []], ['руддщ,', 'ru', [9, -3, -2], 'default', false, []], ['привет', 'ru', [9, -3, -2], 'default', false, []], ['Ghbdtn?', 'en', [-3, 9, -2], 'default', false, []]];
  cases.forEach(([typed, act, z, st, ra, ex], i) => {
    const exs = new Set(ex.map(([d, w]) => d + '\u0000' + w));
    const d = C.decide(K(typed, act), act, cal, () => z, st, ra, exs, lex);
    check('decide', typed + st, [typed, act, z, st, ra, ex.length > 0, d.action, d.reason, d.replacement, rnd(d.margin, 3), d.n_keys], EXP.decide[i]);
  });
});

// ---------- part 4 ----------
guard('poisson', () => { const g = [0, 1, 2, 3, 4, 5].map((k) => rnd(S.poissonUpper(k), 4)); EXP.poisson.forEach((e, i) => check('poisson', 'k=' + i, g[i], e)); });
guard('ev1', () => {
  const cl = (n) => Array.from({ length: n }, (_, i) => ['u' + i, 'd' + i]);
  const cases = [['a', cl(4), 100000, 20, 100], ['b', Array(4).fill(['u1', 'd1']), 100000, 20, 100], ['c', [], 100000, 20, 100], ['d', [], 99999, 20, 100], ['e', [], 200000, 19, 100], ['f', cl(5), 150000, 20, 100], ['g', [['u1', 'd1'], ['u1', 'd1'], ['u2', 'd2'], ['u2', 'd2']], 100000, 20, 100]];
  cases.forEach(([nm, f, n, u, d], i) => check('ev1', EXP.ev1[i][0], [EXP.ev1[i][0], S.ev1Pass(f, n, u, d), rnd(S.ev1Bound(f, n), 7)], EXP.ev1[i]));
});
guard('fnv', () => {
  const b = (s) => Buffer.from(s);
  const g = [['', S.hex(S.fnv1a64(b('')))], ['a', S.hex(S.fnv1a64(b('a')))], ['foobar', S.hex(S.fnv1a64(b('foobar')))], ['ctx_key(2,(95,61))', S.hex(S.ctxKey(2, [95, 61]))], ['pair_key(2,(95,61),63)', S.hex(S.pairKey(2, [95, 61], 63))]];
  g.forEach((r, i) => check('fnv', r[0], r, EXP.fnv[i]));
});
const trainset = () => {
  const row = (w, lay) => C.tokens(K(w, lay));
  return [['hello', 'hell', 'help', 'hero', 'world', 'word'].map((w) => row(w, 'en')), ['привет', 'привал', 'приказ', 'пригород', 'мир', 'мирно'].map((w) => row(w, 'ru')), ['kubectl', 'github', 'asdfgh', 'docker', 'nginx', 'vim'].map((w) => row(w, 'en'))];
};
let WBPAD = false;
guard('wb', () => {
  const ts = trainset();
  const ms = ts.map((r) => new S.WittenBell(WBPAD).fit(r));
  const test = C.tokens(K('ghbdtn', 'en'));
  const pt = C.piTrain(cal); const lp = pt.map(Math.log);
  const lg = ms.map((m, c) => m.logp(test) + lp[c]);
  const W = EXP.wb;
  check('wb', 'logp_by_class', ms.map((m) => rnd(m.logp(test), 6)), W.logp_by_class);
  check('wb', 'logits', lg.map((x) => rnd(x, 6)), W.logits);
  check('wb', 'hello_ru', rnd(ms[1].logp(C.tokens(K('hello', 'en'))), 6), W.hello_ru);
  check('wb', 'hello_en', rnd(ms[0].logp(C.tokens(K('hello', 'en'))), 6), W.hello_en);
  check('wb', 'n_pairs', ms.map((m) => m.nPairs()), W.n_pairs);
  check('wb', 'test_word_keys', 'ghbdtn', W.test_word_keys);
  check('wb', 'lfb_logp (= logp; the LFB1 round trip itself is not testable)', ms.map((m) => rnd(m.logp(test), 6)), W.lfb_logp);
  check('wb', 'lfb_bytes (LFB1 layout not in text)', null, W.lfb_bytes);
  check('wb', 'lfb_sha256_16 (LFB1 layout not in text)', null, W.lfb_sha256_16);
  const lg2 = ms.map((m, c) => m.logp(test) + lp[c]);
  check('wb_score', 'wb_score', rnd(C.score(lg2, 'en', { ...cal, temperature: { network: 1, ngram: 1 } }, 0.01, 'ngram'), 3), EXP.wb_score);
});
guard('lfl', () => {
  const L = EXP.lfl;
  check('lfl', 'key lex_en hello', S.hex(S.lexKey(1, 'hello')), L.keys[0][2]);
  check('lfl', 'key lex_ru привет', S.hex(S.lexKey(2, 'привет')), L.keys[1][2]);
  check('lfl', 'key acr_ru МТС', S.hex(S.lexKey(4, 'МТС')), L.keys[2][2]);
  const set = new Set(['hello', 'the', 'world'].map((s) => S.lexKey(1, s)));
  check('lfl', 'member HELLO', set.has(S.lexKey(1, 'HELLO')), L.member[0][2]);
  check('lfl', 'member hi', set.has(S.lexKey(1, 'hi')), L.member[1][2]);
  const as = new Set(['SQL'].map((s) => S.lexKey(3, s)));
  check('lfl', 'member sql', as.has(S.lexKey(3, 'sql')), L.member[2][2]);
  check('lfl', 'bytes (LFL1 layout not in text)', null, L.bytes);
  check('lfl', 'sha256_16 (LFL1 layout not in text)', null, L.sha256_16);
});
guard('lfw', () => {
  ['bytes', 'sha256_16', 'logits_ghbdtn', 'logits_hello', 'first_floats'].forEach((k) => check('lfw', k + ' (LFW1 layout and toy_weights not in text)', null, EXP.lfw[k]));
});
guard('cal_json', () => { ['bytes', 'sha256_16'].forEach((k) => check('cal_json', k + ' (LFC1 serialisation not in text)', null, EXP.cal_json[k])); });

// ---------- part 3b / 5 (engine, transactions) ----------
if (E) E.runEngineVectors({ check, guard, EXP, C, cal, rnd, results });
if (X) X.runTxVectors({ check, guard, EXP, C, results });

// ---------- report ----------
const order = ['render', 'caps', 'caps_all', 'prefix', 'tok25', 'cands', 'guards', 'manual', 'priors', 'lambdas', 'scores', 'decide', 'trace_run', 'scen', 'trace_undo', 'undo', 'ev1', 'poisson', 'fnv', 'wb', 'wb_score', 'lfw', 'lfl', 'cal_json', 'modes', 'outcome', 'tx', 'fingerprint', 'hook'];
let tp = 0, tt = 0;
for (const k of order) {
  const r = results[k];
  if (!r) { console.log(`${k.padEnd(12)} NOT RUN (0/${Array.isArray(EXP[k]) ? EXP[k].length : 1})`); tt += Array.isArray(EXP[k]) ? EXP[k].length : 1; continue; }
  tp += r.pass; tt += r.total;
  console.log(`${k.padEnd(12)} ${r.pass === r.total ? 'PASS' : 'FAIL'} ${r.pass}/${r.total}`);
  if (process.argv.includes('-v')) r.fails.forEach((f) => console.log('    - ' + f));
}
console.log(`TOTAL ${tp}/${tt}`);
