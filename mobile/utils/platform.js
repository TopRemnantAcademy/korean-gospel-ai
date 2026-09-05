/* ═══════════════════════════════════════════════════════════════════════════
   platform — 웹(PWA) / 안드로이드(Capacitor) 런타임 분기 유틸
   • 단일 소스(mobile/)가 웹과 APK 양쪽에서 동일하게 동작하도록 판별.
   • 네이티브 플러그인 호출은 반드시 isNative() 가드 후 사용.
   ═══════════════════════════════════════════════════════════════════════════ */

const Platform = (function () {
  /* Capacitor 런타임 존재 여부 (브라우저/PWA 에서는 window.Capacitor 미정의) */
  const isNative = !!(window.Capacitor && window.Capacitor.isNative);

  /* 플랫폼 문자열 — 백엔드 푸시 구독 분류 등에 사용
     웹(static PWA) 과 안드로이드(Capacitor WebView) 를 명확히 구분. */
  function getPlatform() {
    if (isNative) return 'android';
    return 'web';
  }

  /* 네이티브 플러그인 안전 호출 래퍼
     플러그인이 없으면(웹) 조용히 무시. 호출부마다 try/catch 반복 제거. */
  function callPlugin(pluginName, method, args) {
    if (!isNative) return Promise.resolve(null);
    try {
      const plugin = window.Capacitor.Plugins && window.Capacitor.Plugins[pluginName];
      if (!plugin || typeof plugin[method] !== 'function') return Promise.resolve(null);
      return Promise.resolve(plugin[method](args || {}));
    } catch (_) {
      return Promise.resolve(null);
    }
  }

  return { isNative, getPlatform, callPlugin };
})();
