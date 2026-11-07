'use strict';
const S = require('./lf_scen.js');
const { loadExpected } = require('./expected.js');
const E = loadExpected();
for (const variant of ['first', 'fixed']) {
  const tr = S.traceRun(variant); let ok = 0;
  tr.forEach((r, i) => { if (JSON.stringify(r) === JSON.stringify(E.trace_run[i])) ok++; else console.log(variant, 'trace_run FAIL', JSON.stringify(r), JSON.stringify(E.trace_run[i])); });
  console.log(variant, 'trace_run', ok, E.trace_run.length);
}
const tu = S.traceUndo('first'); let ok = 0;
tu.forEach((r, i) => { if (JSON.stringify(r) === JSON.stringify(E.trace_undo[i])) ok++; else console.log('trace_undo FAIL', JSON.stringify(r), JSON.stringify(E.trace_undo[i])); });
console.log('trace_undo', ok, E.trace_undo.length);
const sc = S.scenarios(); ok = 0;
for (const [name, exp] of E.scen) { if (JSON.stringify(sc[name]) === JSON.stringify(exp)) ok++; else console.log('scen FAIL', name, JSON.stringify(sc[name]), JSON.stringify(exp)); }
console.log('scen', ok, E.scen.length);
