'use strict';
// Part 1 (spec 19.1, 5.1, 20.2 prose): key tables, tokens, Caps Lock, rendering.

// Table of 19.1: [id] -> [EN, EN+Shift, RU, RU+Shift]
const ROWS = [
  ['`', '~', 'ё', 'Ё'], ['1', '!', '1', '!'], ['2', '@', '2', '"'], ['3', '#', '3', '№'],
  ['4', '$', '4', ';'], ['5', '%', '5', '%'], ['6', '^', '6', ':'], ['7', '&', '7', '?'],
  ['8', '*', '8', '*'], ['9', '(', '9', '('], ['0', ')', '0', ')'], ['-', '_', '-', '_'],
  ['=', '+', '=', '+'],
  ['q', 'Q', 'й', 'Й'], ['w', 'W', 'ц', 'Ц'], ['e', 'E', 'у', 'У'], ['r', 'R', 'к', 'К'],
  ['t', 'T', 'е', 'Е'], ['y', 'Y', 'н', 'Н'], ['u', 'U', 'г', 'Г'], ['i', 'I', 'ш', 'Ш'],
  ['o', 'O', 'щ', 'Щ'], ['p', 'P', 'з', 'З'], ['[', '{', 'х', 'Х'], [']', '}', 'ъ', 'Ъ'],
  ['\\', '|', '\\', '/'],
  ['a', 'A', 'ф', 'Ф'], ['s', 'S', 'ы', 'Ы'], ['d', 'D', 'в', 'В'], ['f', 'F', 'а', 'А'],
  ['g', 'G', 'п', 'П'], ['h', 'H', 'р', 'Р'], ['j', 'J', 'о', 'О'], ['k', 'K', 'л', 'Л'],
  ['l', 'L', 'д', 'Д'], [';', ':', 'ж', 'Ж'], ["'", '"', 'э', 'Э'],
  ['z', 'Z', 'я', 'Я'], ['x', 'X', 'ч', 'Ч'], ['c', 'C', 'с', 'С'], ['v', 'V', 'м', 'М'],
  ['b', 'B', 'и', 'И'], ['n', 'N', 'т', 'Т'], ['m', 'M', 'ь', 'Ь'], [',', '<', 'б', 'Б'],
  ['.', '>', 'ю', 'Ю'], ['/', '?', '.', ','],
];
const NKEYS = 47;
const PAD = 0, BOS = 95, EOS = 96, VOCAB = 97;
const LAYOUTS = { en: 0, ru: 2 };
const isLetter = (ch) => /^\p{L}$/u.test(ch);

function table(layout, k, shift) { return ROWS[k][LAYOUTS[layout] + (shift ? 1 : 0)]; }
function other(layout) { return layout === 'en' ? 'ru' : 'en'; }
// is key k a letter in the given layout (spec 5.1: "the key is a letter in that layout")
function letterIn(layout, k) { return isLetter(table(layout, k, false)); }
// L: keys that are a letter in at least one layout (33 keys)
const L = new Set();
for (let k = 0; k < NKEYS; k++) if (letterIn('en', k) || letterIn('ru', k)) L.add(k);

class Key {
  constructor(k, shift, caps, layout, t) { this.k = k; this.shift = !!shift; this.caps = !!caps; this.layout = layout; this.t = t === undefined ? 0 : t; }
}
// (2) rendered text: raw_shift XOR (caps AND key is a letter in the target layout)
function renderKey(key, target) {
  const s = key.shift !== (key.caps && letterIn(target, key.k));
  return table(target, key.k, s);
}
function render(keys, target) { return keys.map((k) => renderKey(k, target)).join(''); }
// (1) token: 1 + 2k + s, s = raw_shift XOR (caps AND k in L)
function token(key) {
  const s = key.shift !== (key.caps && L.has(key.k));
  return 1 + 2 * key.k + (s ? 1 : 0);
}
const MAX_KEYS = 20; // ASSUMPTION (finding): "the 20-key limit" of 20.12; the value is not stated in the prose
// FIX after the first attempt (tok25): the vector tok25 = 21 for a 25-key word pins only the LENGTH. Reading that fits:
// keep the first MAX_KEYS keys, and drop EOS when the word was cut (the model then sees a prefix). Not stated in the text.
function tokens(keys, eos = true) {
  const cut = keys.length > MAX_KEYS;
  const ks = cut ? keys.slice(0, MAX_KEYS) : keys;
  return [BOS, ...ks.map(token), ...(eos && !cut ? [EOS] : [])];
}
function keysFromText(text, layout) {
  const out = [];
  for (const ch of text) {
    let found = null;
    for (let k = 0; k < NKEYS && !found; k++) {
      for (const sh of [false, true]) if (table(layout, k, sh) === ch) { found = new Key(k, sh, false, layout); break; }
    }
    if (!found) throw new Error('char not on layout ' + layout + ': ' + ch);
    out.push(found);
  }
  return out;
}
module.exports = { ROWS, NKEYS, PAD, BOS, EOS, VOCAB, L, Key, table, other, letterIn, isLetter, renderKey, render, token, tokens, keysFromText, MAX_KEYS };
