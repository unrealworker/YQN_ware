/* Epic UE5.4 owns WebRTC, input serialization, touch and keyboard handling. */
(() => {
  'use strict';
  const { Config, PixelStreaming, Flags, NumericParameters } = window['lib-pixelstreamingfrontend'];
  const $ = id => document.getElementById(id);
  let stream, sceneSearch, terminal = false, firstFrame = false, stage = 0, deadline, elapsedTimer, elapsedStart, sessionToken, reconnectTimer, reconnectAttempts = 0;
  const initialTime = performance.now();
  const metrics = { state: 'connecting', firstFrame: false, width: 0, height: 0, fps: 0, bitrateMbps: 0, rttMs: 0, decodedFrames: 0, mode: null, instanceId: null };
  let pan = null;
  const videoRoot = $('video-root');
  // Browser-level right-button gestures can run before a page receives input.
  // Shift + left drag is an alternative using Epic's public input protocol.
  function videoPoint(event, allowOutside = false) {
    const video = videoRoot.querySelector('video');
    if (!video || !video.videoWidth || !video.videoHeight) return null;
    const rect = video.getBoundingClientRect();
    const scale = Math.min(rect.width / video.videoWidth, rect.height / video.videoHeight);
    const width = video.videoWidth * scale, height = video.videoHeight * scale;
    if (width <= 0 || height <= 0) return null;
    const left = rect.left + (rect.width - width) / 2, top = rect.top + (rect.height - height) / 2;
    const x = (event.clientX - left) / width, y = (event.clientY - top) / height;
    if (!allowOutside && (x < 0 || x > 1 || y < 0 || y > 1)) return null;
    return { x: Math.max(0, Math.min(65535, Math.floor(x * 65536))), y: Math.max(0, Math.min(65535, Math.floor(y * 65536))), width, height };
  }
  function endPan(event) {
    if (!pan) return;
    const point = event && Number.isFinite(event.clientX) ? videoPoint(event, true) : pan.point;
    stream?.toStreamerHandlers.get('MouseUp')?.([2, (point || pan.point).x, (point || pan.point).y]);
    pan = null; videoRoot.classList.remove('panning');
  }
  const consumePan = event => { event.preventDefault(); event.stopImmediatePropagation(); };
  for (const type of ['contextmenu', 'dragstart', 'selectstart', 'auxclick']) videoRoot.addEventListener(type, event => event.preventDefault(), { capture: true });
  videoRoot.addEventListener('mousedown', event => {
    if (event.button !== 0 || !event.shiftKey || !firstFrame || terminal || !stream) return;
    const point = videoPoint(event);
    if (!point || !stream.toStreamerHandlers.has('MouseDown')) return;
    consumePan(event); videoRoot.focus({ preventScroll: true });
    pan = { point, clientX: event.clientX, clientY: event.clientY };
    videoRoot.classList.add('panning'); stream.toStreamerHandlers.get('MouseDown')([2, point.x, point.y]);
  }, { capture: true });
  window.addEventListener('mousemove', event => {
    if (!pan) return;
    consumePan(event);
    if (!(event.buttons & 1)) { endPan(event); return; }
    const point = videoPoint(event, true); if (!point) { endPan(); return; }
    const delta = (value, size) => Math.max(-32768, Math.min(32767, Math.trunc(value * 65534 / size)));
    stream.toStreamerHandlers.get('MouseMove')?.([point.x, point.y, delta(event.clientX - pan.clientX, point.width), delta(event.clientY - pan.clientY, point.height)]);
    pan = { point, clientX: event.clientX, clientY: event.clientY };
  }, { capture: true });
  window.addEventListener('mouseup', event => { if (pan && event.button === 0) { consumePan(event); endPan(event); } }, { capture: true });
  // Do not let Epic's enter/leave helpers reinterpret the physical left button
  // as a second, unrelated drag while the alternative pan is active.
  for (const type of ['mouseenter', 'mouseleave']) videoRoot.addEventListener(type, event => { if (pan) event.stopImmediatePropagation(); }, { capture: true });
  window.addEventListener('blur', () => endPan());
  document.addEventListener('visibilitychange', () => { if (document.hidden) endPan(); });
  // Read-only inspection snapshot for support / real-browser verification.
  Object.defineProperty(window, 'ghsStreamingStats', { get: () => Object.freeze({ ...metrics }) });
  function progress(value, title, text, presentation = 'running') {
    if (terminal || firstFrame) return;
    document.querySelector('.card').dataset.state = presentation;
    stage = Math.max(stage, Math.min(5, value)); $('connection-progress').value = stage; $('stage-title').textContent = title; $('stage-message').textContent = text;
    $('stage-count').textContent = `阶段 ${Math.max(1, stage)} / 5`;
    document.querySelectorAll('.stages li').forEach((item, i) => { item.dataset.state = i + 1 < stage ? 'done' : i + 1 === Math.max(1, stage) ? 'active' : 'waiting'; });
    document.querySelectorAll('.stage-segments span').forEach((item, i) => { item.dataset.state = i + 1 < stage ? 'done' : i + 1 === Math.max(1, stage) ? 'active' : 'waiting'; });
    $('connection-state').textContent = title; metrics.state = title;
  }
  function halt(title, text, evicted = false, presentation = 'fault') {
    endPan(); sceneSearch?.suspend();
    terminal = true; firstFrame = false; metrics.firstFrame = false; document.body.classList.remove('playing'); clearTimeout(deadline); clearTimeout(reconnectTimer); clearTimeout(elapsedTimer); metrics.state = evicted ? 'evicted' : 'stopped';
    if (evicted) sessionStorage.setItem('ghsEvicted', 'true');
    if (stream) { stream.config.setNumericSetting(NumericParameters.MaxReconnectAttempts, 0); stream.config.setFlagEnabled(Flags.WaitForStreamer, false); stream.disconnect(); }
    // Presentation only: retain the existing terminal, eviction and retry policy.
    const card = document.querySelector('.card'); card.classList.add('error'); card.dataset.state = evicted ? 'exited' : presentation;
    $('loading').hidden = false; $('allow-play').hidden = true; $('stage-title').textContent = title; $('stage-message').textContent = text; $('connection-state').textContent = title; $('retry').hidden = false;
  }
  function armDeadline() {
    clearTimeout(deadline); clearTimeout(elapsedTimer); elapsedStart = performance.now();
    const tick = () => { $('elapsed-time').textContent = `已等待 ${String(Math.floor((performance.now() - elapsedStart) / 1000)).padStart(2, '0')} 秒`; if (!terminal && !firstFrame) elapsedTimer = setTimeout(tick, 1000); }; tick();
    deadline = setTimeout(() => halt('连接超时', `视频连接等待超过 120 秒，尚未收到首帧（停留阶段 ${Math.max(1, stage)} / 5）。请检查启动器日志、UE 进程和内网连接，再点击重新进入。`), 120000);
  }
  function markFrame(video) {
    if (terminal || firstFrame || video.videoWidth === 0 || video.readyState < 2) return;
    firstFrame = true; reconnectAttempts = 0; metrics.firstFrame = true; metrics.state = 'playing'; metrics.firstFrameMs = Math.round(performance.now() - initialTime); clearTimeout(deadline); clearTimeout(elapsedTimer);
    $('connection-progress').value = 5; $('stage-count').textContent = '阶段 5 / 5'; $('loading').hidden = true; $('allow-play').hidden = true; document.body.classList.add('playing'); $('connection-state').textContent = '已连接'; updateDimensions(video); $('video-root').focus({ preventScroll: true }); sceneSearch?.ready();
  }
  function updateDimensions(video) { metrics.width = video.videoWidth; metrics.height = video.videoHeight; $('stat-resolution').textContent = `${video.videoWidth} × ${video.videoHeight}`; sceneSearch?.position(); }
  function watchVideo() {
    const video = $('video-root').querySelector('video'); if (!video || video.dataset.ghsWatched) return;
    video.dataset.ghsWatched = 'true'; video.autoplay = true; video.muted = true; video.playsInline = true; video.draggable = false;
    video.addEventListener('loadedmetadata', () => { updateDimensions(video); progress(4, '正在接收视频', '视频轨道已到达，等待第一帧解码显示'); });
    video.addEventListener('playing', () => { if (!video.requestVideoFrameCallback) markFrame(video); });
    if (video.requestVideoFrameCallback) video.requestVideoFrameCallback(() => markFrame(video));
  }
  new MutationObserver(watchVideo).observe($('video-root'), { childList: true, subtree: true });
  $('retry').onclick = () => { sessionStorage.removeItem('ghsSession'); sessionStorage.removeItem('ghsEvicted'); sessionStorage.removeItem('ghsReplaced'); location.reload(); };
  $('fullscreen').onclick = () => { if (document.fullscreenElement) document.exitFullscreen(); else document.documentElement.requestFullscreen().catch(() => {}); };
  $('audio-toggle').onclick = () => {
    if (!stream || terminal) return;
    const muted = !stream.config.isFlagEnabled(Flags.StartVideoMuted); stream.config.setFlagEnabled(Flags.StartVideoMuted, muted); stream.play();
    $('audio-toggle').textContent = muted ? '开启声音' : '静音'; $('audio-toggle').setAttribute('aria-pressed', String(!muted));
  };
  function autoplayBlocked() {
    if (terminal || firstFrame) return;
    document.querySelector('.card').dataset.state = 'waiting';
    $('stage-title').textContent = '浏览器暂未允许播放'; $('stage-message').textContent = '连接已建立，浏览器阻止了自动播放。允许播放后即可进入场景。'; $('allow-play').hidden = false;
  }
  $('allow-play').onclick = async () => {
    const video = videoRoot.querySelector('video'); if (!video || terminal) return;
    try { video.muted = true; await video.play(); stream?.play(); watchVideo(); }
    catch { autoplayBlocked(); }
  };
  async function start() {
    if (sessionStorage.getItem('ghsEvicted') === 'true') return halt('连接已被替换', '新访问者已进入，本标签页已停止自动重连。需要再次访问时，请主动点击“重新进入”。', true);
    if (sessionStorage.getItem('ghsReplaced') === 'true') return halt('已在其他标签页连接', '同一会话已在其他标签页连接，本页已停止自动重连。点击“重新进入”可申请独立名额。', false, 'exited');
    armDeadline();
    progress(1, '正在连接仓库', '正在获取访问会话，请稍候。');
    let response = await fetch('/api/session', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ token: sessionStorage.getItem('ghsSession') || undefined }) });
    if (response.status === 409) { sessionStorage.removeItem('ghsSession'); response = await fetch('/api/session', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' }); }
    const session = await response.json(); if (!response.ok) throw Error(session.error || '无法获取访问会话');
    if (session.evicted) return halt('连接已被替换', session.message, true);
    sessionToken = session.token; sessionStorage.setItem('ghsSession', sessionToken); metrics.mode = session.mode; $('stat-mode').textContent = session.mode === 'shared' ? '共享场景' : '独立场景';
    const wsUrl = `${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws?token=${encodeURIComponent(sessionToken)}`;
    // Own the reconnect timer so an eviction/replaced-tab message can cancel every queued attempt.
    const config = new Config({ useUrlParams: false, initialSettings: { AutoConnect: false, AutoPlayVideo: true, StartVideoMuted: true, HoveringMouse: true, MatchViewportRes: false, TimeoutIfIdle: false, WaitForStreamer: false, OfferToReceive: false, UseMic: false, MaxReconnectAttempts: 0, ss: wsUrl, WebRTCFPS: session.fps, WebRTCMinBitrate: session.minBitrateMbps * 1000, WebRTCMaxBitrate: session.maxBitrateMbps * 1000 } });
    stream = new PixelStreaming(config, { videoElementParent: $('video-root') }); watchVideo();
    sceneSearch = window.GHSSceneSearch.create({ stream, videoRoot, keyboardFlag: Flags.KeyboardInput, beforeFocus: endPan });
    const protocol = stream.webSocketController.signallingProtocol;
    protocol.addMessageHandler('ghsAdmission', payload => { const m = JSON.parse(payload); metrics.instanceId = m.instanceId; $('stat-instance').textContent = m.instanceId; progress(1, '已接入服务', '名额已分配，正在等待场景就绪', 'waiting'); });
    protocol.addMessageHandler('ghsStage', payload => { const m = JSON.parse(payload); progress(m.stage === 'streamerReady' ? 2 : 1, m.stage === 'streamerReady' ? '场景已就绪' : '正在启动场景', m.message, m.stage === 'streamerReady' ? 'running' : 'waiting'); });
    protocol.addMessageHandler('ghsEvicted', payload => halt('连接已被替换', JSON.parse(payload).message, true));
    protocol.addMessageHandler('ghsSessionReplaced', payload => { sessionStorage.setItem('ghsReplaced', 'true'); halt('已在其他标签页连接', JSON.parse(payload).message, false, 'exited'); });
    protocol.addMessageHandler('ghsShutdown', payload => halt('服务已停止', JSON.parse(payload).message, false, 'stopped'));
    protocol.addMessageHandler('ghsInstanceFailed', payload => halt('场景连接失败', JSON.parse(payload).message));
    stream.addEventListener('webRtcSdp', () => progress(3, '正在协商视频', '已交换视频会话信息，正在建立内网媒体连接'));
    stream.addEventListener('webRtcConnected', () => progress(4, '视频已连接', '媒体连接已建立，等待首帧显示'));
    stream.addEventListener('videoInitialized', watchVideo);
    stream.addEventListener('dataChannelOpen', () => { if (firstFrame && !terminal) sceneSearch.ready(); });
    stream.addEventListener('playerCount', e => { $('viewer-count').textContent = `${e.data.count} / 3`; metrics.viewerCount = e.data.count; });
    stream.addEventListener('webRtcDisconnected', e => { endPan(); sceneSearch?.suspend(); if (terminal) return; const wasPlaying = firstFrame; firstFrame = false; metrics.firstFrame = false; $('loading').hidden = false; document.body.classList.remove('playing'); stage = 0; progress(1, '正在恢复连接', '网络暂时中断，正在恢复当前会话；场景状态暂时保留。', 'waiting'); if (wasPlaying) armDeadline(); });
    stream.webSocketController.onClose.addEventListener('close', e => {
      if (terminal) return;
      if (e.detail.code === 4001) return halt('连接已被替换', '连接已被新访问者替换，已停止自动重连。', true);
      if (e.detail.code === 4002) { sessionStorage.setItem('ghsReplaced', 'true'); return halt('已在其他标签页连接', '同一会话已在其他标签页连接，本页已停止自动重连。', false, 'exited'); }
      if (e.detail.code === 1001) return halt('服务已停止', '服务连接已关闭，请在启动器确认状态后重新进入。', false, 'stopped');
      if (reconnectAttempts >= 12) return halt('无法恢复连接', '12次连接尝试均未成功，请检查启动器和网络后重新进入。');
      stream.disconnect(); clearTimeout(reconnectTimer);
      reconnectTimer = setTimeout(() => { if (!terminal) { reconnectAttempts++; stream.connect(); } }, 2000);
    });
    stream.addEventListener('webRtcFailed', () => { if (!terminal) progress(stage, '媒体连接失败', '暂未建立媒体连接，正在等待恢复；请确认客户端和服务端位于同一内网。', 'fault'); });
    stream.addEventListener('playStreamRejected', () => { const video = $('video-root').querySelector('video'); if (video) { video.muted = true; video.play().catch(autoplayBlocked); } });
    stream.addEventListener('statsReceived', e => {
      const stats = e.data.aggregatedStats; const v = stats.inboundVideoStats; const pair = stats.getActiveCandidatePair(); const video = $('video-root').querySelector('video');
      if (video) updateDimensions(video); metrics.fps = v.framesPerSecond || 0; metrics.bitrateMbps = (v.bitrate || 0) / 1000; metrics.rttMs = (pair?.currentRoundTripTime || 0) * 1000; metrics.decodedFrames = v.framesDecoded || 0;
      $('stat-fps').textContent = metrics.fps.toFixed(1) + ' fps'; $('stat-bitrate').textContent = metrics.bitrateMbps.toFixed(2) + ' Mbps'; $('stat-rtt').textContent = metrics.rttMs.toFixed(1) + ' ms'; $('stat-frames').textContent = String(metrics.decodedFrames);
      if (!firstFrame && video && metrics.decodedFrames > 0 && !video.paused) { if (video.requestVideoFrameCallback) video.requestVideoFrameCallback(() => markFrame(video)); else markFrame(video); }
    });
    // Register all status handlers before automatic connection, so fast local UE startup cannot race them.
    stream.connect();
  }
  start().catch(e => halt('连接失败', e.message));
})();
