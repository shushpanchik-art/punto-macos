'use strict';
// Adapter contract test double, engine_mode, outcome, replacement transaction, fingerprint, hook health.
// Everything here is reconstructed from the prose of 13.2, 13.5, 13.7 and 20.14 plus the field names of the vectors.
const crypto = require('crypto');
const C = require('./lfcore.js');

// ---------------- engine_mode (13.5, 13.7) ----------------
const AUTO_REQUIRES = ['READ_RANGE', 'REPLACE_RANGE', 'READBACK', 'ROLLBACK'];
function engineMode(caps, support, f = {}) {
  const o = Object.assign({ hook_ok: true, models_ok: true, watchdog_ok: true, layout_ok: true, permission_ok: true, quarantined: false }, f);
  const cs = new Set(caps);
  if (o.quarantined || !o.permission_ok || !o.layout_ok) return 'OFF';
  if (support === 'UNKNOWN') return 'OFF';
  const canWrite = cs.has('READ_RANGE') && (cs.has('REPLACE_RANGE') || cs.has('SYNTHETIC_INPUT'));
  if (!canWrite) return 'OFF';
  if (support === 'AUTO' && AUTO_REQUIRES.every((c) => cs.has(c)) && o.hook_ok && o.models_ok && o.watchdog_ok) return 'AUTO';
  return 'MANUAL_ONLY';
}
// ---------------- classify_outcome (13.2 step 6) ----------------
function classifyOutcome(attempted, orig, neu, read, verified) {
  if (!attempted) return 'ABORTED';
  if (verified) return 'VERIFIED';
  if (read === orig) return 'RESTORED';
  return 'UNRECOVERED';
}
// ---------------- fingerprint (13.7) ----------------
function tableEntries(lay) { const out = []; for (let i = 0; i < 47; i++) { out.push(C.TABLE[lay][0][i]); out.push(C.TABLE[lay][1][i]); } return out; }
const sha256 = (s) => crypto.createHash('sha256').update(s, 'utf8').digest('hex');
function layoutFingerprint(entries) { return sha256(entries.join('\n')); }
function identifyLayout(entries) {
  const fp = layoutFingerprint(entries);
  for (const lay of ['en', 'ru']) if (fp === layoutFingerprint(tableEntries(lay))) return lay;
  return null;
}
// ---------------- HookHealth (13.5 row 13, 20.14) ----------------
class HookHealth {
  constructor(canary = true) { this.canary = canary; this.ok = true; this.gap = false; this.reason = null; this.raw = []; this.hook = []; this.pairs = 0; this.rearm = false; }
  _lose(why) { if (this.ok) { this.ok = false; this.gap = true; this.reason = why; } this.pairs = 0; }
  _expire(now) {
    const ex = [];
    for (const e of this.raw) if (now - e.t > 300) ex.push([e.t, 'canary_missing']);
    for (const e of this.hook) if (now - e.t > 300) ex.push([e.t, 'canary_extra']);
    this.raw = this.raw.filter((e) => now - e.t <= 300); this.hook = this.hook.filter((e) => now - e.t <= 300);
    ex.sort((a, b) => a[0] - b[0]);
    for (const [, why] of ex) this._lose(why);
  }
  _feed(sideName, t, sig) {
    this._expire(t);
    const side = this[sideName], other = this[sideName === 'raw' ? 'hook' : 'raw'];
    const i = other.findIndex((e) => e.sig === sig);
    if (i >= 0) { other.splice(i, 1); if (this.rearm && !this.ok) { this.pairs++; if (this.pairs >= 3) { this.ok = true; this.reason = null; this.rearm = false; this.pairs = 0; } } }
    else side.push({ t, sig });
  }
  raw_key(t, sig) { this._feed('raw', t, String(sig)); }
  hook_key(t, sig, injected = false) { if (injected) return; this._feed('hook', t, String(sig)); }
  check(now) { this._expire(now); return this.ok; }
  take_gap() { const g = this.gap; this.gap = false; return g; }
  reinstalled() { this.raw = []; this.hook = []; this.pairs = 0; if (this.canary) this.rearm = true; else { this.ok = true; this.reason = null; } }
  tap_disabled(kind) { this._lose(kind === 'timeout' ? 'tap_timeout' : 'tap_user_input'); }
}

