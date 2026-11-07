'use strict';
const K = require('./lf_keys.js');
const { loadExpected } = require('./expected.js');
const E = loadExpected();
let ok = 0, tot = 0;
for (const [text, lay, rendered, toks] of E.render) {
  const keys = K.keysFromText(text, lay);
  const r = K.render(keys, K.other(lay));
  const t = K.tokens(keys);
  tot++; if (r === rendered && JSON.stringify(t) === JSON.stringify(toks)) ok++; else console.log('render FAIL', text, r, t);
}
console.log('render', ok, tot);
ok = 0; tot = 0;
for (const [k, sh, caps, en, ru, tk] of E.caps) {
  const key = new K.Key(k, sh, caps, 'en');
  tot++; if (K.renderKey(key, 'en') === en && K.renderKey(key, 'ru') === ru && K.token(key) === tk) ok++; else console.log('caps FAIL', k, sh, caps);
}
console.log('caps', ok, tot);
ok = 0; tot = 0;
for (const [k, sh, caps, en, ru, tk] of E.caps_all) {
  const key = new K.Key(k, sh, caps, 'en');
  tot++; if (K.renderKey(key, 'en') === en && K.renderKey(key, 'ru') === ru && K.token(key) === tk) ok++; else console.log('caps_all FAIL', k, sh, caps);
}
console.log('caps_all', ok, tot);
console.log('prefix', JSON.stringify(K.tokens(K.keysFromText('ghb', 'en'), false)), JSON.stringify(E.prefix));
// tok25 honest first attempt: truncate to 20 keys, then BOS + 20 + EOS
const keys25 = Array.from({ length: 25 }, (_, i) => new K.Key(i, false, false, 'en'));
console.log('tok25 first attempt (truncate to 20 keys, keep EOS):', K.tokens(keys25.slice(0, 20)).length, 'expected', E.tok25);
