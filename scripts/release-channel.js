/* ═══════════════════════════════════════════════════════════════════════════
   release-channel — 채널별 APK 아카이브 관리

   빌드된 APK 를 releases/<channel>/ 로 이동·등록하고 MANIFEST.json 을 갱신한다.
   (중국 채널은 payment-gateway:5000 을 가리키도록 build-config.js --market=cn 사용)

   사용법:
     node scripts/release-channel.js --channel=global --apk=build/output.apk --version-name=1.0.1 --version-code=2
     node scripts/release-channel.js --channel=china  --apk=build/output.apk --version-name=1.0.1 --version-code=2

   규칙:
     - channel ∈ global | googleplay | china
     - 파일은 반드시 releases/<channel>/ 로 복사됨 (원본 위치 무관)
     - MANIFEST.json.releases 배열에 항목 추가 (중복 versionCode 는 거부)
   ═══════════════════════════════════════════════════════════════════════════ */
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const RELEASES = path.join(ROOT, 'releases');
const MANIFEST = path.join(RELEASES, 'MANIFEST.json');

function arg(name, argv) {
  const f = argv.find(a => a.startsWith(name + '='));
  return f ? f.slice(name.length + 1) : null;
}

function main() {
  const argv = process.argv.slice(2);
  const channel = arg('--channel', argv);
  const apk = arg('--apk', argv);
  const versionName = arg('--version-name', argv) || '1.0.0';
  const versionCode = Number(arg('--version-code', argv) || '1');

  if (!['global', 'googleplay', 'china'].includes(channel)) {
    console.error('[release-channel] --channel 은 global | googleplay | china 만 가능');
    process.exit(1);
  }
  if (!apk || !fs.existsSync(apk)) {
    console.error('[release-channel] --apk=<경로> 가 필요하거나 파일이 없습니다: ' + apk);
    process.exit(1);
  }

  const destDir = path.join(RELEASES, channel);
  fs.mkdirSync(destDir, { recursive: true });
  const baseName = path.basename(apk);
  const dest = path.join(destDir, baseName);
  fs.copyFileSync(apk, dest);
  console.log('[release-channel] 복사: ' + apk + ' → ' + path.relative(ROOT, dest));

  // MANIFEST 갱신
  const manifest = JSON.parse(fs.readFileSync(MANIFEST, 'utf8'));
  const channelMeta = manifest.channels[channel];
  if (manifest.releases.some(r => r.channel === channel && r.versionCode === versionCode)) {
    console.error('[release-channel] ⚠️  versionCode ' + versionCode + ' 는 ' + channel + ' 채널에 이미 존재합니다. 버전을 올리세요.');
    process.exit(1);
  }
  manifest.releases.push({
    channel,
    versionName,
    versionCode,
    file: path.relative(ROOT, dest).replace(/\\/g, '/'),
    backend: channel === 'china' ? 'http://127.0.0.1:5000' : 'http://127.0.0.1:8000',
    releasedAt: new Date().toISOString(),
    notes: channelMeta ? channelMeta.label : channel
  });
  fs.writeFileSync(MANIFEST, JSON.stringify(manifest, null, 2) + '\n', 'utf8');
  console.log('[release-channel] MANIFEST.json 갱신 완료: ' + channel + ' v' + versionName + ' (code ' + versionCode + ')');
}

main();