// ---------------- adapter test double ----------------
class AdapterError extends Error {}
class SimField {
  constructor(text, caps, faults = {}) {
    this.text = text; this.caps = new Set(caps); this.faults = faults; this.cnt = {};
    this.caretPos = text.length; this.keys = 0; this.focused = 'main'; this.bound = null; this.modifier = false;
  }
  _f(op) { this.cnt[op] = (this.cnt[op] || 0) + 1; return this.faults[op + ':' + this.cnt[op]]; }
  _applyKey(f) {
    if (f === 'key') { this.keys++; return true; }
    if (typeof f === 'string' && f.startsWith('user:')) { const c = f.slice(5); this.text = this.text.slice(0, this.caretPos) + c + this.text.slice(this.caretPos); this.caretPos += c.length; this.keys++; return true; }
    return false;
  }
  _chk() { if (this.bound !== null && this.focused !== this.bound) throw new AdapterError('focus moved'); }
  gate() {
    const f = this._f('gate');
    if (f === 'raise') throw new AdapterError('gate');
    if (f === 'DENY' || f === 'UNKNOWN') return f;
    this.bound = this.focused; return 'ALLOW';
  }
  element() { return this.focused; }
  mark() { return this.keys; }
  keys_since(m) { return this.keys - m; }
  modifier_down() { return this.modifier; }
  caret() {
    const f = this._f('caret');
    if (f === 'focus') this.focused = 'other';
    this._chk();
    if (f === 'raise') throw new AdapterError('caret');
    return this.caretPos + (f === 'back' ? -1 : f === 'forward' ? 1 : f === 'forward2' ? 2 : 0);
  }
  read(s, e) {
    const f = this._f('read');
    if (f === 'focus') this.focused = 'other';
    this._chk();
    if (f === 'raise') throw new AdapterError('read');
    this._applyKey(f);
    if (f === 'none') return null;
    const r = this.text.slice(Math.max(0, s), Math.max(0, e));
    if (f === 'stale') return '\u0001' + r.slice(1);
    return r;
  }
  replace(s, e, neu) {
    const f = this._f('replace');
    if (f === 'focus') this.focused = 'other';
    this._chk();
    if (f === 'raise') throw new AdapterError('write');
    this._applyKey(f);
    const put = (str) => { this.text = this.text.slice(0, s) + str + this.text.slice(e); };
    if (f === 'ignored') return;
    if (f === 'partial') { put(neu.slice(0, Math.floor(neu.length / 2)) + this.text.slice(s + Math.floor(neu.length / 2), e)); throw new AdapterError('partial'); }
    if (f === 'applied_error') { put(neu); throw new AdapterError('applied'); }
    if (f === 'autocorrect') { put(neu.slice(0, -1) + '?'); return; }
    put(neu);
    if (f === 'spill') this.text = this.text.slice(0, e) + '?' + this.text.slice(e + 1);
  }
  send(events) {      // events: list of 'BS' or a single character; M2
    for (const ev of events) {
      const f = this._f('event');
      if (f === 'focus') this.focused = 'other';
      this._chk();
      if (f === 'raise') throw new AdapterError('event');
      this._applyKey(f);
      if (f === 'drop') continue;
      if (ev === 'BS') { if (this.caretPos > 0) { this.text = this.text.slice(0, this.caretPos - 1) + this.text.slice(this.caretPos); this.caretPos--; } }
      else { this.text = this.text.slice(0, this.caretPos) + ev + this.text.slice(this.caretPos); this.caretPos += ev.length; }
    }
  }
}

