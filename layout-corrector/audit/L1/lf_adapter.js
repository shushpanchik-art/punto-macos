'use strict';
// Part 5 (spec 13.2, 13.5, 13.7, 20.14 prose): engine_mode, classify_outcome, replacement transaction on a simulated
// field, layout fingerprint, hook health. SimField fault semantics are INFERRED from the names and final texts of
// the tx vectors (the text only lists the faults in prose); see the report.
const crypto = require('crypto');
const K = require('./lf_keys.js');

// ---- engine_mode (13.5, 13.7, 20.14) ----
const AUTO_REQUIRES = ['READ_RANGE', 'REPLACE_RANGE', 'READBACK', 'ROLLBACK'];
function engineMode(caps, status, facts = {}) {
  const f = Object.assign({ models_ok: true, hook_ok: true, watchdog_ok: true, layout_ok: true, permission_ok: true, quarantined: false }, facts);
  const has = (c) => caps.includes(c);
  const canWrite = has('REPLACE_RANGE') || has('SYNTHETIC_INPUT');
  if (f.quarantined || !f.permission_ok || !f.layout_ok || status === 'UNKNOWN' || !canWrite) return 'OFF';
  if (status === 'AUTO' && AUTO_REQUIRES.every(has) && f.models_ok && f.hook_ok && f.watchdog_ok) return 'AUTO';
  return 'MANUAL_ONLY';
}
// ---- classify_outcome (13.2 step 6) ----
// args: began (step 4 began), original, new, read (text read last, null if unreadable), ok (step 5 passed incl. caret)
function classifyOutcome(began, original, newText, read, ok) {
  if (!began) return 'ABORTED';
  if (read !== null && read === newText && ok) return 'VERIFIED';
  if (read !== null && read === original) return 'RESTORED';
  return 'UNRECOVERED';
}
// ---- layout fingerprint (13.7, 20.14) ----
function layoutFingerprint(entries) { return crypto.createHash('sha256').update(entries.join('\n'), 'utf8').digest('hex'); }
function tableEntries(layout) { const o = []; for (let k = 0; k < K.NKEYS; k++) { o.push(K.table(layout, k, false)); o.push(K.table(layout, k, true)); } return o; }
const SUPPORTED = { en: layoutFingerprint(tableEntries('en')), ru: layoutFingerprint(tableEntries('ru')) };
function identifyLayout(digest) { for (const [l, d] of Object.entries(SUPPORTED)) if (d === digest) return l; return null; }

// ---- adapter test double ----
class AdapterError extends Error {}
class SimField {
  constructor(text, caps, faults) {
    this.text = text; this.caret_ = text.length; this.caps = caps; this.faults = faults || {};
    this.cnt = { gate: 0, caret: 0, read: 0, replace: 0, event: 0 };
    this.keys = 0;
  }
  _fault(op) { this.cnt[op]++; return this.faults[op + ':' + this.cnt[op]]; }
  _userKey(ch) { this.keys++; if (ch) { this.text = this.text.slice(0, this.caret_) + ch + this.text.slice(this.caret_); this.caret_ += ch.length; } }
  _pre(f) { // faults that fire before the operation runs
    if (f === undefined) return;
    if (f.startsWith('user:')) this._userKey(f.slice(5));
    else if (f === 'key') this._userKey('');
  }
  gate() { const f = this._fault('gate'); if (f === 'raise') throw new AdapterError('gate'); return f === 'DENY' || f === 'UNKNOWN' ? f : 'ALLOW'; }
  mark() { return this.keys; }
  keysSince(m) { return this.keys - m; }
  modifierDown() { return false; }
  caret() {
    const f = this._fault('caret'); if (f === 'raise') throw new AdapterError('caret');
    let c = this.caret_; if (f === 'back') c -= 1; else if (f === 'forward') c += 1; else if (f === 'forward2') c += 2; return c;
  }
  read(a, b) {
    const f = this._fault('read'); this._preDone = false;
    if (f === 'raise') throw new AdapterError('read');
    if (f === 'none') return null;
    if (f === 'stale') return this.text.slice(Math.max(a - 1, 0), Math.max(b - 1, 0));
    const out = this.text.slice(a, b);   // the read returns the field as it is when the call arrives ...
    this._pre(f);                       // ... a user key / key lands during the call, after the data was taken
    return out;
  }
  replace(a, b, s) {
    const f = this._fault('replace');
    if (f === 'raise') throw new AdapterError('replace');
    this._pre(f && (f.startsWith('user:') || f === 'key') ? f : undefined);
    let w = s;
    if (f === 'partial') { w = s.slice(0, Math.floor(s.length / 2)) + this.text.slice(a + Math.floor(s.length / 2), b); }
    if (f === 'ignored') return;
    if (f === 'autocorrect') w = s.slice(0, -1) + '?';
    if (f === 'spill') { this.text = this.text.slice(0, a) + s + '?' + this.text.slice(b + 1); if (f !== undefined) return; }
    this.text = this.text.slice(0, a) + w + this.text.slice(b);
    if (f === 'partial' || f === 'applied_error') throw new AdapterError('replace');
  }
  send(events) {
    for (const ev of events) {
      const f = this._fault('event');
      if (f === 'raise') throw new AdapterError('event');
      this._pre(f);
      if (ev === '\b') { if (this.caret_ > 0) { this.text = this.text.slice(0, this.caret_ - 1) + this.text.slice(this.caret_); this.caret_--; } }
      else { this.text = this.text.slice(0, this.caret_) + ev + this.text.slice(this.caret_); this.caret_ += ev.length; }
    }
  }
}

