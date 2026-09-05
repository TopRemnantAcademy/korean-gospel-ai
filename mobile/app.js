/* ═══════════════════════════════════════════════════════════════════════════
   Main App — entry point, tab switching, initialization, settings panel
   ═══════════════════════════════════════════════════════════════════════════ */

const SCREEN_RENDERERS = {
  bible: renderBible,
  hymns: renderHymns,
  word: renderWord,
  today: renderToday,
  login: renderLogin,
  mypage: renderMy,
};

// T-8：渲染序列号——快速切换标签时仅应用最新请求
let _renderSeq = 0;

async function renderScreen(tabId) {
  // T-3：清理全局浮层（防止标签切换时残留）
  if (typeof _closeDetail === 'function') _closeDetail();
  if (typeof _closePlaylistDetail === 'function') _closePlaylistDetail();
  if (typeof closeSheet === 'function') closeSheet();
  if (typeof closeActionSheet === 'function') closeActionSheet();

  /* Update tab bar active state */
  $$('.tab-item').forEach(item => {
    item.classList.toggle('active', item.dataset.tab === tabId);
  });

  /* 성경 탭에서만 하드웨어 볼륨키를 폰트 조절에 사용 (이탈 시 일반 볼륨 복원) */
  if (tabId === 'bible') enableFontKeyCapture();
  else disableFontKeyCapture();

  const seq = ++_renderSeq;

  /* Render the screen */
  const renderer = SCREEN_RENDERERS[tabId];
  if (renderer) {
    await renderer();
    // T-8：若出现更新的标签切换，则丢弃此结果
    if (seq !== _renderSeq) return;
  }
}

/* ═══════════════════════════════════════════════════════════════════════════
   Settings Panel (⚙️)
   ═══════════════════════════════════════════════════════════════════════════ */

function openSettings() {
  let panel = $('#settings-overlay');
  if (!panel) {
    panel = _buildSettingsPanel();
    document.body.append(panel);
  }
  panel.classList.add('open');
  _refreshSettingsAuth();
  _refreshSettingsTheme();
}

function closeSettings() {
  const panel = $('#settings-overlay');
  if (panel) panel.classList.remove('open');
}

/* 마이(방문자) 페이지의 멤버십 CTA → 로그인 폼이 있는 설정 패널 오픈 */
function _goToAuth() {
  openSettings();
}

/* ── Android 하드웨어 뒤로가기 ────────────────────────────────────────────────
   열린 오버레이를 우선순위대로 닫고, 닫을 것이 없으면 앱을 종료한다.
   (기존엔 backButton 리스너가 없어 플레이어/설정 등이 열려 있어도 즉시 종료되던 문제) */
function _closeTopOverlay() {
  // 1) 액션시트 (트랙 메뉴/수면 타이머 등)
  if (document.querySelector('.action-sheet.open')) {
    if (typeof closeActionSheet === 'function') closeActionSheet();
    return true;
  }
  // 2) 재생 큐
  if (document.querySelector('#queue-sheet:not(.hidden)')) {
    if (typeof closeQueue === 'function') closeQueue();
    return true;
  }
  // 3) 전체화면 플레이어
  if (document.querySelector('#player-sheet:not(.hidden)')) {
    if (typeof closeSheet === 'function') closeSheet();
    return true;
  }
  // 4) 설정 오버레이
  if (document.querySelector('#settings-overlay.open')) {
    closeSettings();
    return true;
  }
  return false;
}

function _setupBackButton() {
  const Cap = window.Capacitor;
  if (!(Cap && Cap.isNative && Cap.Plugins && Cap.Plugins.App)) return;
  Cap.Plugins.App.addListener('backButton', () => {
    if (_closeTopOverlay()) return;
    Cap.Plugins.App.exitApp();
  });
}

