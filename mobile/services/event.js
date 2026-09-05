/* 활동 이벤트 수집/동기화 — 서버 /mobile/events/batch 로 배치 전송.
 *
 * 캡처 대상: 화면이동(page_view), 미디어 재생(media_play_*), 검색(search),
 * 말씀 annotate(verse_annotation_*), 공유(share), 세션(session_*), 클라이언트 에러(js_error).
 *
 * 설계:
 *  - 인메모리 링 버퍼 + 30s/20건 임계 플러시 + visibilitychange/pagehide 최종 플러시.
 *  - 게스트는 device_id(guestId) 로만 귀속, 로그인 시 Authorization 토큰에서 서버가 sub_id 를 추출.
 *  - 클라이언트가 주장한 subscriber_id 는 서버에서 무시(스푸핑 방지).
 */
const EventService = (function () {
  const FLUSH_MS = 30000;
  const FLUSH_COUNT = 20;
  const MAX_BATCH = 200;

  let _buf = [];
  let _timer = null;
  let _sessionId = null;
  let _inited = false;

  // 미디어 진행 임계 추적 (25/50/75% 버킷 + 90% 완료 플래그)
  let _lastBucket = 0;
  let _reportedComplete = false;

  function _platform() {
    try {
      if (window.Capacitor) {
        const p =
          (window.Capacitor.getPlatform && window.Capacitor.getPlatform()) ||
          window.Capacitor.platform;
        if (p && p !== "web") return p; // android | ios
      }
    } catch (_) {}
    return "web";
  }
  function _appVersion() {
    return window.APP_VERSION || "unknown";
  }
  function _subId() {
    return AppState.get("subId") || null;
  }
  function _deviceId() {
    return AppState.get("guestId") || null;
  }

  function _flush() {
    if (_timer) {
      clearTimeout(_timer);
      _timer = null;
    }
    if (!_buf.length) return;
    const batch = _buf.splice(0, MAX_BATCH);
    const body = {
      device_id: _deviceId(),
      subscriber_id: _subId(),
      session_id: _sessionId,
      platform: _platform(),
      app_version: _appVersion(),
      events: batch,
    };
    fetch(`${API_BASE}/mobile/events/batch`, {
      method: "POST",
      headers: Object.assign(
        { "Content-Type": "application/json" },
        AppState.authHeaders()
      ),
      body: JSON.stringify(body),
      keepalive: true,
    }).catch(function () {
      // 전송 실패 → 버퍼 복원(다음 플러시 재시도). 용량 초과 방지로 앞쪽에 삽입.
      _buf.unshift.apply(_buf, batch);
      if (_buf.length > MAX_BATCH * 3) _buf.length = MAX_BATCH * 3;
    });
  }

  function _ensureTimer() {
    if (_timer) return;
    _timer = setTimeout(_flush, FLUSH_MS);
  }

  function capture(event_type, payload) {
    if (!_inited) return;
    _buf.push({ event_type: event_type, ts: Date.now() / 1000, payload: payload || {} });
    if (_buf.length >= FLUSH_COUNT) _flush();
    else _ensureTimer();
  }

  // ── 미디어 이벤트 (player.js 의 Player.on 구독용) ──────────────────────
  function _resetMedia() {
    _lastBucket = 0;
    _reportedComplete = false;
  }
  function _meta(cur) {
    return {
      media_id: cur && cur.id,
      media_type: (cur && cur.kind) || "unknown",
      title: (cur && cur.title) || "",
      category: (cur && cur.category) || "",
    };
  }
  function onTrack(s) {
    _resetMedia();
    const cur = s && s.current;
    if (!cur) return;
    capture("media_play_start", _meta(cur));
  }
  function onTick(s) {
    const cur = s && s.current;
    if (!cur || !s.isPlaying) return;
    const dur = s.duration || (cur.duration || 0);
    if (!dur) return;
    const pct = Math.round((s.position / dur) * 100);
    if (pct >= 90 && !_reportedComplete) {
      _reportedComplete = true;
      const p = _meta(cur);
      p.duration_sec = Math.round(dur);
      capture("media_play_complete", p);
      return;
    }
    const bucket = Math.floor(pct / 25);
    if (bucket > _lastBucket && bucket < 4) {
      _lastBucket = bucket;
      const p = _meta(cur);
      p.position_sec = Math.round(s.position || 0);
      p.duration_sec = Math.round(dur);
      p.progress_pct = pct;
      capture("media_play_progress", p);
    }
  }

  function init() {
    if (_inited) return;
    _inited = true;
    _sessionId =
      window.crypto && crypto.randomUUID
        ? crypto.randomUUID()
        : "s_" + Date.now() + Math.random().toString(36).slice(2);

    // 미디어 재생 추적
    if (typeof Player !== "undefined") {
      Player.on("track", onTrack);
      Player.on("tick", onTick);
    }

    // 화면 이동 추적
    if (typeof AppState !== "undefined" && AppState.on) {
      AppState.on("activeTab", function (tabId) {
        capture("page_view", { screen: tabId });
      });
    }

    // 세션 시작
    capture("session_start", {
      screen: (typeof AppState !== "undefined" && AppState.get("activeTab")) || "home",
    });
    capture("page_view", {
      screen: (typeof AppState !== "undefined" && AppState.get("activeTab")) || "home",
    });

    // 가시성 변경 → 백그라운드 종료 / 포그라운드 재시작
    document.addEventListener("visibilitychange", function () {
      if (document.hidden) {
        capture("session_end", {});
        _flush();
      } else {
        capture("session_start", {
          screen: (typeof AppState !== "undefined" && AppState.get("activeTab")) || "home",
        });
      }
    });

    // 언로드 시 최종 플러시
    window.addEventListener("pagehide", _flush);
    window.addEventListener("beforeunload", _flush);

    // 전역 에러 비콘
    window.addEventListener("error", function (e) {
      capture("js_error", {
        message: ((e && e.message) || "").slice(0, 500),
        stack: ((e && e.error && e.error.stack) || "").slice(0, 2000),
        screen: (typeof AppState !== "undefined" && AppState.get("activeTab")) || "",
      });
    });
    window.addEventListener("unhandledrejection", function (e) {
      const r = e && e.reason;
      capture("js_error", {
        message: ("Unhandled: " + (r && r.message ? r.message : String(r))).slice(0, 500),
        screen: (typeof AppState !== "undefined" && AppState.get("activeTab")) || "",
      });
    });
  }

  return {
    init: init,
    capture: capture,
    flush: _flush,
    onTrack: onTrack,
    onTick: onTick,
    search: function (query, resultCount) {
      capture("search", { query: query, result_count: resultCount || 0 });
    },
    annotate: function (eventType, info) {
      capture(eventType, info || {});
    },
    share: function (info) {
      capture("share", info || {});
    },
  };
})();