function runTransaction(fld, old, neu, ahead, kw = {}) {
  const mode = kw.mode || 'AUTO';
  const R = (outcome, reason, inc = false) => ({ outcome, reason, incident: inc, quarantine: inc });
  const caps = fld.caps;
  const useM1 = caps.has('REPLACE_RANGE');
  if (mode === 'OFF') return R('ABORTED', 'mode_off');
  if (mode === 'AUTO') { if (!AUTO_REQUIRES.every((c) => caps.has(c))) return R('ABORTED', 'capability'); }
  else if (!(caps.has('READ_RANGE') && caps.has('READBACK') && (caps.has('REPLACE_RANGE') || caps.has('SYNTHETIC_INPUT')))) return R('ABORTED', 'capability');
  const n = Array.from(old).length, a = ahead.length;
  // 1 freeze
  if (a > 3) return R('ABORTED', 'typed_ahead');
  if (kw.context_break || kw.layout_changed) return R('ABORTED', 'context_break');
  if (!useM1) { if (a > 0) return R('ABORTED', 'typed_ahead'); if (fld.modifier_down()) return R('ABORTED', 'modifier_down'); }
  let m;
  try { m = fld.mark(); } catch (e) { return R('ABORTED', 'adapter_error'); }
  // 2 gate
  let g;
  try { g = fld.gate(); } catch (e) { return R('ABORTED', 'gate_changed'); }
  if (g !== 'ALLOW') return R('ABORTED', 'gate_changed');
  const el = fld.element();
  // 3 read and match
  let c, frag = null, before = '', after = '', L = 0, ap = 0;
  try {
    c = fld.caret();
    for (ap = a; ap >= 0; ap--) {
      L = n + 1 + ap;
      const rs = Math.max(0, c - L - 1);
      const s = fld.read(rs, c + 1);
      if (s === null) return R('ABORTED', 'echo_mismatch');
      const hasBefore = c - L - 1 >= 0;
      const b = hasBefore ? s.slice(0, 1) : '';
      const fr = hasBefore ? s.slice(1, 1 + L) : s.slice(0, L);
      const af = hasBefore ? s.slice(1 + L) : s.slice(L);
      if (c - L >= 0 && fr === old + ' ' + ahead.slice(0, ap)) { frag = fr; before = b; after = af; break; }
    }
  } catch (e) { return R('ABORTED', 'adapter_error'); }
  if (frag === null) return R('ABORTED', 'echo_mismatch');
  if (before !== '' && !/\s/.test(before)) return R('ABORTED', 'echo_mismatch');
  // 3b last look
  try {
    if (fld.keys_since(m) > 0) return R('ABORTED', 'typed_ahead');
    if (fld.caret() !== c) return R('ABORTED', 'echo_mismatch');
    if (fld.element() !== el) return R('ABORTED', 'gate_changed');
  } catch (e) { return R('ABORTED', 'adapter_error'); }
  // 4 replace
  const fragStart = c - L, fragNew = neu + ' ' + ahead.slice(0, ap), fragOld = frag;
  let reason = null;
  try {
    if (useM1) fld.replace(fragStart, fragStart + n, neu);
    else { const ev = ['BS']; ev.length = 0; for (let i = 0; i < n + 1; i++) ev.push('BS'); for (const ch of neu) ev.push(ch); ev.push(' '); fld.send(ev); }
  } catch (e) { reason = 'write_error'; }
  // 5 verify
  let verified = false, lastRead = null;
  const readFrag = () => {
    const rs = Math.max(0, c - L - 1);
    const s = fld.read(rs, c + 1);
    if (s === null) return null;
    const hasBefore = c - L - 1 >= 0;
    return { b: hasBefore ? s.slice(0, 1) : '', fr: hasBefore ? s.slice(1, 1 + L) : s.slice(0, L), af: hasBefore ? s.slice(1 + L) : s.slice(L) };
  };
  if (reason === null) {
    try {
      const r = readFrag();
      const k = fld.keys_since(m);
      const cp = fld.caret();
      const ok = r !== null && r.fr === fragNew && r.b === before && (k > 0 || r.af === after) && (k === 0 ? cp === c : (cp >= c && cp <= c + k)) && fld.element() === el && (useM1 || k === 0);
      if (ok) verified = true; else reason = 'verify_failed';
      if (r) lastRead = r.fr;
    } catch (e) { reason = 'verify_failed'; }
  }
  if (verified) return R('VERIFIED', 'ok');
  // failure: one rollback, M1 with ROLLBACK only
  if (useM1 && caps.has('ROLLBACK')) { try { fld.replace(fragStart, fragStart + n, old); } catch (e) { /* rollback failed */ } }
  try { const r = readFrag(); lastRead = r ? r.fr : null; } catch (e) { lastRead = null; }
  const oc = classifyOutcome(true, fragOld, fragNew, lastRead, false);
  return R(oc, reason, true);
}

