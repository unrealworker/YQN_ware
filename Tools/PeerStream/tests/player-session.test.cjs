const {test}=require('node:test');
const assert=require('node:assert/strict');
const {socketUrl,bindSession}=require('../player-session.js');

test('player URL preserves proxy subdirectory and discards search/hash',()=>{
  assert.equal(socketUrl('https://warehouse-sim.iyunquna.com/peer-stream/?x=1#stats'),'wss://warehouse-sim.iyunquna.com/peer-stream/');
  assert.equal(socketUrl('https://warehouse-sim.iyunquna.com/peer-stream/player.html'),'wss://warehouse-sim.iyunquna.com/peer-stream/');
  assert.equal(socketUrl('http://127.0.0.1:8088/'),'ws://127.0.0.1:8088/');
});
test('ending a session disables reconnect and releases media once despite late callbacks',()=>{
  let socketClose=0,peerClose=0,paused=0,forwarded=0,connected=0,notice=0;
  const timers=[];
  const player={reconnect:123,ws:{onclose:()=>{},close(){socketClose++;}},pc:{close(){peerClose++;}},audio:{pause(){paused++;},srcObject:{}},pause(){paused++;},srcObject:{},onWebSocketMessage(){forwarded++;},connectedCallback(){connected++;}};
  const session=bindSession(player,()=>notice++,{clearTimeout:id=>timers.push(id)});
  player.onWebSocketMessage('{"type":"offer"}'); assert.equal(forwarded,1);
  session.stop('已结束','已释放');
  player.connectedCallback(); player.onWebSocketMessage('{"type":"offer"}'); session.stop('第二次');
  assert.equal(session.ended,true); assert.equal(connected,0); assert.equal(forwarded,1);
  assert.equal(socketClose,1); assert.equal(peerClose,1); assert.equal(paused,2); assert.equal(notice,1);
  assert.equal(player.srcObject,null); assert.equal(player.audio.srcObject,null); assert.equal(player.ws.onclose,null); assert.deepEqual(timers,[123]);
});
test('server stop and deployment failure are terminal without implicit reconnect',()=>{
  for(const type of ['deploymentStopped','deploymentError']) {
    let forwarded=0;
    const p={ws:{close(){}},pc:{close(){}},pause(){},onWebSocketMessage(){forwarded++;},connectedCallback(){}};
    const s=bindSession(p,()=>{}, {clearTimeout(){}});
    p.onWebSocketMessage(JSON.stringify({type}));
    assert.equal(s.ended,true); assert.equal(forwarded,0);
  }
});
