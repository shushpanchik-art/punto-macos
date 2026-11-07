'use strict';
// Extracts the expected JSON of spec section 20.12 from the specification text itself.
const fs = require('fs');
const path = require('path');
function loadExpected() {
  const txt = fs.readFileSync(path.join(__dirname, 'spec_without_code.md'), 'utf8');
  const marker = 'Expected output of `python vectors.py`';
  const i = txt.indexOf(marker);
  if (i < 0) throw new Error('marker not found');
  const j = txt.indexOf('```json', i);
  const k = txt.indexOf('\n```', j + 7);
  const body = txt.slice(j + 7, k);
  return JSON.parse(body);
}
module.exports = { loadExpected };
