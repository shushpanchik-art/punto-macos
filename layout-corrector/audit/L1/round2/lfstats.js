'use strict';
// statistics (11.3), FNV-1a-64 keys (7.7, 20.10), Witten-Bell baseline (7.7)

function poissonCdf(k, lam) { let t = Math.exp(-lam), s = t; for (let i = 1; i <= k; i++) { t *= lam / i; s += t; } return s; }
function poissonUpper(k, conf = 0.95) {
  if (!Number.isInteger(k) || k < 0 || !(conf > 0 && conf < 1)) throw new RangeError('bad args');
  let lo = 0, hi = Math.max(10, k + 10);
  while (poissonCdf(k, hi) > 1 - conf) hi *= 2;   // P(X<=k | lam) = 1-conf
  for (let i = 0; i < 200; i++) { const mid = (lo + hi) / 2; if (poissonCdf(k, mid) > 1 - conf) lo = mid; else hi = mid; }
  return (lo + hi) / 2;
}
function ev1Bound(fcs, n) {
  const cl = new Map();
  for (const [u, d] of fcs) { const key = u + '\u0000' + d; cl.set(key, (cl.get(key) || 0) + 1); }
  const c = cl.size; const m = c ? Math.max(...cl.values()) : 1;
  return poissonUpper(c) * m / n;
}
function ev1Pass(fcs, n, users, docs) {
  if (!(n >= 100000 && users >= 20 && docs >= 100)) return false;
  if (!(fcs.length / n <= 4.8e-5)) return false;
  return ev1Bound(fcs, n) <= 1e-4;
}

const M64 = (1n << 64n) - 1n;
function fnv1a64(bytes) {
  let h = 0xcbf29ce484222325n;
  for (const b of bytes) { h ^= BigInt(b); h = (h * 0x100000001b3n) & M64; }
  return h;
}
const hex = (h) => '0x' + h.toString(16);
const ctxKey = (k, ctx) => fnv1a64([0xC0 + k, ...ctx]);
const pairKey = (k, ctx, nxt) => fnv1a64([0xD0 + k, ...ctx, nxt]);
const lexKey = (t, s) => fnv1a64([0xE0 + t, ...Buffer.from(s.toLowerCase(), 'utf8')]);

// Witten-Bell order 3 (contexts of 0,1,2 tokens), uniform base 1/97
class WittenBell {
  constructor(pad = false) { this.cnt = [new Map(), new Map(), new Map()]; this.pad = pad; }
  fit(rows) {
    for (const row of rows) for (let i = 1; i < row.length; i++) for (let k = 0; k < 3; k++) {
      let ctx;
      if (this.pad) { ctx = row.slice(Math.max(0, i - k), i); while (ctx.length < k) ctx.unshift(95); }
      else { if (i < k) continue; ctx = row.slice(i - k, i); }
      const key = ctx.join(',');
      let d = this.cnt[k].get(key); if (!d) { d = new Map(); this.cnt[k].set(key, d); }
      d.set(row[i], (d.get(row[i]) || 0) + 1);
    }
    return this;
  }
  p(k, h, w) {          // h: array of exactly k tokens (oldest first)
    const lower = k === 0 ? 1 / 97 : this.p(k - 1, h.slice(1), w);
    const d = this.cnt[k].get(h.join(','));
    if (!d) return lower;
    let t = 0; for (const v of d.values()) t += v;
    const u = d.size;
    return ((d.get(w) || 0) + u * lower) / (t + u);
  }
  logp(row) {
    let s = 0;
    for (let i = 1; i < row.length; i++) {
      const h = row.slice(Math.max(0, i - 2), i);
      const k = h.length;
      s += Math.log(this.p(k, h, row[i]));
    }
    return s;
  }
  nPairs() { let n = 0; for (const m of this.cnt) for (const d of m.values()) n += d.size; return n; }
}

module.exports = { poissonUpper, ev1Bound, ev1Pass, fnv1a64, hex, ctxKey, pairKey, lexKey, WittenBell };