function _buildSettingsPanel() {
  const overlay = h('div', { id: 'settings-overlay', className: 'settings-overlay',
    onClick: (e) => { if (e.target === e.currentTarget) closeSettings(); }
  });
  const panel = h('div', { className: 'settings-panel' });

  /* Header — 그라데이션 배너 + 서브타이틀 */
  panel.append(h('div', { className: 'settings-panel-header' },
    h('div', { className: 'settings-panel-header__inner' },
      h('span', { className: 'settings-panel-header__icon', textContent: '⚙️' }),
      h('div', { className: 'settings-panel-header__text' },
        h('h3', { textContent: uiT('settings.title') }),
        h('p', { className: 'settings-panel-header__sub', textContent: uiT('settings.titleSub') }),
      ),
    ),
    h('button', { className: 'btn-icon settings-close', textContent: '✕', onClick: closeSettings }),
  ));

  /* 스크롤 컨테이너 — 카드 기반 레이아웃 */
  const body = h('div', { className: 'settings-body' });

  /* 네비게이션 그룹: 계정 */
  const accountGroup = h('div', { className: 'settings-group' });
  accountGroup.append(h('p', { className: 'settings-group__label', textContent: uiT('my.account') }));
  accountGroup.append(_buildAuthSection());
  body.append(accountGroup);

  /* 네비게이션 그룹: 화면 */
  const displayGroup = h('div', { className: 'settings-group' });
  displayGroup.append(h('p', { className: 'settings-group__label', textContent: uiT('my.displayFont') }));
  displayGroup.append(_buildThemeSection());
  displayGroup.append(_buildLangSection());
  body.append(displayGroup);

  panel.append(body);
  overlay.append(panel);
  return overlay;
}

/* ── Theme 3종 선택 (밝음/어두움/시스템) ─────────────────────────── */
function _buildThemeSection() {
  const section = h('div', { className: 'settings-card settings-card--pad' });
  const text = h('div', { className: 'settings-row__text settings-row__text--icon' },
    h('span', { className: 'settings-row__icon', textContent: '🎨' }),
    h('div', {},
      h('p', { className: 'settings-row__title', textContent: uiT('settings.theme') }),
      h('p', { className: 'settings-row__sub', textContent: uiT('settings.themeHint') }),
    ),
  );
  const current = AppState.get('darkMode');
  const options = h('div', { className: 'theme-options' });
  const choices = [
    { mode: 'light', icon: '☀️', label: uiT('settings.themeLight') },
    { mode: 'dark', icon: '🌙', label: uiT('settings.themeDark') },
    { mode: 'system', icon: '🖥️', label: uiT('settings.themeSystem') },
  ];
  // 시스템 모드: darkMode가 null(미설정)이면 시스템, 명시적 true/false면 그 모드
  const activeMode = current === null ? 'system' : (current ? 'dark' : 'light');
  choices.forEach(c => {
    const b = h('button', {
      className: 'theme-option' + (activeMode === c.mode ? ' active' : ''),
      onClick: () => {
        // 시스템: gospel_dark 제거(기본=시스템 밝기 따라감) / 그 외: 명시 저장
        if (c.mode === 'system') {
          localStorage.removeItem('gospel_dark');
          AppState.set('darkMode', null);
        } else {
          const isDark = c.mode === 'dark';
          localStorage.setItem('gospel_dark', isDark);
          AppState.set('darkMode', isDark);
        }
        document.documentElement.classList.toggle('dark', c.mode === 'dark' ||
          (c.mode === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches));
        options.querySelectorAll('.theme-option').forEach(x => x.classList.remove('active'));
        b.classList.add('active');
      },
    },
      h('span', { className: 'theme-option__icon', textContent: c.icon }),
      h('span', { className: 'theme-option__label', textContent: c.label }),
    );
    options.append(b);
  });
  section.append(text, options);
  return section;
}