function runTxVectors({ check, guard, EXP, C, results }) {
  guard('modes', () => EXP.modes.forEach((row) => {
    const [name, caps, sup, flags] = row;
    check('modes', name + sup + JSON.stringify(flags), [name, caps, sup, flags, engineMode(caps, sup, flags)], row);
  }));
  guard('outcome', () => EXP.outcome.forEach((row) => {
    const [a, o, nn, f, v] = row; check('outcome', JSON.stringify(row), [a, o, nn, f, v, classifyOutcome(a, o, nn, f, v)], row);
  }));
  guard('fingerprint', () => {
    const en = tableEntries('en'), ru = tableEntries('ru');
    const typew = ru.slice(); typew[9] = '$';
    const rot = en.slice(1).concat(en.slice(0, 1));
    const got = [['en', layoutFingerprint(en), identifyLayout(en)], ['ru', layoutFingerprint(ru), identifyLayout(ru)], ['ru with key 4 shifted changed to $', layoutFingerprint(typew), identifyLayout(typew)], ['en rotated by one entry', layoutFingerprint(rot), identifyLayout(rot)]];
    got.forEach((r, i) => check('fingerprint', r[0], r, EXP.fingerprint[i]));
  });
  guard('hook', () => {
    const hh = []; let h = new HookHealth(true);
    for (const t of [0, 100, 200]) { h.raw_key(t, 's' + t); h.hook_key(t + 5, 's' + t); }
    hh.push(['three matched keys', h.check(250), h.take_gap()]);
    h.raw_key(1000, 'k'); hh.push(['key unseen by the hook, at the limit', h.check(1300), h.take_gap()]);
    hh.push(['key unseen by the hook, past the limit', h.check(1301), h.take_gap(), h.reason]);
    hh.push(['gap is reported once', h.ok, h.take_gap()]);
    h.reinstalled();
    for (let i = 0; i < 3; i++) { h.raw_key(3000 + i, i); h.hook_key(3000 + i, i); hh.push([`re-arm pair ${i + 1}`, h.ok, h.take_gap()]); }
    let c = new HookHealth(); c.raw_key(0, 'a'); c.hook_key(3, 'a'); c.raw_key(100, 'b'); c.hook_key(105, 'c');
    hh.push(['lost b and extra c cancel as counts, at the limit', c.check(400), c.take_gap(), c.reason]);
    hh.push(['lost b and extra c cancel as counts, past the limit', c.check(401), c.take_gap(), c.reason]);
    c = new HookHealth(); c.hook_key(0, 'c'); hh.push(['extra hook key alone, at the limit', c.check(300), c.take_gap(), c.reason]);
    hh.push(['extra hook key alone, past the limit', c.check(301), c.take_gap(), c.reason]);
    c = new HookHealth(); c.hook_key(10, 'a'); c.raw_key(12, 'a'); c.hook_key(30, 'c', true);
    hh.push(['hook event first, injected event ignored', c.check(10000), c.take_gap(), c.reason]);
    c = new HookHealth(); c.raw_key(0, 'a'); c.raw_key(50, 'a'); c.hook_key(55, 'a');
    hh.push(['two physical presses, one reported, at the limit of the unmatched press', c.check(350), c.take_gap(), c.reason]);
    hh.push(['two physical presses, one reported, past the limit of the unmatched press', c.check(351), c.take_gap(), c.reason]);
    c = new HookHealth(); c.raw_key(0, 'a'); c.hook_key(300, 'a'); hh.push(['counterpart exactly at the limit, the watchdog has not run', c.ok, c.take_gap(), c.reason]);
    c = new HookHealth(); c.raw_key(0, 'a'); c.hook_key(301, 'a'); hh.push(['hook event one ms too late, the watchdog has not run', c.ok, c.take_gap(), c.reason]);
    c = new HookHealth(); c.hook_key(0, 'a'); c.raw_key(301, 'a'); hh.push(['raw event one ms too late, the watchdog has not run', c.ok, c.take_gap(), c.reason]);
    c = new HookHealth(); c.raw_key(0, 'a'); c.raw_key(301, 'b'); hh.push(['a later event of the same side shows that the first has expired', c.ok, c.take_gap(), c.reason]);
    const m = new HookHealth(false); m.tap_disabled('timeout'); hh.push(['macOS tapDisabledByTimeout', m.ok, m.take_gap(), m.reason]);
    m.reinstalled(); hh.push(['macOS tap enabled again', m.ok, m.take_gap(), m.reason]);
    m.tap_disabled('user_input'); hh.push(['macOS tapDisabledByUserInput', m.ok, m.take_gap(), m.reason]);
    hh.forEach((r, i) => check('hook', r[0], r, EXP.hook[i]));
  });
  guard('tx', () => EXP.tx.forEach((row) => {
    const [name, caps, text, faults, ahead, kw, outcome, reason, final, incident] = row;
    const fl = {}; for (const [k, v] of Object.entries(faults)) { const [op, i] = k.split(':'); fl[op + ':' + parseInt(i, 10)] = v; }
    const f = new SimField(text, caps, fl);
    const r = runTransaction(f, 'ghbdtn', 'привет', ahead, kw);
    check('tx', name, [name, r.outcome, r.reason, f.text, r.incident, r.quarantine], [name, outcome, reason, final, incident, incident]);
  }));
}
module.exports = { runTxVectors, engineMode, classifyOutcome, HookHealth, SimField, runTransaction, layoutFingerprint, tableEntries };
