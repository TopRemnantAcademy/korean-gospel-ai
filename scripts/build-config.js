/* ═══════════════════════════════════════════════════════════════════════════
   build-config — 웹(PWA) / 안드로이드(APK) 빌드 시 API 주소 + 시장별 설정 주입

   ⚠️ 중요: 이 스크립트는 소스(mobile/index.html)를 절대 수정하지 않는다.
      빌드 결과는 항상 mobile/dist/<target>/ 로 출력된다.
        web     → mobile/dist/web/      (PWA 정적 서빙용)
        android → mobile/dist/android/  (Capacitor webDir)
      → 서버(8000) · PWA(4174) · APK 빌드가同一个 소스를 공유하더라도
        빌드 산출물이 소스를 덮어쓰지 않아 서로 밟지 않는다(混淆 根本消除).

   index.html 에는 플레이스홀더가 네 개 있다:
     __GOSPEL_API_BASE__        → 백엔드 API 주소
     __GOSPEL_GOOGLE_SDK__       → Google Identity Services SDK <script> 태그 (중국은 비움)
     __GOSPEL_PORTONE_SDK__      → PortOne V2 결제 SDK <script> 태그
     __GOSPEL_PAYMENT_CHANNEL__  → 런타임 window.GOSPEL_PAYMENT_CHANNEL ('direct'|'googleplay')

   사용법:
     node scripts/build-config.js web     --api=https://api.domain.com
     node scripts/build-config.js android --api=https://api.domain.com --market=cn
     node scripts/build-config.js android --channel=googleplay   # GP 상점용: 제3자 결제 0

   --market=cn   : 중국 직분용. Google SDK 주입 안 함. 단 PortOne 은 주입(위챗/알리페이
                   해외 채널이 PortOne 에 내장 — 별도 제3자 SDK 아님). API는 CN_API_BASE.
   --market=global: 해외 배포용. Google GIS SDK + PortOne 모두 주입.
   --channel=googleplay: Google Play 상점용. PortOne SDK 완전 제거(제3자 결제 코드 0),
                   런타임 채널='googleplay' → openPayment 가 GP Billing placeholder 로 폴백.
                   (GP 정책: 제3자 결제 금지 → 물리적 격리 필수)

   환경변수 파일(.env.mobile)로도 주입 가능:
     WEB_API_BASE=...   ANDROID_API_BASE=...
     CN_API_BASE=...    GLOBAL_API_BASE=...
   ═══════════════════════════════════════════════════════════════════════════ */
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const SRC_DIR = path.join(ROOT, 'mobile');          // 소스(절대 수정 금지)
const INDEX = path.join(SRC_DIR, 'index.html');     // 소스 템플릿
const DIST_ROOT = path.join(SRC_DIR, 'dist');       // 빌드 산출물 루트

const PH_API = '__GOSPEL_API_BASE__';
const PH_GOOGLE = '__GOSPEL_GOOGLE_SDK__';
const PH_PORTONE = '__GOSPEL_PORTONE_SDK__';
const PH_CHANNEL = '__GOSPEL_PAYMENT_CHANNEL__';

const GOOGLE_SDK_TAG = '<script src="https://accounts.google.com/gsi/client" async defer></script>';
const PORTONE_SDK_TAG = '<script src="https://cdn.portone.io/v2/browser-sdk.js"></script>';

// dist 에 복사하지 않을 항목(소스 전용/불필요)
const COPY_EXCLUDE = new Set(['dist', 'node_modules', '.git']);

