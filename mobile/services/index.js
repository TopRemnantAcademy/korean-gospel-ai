/* ═══════════════════════════════════════════════════════════════
   Services — 后端 API 对接（失败时回退本地 JSON）
   ═══════════════════════════════════════════════════════════════ */

/* API 基础地址 — 由 index.html 通过 window.GOSPEL_API_BASE 设置（默认 localhost:8000） */
const API_BASE = window.GOSPEL_API_BASE || 'http://127.0.0.1:8000';

async function apiGet(path) {
  const url = path.startsWith('http') ? path : API_BASE + path;
  const res = await fetch(url, { headers: { 'Accept': 'application/json' } });
  if (!res.ok) throw new Error('HTTP ' + res.status);
  return res.json();
}

/* ── PortOne 결제 (V2 pre-register 흐름) ─────────────────────────────────
   플랜 조회 → prepare(paymentId + 채널키 발급) →
   PortOne.requestPayment({ paymentId, channelKey, ... }) → complete(승급).
   결제는 로그인된 구독자만 가능(AppState.authHeaders 사용, Bearer 토큰). */
const PaymentService = {
  async getPlans() {
    return apiGet('/api/payment/plans');
  },
  async prepare(planId) {
    const res = await fetch(API_BASE + '/api/payment/prepare', {
      method: 'POST',
      headers: Object.assign({ 'Content-Type': 'application/json' }, AppState.authHeaders()),
      body: JSON.stringify({ plan_id: planId }),
    });
    if (!res.ok) {
      const d = await res.json().catch(() => ({}));
      throw new Error(d.detail || ('HTTP ' + res.status));
    }
    return res.json();
  },
  async complete(paymentId) {
    const res = await fetch(API_BASE + '/api/payment/complete', {
      method: 'POST',
      headers: Object.assign({ 'Content-Type': 'application/json' }, AppState.authHeaders()),
      body: JSON.stringify({ payment_id: paymentId }),
    });
    if (!res.ok) {
      const d = await res.json().catch(() => ({}));
      throw new Error(d.detail || ('HTTP ' + res.status));
    }
    return res.json();
  },
};

/* ── App 버전 게이트 (2026-08-01) ───────────────────────────────────────────
   로컬 version.json(versionCode) 을 서버 /mobile/app-config 와 비교.
   - local < min → force_update (강제 업데이트 차단)
   - local < latest → 권장 업데이트 안내
   네트워크 실패 시 게이트를 통과(오프라인에서 앱 못 쓰는 상황 방지). */
const VersionService = {
  async getLocalVersion() {
    try {
      const v = await fetch('./version.json', { cache: 'no-cache' }).then(r => r.json());
      return { versionName: v.versionName || '0.0.0', versionCode: Number(v.versionCode) || 0 };
    } catch (_) {
      return { versionName: '0.0.0', versionCode: 0 };
    }
  },
  async check() {
    const local = await this.getLocalVersion();
    let cfg;
    try {
      cfg = await apiGet('/mobile/app-config');
    } catch (_) {
      // 서버 조회 실패 → 게이트 통과(강제 업데이트 안 함)
      return { ...local, ok: true, forceUpdate: false, latestAvailable: false, updateUrl: '', serverReachable: false };
    }
    const minCode = Number(cfg.min_version_code) || 0;
    const latestCode = Number(cfg.latest_version_code) || 0;
    const forceUpdate = local.versionCode > 0 && local.versionCode < minCode;
    const latestAvailable = !forceUpdate && local.versionCode > 0 && local.versionCode < latestCode;
    return {
      ...local,
      ok: true,
      forceUpdate,
      latestAvailable,
      minVersionCode: minCode,
      latestVersionCode: latestCode,
      latestVersionName: cfg.latest_version_name || '',
      updateUrl: cfg.update_url || '',
      serverReachable: true,
    };
  },
};
/* 관리자 업로드 → 서버가 구독 기기에 푸시 → 탭 열면 최신 카탈로그 풀.
   구독은 Bearer 없이 sub_id(로그인 또는 게스트)로 등록 (백엔드가 게스트도 수용). */
