/* Offline ZIP writer: UTF-8 names, STORE compression, CRC32; no dependencies/network. */
const SaasZip=(()=>{
 const table=new Uint32Array(256);
 for(let n=0;n<256;n++){let c=n;for(let k=0;k<8;k++)c=c&1?0xedb88320^(c>>>1):c>>>1;table[n]=c>>>0;}
 function crc32(bytes){let c=0xffffffff;for(const b of bytes)c=table[(c^b)&255]^(c>>>8);return(c^0xffffffff)>>>0;}
 function bytes(value){return typeof value==='string'?new TextEncoder().encode(value):value instanceof Uint8Array?value:new Uint8Array(value);}
 function build(files,date=new Date()){
  if(files.length>65535)throw new Error('ZIP 文件数超过限制');
  const names=new Set(),local=[],central=[];let offset=0,centralSize=0;
  const dosTime=(date.getHours()<<11)|(date.getMinutes()<<5)|(date.getSeconds()>>1),dosDate=((Math.max(1980,date.getFullYear())-1980)<<9)|((date.getMonth()+1)<<5)|date.getDate();
  for(const file of files){
   if(names.has(file.name))throw new Error('ZIP 文件名重复：'+file.name);names.add(file.name);
   const name=bytes(file.name),data=bytes(file.data),crc=crc32(data);
   if(name.length>65535||data.length>0xffffffff||offset>0xffffffff)throw new Error('ZIP 大小超过限制');
   const h=new Uint8Array(30+name.length),v=new DataView(h.buffer);
   v.setUint32(0,0x04034b50,true);v.setUint16(4,20,true);v.setUint16(6,0x800,true);v.setUint16(8,0,true);v.setUint16(10,dosTime,true);v.setUint16(12,dosDate,true);v.setUint32(14,crc,true);v.setUint32(18,data.length,true);v.setUint32(22,data.length,true);v.setUint16(26,name.length,true);h.set(name,30);
   local.push(h,data);
   const c=new Uint8Array(46+name.length),cv=new DataView(c.buffer);
   cv.setUint32(0,0x02014b50,true);cv.setUint16(4,20,true);cv.setUint16(6,20,true);cv.setUint16(8,0x800,true);cv.setUint16(10,0,true);cv.setUint16(12,dosTime,true);cv.setUint16(14,dosDate,true);cv.setUint32(16,crc,true);cv.setUint32(20,data.length,true);cv.setUint32(24,data.length,true);cv.setUint16(28,name.length,true);cv.setUint32(42,offset,true);c.set(name,46);
   central.push(c);offset+=h.length+data.length;centralSize+=c.length;
  }
  if(offset+centralSize+22>0xffffffff)throw new Error('ZIP 超过4GB，未使用ZIP64');
  const end=new Uint8Array(22),e=new DataView(end.buffer);e.setUint32(0,0x06054b50,true);e.setUint16(8,files.length,true);e.setUint16(10,files.length,true);e.setUint32(12,centralSize,true);e.setUint32(16,offset,true);
  const result=new Uint8Array(offset+centralSize+22);let cursor=0;for(const part of local.concat(central,[end])){result.set(part,cursor);cursor+=part.length;}return result;
 }
 return{build,crc32};
})();
if(typeof module!=='undefined')module.exports=SaasZip;