function loadEnvMobile() {
  const envPath = path.join(ROOT, '.env.mobile');
  const out = {};
  if (fs.existsSync(envPath)) {
    for (const line of fs.readFileSync(envPath, 'utf8').split('\n')) {
      const m = line.match(/^\s*([\w.]+)\s*=\s*(.*)\s*$/);
      if (m) out[m[1]] = m[2].replace(/^["']|["']$/g, '');
    }
  }
  return out;
}

function arg(flagName, argv) {
  const f = argv.find(a => a.startsWith(flagName + '='));
  return f ? f.slice(flagName.length + 1) : null;
}

function getApiBase(target, market, argv, env) {
  const fromFlag = arg('--api', argv);
  if (fromFlag) return fromFlag;
  if (market === 'cn') return env.CN_API_BASE || 'http://127.0.0.1:5000';   // 중국 채널 = payment-gateway(:5000)
  if (market === 'global') return env.GLOBAL_API_BASE || 'http://127.0.0.1:8000'; // 글로벌/다이렉트 = 메인 백엔드(:8000)
  // market 미지정: 타겟 기본
  if (target === 'android' && env.ANDROID_API_BASE) return env.ANDROID_API_BASE;
  if (target === 'web' && env.WEB_API_BASE) return env.WEB_API_BASE;
  return 'http://127.0.0.1:8000';
}

// 소스 템플릿(index.html)에서 플레이스홀더 4개 존재 확인.
// 소스는 git 에 의해 보존되므로 백업 불필요 — 손실 시 git checkout 으로 복구.
function readTemplate() {
  if (!fs.existsSync(INDEX)) {
    console.error('[build-config] mobile/index.html 소스 템플릿이 없습니다. git checkout mobile/index.html 후 재시도하세요.');
    process.exit(1);
  }
  const html = fs.readFileSync(INDEX, 'utf8');
  const ok = [PH_API, PH_GOOGLE, PH_PORTONE, PH_CHANNEL].every(p => html.includes(p));
  if (!ok) {
    console.error('[build-config] mobile/index.html 에 플레이스홀더(' + PH_API + '/' + PH_GOOGLE + '/' + PH_PORTONE + '/' + PH_CHANNEL +
      ')가 없습니다. 소스 템플릿이 손상되었으니 git checkout mobile/index.html 후 재시도하세요.');
    process.exit(1);
  }
  return html;
}

// 소스 디렉터리 전체를 출력 디렉터리로 복사(재귀, exclude 적용).
function copyTree(src, dest) {
  fs.mkdirSync(dest, { recursive: true });
  for (const entry of fs.readdirSync(src, { withFileTypes: true })) {
    if (COPY_EXCLUDE.has(entry.name)) continue;
    const s = path.join(src, entry.name);
    const d = path.join(dest, entry.name);
    if (entry.isDirectory()) {
      copyTree(s, d);
    } else if (entry.isFile()) {
      fs.copyFileSync(s, d);
    }
  }
}

// 단일 파일을 조건부 복사(원본 없으면 무시).
function copyIfExists(src, dest) {
  if (!fs.existsSync(src)) return;
  fs.copyFileSync(src, dest);
  console.log('[build-config] 복사: ' + path.relative(ROOT, src) + ' → ' + path.relative(ROOT, dest));
}

// 디렉터리를 조건부 복사(원본 없으면 무시). releases/ 는 gitignore 되어 있으므로 출력에도 미포함.
function copyDirIfExists(src, dest) {
  if (!fs.existsSync(src)) return;
  copyTree(src, dest);
  console.log('[build-config] 복사: ' + path.relative(ROOT, src) + ' → ' + path.relative(ROOT, dest));
}

// 안드로이드 타겟 빌드 시 채널에 따라 capacitor.config.json 의 appId 를 분리.
//   direct     → com.gospelai.app      (자체 공식사이트 직링크, PortOne 결제 포함)
//   googleplay → com.gospelai.app.play (GP 상점 전용, 제3자 결제 0 — GP 정책 준수 물리적 격리)
// GP 에는 반드시 play 패키지별도 업로드 — direct 패키지와 패키지명 충돌 금지.
function applyAndroidAppId(channel) {
  const cfgPath = path.join(ROOT, 'capacitor.config.json');
  if (!fs.existsSync(cfgPath)) return;
  const cfg = JSON.parse(fs.readFileSync(cfgPath, 'utf8'));
  const appId = channel === 'googleplay' ? 'com.gospelai.app.play' : 'com.gospelai.app';
  if (cfg.appId === appId) return; // 이미 동일 → 미변경(깨끗하게 유지)
  cfg.appId = appId;
  fs.writeFileSync(cfgPath, JSON.stringify(cfg, null, 2) + '\n', 'utf8');
  console.log('[build-config] capacitor.config.json appId → ' + appId + ' (channel=' + channel + ')');
}

// 안드로이드 타겟 빌드 시 version.json(versionCode/versionName) 을
// android/app/build.gradle 로 동기화(수동 불일치 방지). namespace/applicationId 는 미변경.
// version.json 은 저장소 루트에 위치(빌드 스크립트는 이를 정설로 읽음).
function applyVersionToGradle() {
  const verPath = path.join(ROOT, 'version.json');
  const gradlePath = path.join(ROOT, 'android', 'app', 'build.gradle');
  if (!fs.existsSync(verPath) || !fs.existsSync(gradlePath)) return;
  let v;
  try { v = JSON.parse(fs.readFileSync(verPath, 'utf8')); } catch (_) { return; }
  const code = Number(v.versionCode) || 1;
  const name = String(v.versionName || '1.0.0');
  let g = fs.readFileSync(gradlePath, 'utf8');
  g = g.replace(/versionCode\s+\d+/, 'versionCode ' + code);
  g = g.replace(/versionName\s+"[^"]*"/, 'versionName "' + name + '"');
  fs.writeFileSync(gradlePath, g, 'utf8');
  console.log('[build-config] android/app/build.gradle versionCode=' + code + ' versionName="' + name + '" (← mobile/version.json)');
}

function main() {
  const target = process.argv[2];
  if (target !== 'web' && target !== 'android') {
    console.error('Usage: node scripts/build-config.js <web|android> [--api=URL] [--market=cn|global] [--channel=direct|googleplay]');
    process.exit(1);
  }
  const rest = process.argv.slice(3);
  let market = arg('--market', rest) || 'hk';
  // hk = 香港部署（中国大陆用户可达，无需 Google 框架）:
  //   后端用香港域名，但 GIS SDK 仍注入（海外/香港 Google 框架可用）。
  //   若只想服务大陆且彻底零 Google，用 --market=cn（不注入 GIS）。
  if (market === 'hk') market = 'global';
  // 결제 채널: direct(기본) = PortOne 단일 SDK 로 한국카드+중국 위챗/알리페이 커버
  //            googleplay = GP 상점용, 제3자 결제 0 (런타임에서 GP Billing placeholder 로 폴백)
  let channel = arg('--channel', rest) || 'direct';
  if (channel !== 'direct' && channel !== 'googleplay') {
    console.error('[build-config] --channel 은 direct 또는 googleplay 만 가능합니다.');
    process.exit(1);
  }
  const env = loadEnvMobile();
  const apiBase = getApiBase(target, market, rest, env);

  // ── 안드로이드(APK) 가드: localhost/loopback API 는 실기기에서 동작 불가 ──
  // (127.0.0.1 은 기기 자신을 가리킴 + WebView 는 https 컨텍스트라 http mixed-content 도 차단)
  // 배포용 APK 를 만들 때는 반드시 공개 HTTPS 도메인을 주입해야 한다.
  if (target === 'android' && /^https?:\/\/(127\.0\.0\.1|localhost)([:/]|$)/i.test(apiBase)) {
    console.warn(
      '[build-config] ⚠️  WARNING: android 타겟의 API base가 localhost(' + apiBase + ')입니다.\n' +
      '    실기기 APK 는 백엔드에 연결할 수 없습니다. --api=https://<공개도메인> 또는 .env.mobile 의\n' +
      '    ANDROID_API_BASE/GLOBAL_API_BASE 를 실제 HTTPS 도메인으로 지정하세요.'
    );
  }

  // ── 소스를 출력 디렉터리로 복사(기존 출력은 매번 깨끗하게 덮어씀) ──
  const outDir = path.join(DIST_ROOT, target);
  try {
    fs.rmSync(outDir, { recursive: true, force: true });
  } catch (_) {
    // Windows 에서 PWA 서버(http.server)가 dist/web 을 점유 중이면 EBUSY 발생.
    // 삭제 실패해도 아래 copyTree 가 파일을 덮어쓰므로 계속 진행(구동 중 핫리로드 안전).
    console.warn('[build-config] 기존 ' + path.relative(ROOT, outDir) + ' 삭제 실패(점유 중?). 덮어쓰기로 진행합니다.');
  }
  copyTree(SRC_DIR, outDir);

  // ── 강제 업데이트 오버레이 링크 보정(숨은 버그 수정) ──
  // download.html 은 저장소 루트에 있음. 빌드 출력(mobile/dist/<target>/)에는 없으므로,
  // PWA(4174 서빙)·APK(네이티브 자산) 모두에서 `./download.html` → 404 가 됨.
  // 강제 업데이트 시 사용자가 APK 를 받을 수 없게 되므로 출력 디렉터리에 함께 복사한다.
  // download.html 내부 링크는 `./releases/flow-ai.apk` 이므로 releases/ 도 같이 복사(web 은 로컬 테스트용,
  // android 는 오프라인 자체 포함 폴백 — 운영 시 백엔드 update_url 로 호스팅 URL 지정 권장).
  copyIfExists(path.join(ROOT, 'download.html'), path.join(outDir, 'download.html'));
  copyDirIfExists(path.join(ROOT, 'releases'), path.join(outDir, 'releases'));

  // 안드로이드 빌드만: 채널별 appId 분리 + version.json 연동(GP 패키지 격리 필수).
  if (target === 'android') {
    applyAndroidAppId(channel);
    applyVersionToGradle();
  }

  let html = readTemplate();

  // ── API base 치환 ──
  html = html.replaceAll(PH_API, apiBase);

  // ── Google SDK 치환 (중국 시장은 주입 안 함) ──
  const googleTag = market === 'cn' ? '' : GOOGLE_SDK_TAG;
  html = html.replaceAll(PH_GOOGLE, googleTag);

  // ── PortOne SDK 치환 ──
  //   direct 채널: 모든 market 에 주입(cn 도 주입 — 위챗/알리페이 해외채널이 PortOne 에 내장,
  //               별도 제3자 SDK 가 아님. GP 정책 위반 아님).
  //   googleplay 채널: 완전 제거(제3자 결제 코드 0 — GP 정책 준수 물리적 격리).
  const portoneTag = channel === 'googleplay' ? '' : PORTONE_SDK_TAG;
  html = html.replaceAll(PH_PORTONE, portoneTag);

  // ── 결제 채널 치환 (런타임 window.GOSPEL_PAYMENT_CHANNEL) ──
  html = html.replaceAll(PH_CHANNEL, channel);

  // 출력 디렉터리의 index.html 에만 기록 — 소스는 그대로 보존.
  fs.writeFileSync(path.join(outDir, 'index.html'), html, 'utf8');
  console.log('[build-config] ' + target + ' / market=' + market + ' / channel=' + channel +
    ' → out=' + path.relative(ROOT, outDir) +
    ', API=' + apiBase +
    ', GoogleSDK=' + (market === 'cn' ? 'OFF(중국)' : 'ON') +
    ', PortOneSDK=' + (channel === 'googleplay' ? 'OFF(GP)' : 'ON') +
    ', PaymentChannel=' + channel);
}

main();
