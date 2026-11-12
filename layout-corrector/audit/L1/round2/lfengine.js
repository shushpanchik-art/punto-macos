'use strict';
// Event state machine (10.2, 13.2, 13.3, 20.7 prose) re-implemented from the text only.
const C = require('./lfcore.js');

class Event { constructor(kind, key = null, layout = null, t = 0) { this.kind = kind; this.key = key; this.layout = layout; this.t = t; } }

class Engine {
  constructor(cal, scorer, lex) {
    this.cal = cal; this.scorer = scorer; this.lex = lex;
    this.gate = 'ALLOW'; this.mode = 'AUTO';
    this.run = []; this.runLayout = null; this.dropped = false; this.overflow = false;
    this.credit = 0; this.after_switch = false;
    this.exceptions = new Set();
    this.cool_words = 0; this.coolUntil = -Infinity;
    this.snapshot = null; this.pending = null; this.pendingUndo = null;
    this.quarantined = false;
  }
  _clearWord() { this.run = []; this.runLayout = null; this.dropped = false; this.overflow = false; }
  _destroySnapshot() { this.snapshot = null; this.pending = null; this.pendingUndo = null; }
  _discardAll() { this._clearWord(); this.credit = 0; this._destroySnapshot(); }
  _live() { return !this.quarantined && this.mode === 'AUTO' && this.gate === 'ALLOW'; }
  set_gate(v) { this.gate = v; if (v !== 'ALLOW') this._discardAll(); }
  set_mode(m) { this.mode = m; if (m !== 'AUTO') this._discardAll(); }
  release_quarantine() { this.quarantined = false; }
  _count() {
    if (this.snapshot) { this.snapshot.count++; if (this.snapshot.count > 100) this._destroySnapshot(); }
  }
  on_event(ev) {
    if (!this._live()) return null;
    switch (ev.kind) {
      case 'key': {
        this._count();
        if (this.dropped) return null;
        if (!this.run.length && !this.overflow) this.runLayout = ev.layout;
        else if (ev.layout !== this.runLayout) { this.dropped = true; this.run = []; this.overflow = false; this.credit = 0; return null; }
        if (this.run.length >= 64) { this.overflow = true; return null; }
        this.run.push(ev.key);
        return null;
      }
      case 'space': return this._space(ev);
      case 'backspace': {
        if (this.dropped) return null;
        if (this.run.length) { this.run.pop(); return null; }
        this.credit = 0; this._destroySnapshot(); return null;
      }
      case 'break': this._clearWord(); this.credit = 0; this._destroySnapshot(); return null;
      case 'layout': {
        if (this.run.length) this.dropped = true;
        this.run = []; this.overflow = false;
        this.after_switch = true; this.credit = 0; this._destroySnapshot(); return null;
      }
      case 'gap': this._clearWord(); this.credit = 0; this._destroySnapshot(); return null;
      default: return null;
    }
  }
  _space(ev) {
    this._count();
    if (this.dropped) { this._clearWord(); return null; }
    if (!this.run.length && !this.overflow) return null;
    const run = this.run, lay = this.runLayout, over = this.overflow;
    this._clearWord();
    const D = (action, reason) => ({ action, reason, replacement: null, margin: null, n_keys: run.length });
    if (over) return D('KEEP', 'overflow');
    if (ev.layout !== lay) return D('KEEP', 'layout_changed_at_boundary');
    if (this.cool_words > 0 || ev.t < this.coolUntil) { this.cool_words = Math.max(0, this.cool_words - 1); return D('KEEP', 'cooldown'); }
    const state = this.credit > 0 ? 'run' : (this.after_switch ? 'after_switch' : 'default');
    const d = C.decide(run, lay, this.cal, this.scorer, state, this.credit > 0, this.exceptions, this.lex);
    const reachedPolicy = !['no_eligible_candidate'].includes(d.reason) || true;
    if (reachedPolicy) this.after_switch = false;
    if (d.action === 'CONVERT') {
      const cand = C.candidate(run, C.OTHER_LAYOUT[lay]);
      const next = state === 'run' ? Math.max(this.credit - 1, 0) : 3;
      const dir = lay === 'en' ? 'en2ru' : 'ru2en';
      this.snapshot = { keys: run, layout: lay, t: ev.t, count: 0, confirmed: false, exc: dir + '\u0000' + C.render(cand.core, lay).toLowerCase() };
      this.pending = { credit: next }; this.pendingUndo = null;
    } else if (['user_exception', 'acronym', 'lexicon_active', 'abstain'].includes(d.reason)) this.credit = 0;
    return d;
  }
  on_outcome(outcome, incident = false) {
    if (outcome === 'VERIFIED') {
      if (this.pending && this.snapshot) { this.snapshot.confirmed = true; this.credit = this.pending.credit; this.pending = null; }
      return;
    }
    this._destroySnapshot(); this.credit = 0;
    if (incident) { this.quarantined = true; this._clearWord(); }
  }
  undo(t) {
    const s = this.snapshot;
    if (!s || !s.confirmed) return null;
    if (t - s.t > 10000) { this._destroySnapshot(); return null; }
    this.pendingUndo = { t };
    return C.render(s.keys, s.layout);
  }
  undo_outcome(outcome, incident = false) {
    const u = this.pendingUndo, s = this.snapshot;
    this.pendingUndo = null;
    if (!u || !s) return;
    if (outcome === 'VERIFIED') {
      this.exceptions.add(s.exc); this.cool_words = 3; this.coolUntil = u.t + 10000; this.credit = 0; this._destroySnapshot();
    } else if (outcome === 'UNRECOVERED' || incident) {
      this._destroySnapshot(); this.credit = 0; this.quarantined = true; this._clearWord();
    }
  }
  tick(t) { if (this.snapshot && t - this.snapshot.t > 10000) this._destroySnapshot(); }
}

