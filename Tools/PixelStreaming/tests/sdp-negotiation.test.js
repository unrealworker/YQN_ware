'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const crypto = require('node:crypto');
const quality = require('../player/stream-quality');
const { patchFrontendSDK } = require('../frontend-sdk-patch');
const sdkPath = path.join(__dirname, '../vendor/package/dist/lib-pixelstreamingfrontend.js');
const originalSDK = fs.readFileSync(sdkPath, 'utf8');
const patched = patchFrontendSDK(originalSDK);
const sdp = ['v=0', 'm=video 9 UDP/TLS/RTP/SAVPF 96 97', 'a=rtpmap:96 H264/90000',
  'a=fmtp:96 level-asymmetry-allowed=1;packetization-mode=1;profile-level-id=42e01f',
  'a=rtpmap:97 rtx/90000', 'a=fmtp:97 apt=96',
  'm=audio 9 UDP/TLS/RTP/SAVPF 111', 'a=rtpmap:111 opus/48000/2', 'a=fmtp:111 minptime=10;useinbandfec=1', ''].join('\r\n');

// Execute the shipped Epic UMD, real Config and real startSession/mungeSDP.
// Only the browser's media transport is substituted; the SDP code is not mocked.
function controller(code, session, configure = true) {
  const scope = { Event, EventTarget, URLSearchParams, console,
    location: { hostname: 'localhost', protocol: 'https:', search: '' }, navigator: {},
    RTCPeerConnection: class {
      constructor() { this.transceivers = []; }
      getTransceivers() { return this.transceivers; }
      addTransceiver(kind) { this.transceivers.push({ receiver: { track: { kind } } }); }
      async setRemoteDescription(description) { this.remoteDescription = description; }
      async setLocalDescription(description) { this.currentLocalDescription = description; }
      async createOffer() { return { type: 'offer', sdp }; }
      async createAnswer() { return { type: 'answer', sdp }; }
    },
    RTCRtpReceiver: { getCapabilities: () => ({ codecs: [{ mimeType: 'video/H264', sdpFmtpLine: 'profile-level-id=42e01f' }] }) },
    sdp: require('../vendor/sdp/sdp.js') };
  scope.window = scope;
  vm.runInNewContext(code, scope, { filename: 'epic-sdk.js' });
  const sdk = scope['lib-pixelstreamingfrontend'];
  const config = new sdk.Config({ useUrlParams: false, initialSettings: { BrowserSendOffer: false,
    WebRTCMinBitrate: session.minBitrateMbps * 1000, WebRTCMaxBitrate: session.maxBitrateMbps * 1000 } });
  if (configure) quality.configureBitrates(config, session);
  const owner = Object.create(sdk.WebRtcPlayerController.prototype); owner.config = config;
  owner.preferredCodec = ''; owner.pixelStreaming = { _onWebRtcConnecting() {}, _onWebRtcFailed() {} };
  owner.startSession({ iceServers: [] });
  return owner.peerConnectionController;
}

test('actual SDK SDP uses the session startup and maximum bitrates', () => {
  const peer = controller(patched.code, { minBitrateMbps: 1, startBitrateMbps: 8, maxBitrateMbps: 24 });
  const result = peer.mungeSDP(sdp, false);
  assert.match(result, /x-google-start-bitrate=8000(?:;|\r\n)/);
  assert.match(result, /x-google-max-bitrate=24000(?:;|\r\n)/);
  assert.match(result, /x-google-min-bitrate=1000(?:;|\r\n)/);
});

test('the pinned archive is intact and SDK changes fail closed at build time', () => {
  const pin = require('../dependency-pins.json').packages.find(p => p.name.includes('frontend'));
  const bytes = fs.readFileSync(path.join(__dirname, '../vendor', pin.archive));
  assert.equal('sha512-' + crypto.createHash('sha512').update(bytes).digest('base64'), pin.integrity);
  assert.equal(patched.manifest.replacements, 1);
  assert.equal(crypto.createHash('sha256').update(originalSDK).digest('hex'), patched.manifest.originalSha256);
  assert.equal(crypto.createHash('sha256').update(patched.code).digest('hex'), patched.manifest.patchedSha256);
  assert.throws(() => patchFrontendSDK(originalSDK + '\n'), /SHA256/);
  assert.throws(() => patchFrontendSDK(patched.code), /SHA256/);
});

test('the generated player bundle and provenance match the verified build patch', () => {
  const built = fs.readFileSync(path.join(__dirname, '../player/vendor/epic-ue5.4-1.1.6.js'), 'utf8');
  const manifest = JSON.parse(fs.readFileSync(path.join(__dirname, '../player/vendor/epic-sdp-patch.json'), 'utf8'));
  assert.equal(built, patched.code, 'run node build.js after changing the frontend build patch');
  assert.equal(manifest.patchedSha256, patched.manifest.patchedSha256);
  for (const [field, file] of [['patchScriptSha256', '../frontend-sdk-patch.js'], ['qualityPolicySha256', '../player/stream-quality.js']]) {
    assert.equal(manifest[field], crypto.createHash('sha256').update(fs.readFileSync(path.join(__dirname, file))).digest('hex'));
  }
  const peer = controller(built, { minBitrateMbps: 2, startBitrateMbps: 6, maxBitrateMbps: 18 });
  assert.match(peer.mungeSDP(sdp, false), /x-google-min-bitrate=2000;x-google-start-bitrate=6000;x-google-max-bitrate=18000/);
});