const PushService = {
  _reg: null,
  async setup() {
    if (!('serviceWorker' in navigator)) return;
    try {
      this._reg = await navigator.serviceWorker.register('./sw.js');
    } catch (_) { return; }

    // SW → 앱 메시지 수신(알림 탭 이동)
    navigator.serviceWorker.addEventListener('message', (e) => {
      if (e.data && e.data.type === 'new_media') {
        MediaService.invalidate();
        AppState.set('activeTab', e.data.tab || 'today');
        renderScreen(e.data.tab || 'today');
      }
    });

    if (!('PushManager' in window) || !('Notification' in window)) return;
    let perm = Notification.permission;
    if (perm === 'default') {
      try { perm = await Notification.requestPermission(); } catch (_) {}
    }
    if (perm !== 'granted') return;
    try {
      let sub = await this._reg.pushManager.getSubscription();
      if (!sub) {
        const key = await this._vapidKey();
        if (!key) return;
        sub = await this._reg.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: key,
        });
      }
      if (sub) await this._upload(sub);
    } catch (_) {}
  },
  async _vapidKey() {
    try {
    const d = await apiGet('/mobile/push/vapid');
    // 백엔드 응답 필드명은 public_key 임 (vapidPublicKey 아님 — 구독 누락 버그)
    const b64 = (d && d.public_key) || '';
      return b64 ? this._b64ToUint8(b64) : null;
    } catch (_) { return null; }
  },
  async _upload(sub) {
    const subId = AppState.get('subId') || AppState.get('guestId');
    if (!subId) return;
    try {
      await fetch(API_BASE + '/mobile/push/subscribe', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token: JSON.stringify(sub), platform: (typeof Platform !== 'undefined' && Platform.getPlatform) ? Platform.getPlatform() : 'web', sub_id: subId }),
      });
    } catch (_) {}
  },
  _b64ToUint8(b64) {
    const pad = '='.repeat((4 - (b64.length % 4)) % 4);
    const s = atob((b64 + pad).replace(/-/g, '+').replace(/_/g, '/'));
    const u = new Uint8Array(s.length);
    for (let i = 0; i < s.length; i++) u[i] = s.charCodeAt(i);
    return u;
  },
};

/* ── Bible Service ──────────────────────────────────────────────── */
// 성경 버전 정의: simpl(간체, 기본) / trad(번체 화합본)
const BIBLE_VERSIONS = [
  { id: 'simpl', label: '简体中文和合本', dir: 'bible' },
  { id: 'trad', label: '繁體中文和合本', dir: 'bible_trad' },
  { id: 'kjv', label: 'King James Version', dir: 'bible_kjv' },
];