// ---------- vectors ----------
function runEngineVectors({ check, guard, EXP, C, cal, rnd }) {
  const K = C.keysFromText;
  const lex = { en: new Set(['hello', 'the']), ru: new Set(['привет']), acr_en: new Set(['sql']), acr_ru: new Set(['мтс']) };
  const stubByWord = (table, dflt) => (ids) => {
    const txt = ids.filter((t) => t >= 1 && t <= 94).map((t) => C.TABLE.en[(t - 1) % 2][(t - 1) >> 1]).join('');
    return table[txt.toLowerCase()] || dflt;
  };
  const HI = [-3, 9, -2], MID = [-3, 6.5, -2];
  const sc1 = stubByWord({ ghbdtn: HI }, MID);
  let E1 = new Engine(cal, sc1, lex);
  const word = (E, txt, lay, t0) => {
    K(txt, lay).forEach((k, i) => E.on_event(new Event('key', k, lay, t0 + i * 100)));
    const d = E.on_event(new Event('space', null, lay, t0 + txt.length * 100 + 50));
    if (d && d.action === 'CONVERT') E.on_outcome('VERIFIED');
    return d;
  };
  guard('trace_run', () => {
    [['ghbdtn', 0], ['z', 1000], ['ntcn', 2000], ['vbh', 3000], ['ntcn', 4000], ['ntcn', 5000]].forEach(([txt, t0], i) => {
      const st = E1.credit > 0 ? 'run' : (E1.after_switch ? 'after_switch' : 'default');
      const d = word(E1, txt, 'en', t0);
      check('trace_run', txt, [txt, st, d.action, d.reason, rnd(d.margin, 3), E1.credit], EXP.trace_run[i]);
    });
  });
  guard('trace_undo', () => {
    const E = new Engine(cal, sc1, lex); const out = [];
    let d = word(E, 'ghbdtn', 'en', 0); out.push(['ghbdtn', d.action, d.reason, E.credit]);
    E.undo(1000); E.undo_outcome('VERIFIED'); out.push(['(undo at 1000 ms)', '', '', E.credit]);
    for (const [txt, t0] of [['ghbdtn', 2000], ['ghbdtn', 3000], ['ghbdtn', 4000], ['ghbdtn', 5000], ['ghbdtn', 11500]]) { d = word(E, txt, 'en', t0); out.push([`${txt} @${t0}`, d.action, d.reason, E.credit]); }
    out.forEach((r, i) => check('trace_undo', r[0], r, EXP.trace_undo[i]));
  });
  guard('scen', () => {
    const scen = (name, evs) => {
      const E = new Engine(cal, sc1, lex); const res = [];
      for (const ev of evs) {
        if (ev === 'gate:DENY') { E.set_gate('DENY'); continue; }
        if (ev === 'gate:ALLOW') { E.set_gate('ALLOW'); continue; }
        const r = E.on_event(ev); if (r) res.push([r.action, r.reason]);
      }
      return [name, res];
    };
    const ks = (t, l = 'en', tl = 'en') => K(t, tl).map((k, i) => new Event('key', k, l, i * 100));
    const sp = (l = 'en', t = 9000) => new Event('space', null, l, t);
    const B = () => new Event('break');
    const all = [
      scen('word + Space', [...ks('ghbdtn'), sp()]),
      scen('word + Enter (break), then Space', [...ks('ghbdtn'), B(), sp()]),
      scen('word + Tab (break), then Space', [...ks('ghbdtn'), B(), sp()]),
      scen('layout changes inside the word (key layout differs)', [...ks('ghb'), ...ks('dtn', 'ru', 'en'), sp('ru')]),
      scen('manual layout event inside the word', [...ks('ghb'), new Event('layout'), ...ks('dtn'), sp()]),
      scen('Space sampled on another layout', [...ks('ghbdtn'), sp('ru')]),
      scen('gate DENY while typing (password field)', ['gate:DENY', ...ks('ghbdtn'), sp()]),
      scen('gate DENY then ALLOW again, new word', ['gate:DENY', ...ks('ghbdtn'), sp(), 'gate:ALLOW', ...ks('ghbdtn'), sp()]),
      scen('Backspace edits the word', [...ks('ghbdtnx'), new Event('backspace'), sp()]),
      scen('65 keys (overflow)', [...Array.from({ length: 65 }, (_, i) => new Event('key', new C.Key(i % 33), 'en', i)), sp()]),
      scen('two Spaces', [...ks('ghbdtn'), sp(), sp()]),
    ];
    all.forEach((r, i) => check('scen', r[0], r, EXP.scen[i]));
  });
  guard('undo', () => {
    const fresh = (layout = 'en', t0 = 1000, w = 'ghbdtn', caps = false, verified = true) => {
      const e = new Engine(cal, layout === 'en' ? () => [-3, 9, -2] : () => [9, -3, -2], lex);
      K(w, layout).forEach((k, i) => e.on_event(new Event('key', new C.Key(k.id, k.shift, caps), layout, t0 + i)));
      const d = e.on_event(new Event('space', null, layout, t0 + w.length));
      if (verified && d.action === 'CONVERT') e.on_outcome('VERIFIED');
      return [e, d, t0 + w.length];
    };
    const exc = (e) => [...e.exceptions].sort().map((s) => s.split('\u0000'));
    const ul = [];
    let [e, d, ts] = fresh(); ul.push(['convert', d.action, d.replacement, e.snapshot !== null]);
    let r = e.undo(ts + 500); ul.push(['undo chord, before its outcome', r, exc(e), e.credit, e.cool_words, e.snapshot !== null]);
    e.undo_outcome('VERIFIED'); ul.push(['undo after 500 ms, VERIFIED', exc(e), e.credit, e.cool_words, e.snapshot !== null]);
    ul.push(['second undo', e.undo(ts + 600)]);
    for (const oc of ['ABORTED', 'RESTORED', 'UNRECOVERED']) {
      [e, d, ts] = fresh(); e.undo(ts + 500); e.undo_outcome(oc, oc === 'UNRECOVERED');
      ul.push([`undo ended ${oc}`, exc(e), e.credit, e.cool_words, e.snapshot !== null, e.undo(ts + 600), e.quarantined]);
    }
    [e, d, ts] = fresh('en', 1000, 'ghbdtn', false, false); ul.push(['undo before the conversion is VERIFIED', e.undo(ts + 5), e.credit, e.snapshot !== null]);
    e.on_outcome('ABORTED'); ul.push(['conversion ended ABORTED', e.undo(ts + 6), e.credit, e.snapshot !== null]);
    [e, d, ts] = fresh('en', 1000, 'ghbdtn', false, false); ul.push(['credit before the outcome', e.credit]); e.on_outcome('VERIFIED'); ul.push(['credit after VERIFIED', e.credit]);
    [e, d, ts] = fresh(); e.on_outcome('UNRECOVERED', true);
    ul.push(['incident: engine records nothing', e.quarantined, e.on_event(new Event('key', new C.Key(5), 'en', ts + 9)), e.run.length]);
    e.release_quarantine(); e.on_event(new Event('key', new C.Key(5), 'en', ts + 10)); ul.push(['after release', e.quarantined, e.run.length]);
    [e, d, ts] = fresh(); ul.push(['undo at exactly 10000 ms', e.undo(ts + 10000)]);
    [e, d, ts] = fresh(); ul.push(['undo at 10001 ms', e.undo(ts + 10001)]);
    for (const n of [100, 101]) {
      [e, d, ts] = fresh();
      for (let i = 0; i < n; i++) e.on_event(new Event('key', new C.Key(i % 47), 'en', ts + 10 + i));
      ul.push([`undo after ${n} further characters`, e.undo(ts + 2000)]);
    }
    [e, d, ts] = fresh('en', 1000, 'ghbdtn', true); ul.push(['Caps Lock word', d.action, d.replacement, e.undo(ts + 5)]);
    [e, d, ts] = fresh('ru', 1000, 'руддщ'); ul.push(['ru to en', d.action, d.replacement, e.undo(ts + 5)]);
    for (const [name, act] of [['break', (e) => e.on_event(new Event('break'))], ['layout change', (e) => e.on_event(new Event('layout', null, 'ru'))], ['gap', (e) => e.on_event(new Event('gap'))], ['gate DENY', (e) => e.set_gate('DENY')], ['mode MANUAL_ONLY', (e) => e.set_mode('MANUAL_ONLY')], ['outcome RESTORED', (e) => e.on_outcome('RESTORED')], ['outcome VERIFIED', (e) => e.on_outcome('VERIFIED')], ['backspace', (e) => e.on_event(new Event('backspace'))]]) {
      [e, d, ts] = fresh(); act(e); ul.push([`after ${name}`, e.undo(ts + 5), e.credit]);
    }
    ul.forEach((r, i) => check('undo', r[0], r, EXP.undo[i]));
  });
}
module.exports = { Event, Engine, runEngineVectors };
