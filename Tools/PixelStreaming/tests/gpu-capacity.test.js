'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const {parseGpuCapacity,createGpuCapacityProbe}=require('../server/gpu-capacity');
test('GPU reserve uses the worst absolute or proportional headroom and rejects malformed snapshots',()=>{
  assert.deepEqual(parseGpuCapacity('12288, 16384\n4096, 24576\n',100),{gpuFreeMiB:4096,gpuTotalMiB:24576,gpuReceivedAt:100});
  assert.deepEqual(parseGpuCapacity('4096, 16384\n5000, 49152\n',100),{gpuFreeMiB:5000,gpuTotalMiB:49152,gpuReceivedAt:100});
  for(const text of ['', 'N/A, 16384', '-1, 16384','18000, 16384','4096, 0','4096, 16384\nunknown'])assert.equal(parseGpuCapacity(text,100),null);
});
test('GPU probe is asynchronous, single-flight, bounded, and stop ignores late callback',()=>{
  let callback,calls=0,killed=0,requestedOptions;
  const probe=createGpuCapacityProbe({now:()=>100,execFile:(file,args,options,done)=>{calls++;requestedOptions=options;callback=done;return{kill(){killed++;}};},intervalMs:100000});
  probe.start();probe.start();assert.equal(calls,1);assert.equal(probe.snapshot(),null);assert.equal(requestedOptions.timeout,3000);assert.equal(requestedOptions.windowsHide,true);
  callback(null,'8192, 16384');assert.equal(probe.snapshot().gpuFreeMiB,8192);
  probe.stop();assert.equal(probe.snapshot(),null);assert.equal(killed,0);
  const late=createGpuCapacityProbe({execFile:(file,args,options,done)=>{callback=done;return{kill(){killed++;}};},intervalMs:100000});
  late.start();late.stop();callback(null,'8192, 16384');assert.equal(late.snapshot(),null);assert.equal(killed,1);
});
test('failed GPU query leaves resources unknown instead of reusing previous headroom forever',()=>{
  let callback;
  const probe=createGpuCapacityProbe({execFile:(file,args,options,done)=>{callback=done;return{kill(){}};},intervalMs:100000});
  probe.start();callback(Error('query failed'));assert.equal(probe.snapshot(),null);probe.stop();
});