const BibleService = {
  _meta: null,      // BB-5: 缓存分卷元数据，用于 书名→卷序号(1-based) 映射
  _bookCache: {},  // BB-5: 按卷序号缓存分卷文件，避免每次回退都重新下载整本 4.7MB
  // key = "version:idx" — 不同版本的同名卷不会互相污染缓存

  // 返回本地实际打包了的版本列表 [{id, label, dir}]，供 UI 切换用
  async getVersions() {
    const available = [];
    for (const v of BIBLE_VERSIONS) {
      try {
        const base = new URL(`./data/${v.dir}/`, location.href).href;
        const r = await fetch(base + 'bible_meta.json');
        if (r.ok) available.push(v);
      } catch (_) { /* skip */ }
    }
    if (!available.length) available.push(BIBLE_VERSIONS[0]);
    return available;
  },

  async _localMeta(version = 'simpl') {
    const v = BIBLE_VERSIONS.find(x => x.id === version) || BIBLE_VERSIONS[0];
    const key = v.id;
    if (this._meta && this._meta._version === key) return this._meta;
    try {
      const base = new URL(`./data/${v.dir}/`, location.href).href;  // R4: Capacitor origin 안전용 절대경로
      const d = await fetch(base + 'bible_meta.json').then(r => r.json());
      d._version = key;
      this._meta = d;
      return d;
    } catch (_) { return null; }
  },

  _dirFor(version = 'simpl') {
    const v = BIBLE_VERSIONS.find(x => x.id === version) || BIBLE_VERSIONS[0];
    return v.dir;
  },

  // LOCAL-FIRST: 圣经文本是静态的，本地分卷即权威来源 → 优先本地，跳过 /mobile/bible/books 网络请求；
  // 仅在本地缺失(尚未打包)时才回退到服务器。
  async getBooks(version = 'simpl') {
    try {
      const data = await this._localMeta(version);
      if (data && Array.isArray(data.bible_books) && data.bible_books.length) {
        return data.bible_books.map(b => ({
          id: b.id, name: b.name, chapters: b.chapters, testament: b.testament || 'old',
        }));
      }
    } catch (_) {}
    // 回退：服务器
    try {
      const data = await apiGet(`/mobile/bible/books?version=${encodeURIComponent(version)}`);
      if (data && Array.isArray(data.books)) {
        return data.books.map(b => ({
          id: b.id, name: b.name, chapters: b.total_chapters, testament: b.testament || 'old',
        }));
      }
    } catch (e) { /* 后端未连接 */ }
    return [];
  },

  // verseStart/verseEnd: 节范围选择（null 表示整章）
  // LOCAL-FIRST: 先读本地分卷文件，跳过 /mobile/bible/read 网络请求；本地缺失才回退服务器。
  async getPassage(bookId, chapter, verseStart = null, verseEnd = null, version = 'simpl') {
    try {
      const meta = await this._localMeta(version);
      if (meta) {
        const idx = (meta.bible_books || []).findIndex(b => b.id === bookId || b.name === bookId) + 1;
        if (idx > 0) {
          const base = new URL(`./data/${this._dirFor(version)}/`, location.href).href;  // R4: 与 _localMeta 一致，避免 base 未定义
          const cacheKey = `${version}:${idx}`;
          let bookData = this._bookCache[cacheKey];
          if (!bookData) {
            const r = await fetch(base + `${idx}.json`);
            if (r.ok) { bookData = await r.json(); this._bookCache[cacheKey] = bookData; }
          }
          if (bookData) {
            let verses = bookData.chapters[String(chapter)] || bookData.chapters[chapter];
            if (verses) {
              if (verseStart != null || verseEnd != null) {
                const lo = verseStart != null ? verseStart : (verses[0] ? verses[0].v : 1);
                const hi = verseEnd != null ? verseEnd : (verses[verses.length - 1] ? verses[verses.length - 1].v : 1);
                verses = verses.filter(v => v.v >= lo && v.v <= hi);
              }
              return { verses, reference: `${bookData.book} 第${chapter}章`, verseCount: verses.length };
            }
          }
        }
      }
    } catch (_) {}
    // 回退：服务器
    try {
      let path = `/mobile/bible/read?book=${encodeURIComponent(bookId)}&chapter=${chapter}&version=${encodeURIComponent(version)}`;
      if (verseStart != null) path += `&verse_start=${verseStart}`;
      if (verseEnd != null) path += `&verse_end=${verseEnd}`;
      const data = await apiGet(path);
      if (data && data.available && Array.isArray(data.verses)) {
        return { verses: data.verses, reference: data.reference, verseCount: data.verse_count };
      }
    } catch (e) { /* 回退 */ }
    return null;
  },

  // LOCAL-FULL-TEXT-SEARCH: 在手机本地对 66 卷圣经做全文检索，无需服务器。
  // 完全替代 /mobile/bible/search(RAG 管线：embedder + Qdrant + reranker)，服务器零负担。
  // 返回 [{ bookId, bookName, chapter, verse, text, reference }]
  async searchLocal(query, limit = 60, version = 'simpl') {
    const q = (query || '').trim();
    if (!q) return [];
    const meta = await this._localMeta(version);
    if (!meta || !Array.isArray(meta.bible_books)) return [];
    const books = meta.bible_books;
    const lower = q.toLowerCase();
    const results = [];
    for (let i = 0; i < books.length; i++) {
      const b = books[i];
      const idx = i + 1;
      const cacheKey = `${version}:${idx}`;
      let bookData = this._bookCache[cacheKey];
      if (!bookData) {
        try {
          // R4: Capacitor origin 안전용 절대경로 (상대경로는 origin 맥락에 따라 실패 가능)
          const base = new URL(`./data/${this._dirFor(version)}/`, location.href).href;
          const r = await fetch(base + `${idx}.json`);
          if (!r.ok) continue;
          bookData = await r.json();
          this._bookCache[cacheKey] = bookData;
        } catch (_) { continue; }
      }
      const chaptersObj = bookData.chapters || {};
      for (const ch of Object.keys(chaptersObj)) {
        const verses = chaptersObj[ch] || [];
        for (const v of verses) {
          const t = v.t || '';
          if (t.toLowerCase().includes(lower)) {
            results.push({
              bookId: b.id, bookName: b.name,
              chapter: parseInt(ch, 10), verse: v.v,
              text: t, reference: `${b.name} ${ch}:${v.v}`,
            });
            if (results.length >= limit) return results;
          }
        }
      }
    }
    return results;
  }
};

/* ── Media Service（诗歌/讲道音频）────────────────────────────────── */
// T-2: 全字段映射 — 后端模式下避免讲道标签页核心字段缺失
function mapMedia(items, kind = 'worship') {
  return (items || []).map(m => ({
    id: m.asset_id,
    title: m.title,
    subtitle: m.artist || m.preacher || '',
    preacher: m.preacher || '',
    date: m.date || '',
    scripture: m.scripture || '',
    scripture_refs: m.scripture_refs || [],
    series: m.series || null,
    stream_url: m.stream_url ? API_BASE + m.stream_url : null,
    category: m.category || (kind === 'sermon' ? '讲道' : '诗歌'),
    lyrics: m.lyrics || null,
    duration: m.duration || (kind === 'sermon' ? 1200 : 20),
    views: m.views || 0,
    featured: !!m.featured,
    cover: m.cover || 'emerald',
    summary: m.summary || '',
    transcript: m.transcript || null,
    number: kind === 'sermon' ? '✚' : (m.number || m.id),
    kind,
  }));
}

