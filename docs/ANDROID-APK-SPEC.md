# 安卓 APK 极致落地规格书（ANDROID-APK-SPEC）

> 配套文档：`MULTI-PLATFORM-PLAN.md`（总体分阶段计划）。
> 本文档是安卓客户端的**工程级实现规格**：精确到文件、方法、参数、命令、验证与回滚。
> 适用范围：国内版（`cn`，包名 `com.gospelai.app`）、Google Play 版（`googleplay`，包名 `com.gospelai.app.play`）。
> 用户硬约束（原话）：**推送只做 Google FCM**；**后台播放一定要做，不管什么版本**。

---

## 0. 目标定义（"极致"的具体含义）

| 维度 | 极致标准 |
|---|---|
| 后台播放 | App 退到后台 / 锁屏 / 杀掉 WebView 进程后，音频**持续播放**；通知栏 + 锁屏有播放/暂停/±15s/上下首控制 |
| 推送 | Play 版经 FCM 真实送达（非"订阅了收不到"） |
| 启动体验 | Splash 1.5s + 无白屏；首屏 API 失败有离线兜底 |
| 性能 | 冷启动 < 2.5s；滚动 60fps；音频播放期间无主线程长任务卡顿 |
| 兼容 | minSdk 22（Android 5.1）到 target 34；覆盖小米/华为/OPPO/vivo/Samsung 主流机型 |
| 构建 | 一条命令产出 cn-debug / play-release-aab，参数全由 `build-config.js` 注入，零手工改码 |
| 包体 | 启用 R8 + 资源压缩；AAB < 25MB（Play 限制友好） |
| 上架 | Play 版走 AAB + Play 签名；国内版走自有分发（官网/应用宝占位） |

---

## 1. 后台播放：根因诊断与正确架构

### 1.1 现状根因（已读码确认，非猜测）

现有原生层 `android/app/src/main/java/com/gospelai/app/`：
- `MediaSessionPlugin.java`：Capacitor 插件，`@PluginMethod` 暴露 `startService/stopService/notifyState/updateMetadata`；实现 `MediaPlaybackService.PlaybackController`，把原生意图经 `evaluateJavascript` 调回 `window.Player._nativePlay()` 等。
- `MediaPlaybackService.java`：前台 Service，`MediaSessionCompat` + 通知栏 `MediaStyle` + 音频焦点。**第 32 行注释原文**：*"실제 오디오 디코딩은 웹의 `<audio>` 가 담당"*（实际音频解码由 Web 的 `<audio>` 负责）。

**结论（根因）**：原生服务**只持有 MediaSession 和通知 UI**，真正出声的 `<audio>` 跑在 **WebView 的 JS 里**。当 App 退后台/锁屏，Android 对 WebView 进程降权/挂起，JS 的 `<audio>` 被暂停 → 服务还在、通知还在、锁屏控件还在，但**无声**。这正是用户遇到的"后台不播"。

> 误区澄清：现有方案试图用"前台服务 + `mediaPlayback` 类型"保活 WebView 进程。但 Android 8+ 对后台 WebView 的渲染/网络仍有严格限制（尤其 MIUI/EMUI 的进程管理），保活不可靠。**唯一可靠方案是把音频解码本身移到原生。**

### 1.2 目标架构（WebView 仅做 UI + 指令，原生层真正播放）

```
┌─────────────────────────────────────────────────────────────┐
│ WebView (mobile/player.js, JS UI)                            │
│  - 渲染进度条/封面/歌词/控制按钮                               │
│  - 调用桥接: NativePlayer.play(url) / pause() / seek(ms)      │
│  - 监听桥接事件: onState / onProgress / onEnded / onError     │
└───────────────┬─────────────────────────────────────────────┘
                │ Capacitor Plugin bridge (evaluateJavascript ↔ native calls)
┌───────────────▼─────────────────────────────────────────────┐
│ MediaPlaybackService (原生, 真正持有播放器)                   │
│  - ExoPlayer (或 MediaPlayer) 实例 → 解码/输出音频            │
│  - MediaSessionCompat → 锁屏/通知栏控件 + 媒体按键            │
│  - AudioFocus 管理（来电/其他 App 抢占→暂停）                 │
│  - 前台服务 (foregroundServiceType=mediaPlayback)             │
│  - 通知栏 MediaStyle + 播放/暂停/±15s/上下首 Action           │
└─────────────────────────────────────────────────────────────┘
```

