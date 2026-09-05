#  Android APK 发布指南

## 当前已准备的内容

- `mobile/index.html`：包含咨询、圣经、赞美标签页的移动端应用界面
- `mobile/app.js`：对接现有 FastAPI `POST /chat`、圣经主题卡片、内置灵修音频
- `mobile/manifest.webmanifest`：用于 PWA/TWA 打包的 manifest
- `mobile/sw.js`：静态资源离线缓存
- `mobile/icons/`：Android 应用图标用 SVG

## 重要架构说明

本项目的 AI 功能并非在 Android 设备本地独立运行，而是调用已部署的 FastAPI 服务器。

APK 发布时，应用设置中的 API 地址必须为生产环境的 HTTPS 地址。

例如：

```text
https://api.your-domain.com
```

`http://127.0.0.1:8000` 仅在开发用 PC 内部有意义，真实手机 APK 中无法使用。

### CORS 配置（生产部署必填）

移动端应用的托管域名要调用后端，必须在后端 `.env` 的 `CORS_ORIGINS` 中加入移动端托管地址。多个 origin 用逗号分隔。

```text
CORS_ORIGINS=https://app.your-domain.com,https://admin.your-domain.com
```

## 本地预览

```powershell
cd C:\Desktop\korean-gospel-ai
.\.venv312\Scripts\python.exe -m http.server 4174 -d mobile --bind 127.0.0.1
```

在浏览器中打开：

```text
http://127.0.0.1:4174/
```

## APK 打包所需安装

当前此 PC 会话的 PATH 中未包含 Java、Gradle、Android SDK。制作 APK 需要以下内容：

- Android Studio
- Android SDK Platform Tools
- JDK 17 及以上
- Node.js 与 npm

## 推荐发布路径

### 1. 服务器部署

先部署 FastAPI 后端。

```powershell
docker compose -f docker-compose.prod.yml up -d
```

或参照 Railway/Fly.io 部署文档。

### 2. 移动端应用托管

将 `mobile/` 文件夹上传至 HTTPS 静态托管。

例如：

```text
https://app.your-domain.com
```

### 3. APK 打包

快速发布可使用 Trusted Web Activity（TWA），最为简单。若需上架应用商店，建议在 Android Studio 中生成签名 AAB。

Capacitor 方式示例：

```powershell
npm create @capacitor/app flow-ai-android -- --web-dir=../mobile
cd flow-ai-android
npm install @capacitor/android
npx cap add android
npx cap sync android
npx cap open android
```

在 Android Studio 中执行：

```text
Build > Generate Signed Bundle / APK
```

### 4. 发布前检查

- 确认生产 API 以 HTTPS 开放
- 在 Android 应用中将 API 地址保存为生产地址
- 在后端 `.env` 的 `CORS_ORIGINS` 中加入移动端托管域名 + `capacitor://localhost`、`https://localhost`
- 验证咨询回复、圣经检索/阅读、赞美播放、我的记录查看
- 确认危机咨询提示语与隐私政策（应用设置 > 危机咨询提示）
- Google Play 上架时填写应用签名密钥、包名（`com.gospelai.app`）、隐私表单

## 已完成实现（方案：应用全规格 + APK 构建）

### 会员功能
- ✅ 会员登录/注册对接（`/auth/signup`、`/auth/login`、Bearer 令牌）
- ✅ 我的对话记录 + 反馈 👍👎（`/mobile/history`、`/feedback`）
- ✅ 访客对话 → 注册时自动继承

### 圣经
- ✅ 圣经/讲道 RAG 检索（`/mobile/bible/search`）
- ✅ 圣经正文阅读（`/mobile/bible/read`）——公有领域文本，可通过在 `data/bible/` 增加文件扩展
- ✅ 参考经文浏览（`/mobile/bible/refs`）

### 赞美/灵修
- ✅ 赞美目录（`/mobile/music`）——`data/music/` 文件 + Web Audio 合成整合
- ✅ 音频文件流式播放（`/mobile/music/{id}/stream`）——支持 Range 请求（SEEK）
- ✅ 今日灵修/话语（`/mobile/verse/daily`）

### 推送通知
- ✅ Web Push（VAPID）订阅/退订（`/mobile/push/subscribe`）
- ✅ 每日今日话语自动发送（APScheduler，启用 `PUSH_ENABLED=true` 时激活）
- ✅ 测试通知（`/mobile/push/test`）
- ⚙️ FCM（Android/iOS 原生）发送需在安装 `firebase-admin` 后启用

### 安全/法务
- ✅ 危机咨询提示 + 隐私政策（`/mobile/legal`）
- ✅ Service Worker 安全加固——阻止认证 API 响应缓存

### Android 构建
- ✅ Capacitor 配置（`mobile/capacitor.config.json`，`npx cap add android` 生成 `android/`）
- ✅ 硬件音量键 → 圣经字体调节：原生桥接代码在 `mobile/integration/android/`
  （`FontKeyPlugin.java` + `MainActivity.java`，覆盖到生成的 `android/app/src/main/java/com/gospelai/app/`）
- ✅ 详细构建/连线指南见 `mobile/integration/android/README.md`（调试 APK / 发布 AAB / 签名 / FCM）
- ⚠️ 硬件音量键拦截**仅 Capacitor WebView 可行**；TWA 无法拦截物理按键。

## 启用方法（生产部署）

### 添加音频
将 mp3/ogg 文件放入 `data/music/` 文件夹，即自动加入目录。

### 添加圣经正文
以 `data/bible/{书名}.txt` 形式新增文件，即可通过 `/mobile/bible/read` 阅读。

### 启用推送通知
```text
# 取消 requirements.txt 注释后安装
pip install pywebpush apscheduler

# 在 .env 中追加
PUSH_ENABLED=true
PUSH_HOUR_KST=7
VAPID_SUBJECT=mailto:admin@your-domain.com
```

### Android APK 构建
参见 `ANDROID_BUILD.md`。摘要：
```powershell
npm install
npx cap add android
npx cap sync android
npx cap open android    # 在 Android Studio 中 Build > Generate Signed Bundle/APK
```

## 后续实现候选

- 面向 Play Store 的 AAB 自动构建 CI/CD 工作流（GitHub Actions）
- 圣经正文全卷摄入（当前为约翰福音样例）
- 真实音频录音/上传管理页面
