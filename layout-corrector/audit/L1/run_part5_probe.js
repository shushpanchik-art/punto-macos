'use strict';
const AD = require('./lf_adapter.js');
const { loadExpected } = require('./expected.js');
const E = loadExpected();
let ok = 0, tot = 0;
for (const [name, caps, status, facts, mode] of E.modes) { const got = AD.engineMode(caps, status, facts); tot++; if (got === mode) ok++; else console.log('modes FAIL', name, got, mode); }
console.log('modes', ok, tot); ok = tot = 0;
for (const [began, o, n, r, okv, exp] of E.outcome) { const got = AD.classifyOutcome(began, o, n, r, okv); tot++; if (got === exp) ok++; else console.log('outcome FAIL', got, exp); }
console.log('outcome', ok, tot); ok = tot = 0;
const LAYOUT = { en: AD.SUPPORTED.en, ru: AD.SUPPORTED.ru };
for (const [name, dig, lay] of E.fingerprint) { tot++; if (AD.identifyLayout(dig) === lay) ok++; else console.log('fingerprint FAIL', name); }
console.log('fingerprint (identify only)', ok, tot); ok = tot = 0;
for (const [name, caps, text, faults, ahead, extra, outcome, reason, final, incident] of E.tx) {
  const f = new AD.SimField(text, caps, faults);
  const word = 'ghbdtn', K = require('./lf_keys.js');
  const r = AD.runTransaction(f, caps, word, K.render(K.keysFromText(word, 'en'), 'ru'), ahead, extra);
  tot++;
  if (r.outcome === outcome && r.reason === reason && r.text === final && r.incident === incident) ok++;
  else console.log('tx FAIL', name, JSON.stringify([r.outcome, r.reason, r.text, r.incident]), JSON.stringify([outcome, reason, final, incident]));
}
console.log('tx', ok, tot);