**关键改动**：`MediaPlaybackService` 不再只做"遥控器"，而是**真正创建并控制 `ExoPlayer`**；`MediaSessionPlugin.PlaybackController` 的 `onPlay/onPause/...` 改为**直接命令原生 `ExoPlayer`**，而非回传 JS。WebView 中的 `<audio>` 仅作为**网页端（PWA/浏览器）回退**使用。

### 1.3 为什么选 ExoPlayer（而非 MediaPlayer）

| 项 | MediaPlayer | ExoPlayer（推荐） |
|---|---|---|
| 流式/分段 | 弱 | 强（支持 HLS/DASH/渐进式，匹配现有流媒体接口） |
| 后台保活 | 需自行接 Service | 同为 Service 持有，但 API 更完整 |
| 音频焦点/元数据 | 手动 | 与 MediaSession 配合成熟 |
| 边下边播/缓存 | 难 | 内置（`CacheDataSource`） |
| 维护状态 | 系统级，稳定但功能旧 | Google 官方维护，功能活跃 |

> 现有播放器已支持"离线下载 + 流式"。ExoPlayer 的 `ProgressiveMediaSource` + `CacheDataSource` 可直接复用该模型。

---

## 2. 原生层改造规格（逐文件）

### 2.1 `MediaPlaybackService.java`（核心重写）

**现有**：持有 MediaSession + 通知，无播放器实例。
**目标**：持有 `ExoPlayer`，实现真正的播放/暂停/seek/上下首。

新增依赖与字段：
```java
import androidx.media3.exoplayer.ExoPlayer;       // 或 com.google.android.exoplayer2.ExoPlayer
import androidx.media3.common.MediaItem;
import androidx.media3.datasource.CacheDataSource;
import androidx.media3.datasource.DefaultHttpDataSource;
import androidx.media3.datasource.cache.SimpleCache;
import androidx.media3.exoplayer.source.ProgressiveMediaSource;

private ExoPlayer player;          // 真正播放器
private SimpleCache cache;         // 离线/边下边播缓存
```

生命周期与播放控制（伪代码骨架，落地时补全）：
```java
@Override public void onCreate() {
  super.onCreate();
  // 现有: mediaSession / audioFocus / notifChannel 初始化（保留）
  player = new ExoPlayer.Builder(this).build();
  player.addListener(new Player.Listener() {
    @Override public void onPlaybackStateChanged(int state) {
      // STATE_ENDED → 通知 JS 播下一首 / onEnded
      // 更新通知进度 / MediaSession 进度
    }
    @Override public void onIsPlayingChanged(boolean playing) {
      rebuildNotification(playing);      // 通知栏播放/暂停图标切换
    }
  });
}

/** JS 调用: 播放指定 URL（支持流式 + 缓存） */
public void play(String url, long startMs) {
  MediaItem item = MediaItem.fromUri(url);
  ProgressiveMediaSource src = new ProgressiveMediaSource.Factory(
      new CacheDataSource.Factory().setCache(cache)
          .setUpstreamDataSourceFactory(new DefaultHttpDataSource.Factory())).createMediaSource(item);
  player.setMediaSource(src);
  player.prepare();
  player.seekTo(startMs);
  player.play();
  // 起前台服务 + 通知
}

public void pause() { player.pause(); rebuildNotification(false); }
public void resume() { player.play(); rebuildNotification(true); }
public void seekTo(long ms) { player.seekTo(ms); }
public void seekRelative(long deltaMs) { player.seekTo(player.getCurrentPosition() + deltaMs); }
public long getPosition() { return player.getCurrentPosition(); }
public long getDuration() { return player.getDuration(); }
```

`PlaybackController`（来自 `MediaSessionPlugin`）改为指挥原生 `player`：
```java
// 之前: sController.onPlay() → evaluateJavascript("window.Player._nativePlay()")
// 之后: 直接 this.play(...) / pause() / seekTo()
```
但需保留"JS → 原生"的指令通道（`MediaSessionPlugin` 暴露 `play/pause/seek/next/prev` 给 JS），以及"原生 → JS"的事件回传（`onProgress` 每 1s 调 `window.Player._onNativeProgress(ms,dur)`，`onEnded` 调 `window.Player._onNativeEnded()`）。

