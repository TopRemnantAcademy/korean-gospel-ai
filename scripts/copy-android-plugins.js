/* ═══════════════════════════════════════════════════════════════════════════
   copy-android-plugins — cap add android 후 네이티브 플러그인 복사
   integration/android/FontKeyPlugin.java 등을 android/app/src/main/java/com/gospelai/app/ 로 복사
   ═══════════════════════════════════════════════════════════════════════════ */
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const SRC = path.join(ROOT, 'mobile', 'integration', 'android');
const DST = path.join(ROOT, 'android', 'app', 'src', 'main', 'java', 'com', 'gospelai', 'app');

function copyRecursive(src, dst) {
  if (!fs.existsSync(src)) return;
  const stat = fs.statSync(src);
  if (stat.isDirectory()) {
    if (!fs.existsSync(dst)) fs.mkdirSync(dst, { recursive: true });
    for (const f of fs.readdirSync(src)) copyRecursive(path.join(src, f), path.join(dst, f));
  } else {
    fs.copyFileSync(src, dst);
    console.log('[copy-android-plugins] ' + path.relative(ROOT, dst));
  }
}

if (!fs.existsSync(path.join(ROOT, 'android'))) {
  console.error('[copy-android-plugins] android/ 프로젝트가 없습니다. 먼저 `npm run add:android` 를 실행하세요.');
  process.exit(1);
}
copyRecursive(SRC, DST);
console.log('[copy-android-plugins] 완료. Android Studio 에서 MainActivity 에 플러그인 등록 확인 필요.');
