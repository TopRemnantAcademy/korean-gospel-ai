const cacheName = "gospel-mobile-v11";
const staticAssets = [
  "./","./index.html","./styles.css","./styles-media.css","./app.js",
  "./utils/dom.js","./utils/state.js","./utils/offline.js",
  "./components/index.js","./services/index.js","./screens/index.js","./player.js",
  "./data/bible/bible_meta.json","./data/hymns.json","./data/meditation.json","./data/sermons.json",
  "./manifest.webmanifest",
];
self.addEventListener("install",e=>{e.waitUntil(caches.open(cacheName).then(c=>c.addAll(staticAssets)));self.skipWaiting()});
self.addEventListener("activate",e=>{e.waitUntil(Promise.all([caches.keys().then(ks=>Promise.all(ks.filter(k=>k!==cacheName).map(k=>caches.delete(k)))),self.clients.claim()]))});
// network-first：在线时始终返回最新文件（确保中文化等更新立即生效），离线时回退缓存
// Z-3: 백엔드 API(타 출처) 요청은 캐싱하지 않고 항상 최신을 받는다(network-only).
//      잘못 캐시된 API 응답이 PWA 에서 구형 데이터로 서빙되는 버그 방지.
self.addEventListener("fetch",e=>{
  if(e.request.method!=="GET")return;
  const reqUrl=new URL(e.request.url);
  // 동일 출처(정적 자산)가 아니면 서비스 워커 캐시를 거치지 않음
  if(reqUrl.origin!==self.location.origin)return;
  e.respondWith(
    fetch(e.request).then(res=>{
      const copy=res.clone();
      caches.open(cacheName).then(c=>c.put(e.request,copy));
      return res;
    }).catch(()=>caches.match(e.request,{ignoreSearch:true}))
  );
});

// ── Web Push (2026-07-29 미디어 동기화) ──────────────────────────────────
// 백엔드 push_service.broadcast_media_update 가 json.dumps(payload) 로 전송.
// payload = {title, body, data:{type:"new_media", tab, items}}
self.addEventListener("push", (e) => {
  let payload = { title: "새로운 소식", body: "", data: {} };
  try {
    if (e.data) {
      const parsed = JSON.parse(e.data.text());
      payload = {
        title: parsed.title || "새로운 소식",
        body: parsed.body || "",
        data: parsed.data || parsed,
      };
    }
  } catch (_) {}
  e.waitUntil(
    self.registration.showNotification(payload.title, {
      body: payload.body,
      icon: "./icons/icon-192.png",
      badge: "./icons/badge.png",
      tag: "new_media",          // 동일 tag 알림은 교체(알림 폭탄 방지)
      renotify: false,
      data: payload.data,
    })
  );
});

self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  const data = (e.notification && e.notification.data) || {};
  const tab = (data && data.tab) || "today";
  e.waitUntil(
    (async () => {
      const all = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
      for (const c of all) {
        if ("focus" in c) {
          c.postMessage({ type: "new_media", tab, data });
          return c.focus();
        }
      }
      if (self.clients.openWindow) {
        return self.clients.openWindow("./index.html");
      }
    })()
  );
});
