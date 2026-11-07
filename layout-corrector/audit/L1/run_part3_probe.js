'use strict';
const K = require('./lf_keys.js');
const A = require('./lf_cal.js');
const { loadExpected } = require('./expected.js');
const E = loadExpected();
let ok = 0, tot = 0;
for (const [lay, st, w, vec] of E.priors) {
  const got = A.deploymentPrior(lay, A.W[st]).map(A.r4);
  tot++; if (A.W[st] === w && JSON.stringify(got) === JSON.stringify(vec)) ok++; else console.log('priors FAIL', lay, st, got, vec);
}
console.log('priors', ok, tot); ok = 0; tot = 0;
for (const [t, nats] of E.lambdas) { tot++; if (A.r3(A.logit(t)) === nats) ok++; else console.log('lambda FAIL', t, A.r3(A.logit(t)), nats); }
console.log('lambdas', ok, tot); ok = 0; tot = 0;
for (const [z, lay, st, s] of E.scores) { const got = A.r3(A.score(z, lay, st, A.exampleCal)); tot++; if (got === s) ok++; else console.log('scores FAIL', z, lay, st, got, s); }
console.log('scores', ok, tot); ok = 0; tot = 0;
for (const row of E.decide) {
  const [text, lay, z, st, credPos, exc, act, reason, repl, margin, n] = row;
  const keys = K.keysFromText(text, lay);
  const exceptions = new Set(exc ? [(lay === 'en' ? 'en2ru' : 'ru2en') + '|' + A.fold(text)] : []);
  const d = A.decide(keys, lay, A.exampleCal, () => z, st, credPos ? 3 : 0, exceptions);
  const got = [d.action, d.reason, d.replacement, d.margin === null ? null : A.r3(d.margin), d.nKeys];
  const exp = [act, reason, repl, margin, n];
  tot++; if (JSON.stringify(got) === JSON.stringify(exp)) ok++; else console.log('decide FAIL', text, JSON.stringify(got), JSON.stringify(exp));
}
console.log('decide', ok, tot);