test('actual SDK offer and answer signalling both carry the custom session budget', async () => {
  for (const type of ['offer', 'answer']) {
    const peer = controller(patched.code, { minBitrateMbps: 1.25, startBitrateMbps: 5.5, maxBitrateMbps: 15.75 });
    let sent;
    peer.onSendWebRTCOffer = description => { sent = description; };
    peer.onSendWebRTCAnswer = description => { sent = description; };
    if (type === 'offer') await peer.createOffer({}, peer.config);
    else await peer.receiveOffer({ type: 'offer', sdp }, peer.config);
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(sent?.type, type);
    assert.equal(sent?.sdp, peer.peerConnection.currentLocalDescription.sdp);
    assert.match(sent.sdp, /x-google-min-bitrate=1250;x-google-start-bitrate=5500;x-google-max-bitrate=15750/);
    assert.doesNotMatch(sent.sdp, /x-google-start-bitrate=10000|x-google-max-bitrate=100000/);
  }
});

test('video policy replaces stale duplicate hints without changing codecs RTX ICE or audio behavior', () => {
  const session = { minBitrateMbps: 1, startBitrateMbps: 8, maxBitrateMbps: 24 };
  const peer = controller(patched.code, session), baseline = controller(originalSDK, session, false);
  const input = sdp.replace('profile-level-id=42e01f', 'profile-level-id=42e01f;x-google-start-bitrate=10000;x-google-max-bitrate=100000; x-google-max-bitrate=90000')
    .replace('m=audio', 'a=candidate:1 1 udp 2122260223 10.100.185.161 50000 typ host\r\nm=audio');
  for (const mic of [false, true]) {
    const actual = peer.mungeSDP(input, mic), old = baseline.mungeSDP(input, mic);
    assert.equal(actual.slice(actual.indexOf('m=audio')), old.slice(old.indexOf('m=audio')));
    assert.match(actual, /level-asymmetry-allowed=1;packetization-mode=1;profile-level-id=42e01f;/);
    assert.match(actual, /a=fmtp:97 apt=96\r\n/);
    assert.match(actual, /10\.100\.185\.161 50000 typ host/);
    assert.equal((actual.match(/x-google-max-bitrate=/g) || []).length, 1);
    assert.equal((actual.match(/x-google-start-bitrate=/g) || []).length, 1);
    assert.equal(peer.config.ghsMungeVideoSDP(actual), actual, 'video rewrite is idempotent across renegotiation');
  }
});

test('video-only policy handles multiple payloads and missing fmtp while preserving rejected and data sections', () => {
  const peer = controller(patched.code, { minBitrateMbps: 1, startBitrateMbps: 2, maxBitrateMbps: 3 });
  const input = ['v=0', 'm=video 9 UDP/TLS/RTP/SAVPF 96 97', 'a=rtpmap:96 VP8/90000', 'a=rtpmap:97 VP9/90000', 'a=fmtp:97 profile-id=0',
    'm=video 0 UDP/TLS/RTP/SAVPF 98', 'a=rtpmap:98 H264/90000', 'a=fmtp:98 profile-level-id=42e01f',
    'm=application 9 UDP/DTLS/SCTP webrtc-datachannel', 'a=sctp-port:5000', ''].join('\n');
  const output = peer.mungeSDP(input, false);
  assert.equal((output.match(/x-google-max-bitrate=3000/g) || []).length, 2);
  assert.match(output, /a=fmtp:97 profile-id=0;x-google-min-bitrate=1000/);
  assert.equal(output.slice(output.indexOf('m=video 0')), input.slice(input.indexOf('m=video 0')));
});

test('sessions remain isolated and old launchers use their clamped 8 Mbps startup default', () => {
  const a = controller(patched.code, { minBitrateMbps: 1, startBitrateMbps: 4, maxBitrateMbps: 12 });
  const b = controller(patched.code, { minBitrateMbps: 2, startBitrateMbps: 7, maxBitrateMbps: 16 });
  assert.match(a.mungeSDP(sdp, false), /start-bitrate=4000;x-google-max-bitrate=12000/);
  assert.match(b.mungeSDP(sdp, false), /start-bitrate=7000;x-google-max-bitrate=16000/);
  assert.match(a.mungeSDP(sdp, false), /start-bitrate=4000;x-google-max-bitrate=12000/);
  for (const [min, max, expected] of [[1, 24, 8000], [1, 6, 6000], [12, 35, 12000]]) {
    const legacy = controller(patched.code, { minBitrateMbps: min, maxBitrateMbps: max });
    assert.ok(legacy.mungeSDP(sdp, false).includes('x-google-start-bitrate=' + expected + ';'));
  }
  const noPolicy = controller(patched.code, { minBitrateMbps: 1, maxBitrateMbps: 24 }, false);
  assert.doesNotMatch(noPolicy.mungeSDP(sdp, false), /x-google-/);
});

test('invalid budgets are rejected before starting media negotiation', () => {
  for (const session of [
    { minBitrateMbps: 1, startBitrateMbps: NaN, maxBitrateMbps: 24 },
    { minBitrateMbps: 1, startBitrateMbps: 30, maxBitrateMbps: 24 },
    { minBitrateMbps: 9, startBitrateMbps: 8, maxBitrateMbps: 24 },
    { minBitrateMbps: 1, startBitrateMbps: 8, maxBitrateMbps: Infinity }
  ]) assert.throws(() => quality.configureBitrates({}, session), /会话码率配置无效/);
});
