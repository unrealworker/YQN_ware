// UI Motion navigation/tabs: one selected layer, compositor-only translation.
// Accepted business navigation owns selection; hover and focus never change it.
export function createNavigation(nav, { canAnimate, document, ResizeObserver }) {
  const pill = document.createElement('span');
  pill.className = 'motion-nav-highlight'; pill.setAttribute('aria-hidden', 'true');
  nav.prepend(pill); nav.classList.add('motion-navigation');
  let previous = null;
  const active = () => nav.querySelector('[aria-current="page"]');
  function move(immediate = false) {
    const button = active();
    if (!button) return;
    // DOMRects are transformed by UE DPI scaling; offsets are design pixels.
    const next = { x: button.offsetLeft, y: button.offsetTop, width: button.offsetWidth, height: button.offsetHeight };
    const same = previous && Object.keys(next).every(key => next[key] === previous[key]);
    if (same && !immediate) return;
    const snap = !previous || immediate || !canAnimate();
    pill.style.transition = snap ? 'none' : '';
    pill.style.width = `${next.width}px`; pill.style.height = `${next.height}px`;
    pill.style.transform = `translate3d(${next.x}px,${next.y}px,0)`;
    pill.style.opacity = '1'; previous = next;
    // Commit only initial/reduced-motion/layout alignment. Regular retargeting
    // leaves the current visual transform to CSS, without RAF work or a jump.
    if (snap) { void pill.offsetWidth; pill.style.transition = ''; }
  }
  function resize() {
    const button = active();
    if (!button || !previous) { move(true); return; }
    if (button.offsetLeft !== previous.x || button.offsetTop !== previous.y ||
        button.offsetWidth !== previous.width || button.offsetHeight !== previous.height) move(true);
  }
  const observer = new ResizeObserver(resize); observer.observe(nav);
  // Font/layout changes can resize a child without resizing the scroll rail.
  nav.querySelectorAll('[data-page]').forEach(button => observer.observe(button));
  document.addEventListener('twin-viewport-change', resize);
  return {
    update: () => move(), settle: () => move(true),
    dispose() { observer.disconnect(); document.removeEventListener('twin-viewport-change', resize); }
  };
}
