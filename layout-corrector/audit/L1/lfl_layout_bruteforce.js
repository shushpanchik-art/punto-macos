const S=require('./lf_stats.js'); const crypto=require('crypto');
const T=[[0xE1,'hello'],[0xE2,'привет'],[0xE3,'sql'],[0xE4,'мтс']];
const key=(t,w)=>S.fnv1a64([t,...S.utf8(w)]);
const want='c737f8710843f069';
function u(n,bytes,le){const b=Buffer.alloc(bytes);if(bytes===1)b[0]=n;else if(bytes===2)le?b.writeUInt16LE(n):b.writeUInt16BE(n);else if(bytes===4)le?b.writeUInt32LE(n):b.writeUInt32BE(n);else le?b.writeBigUInt64LE(BigInt(n)):b.writeBigUInt64BE(BigInt(n));return b;}
let found=0;
const orders=[[0,1,2,3],[0,1,3,2],[2,3,0,1],[3,2,1,0]];
for (const order of orders) for (const le of [true,false]) for (const tagB of [0,1,2,4,8]) for (const cntB of [1,2,4,8]) for (const keyLe of [true,false]) for (const hdr of ['LFL1','LFL1\x01','LFL1\x00']) for (const nt of [0,1,2,4]) for (const tagKind of ['byte','name']) {
  const parts=[Buffer.from(hdr,'latin1')];
  if (nt) parts.push(u(4,nt,le));
  for (const i of order){ const [t,w]=T[i];
    const name=['lex_en','lex_ru','acr_en','acr_ru'][i];
    if (tagKind==='byte'){ if(tagB) parts.push(u(t,tagB,le)); else continue; }
    else { const nb=Buffer.alloc(tagB||8); Buffer.from(name).copy(nb); parts.push(nb); }
    parts.push(u(1,cntB,le));
    const k=key(t,w); const b=Buffer.alloc(8); keyLe?b.writeBigUInt64LE(k):b.writeBigUInt64BE(k); parts.push(b);
  }
  const buf=Buffer.concat(parts);
  if (buf.length===84) { const h=crypto.createHash('sha256').update(buf).digest('hex').slice(0,16); if(h===want){console.log('MATCH',{order,le,tagB,cntB,keyLe,hdr:JSON.stringify(hdr),nt,tagKind});found++;} }
}
console.log('found',found);
