/* UE5.4 frontend 1.1.6 compatibility and receiver diagnostics; no extra stats poll. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.GHSStreamQuality = api;
})(typeof window === 'object' ? window : globalThis, function () {
  'use strict';
  const finite = n => typeof n === 'number' && Number.isFinite(n);
  function configureUncapped(config, fps) {
    if (fps !== 0) return;
    // The pinned SDK exposes its SettingNumber objects, but its FPS minimum is 1.
    // Change that single bound before constructing PixelStreaming so subsequent
    // InitialSettings messages cannot turn the server's uncapped 0 into 1 FPS.
    const setting = config.getNumericSettings?.().find(s => s.id === 'WebRTCFPS');
    if (setting) setting._min = 0;
    config.setNumericSetting('WebRTCFPS', 0);
  }
  function configureReceivers(peer) {
    let applied = false;
    for (const receiver of peer?.getReceivers?.() || []) {
      if (receiver.track?.kind !== 'video') continue;
      for (const key of ['jitterBufferTarget', 'playoutDelayHint']) {
        if (!(key in receiver)) continue;
        try { receiver[key] = 0; applied = true; } catch (_) { /* optional browser hint */ }
      }
    }
    return applied;
  }
  function createMeter() {
    let previous;
    return {
      reset() { previous = undefined; },
      update(video) {
        const out = { fps: finite(video.framesPerSecond) ? video.framesPerSecond : null, bitrateMbps: null, bufferMs: null, decodeMs: null, lossPercent: null, freezes: null };
        const same = previous && previous.id === video.id && previous.ssrc === video.ssrc;
        const dt = same ? (video.timestamp - previous.timestamp) / 1000 : 0;
        const delta = key => same && finite(video[key]) && finite(previous[key]) && video[key] >= previous[key] ? video[key] - previous[key] : null;
        if (dt > 0 && dt <= 10) {
          const frames = delta('framesDecoded'), bytes = delta('bytesReceived');
          const emitted = delta('jitterBufferEmittedCount'), delay = delta('jitterBufferDelay'), decode = delta('totalDecodeTime');
          if (frames !== null) out.fps = frames / dt;
          if (bytes !== null) out.bitrateMbps = bytes * 8 / dt / 1e6;
          if (emitted > 0 && delay !== null) out.bufferMs = delay / emitted * 1000;
          if (frames > 0 && decode !== null) out.decodeMs = decode / frames * 1000;
          const lost = delta('packetsLost'), received = delta('packetsReceived');
          if (lost !== null && received !== null && lost + received > 0) out.lossPercent = lost / (lost + received) * 100;
          out.freezes = delta('freezeCount');
        }
        previous = { ...video };
        return out;
      }
    };
  }
  function privateAddress(address) {
    return /^(10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|127\.|169\.254\.|f[cd][0-9a-f]{2}:|fe80:|::1$)/i.test(address || '');
  }
  function describePath(pair, locals = [], remotes = []) {
    if (!pair) return '协商中';
    const local = locals.find(c => c.id === pair.localCandidateId);
    const remote = remotes.find(c => c.id === pair.remoteCandidateId);
    const relay = [local, remote].find(c => c?.candidateType === 'relay');
    const protocol = (relay?.relayProtocol || remote?.protocol || local?.protocol || '未知').toUpperCase();
    const kind = relay ? 'TURN 中继' : privateAddress(remote?.address) ? '内网地址' : remote?.candidateType === 'srflx' || remote?.candidateType === 'prflx' ? '公网映射' : '直连';
    return kind + ' · ' + protocol;
  }
  return { configureUncapped, configureReceivers, createMeter, describePath };
});
