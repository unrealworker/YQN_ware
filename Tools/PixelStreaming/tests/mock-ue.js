'use strict';
const WebSocket = require('ws');
const ws = new WebSocket(`ws://127.0.0.1:${process.argv[2]}`);
ws.on('message', bytes => {
  const m = JSON.parse(bytes);
  if (m.type === 'identify') ws.send(JSON.stringify({ type: 'endpointId', id: process.argv[3] }));
  if (m.type === 'playerConnected') ws.send(JSON.stringify({ type: 'offer', playerId: m.playerId, sdp: 'mock-offer-' + process.argv[3] }));
  if (m.type === 'answer') ws.send(JSON.stringify({ type: 'iceCandidate', playerId: m.playerId, candidate: { candidate: 'answer-received', sdpMid: '0', sdpMLineIndex: 0 } }));
});
ws.on('error', () => process.exit(2));
setInterval(() => {}, 1000);
