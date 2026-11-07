'use strict';
// Part 2 (spec 5.3, 13.1 guard table, 20.3, 20.4 prose, 20.8, 13.3): candidate, shape guards, manual conversion.
const K = require('./lf_keys.js');

const OPENERS = new Set(['(', '[', '{', '"', "'"]);
const TRAILING = new Set(['.', ',', ';', ':', '!', '?', '"', "'", ')', ']', '}']);

// 5.3 steps 1-5. keys: array of Key typed on the layout other than T (target).
// returns {opener, core, marks, nOpen, nCore, nMarks, coreKeys, text} (strings read on T) or null
function candidate(keys, T) {
  const n = keys.length;
  if (n === 0) return null;
  const rd = keys.map((k) => K.renderKey(k, T));
  const isLet = keys.map((k) => K.letterIn(T, k.k)); // "is a letter on T" is a property of the key on T
  let start = 0;
  // 2. leading opener (at most one)
  if (OPENERS.has(rd[0]) && !isLet[0]) start = 1;
  // 3. peel up to two trailing marks from the end
  let end = n;
  let peeled = 0;
  while (peeled < 2 && end > start && TRAILING.has(rd[end - 1]) && !isLet[end - 1]) { end--; peeled++; }
  // 4. core: non-empty, all letters on T
  if (end - start < 1) return null;
  for (let i = start; i < end; i++) if (!isLet[i]) return null;
  return {
    opener: rd.slice(0, start).join(''),
    core: rd.slice(start, end).join(''),
    marks: rd.slice(end).join(''),
    nCore: end - start,
    coreKeys: keys.slice(start, end),
    text: rd.join(''), // 5. replacement text = whole run read on T
  };
}

// ---- 20.4 shape guards (code removed; reconstructed from the prose of 13.1 / 20.4 / 5.2 table) ----
// ASSUMPTION lists: the spec says "The suffix list is the starting list of the first release" but does not print it.
const SUFFIXES = ['com', 'org', 'net', 'io', 'ru', 'edu', 'gov', 'info', 'dev', 'app', 'txt', 'pdf', 'doc', 'docx', 'xls', 'xlsx', 'py', 'js', 'ts', 'html', 'css', 'json', 'xml', 'md', 'png', 'jpg', 'zip', 'exe', 'sh', 'cpp', 'java', 'рф', 'su', 'ua', 'by'];
const ROW_OF = (k) => (k <= 12 ? 0 : k <= 25 ? 1 : k <= 36 ? 2 : 3); // number row, top, home, bottom rows
function shapeGuard(keys) {
  const reads = ['en', 'ru'].map((lay) => K.render(keys, lay));
  for (const r of reads) if (/:\/\/|(^|[^\p{L}])www\./iu.test(r)) return 'shape_url';
  for (const r of reads) if (/^[\p{L}\p{N}._%+-]+@[\p{L}\p{N}-]+(\.[\p{L}\p{N}-]+)+$/u.test(r)) return 'shape_email';
  const sfx = new RegExp('[\\p{L}\\p{N}_-]\\.(' + SUFFIXES.join('|') + ')$', 'iu');
  for (const r of reads) if (sfx.test(r)) return 'shape_dotted';
  // camelCase: a lower-case letter directly followed by an upper-case letter, in either reading
  for (const r of reads) if (/\p{Ll}\p{Lu}/u.test(r)) return 'shape_camel';
  // key walk: four neighbouring keys of one row in a monotone walk (either direction)
  for (let i = 0; i + 3 < keys.length; i++) {
    const ids = keys.slice(i, i + 4).map((x) => x.k);
    const d = ids[1] - ids[0];
    if ((d === 1 || d === -1) && ids.every((v, j) => j === 0 || v - ids[j - 1] === d) && ids.every((v) => ROW_OF(v) === ROW_OF(ids[0]))) return 'shape_keywalk';
  }
  return null;
}

// ---- 20.8 manual conversion ----
function manualDirection(text) {
  let cyr = 0, lat = 0;
  for (const ch of text) {
    if (/\p{Script=Cyrillic}/u.test(ch) && /\p{L}/u.test(ch)) cyr++;
    else if (/[A-Za-z]/.test(ch)) lat++;
  }
  if (cyr + lat === 0) return null;
  return cyr > lat ? 'ru2en' : 'en2ru';
}
function manualConvert(text) {
  const dir = manualDirection(text);
  if (dir === null) return [null, text];
  const src = dir === 'en2ru' ? 'en' : 'ru';
  const dst = K.other(src);
  let out = '';
  for (const ch of text) {
    let rep = ch;
    for (let k = 0; k < K.NKEYS; k++) {
      let hit = false;
      for (const sh of [false, true]) if (K.table(src, k, sh) === ch) { rep = K.table(dst, k, sh); hit = true; break; }
      if (hit) break;
    }
    out += rep;
  }
  return [dir, out];
}
module.exports = { candidate, shapeGuard, manualDirection, manualConvert, OPENERS, TRAILING };