const MediaService = {
  // 저비용 버전 캐시: /mobile/media/version 이 안 바뀌면 재다운로드 생략
  _cache: { version: null, byCat: {} },
  invalidate() { this._cache = { version: null, byCat: {} }; },
  async version() {
    try { return await apiGet('/mobile/media/version'); } catch (_) { return null; }
  },
  async list(category, kind = 'worship') {
    try {
      const v = await this.version();
      if (v && this._cache.version === v.version && this._cache.byCat[category]) {
        return this._cache.byCat[category];
      }
      const data = await apiGet(`/mobile/media?category=${category}`);
      const items = (data && Array.isArray(data.items)) ? mapMedia(data.items, kind) : [];
      if (v) this._cache.version = v.version;
      this._cache.byCat[category] = items;
      return items;
    } catch (e) { /* 回退 */ }
    return [];
  }
};

const WorshipService = {
  async getAll() {
    const items = await MediaService.list('worship');
    if (items.length) return items;
    // 回退：本地诗歌 JSON（无音频）
    try {
      const data = await fetch('./data/hymns.json').then(r => r.json());
      return (data.hymns || []).map(h => ({
        id: String(h.id), number: parseInt(h.number || h.id) || 0, title: h.title, subtitle: h.subtitle,
        scripture_refs: h.scripture_refs || [], stream_url: h.stream_url || null,
        category: h.category || '诗歌', lyrics: h.lyrics, favorite: !!h.favorite,
        duration: h.duration || (h.lyrics ? h.lyrics.length * 4 : 20),
      }));
    } catch (_) { return []; }
  }
};

const SermonService = {
  async getAll() {
    const items = await MediaService.list('sermon');
    if (items.length) return items;
    // 回退：本地讲道 JSON（无音频）
    try {
      const data = await fetch('./data/sermons.json').then(r => r.json());
      return (data.sermons || []).map(s => ({
        id: String(s.id),
        title: s.title,
        subtitle: s.preacher || '',
        preacher: s.preacher || '',
        date: s.date || '',
        scripture: s.scripture || '',
        scripture_refs: s.scripture ? [s.scripture] : [],
        series: s.series || null,
        category: s.category || '讲道',
        summary: s.summary || '',
        transcript: s.transcript || null,
        stream_url: s.stream_url || null,
        duration: s.duration || 1200,
        views: s.views || 0,
        featured: !!s.featured,
        cover: s.cover || 'emerald',
        number: '✚',
        kind: 'sermon',
      }));
    } catch (_) { return []; }
  },
  // featured(英雄卡) 1篇 + 精选(点击量靠前) 展示用
  async getFeatured() {
    const all = await this.getAll();
    return all.find(s => s.featured) || all[0] || null;
  },
  async getHighlights(n = 8) {
    const all = await this.getAll();
    return [...all].sort((a, b) => (b.views || 0) - (a.views || 0)).slice(0, n);
  },
  async getSeries() {
    const all = await this.getAll();
    const map = {};
    all.forEach(s => {
      const key = s.series || '未分类';
      if (!map[key]) map[key] = { name: key, items: [], cover: s.cover };
      map[key].items.push(s);
    });
    return Object.values(map).map(g => ({
      name: g.name,
      count: g.items.length,
      cover: g.cover,
      latest: g.items.slice().sort((a, b) => (b.date || '').localeCompare(a.date || ''))[0],
      items: g.items,
    })).sort((a, b) => b.count - a.count);
  },
  async getCategories() {
    const all = await this.getAll();
    const set = new Set(all.map(s => s.category).filter(Boolean));
    return ['全部', ...set];
  },
};

/* ── Meditation Service（后端 /mobile/content 对接 + 本地回退）── */
const MeditationService = {
  async getDaily() {
    // 首选：后端 /mobile/content?category=devotion
    try {
      const data = await apiGet('/mobile/content?category=devotion&lang=zh');
      if (data.items && data.items.length) {
        const item = data.items[0];
        return {
          title: (typeof uiT === 'function') ? uiT('meditation.dailyLabel') : '今日灵修',
          subtitle: item.title,
          verse: (item.tags && item.tags[0]) || '',
          verseText: item.description || '',
          body: item.description || '',
        };
      }
    } catch (_) {}
    // 次选：本地 JSON — 解析失败（离线/损坏）也不应让界面崩溃，做防御（第六部分 P6-5）
    try {
      const data = await fetch('./data/meditation.json').then(r => r.json());
      return data.daily || {};
    } catch (_) { return {}; }
  },
  async getCards() {
    try {
      const data = await apiGet('/mobile/content?category=devotion&lang=zh');
      if (data.items && data.items.length) {
        return data.items.map(i => ({
          id: i.link_id,
          title: i.title,
          verse: (i.tags && i.tags[0]) || '',
          text: i.description || '',
          thumbnail: '📖',
          date: i.created_at,
        }));
      }
    } catch (_) {}
    // 本地 JSON — 未做保护解析会导致界面崩溃，做防御（第六部分 P6-5）
    try {
      const data = await fetch('./data/meditation.json').then(r => r.json());
      return data.cards || [];
    } catch (_) { return []; }
  }
};