// ---- run_transaction (13.2) ----
// returns {outcome, reason, text, incident}
function runTransaction(field, caps, runKeysText, newText, ahead, extra) {
  extra = extra || {};
  const mode = extra.mode || 'AUTO';
  const has = (c) => caps.includes(c);
  const res = (outcome, reason) => ({ outcome, reason, text: field.text, incident: outcome !== 'ABORTED' && outcome !== 'VERIFIED' });
  const n = [...runKeysText].length;
  if (mode === 'OFF') return res('ABORTED', 'mode_off');
  if (mode === 'AUTO' && !AUTO_REQUIRES.every(has)) return res('ABORTED', 'capability');
  if (mode === 'MANUAL_ONLY' && !(has('READ_RANGE') && (has('REPLACE_RANGE') || has('SYNTHETIC_INPUT')))) return res('ABORTED', 'capability');
  const m1 = has('REPLACE_RANGE');
  const a = ahead.length;
  // 1. freeze
  if (a > 3) return res('ABORTED', 'typed_ahead');
  if (extra.context_break || extra.layout_changed) return res('ABORTED', 'context_break');
  if (!m1 && a > 0) return res('ABORTED', 'typed_ahead');
  if (!m1 && field.modifierDown()) return res('ABORTED', 'modifier_down');
  let mk;
  try { mk = field.mark(); } catch (e) { return res('ABORTED', 'adapter_error'); }
  // 2. gate
  try { if (field.gate() !== 'ALLOW') return res('ABORTED', 'gate_changed'); } catch (e) { return res('ABORTED', 'gate_changed'); }
  // 3. read and match
  let c, fragStart = -1, frag = null;
  try {
    c = field.caret();
    for (let ap = a; ap >= 0; ap--) {
      const len = n + 1 + ap;
      const got = field.read(c - len, c);
      if (got === (runKeysText + ' ' + ahead.slice(0, ap))) { fragStart = c - len; frag = ap; break; }
    }
  } catch (e) { return res('ABORTED', 'adapter_error'); }
  if (frag === null) return res('ABORTED', 'echo_mismatch');
  const origFrag = runKeysText + ' ' + ahead.slice(0, frag), newFrag = newText + ' ' + ahead.slice(0, frag);
  if (!m1) { // 3b last look
    if (field.keysSince(mk) > 0) return res('ABORTED', 'typed_ahead');
  }
  // 4. replace
  let reason = 'ok', failed = false;
  try {
    if (m1) field.replace(fragStart, fragStart + n, newText);
    else field.send([...'\b'.repeat(n + 1), ...newText, ' ']);
  } catch (e) { failed = true; reason = 'write_error'; }
  // 5. verify
  let readBack = null, okv = false;
  if (!failed) {
    try {
      readBack = field.read(fragStart, fragStart + newFrag.length);
      const caret = field.caret(); const k = field.keysSince(mk);
      okv = readBack === newFrag && caret >= c && caret <= c + k;
    } catch (e) { okv = false; }
    if (!okv) { failed = true; reason = 'verify_failed'; }
  }
  if (!failed) return res('VERIFIED', 'ok');
  // 6. outcome: one rollback attempt for M1 only
  if (m1 && has('ROLLBACK')) { try { field.replace(fragStart, fragStart + n, runKeysText); } catch (e) { /* the rollback failed */ } }
  let last = null;
  try { last = field.read(fragStart, fragStart + origFrag.length); } catch (e) { last = null; }
  const outcome = classifyOutcome(true, origFrag, newFrag, last, false);
  return res(outcome, reason);
}

// ---- HookHealth (13.5 row 13, 13.7, 20.14) ----
class HookHealth {
  constructor(limitMs = 300, needPairs = 3) {
    this.limit = limitMs; this.need = needPairs;
    this.pending = { raw: [], hook: [] }; // events waiting for their counterpart: {sig, t}
    this.trusted = true; this.gapReported = false; this.reason = null; this.rearm = 0; this.armed = true;
  }
  _lose(reason) { if (this.trusted) { this.trusted = false; this.gapReported = true; this.reason = reason; this.rearm = 0; } }
  _expire(now) {
    for (const [side, other, reason] of [['raw', 'hook', 'canary_missing'], ['hook', 'raw', 'canary_extra']]) {
      const keep = [];
      for (const e of this.pending[side]) { if (now - e.t > this.limit) this._lose(reason); else keep.push(e); }
      this.pending[side] = keep;
    }
  }
  // side: 'raw' | 'hook'; injected events are not compared
  event(side, sig, t, injected = false) {
    if (injected) return;
    this._expire(t);
    const other = side === 'raw' ? 'hook' : 'raw';
    const i = this.pending[other].findIndex((e) => e.sig === sig);
    if (i >= 0) { this.pending[other].splice(i, 1); if (!this.trusted && this.armed === 'rearming') { this.rearm++; if (this.rearm >= this.need) { this.trusted = true; this.reason = null; this.armed = true; } } }
    else this.pending[side].push({ sig, t });
  }
  check(now) { this._expire(now); }
  tap(disabled, reason) { if (disabled) this._lose(reason); else { this.trusted = true; } }
  reinstall() { this.armed = 'rearming'; this.rearm = 0; }
  takeGap() { const g = this.gapReported; this.gapReported = false; return g; }
}
module.exports = { engineMode, classifyOutcome, layoutFingerprint, tableEntries, SUPPORTED, identifyLayout, AdapterError, SimField, runTransaction, HookHealth, AUTO_REQUIRES };