/* ── UI 언어 선택 ────────────────────────────────────────────────────── */
function _buildLangSection() {
  const section = h('div', { className: 'settings-card' });
  const row = h('div', { className: 'settings-row settings-row--stack' });
  row.append(h('div', { className: 'settings-row__text settings-row__text--icon' },
    h('span', { className: 'settings-row__icon', textContent: '🌐' }),
    h('div', {},
      h('p', { className: 'settings-row__title', textContent: uiT('settings.language') }),
      h('p', { className: 'settings-row__sub', textContent: uiT('settings.langHint') }),
    ),
  ));
  const opts = h('div', { className: 'lang-options' });
  const current = AppState.get('uiLang') || '__system__';
  const langs = [
    { code: '__system__', label: uiT('settings.langSystem') },
    { code: 'ko', label: uiT('lang.ko') },
    { code: 'en', label: uiT('lang.en') },
    { code: 'zh-CN', label: uiT('lang.zhcn') },
    { code: 'zh-TW', label: uiT('lang.zhtw') },
  ];
  langs.forEach(o => {
    const b = h('button', {
      className: 'lang-opt' + (current === o.code ? ' active' : ''),
      textContent: o.label,
      onClick: () => {
        AppState.setUiLang(o.code === '__system__' ? null : o.code);
        opts.querySelectorAll('.lang-opt').forEach(x => x.classList.remove('active'));
        b.classList.add('active');
      },
    });
    opts.append(b);
  });
  row.append(opts);
  section.append(row);
  return section;
}

function _refreshSettingsTheme() {  const knob = $('#settings-theme-knob');
  const label = $('#settings-theme-label');
  const isDark = AppState.get('darkMode');
  if (knob) knob.classList.toggle('on', isDark);
  if (label) label.textContent = isDark ? uiT('theme.dark') : uiT('theme.light');
}

/* ── Auth section ──────────────────────────────────────────────────────── */
function _buildAuthSection() {
  const section = h('div', { className: 'settings-card', id: 'settings-auth-section' });
  return section;
}

function _refreshSettingsAuth() {
  const section = $('#settings-auth-section');
  if (!section) return;
  section.innerHTML = '';

  if (AppState.get('isLoggedIn')) {
    const user = AppState.get('user') || {};
    section.append(
      h('div', { className: 'settings-profile' },
        h('div', { className: 'avatar-lg', textContent: (user.name || '?')[0].toUpperCase() }),
        h('p', { className: 'text-lg', textContent: user.name }),
        h('p', { className: 'text-muted', textContent: user.email || '' }),
      ),
      h('button', {
        className: 'btn-primary settings-logout-btn',
        textContent: uiT('account.logout'),
        onClick: () => { AppState.logout(); _refreshSettingsAuth(); }
      }),
    );
    return;
  }

  // Login / Signup form
  if (!window._settingsAuthMode) window._settingsAuthMode = 'login';
  const mode = window._settingsAuthMode;

  const tabs = h('div', { className: 'auth-tabs' },
    h('button', {
      className: 'auth-tab' + (mode === 'login' ? ' active' : ''),
      textContent: uiT('account.login'),
      onClick: () => { window._settingsAuthMode = 'login'; _refreshSettingsAuth(); }
    }),
    h('button', {
      className: 'auth-tab' + (mode === 'signup' ? ' active' : ''),
      textContent: uiT('account.signup'),
      onClick: () => { window._settingsAuthMode = 'signup'; _refreshSettingsAuth(); }
    }),
  );

  const emailInput = h('input', { type: 'email', placeholder: uiT('account.email'), className: 'input', id: 'settingsEmail' });
  const pwInput = h('input', { type: 'password', placeholder: uiT('account.passwordPlaceholder'), className: 'input', id: 'settingsPassword' });
  const errorEl = h('p', { className: 'error-text hidden', id: 'settingsLoginError' });

  const submitBtn = h('button', {
    className: 'btn-primary',
    textContent: mode === 'login' ? uiT('account.loginBtn') : uiT('account.signupBtn'),
    onClick: async (event) => {
      const email = emailInput.value.trim();
      const pw = pwInput.value;
      if (!email || !pw) {
        errorEl.textContent = uiT('auth.needEmailPw');
        show(errorEl);
        return;
      }
      hide(errorEl);
      const btn = event.currentTarget;
      if (btn) { btn.textContent = uiT('common.processing'); btn.disabled = true; }

      const result = mode === 'login'
        ? await AuthService.login(email, pw)
        : await AuthService.signup(email, pw);

      if (result.ok) {
        if (result.email_verification_required) {
          errorEl.textContent = uiT('auth.verifySent');
          show(errorEl);
          if (btn) { btn.textContent = mode === 'login' ? uiT('account.loginBtn') : uiT('account.signupBtn'); btn.disabled = false; }
          return;
        }
        AppState.login(result.user, result.token, result.sub_id);
        _refreshSettingsAuth();
      } else {
        errorEl.textContent = result.error || uiT('auth.fail');
        show(errorEl);
        if (btn) { btn.textContent = mode === 'login' ? uiT('account.loginBtn') : uiT('account.signupBtn'); btn.disabled = false; }
      }
    }
  });

  // Google login (GIS SDK 미주입/중국 빌드에서는 숨김 — 죽은 버튼 방지)
  const googleBtn = h('button', {
    className: 'btn-google',
    textContent: uiT('account.google'),
    onClick: async () => {
      googleBtn.textContent = uiT('account.googleProcessing');
      googleBtn.disabled = true;
      try {
        const result = await AuthService.loginWithGoogle();
        if (result.ok) {
          AppState.login(result.user, result.token, result.sub_id);
          _refreshSettingsAuth();
        } else {
          errorEl.textContent = result.error || uiT('auth.googleFail');
          show(errorEl);
          googleBtn.textContent = uiT('account.google');
          googleBtn.disabled = false;
        }
      } catch (_) {
        errorEl.textContent = uiT('auth.googleError');
        show(errorEl);
        googleBtn.textContent = uiT('account.google');
        googleBtn.disabled = false;
      }
    }
  });
  // GIS SDK 가 로드되지 않았거나(중국 빌드) Client ID 가 없으면 버튼 숨김
  if (!window.google || !window.google.accounts) {
    googleBtn.classList.add('hidden');
  }

  const divider = h('div', { className: 'divider' }, h('span', { textContent: uiT('common.or') }));

  // GIS SDK 미로드 시 Google 버튼과 구분선을 함께 숨김 (혼자 떠 있는 '或' 방지)
  if (!window.google || !window.google.accounts) {
    divider.classList.add('hidden');
    section.append(tabs, emailInput, pwInput, errorEl, submitBtn);
  } else {
    section.append(tabs, emailInput, pwInput, errorEl, submitBtn, divider, googleBtn);
  }
}

