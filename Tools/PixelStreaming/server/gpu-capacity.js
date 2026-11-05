'use strict';
const fs=require('node:fs'),path=require('node:path');
const {execFile}=require('node:child_process');

function parseGpuCapacity(text,now=Date.now()) {
  if(typeof text!=='string'||text.length>8192||!text.trim())return null;
  const rows=text.trim().split(/\r?\n/).map(line=>line.trim().split(/\s*,\s*/));
  if(rows.some(row=>row.length!==2||!row.every(value=>/^\d+(?:\.\d+)?$/.test(value))))return null;
  const values=rows.map(row=>row.map(Number));
  if(values.some(([free,total])=>!Number.isFinite(free)||!Number.isFinite(total)||total<=0||total>1048576||free>total))return null;
  // Use the smallest headroom above the pool's reserve, including its percentage
  // floor. Absolute free memory alone can hide pressure on a larger adapter.
  const margin=([free,total])=>free-Math.max(3072,total*.2);
  const [gpuFreeMiB,gpuTotalMiB]=values.reduce((a,b)=>margin(b)<margin(a)?b:a);
  return {gpuFreeMiB,gpuTotalMiB,gpuReceivedAt:now};
}

function createGpuCapacityProbe(options={}) {
  const run=options.execFile||execFile,now=options.now||Date.now;
  const candidates=process.platform==='win32'
    ?[path.join(process.env.SystemRoot||'C:\\Windows','System32','nvidia-smi.exe'),path.join(process.env.ProgramFiles||'C:\\Program Files','NVIDIA Corporation','NVSMI','nvidia-smi.exe')]
    :['/usr/bin/nvidia-smi'];
  const executable=options.execFile?'nvidia-smi':candidates.find(file=>fs.existsSync(file));
  let running=false,pending=false,child=null,timer=null,latest=null,generation=0;
  function query() {
    if(!running||pending||!executable)return;
    pending=true;const activeGeneration=generation;
    try {
      child=run(executable,['--query-gpu=memory.free,memory.total','--format=csv,noheader,nounits'],{windowsHide:true,timeout:3000,maxBuffer:8192,encoding:'utf8'},(error,stdout)=>{
        if(!running||activeGeneration!==generation)return;
        pending=false;child=null;latest=error?null:parseGpuCapacity(stdout,now());
      });
    } catch {pending=false;child=null;latest=null;}
  }
  return {
    start(){if(running)return;running=true;generation++;query();timer=setInterval(query,options.intervalMs||10000);timer.unref?.();},
    stop(){running=false;generation++;clearInterval(timer);timer=null;latest=null;pending=false;child?.kill();child=null;},
    snapshot(){return latest?{...latest}:null;}
  };
}
module.exports={parseGpuCapacity,createGpuCapacityProbe};
