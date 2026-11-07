'use strict';
// Part 1: key tables (19.1), tokens (5.1), Caps Lock rules (5.1), rendering.
// Written from the specification text only.

// [EN, EN+Shift, RU, RU+Shift] for key ids 0..46 (table of 19.1)
const TABLE = [
  ['`', '~', 'ё', 'Ё'],
  ['1', '!', '1', '!'],
  ['2', '@', '2', '"'],
  ['3', '#', '3', '№'],
  ['4', '$', '4', ';'],
  ['5', '%', '5', '%'],
  ['6', '^', '6', ':'],
  ['7', '&', '7', '?'],
  ['8', '*', '8', '*'],
  ['9', '(', '9', '('],
  ['0', ')', '0', ')'],
  ['-', '_', '-', '_'],
  ['=', '+', '=', '+'],
  ['q', 'Q', 'й', 'Й'],
  ['w', 'W', 'ц', 'Ц'],
  ['e', 'E', 'у', 'У'],
  ['r', 'R', 'к', 'К'],
  ['t', 'T', 'е', 'Е'],
  ['y', 'Y', 'н', 'Н'],
  ['u', 'U', 'г', 'Г'],
  ['i', 'I', 'ш', 'Ш'],
  ['o', 'O', 'щ', 'Щ'],
  ['p', 'P', 'з', 'З'],
  ['[', '{', 'х', 'Х'],
  [']', '}', 'ъ', 'Ъ'],
  ['\\', '|', '\\', '/'],
  ['a', 'A', 'ф', 'Ф'],
  ['s', 'S', 'ы', 'Ы'],
  ['d', 'D', 'в', 'В'],
  ['f', 'F', 'а', 'А'],
  ['g', 'G', 'п', 'П'],
  ['h', 'H', 'р', 'Р'],
  ['j', 'J', 'о', 'О'],
  ['k', 'K', 'л', 'Л'],
  ['l', 'L', 'д', 'Д'],
  [';', ':', 'ж', 'Ж'],
  ["'", '"', 'э', 'Э'],
  ['z', 'Z', 'я', 'Я'],
  ['x', 'X', 'ч', 'Ч'],
  ['c', 'C', 'с', 'С'],
  ['v', 'V', 'м', 'М'],
  ['b', 'B', 'и', 'И'],
  ['n', 'N', 'т', 'Т'],
  ['m', 'M', 'ь', 'Ь'],
  [',', '<', 'б', 'Б'],
  ['.', '>', 'ю', 'Ю'],
  ['/', '?', '.', ','],
];
const BOS = 95, EOS = 96, PAD = 0, VOCAB = 97;
const MAX_TOKEN_KEYS = 20; // "the 20-key limit" (20.12 table) -- see finding on tok25

const OTHER = { en: 'ru', ru: 'en' };
const col = (layout) => (layout === 'en' ? 0 : 2);

// letter keys per layout (derived from the table: unshifted char is a letter)
const EN_LETTER = new Set();
const RU_LETTER = new Set();
for (let k = 0; k < 47; k++) {
  if (/^[a-z]$/.test(TABLE[k][0])) EN_LETTER.add(k);
  if (/^[а-яё]$/u.test(TABLE[k][2])) RU_LETTER.add(k);
}
const LETTER_SET = { en: EN_LETTER, ru: RU_LETTER };
// L: the 33 keys that are a letter in at least one layout
const L = new Set([...EN_LETTER, ...RU_LETTER]);

function isLetterKey(layout, k) { return LETTER_SET[layout].has(k); }

// A key event: {k, shift, caps, layout}
function Key(k, shift, caps, layout) { return { k, shift: !!shift, caps: !!caps, layout }; }

// token (5.1): 1 + 2k + s, s = raw_shift XOR (caps AND k in L)
function token(key) {
  const s = (key.shift ? 1 : 0) ^ ((key.caps && L.has(key.k)) ? 1 : 0);
  return 1 + 2 * key.k + s;
}

// text of one key on a target layout (5.1 rule 2)
function charOn(key, layout) {
  const s = (key.shift ? 1 : 0) ^ ((key.caps && isLetterKey(layout, key.k)) ? 1 : 0);
  return TABLE[key.k][col(layout) + s];
}

// render a key list on a target layout
function render(keys, layout) { return keys.map((k) => charOn(k, layout)).join(''); }

// tokens of a key list (model input). eos=false gives a prefix sample.
// Limit of 20 keys: assumption (spec does not say what happens past 20; see report).
function tokens(keys, eos = true, maxKeys = MAX_TOKEN_KEYS) {
  const cut = keys.length > maxKeys;
  const ks = cut ? keys.slice(0, maxKeys) : keys;
  const out = [BOS, ...ks.map(token)];
  if (eos && !cut) out.push(EOS);
  return out;
}

// reverse lookup text -> keys (caps off) for one layout
const REV = { en: new Map(), ru: new Map() };
for (let k = 0; k < 47; k++) {
  for (let s = 0; s < 2; s++) {
    for (const layout of ['en', 'ru']) {
      const ch = TABLE[k][col(layout) + s];
      if (!REV[layout].has(ch)) REV[layout].set(ch, [k, s]);
    }
  }
}
function keysFromText(text, layout, caps = false) {
  const out = [];
  for (const ch of text) {
    const hit = REV[layout].get(ch);
    if (!hit) return null;
    out.push(Key(hit[0], hit[1] === 1, caps, layout));
  }
  return out;
}

module.exports = {
  TABLE, BOS, EOS, PAD, VOCAB, OTHER, L, EN_LETTER, RU_LETTER,
  isLetterKey, Key, token, charOn, render, tokens, keysFromText, REV,
};