新增 Intent Action：`ACTION_PLAY_URL`（带 `url` + `position` extra），`MediaSessionPlugin.play(url)` 经此启动/命令 Service。

**前台服务**：保留现有 `ServiceCompat.startForeground(..., FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK)`。注意：ExoPlayer 在后台播放时，Service 必须处于前台（已有），否则 Android 12+ 抛 `MissingForegoundServiceTypeException`。

### 2.2 `MediaSessionPlugin.java`（桥接扩展）

现有 5 个 `@PluginMethod`（`startService/stopService/notifyState/updateMetadata`）+ `PlaybackController` 回调。
**新增方法**（供 JS 调用）：
```java
@PluginMethod public void play(PluginCall call) {
  String url = call.getString("url"); long pos = call.getLong("position", 0L);
  Intent i = new Intent(getContext(), MediaPlaybackService.class);
  i.setAction(MediaPlaybackService.ACTION_PLAY_URL);
  i.putExtra("url", url); i.putExtra("position", pos);
  getContext().startService(i); call.resolve();
}
@PluginMethod public void pause(PluginCall call)   { /* → ACTION_PAUSE */ }
@PluginMethod public void resume(PluginCall call)  { /* → ACTION_PLAY (resume) */ }
@PluginMethod public void seek(PluginCall call)    { long ms=call.getLong("position",0L); /* → ACTION_SEEK */ }
@PluginMethod public void seekRelative(PluginCall call) { long d=call.getLong("delta",0L); /* → ACTION_FWD/RWD */ }
@PluginMethod public void next(PluginCall call)    { /* → ACTION_NEXT */ }
@PluginMethod public void prev(PluginCall call)    { /* → ACTION_PREV */ }
@PluginMethod public void getState(PluginCall call){ /* 返回 position/duration/playing */ }
```
**新增事件回传**（Service → WebView）通过 `evaluateJavascript`：
- `window.Player._onNativeProgress(posMs, durMs)`（1s 心跳）
- `window.Player._onNativeState(playing)`
- `window.Player._onNativeEnded()`
- `window.Player._onNativeError(code, msg)`

`PlaybackController` 的 `onPlay/onPause/...` 改为直接调用 Service 的 `player`（不再回传 JS），避免"双重控制"循环。

### 2.3 `AndroidManifest.xml`（核对项，基本已就绪）

现有已声明：
```xml
<service android:name=".MediaPlaybackService"
         android:exported="false"
         android:foregroundServiceType="mediaPlayback" />
<uses-permission android:name="android.permission.FOREGROUND_SERVICE" />
<uses-permission android:name="android.permission.FOREGROUND_SERVICE_MEDIA_PLAYBACK" />
<uses-permission android:name="android.permission.POST_NOTIFICATIONS" />
<uses-permission android:name="android.permission.INTERNET" />
```
**需补充**（若 ExoPlayer 需网络/存储）：
- `android.permission.WAKE_LOCK`（可选，ExoPlayer 有 `setWakeMode`，建议用 `MediaSession` + `WakeLock` 防 CPU 休眠断播；或依赖 `ForegroundService` 已足够）
- 若走缓存到外部存储：`READ_EXTERNAL_STORAGE`（API<33 需要；建议缓存放 `getCacheDir()` 免权限）
- ExoPlayer 依赖通过 Gradle 引入（见 2.5）

### 2.4 `MainActivity.java`（无需改）

现有已 `registerPlugin(MediaSessionPlugin.class)` + 运行时请求 `POST_NOTIFICATIONS`。保持不变。

### 2.5 Gradle 依赖

