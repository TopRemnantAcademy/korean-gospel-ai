/* ═══════════════════════════════════════════════════════════════════════════
   Components — reusable UI building blocks
   ═══════════════════════════════════════════════════════════════════════════ */

/* ── Tab Bar ───────────────────────────────────────────────────────────── */
function renderTabBar(tabs) {
  const nav = h('nav', { className: 'tab-bar' });
  tabs.forEach(tab => {
    const item = h('button', {
      className: 'tab-item' + (AppState.get('activeTab') === tab.id ? ' active' : ''),
      'data-tab': tab.id,
      onClick: () => {
        AppState.set('activeTab', tab.id);
        // renderScreen 由 app.js 的 AppState 监听器处理——移除重复调用
      }
    },
      h('span', { className: 'tab-icon' }, svgIcon(tab.icon, 22)),
      h('span', { className: 'tab-label', textContent: uiT(tab.labelKey) }),
    );
    nav.append(item);
  });
  return nav;
}

const TABS = [
  { id: 'bible', icon: 'bible', labelKey: 'tab.bible' },
  { id: 'hymns', icon: 'music', labelKey: 'tab.hymns' },
  { id: 'today', icon: 'calendar', labelKey: 'tab.today' },
  { id: 'word', icon: 'scroll', labelKey: 'tab.word' },
  { id: 'mypage', icon: 'settings', labelKey: 'tab.settings' },
];

/* ── Bible Verse Rendering ─────────────────────────────────────────────── */
function renderVerse(verse, selected = false, ann = null, onTap = null) {
  const cls = 'verse-line' + (selected ? ' verse-selected' : '') +
    (ann && ann.color ? ' hl-' + ann.color : '') +
    (ann && ann.note ? ' has-note' : '');
  const el = h('p', { className: cls },
    h('sup', { className: 'verse-num', textContent: verse.v }),
    verse.t
  );
  if (ann && ann.note) {
    el.append(h('span', { className: 'verse-note-dot', title: ann.note, textContent: '📝' }));
  }
  if (onTap) el.addEventListener('click', () => onTap(verse.v, verse.t, ann));
  return el;
}

function renderPassage(passage, lo = null, hi = null, opts = null) {
  const container = h('div', { className: 'passage' });
  const book = opts && opts.book;
  const chapter = opts && opts.chapter;
  const onVerseTap = opts && opts.onVerseTap;
  (passage.verses || []).forEach(v => {
    const sel = lo != null && hi != null && v.v >= lo && v.v <= hi;
    const ann = (book != null && chapter != null && onVerseTap)
      ? AppState.getVerseAnnotation(book, chapter, v.v)
      : null;
    container.append(renderVerse(v, sel, ann, onVerseTap));
  });
  return container;
}

/* ── Card ──────────────────────────────────────────────────────────────── */
function Card({ title, subtitle, thumbnail, body, footer, onClick } = {}) {
  const card = h('article', { className: 'card' });
  if (onClick) card.addEventListener('click', onClick);
  if (thumbnail) card.append(h('span', { className: 'card-thumb', textContent: thumbnail }));
  const content = h('div', { className: 'card-body' });
  if (title) content.append(h('h3', { className: 'card-title', textContent: title }));
  if (subtitle) content.append(h('p', { className: 'card-subtitle', textContent: subtitle }));
  if (body) content.append(h('p', { className: 'card-text', textContent: body }));
  card.append(content);
  if (footer) card.append(h('div', { className: 'card-footer' }, footer));
  return card;
}

/* ── Search Bar ────────────────────────────────────────────────────────── */
function SearchBar({ placeholder, onInput, compact }) {
  let _timer;
  const input = h('input', {
    type: 'search', placeholder: placeholder || '搜索...',
    onInput: e => {
      // U-3: 200ms 防抖——避免每输入一字就整体重渲染（输入法组合中也安全）
      clearTimeout(_timer);
      _timer = setTimeout(() => onInput && onInput(e.target.value), 200);
    },
    // 收缩态：点击/聚焦时展开，失焦且为空时收回
    onFocus: () => bar.classList.add('expanded'),
    onBlur: (e) => { if (!e.target.value) bar.classList.remove('expanded'); },
  });
  const bar = h('div', { className: 'search-bar' + (compact ? ' compact' : '') },
    h('span', { className: 'search-icon', textContent: '🔍' }),
    input,
  );
  bar.addEventListener('click', () => input.focus());
  return bar;
}

/* ── SVG Icons (no emoji) ─────────────────────────────────────────────── */
const _ICONS = {
  settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>',
  spark: '<path d="M13 2 3 14h9l-1 8 10-12h-9l1-8z"/>',
  bible: '<path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>',
  music: '<path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>',
  sermon: '<path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><path d="M12 19v4"/>',
  meditation: '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>',
  flame: '<path d="M12 2c1 3 4 4.5 4 8a4 4 0 0 1-8 0c0-1 .4-2 1-2.5C7 9 5 11 5 14a7 7 0 0 0 14 0c0-5-4.5-9-7-12z"/>',
  chat: '<path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/>',
  arrow: '<path d="M5 12h14"/><path d="M13 6l6 6-6 6"/>',
  send: '<path d="M22 2 11 13"/><path d="M22 2 15 22l-4-9-9-4 20-7z"/>',
  grid: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/>',
  volume: '<path d="M11 5 6 9H2v6h4l5 4V5z"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 4-6 8-6s8 2 8 6"/>',
  calendar: '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4"/><path d="M8 2v4"/><path d="M3 10h18"/><circle cx="12" cy="15" r="1.4"/>',
  scroll: '<path d="M5 3h11a2 2 0 0 1 2 2v12a2 2 0 0 0 2 2H7a2 2 0 0 1-2-2V3z"/><path d="M5 3a2 2 0 0 0-2 2v12a2 2 0 0 1 2 2"/><path d="M9 7h6M9 11h6"/>',
};

function svgIcon(name, size = 22) {
  const wrap = document.createElement('div');
  wrap.innerHTML =
    `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" ` +
    `stroke="currentColor" stroke-width="1.8" stroke-linecap="round" ` +
    `stroke-linejoin="round" class="icon-svg" aria-hidden="true">${_ICONS[name] || ''}</svg>`;
  return wrap.firstElementChild;
}
