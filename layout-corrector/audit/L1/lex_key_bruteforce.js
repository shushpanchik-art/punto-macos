const S=require('./lf_stats.js'); const A=require('./lf_cal.js');
const target={hello:'0x1f466cfcfe5bb68c',привет:'0x5ac2513bb852af1f',МТС:'0x3a1b89f4ad0b309e'};
const tags={hello:'lex_en',привет:'lex_ru',МТС:'acr_ru'};
const pre=[];
for (let b=0;b<256;b++) pre.push([b]);
function tryit(label,f){ for(const w of Object.keys(target)){ const h=S.hex(f(w)); if(h===target[w]) console.log('MATCH',label,w);} }
for (const b of pre){ tryit('pre'+b,(w)=>S.fnv1a64([...b,...S.utf8(w.toLowerCase())])); tryit('post'+b,(w)=>S.fnv1a64([...S.utf8(w.toLowerCase()),...b])); }
tryit('tag+word',w=>S.fnv1a64([...S.utf8(tags[w]),...S.utf8(w.toLowerCase())]));
tryit('tag+0+word',w=>S.fnv1a64([...S.utf8(tags[w]),0,...S.utf8(w.toLowerCase())]));
tryit('word+0+tag',w=>S.fnv1a64([...S.utf8(w.toLowerCase()),0,...S.utf8(tags[w])]));
tryit('lang',w=>S.fnv1a64([...S.utf8(w.toLowerCase())]));
tryit('nfc',w=>S.fnv1a64([...S.utf8(w.normalize('NFC').toLowerCase())]));
// fnv1 (not 1a)
function fnv1(bytes){let h=0xcbf29ce484222325n;const M=(1n<<64n)-1n;for(const b of bytes){h=(h*0x100000001b3n)&M;h^=BigInt(b);}return h;}
tryit('fnv1',w=>fnv1(S.utf8(w.toLowerCase())));
// wb_score T
const z=[-36.612053,-4.207615,-25.571149];
for (const T of [0.5,1,1.5,2,2.5,3,4,5]) { const c={T,oLat:0.25,piTrainCounts:[38,40,22]}; console.log(T,A.score(z,'en','default',c).toFixed(3)); }