`android/app/build.gradle` 的 `dependencies` 新增（用 `androidx.media3` 官方包）：
```gradle
// ExoPlayer (Media3)
implementation "androidx.media3:media3-exoplayer:1.3.1"
implementation "androidx.media3:media3-common:1.3.1"
implementation "androidx.media3:media3-datasource:1.3.1"
implementation "androidx.media3:media3-datasource-cache:1.3.1"
implementation "androidx.media3:media3-session:1.3.1"   // MediaSession 兼容层（可选，现有用 androidx.media 亦可）
```
> 版本号以 `androidx.media3` 当前稳定版为准（落地时查 Maven 最新 1.x）。若项目已用旧 `com.google.android.exoplayer2`，则沿用其版本避免冲突——**先 `grep` 现有依赖确认**。

---

## 3. JS 播放器统一抽象层（`mobile/player.js`）

### 3.1 设计原则

- **单一 `Player` 对象**，内部有 `backend` 枚举：`'web'`（HTML5 `<audio>`，用于浏览器 PWA）或 `'native'`（Capacitor 桥接，用于 APK/AAB）。
- 启动时检测：`const useNative = !!window.Capacitor && Capacitor.isNativePlatform()`。
- 对外暴露**统一接口**，UI 不感知后端差异：`play(track)/pause()/resume()/seek(sec)/seekRelative(sec)/next()/prev()/getState()`。
- 事件总线：`Player.on('progress'|'state'|'ended'|'error', cb)`。

### 3.2 原生后端实现要点

```js
const NativePlayer = {
  play(track, startSec=0) {
    Capacitor.Plugins.MediaSession.play({ url: track.audioUrl, position: startSec*1000 });
  },
  pause()  { Capacitor.Plugins.MediaSession.pause(); },
  resume() { Capacitor.Plugins.MediaSession.resume(); },
  seek(sec){ Capacitor.Plugins.MediaSession.seek({ position: sec*1000 }); },
  seekRelative(d){ Capacitor.Plugins.MediaSession.seekRelative({ delta: d*1000 }); },
  next()   { Capacitor.Plugins.MediaSession.next(); },
  prev()   { Capacitor.Plugins.MediaSession.prev(); },
};

// 原生 → JS 事件（由 MediaSessionPlugin 经 evaluateJavascript 调用）
window.Player._onNativeProgress = (posMs, durMs) => bus.emit('progress', {pos:posMs/1000, dur:durMs/1000});
window.Player._onNativeState    = (playing) => bus.emit('state', {playing});
window.Player._onNativeEnded    = () => handleEnded();   // 自动下一首逻辑
window.Player._onNativeError    = (code,msg) => bus.emit('error', {code,msg});
```

### 3.3 现有 `_native*` 钩子的去留

现有 `player.js` 第 559-563 行定义了 `window.Player._nativePlay/Pause/SeekTo/Next/Prev`，这些是**被原生回调的旧入口**（原生只做遥控时）。改造后：
- 删除"原生 → 回传 JS 再控制 `<audio>`"的回路（那是根因）。
- 改为"JS → 原生指令"（见 3.2）+ "原生 → JS 事件"（见 3.2 回调）。
- 保留 `_onNativeEnded` 里的"自动播下一首"业务逻辑（这是 JS 侧该有的智能，原生只报 ended）。

### 3.4 EQ / A-B 循环 / 睡眠定时器 / 离线下载 的兼容

- **EQ（WebAudio BiquadFilter）**：仅网页端可用。原生端 ExoPlayer 自带 `Equalizer`/`audioSessionId` 可接 `android.media.audiofx`，但**本期不强制**——EQ 在原生端可标记为"网页专属功能"，或在原生端用 ExoPlayer 的 `AudioProcessor` 链实现简易增益（后续增强）。
- **A-B 循环 / 睡眠定时器**：纯 JS 逻辑（定时 seek / 定时 pause），与原生播放解耦，无需改。
- **离线下载**：现有下载的是音频文件到本地；原生端播放时若 URL 为本地 `file://` 或 `content://`，ExoPlayer 用 `FileDataSource` 加载即可（替换 `DefaultHttpDataSource`）。需 `MediaSessionPlugin.play` 支持 `isLocal` 标志。

---

## 4. 推送：FCM 完整接入（仅 Play 版）

### 4.1 范围

- **仅 `googleplay` 渠道**（`--channel=googleplay`，包名 `com.gospelai.app.play`）。
- **cn 版不做推送**（零 Google 无 FCM）。
- 一家 FCM 覆盖所有安卓机型（Play 用户均在 Google 生态）。

