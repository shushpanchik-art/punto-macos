'use strict';
// Part 4 (spec 11.3, 20.9 prose): EV-1 rule; FNV-1a 64 hashing (20.10 prose).
// exact one-sided 95% Poisson upper limit: the mean mu with P(X <= c | mu) = 0.05
function poissonCdf(c, mu) { let term = Math.exp(-mu), s = term; for (let i = 1; i <= c; i++) { term *= mu / i; s += term; } return s; }
function poissonUpper(c, conf = 0.95) {
  let lo = 0, hi = 10 + 3 * c + 10 * Math.sqrt(c + 1);
  for (let i = 0; i < 200; i++) { const mid = (lo + hi) / 2; if (poissonCdf(c, mid) > 1 - conf) lo = mid; else hi = mid; }
  return (lo + hi) / 2;
}
// m: ASSUMPTION m is floored at 1 (the vector "0 errors, n=100000" has bound 3e-05, not 0)
function ev1Bound(n, c, m) { return poissonUpper(c) * Math.max(m, 1) / n; }
function ev1Pass(n, users, docs, k, c, m, fixedBefore = true, logged = true) {
  const b = ev1Bound(n, c, m);
  const c1 = n >= 100000 && users >= 20 && docs >= 100 && fixedBefore;
  const c2 = k / n <= 4.8e-5;
  const c3 = b <= 1e-4;
  return [c1 && c2 && c3 && logged, b];
}
const MASK = (1n << 64n) - 1n;
function fnv1a64(bytes) {
  let h = 0xcbf29ce484222325n;
  for (const b of bytes) { h ^= BigInt(b); h = (h * 0x100000001b3n) & MASK; }
  return h;
}
const hex = (h) => '0x' + h.toString(16).padStart(16, '0');
const utf8 = (s) => Buffer.from(s, 'utf8');
// 20.10 prose: context hash = FNV-1a-64(0xC0+k || context bytes); pair hash = FNV-1a-64(0xD0+k || context bytes || next token)
// ASSUMPTION: each token (0..96) is one byte
function ctxKey(k, ctx) { return fnv1a64([0xC0 + k, ...ctx]); }
function pairKey(k, ctx, nxt) { return fnv1a64([0xD0 + k, ...ctx, nxt]); }
module.exports = { poissonUpper, ev1Bound, ev1Pass, fnv1a64, hex, utf8, ctxKey, pairKey };