/* ── Auth Service ──────────────────────────────────────────────────── */
const AuthService = {
  async login(email, password) {
    try {
      const res = await fetch(API_BASE + '/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      });
      const data = await res.json();
      if (res.ok) {
        return {
          ok: true,
          user: { email, name: data.display_name || email.split('@')[0] },
          token: data.token,
          sub_id: data.sub_id,
        };
      }
      return { ok: false, error: data.detail || '登录失败', code: res.status };
    } catch (e) {
      return { ok: false, error: '系统正在维护中，请稍后再试。' };
    }
  },

  async signup(email, password, displayName, termsAccepted, privacyAccepted) {
    try {
      const res = await fetch(API_BASE + '/auth/signup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email, password, display_name: displayName,
          terms_accepted: !!termsAccepted,
          privacy_accepted: !!privacyAccepted,
        }),
      });
      const data = await res.json();
      if (res.ok) {
        return {
          ok: true,
          user: { email, name: data.display_name || displayName || email.split('@')[0] },
          token: data.token,
          sub_id: data.sub_id,
          email_verification_required: !!data.email_verification_required,
        };
      }
      return { ok: false, error: data.detail || '注册失败', code: res.status };
    } catch (e) {
      return { ok: false, error: '无法连接服务器。' };
    }
  },

  async forgotPassword(email, lang) {
    try {
      const res = await fetch(API_BASE + '/auth/forgot-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, lang: lang || 'ko' }),
      });
      const data = await res.json();
      return res.ok
        ? { ok: true }
        : { ok: false, error: data.detail || '请求失败，请稍后再试。' };
    } catch (e) {
      return { ok: false, error: '无法连接服务器，请稍后再试。' };
    }
  },

  async resetPassword(token, password, lang) {
    try {
      const res = await fetch(API_BASE + '/auth/reset-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token, password, lang: lang || 'ko' }),
      });
      const data = await res.json();
      return res.ok
        ? { ok: true }
        : { ok: false, error: data.detail || '重置失败，链接可能已过期。' };
    } catch (e) {
      return { ok: false, error: '无法连接服务器，请稍后再试。' };
    }
  },

  async changePassword(currentPassword, newPassword) {
    try {
      const res = await fetch(API_BASE + '/auth/change-password', {
        method: 'POST',
        headers: Object.assign({ 'Content-Type': 'application/json' }, AppState.authHeaders()),
        body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
      });
      const data = await res.json();
      return res.ok
        ? { ok: true }
        : { ok: false, error: data.detail || '密码修改失败，请稍后再试。' };
    } catch (e) {
      return { ok: false, error: '无法连接服务器，请稍后再试。' };
    }
  },

  async listSessions() {
    try {
      const res = await fetch(API_BASE + '/auth/sessions', {
        headers: AppState.authHeaders(),
      });
      const data = await res.json();
      return res.ok
        ? { ok: true, sessions: data.sessions, current_device_id: data.current_device_id }
        : { ok: false, error: data.detail || '无法获取设备列表。' };
    } catch (e) {
      return { ok: false, error: '无法连接服务器，请稍后再试。' };
    }
  },

  async revokeSession(deviceId) {
    try {
      const res = await fetch(API_BASE + '/auth/sessions/' + encodeURIComponent(deviceId), {
        method: 'DELETE',
        headers: AppState.authHeaders(),
      });
      const data = await res.json();
      return res.ok
        ? { ok: true }
        : { ok: false, error: data.detail || '无法退出该设备。' };
    } catch (e) {
      return { ok: false, error: '无法连接服务器，请稍后再试。' };
    }
  },

  async loginWithGoogle() {
    // 通过 Google Identity Services 获取 ID 令牌
    return new Promise((resolve) => {
      if (!window.google || !window.google.accounts) {
        resolve({ ok: false, error: '无法使用 Google 登录（GIS 未加载）' });
        return;
      }

      // 确定 Google Client ID：
      //   1) 构建时注入的 window.GOSPEL_GOOGLE_CLIENT_ID
      //   2) 否则从后端 /auth/google/config 动态获取
      const resolveClientId = async () => {
        if (window.GOSPEL_GOOGLE_CLIENT_ID) return window.GOSPEL_GOOGLE_CLIENT_ID;
        try {
          const res = await fetch(API_BASE + '/auth/google/config');
          if (res.ok) {
            const cfg = await res.json();
            return cfg.client_id || '';
          }
        } catch (e) { /* 忽略 */ }
        return '';
      };

      resolveClientId().then((clientId) => {
        if (!clientId) {
          resolve({ ok: false, error: '未配置 Google 登录，请向管理员申请设置 GOOGLE_CLIENT_ID。' });
          return;
        }

        window.google.accounts.id.initialize({
          client_id: clientId,
          callback: async (response) => {
            const idToken = response.credential;
            if (!idToken) {
              resolve({ ok: false, error: '未能获取 Google 认证令牌。' });
              return;
            }
            // 将令牌发送到后端 → 校验 → 签发会话令牌
            try {
              const res = await fetch(API_BASE + '/auth/google', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ id_token: idToken }),
              });
              const data = await res.json();
              if (res.ok) {
                resolve({
                  ok: true,
                  user: {
                    email: data.email || '',
                    name: data.display_name || 'Google User',
                  },
                  token: data.token,
                  sub_id: data.sub_id,
                });
              } else {
                resolve({ ok: false, error: data.detail || 'Google 登录失败' });
              }
            } catch (e) {
              resolve({ ok: false, error: '无法连接服务器。' });
            }
          },
        });

        // 显示 Google One Tap / 弹窗
        window.google.accounts.id.prompt((notification) => {
          if (notification.isNotDisplayed() || notification.isSkippedMoment()) {
            resolve({ ok: false, error: 'Google 登录窗口未能显示，请关闭弹窗拦截。' });
          }
        });
      });
    });
  },
};

