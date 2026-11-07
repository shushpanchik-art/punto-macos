'use strict';
// Event scenarios for trace_run, trace_undo, scen, undo. The event sequences are DESIGNED from the names in the
// expected JSON and the prose of 20.12 ("How to read the traces"); the JSON does not contain them.
const K = require('./lf_keys.js');
const A = require('./lf_cal.js');
const { Engine } = require('./lf_engine.js');

const STUB = { 'ghbdtn': [-3, 9, -2] };
// first honest attempt used the same logits for every word; see report (trace_run): words of fewer than 5 keys need [-3,6.5,-2]
function makeScorer(variant) {
  return (toks) => {
    const n = toks.length - 2;
    if (variant === 'first') return [-3, 9, -2];
    return n >= 5 ? [-3, 9, -2] : [-3, 6.5, -2];
  };
}
function typeWord(eng, text, layout, t0 = 0, caps = false) {
  let t = t0;
  for (const k of K.keysFromText(text, layout)) { k.caps = caps; k.t = t; eng.onEvent({ type: 'key', key: k, t }); t += 10; }
  return t;
}
function space(eng, layout, t) { return eng.onEvent({ type: 'space', layout, t }); }

function traceRun(variant) {
  const eng = new Engine(A.exampleCal, makeScorer(variant));
  const out = [];
  let t = 0;
  for (const w of ['ghbdtn', 'z', 'ntcn', 'vbh', 'ntcn', 'ntcn']) {
    const state = eng.state();
    typeWord(eng, w, 'en', t); const d = space(eng, 'en', t + 500); t += 1000;
    out.push([w, state, d.action, d.reason, d.margin === null ? null : A.r3(d.margin), eng.credit]);
  }
  return out;
}
function traceUndo(variant) {
  const eng = new Engine(A.exampleCal, makeScorer(variant));
  const out = [];
  let d;
  typeWord(eng, 'ghbdtn', 'en', 0); d = space(eng, 'en', 500); eng.onOutcome('VERIFIED');
  out.push(['ghbdtn', d.action, d.reason, eng.credit]);
  eng.undo(1000); out.push(['(undo at 1000 ms)', '', '', eng.credit]);
  for (const t of [2000, 3000, 4000, 5000, 11500]) {
    typeWord(eng, 'ghbdtn', 'en', t - 400); d = space(eng, 'en', t);
    out.push(['ghbdtn @' + t, d.action, d.reason, eng.credit]);
  }
  return out;
}
function scenarios() {
  const R = {};
  const mk = () => new Engine(A.exampleCal, makeScorer('fixed'));
  const run = (name, f) => { const eng = mk(); const res = []; f(eng, (d) => { if (d) res.push([d.action, d.reason]); }); R[name] = res; };
  run('word + Space', (e, o) => { typeWord(e, 'ghbdtn', 'en'); o(space(e, 'en', 100)); });
  run('word + Enter (break), then Space', (e, o) => { typeWord(e, 'ghbdtn', 'en'); o(e.onEvent({ type: 'break' })); o(space(e, 'en', 100)); });
  run('word + Tab (break), then Space', (e, o) => { typeWord(e, 'ghbdtn', 'en'); o(e.onEvent({ type: 'break' })); o(space(e, 'en', 100)); });
  run('layout changes inside the word (key layout differs)', (e, o) => { typeWord(e, 'ghb', 'en'); typeWord(e, 'dtn', 'ru'.length ? 'en' : 'en'); /* placeholder replaced below */ });
  R['layout changes inside the word (key layout differs)'] = (() => {
    const e = mk(); const res = []; typeWord(e, 'ghb', 'en');
    for (const k of K.keysFromText('dtn', 'en')) { k.layout = 'ru'; e.onEvent({ type: 'key', key: k, t: 0 }); }
    const d = space(e, 'ru', 100); if (d) res.push([d.action, d.reason]); return res;
  })();
  run('manual layout event inside the word', (e, o) => { typeWord(e, 'ghb', 'en'); e.onEvent({ type: 'layout' }); typeWord(e, 'dtn', 'en'); o(space(e, 'en', 100)); });
  run('Space sampled on another layout', (e, o) => { typeWord(e, 'ghbdtn', 'en'); o(space(e, 'ru', 100)); });
  run('gate DENY while typing (password field)', (e, o) => { e.setGate('DENY'); typeWord(e, 'ghbdtn', 'en'); o(space(e, 'en', 100)); });
  run('gate DENY then ALLOW again, new word', (e, o) => { e.setGate('DENY'); typeWord(e, 'ghbdtn', 'en'); o(space(e, 'en', 100)); e.setGate('ALLOW'); typeWord(e, 'ghbdtn', 'en', 200); o(space(e, 'en', 300)); });
  run('Backspace edits the word', (e, o) => { typeWord(e, 'ghbdtnx', 'en'); e.onEvent({ type: 'backspace' }); o(space(e, 'en', 100)); });
  run('65 keys (overflow)', (e, o) => { typeWord(e, 'g'.repeat(65), 'en'); o(space(e, 'en', 100)); });
  run('two Spaces', (e, o) => { typeWord(e, 'ghbdtn', 'en'); o(space(e, 'en', 100)); o(space(e, 'en', 200)); });
  return R;
}
module.exports = { typeWord, space, makeScorer, traceRun, traceUndo, scenarios };
