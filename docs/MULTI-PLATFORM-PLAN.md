# Gospel AI — 多端架构详细实施计划（安卓优先 · 事实驱动版）

> 本文档**仅规划，不修改任何代码**。所有结论均基于对 `C:\Desktop\korean-gospel-ai` 真实代码的阅读核实，非假设。
> 权威仓库：`korean-gospel-ai`（Gospel AI 唯一仓库；`madang-studio` 是无关视频项目，已排除）。
> 最后更新：2026-08-19，决策已闭环。

---

## 0. 已核实的真实现状（关键事实，规划的全部基础）

### 0.1 技术栈与架构
| 层 | 真实情况（读码确认） |
|---|---|
| 后端 | `backend/app`（FastAPI）+ Qdrant + KURE/bge-m3 嵌入 + Gemini/DeepSeek fallback。引擎 `search_v4.AdvancedSearchEngine`。数据集 `data/*.jsonl`（sermons/bible/hymns/…）。 |
| 移动端 | `mobile/`（原生 JS PWA，**6 tab**：Bible / Hymns / Sermon·Word / Meditation·Today / Chat / Settings）。同一份源码经 Capacitor 打包成 Android APK。 |
| 安卓壳 | `android/` 已存在（Capacitor 工程）。`capacitor.config.json` `server.url=null` → **APK 内置静态资源**，运行时经 `GOSPEL_API_BASE`（build 注入）连后端。 |
| 构建 | `scripts/build-config.js` 已支持三市场 + 双包名：<br>— `--market=cn`：零 Google SDK，API 走 `CN_API_BASE`（payment-gateway :5000）<br>— `--market=global`/`hk`（`hk` 自动映射成 `global`，**注入 Google GIS SDK**）<br>— `--channel=googleplay`：包名 `com.gospelai.app.play`、移 PortOne、运行时 `GOSPEL_PAYMENT_CHANNEL='googleplay'` 走 GP 占位<br>— `direct` 渠道包名 `com.gospelai.app` |
| Admin | `admin/`（Streamlit）管资料库/公告/热门Q&A/用户/定价/内容链接/**自广告(ads)**。无 per-platform 功能开关。 |
| 推送后端 | `backend/app/services/push_service.py` 已实现 **Web Push(VAPID)**，`push_scheduler` 每天 07:00 KST 自动发。但 **FCM 分支是"跳过未实现"**（`_send()` 遇到 `firebase:` token 直接 skipped，注释写明需 firebase-admin）。 |
| 支付 | `api/payment.py` 已实现 **PortOne V2**（微信/支付宝），play 渠道自动 fallback 免费占位。本期不接真实订阅。 |
| 安卓编译 | `android/variables.gradle`：`minSdk=22`(Android 5.1)、`compileSdk=34`、`targetSdk=34`。覆盖极广，无需改。 |

### 0.2 三个之前规划漏掉、但致命的真实约束
1. **🔴 Caddy 不暴露后端（部署架构缺陷）**
   `Caddyfile` 当前**只反向代理 UI:8501（Streamlit Admin）**，**完全不暴露 backend:8000**。安卓连 `https://api.xxx.com` 会 404/连接拒绝，因为 API 路径（`/api`、`/mobile`、`/auth`、`/chat`、`/trending`…）根本没被代理。
   → 阶段 0 必须重写 `Caddyfile`（或另起一个 backend 反代），把后端路径一并暴露。这是出包前真正的硬阻塞，比"没域名"更底层。

2. **🔴 安卓原生推送现在根本发不出去**
   `push_service._send()` 第 154 行：`if platform in ("android","ios") or token.startswith("firebase:")` → `skipped += 1`（注释："firebase-admin 필요(현재 미구현)"）。
   → 即便前端接了 FCM、把 token 传给后端，后端也只会跳过。要做安卓推送，**前后端都要改**：前端集成 `@capacitor/push` 拿 FCM token 并 `POST /mobile/push/subscribe`；后端 `push_service` 要真实调用 `firebase-admin` 发 FCM（Play 版）或厂商 SDK（国内版 cn）。

3. **🟡 CORS 缺真机稳定 origin**
   `.env` 的 `CORS_ORIGINS` 含 `capacitor://localhost,https://localhost`，但出包/公网后要确保包含 APK 实际 origin（`capacitor://localhost` 通常够，但需真机验证；Web 端需 `https://app.gospelai.com` 之类）。

### 0.3 已闭环的决策
| 项 | 决策 |
|---|---|
| 仓库边界 | `korean-gospel-ai`（非 madang-studio） |
| Web 形态 | 现保留 6-tab 不动；**以后只对外推 AI 搜索**（代码暂不砍） |
| 登录 | 邮箱密码（`/auth/login`、`/auth/signup` 已支持） |
| 支付 | 本期免费/占位，真实订阅后置（PortOne/play fallback 已就绪，不改） |
| 推送 | **只做 Google FCM**（用户原话："推送只做谷歌的"）。仅 **Play 版(googleplay) 走 FCM**；**国内版(cn) 本期不做推送**（零 Google 无 FCM，且用户未要求厂商通道）。iOS 推送（APNs）因 iOS 客户端不做而顺延。 |
| 后台播放 | **必须做，且所有版本（cn + Play + 以后 iOS）都要**（用户原话："后台播放一定要做，不管什么版本"）。App 退到后台 / 锁屏后音频仍连续播放，含通知栏 + 锁屏控制。 |
| 广告(ads) | 保留，自己给自己打，不接外部联盟 |
| 域名 | 以后再说；但出包前需**临时 HTTPS 端点**（推荐 Cloudflare Tunnel，免域名费、国内可达） |
| 后端部署 | 香港 VPS + Docker，三端（安卓/iOS未来/Web）共用同一引擎 |
| iOS | 本期不做 |
| 视频模块 | 策略(a)：`api/media.py`/`ccp.py` 仅认知排除，代码保留不删 |

---

## 1. 模块归属（策略 a）

**安卓接入（核心，三端共用同一后端）**：
`chat`(AI问答) / `trending`(热门问答) / `bible` / `retrieval` / `memory` / `auth`(邮箱密码) / `mobile`(history/bible/push/legal/content) / `subscriber` / `support` / `prompts` / `documents` / `drafts` / `jobs` / `admin` / `content_admin` / `ads`(自广告)。

**认知排除（代码保留，安卓不接）**：`api/media.py`、`api/ccp.py`（视频/内容合作平台残留，非 Gospel AI 范畴）。

---

## 2. 阶段 0：后端公网化（所有出包的前置，必须先做）

### 2.1 目标
让安卓真机能 HTTPS 访问 `backend/app` 的全部 API 路径，且国内用户直连快、免 ICP。

### 2.2 推荐方案：香港 VPS + Docker + Cloudflare Tunnel（免买域名）
- **为什么 Cloudflare Tunnel**：你"域名以后再说"，但出包必须 HTTPS 端点。Cloudflare Tunnel 免费、自带 HTTPS、给一个 `*.trycloudflare.com` 临时域名、国内可达性尚可，且**不需要你买域名/配 DNS**。后期买了 `gospelai.com` 再切到正式域名即可。
- **香港 VPS**：Lightsail 香港 / 阿里云国际香港 / Tencent Cloud 国际香港（约 $5-10/月）。装 Docker + Docker Compose。

### 2.3 具体步骤（命令级，待你授权执行）
```bash
# 1) VPS 装 Docker（Ubuntu 示例）
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER   # 重登生效

# 2) 传代码与 .env.production 到 VPS
scp -r /path/to/korean-gospel-ai user@<HK_IP>:~/
#   关键：.env.production 必须含真实密钥（GEMINI/DEEPSEEK/QDRANT/KURE、VAPID_*, CORS_ORIGINS）

# 3) 改 Caddyfile（见 2.4）—— 必须同时暴露 backend:8000 的 API 路径

# 4) 起服务
cd ~/korean-gospel-ai
docker compose -f docker-compose.prod.yml up -d

# 5) 装 cloudflared，建隧道暴露 backend（8000）与 UI（8501）
cloudflared tunnel --url http://localhost:8000   # 记下给出的 https://xxx.trycloudflare.com
#   （生产应建命名 tunnel + 配置文件做持久化，此处为快速验证）
```

### 2.4 🔴 Caddyfile 必须重写（当前只暴露 UI）
当前 `Caddyfile` 仅 `:8501 { reverse_proxy ui:8501 }`，**后端 8000 未代理**。改为（示例，API 子路径并入）：
```caddy
# 用 Cloudflare Tunnel 时，Caddy 可只监听内网，由 tunnel 转发；
# 域名就绪后改用下面正式块。
:8000 {
    reverse_proxy backend:8000
}
:8501 {
    reverse_proxy ui:8501
}
# 域名就绪后：
# api.your-domain.com {
#     encode zstd gzip
#     reverse_proxy backend:8000        # 暴露 /api /mobile /auth /chat /trending ...
# }
# app.your-domain.com {
#     reverse_proxy ui:8501             # Admin/Web
# }
```
> ⚠️ 注意：`docker-compose.prod.yml` 里 backend 服务名、端口需与 Caddy 的 `reverse_proxy` 目标一致（读 `docker-compose.prod.yml` 确认服务名是 `backend` 还是 `api`、端口是 `8000`）。

### 2.5 验证清单（阶段 0 完成标准）
- [ ] `curl https://<tunnel-or-domain>/health` 返回 200（确认后端路径被代理）
- [ ] `curl https://<...>/mobile/app-config` 返回 JSON（确认 `/mobile` 暴露）
- [ ] `curl https://<...>/auth/login -X POST ...` 邮箱密码登录成功拿 token
- [ ] 国内真机浏览器开 `https://<...>/docs` 可达（FastAPI Swagger）
- [ ] CORS：`.env.production` 的 `CORS_ORIGINS` 含 `capacitor://localhost,https://localhost` + Web 域名
- [ ] 出包前把该 HTTPS 端点写进 `build-config.js` 的 `CN_API_BASE` / `WEB_API_BASE`（或 `--api=` 传）

### 2.6 回滚
- 若 Tunnel 不稳，回退到"买 `gospelai.com` + Caddy 正式 HTTPS"路线（你域名就绪时）。
- 代码改动仅 `Caddyfile` 与 `.env.production`，无业务代码改动。

---

## 3. 阶段 1：Web 维护（最小改动，先不动）

已定：Web 现保留 6-tab，**以后只对外推 AI 搜索**。
- [ ] **核查** `mobile/screens/index.js` 是否含指向 `media`/`ccp` 的创作入口 → 当前读码未见，确认后不需改。
- [ ] 把 `mobile/` 中的 **AI 搜索(Chat)** 设为对外推广主入口（营销层面，非代码层面）。
- [ ] 代码层面暂不砍任何 tab（你"以后再说"）。
- [ ] 确认 `sw.js`（Web Push + 离线缓存）在 Web PWA 正常，作为推送实现的参考基线。

> 本阶段零风险，可与阶段 0 并行。

---

## 4. 阶段 2：安卓国内版（cn）出包 + 真机验证

### 4.1 构建命令（已有脚本）
```powershell
cd C:\Desktop\korean-gospel-ai
npm install
npm run android:init            # 首次：cap add android + FontKeyPlugin 复制

# 注入 API 地址（用阶段0的 HTTPS 端点）后出 debug APK
npm run build:apk-debug -- --api=https://<阶段0端点> --market=cn
#   → android/app/build/outputs/apk/debug/app-debug.apk
```
> `build-config.js` 对 `127.0.0.1`/`localhost` 会告警；必须传真实 HTTPS 端点。

### 4.2 真机验证清单（国内网络）
- [ ] 安装 APK（"设置→允许此来源"），邮箱密码登录成功
- [ ] Chat（AI 问答）流式返回正常（`/chat/stream`）
- [ ] 热门问答 `/trending/cards?lang=zh` 正常
- [ ] 圣经阅读（离线 JSON 正常加载，绝对路径）
- [ ] 自广告 `/ads/list` 显示（你自己给自己的广告）
- [ ] CORS 无报错（logcat 看 `capacitor://localhost` 是否被接受）
- [ ] 白屏排查：`npm run android:sync` 后重 build

### 4.3 国内版（cn）推送 —— 本期不做
按用户最新决策："推送只做谷歌的"。国内版(cn) 走零 Google 路线，**无 FCM 可用**，且用户未要求国产厂商通道，故 **cn 版本期不做任何服务端推送**（Web Push 频道不注入 cn 包）。
- 替代触达：cn 版保留 **App 内每日灵修提醒 + 本地通知**（`@capacitor/local-notifications`，零外部依赖，App 安装即有），作为轻量触达，不等同于后台推送。
- 后续若需 cn 后台推送，再评估厂商通道（华为/小米/OPPO/vivo）或 UniPush 聚合——但本期不排期。

### 4.4 签名与分发
```powershell
keytool -genkey -v -keystore gospel-release.keystore -alias gospel -keyalg RSA -keysize 2048 -validity 10000
# android/app/build.gradle 加 signingConfigs.release
npm run build:apk-release -- --api=https://<端点> --market=cn
npm run publish:web   # → releases/flow-ai.apk
```
- 分发：`releases/` + `download.html`（中文明文安装引导）挂香港节点静态托管。
- 更新链路：`download.html` 强制更新已内置。

---

## 5. 阶段 3：安卓 Google Play 版（googleplay）出包 + 上架

### 5.1 构建命令
```powershell
npm run build:aab-release -- --api=https://<端点> --channel=googleplay
#   自动：包名 com.gospelai.app.play、移 PortOne、GOSPEL_PAYMENT_CHANNEL='googleplay'(免费占位)
#   → android/app/build/outputs/bundle/release/app-release.aab
```
> 与 direct 包名 `com.gospelai.app` 物理隔离，GP 控制台不冲突。

### 5.2 Play 版推送（FCM，本期唯一推送实现）
用户决策："推送只做谷歌的"。因此 **FCM 是本期唯一的安卓推送通道**，仅作用于 Play 版（`--channel=googleplay`）。
- **前端**：加 `@capacitor/push` + `google-services.json`（Firebase 项目），拿 FCM token → `POST /mobile/push/subscribe {platform:"android", token:"firebase:xxx"}`。仅 Play 构建注入 Firebase SDK（cn 构建不注入）。
- **后端**：`push_service._send()` 的 `firebase:` 分支**从跳过改为真实实现**——`pip install firebase-admin`，按 `firebase:` token 调 `messaging.send()`。需 `FIREBASE_CREDENTIALS` 环境变量（JSON 路径）。
- 这是 Play 版推送能工作的**必要条件**，否则推送又是"订阅了但收不到"。
- 注：FCM 一家即覆盖所有安卓机型（Play 版用户全在 Google 生态内），无需多厂商。

### 5.3 GP 上架前置
- [ ] 隐私政策页（GP 强制）+ 数据处理说明（gemini/deepseek 调用需在隐私政策声明）
- [ ] 已物理隔离第三方支付（PortOne 在 play 渠道移除）→ 不违反 GP 政策
- [ ] 免费 App 可先上架（GP Billing 真实订阅后置）
- [ ] 上传 `com.gospelai.app.play` AAB

---

## 6. 推送专项（贯穿阶段 2/3，独立跟踪）

| 子项 | 现状 | 本期要做 | 涉及文件 |
|---|---|---|---|
| Web Push(Web PWA) | ✅ 已实现(VAPID) | 保持（不注入 cn 包） | `push_service.py`, `sw.js`, `mobile/services/push` |
| 安卓 FCM(Play) | 🔴 后端跳过 | **本期唯一推送实现**：接 firebase-admin + @capacitor/push | `push_service._send()`, `mobile/services/push`, `android/` 加 Firebase（仅 Play 构建） |
| 安卓厂商(cn) | ⛔ 本期不做 | 用户决策"只做谷歌的"，cn 零 Google 无 FCM → 不排期 | （后续如需再评估厂商 SDK/UniPush） |
| 推送调度 | ✅ 每天 07:00 KST | 保持；可加"新内容/灵修"触发 | `push_scheduler.py` |

> iOS 推送（APNs）本期不做，因 iOS 客户端不做。
> **推送范围收敛结论**：本期推送 = Play 版 FCM 一项。cn 版靠 App 内本地通知触达，不做服务端推送。

---

## 6.5 后台播放专项（所有版本强制，独立跟踪）

**用户硬需求（原话："后台播放一定要做，不管什么版本"）**——App 退到后台 / 锁屏后，音频（讲道、冥想、诗歌）仍连续播放，且通知栏 + 锁屏有播放/暂停/上一首/下一首控制。

### 现状与缺口（已读 `mobile/player.js` 核实）
- 当前播放器：HTML5 `<audio>` + Web Audio，已接 `navigator.mediaSession` 及 Capacitor `MediaSession` 插件桥接（只更新元信息 / 控制回调，**未起原生播放 Service**）。
- **致命缺口**：安卓 WebView 退到后台或锁屏时，系统会挂起 WebView 渲染 → HTML5 `<audio>` 停止。混合 App 经典坑。
- 现有 `media-session` Capacitor 插件只做了"元信息同步"，**没有把音频交给原生 MediaPlayer/ExoPlayer**，所以锁屏只显示信息、不能真正在后台播。

### 本期实现方案（推荐路径）
在 `android/` 增加**原生播放层**，JS 经桥接控制，覆盖 cn + Play + 以后 iOS：
1. **原生音频桥接（自建轻量 Capacitor 插件 或 集成成熟插件）**
   - 选项 A（推荐，省事）：集成成熟 Capacitor 音频插件（如 `capacitor-stream-audio` / `@capacitor-community/media`），其原生层用 `MediaPlayer`/`ExoPlayer` + `MediaSessionCompat` 在前台服务播放。
   - 选项 B（可控）：自建 `capacitor-audio-bg` 插件：`AudioPlaybackService`（foreground service, `foregroundServiceType="mediaPlayback"`）+ `MediaSessionCompat` + 通知栏 `MediaStyle`，暴露 `play(url)/pause/seek/setMetadata` 给 JS。
2. **AndroidManifest 补声明**：`<service android:name=".AudioPlaybackService" android:foregroundServiceType="mediaPlayback" />` + `FOREGROUND_SERVICE` / `FOREGROUND_SERVICE_MEDIA_PLAYBACK` 权限（Android 12+ 强制，否则系统杀进程）。
3. **JS 播放器改造**（`mobile/player.js`）：`playInBackground=true` 时改用原生桥接播放（而非 `<audio>`）；保留现有 `mediaSession` 元信息同步；统一抽象 `play/pause/seek/onEnded` 接口，网页端走 `<audio>`、原生端走桥接。
4. **iOS 前瞻**：iOS 上同样需原生 `AVPlayer` + `MPNowPlayingInfoCenter`（未来 iOS 阶段复用同一 JS 抽象层）。

### 关键文件
- `mobile/player.js`（JS 播放器，加原生分支 + 统一接口）
- `android/app/src/main/java/.../AudioPlaybackService.java`（新建）
- `android/app/src/main/AndroidManifest.xml`（补 service + 权限）
- 自建插件目录 `android/` + `mobile/` 桥接，或 `package.json` 加第三方插件依赖
- `mobile/plugins/media-session`（现有桥接，扩展为含播放控制，或替换）

### 验证清单
- [ ] cn 构建 + Play 构建：播放中按 Home 键 / 锁屏 → 音频**不中断**
- [ ] 通知栏出现播放控件，可暂停/继续/切歌
- [ ] 锁屏界面显示标题/封面 + 控制按钮
- [ ] 拔掉耳机/蓝牙断开 → 正确暂停或继续（按媒体键语义）
- [ ] 杀掉 WebView 后台后仍播（证明走原生层，非 WebView）

### 与推送的关系
后台播放与推送**正交**：推送是"服务器唤醒"，后台播放是"本地持续播放"。两者都做，但互不影响实现路径。

---

## 7. Admin 控制力（你的原问，明确结论）

- **能控制（数据层，三端自动生效）**：热门问答置顶/编辑、公告、定价计划、用户管理、**自广告(ads)内容**、内容链接。改完安卓立即看到。→ 你"自己给自己打广告"完全够用。
- **不能控制（无机制）**：按平台开关功能、强制安卓弹更新（`download.html` 强制更新链路负责，非 Admin 触发）、禁用安卓某按钮。
- **如需 per-platform 开关**：需新增后端 feature-flag 表 + Admin 页，本期非必需，建议后置。

---

## 8. 风险与已知缺口（周全版）

| 缺口 | 严重度 | 影响 | 处理 |
|---|---|---|---|
| 🔴 Caddy 不暴露后端 API | blocker | 安卓连不上任何 API | 阶段 0 重写 Caddyfile 暴露 8000 路径 |
| 🔴 安卓后台播放 WebView 挂起 | 高（用户硬需求） | 退后台/锁屏音频停 | 阶段 2/3 加原生播放层（foreground service + 桥接），见 §6.5 |
| 🔴 Play 推送后端跳过 | 中（仅 Play） | Play 订阅了也收不到 | 阶段 3 改 `push_service._send()` firebase 分支真实发 FCM |
| 🟡 无正式域名 | 中 | 出包需临时 HTTPS | Cloudflare Tunnel 临时端点（阶段 0） |
| 🟡 CORS 缺稳定 origin | 中 | 真机 CORS 报错 | `.env.production` 补 origin（阶段 0 验证） |
| 🟢 `hk`≠国内纯净 | 低 | `hk` 注入 Google SDK | 国内纯净用 `--market=cn` |
| 🟢 支付占位 | 低 | 本期无真实订阅 | PortOne/play fallback 已就绪，不改 |
| 🟢 单实例 SQLite | 低 | 多 API 实例需 PG/Redis | 当前单实例够（DEPLOYMENT_GUIDE 已说明扩展） |
| 🟢 视频模块残留 | 低 | 不接即可 | 策略(a)，代码保留 |

---

## 9. 执行顺序与时间线（建议）

```
阶段 0 (后端公网化 + Caddy 暴露 API)  ──►  阶段 1 (Web 核查, 并行)
        │
        ▼
阶段 2 (安卓 cn 出包 + 真机 + 后台播放原生层)
        │
        ▼
阶段 3 (安卓 Play 出包 + FCM 推送 + 后台播放验证 + 上架)
        │
        ▼
（后置）真实订阅支付 / iOS / per-platform 开关 / 视频模块清理
```

**关键路径依赖**：阶段 0 的"后端 HTTPS 可达 + Caddy 暴露 API"是阶段 2/3 的硬前置；后台播放原生层（§6.5）是 cn 与 Play 双版本的共同硬需求，建议阶段 2 即落地（一次实现两端复用）。

---

## 10. 待你最终拍板（仅剩 1 项，其余已闭环）

1. **香港 VPS**：你是否愿意自己购买一台香港云服务器（约 $5-10/月）？这是阶段 0 的硬前提，我无法替你买。

> 已闭环项：推送只做 Google FCM（cn 不做推送）/ 后台播放所有版本强制 / Web 保留 6-tab / 邮箱登录 / 免费支付 / ads 保留 / 域名暂缓（Cloudflare Tunnel 临时端点）/ 香港 Docker 三端共用 / iOS 本期不做。

### 关于"后台播放"的一个技术选项需你知晓（非阻塞）
后台播放原生层有两条实现路径，等你到阶段 2 时我再按"省事优先"推荐落地，你也可指定：
- **A（推荐）**：集成成熟 Capacitor 音频插件（`capacitor-stream-audio` 等），原生层已含 foreground service + 锁屏控制，JS 改造成本低。
- **B**：自建轻量 Capacitor 插件（`AudioPlaybackService` + `MediaSessionCompat`），可控但需写 Java 原生代码。
两条都满足"锁屏/退后台仍播放 + 通知栏控制"，效果一致。
