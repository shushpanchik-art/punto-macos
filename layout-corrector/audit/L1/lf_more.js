'use strict';
// Part 4/5 additions: EV-1 cases (inputs live only in the vector names), lex_key, fingerprint variants,
// undo scenarios (shape of the entries is not documented: guessed), hook scenarios (stimuli designed from the names).
const K = require('./lf_keys.js');
const S = require('./lf_stats.js');
const A = require('./lf_cal.js');
const AD = require('./lf_adapter.js');
const { Engine } = require('./lf_engine.js');
const SC = require('./lf_scen.js');

// ---- ev1: parameters (n, users, docs, k, c, m) read from the NAME of each vector; "19 users" case has n inferred from the bound
const EV1 = {
  '4 errors, 4 users, n=100000, 20 users, 100 docs': { n: 100000, users: 20, docs: 100, k: 4, c: 4, m: 1 },
  '4 errors in one document': { n: 100000, users: 20, docs: 100, k: 4, c: 1, m: 4 },
  '0 errors, n=100000': { n: 100000, users: 20, docs: 100, k: 0, c: 0, m: 0 },
  '0 errors, n=99999': { n: 99999, users: 20, docs: 100, k: 0, c: 0, m: 0 },
  '0 errors, 19 users': { n: 200000, users: 19, docs: 100, k: 0, c: 0, m: 0 }, // n=200000 is NOT in the name; inferred from the bound 1.5e-05
  '5 errors in 5 clusters, n=150000': { n: 150000, users: 20, docs: 100, k: 5, c: 5, m: 1 },
  '2+2 errors in 2 clusters, n=100000': { n: 100000, users: 20, docs: 100, k: 4, c: 2, m: 2 },
};
// 11.3 cond. 3 literally: U(c)*m/n with m = largest cluster size. For k=0 that is m=0 -> bound 0, but the vector shows 3e-05.
function ev1(name, floorM) {
  const p = EV1[name]; if (!p) return null;
  const m = floorM ? Math.max(p.m, 1) : p.m;
  const bound = S.poissonUpper(p.c) * m / p.n;
  const c1 = p.n >= 100000 && p.users >= 20 && p.docs >= 100;
  const c2 = p.k / p.n <= 4.8e-5;
  const c3 = bound <= 1e-4;
  return [c1 && c2 && c3, Number(bound.toFixed(7))];
}

// ---- lex_key: prefix byte (0xE1 lex_en, 0xE2 lex_ru, 0xE3 acr_en?, 0xE4 acr_ru) + UTF-8 of the case-folded word, FNV-1a-64.
// NOT defined in the text; found by brute force against the three keys of the `lfl` vector.
const TAGBYTE = { lex_en: 0xE1, lex_ru: 0xE2, acr_en: 0xE3, acr_ru: 0xE4 };
function lexKey(tag, word) { return S.fnv1a64([TAGBYTE[tag], ...S.utf8(word.toLowerCase())]); }

// ---- fingerprint variants
function tableEntries(layout) { return AD.tableEntries(layout); }
const sha = AD.layoutFingerprint;
function fpVariant(name) {
  if (name === 'en' || name === 'ru') return sha(tableEntries(name));
  if (name === 'ru with key 4 shifted changed to $') { const e = tableEntries('ru'); e[2 * 4 + 1] = '$'; return sha(e); }
  if (name === 'en rotated by one entry') { const e = tableEntries('en'); return [sha(e.slice(1).concat(e[0])), sha([e[e.length - 1]].concat(e.slice(0, -1)))]; }
  return null;
}

// ---- undo scenarios (the columns of the entries are not documented; see report) ----
function undoScenarios() {
  const mk = () => new Engine(A.exampleCal, (toks) => (toks[1] <= 0 ? [-3, 9, -2] : [-3, 9, -2]));
  const out = [];
  const conv = (eng, word, lay, t0, caps) => {
    const scorer = lay === 'en' ? () => [-3, 9, -2] : () => [9, -3, -2];
    eng.scorer = scorer;
    SC.typeWord(eng, word, lay, t0, !!caps);
    const d = eng.onEvent({ type: 'space', layout: lay, t: t0 + 100 });
    return d;
  };
  const verified = (name, fn) => { const e = mk(); const d = conv(e, 'ghbdtn', 'en', 1000); e.onOutcome('VERIFIED'); return fn(e, d); };
  // 1 convert
  { const e = mk(); const d = conv(e, 'ghbdtn', 'en', 1000); e.onOutcome('VERIFIED'); out.push(['convert', d.action, d.replacement, !!e.snap]); }
  // 2 undo after 500 ms
  { const e = mk(); conv(e, 'ghbdtn', 'en', 1000); e.onOutcome('VERIFIED'); const u = e.undo(1100 + 500);
    out.push(['undo after 500 ms', u, [...e.exceptions].map((x) => x.split('|')), e.credit, 3, !!e.snap]); }
  // 3 second undo
  { const e = mk(); conv(e, 'ghbdtn', 'en', 1000); e.onOutcome('VERIFIED'); e.undo(1600); out.push(['second undo', e.undo(1700)]); }
  // 4 / 5 exact 10000 / 10001 ms after the Space
  for (const [nm, dt] of [['undo at exactly 10000 ms', 10000], ['undo at 10001 ms', 10001]]) { const e = mk(); conv(e, 'ghbdtn', 'en', 1000); e.onOutcome('VERIFIED'); out.push([nm, e.undo(1100 + dt)]); }
  // 6 / 7 100 / 101 further characters
  for (const [nm, nk] of [['undo after 100 further characters', 100], ['undo after 101 further characters', 101]]) {
    const e = mk(); conv(e, 'ghbdtn', 'en', 1000); e.onOutcome('VERIFIED');
    for (let i = 0; i < nk; i++) { const k = K.keysFromText('a', 'en')[0]; k.t = 1200; e.onEvent({ type: 'key', key: k, t: 1200 }); }
    out.push([nm, e.undo(2000)]);
  }
  // 8 Caps Lock word / 9 ru to en
  { const e = mk(); const d = conv(e, 'ghbdtn', 'en', 1000, true); e.onOutcome('VERIFIED'); out.push(['Caps Lock word', d.action, d.replacement, e.undo(1500)]); }
  { const e = mk(); const d = conv(e, 'руддщ', 'ru', 1000); e.onOutcome('VERIFIED'); out.push(['ru to en', d.action, d.replacement, e.undo(1500)]); }
  // 10..17 destroyers
  const destroyer = (nm, f, outcome = 'VERIFIED') => { const e = mk(); conv(e, 'ghbdtn', 'en', 1000); f(e, outcome); const u = e.undo(1500); out.push([nm, u, e.credit]); };
  destroyer('after break', (e) => { e.onOutcome('VERIFIED'); e.onEvent({ type: 'break' }); });
  destroyer('after layout change', (e) => { e.onOutcome('VERIFIED'); e.onEvent({ type: 'layout' }); });
  destroyer('after gap', (e) => { e.onOutcome('VERIFIED'); e.onEvent({ type: 'gap' }); });
  destroyer('after gate DENY', (e) => { e.onOutcome('VERIFIED'); e.setGate('DENY'); });
  destroyer('after mode MANUAL_ONLY', (e) => { e.onOutcome('VERIFIED'); e.setMode('MANUAL_ONLY'); });
  destroyer('after outcome RESTORED', (e) => { e.onOutcome('RESTORED'); });
  destroyer('after outcome VERIFIED', (e) => { e.onOutcome('VERIFIED'); });
  destroyer('after backspace', (e) => { e.onOutcome('VERIFIED'); e.onEvent({ type: 'backspace' }); });
  return out;
}

