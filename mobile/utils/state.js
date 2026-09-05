/* ═══════════════════════════════════════════════════════════════════════════
   Simple State Manager — pub/sub pattern, no dependencies
   ═══════════════════════════════════════════════════════════════════════════ */

/* ── Safe localStorage helpers ──────────────────────────────────────────── */
function _safeParse(value, fallback) {
  if (!value) return fallback;
  try { return JSON.parse(value) || fallback; }
  catch { return fallback; }
}
function _safeGet(key, fallback) {
  return _safeParse(localStorage.getItem(key), fallback);
}

const AppState = {
  _store: {
    activeTab: 'today',
    darkMode: localStorage.getItem('gospel_dark') !== 'false',  /* 默认深色，切换状态持久化 */
    fontSize: parseInt(localStorage.getItem('gospel_font')) || 20,
    recentReadings: _safeGet('gospel_recent', []),
    hymnFavorites: _safeGet('gospel_hf', []),
    hymnRecent: _safeGet('gospel_hr', []),
    hymnFilter: '全部',
    hymnSort: 'number',
    hymnDownloads: _safeGet('gospel_hd', []),   /* 离线下载完成曲目 id 列表 */
    playlists: _safeGet('gospel_pl', []),       /* [{id,name,cover,ids:[trackId]}] */
    eqPreset: localStorage.getItem('gospel_eqp') || 'flat',
    eqGains: _safeGet('gospel_eqg', [0,0,0,0,0]),
    audioQuality: localStorage.getItem('gospel_aq') || 'standard',  /* standard|hifi|saver */
    sermonFavorites: _safeGet('gospel_sf', []),
    sermonRecent: _safeGet('gospel_sr', []),
    sermonFilter: { q: '', category: '全部', series: '全部', sort: 'recent' },
    annotations: _safeGet('gospel_ann', []),  /* 말씀 하이라이트/북마크/메모 [{id,book,chapter,verse,color,note}] */
    // P4 #7: 认证令牌仅存于内存（不使用 localStorage）→ 防止 XSS 窃取。
    // 刷新/重启后令牌丢失 → 必须重新登录。따라서 isLoggedIn 은 localStorage 기반으로
    // "로그인 유지" 판정하면 안 되고, 항상 로그아웃 상태로 시작해야 UI 와 실제 인증이 일치한다.
    // (기존 `!!localStorage.getItem('gospel_sub_id')` 는 subId 잔존으로 "로그인 표시/실제 미인증" 불일치)
    isLoggedIn: false,
    user: _safeGet('gospel_user', null),
    token: null,
    subId: null,  // 구독자 id 도 토큰과 함께 메모리에서만 유지(재시작 후 게스트로 동작, guestId 가 익명 연속성 담당)
    // 未登录设备标识：使用设备级 UUID（localStorage 持久化），而非全局 'mobile_guest'。
    // 与 8501(Streamlit) 的 "anon_<uuid>" 同样用于 per-device 配额隔离 —
    // 若使用全局字符串，所有匿名移动端将共享 'sub:mobile_guest' 桶，
    // 一旦耗尽，所有匿名移动用户都会被 429(QUOTA_EXCEEDED) 拦截。
    guestId: (function () {
      let g = localStorage.getItem('gospel_guest_uuid');
      if (!g) {
        const rand = (window.crypto && crypto.randomUUID)
          ? crypto.randomUUID()
          : Date.now().toString(36) + Math.random().toString(36).slice(2);
        g = 'g_' + rand;
        localStorage.setItem('gospel_guest_uuid', g);
      }
      return g;
    })(),
    currentBook: 'psa',
    currentChapter: 23,
    bibleVersion: localStorage.getItem('gospel_bible_ver') || null,  /* 성경 버전: null=시스템 언어 따라감 / simpl/trad/kjv=명시 선택 */
    chatMessages: _safeGet('gospel_chat', []),  /* 대화 영속화(재시작 후에도 이어짐) */
    pendingQuestion: null,  /* 热门问答 클릭 → QA 탭 채팅에 질문 자동 전송 */
    targetLang: localStorage.getItem('gospel_lang') || 'auto',  /* 명시 토글은 유지, 기본은 'auto'(질문 언어 자동 감지) */
    uiLang: localStorage.getItem('gospel_uilang') || null,  /* UI 표시 언어: null=시스템 따름(ko/en/zh-CN/zh-TW) */
  },

  _listeners: {},

  get(key) {
    if (arguments.length === 0) return { ...this._store };
    return this._store[key];
  },

  set(key, value) {
    this._store[key] = value;
    // 대화 기록은 영속화(재시작 후에도 이어지도록)
    if (key === 'chatMessages') {
      try { localStorage.setItem('gospel_chat', JSON.stringify(value)); } catch (_) {}
    }
    // 성경 버전 선택 영속화 (null=시스템 언어 따라감 → 저장 항목 제거)
    if (key === 'bibleVersion') {
      try {
        if (value == null) localStorage.removeItem('gospel_bible_ver');
        else localStorage.setItem('gospel_bible_ver', value);
      } catch (_) {}
    }
    this._notify(key, value);
  },

  setMultiple(updates) {
    Object.assign(this._store, updates);
    for (const key of Object.keys(updates)) {
      this._notify(key, updates[key]);
    }
  },

  on(key, fn) {
    if (!this._listeners[key]) this._listeners[key] = [];
    this._listeners[key].push(fn);
    return () => {
      this._listeners[key] = this._listeners[key].filter(f => f !== fn);
    };
  },

  _notify(key, value) {
    (this._listeners[key] || []).forEach(fn => fn(value));
    (this._listeners['*'] || []).forEach(fn => fn(key, value));
  },

  /* ── Persisted getters/setters ────────────────────────────────────────── */
  toggleDark() {
    const next = !this._store.darkMode;
    this.set('darkMode', next);
    localStorage.setItem('gospel_dark', next);
    document.documentElement.classList.toggle('dark', next);
  },

  setFontSize(px) {
    this.set('fontSize', px);
    localStorage.setItem('gospel_font', px);
    document.documentElement.style.setProperty('--font-size', px + 'px');
  },

  addRecentReading(key) {
    const recent = [key, ...this._store.recentReadings.filter(k => k !== key)].slice(0, 10);
    this.set('recentReadings', recent);
    localStorage.setItem('gospel_recent', JSON.stringify(recent));
  },

  toggleHymnFav(id) {
    const fav = [...this._store.hymnFavorites];
    const idx = fav.indexOf(id);
    if (idx >= 0) fav.splice(idx, 1); else fav.push(id);
    this.set('hymnFavorites', fav);
    localStorage.setItem('gospel_hf', JSON.stringify(fav));
  },

  addHymnRecent(id) {
    const recent = [id, ...this._store.hymnRecent.filter(k => k !== id)].slice(0, 20);
    this.set('hymnRecent', recent);
    localStorage.setItem('gospel_hr', JSON.stringify(recent));
  },

  /* ── 下载（离线播放）──────────────────────────────────────── */
  isHymnDownloaded(id) {
    return this._store.hymnDownloads.indexOf(String(id)) >= 0;
  },
  setHymnDownloaded(id, on) {
    let dl = [...this._store.hymnDownloads];
    const i = dl.indexOf(String(id));
    if (on && i < 0) dl.push(String(id));
    if (!on && i >= 0) dl.splice(i, 1);
    this.set('hymnDownloads', dl);
    localStorage.setItem('gospel_hd', JSON.stringify(dl));
  },

  /* ── 播放列表（用户自建）──────────────────────────────────── */
  getPlaylists() { return [...this._store.playlists]; },
  getPlaylist(id) { return this._store.playlists.find(p => p.id === id) || null; },
  createPlaylist(name) {
    const id = 'pl_' + Date.now().toString(36) + Math.floor(Math.random() * 1e3).toString(36);
    const palette = ['emerald', 'brass', 'rust', 'ink', 'cream'];
    const pl = { id, name: name || '新建播放列表', cover: palette[this._store.playlists.length % palette.length], ids: [] };
    const list = [...this._store.playlists, pl];
    this.set('playlists', list);
    localStorage.setItem('gospel_pl', JSON.stringify(list));
    return pl;
  },
  renamePlaylist(id, name) {
    const list = this._store.playlists.map(p => p.id === id ? { ...p, name } : p);
    this.set('playlists', list);
    localStorage.setItem('gospel_pl', JSON.stringify(list));
  },
  deletePlaylist(id) {
    const list = this._store.playlists.filter(p => p.id !== id);
    this.set('playlists', list);
    localStorage.setItem('gospel_pl', JSON.stringify(list));
  },
  addToPlaylist(id, trackId) {
    const list = this._store.playlists.map(p => {
      if (p.id !== id) return p;
      if (p.ids.indexOf(String(trackId)) >= 0) return p;
      return { ...p, ids: [...p.ids, String(trackId)] };
    });
    this.set('playlists', list);
    localStorage.setItem('gospel_pl', JSON.stringify(list));
  },
  removeFromPlaylist(id, trackId) {
    const list = this._store.playlists.map(p =>
      p.id === id ? { ...p, ids: p.ids.filter(x => x !== String(trackId)) } : p);
    this.set('playlists', list);
    localStorage.setItem('gospel_pl', JSON.stringify(list));
  },

  /* ── Equalizer + audio quality ─────────────────────────────────────── */
  setEq(preset, gains) {
    if (preset) { this.set('eqPreset', preset); localStorage.setItem('gospel_eqp', preset); }
    if (gains) { this.set('eqGains', gains); localStorage.setItem('gospel_eqg', JSON.stringify(gains)); }
  },
  setAudioQuality(q) {
    this.set('audioQuality', q);
    localStorage.setItem('gospel_aq', q);
  },

  toggleSermonFav(id) {
    const fav = [...this._store.sermonFavorites];
    const idx = fav.indexOf(id);
    if (idx >= 0) fav.splice(idx, 1); else fav.push(id);
    this.set('sermonFavorites', fav);
    localStorage.setItem('gospel_sf', JSON.stringify(fav));
  },

  addSermonRecent(id) {
    const recent = [id, ...this._store.sermonRecent.filter(k => k !== id)].slice(0, 20);
    this.set('sermonRecent', recent);
    localStorage.setItem('gospel_sr', JSON.stringify(recent));
  },

  /* ── 말씀 하이라이트/북마크/메모 (로컬 영속 + 서버 동기화는 UI 레이어에서) ── */
  getVerseAnnotation(book, chapter, verse) {
    return this._store.annotations.find(a =>
      a.book === book && a.chapter === chapter && a.verse === verse) || null;
  },
  upsertAnnotation(book, chapter, verse, color, note) {
    const list = [...this._store.annotations];
    const idx = list.findIndex(a => a.book === book && a.chapter === chapter && a.verse === verse);
    const ann = {
      id: (idx >= 0 ? list[idx].id : 'a_' + Date.now().toString(36) + Math.floor(Math.random() * 1e4).toString(36)),
      book, chapter, verse,
      color: color ?? null,
      note: note ?? null,
    };
    if (idx >= 0) list[idx] = ann; else list.push(ann);
    this.set('annotations', list);
    localStorage.setItem('gospel_ann', JSON.stringify(list));
    return ann;
  },
  removeAnnotation(id) {
    const list = this._store.annotations.filter(a => a.id !== id);
    this.set('annotations', list);
    localStorage.setItem('gospel_ann', JSON.stringify(list));
  },

  login(user, token, subId) {
    if (token) {
      // P4 #7: 令牌仅存于内存（不使用 localStorage）
      this._store.token = token;
    }
    if (subId) {
      // 구독자 id 는 토큰과 수명을 같이 한다(메모리-only). 토큰이 재시작 시 소실되므로
      // subId 도 localStorage 에 영속화하지 않아야 재시작 후 "로그인 표시/미인증" 불일치가 없다.
      // (익명 연속성은 guestId 가 담당 — gospel_guest_uuid)
      this._store.subId = subId;
    }
    // 用户对象也持久化 → 刷新后“我的账户”界面不会崩溃（部分6 P6-3）
    if (user) {
      this._store.user = user;
      try { localStorage.setItem('gospel_user', JSON.stringify(user)); } catch (_) {}
    }
    this.setMultiple({ isLoggedIn: true, user: this._store.user });
  },

  logout() {
    this._store.token = null;
    this._store.subId = null;
    localStorage.removeItem('gospel_sub_id');
    localStorage.removeItem('gospel_user');
    this.setMultiple({ isLoggedIn: false, user: null, token: null, subId: null });
  },

  authHeaders() {
    const h = {};
    if (this._store.token) h['Authorization'] = 'Bearer ' + this._store.token;
    return h;
  },

  setTargetLang(code) {
    this.set('targetLang', code);
    localStorage.setItem('gospel_lang', code);
  },

  /* UI 표시 언어 설정 + 영속화 + 언어 변경 이벤트 발행(applyUiLangAll 가 구독) */
  setUiLang(code) {
    this.set('uiLang', code);
    if (code) localStorage.setItem('gospel_uilang', code); else localStorage.removeItem('gospel_uilang');
    if (typeof applyUiLangAll === 'function') applyUiLangAll();
  },
};

/* Initialize — apply saved dark mode preference (default: dark) */
if (AppState._store.darkMode) {
  document.documentElement.classList.add('dark');
}
// T-9: 字体大小在刷新后仍保留
document.documentElement.style.setProperty('--font-size', AppState._store.fontSize + 'px');