### 4.2 前端（`mobile/` + `android/`）

1. Firebase 控制台建项目 → 添加 Android 应用（包名 `com.gospelai.app.play`）→ 下载 `google-services.json`。
2. `google-services.json` **仅放入 Play 构建**（通过 `build-config.js` 在 `--channel=googleplay` 时复制到 `android/app/`；cn 构建不复制）。
3. `android/build.gradle` 顶层加 `classpath 'com.google.gms:google-services:4.4.x'`；`android/app/build.gradle` 加 `apply plugin: 'com.google.gms.google-services'` + `implementation 'com.google.firebase:firebase-messaging:24.x'` + `@capacitor/push`。
4. `mobile/package.json` 或根 `package.json` 加 `@capacitor/push`（仅 Play 配置注入）。
5. JS 在 `Capacitor.isNativePlatform()` 且渠道为 play 时：初始化 `@capacitor/push`，`PushNotifications.register()` → 拿 FCM token → `POST /mobile/push/subscribe {platform:'android', token:'firebase:'+token, channel:'googleplay'}`。

### 4.3 后端（`backend/app/services/push_service.py`）

- 当前 `_send()` 遇 `firebase:` token 直接 `skipped`（firebase-admin 未实现）。
- 改为：`pip install firebase-admin`；读 `FIREBASE_CREDENTIALS`（JSON 路径，Play 版 Firebase 项目私钥）；`messaging.send({token, notification, data})`。
- 加环境变量到 `.env` / `docker-compose.prod.yml`：`FIREBASE_CREDENTIALS=/secrets/firebase-play.json`。
- 健壮性：FCM 失败（token 失效）→ 标记订阅无效，避免反复重试。

### 4.4 构建隔离（关键）

`build-config.js` 增加：当 `--channel=googleplay` 时
- 复制 `google-services.json` 到 `android/app/`
- 在生成的 `android/app/build.gradle` 注入 `google-services` 插件（或预置条件块，靠文件存在与否启用）
- cn 构建**不复制**，且 `google-services.json` 不存在时 Gradle 不启用该插件（用 `apply plugin` 条件判断或 flavor）。

> 防坑：若 `google-services.json` 存在于 cn 构建，Firebase 会尝试初始化但无 Google 服务 → 崩溃。必须**文件级隔离**。

---

## 5. 构建 / 签名 / 多渠道矩阵

### 5.1 构建命令（已存在，核对）

```bash
# 网页
npm run build:web -- --api=https://<tunnel>.trycloudflare.com

# cn 版 APK (debug 自测)
npm run build:apk-debug -- --market=cn --api=https://<tunnel>.trycloudflare.com
# 等价: npm run android:config:cn && cap sync android && cd android && gradlew assembleDebug

# Play 版 AAB (release 上架)
npm run build:aab-release -- --channel=googleplay --api=https://<tunnel>.trycloudflare.com
# 等价: npm run android:config:play && cap sync android && SET JAVA_HOME=... && gradlew bundleRelease
```

### 5.2 双包名 / 双渠道参数表

| 维度 | cn（国内） | googleplay（Play） |
|---|---|---|
| 包名 | `com.gospelai.app` | `com.gospelai.app.play` |
| build-config | `--market=cn` | `--channel=googleplay` |
| Google SDK | 不注入 | 注入（Firebase + GIS） |
| PortOne | 注入（微信/支付宝） | 不注入（去第三方支付） |
| 推送 | 不做（无 FCM） | FCM（firebase-admin） |
| 后台播放 | 原生 ExoPlayer | 原生 ExoPlayer（同） |
| 签名 | 自有 keystore | Play 签名（上传密钥 + Play 管理） |
| 分发 | 官网/应用宝/自有 | Google Play Console |

### 5.3 签名配置

**cn 版（自有分发）**：
- 生成 keystore：`keytool -genkey -v -keystore gospel-cn.keystore -alias gospel-cn -keyalg RSA -keysize 2048 -validity 10000`
- `android/app/build.gradle` 的 `signingConfigs.release` 配 `storeFile/storePassword/keyAlias/keyPassword`（从 `gradle.properties` 或环境变量读，勿硬编码进 git）。
- 输出：`app-release.apk`（对齐 + 签名）。

