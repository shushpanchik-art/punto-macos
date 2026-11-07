'use strict';
// Part 3/5 (spec 10.2, 10.4 rows 1-4, 13.2 events table, 13.3, 13.4, 20.7 prose): event machine.
const K = require('./lf_keys.js');
const C = require('./lf_cand.js');
const A = require('./lf_cal.js');

const MAXKEYS = 64;
const COOLDOWN_MS = 10000, COOLDOWN_WORDS = 3;
const UNDO_MS = 10000, UNDO_KEYS = 100;

class Engine {
  constructor(cal, scorer, lex) {
    this.cal = cal; this.scorer = scorer; this.lex = lex || A.exampleLex;
    this.gate = 'ALLOW'; this.mode = 'AUTO';
    this.credit = 0; this.afterSwitch = false;
    this.exceptions = new Set();
    this.cool = null; // {t, suppressed}
    this.snap = null; this.pending = null;
    this._clearWord();
  }
  _clearWord() { this.buf = []; this.dropped = false; this.overflow = false; this.layoutOfWord = null; }
  _destroySnapshot() { this.snap = null; this.pending = null; }
  _breakCtx() { this._clearWord(); this.credit = 0; this._destroySnapshot(); }
  setGate(v) {
    if (v !== 'ALLOW') { this._clearWord(); this.credit = 0; this._destroySnapshot(); }
    else if (this.gate !== 'ALLOW') { this._clearWord(); }
    this.gate = v;
  }
  // FIX after the first attempt (undo vector 'after mode MANUAL_ONLY' expects credit 0): a mode change also clears the credit.
  // 10.2 does not list the mode among the resets; 13.5 only says MANUAL_ONLY records nothing.
  setMode(m) { if (m !== this.mode) { this._destroySnapshot(); this._clearWord(); this.credit = 0; } this.mode = m; }
  get active() { return this.gate === 'ALLOW' && this.mode === 'AUTO'; }
  state() { return this.credit > 0 ? 'run' : this.afterSwitch ? 'after_switch' : 'default'; }
  _further() { if (this.snap) { this.snap.further++; if (this.snap.further > UNDO_KEYS) this.snap = null; } }
  onEvent(ev) {
    if (!this.active) return null;
    switch (ev.type) {
      case 'key': {
        this._further();
        if (this.dropped) return null;
        if (this.layoutOfWord === null) this.layoutOfWord = ev.key.layout;
        else if (ev.key.layout !== this.layoutOfWord) { this.dropped = true; this.buf = []; this.credit = 0; this._destroySnapshot(); return null; }
        if (this.buf.length >= MAXKEYS) { this.overflow = true; return null; }
        this.buf.push(ev.key); return null;
      }
      case 'backspace': {
        if (this.dropped) return null;
        if (this.buf.length === 0) { this._breakCtx(); return null; }
        this.buf.pop(); if (this.buf.length === 0) { this.layoutOfWord = null; }
        // FIX: the first attempt also destroyed the snapshot here. 13.3 lists the destroyers and a Backspace inside the next word
        // is not among them (a Backspace on an EMPTY buffer is a context break, handled above), so the snapshot stays.
        return null;
      }
      case 'layout': { const mid = this.buf.length > 0; this._clearWord(); this.dropped = mid; this.afterSwitch = true; this.credit = 0; this._destroySnapshot(); return null; }
      case 'break': this._breakCtx(); return null;
      case 'gap': this._breakCtx(); return null;
      case 'space': return this._space(ev);
    }
    return null;
  }
  _space(ev) {
    this._further();
    const keys = this.buf, dropped = this.dropped, overflow = this.overflow, lay = this.layoutOfWord;
    this._clearWord();
    if (dropped || keys.length === 0 && !overflow) return null;
    const mk = (action, reason, extra) => Object.assign({ action, reason, replacement: null, margin: null }, extra || {});
    if (overflow) return mk('KEEP', 'overflow');
    if (ev.layout !== lay) return mk('KEEP', 'layout_changed_at_boundary');
    if (this.cool) {
      const done = this.cool.suppressed >= COOLDOWN_WORDS && ev.t - this.cool.t >= COOLDOWN_MS;
      if (!done) { this.cool.suppressed++; return mk('KEEP', 'cooldown'); }
      this.cool = null;
    }
    const state = this.state();
    const dir = lay === 'en' ? 'en2ru' : 'ru2en';
    const d = A.decide(keys, lay, this.cal, this.scorer, state, this.credit, this.exceptions, this.lex);
    this.afterSwitch = false; // cleared by the next decision that reaches the policy
    const evidence = ['user_exception', 'acronym', 'lexicon_active', 'abstain'];
    if (d.action === 'CONVERT') this.credit = state === 'run' ? Math.max(this.credit - 1, 0) : 3;
    else if (evidence.includes(d.reason)) this.credit = 0;
    if (d.action === 'CONVERT') {
      const cand = C.candidate(keys, K.other(lay));
      this.pending = { keys, layout: lay, t: ev.t, dir, coreAsTyped: A.fold(K.render(cand.coreKeys, lay)) };
    }
    return d;
  }
  onOutcome(outcome) {
    if (!this.pending) return;
    if (outcome === 'VERIFIED') this.snap = Object.assign({ further: 0 }, this.pending);
    else { this.snap = null; this.credit = 0; }
    this.pending = null;
  }
  undo(now) {
    const s = this.snap;
    if (!s) return null;
    if (now - s.t > UNDO_MS || s.further > UNDO_KEYS) { this.snap = null; return null; }
    this.exceptions.add(s.dir + '|' + s.coreAsTyped);
    this.cool = { t: now, suppressed: 0 };
    this.credit = 0; this.snap = null;
    return K.render(s.keys, s.layout);
  }
  tick(now) { if (this.snap && now - this.snap.t > UNDO_MS) this.snap = null; }
}
module.exports = { Engine };