/* ── Chat Service（实际 /chat API 对接）─────────────────────────── */
/* ── LOCAL GREETING/SMALLTALK SHORT-CIRCUIT ───────────────────────
   与后端 chat_pipeline.is_greeting_or_smalltalk 完全一致的判定，
   在手机端先行识别纯问候/感谢/闲聊，直接返回本地文案，
   跳过整条 /chat/stream(RAG + LLM) 网络请求 → 服务器零负担。
   危机表达不在该正则内，会继续走服务器(安全)。 */
const _GREETING_RE = /^(?:안녕(?:하세요|하십니까|하십니(?:까)?|해|히|하)?|반가(?:워(?:요)?|습니까|습니다|웁니다|워요|합니까)?|반갑(?:습니다|습니까|해요|해|니(?:까)?)?|만나서\s*(?:반가(?:워(?:요)?|습니까|습니다|워요)?|반갑(?:습니다|습니까|해요|해)?)|오랜만(?:이에요|이야|이십니까|이에요|이야|이십니(?:까)?)?|여보세(?:요|여)?|하이(?:요)?|헬로(?:우)?|하로|hi+(?:\s+(?:there|all|everyone|everybody|folks|guys|mate))?|hello+(?:\s+(?:there|all|everyone|everybody|folks|guys|mate))?|hey+(?:\s+(?:there|all|guys|mate))?|howdy|yo+|good\s*(?:morning|afternoon|evening|day)|how\s+are\s+you|what'?s\s*up|sup\b|감사(?:합니다|해요|해|함다|함니(?:까)?)?|고마워(?:요)?|고맙(?:습니다|네요|요|습니까|해요|해)?|땡큐|땡스|thank\s*you|thanks+|tnx|thx|잘\s*부탁|방가(?:요)?|뱅가|반가워요|ㅋ{2,}|ㅎ{2,}|ㅋ+ㅎ+|ㅎ+ㅋ+|你好|您好|哈喽|嗨)[\s~!.,?~ㅋㅎㅠㅜ]*$/i;

function isGreetingOrSmalltalk(query) {
  if (!query) return false;
  const q = query.trim();
  if (!q || q.length > 40) return false;
  return _GREETING_RE.test(q);
}

const _GREETING_REPLIES = {
  zh: '您好！很高兴与您同行。关于信仰与圣经，您可以向我提出任何问题。让我们一起祷告、默想。🙏',
  ko: '안녕하세요! 믿음과 성경에 관해 어떤 질문이든 편히 물어보세요. 함께 기도하고 묵상해요. 🙏',
  en: 'Hello! Feel free to ask me anything about faith and the Bible. Let’s pray and reflect together. 🙏',
};
function _greetingReply(lang) {
  return _GREETING_REPLIES[lang] || _GREETING_REPLIES.zh;
}

/* 간단 언어 감지(지배 문자 기준) — 로컬 인사말 폴백에만 사용. RAG 본문은 백엔드가 감지. */
function _detectLang(text) {
  const hangul = (text.match(/[\uac00-\ud7a3]/g) || []).length;
  const hanzi = (text.match(/[\u4e00-\u9fff]/g) || []).length;
  if (hangul >= hanzi && hangul > 0) return 'ko';
  if (hanzi > 0) return 'zh';
  return 'en';
}

const ChatService = {
  async send(message, history = [], targetLang = 'auto', onToken = null) {
    // LOCAL SHORT-CIRCUIT: 纯问候/闲聊在本地直接回复，不发往服务器(跳过 RAG + LLM)。
    if (isGreetingOrSmalltalk(message)) {
      const lang = (targetLang && targetLang !== 'auto') ? targetLang : _detectLang(message);
      return { role: 'assistant', content: _greetingReply(lang), sources: [], quotaExceeded: false, loginRequired: false };
    }
    const controller = new AbortController();
    // 后端 llm_provider_timeout_sec + RAG/网络缓冲 → 上限 120s
    const timeout = setTimeout(() => controller.abort(), 120000);

    try {
      const headers = {
        'Content-Type': 'application/json',
        ...AppState.authHeaders(),
      };
      const res = await fetch(API_BASE + '/chat/stream', {
        method: 'POST',
        headers,
        body: JSON.stringify({
          query: message,
          history: history.slice(-10),
          user_id: AppState.get('subId') || AppState.get('guestId'),
          target_lang: targetLang,
        }),
        signal: controller.signal,
      });
      clearTimeout(timeout);

      if (!res.ok) {
        // 429 配额超限等 → 后端正文以 JSON 形式给出友好提示（与 web/app.js 行为一致）
        let detail = null;
        try { detail = await res.json(); } catch (_) { /* 忽略 */ }
        const d = (detail && detail.detail) ? detail.detail : detail;
        if (res.status === 429 && d && d.code === 'QUOTA_EXCEEDED') {
          const loginReq = d.login_required !== false;
          // 不强制弹出登录窗口，而是引导用户在聊天提示消息中操作。
          // 若 login_required 为 true，提示气泡会附带“登录以继续”按钮。
          const content = loginReq
            ? '⚠️ 今日免费提问次数已用完。登录后每天可使用更多次提问。请点击下方“登录以继续”按钮。'
            : '⚠️ 今日免费提问次数已用完，明天可再次使用。🙏';
          return {
            role: 'assistant',
            content,
            quotaExceeded: true,
            loginRequired: loginReq,
          };
        }
        // 429 以外的服务器错误（500/502/403 等）— 与网络中断明确区分。
        const serverMsg = (typeof d === 'string' && d)
          || (d && d.message)
          || ('服务器发生错误（HTTP ' + res.status + '）');
        return { role: 'assistant', content: String(serverMsg) };
      }

      // ⚡ OPT-SPEED: SSE 流式 — 从首个 token（nvidia 实测 TTFT 0.48s）开始实时逐字输入。
      // SSE 解析器与 web/app.js 采用相同规约：
      //   - event: done → 结束
      //   - data: 若为 JSON({...}) 则是元信息(interaction_id/sources)，否则为回复片段
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = '';
      let meta = null;
      let content = '';

      const processEvent = (raw) => {
        let eventName = null; const dataLines = [];
        raw.split('\n').forEach((line) => {
          if (line.startsWith('event:')) eventName = line.slice(6).trim();
          else if (line.startsWith('data:')) dataLines.push(line.slice(5).replace(/^ /, ''));
        });
        const dataStr = dataLines.join('\n');
        if (eventName === 'done') return;
        if (!dataStr) return;
        const trimmed = dataStr.trim();
        if (trimmed.startsWith('{') && trimmed.endsWith('}')) {
          try { meta = JSON.parse(trimmed); return; } catch (_) { /* 非元信息 → 按文本处理 */ }
        }
        content += dataStr;
        if (onToken) onToken(content);
      };

      while (true) {
        const { done, value } = await reader.read();
        if (done) { if (buf.trim()) processEvent(buf); break; }
        buf += decoder.decode(value, { stream: true });
        let idx;
        while ((idx = buf.indexOf('\n\n')) !== -1) {
          const ev = buf.slice(0, idx);
          buf = buf.slice(idx + 2);
          processEvent(ev);
        }
      }

      return {
        role: 'assistant',
        content: content || '未能收到回复。',
        quotaExceeded: false,
        loginRequired: false,
        meta,
      };
    } catch (e) {
      clearTimeout(timeout);
      if (e.name === 'AbortError') {
        return { role: 'assistant', content: '响应超时，请稍后再试。' };
      }
      return { role: 'assistant', content: '系统正在维护中，请稍后再试。🙏' };
    }
  }
};

/* ═══════════════════════════════════════════════════════════════════════════
   AdService — 광고 배너 조회
   ═══════════════════════════════════════════════════════════════════════════ */
const AdService = {
  /**
   * Fetch active ads from backend.
   * Returns { ads: [{ id, title, subtitle, link_url, slot, image_url? }] }.
   * Ads are cached for 5 minutes in memory.
   */
  _cache: null,
  _cacheTime: 0,

  async fetchAds() {
    const now = Date.now();
    if (this._cache && now - this._cacheTime < 5 * 60 * 1000) {
      return this._cache;
    }
    try {
      const res = await fetch(`${API_BASE}/ads/list`);
      if (!res.ok) return { ads: [] };
      const data = await res.json();
      this._cache = data;
      this._cacheTime = now;
      return data;
    } catch (_) {
      return { ads: [] };
    }
  },

  /** Get full image URL for an ad. */
  imageUrl(adId) {
    return `${API_BASE}/ads/image/${adId}`;
  },
};

/* ═══════════════════════════════════════════════════════════════════════════
   QAService — 인기 질문 랭킹 조회
   ═══════════════════════════════════════════════════════════════════════════ */
const QAService = {
  // 客户端 5 分钟 TTL 缓存：避免每次切到 Today 标签都请求 /trending/cards (lang=zh)。
  _cache: {},
  _cacheTime: {},
  /**
   * Fetch top questions (public ranking endpoint).
   * Returns { ranking: [{ question_id, question, answer_count, score, ... }] }.
   */
  async fetchRanking(limit = 20, lang = 'zh') {
    const key = `${lang}:${limit}`;
    const now = Date.now();
    if (this._cache[key] && now - (this._cacheTime[key] || 0) < 5 * 60 * 1000) {
      return this._cache[key];
    }
    try {
      const res = await fetch(`${API_BASE}/trending/cards?period=7d&limit=${limit}&lang=${lang}`);
      if (!res.ok) return { ranking: [] };
      const data = await res.json();
      // 백엔드 응답 키는 'rankings' (구 버전 'ranking' 도 호환)
      const rankings = data.cards || data.rankings || data.ranking || [];
      const result = { ranking: rankings };
      this._cache[key] = result;
      this._cacheTime[key] = now;
      return result;
    } catch (_) {
      return { ranking: [] };
    }
  },
};

/* ── 대화 기록 (서버 /mobile/history) ─────────────────────────────────────
   로그인 사용자만 서버 기록 조회 가능. 게스트는 로컬 영속(gospel_chat)만 사용. */
const HistoryService = {
  async list(search = '', limit = 100) {
    if (!AppState.get('isLoggedIn')) return { history: [] };
    const q = search ? `&search=${encodeURIComponent(search)}` : '';
    try {
      const res = await fetch(`${API_BASE}/mobile/history?limit=${limit}${q}`, {
        headers: Object.assign({ 'Accept': 'application/json' }, AppState.authHeaders()),
      });
      if (!res.ok) return { history: [] };
      const data = await res.json();
      return { history: Array.isArray(data) ? data : (data.history || []) };
    } catch (_) {
      return { history: [] };
    }
  },
  async remove(interactionId) {
    try {
      const res = await fetch(`${API_BASE}/mobile/history/${encodeURIComponent(interactionId)}`, {
        method: 'DELETE',
        headers: AppState.authHeaders(),
      });
      return res.ok;
    } catch (_) {
      return false;
    }
  },
};

/* ── 말씀 하이라이트/북마크/메모 (서버 /mobile/annotations) ──────────────── */
const AnnotationService = {
  async list() {
    if (!AppState.get('isLoggedIn')) return { annotations: [] };
    try {
      const res = await fetch(`${API_BASE}/mobile/annotations`, {
        headers: Object.assign({ 'Accept': 'application/json' }, AppState.authHeaders()),
      });
      if (!res.ok) return { annotations: [] };
      const data = await res.json();
      return { annotations: Array.isArray(data) ? data : (data.annotations || []) };
    } catch (_) {
      return { annotations: [] };
    }
  },
  async save(annotation) {
    try {
      const res = await fetch(`${API_BASE}/mobile/annotations`, {
        method: 'POST',
        headers: Object.assign({ 'Content-Type': 'application/json' }, AppState.authHeaders()),
        body: JSON.stringify(annotation),
      });
      if (!res.ok) return null;
      return res.json();
    } catch (_) {
      return null;
    }
  },
  async remove(id) {
    try {
      const res = await fetch(`${API_BASE}/mobile/annotations/${encodeURIComponent(id)}`, {
        method: 'DELETE',
        headers: AppState.authHeaders(),
      });
      return res.ok;
    } catch (_) {
      return false;
    }
  },
  async removeByRef(book, chapter, verse) {
    try {
      const res = await fetch(`${API_BASE}/mobile/annotations/ref/${encodeURIComponent(book)}/${chapter}/${verse}`, {
        method: 'DELETE',
        headers: AppState.authHeaders(),
      });
      return res.ok;
    } catch (_) {
      return false;
    }
  },
};