**Play 版（Play 签名）**：
- 本地用 **upload key**（与 cn 不同别名），输出 AAB。
- Play Console 第一次上传时选"Play 管理密钥"（推荐），之后每次上传 AAB，Play 重新签名分发。
- `play` 包名独立，可与 cn 共存同一 Console 账户的不同应用条目。

### 5.4 包体优化（极致要求）

`android/app/build.gradle`：
```gradle
buildTypes {
  release {
    minifyEnabled true
    shrinkResources true
    proguardFiles getDefaultProguardFile('proguard-android-optimize.txt'), 'proguard-rules.pro'
    // ExoPlayer / Capacitor 需保留规则（见 5.5）
  }
}
```
`proguard-rules.pro` 至少保留：
```
-keep class com.gospelai.app.** { *; }            // 原生插件
-keep class androidx.media3.** { *; }             // ExoPlayer
-keep class com.getcapacitor.** { *; }
```

### 5.5 多渠道资源隔离（防踩）

- `capacitor.config.json` 中 `appId` 是模板；`build-config.js` 需按渠道改 `appId`（`com.gospelai.app` vs `com.gospelai.app.play`），否则两包冲突、且 Play 拒收。
- **确认 `build-config.js` 是否已处理 play 包名**——若仅改 `applicationId` 而未改 `capacitor.config.json` 的 `appId`，Capacitor `cap sync` 会覆盖。需双写：`capacitor.config.json` 的 `appId` 与 `android` 的 `applicationId` 同步。

---

## 6. 验证清单（逐条可勾选）

### 6.1 后台播放（cn + play 都要过）

- [ ] 播放中按 Home → 音频**不中断**；下拉通知栏见播放控件
- [ ] 锁屏（电源键）→ 锁屏界面显示封面/标题 + 播放/暂停/±15s/上下首
- [ ] 蓝牙/有线耳机按键 → 播放/暂停/上下首生效
- [ ] 来电/其他 App 抢音频焦点 → 自动暂停；挂断后不自动抢回（符合系统惯例）
- [ ] 杀掉 WebView（开发者选项"停止应用"）→ 音频**仍播**（证明走原生 ExoPlayer，非 WebView）
- [ ] 后台播放 10 分钟后 → 仍播（验证前台服务未被系统回收，尤其小米/华为）
- [ ] 切歌（next/prev）→ 原生无缝切换，通知栏更新标题
- [ ] 睡眠定时器到点 → 原生 `pause()`，通知栏变暂停态
- [ ] A-B 循环 → JS 定时 `seekRelative` 在原生端生效

### 6.2 推送（仅 play）

- [ ] 真机 Play 构建安装 → 首次启动注册 FCM，后端收到 `firebase:` 订阅
- [ ] 后端 `push_scheduler` / 手动触发 → 真机收到通知（即使 App 杀掉）
- [ ] 点击通知 → 打开 App 并跳转对应内容
- [ ] cn 构建**不**请求 FCM、无 Firebase 初始化崩溃

### 6.3 构建/兼容

- [ ] `assembleDebug` (cn) / `bundleRelease` (play) 均成功，无 proguard 崩溃
- [ ] minSdk 22 机型（Android 5.1）可装可播
- [ ] target 34 机型（Android 14）通知权限弹窗正常，播放不被前台服务限制拦截
- [ ] AAB < 25MB（否则 Play 警告，非阻断）

---

## 7. 逐文件改动清单（Checklist）