/* ═══════════════════════════════════════════════════════════════════════════
   Init
   ═══════════════════════════════════════════════════════════════════════════ */

async function initApp() {
  /* Z-4: Capacitor 네이티브 플러그인 초기화 (브라우저/PWA 에서는 no-op).
     Capacitor 런타임이 있고 해당 플러그인이 등록돼 있을 때만 동작. */
  if (window.Capacitor && window.Capacitor.Plugins) {
    const { Keyboard, StatusBar, Device } = window.Capacitor.Plugins;
    if (StatusBar && StatusBar.setBackgroundColor) {
      StatusBar.setBackgroundColor({ color: '#0C0A08' }).catch(() => {});
    }
    if (Keyboard) {
      // 입력 포커스 시 화면 위로 스크롤 보장
      Keyboard.setScroll({ isDisabled: false }).catch(() => {});
    }
    // L-2: 시스템 언어 감지(앱 설치 후 첫 실행 시 기기 언어 자동 적용).
    // AppState.uiLang 가 명시적으로 설정돼 있으면 사용자 선택을 존중(덮어쓰지 않음).
    if (Device && Device.getLanguageCode) {
      Device.getLanguageCode().then(r => {
        if (r && r.value) {
          window.__deviceLangCode = r.value;
          // BUG FIX(2026-08-18): 첫 renderScreen() 은 getLanguageCode resolve 전에 실행되므로
          // 기본(영어/첫 언어)으로 그려진다. resolve 후 applyUiLangAll() 로 현재 탭 UI 를
          // 기기 언어로 재렌더링해야 설치 직후 화면이 시스템 언어를 따른다.
          if (!AppState.get('uiLang')) {
            document.documentElement.lang = (r.value || 'en').toLowerCase().indexOf('ko') === 0 ? 'ko'
              : (r.value || 'en').toLowerCase().indexOf('zh') === 0 ? ((r.value || 'en').toLowerCase().indexOf('tw') >= 0 || (r.value || 'en').toLowerCase().indexOf('hant') >= 0 ? 'zh-TW' : 'zh-CN') : 'en';
            if (typeof applyUiLangAll === 'function') applyUiLangAll();
          }
        }
      }).catch(() => {});
    }
  }

  const app = $('#app');

  /* Screen container */
  const screenContainer = h('main', { id: 'screen-container', className: 'screen-container' });

  /* Tab bar */
  const tabBar = renderTabBar(TABS);

  app.append(screenContainer, tabBar);

  /* 全局诗歌播放器（迷你栏 + 完整面板） */
  if (typeof initPlayer === 'function') initPlayer();

  /* 활동 이벤트 수집 → 서버 동기화 (EventService 는 player 이후 init) */
  if (typeof EventService !== 'undefined') EventService.init();

  /* Listen to tab changes */
  AppState.on('activeTab', tabId => renderScreen(tabId));

  /* Listen to dark mode changes */
  AppState.on('darkMode', isDark => {
    document.documentElement.classList.toggle('dark', isDark);
    localStorage.setItem('gospel_dark', isDark);
    _refreshSettingsTheme();
  });

  /* Apply initial dark mode */
  (function() {
    const isDark = AppState.get('darkMode');
    document.documentElement.classList.toggle('dark', isDark);
  })();

  /* Android 하드웨어 뒤로가기 처리 — 열린 오버레이를 우선순위대로 닫고, 없으면 앱 종료.
     (기존엔 backButton 리스너가 없어 시트/설정이 열려 있어도 앱이 즉시 종료되던 UX 버그) */
  _setupBackButton();

  /* BB-4: 백그라운드 전환(탭 숨김) 시 합성 패드 재생만 정지 — CPU/배터리 절약.
     실제 오디오(audio) 재생 중에는 건드리지 않음(사용자 의도 보존). */
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      if (typeof Player !== 'undefined') {
        const _st = Player.getState();
        if (_st.isPlaying && !_st.audio) Player.pause();
      }
    } else {
      // 포그라운드 복귀 → 미디어 캐시 무효화 후 현재 탭 재렌더(최신 카탈로그 즉시 반영)
      if (typeof MediaService !== 'undefined') MediaService.invalidate();
      renderScreen(AppState.get('activeTab'));
    }
  });

  /* 2026-08-01: 버전 게이트 — 강제 업데이트 대상이면 앱 구동 차단.
     서버 조회 실패 시 통과(오프라인에서 앱 못 쓰는 상황 방지). */
  try {
    if (typeof VersionService !== 'undefined') {
      const vres = await VersionService.check();
      if (vres.forceUpdate) {
        _renderForceUpdateOverlay(vres);
        return; // 초기 렌더 중단 — 강제 업데이트만 노출
      }
      if (vres.latestAvailable && typeof showToast === 'function') {
        const url = vres.updateUrl || './download.html';
        showToast(uiT('update.available') + ' ' + vres.latestVersionName + uiT('update.availableTail'));
      }
    }
  } catch (_) { /* 게이트 실패는 무시(앱 정상 구동) */ }

  /* 2026-07-29: Web Push 구독(알림 수신) — 게스트 포함 모든 사용자.
     SW 등록 + 권한 요청 + 구독은 내부에서 try/catch 로 안전 처리. */
  if (typeof PushService !== 'undefined') {
    PushService.setup().catch(() => {});
  }

  /* Initial render */
  renderScreen(AppState.get('activeTab'));
}

/* 강제 업데이트 차단 오버레이 */
function _renderForceUpdateOverlay(vres) {
  const app = $('#app');
  app.innerHTML = '';
  const url = vres.updateUrl || './download.html';
  const overlay = h('div', { className: 'force-update-overlay' },
    h('div', { className: 'force-update-card' },
      h('div', { className: 'force-update-icon', textContent: '⤓' }),
      h('h2', { textContent: uiT('update.title') }),
      h('p', { className: 'text-muted', textContent: uiT('update.body') }),
      h('a', { className: 'btn-primary', href: url, textContent: uiT('update.get') }),
    ),
  );
  app.append(overlay);
}

document.addEventListener('DOMContentLoaded', initApp);