// ---- hook scenarios: stimuli designed from the names (the JSON holds names and results only) ----
function hookScenarios() {
  const res = [];
  const q = (name, H, now, withNull) => { if (now !== undefined) H.check(now); const tr = H.trusted; const g = H.takeGap(); const r = g ? H.reason : null; res.push([name, tr, g, r]); };
  const fresh = () => new AD.HookHealth();
  const pair = (H, sig, t, firstSide = 'raw', dt = 5) => { const second = firstSide === 'raw' ? 'hook' : 'raw'; H.event(firstSide, sig, t); H.event(second, sig, t + dt); };
  { const H = fresh(); pair(H, 'a', 0); pair(H, 'b', 10); pair(H, 'c', 20); q('three matched keys', H, 400); }
  // 2,3,4: key unseen by the hook; at the limit (300), past the limit (301), reported once
  let H2 = fresh(); pair(H2, 'a', 0); H2.event('raw', 'x', 100); q('key unseen by the hook, at the limit', H2, 400);
  q('key unseen by the hook, past the limit', H2, 401);
  q('gap is reported once', H2, 402);
  // 5,6,7 re-arm: hook installed again, then 3 pairs with equal signatures
  H2.reinstall(); pair(H2, 'p', 1000); q('re-arm pair 1', H2, 1010);
  pair(H2, 'q', 1020); q('re-arm pair 2', H2, 1030);
  pair(H2, 'r', 1040); q('re-arm pair 3', H2, 1050);
  { const H = fresh(); pair(H, 'a', 0); H.event('raw', 'b', 10); H.event('hook', 'c', 12); q('lost b and extra c cancel as counts, at the limit', H, 310); }
  { const H = fresh(); pair(H, 'a', 0); H.event('raw', 'b', 10); H.event('hook', 'c', 12); q('lost b and extra c cancel as counts, past the limit', H, 311); }
  { const H = fresh(); H.event('hook', 'c', 0); q('extra hook key alone, at the limit', H, 300); }
  { const H = fresh(); H.event('hook', 'c', 0); q('extra hook key alone, past the limit', H, 301); }
  { const H = fresh(); H.event('hook', 'a', 0); H.event('raw', 'a', 3); H.event('raw', 'z', 5, true); H.event('hook', 'y', 6, true); q('hook event first, injected event ignored', H, 400); }
  { const H = fresh(); H.event('raw', 'a', 0); H.event('raw', 'a', 100); H.event('hook', 'a', 110); q('two physical presses, one reported, at the limit of the unmatched press', H, 400); }
  { const H = fresh(); H.event('raw', 'a', 0); H.event('raw', 'a', 100); H.event('hook', 'a', 110); q('two physical presses, one reported, past the limit of the unmatched press', H, 401); }
  { const H = fresh(); H.event('raw', 'a', 0); H.event('hook', 'a', 300); q('counterpart exactly at the limit, the watchdog has not run', H); }
  { const H = fresh(); H.event('raw', 'a', 0); H.event('hook', 'a', 301); q('hook event one ms too late, the watchdog has not run', H); }
  { const H = fresh(); H.event('hook', 'a', 0); H.event('raw', 'a', 301); q('raw event one ms too late, the watchdog has not run', H); }
  { const H = fresh(); H.event('raw', 'a', 0); H.event('raw', 'b', 301); q('a later event of the same side shows that the first has expired', H); }
  { const H = fresh(); H.tap(true, 'tap_timeout'); q('macOS tapDisabledByTimeout', H); H.tap(false); q('macOS tap enabled again', H); H.tap(true, 'tap_user_input'); q('macOS tapDisabledByUserInput', H); }
  return res;
}
module.exports = { EV1, ev1, lexKey, fpVariant, undoScenarios, hookScenarios, TAGBYTE };