| 文件 | 改动 |
|---|---|
| `android/app/src/main/java/com/gospelai/app/MediaPlaybackService.java` | 引入 ExoPlayer；`play/pause/seek/seekRelative/getState` 真正控制播放器；`onPlaybackStateChanged` 回传 JS；`ACTION_PLAY_URL` 处理 |
| `android/app/src/main/java/com/gospelai/app/MediaSessionPlugin.java` | 新增 `play/pause/resume/seek/seekRelative/next/prev/getState` 方法；事件回传 `_onNativeProgress/_onNativeState/_onNativeEnded/_onNativeError`；`PlaybackController` 改指挥原生 player |
| `android/app/src/main/AndroidManifest.xml` | 核对前台服务类型/权限（已齐）；按需加 WAKE_LOCK |
| `android/app/build.gradle` | 加 ExoPlayer 依赖；签名配置；`minifyEnabled/shrinkResources`；play 渠道 `google-services` 插件（条件） |
| `android/build.gradle` | 顶层 `google-services` classpath（play 用） |
| `android/app/google-services.json` | 仅 Play 构建由 `build-config.js` 复制 |
| `mobile/player.js` | 加 `NativePlayer` 后端；`backend` 检测；事件总线；`_onNative*` 回调；离线本地 URL 支持 |
| `mobile/package.json`（或根） | 加 `@capacitor/push`（play 注入） |
| `scripts/build-config.js` | play 渠道复制 `google-services.json` + 注入包名 `com.gospelai.app.play` + 启用 Firebase 构建块；cn 排除 |
| `backend/app/services/push_service.py` | `_send()` firebase 分支真实实现（firebase-admin） |
| `backend/` `.env` / `docker-compose.prod.yml` | `FIREBASE_CREDENTIALS` 变量 |
| `proguard-rules.pro`（新建/补） | 保留 ExoPlayer/Capacitor/原生插件 |

---

## 8. 风险矩阵与回滚

| 风险 | 等级 | 触发 | 缓解 / 回滚 |
|---|---|---|---|
| ExoPlayer 与现有 `androidx.media` 冲突 | 中 | 引入 media3 | 统一用 `androidx.media3.session` 替代旧 `androidx.media`，或沿用旧 exoplayer2 版本 |
| 原生播放后 JS 进度不同步 | 中 | 事件回传丢失 | `_onNativeProgress` 心跳 1s 保底；断联时 JS 周期性 `getState()` 拉取 |
| Play 版 Firebase 初始化崩溃（cn 误带） | 高 | 文件隔离失效 | `build-config.js` 严格按渠道复制；CI 校验 `google-services.json` 不存在于 cn 产物 |
| 前台服务被 MIUI/EMUI 杀 | 中 | 国产 ROM 激进管理 | 引导用户"锁定后台/允许自启动"；`START_STICKY` + 通知常驻；必要时接厂商保活 SDK（后续） |
| proguard 误删原生桥 | 中 | release 崩溃 | `proguard-rules.pro` 显式 keep；release 先本地 `assembleRelease` 自测再上架 |
| 双包名冲突 | 高 | `appId` 未同步 | `build-config.js` 同时改 `capacitor.config.json.appId` 与 `applicationId` |

**回滚策略**：每个文件改动独立 commit；若原生播放引入回归，可 `git revert` 该文件回退到"仅 WebView 播放"旧状态（不影响其他模块）。ExoPlayer 依赖以 `build.gradle` 一处开关控制，回退即注释依赖 + 恢复旧 `MediaPlaybackService`。

---

## 9. 执行顺序建议（与 MULTI-PLATFORM-PLAN 阶段对齐）

1. **阶段 0 之后、阶段 2 之前**：本规格的"原生播放层"（§2）+ "JS 抽象层"（§3）先行落地，因它是 cn/play 共同硬需求。
2. **阶段 2（cn 出包）**：验证 §6.1 后台播放全部用例（cn 端）。
3. **阶段 3（play 出包）**：FCM（§4）+ 后台播放在 play 端验证（§6.1 + §6.2）+ AAB 上架（§5.3）。
4. 包体优化（§5.4）放在阶段 3 release 前最后做，避免 debug 期 proguard 干扰排查。

---

## 10. 待确认（非阻塞，阶段 2 落地时定）

- **ExoPlayer 版本**：落地时查 `androidx.media3` 最新稳定版；先 `grep` 现有 `android/app/build.gradle` 是否已有 exoplayer2 依赖避免重复。
- **EQ 在原生端**：本期是否要求原生 EQ？默认"网页专属"，原生端后续增强。如必须，用 ExoPlayer `AudioProcessor` 链（增加工作量，单列）。
- **本地通知（cn 触达）**：`@capacitor/local-notifications` 是否已在依赖？如未加，阶段 2 补（轻量，零外部账号）。
