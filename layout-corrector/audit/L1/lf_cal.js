'use strict';
// Part 3 (spec 10.1-10.4, 20.5/20.6 prose): temperature, priors, score in nats, thresholds, decide.
const K = require('./lf_keys.js');
const C = require('./lf_cand.js');

const STATES = ['default', 'after_switch', 'run'];
const W = { default: 0.01, after_switch: 0.003, run: 0.25 };
const O_LAT = 0.25;
// example fixture of 20.5 (values not printed in the text: T=1 and the class mix 38/40/22 are inferred; see report)
const PI_TRAIN_COUNTS = [38, 40, 22];

function deploymentPrior(layout, w, oLat = O_LAT) {
  if (layout === 'en') return [(1 - w) * (1 - oLat), w, (1 - w) * oLat];
  return [w * (1 - oLat), 1 - w, w * oLat];
}
const logit = (p) => Math.log(p / (1 - p));
function lse(a) { const m = Math.max(...a); return m + Math.log(a.reduce((s, x) => s + Math.exp(x - m), 0)); }

// 10.1: p = softmax(z/T); p'(c) ∝ p(c) * pi_dep / pi_train; score = two-way log-odds in nats
function score(z, layout, state, cal) {
  const T = cal.T;
  const prior = deploymentPrior(layout, W[state], cal.oLat);
  const tot = cal.piTrainCounts.reduce((a, b) => a + b, 0);
  const lp = z.map((x, i) => x / T + Math.log(prior[i]) - Math.log(cal.piTrainCounts[i] / tot));
  const Z = lse(lp);
  const lq = lp.map((x) => x - Z); // ln p'
  const [en, ru, ot] = lq;
  const notRu = lse([en, ot]);
  return layout === 'en' ? ru - notRu : notRu - ru;
}
function bucket(n) { return n <= 2 ? null : n <= 4 ? 0 : n <= 7 ? 1 : 2; }
const exampleCal = {
  T: 1, oLat: O_LAT, piTrainCounts: PI_TRAIN_COUNTS,
  // thresholds in nats: [3-4, 5-7, 8+], by kind and direction (the text says both directions are stored; the example uses the same numbers)
  lambda: (kind, direction, n) => { const b = bucket(n); return b === null ? null : [logit(0.999), logit(0.997), logit(0.995)][b]; },
  allowEN: new Set('of to in is it on at as be by or an if so do go he we me my no up us'.split(' ')),
  allowRU: new Set('на не но да по из за то ты мы вы он ли ну во со до от ни же бы'.split(' ')),
};
// fixture lexicons (ASSUMPTION: only the words shown by the vectors)
const exampleLex = {
  lex_en: new Set(['hello']), lex_ru: new Set(['привет']), acr_en: new Set(['sql']), acr_ru: new Set(['мтс']),
};
const fold = (s) => s.toLowerCase();

// 20.6: priority matrix rows 5-12 (rows 1-4 belong to the event machine)
function decide(keys, layout, cal, scorer, state, credit, exceptions, lex = exampleLex) {
  const T = K.other(layout);
  const cand = C.candidate(keys, T);
  const R = (action, reason, repl, margin, n) => ({ action, reason, replacement: repl, margin, nKeys: n, state });
  if (!cand) return R('KEEP', 'no_eligible_candidate', null, null, 0);
  const n = cand.nCore;
  if (n === 1) return R('KEEP', 'one_key', null, null, n);
  const asTyped = fold(K.render(cand.coreKeys, layout)); // as-typed core read on the active layout
  const dir = layout === 'en' ? 'en2ru' : 'ru2en';
  if (exceptions.has(dir + '|' + asTyped)) return R('KEEP', 'user_exception', null, null, n);
  const g = C.shapeGuard(keys);
  if (g) return R('KEEP', g, null, null, n);
  if (lex['acr_' + layout].has(asTyped)) return R('KEEP', 'acronym', null, null, n);
  if (lex['lex_' + layout].has(asTyped)) return R('KEEP', 'lexicon_active', null, null, n);
  if (n === 2) {
    const tgt = fold(cand.core);
    const allow = T === 'ru' ? cal.allowRU : cal.allowEN;
    if (credit > 0 && allow.has(tgt)) return R('CONVERT', 'two_key_allow_list', cand.text, null, n);
    return R('KEEP', 'two_key_rule', null, null, n);
  }
  const s = score(scorer(K.tokens(cand.coreKeys)), layout, state, cal);
  const lam = cal.lambda('network', layout === 'en' ? 'en2ru' : 'ru2en', n);
  const margin = s - lam;
  if (margin >= 0) return R('CONVERT', 'score_above_threshold', cand.text, margin, n);
  return R('KEEP', 'abstain', null, margin, n);
}
const r3 = (x) => Number(x.toFixed(3));
const r4 = (x) => Number(x.toFixed(4));
module.exports = { STATES, W, O_LAT, deploymentPrior, logit, lse, score, exampleCal, exampleLex, decide, fold, r3, r4 };
