'use strict';
const K = require('./lf_keys.js');
const C = require('./lf_cand.js');
const { loadExpected } = require('./expected.js');
const E = loadExpected();
let ok = 0, tot = 0;
for (const [text, T, exp] of E.cands) {
  const keys = K.keysFromText(text, K.other(T));
  const c = C.candidate(keys, T);
  const got = c ? [c.opener, c.core, c.marks] : null;
  tot++; if (JSON.stringify(got) === JSON.stringify(exp)) ok++; else console.log('cands FAIL', text, T, JSON.stringify(got), JSON.stringify(exp));
}
console.log('cands', ok, tot);
ok = 0; tot = 0;
for (const [text, A, exp] of E.guards) {
  const keys = K.keysFromText(text, A);
  const c = C.candidate(keys, K.other(A));
  const got = c ? C.shapeGuard(keys) : 'no_candidate';
  tot++; if (got === exp) ok++; else console.log('guards FAIL', text, A, got, exp);
}
console.log('guards', ok, tot);
ok = 0; tot = 0;
for (const [text, dir, exp] of E.manual) {
  const [d, out] = C.manualConvert(text);
  tot++; if (d === dir && out === exp) ok++; else console.log('manual FAIL', text, d, out, exp);
}
console.log('manual', ok, tot);
