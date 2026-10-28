/* UE5.4 frontend 1.1.6 compatibility and receiver diagnostics; no extra stats poll. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.GHSStreamQuality = api;
})(typeof window === 'object' ? window : globalThis, function () {
  'use strict';
  const finite = n => typeof n === 'number' && Number.isFinite(n);
  function configureBitrates(config, session) {
    const min = session.minBitrateMbps, max = session.maxBitrateMbps;
    // Old launchers did not return startBitrateMbps; retain their 8 Mbps default
    // within the advertised range. New sessions always supply all three values.
    const start = session.startBitrateMbps === undefined ? Math.min(max, Math.max(min, 8)) : session.startBitrateMbps;
    if (![min, start, max].every(n => finite(n) && n >= 1 && n <= 200) || min > start || start > max) throw Error('会话码率配置无效，请检查启动器设置');
    const budget = { min: Math.round(min * 1000), start: Math.round(start * 1000), max: Math.round(max * 1000) };
    config.setNumericSetting('WebRTCMinBitrate', budget.min);
    config.setNumericSetting('WebRTCMaxBitrate', budget.max);
    // The generated SDK calls this per-Config hook in both offer and answer paths.
    // Keep policy on the session, isolated from other players and SDK defaults.
    config.ghsMungeVideoSDP = sdp => rewriteVideoBitrates(sdp, budget);
  }
  function rewriteVideoBitrates(sdp, budget) {
    const newline = sdp.includes('\r\n') ? '\r\n' : '\n';
    const hints = `x-google-min-bitrate=${budget.min};x-google-start-bitrate=${budget.start};x-google-max-bitrate=${budget.max}`;
    return sdp.split(/(?=^m=)/m).map(section => {
      if (!/^m=video (?!0(?:\s|$))/.test(section)) return section;
      const lines = section.split(/\r?\n/), payloads = new Set(), existing = new Set();
      for (const line of lines) {
        const match = /^a=rtpmap:(\d+) (?:H264|VP8|VP9|AV1)\/\d+/i.exec(line);
        if (match) payloads.add(match[1]);
      }
      for (let i = 0; i < lines.length; i++) {
        const fmtp = /^a=fmtp:(\d+) (.*)$/.exec(lines[i]);
        if (!fmtp || !payloads.has(fmtp[1])) continue;
        existing.add(fmtp[1]);
        const parameters = fmtp[2].split(';').filter(p => p.trim() && !/^x-google-(?:min|start|max)-bitrate\s*=/i.test(p.trim()));
        lines[i] = `a=fmtp:${fmtp[1]} ` + [...parameters, hints].join(';');
      }
      return lines.flatMap(line => {
        const rtp = /^a=rtpmap:(\d+) /.exec(line);
        return rtp && payloads.has(rtp[1]) && !existing.has(rtp[1]) ? [line, `a=fmtp:${rtp[1]} ${hints}`] : [line];
      }).join(newline);
    }).join('');
  }
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
  return { configureBitrates, configureUncapped, configureReceivers, createMeter, describePath };
});
