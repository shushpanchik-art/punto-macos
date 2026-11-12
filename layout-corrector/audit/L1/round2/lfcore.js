'use strict';
// Blind re-implementation (audit lane L1, round 2): key tables, tokens, candidate, guards,
// priors, score, decide, manual conversion. Written from the specification text only.

// ---- 19.1 physical key map (typed from the table in the spec) ----
const EN0 = Array.from("`1234567890-=qwertyuiop[]\\asdfghjkl;'zxcvbnm,./");
const EN1 = Array.from('~!@#$%^&*()_+QWERTYUIOP{}|ASDFGHJKL:"ZXCVBNM<>?');
const RU0 = Array.from('ё1234567890-=йцукенгшщзхъ\\фывапролджэячсмитьбю.');
const RU1 = Array.from('Ё!"№;%:?*()_+ЙЦУКЕНГШЩЗХЪ/ФЫВАПРОЛДЖЭЯЧСМИТЬБЮ,');
const TABLE = { en: [EN0, EN1], ru: [RU0, RU1] };
const OTHER_LAYOUT = { en: 'ru', ru: 'en' };
const BOS = 95, EOS = 96;

const isAlpha = (ch) => /^[A-Za-zЀ-ӿ]$/.test(ch);
// letter-ness of a key on a layout: decided from the unshifted character
const LETTER = { en: EN0.map(isAlpha), ru: RU0.map(isAlpha) };
// L: keys that are a letter in at least one layout
const L_SET = new Set();
for (let i = 0; i < 47; i++) if (LETTER.en[i] || LETTER.ru[i]) L_SET.add(i);

class Key {
  constructor(id, shift = false, caps = false) { this.id = id; this.shift = !!shift; this.caps = !!caps; }
}
function renderKey(k, layout) {
  const s = k.shift !== (k.caps && LETTER[layout][k.id]);
  return TABLE[layout][s ? 1 : 0][k.id];
}
function token(k) {
  const s = k.shift !== (k.caps && L_SET.has(k.id));
  return 1 + 2 * k.id + (s ? 1 : 0);
}
function render(keys, layout) { return keys.map((k) => renderKey(k, layout)).join(''); }
function tokens(keys, complete = true) {
  const t = [BOS];
  const first = keys.slice(0, 20).map(token);
  for (const x of first) t.push(x);
  if (complete && keys.length <= 20) t.push(EOS);
  return t;
}
const REV = { en: new Map(), ru: new Map() };
for (const lay of ['en', 'ru']) for (let s = 0; s < 2; s++) for (let i = 0; i < 47; i++) {
  const ch = TABLE[lay][s][i];
  if (!REV[lay].has(ch)) REV[lay].set(ch, [i, s === 1]);
}
function keysFromText(text, layout) {
  const out = [];
  for (const ch of text) {
    const r = REV[layout].get(ch);
    if (!r) throw new Error('char not on layout: ' + ch);
    out.push(new Key(r[0], r[1], false));
  }
  return out;
}

// ---- 5.3 candidate ----
const OPEN = new Set(['(', '[', '{', '"', "'"]);
const CLOSE = new Set(['.', ',', ';', ':', '!', '?', '"', "'", ')', ']', '}']);
function candidate(run, tgt) {
  const n = run.length;
  if (!n) return null;
  const ch = run.map((k) => renderKey(k, tgt));
  const let_ = run.map((k) => LETTER[tgt][k.id]);
  let lead = 0;
  if (OPEN.has(ch[0]) && !let_[0]) lead = 1;
  let end = n, trail = 0;
  while (trail < 2 && end - 1 >= lead && CLOSE.has(ch[end - 1]) && !let_[end - 1]) { end--; trail++; }
  const core = run.slice(lead, end);
  if (!core.length) return null;
  for (let i = lead; i < end; i++) if (!let_[i]) return null;
  return { lead: run.slice(0, lead), core, trail: run.slice(end) };
}

// ---- 20.4 shape guards (rules reconstructed from the prose of 13.1; code block removed) ----
const SUFFIXES = ['com', 'org', 'net', 'io', 'ru', 'ua', 'de', 'uk', 'edu', 'gov', 'info', 'dev', 'app', 'txt', 'py', 'js', 'ts', 'md', 'json', 'html', 'css', 'pdf', 'exe', 'zip', 'png', 'jpg', 'doc', 'docx', 'xls', 'csv', 'cpp', 'java', 'sh', 'rs', 'go'];
const ROWS = [[0, 12], [13, 25], [26, 36], [37, 46]];
function rowOf(id) { for (let r = 0; r < ROWS.length; r++) if (id >= ROWS[r][0] && id <= ROWS[r][1]) return r; return -1; }
function keywalk(run) {
  let up = 1, down = 1;
  for (let i = 1; i < run.length; i++) {
    const a = run[i - 1].id, b = run[i].id;
    up = (b === a + 1 && rowOf(a) === rowOf(b)) ? up + 1 : 1;
    down = (b === a - 1 && rowOf(a) === rowOf(b)) ? down + 1 : 1;
    if (up >= 4 || down >= 4) return true;
  }
  return false;
}
function shapeReason(text) {
  if (text.includes('://') || /(^|[^A-Za-z0-9])www\./i.test(text)) return 'shape_url';
  if (/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(text)) return 'shape_email';
  const m = /^[\p{L}\p{N}_-]+(\.[\p{L}\p{N}_-]+)*\.([A-Za-z]+)$/u.exec(text);
  if (m && SUFFIXES.includes(m[2].toLowerCase())) return 'shape_dotted';
  if (/[a-zа-яё][A-ZА-ЯЁ]/.test(text)) return 'shape_camel';
  return null;
}
function shapeGuard(run, active, core) {
  for (const lay of [active, OTHER_LAYOUT[active]]) {
    const r = shapeReason(render(run, lay));
    if (r) return r;
  }
  if (keywalk(run)) return 'shape_keywalk';
  return null;
}

