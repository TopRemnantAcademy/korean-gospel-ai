/* ═══════════════════════════════════════════════════════════════════════════
   publish-apk — 构建好的 APK 复制到官网下载目录(releases/)供直链分发
   ───────────────────────────────────────────────────────────────────────────
   官网分发流程（不依赖 Google Play）：
     1) npm run build:apk-release   (或 build:apk-debug 测试)
     2) npm run publish:web         → 复制到 releases/flow-ai.apk
     3) 把 releases/ 整体部署到你的官网（香港节点），访问 /download.html 即可下载
        (download.html 现位于 releases/ 同级的官网静态目录，或单独部署)

   用法:
     node scripts/publish-apk.js                # 复制最新 APK → releases/flow-ai.apk
     node scripts/publish-apk.js --abi=arm64-v8a # 同时输出带架构名的副本(供分流)
   ═══════════════════════════════════════════════════════════════════════════ */
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const ANDROID_OUT = path.join(ROOT, 'android', 'app', 'build', 'outputs', 'apk');
const RELEASE_DIR = path.join(ROOT, 'releases');
const ABI = process.argv.find(a => a.startsWith('--abi='))?.slice(6);

function findApk() {
  // 优先 release，其次 debug
  const variants = ['release', 'debug'];
  for (const v of variants) {
    const dir = path.join(ANDROID_OUT, v);
    if (fs.existsSync(dir)) {
      const files = fs.readdirSync(dir).filter(f => f.endsWith('.apk'));
      if (files.length) return path.join(dir, files[0]);
    }
  }
  return null;
}

function main() {
  const src = findApk();
  if (!src) {
    console.error('[publish-apk] APK 를 찾을 수 없습니다. 먼저 빌드하세요:\n' +
      '  npm run build:apk-debug  또는  npm run build:apk-release');
    process.exit(1);
  }
  if (!fs.existsSync(RELEASE_DIR)) fs.mkdirSync(RELEASE_DIR, { recursive: true });

  const outMain = path.join(RELEASE_DIR, 'flow-ai.apk');
  fs.copyFileSync(src, outMain);
  console.log('[publish-apk] ' + path.basename(src) + ' → releases/flow-ai.apk');

  if (ABI) {
    const outAbi = path.join(RELEASE_DIR, `flow-ai-${ABI}.apk`);
    fs.copyFileSync(src, outAbi);
    console.log('[publish-apk] → releases/flow-ai-' + ABI + '.apk');
  }
  console.log('[publish-apk] 완료. releases/ 를官网(香港节点)에 배포 후 /download.html 에서 다운로드 가능.');
}

main();
