/* DOM IME surface for the scene's actual search box. UE owns matching and focus. */
(() => {
  'use strict';
  window.GHSSceneSearch = { create({ stream, videoRoot, keyboardFlag, beforeFocus }) {
    const $ = id => document.getElementById(id);
    const overlay = $('scene-search'), input = $('scene-search-input'), panel = $('scene-search-results');
    const list = $('scene-search-list'), summary = $('scene-search-summary'), clear = $('scene-search-clear'), retry = $('scene-search-retry'), more = $('scene-search-more');
    let connected = false, geometry, open = false, composing = false, commitEnter = false, commitTimer, requestTimer;
    let items = [], active = 0, currentRequest = 0, lastQuery = null, lastData = '', pending = false, keyboardWasEnabled = true;
    let requestAction = '', pendingOffset = 0, hasMore = false, total = 0, jumpOnAppend = false;
    // UE responses may be broadcast. This random page nonce is not a session/control credential.
    const clientId = Array.from(window.crypto.getRandomValues(new Uint8Array(16)), value => value.toString(16).padStart(2, '0')).join('');
    let sequence = 0;
    const consume = event => event.stopImmediatePropagation();
    function send(action, fields = {}) {
      const requestId = ++sequence;
      currentRequest = requestId;
      requestAction = action;
      const sent = connected && stream.emitUIInteraction({ type: 'ghs.sceneSearch', clientId, action, requestId, ...fields });
      return sent !== false;
    }
    function position() {
      const video = videoRoot.querySelector('video');
      if (!connected || !geometry?.visible || !video?.videoWidth || !video.videoHeight) { overlay.hidden = true; return; }
      const { rect, viewport } = geometry;
      if (![rect?.x, rect?.y, rect?.width, rect?.height, viewport?.width, viewport?.height].every(Number.isFinite) || rect.width <= 0 || rect.height <= 0 || viewport.width <= 0 || viewport.height <= 0) { overlay.hidden = true; return; }
      const bounds = video.getBoundingClientRect(), scale = Math.min(bounds.width / video.videoWidth, bounds.height / video.videoHeight);
      const width = video.videoWidth * scale, height = video.videoHeight * scale;
      const left = bounds.left + (bounds.width - width) / 2, top = bounds.top + (bounds.height - height) / 2;
      const x = left + rect.x * width / viewport.width, y = top + rect.y * height / viewport.height;
      const boxWidth = Math.min(rect.width * width / viewport.width, left + width - x), boxHeight = rect.height * height / viewport.height;
      if (boxWidth <= 0 || x < left || y < top || y + boxHeight > top + height + 1) { overlay.hidden = true; return; }
      Object.assign(overlay.style, { left: `${x}px`, top: `${y}px`, width: `${boxWidth}px` });
      $('scene-search-field').style.height = `${boxHeight}px`;
      panel.style.maxHeight = `${Math.max(0, top + height - y - boxHeight - 12)}px`;
      overlay.hidden = false;
    }
    function render() {
      const scrollTop = panel.scrollTop;
      panel.hidden = !open;
      input.setAttribute('aria-expanded', String(open));
      clear.hidden = !input.value;
      more.hidden = !hasMore; more.disabled = pending; more.textContent = pending && pendingOffset > 0 ? '正在加载…' : `加载更多（已显示 ${items.length} / ${total}）`;
      list.replaceChildren();
      items.forEach((item, index) => {
        const row = document.createElement('button'); row.type = 'button'; row.id = `scene-search-option-${index}`; row.className = 'scene-search-option';
        row.setAttribute('role', 'option'); row.setAttribute('aria-selected', String(index === active)); row.tabIndex = -1;
        const main = document.createElement('span'), title = document.createElement('strong'), detail = document.createElement('span'), status = document.createElement('span');
        title.textContent = item.title || item.id; detail.textContent = [item.type, item.location].filter(Boolean).join(' · '); detail.className = 'scene-search-detail';
        status.textContent = item.status || ''; status.className = 'scene-search-status'; main.append(title, detail); row.append(main, status);
        row.onmousedown = event => event.preventDefault(); row.onclick = () => select(index); list.append(row);
      });
      if (items[active]) input.setAttribute('aria-activedescendant', `scene-search-option-${active}`); else input.removeAttribute('aria-activedescendant');
      panel.scrollTop = scrollTop;
    }
    function query(force = false, offset = 0, advanceSelection = false) {
      if (composing || !connected || (!force && input.value === lastQuery)) return;
      if (input.value !== lastQuery) offset = 0;
      lastQuery = input.value; pendingOffset = offset; jumpOnAppend = advanceSelection;
      if (offset === 0) { items = []; active = 0; hasMore = false; total = 0; panel.scrollTop = 0; }
      open = true; pending = true; retry.hidden = true;
      summary.textContent = offset > 0 ? `GHS · 已显示 ${items.length} / ${total}，正在加载更多…` : '正在查询 GHS 当前仓库…'; render(); clearTimeout(requestTimer);
      send('query', { query: input.value, offset });
      requestTimer = setTimeout(() => { if (!pending) return; pending = false; summary.textContent = offset > 0 ? '更多结果暂未响应，已保留当前列表。' : '查询暂未响应，已保留输入。'; retry.hidden = false; render(); }, 5000);
    }
    function loadMore(advanceSelection = false) {
      if (!hasMore || pending) return;
      query(true, items.length, advanceSelection);
    }
    function close(notify = true) {
      open = false; composing = false; pending = false; clearTimeout(requestTimer); render();
      if (notify && connected) send('close', { query: input.value });
      if (document.activeElement === input) input.blur();
    }
    function select(index) {
      if (composing || pending || !items[index]) return;
      send('select', { id: items[index].id, query: input.value }); close(false); videoRoot.focus({ preventScroll: true });
    }
    function receive(raw) {
      let state; try { state = typeof raw === 'string' ? JSON.parse(raw) : raw; } catch { return; }
      if (state?.type !== 'ghs.sceneSearch') return;
      geometry = state; position();
      if (!state.visible) { close(false); return; }
      // Unaddressed geometry is shared; search data is strictly addressed to this page.
      if (state.clientId !== clientId || state.requestId !== currentRequest) return;
      if (composing || (pending && state.query !== input.value)) return;
      const offset = Number.isInteger(state.offset) && state.offset >= 0 ? state.offset : 0;
      if (requestAction === 'query' && offset !== pendingOffset) return;
      const data = JSON.stringify([state.requestId, state.open, state.query, state.results, state.total, state.selectedIndex, offset, state.hasMore]);
      if (data === lastData) return;
      lastData = data;
      pending = false; clearTimeout(requestTimer); retry.hidden = true;
      open = Boolean(state.open); input.value = typeof state.query === 'string' ? state.query : ''; lastQuery = input.value;
      const pageItems = Array.isArray(state.results) ? state.results.filter(item => item && typeof item.id === 'string') : [];
      const previousCount = items.length;
      if (offset === 0) items = [];
      const existingIds = new Set(items.map(item => item.id));
      for (const item of pageItems) if (!existingIds.has(item.id)) { items.push(item); existingIds.add(item.id); }
      total = Number.isFinite(state.total) && state.total >= 0 ? state.total : items.length;
      hasMore = state.hasMore === true && items.length < total;
      if (offset === 0) active = Math.max(0, Math.min(items.length - 1, Number(state.selectedIndex) || 0));
      else if (jumpOnAppend && items.length > previousCount) active = previousCount;
      summary.textContent = items.length ? `GHS · 匹配设备（${total}）· 已显示 ${items.length}` : input.value ? `GHS 中未找到“${input.value}”，试试设备类型、编号或物料名称。` : '搜索当前仓库的设备名称、类型、编号、货位或物料';
      render();
      if (jumpOnAppend) list.children[active]?.scrollIntoView({ block: 'nearest' });
      jumpOnAppend = false;
      if (open && document.activeElement !== input) input.focus({ preventScroll: true });
    }
    input.addEventListener('focus', () => {
      beforeFocus(); keyboardWasEnabled = stream.config.isFlagEnabled(keyboardFlag); stream.config.setFlagEnabled(keyboardFlag, false);
      if (!open) { open = true; render(); send('open', { query: input.value }); }
    });
    input.addEventListener('blur', () => stream.config.setFlagEnabled(keyboardFlag, keyboardWasEnabled));
    input.addEventListener('compositionstart', event => { consume(event); composing = true; commitEnter = false; clearTimeout(commitTimer); });
    input.addEventListener('compositionupdate', consume);
    input.addEventListener('compositionend', event => {
      consume(event); composing = false; commitEnter = true; query();
      // Some engines dispatch compositionend before the committing Enter keydown.
      clearTimeout(commitTimer); commitTimer = setTimeout(() => { commitEnter = false; }, 80);
    });
    input.addEventListener('input', event => { consume(event); clear.hidden = !input.value; if (!event.isComposing) query(); });
    input.addEventListener('keydown', event => {
      consume(event);
      if (composing || event.isComposing || event.keyCode === 229) return;
      if (event.key === 'Enter') { event.preventDefault(); if (!commitEnter) select(active); }
      else if (event.key === 'Escape') { event.preventDefault(); close(); videoRoot.focus({ preventScroll: true }); }
      else if ((event.key === 'ArrowDown' || event.key === 'ArrowUp') && items.length) {
        event.preventDefault();
        if (event.key === 'ArrowDown' && active === items.length - 1 && hasMore) { loadMore(true); return; }
        active = (active + (event.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length; render(); list.children[active]?.scrollIntoView({ block: 'nearest' });
      }
    });
    input.addEventListener('keyup', event => { consume(event); if (event.key === 'Enter') commitEnter = false; });
    input.addEventListener('keypress', consume);
    // The overlay is a sibling of Epic's video element. Its gestures never reach scene input.
    for (const type of ['mousedown', 'mouseup', 'mousemove', 'click', 'dblclick', 'pointerdown', 'pointerup', 'pointermove', 'touchstart', 'touchmove', 'touchend', 'wheel', 'contextmenu']) overlay.addEventListener(type, consume);
    clear.onmousedown = event => event.preventDefault(); clear.onclick = () => { input.value = ''; composing = false; query(true); if (document.activeElement !== input) input.focus({ preventScroll: true }); };
    retry.onmousedown = event => event.preventDefault(); retry.onclick = () => query(true, pendingOffset, jumpOnAppend);
    more.onmousedown = event => event.preventDefault(); more.onclick = () => loadMore();
    document.addEventListener('mousedown', event => { if (open && !overlay.contains(event.target)) close(); }, { capture: true });
    window.addEventListener('resize', position);
    stream.addResponseEventListener('ghs.sceneSearch', receive);
    overlay.hidden = true; retry.hidden = true; render();
    return {
      ready() { connected = true; position(); send('ready', { query: input.value }); },
      position,
      suspend() { connected = false; overlay.hidden = true; close(false); clearTimeout(commitTimer); }
    };
  } };
})();