// ---- 10.1 / 10.2 calibration arithmetic ----
const STATES = ['default', 'after_switch', 'run'];
const logit = (p) => Math.log(p / (1 - p));
function deploymentPrior(a, w, o) {
  return a === 'en' ? [(1 - w) * (1 - o), w, (1 - w) * o] : [w * (1 - o), 1 - w, w * o];
}
function lse(xs) { const m = Math.max(...xs); return m + Math.log(xs.reduce((s, x) => s + Math.exp(x - m), 0)); }
function piTrain(cal) { const s = cal.pi_train_counts.reduce((a, b) => a + b, 0); return cal.pi_train_counts.map((c) => c / s); }
function score(z, a, cal, w, kind = 'network') {
  const T = cal.temperature[kind];
  const pt = piTrain(cal), pd = deploymentPrior(a, w, cal.o_lat);
  const lp = z.map((x, i) => x / T + Math.log(pd[i] / pt[i]));
  const l = lse(lp);
  const q = lp.map((x) => x - l);                 // ln p'
  const ru = q[1], other = lse([q[0], q[2]]);
  return a === 'en' ? ru - other : other - ru;
}
// the starting calibration package (values of 10.1 to 10.3; T = 1 and pi_train 38/40/22 inferred, see report)
function exampleCal(exact = true) {
  const t = (p) => (exact ? logit(p) : Math.round(logit(p) * 1000) / 1000);
  const th = { b34: t(0.999), b57: t(0.997), b8: t(0.995) };
  return {
    temperature: { network: 1.0, ngram: 1.0 },
    pi_train_counts: [38, 40, 22],
    o_lat: 0.25,
    w: { en: { default: 0.01, after_switch: 0.003, run: 0.25 }, ru: { default: 0.01, after_switch: 0.003, run: 0.25 } },
    lam: { network: { en2ru: th, ru2en: th }, ngram: { en2ru: th, ru2en: th } },
  };
}
const TWO_ALLOW = { ru: new Set('на не но да по из за то ты мы вы он ли ну во со до от ни же бы'.split(' ')), en: new Set('of to in is it on at as be by or an if so do go he we me my no up us'.split(' ')) };
function bucket(n) { return n <= 4 ? 'b34' : n <= 7 ? 'b57' : 'b8'; }

// ---- 10.4 / 20.6 decide ----
function decide(run, active, cal, scorer, state, runActive, exceptions, lex, kind = 'network') {
  const T = OTHER_LAYOUT[active];
  const dir = active === 'en' ? 'en2ru' : 'ru2en';
  const D = (action, reason, repl = null, margin = null, n = 0) => ({ action, reason, replacement: repl, margin, n_keys: n });
  const c = candidate(run, T);
  if (!c) return D('KEEP', 'no_eligible_candidate', null, null, 0);
  const n = c.core.length;
  if (n === 1) return D('KEEP', 'one_key', null, null, n);
  const typed = render(c.core, active).toLowerCase();
  if (exceptions && exceptions.has(dir + '\u0000' + typed)) return D('KEEP', 'user_exception', null, null, n);
  const g = shapeGuard(run, active, c.core);
  if (g) return D('KEEP', g, null, null, n);
  if (lex['acr_' + active].has(typed)) return D('KEEP', 'acronym', null, null, n);
  if (lex[active].has(typed)) return D('KEEP', 'lexicon_active', null, null, n);
  const repl = render(c.lead.concat(c.core, c.trail), T);
  if (n === 2) {
    const conv = render(c.core, T).toLowerCase();
    if (runActive && TWO_ALLOW[T].has(conv)) return D('CONVERT', 'two_key_allow_list', repl, null, n);
    return D('KEEP', 'two_key_rule', null, null, n);
  }
  const z = scorer(tokens(c.core));
  const s = score(z, active, cal, cal.w[active][state], kind);
  const lam = cal.lam[kind][dir][bucket(n)];
  const margin = s - lam;
  return margin >= 0 ? D('CONVERT', 'score_above_threshold', repl, margin, n) : D('KEEP', 'abstain', null, margin, n);
}

// ---- 20.8 manual conversion ----
function manualConvert(text) {
  let cy = 0, la = 0;
  for (const ch of text) { if (/[Ѐ-ӿ]/.test(ch) && /\p{L}/u.test(ch)) cy++; else if (/[A-Za-z]/.test(ch)) la++; }
  if (cy + la === 0) return [null, text];
  const src = cy > la ? 'ru' : 'en', dst = OTHER_LAYOUT[src];
  let out = '';
  for (const ch of text) {
    const r = REV[src].get(ch);
    out += r ? TABLE[dst][r[1] ? 1 : 0][r[0]] : ch;
  }
  return [cy > la ? 'ru2en' : 'en2ru', out];
}

module.exports = { TABLE, OTHER_LAYOUT, BOS, EOS, Key, renderKey, token, render, tokens, keysFromText, candidate, shapeGuard, STATES, logit, deploymentPrior, score, exampleCal, decide, manualConvert, lse, piTrain, LETTER, L_SET, bucket };
