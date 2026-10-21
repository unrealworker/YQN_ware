'use strict';
const { webcrypto } = require('node:crypto');
const test = require('node:test'); const assert = require('node:assert/strict'); const fs = require('node:fs'); const path = require('node:path'); const vm = require('node:vm');
// Browser boundary harness: simulate the official library's public events, real page policy runs unchanged.
async function page(initialStorage = {}) {
  const elements = new Map(), store = new Map(Object.entries(initialStorage)), timers = new Map(); let timerId = 0, streaming, videoFrame, now = 100, created = 0;
  function events(object) { const listeners = new Map(); return Object.assign(object, { addEventListener(type, fn) { if (!listeners.has(type)) listeners.set(type, []); listeners.get(type).push(fn); }, fire(type, fields = {}) { const e = { type, button: 0, buttons: 1, clientX: 900, clientY: 550, shiftKey: false, defaultPrevented: false, stopped: false, preventDefault() { this.defaultPrevented = true; }, stopImmediatePropagation() { this.stopped = true; }, ...fields }; for (const fn of listeners.get(type) || []) { fn(e); if (e.stopped) break; } return e; } }); }
  const video = events({ videoWidth: 1920, videoHeight: 1080, readyState: 3, paused: false, dataset: {}, play: () => Promise.resolve(), getBoundingClientRect: () => ({ left: 100, top: 50, width: 1600, height: 1000 }), requestVideoFrameCallback(fn) { videoFrame = fn; } });
  const element = id => { if (!elements.has(id)) elements.set(id, events({ id, hidden: false, textContent: '', value: '', dataset: {}, style: {}, children: [], attributes: {}, classList: { add() {}, remove() {}, toggle() {} }, setAttribute(k, v) { this.attributes[k] = v; }, removeAttribute(k) { delete this.attributes[k]; }, append(...nodes) { this.children.push(...nodes); nodes.forEach(n => n.parentElement = this); }, replaceChildren(...nodes) { this.children = []; this.append(...nodes); }, contains(node) { return this === node || this.children.some(child => child.contains?.(node)); }, focus() { sandbox.document.activeElement = this; this.fire('focus'); }, blur() { sandbox.document.activeElement = null; this.fire('blur'); }, scrollIntoView() {}, querySelector: () => video })); return elements.get(id); };
  class Config { constructor(params) { this.settings = { ...params.initialSettings }; } setFlagEnabled(k, v) { this.settings[k] = v; } setNumericSetting(k, v) { this.settings[k] = v; } isFlagEnabled(k) { return this.settings[k]; } }
  class PixelStreaming {
    constructor(config) { streaming = this; this.config = config; this.events = new Map(); this.protocol = new Map(); this.responses = new Map(); this.ui = []; this.closed = 0; this.connected = 0; this.input = []; this.toStreamerHandlers = new Map(['MouseDown', 'MouseUp', 'MouseMove'].map(type => [type, values => this.input.push({ type, values: [...values] })])); this.webSocketController = { signallingProtocol: { addMessageHandler: (name, cb) => this.protocol.set(name, cb) }, onClose: { addEventListener: (_name, cb) => { this.onClose = cb; } } }; }
    addEventListener(name, cb) { this.events.set(name, cb); } connect() { this.connected++; } reconnect() { this.connected++; } disconnect() { this.closed++; } play() {}
    emitUIInteraction(payload) { this.ui.push(JSON.parse(JSON.stringify(payload))); return true; } addResponseEventListener(name, cb) { this.responses.set(name, cb); }
  }
  const sandbox = { window: events({ crypto: webcrypto, 'lib-pixelstreamingfrontend': { Config, PixelStreaming, Flags: { StartVideoMuted: 'StartVideoMuted', WaitForStreamer: 'WaitForStreamer', KeyboardInput: 'KeyboardInput' }, NumericParameters: { MaxReconnectAttempts: 'MaxReconnectAttempts' } } }), document: events({ body: element('body'), getElementById: element, querySelector: element, querySelectorAll: () => Array.from({length: 5}, (_, i) => element('stage-' + (i + 1))), createElement: tag => element(tag + ++created) }), sessionStorage: { getItem: k => store.get(k) || null, setItem: (k, v) => store.set(k, v), removeItem: k => store.delete(k) }, location: { protocol: 'http:', host: 'test:8080', reload() {} }, performance: { now: () => now }, MutationObserver: class { observe() {} }, setTimeout: (cb, ms) => { timers.set(++timerId, { cb, ms }); return timerId; }, clearTimeout: id => timers.delete(id), fetch: async () => ({ ok: true, status: 200, json: async () => ({ token: 'token123', mode: 'shared', fps: 60, minBitrateMbps: 8, maxBitrateMbps: 35 }) }), console };
  const searchPath = path.join(__dirname, '../player/scene-search.js'); if (fs.existsSync(searchPath)) vm.runInNewContext(fs.readFileSync(searchPath, 'utf8'), sandbox);
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../player/app.js'), 'utf8'), sandbox); await new Promise(r => setImmediate(r));
  return { elements, store, timers, window: sandbox.window, document: sandbox.document, video, get stream() { return streaming; }, frame() { videoFrame(); }, stats: () => sandbox.window.ghsStreamingStats, advance(ms) { now += ms; }, reply(fields = {}) { const state = { type: 'ghs.sceneSearch', clientId: streaming.ui.at(-1)?.clientId, requestId: streaming.ui.at(-1)?.requestId || 0, viewport: { width: 1920, height: 1080 }, rect: { x: 1100, y: 90, width: 420, height: 48 }, visible: true, open: false, query: '', results: [], total: 0, selectedIndex: 0, ...fields }; for (const cb of streaming.responses.values()) cb(JSON.stringify(state)); } };
}
test('page automatically connects muted and does not declare success before actual video frame', async () => {
  const p = await page(); assert.equal(p.stream.connected, 1); assert.equal(p.stream.config.settings.AutoPlayVideo, true); assert.equal(p.stream.config.settings.StartVideoMuted, true); assert.equal(p.stream.config.settings.MatchViewportRes, false);
  p.stream.events.get('webRtcConnected')(); assert.equal(p.stats().firstFrame, false); assert.equal(p.elements.get('loading')?.hidden || false, false);
  p.frame(); assert.equal(p.stats().firstFrame, true); assert.equal(p.elements.get('loading').hidden, true); assert.equal(p.stats().width, 1920);
});
test('session replacement stops reconnect policy and survives page reload without taking the session back', async () => {
  const p = await page(); p.stream.onClose({ detail: { code: 4002 } });
  for (const timer of [...p.timers.values()]) if (timer.ms < 120000) timer.cb();
  assert.equal(p.stream.connected, 1); assert.ok(p.stream.closed > 0); assert.equal(p.store.get('ghsReplaced'), 'true');
  const refreshed = await page(Object.fromEntries(p.store)); assert.equal(refreshed.stream, undefined); assert.match(refreshed.elements.get('stage-title').textContent, /其他标签页/);
});
test('evicted page refuses automatic re-entry and transport recovery timer cannot override eviction', async () => {
  const p = await page(); p.stream.onClose({ detail: { code: 1006 } }); p.stream.protocol.get('ghsEvicted')(JSON.stringify({ message: '被第四人替换' }));
  for (const timer of [...p.timers.values()]) timer.cb();
  assert.equal(p.stream.connected, 1); assert.equal(p.store.get('ghsEvicted'), 'true'); assert.equal(p.stats().state, 'evicted');
  const refreshed = await page(Object.fromEntries(p.store)); assert.equal(refreshed.stream, undefined);
});
test('repeated transport failures cannot postpone the initial first-frame deadline', async () => {
  const p = await page(); const originalDeadline = [...p.timers].find(([, timer]) => timer.ms === 120000)[0];
  for (let attempt = 0; attempt < 5; attempt++) p.stream.events.get('webRtcDisconnected')({ data: { eventString: 'network unavailable' } });
  assert.ok(p.timers.has(originalDeadline), 'failed attempts must retain the same absolute timeout');
  p.timers.get(originalDeadline).cb(); assert.match(p.elements.get('stage-title').textContent, /超时/); assert.equal(p.elements.get('retry').hidden, false);
});
test('shift-left drag pans with right-button messages in visible video coordinates and never emits a left click', async () => {
  const p = await page(); p.frame(); const root = p.elements.get('video-root');
  const down = root.fire('mousedown', { shiftKey: true }); assert.equal(down.defaultPrevented, true); assert.equal(down.stopped, true);
  const move = p.window.fire('mousemove', { clientX: 1060, clientY: 640, shiftKey: false }); assert.equal(move.stopped, true);
  p.window.fire('mouseup', { clientX: 1060, clientY: 640, buttons: 0 });
  assert.deepEqual(p.stream.input, [
    { type: 'MouseDown', values: [2, 32768, 32768] },
    { type: 'MouseMove', values: [39321, 39321, 6553, 6553] },
    { type: 'MouseUp', values: [2, 39321, 39321] }
  ]);
});
test('normal clicks and middle reset remain with Epic while native drag selection and context menu are suppressed', async () => {
  const p = await page(); p.frame(); const root = p.elements.get('video-root');
  for (const button of [0, 1, 2]) { assert.equal(root.fire('mousedown', { button }).stopped, false); assert.equal(p.window.fire('mouseup', { button, buttons: 0 }).stopped, false); }
  assert.equal(p.stream.input.length, 0);
  for (const type of ['contextmenu', 'dragstart', 'selectstart', 'auxclick']) assert.equal(root.fire(type).defaultPrevented, true, type);
});
test('pan is not started in the letterbox and a lost focus releases its remote right button once', async () => {
  const p = await page(); p.frame(); const root = p.elements.get('video-root');
  root.fire('mousedown', { shiftKey: true, clientY: 75 }); assert.equal(p.stream.input.length, 0);
  root.fire('mousedown', { shiftKey: true }); p.window.fire('blur'); p.window.fire('mouseup', { buttons: 0 });
  assert.deepEqual(p.stream.input.map(x => x.type), ['MouseDown', 'MouseUp']); assert.deepEqual(p.stream.input[1].values, [2, 32768, 32768]);
});
test('transport disconnect releases an alternative pan and stops capturing later pointer movement', async () => {
  const p = await page(); p.frame(); p.elements.get('video-root').fire('mousedown', { shiftKey: true });
  p.stream.events.get('webRtcDisconnected')({ data: { eventString: 'network unavailable' } });
  assert.deepEqual(p.stream.input.map(x => x.type), ['MouseDown', 'MouseUp']);
  assert.equal(p.window.fire('mousemove').stopped, false);
});
test('loading reports actual five-stage progress and elapsed seconds without a fabricated percentage', async () => {
  const p = await page(); p.stream.protocol.get('ghsAdmission')(JSON.stringify({ instanceId: 'UE-1' }));
  assert.equal(p.elements.get('stage-count').textContent, '阶段 1 / 5');
  p.advance(8100); [...p.timers.values()].find(t => t.ms === 1000).cb();
  assert.equal(p.elements.get('elapsed-time').textContent, '已等待 08 秒');
  p.stream.events.get('webRtcSdp')(); assert.equal(p.elements.get('stage-count').textContent, '阶段 3 / 5');
  p.frame(); assert.equal(p.elements.get('connection-progress').value, 5); assert.equal(p.elements.get('loading').hidden, true);
});
test('scene search uses real UE viewport coordinates inside the contained video, including letterboxing', async () => {
  const p = await page(); p.frame(); assert.equal(p.stream.ui.at(-1).action, 'ready'); p.reply();
  const overlay = p.elements.get('scene-search');
  assert.equal(overlay.hidden, false); assert.equal(parseFloat(overlay.style.left), 100 + 1100 * 1600 / 1920);
  assert.equal(parseFloat(overlay.style.top), 100 + 90 * 1600 / 1920); assert.equal(parseFloat(overlay.style.width), 350);
  p.reply({ visible: false }); assert.equal(overlay.hidden, true);
});
test('Chinese composition emits one complete query and Enter confirms a candidate before selecting an actual UE result', async () => {
  const p = await page(); p.frame(); p.reply(); const input = p.elements.get('scene-search-input'); input.focus();
  input.fire('compositionstart'); input.value = 'cha che'; input.fire('input', { isComposing: true });
  assert.equal(p.stream.ui.filter(m => m.action === 'query').length, 0);
  assert.equal(input.fire('keydown', { key: 'Enter', isComposing: true, keyCode: 229 }).defaultPrevented, false);
  input.value = '叉车'; input.fire('compositionend'); input.fire('input');
  assert.equal(p.stream.ui.filter(m => m.action === 'query').length, 1); assert.equal(p.stream.ui.at(-1).query, '叉车');
  p.reply({ open: true, query: '叉车', results: [{ id: 'actual-actor', title: 'FORK-07', type: '人工叉车', location: '地堆区 B', status: '待机' }], total: 1 });
  input.fire('keydown', { key: 'Enter' }); assert.equal(p.stream.ui.filter(m => m.action === 'select').length, 0);
  input.fire('keyup', { key: 'Enter' }); input.fire('keydown', { key: 'Enter' });
  assert.equal(p.stream.ui.at(-1).action, 'select'); assert.equal(p.stream.ui.at(-1).id, 'actual-actor'); assert.equal(p.stream.ui.at(-1).query, '叉车'); assert.equal(p.stream.input.length, 0);
});
test('search ignores stale and other-client results, supports keyboard selection, clear and Escape', async () => {
  const p = await page(); p.frame(); p.reply(); const input = p.elements.get('scene-search-input'); input.focus(); input.value = 'ag'; input.fire('input'); const old = p.stream.ui.at(-1).requestId;
  input.value = 'agv'; input.fire('input'); const current = p.stream.ui.at(-1).requestId;
  p.reply({ requestId: old, open: true, query: 'ag', results: [{ id: 'old', title: 'Old' }] }); assert.equal(input.value, 'agv');
  p.reply({ requestId: current, open: true, query: 'agv', results: [{ id: 'agv1', title: 'AGV-01' }, { id: 'agv2', title: 'AGV-02' }], total: 2 });
  input.fire('keydown', { key: 'ArrowDown' }); input.fire('keydown', { key: 'Enter' }); assert.equal(p.stream.ui.at(-1).id, 'agv2');
  p.elements.get('scene-search-clear').onclick(); assert.equal(input.value, ''); assert.equal(p.stream.ui.at(-1).query, '');
  input.fire('keydown', { key: 'Escape' }); assert.equal(p.stream.ui.at(-1).action, 'close'); assert.equal(p.elements.get('scene-search-results').hidden, true);
});
test('search locally consumes IME and pointer events and disconnect hides the overlay', async () => {
  const p = await page(); p.frame(); p.reply(); const input = p.elements.get('scene-search-input'); input.focus();
  assert.equal(p.stream.config.settings.KeyboardInput, false);
  assert.equal(input.fire('compositionend').stopped, true); assert.equal(input.fire('keydown', { key: 'a' }).stopped, true);
  assert.equal(p.elements.get('scene-search').fire('mousedown').stopped, true);
  p.stream.events.get('webRtcDisconnected')({ data: { eventString: 'offline' } }); assert.equal(p.elements.get('scene-search').hidden, true);
});
test('autoplay rejection leaves a manual play recovery action and hides it only when a frame is rendered', async () => {
  const p = await page(); p.video.play = () => Promise.reject(new Error('blocked'));
  p.stream.events.get('playStreamRejected')(); await new Promise(r => setImmediate(r));
  assert.equal(p.elements.get('allow-play').hidden, false); assert.equal(p.stats().firstFrame, false);
  p.video.play = () => Promise.resolve(); await p.elements.get('allow-play').onclick(); p.frame();
  assert.equal(p.elements.get('loading').hidden, true); assert.equal(p.stream.closed, 0);
});
test('query timeout keeps completed text, retries on demand and remote geometry cannot steal an active composition', async () => {
  const p = await page(); p.frame(); p.reply(); const input = p.elements.get('scene-search-input'); input.focus(); input.value = '货架'; input.fire('input');
  [...p.timers.values()].find(t => t.ms === 5000).cb(); assert.equal(input.value, '货架'); assert.equal(p.elements.get('scene-search-retry').hidden, false);
  p.elements.get('scene-search-retry').onclick(); assert.equal(p.stream.ui.at(-1).query, '货架');
  input.fire('compositionstart'); input.value = 'huo jia a'; p.reply({ requestId: 0, open: true, query: '别人', results: [{ id: 'remote', title: '其他设备' }], rect: { x: 1000, y: 90, width: 420, height: 48 } });
  assert.equal(input.value, 'huo jia a'); assert.equal(parseFloat(p.elements.get('scene-search').style.left), 100 + 1000 * 1600 / 1920);
});
test('server stop ends the frame deadline and search; manual re-entry clears eviction state', async () => {
  const p = await page(); p.frame(); p.reply(); p.stream.protocol.get('ghsShutdown')(JSON.stringify({ message: '启动器已停止服务' }));
  assert.equal(p.elements.get('scene-search').hidden, true); assert.equal(p.elements.get('loading').hidden, false); assert.match(p.elements.get('stage-title').textContent, /服务已停止/);
  assert.equal([...p.timers.values()].some(t => t.ms === 120000 || t.ms === 2000), false);
  const evicted = await page({ ghsEvicted: 'true', ghsSession: 'old', ghsReplaced: 'true' }); evicted.elements.get('retry').onclick(); assert.equal(evicted.store.size, 0);
});
test('shared-scene clients with identical request numbers isolate replies while unaddressed geometry follows the panel', async () => {
  const a = await page(), b = await page();
  for (const p of [a, b]) { p.frame(); p.reply(); p.elements.get('scene-search-input').focus(); }
  const aInput = a.elements.get('scene-search-input'), bInput = b.elements.get('scene-search-input');
  aInput.value = 'agv'; aInput.fire('input'); bInput.value = '叉车'; bInput.fire('input');
  const aReq = a.stream.ui.at(-1), bReq = b.stream.ui.at(-1); assert.equal(aReq.requestId, bReq.requestId); assert.notEqual(aReq.clientId, bReq.clientId);
  a.reply({ ...bReq, open: true, results: [{ id: 'fork', title: '叉车' }] }); assert.equal(aInput.value, 'agv');
  a.reply({ ...aReq, open: true, results: [{ id: 'agv1', title: 'AGV-01' }, { id: 'agv2', title: 'AGV-02' }], total: 2 }); aInput.fire('keydown', { key: 'ArrowDown' });
  a.reply({ clientId: undefined, requestId: undefined, query: '叉车', rect: { x: 1200, y: 90, width: 420, height: 48 } });
  assert.equal(aInput.value, 'agv'); assert.equal(parseFloat(a.elements.get('scene-search').style.left), 1100);
  aInput.fire('keydown', { key: 'Enter' }); assert.equal(a.stream.ui.at(-1).id, 'agv2'); assert.equal(a.stream.ui.at(-1).query, 'agv');
});
test('closing a shared-scene search preserves the caller query after another viewer searches', async () => {
  const a = await page(), b = await page();
  for (const p of [a, b]) { p.frame(); p.reply(); p.elements.get('scene-search-input').focus(); }
  const aInput = a.elements.get('scene-search-input'), bInput = b.elements.get('scene-search-input');
  aInput.value = 'AGV'; aInput.fire('input'); a.reply({ open: true, query: 'AGV', results: [{ id: 'agv1', title: 'AGV-01' }] });
  bInput.value = '叉车'; bInput.fire('input'); const bRequest = b.stream.ui.at(-1);
  a.reply({ ...bRequest, open: true, results: [{ id: 'fork', title: '叉车' }] });
  aInput.fire('keydown', { key: 'Escape' }); const close = a.stream.ui.at(-1);
  assert.equal(close.action, 'close'); assert.equal(close.query, 'AGV');
  // UE applies the caller query before echoing its addressed close acknowledgement.
  a.reply({ ...close, open: false }); assert.equal(aInput.value, 'AGV'); assert.equal(a.elements.get('scene-search-results').hidden, true);
  a.stream.events.get('dataChannelOpen')(); assert.equal(a.stream.ui.at(-1).action, 'ready'); assert.equal(a.stream.ui.at(-1).query, 'AGV');
});
test('search loads every result across multiple pages and selects a device beyond the first fifty', async () => {
  const p = await page(); p.frame(); p.reply(); const input = p.elements.get('scene-search-input'); input.focus(); input.value = 'AGV'; input.fire('input');
  const rows = (offset, count) => Array.from({ length: count }, (_, i) => ({ id: `agv${offset + i + 1}`, title: `AGV-${offset + i + 1}` }));
  assert.equal(p.stream.ui.at(-1).offset, 0);
  p.reply({ open: true, query: 'AGV', offset: 0, hasMore: true, total: 125, results: rows(0, 50) });
  const list = p.elements.get('scene-search-list'), more = p.elements.get('scene-search-more'), panel = p.elements.get('scene-search-results');
  assert.equal(list.children.length, 50); assert.equal(more.hidden, false); panel.scrollTop = 900;
  more.onclick(); assert.equal(p.stream.ui.at(-1).offset, 50); assert.equal(list.children.length, 50);
  p.reply({ open: true, query: 'AGV', offset: 50, hasMore: true, total: 125, selectedIndex: 50, results: rows(50, 50) });
  assert.equal(list.children.length, 100); assert.equal(panel.scrollTop, 900);
  more.onclick(); assert.equal(p.stream.ui.at(-1).offset, 100);
  p.reply({ open: true, query: 'AGV', offset: 100, hasMore: false, total: 125, selectedIndex: 100, results: rows(100, 25) });
  assert.equal(list.children.length, 125); assert.equal(more.hidden, true); assert.match(p.elements.get('scene-search-summary').textContent, /125/);
  list.children[124].onclick(); assert.equal(p.stream.ui.at(-1).id, 'agv125'); assert.equal(p.stream.ui.at(-1).query, 'AGV');
});
test('pagination timeout retries the same offset without deleting existing rows and ignores other clients', async () => {
  const p = await page(); p.frame(); p.reply(); const input = p.elements.get('scene-search-input'); input.focus(); input.value = '货架'; input.fire('input');
  p.reply({ open: true, query: '货架', offset: 0, hasMore: true, total: 3, results: [{ id: 'a', title: '货架 A' }, { id: 'b', title: '货架 B' }] });
  const list = p.elements.get('scene-search-list'); p.elements.get('scene-search-more').onclick();
  [...p.timers.values()].find(t => t.ms === 5000).cb(); assert.equal(list.children.length, 2); assert.equal(input.value, '货架');
  p.elements.get('scene-search-retry').onclick(); assert.equal(p.stream.ui.at(-1).offset, 2); assert.equal(list.children.length, 2);
  p.reply({ clientId: 'another-viewer', open: true, query: '货架', offset: 2, hasMore: false, total: 3, results: [{ id: 'foreign', title: '其他仓库' }] }); assert.equal(list.children.length, 2);
  p.reply({ open: true, query: '货架', offset: 2, hasMore: false, total: 3, results: [{ id: 'b', title: '货架 B' }, { id: 'c', title: '货架 C' }] });
  assert.equal(list.children.length, 3); assert.equal(p.elements.get('scene-search-more').hidden, true);
});
test('ArrowDown at the loaded-page boundary requests more and a new query rejects a stale appended page', async () => {
  const p = await page(); p.frame(); p.reply(); const input = p.elements.get('scene-search-input'); input.focus(); input.value = 'AGV'; input.fire('input');
  p.reply({ open: true, query: 'AGV', offset: 0, hasMore: true, total: 2, results: [{ id: 'a', title: 'AGV-01' }] });
  input.fire('keydown', { key: 'ArrowDown' }); assert.equal(p.stream.ui.at(-1).offset, 1); const stale = p.stream.ui.at(-1);
  input.value = '叉车'; input.fire('input'); assert.equal(p.stream.ui.at(-1).offset, 0);
  p.reply({ ...stale, open: true, offset: 1, hasMore: false, total: 2, results: [{ id: 'b', title: 'AGV-02' }] }); assert.equal(p.elements.get('scene-search-list').children.length, 0); assert.equal(input.value, '叉车');
  p.reply({ open: true, query: '叉车', offset: 0, hasMore: false, total: 1, results: [{ id: 'fork', title: '叉车' }] }); assert.equal(p.elements.get('scene-search-list').children.length, 1);
});
