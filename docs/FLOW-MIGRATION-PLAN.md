# FLOW 全生命周期启动计划（FLOW-MIGRATION-PLAN）

> 目标：把 `C:\Desktop\korean-gospel-ai` 的可用代码，安全迁移到新仓库 `C:\Desktop\FLOW`（产品名 FLOW），并明确"如何改名才不出错"。
> 配套：`MULTI-PLATFORM-PLAN.md`（分阶段）、`ANDROID-APK-SPEC.md`（安卓极致规格）。
> 状态：待用户确认后执行。

---

## 0. 用户已确认决策

1. **新仓库**：`C:\Desktop\FLOW`，产品名 FLOW。
2. **视频模块**：用户"没做过视频功能，media/ads/ccp 不要搬"。→ 读码发现它们是系统依赖（`main.py` lifespan 硬依赖 media；`ccp` 被 token 计费 + orm 依赖；`ads` 被挂载路由）。**落地：后端保留这三个模块保启动，安卓前端不调用**（已验证 mobile 无 `<video>` 标签）。
3. **品牌改名**：用户担心"替换细节不匹配出错"。→ **结论：代码标识符一律不动，只改 UI 可见文案**（见 §2 精确边界）。这是最安全方案。

---

## 1. 为什么"不批量替换"是对的（风险分析）

批量把 "Gospel AI" → "FLOW" 会在**代码标识符层**引入隐性 bug：

| 标识符类型 | 例子 | 误改后果 |
|---|---|---|
| 前端 API 占位符 | `window.GOSPEL_API_BASE` / `__GOSPEL_API_BASE__` | 三处（index.html / services/index.js / build-config.js）必须一致；改漏一处 → 所有 API 请求 404 |
| localStorage 键 | `gospel_dark` / `gospel_user` / `gospel_offline`（约 40+ 处） | 改了 → 用户设置/登录态/离线库**静默丢失**（最隐蔽坑） |
| 后端 DB 文件 | `.gospel.db`、迁移列 `gospel_core_tag` | 改了需同步库结构，否则迁移失败 |
| 业务语义字段 | `gospel_core_tag`（"福音核心"神学标签，RAG 检索用） | 这是**产品功能**，非品牌名，改了破坏 AI 检索逻辑 |
| 提示词常量 | `GOSPEL_SYSTEM_PROMPT` | AI 行为相关，改了影响输出 |
| service / 日志名 | `korean-gospel-rag`、`gospel-api.trending` | 纯内部，改了要全链路同步 |

**所以：标识符全不动 = 零崩溃风险。只改用户肉眼可见文案 = 品牌更新。两者解耦。**

---

## 2. 安全改名策略（核心章节）

### 2.1 绝对不能动（IDENTIFIERS-FROZEN）

以下**原样保留**，任何阶段都不要改：

**前端（mobile/）**：
- `window.GOSPEL_API_BASE` / `__GOSPEL_API_BASE__`
- `window.GOSPEL_PAYMENT_CHANNEL` / `__GOSPEL_PAYMENT_CHANNEL__`
- `window.GOSPEL_GOOGLE_CLIENT_ID` / `__GOSPEL_GOOGLE_SDK__` / `__GOSPEL_PORTONE_SDK__`
- 所有 `localStorage` 键：`gospel_*`（state.js 约 40 处）、`gospel_offline`（offline.js 的 IndexedDB 名）
- `capacitor.config.json` 的 `appId`：`com.gospelai.app` / `com.gospelai.app.play`（见 §2.3 关于包名的处理）

**后端（backend/）**：
- `service` 字段值 `korean-gospel-rag`（test_main.py 断言）
- DB 文件 `.gospel.db`、迁移列 `gospel_core_tag`
- 日志名 `gospel-api.*`、service 名
- `GOSPEL_SYSTEM_PROMPT`、词表 "gospel"（extraction_service）
- `media/ads/ccp` 模块名（系统依赖，保留）

### 2.2 可以安全改（UI-TEXT-ONLY，定向替换）

仅改**用户肉眼可见**的文案，逐处确认，不用全局暴力替换：

| 文件 | 位置 | 改法 |
|---|---|---|
| `mobile/portal.html` | 第 121 行 `<p>GOSPEL</p>` 装饰字 | 改为 `FLOW` |
| `backend/app/services/email_service.py` | 第 84 / 171 行邮件标题 `"Gospel AI — ..."` | 改为 `"FLOW — ..."` |
| 关于页 / 欢迎语 / 设置页里的 "Gospel AI" 字样 | 在 `mobile/screens/*.js` 中 | 全局搜 "Gospel AI"（注意大小写）逐处改 "FLOW" |
| `mobile/README.md` | 标题 | 改名 FLOW（文档无所谓） |

> **操作纪律**：用 IDE "在选中范围查找" + 逐处 review，绝不用 `sed -i` 全局替换 "Gospel"。

### 2.3 包名 / appId 的处理（重要）

你产品叫 FLOW，但 `com.gospelai.app` 是 Android 应用 ID（上架身份）。两种选择：
- **方案 A（推荐，零风险）**：包名保持 `com.gospelai.app` / `com.gospelai.app.play`。应用 ID 是技术身份，用户看不见；商店显示名改为 "FLOW" 即可。避免改包名导致的签名/上架/双包名冲突。
- **方案 B（彻底改名）**：改成 `com.flow.app` / `com.flow.app.play`。需同步 `capacitor.config.json` 的 `appId` 和 `android/applicationId`，且**必须重新生成签名密钥**（包名变 = 新应用）。工作量大、风险高。

→ **建议方案 A**：用户看到的名字是 FLOW（商店 + UI），底层包名不动。

---

## 3. 搬运范围（精确清单）

### 3.1 必搬（已验证）
```
mobile/                  (整目录，含 data/ 圣经诗歌讲道 json)
android/                (整目录，含 MediaSessionPlugin / MediaPlaybackService)
backend/app/            (整目录，含 api/services/models/migrations，media/ads/ccp 保留)
backend/tests/          (建议搬)
backend/migrations/     (已含于 app/ 下)
scripts/                (build-config.js / publish-apk.js / copy-android-plugins.js / 种子导入脚本)
package.json, version.json
capacitor.config.json
docker-compose.yml, docker-compose.prod.yml
Dockerfile, Dockerfile.ui, Dockerfile.rag
Caddyfile               (阶段0需改，见 §5)
.env.example
docs/MULTI-PLATFORM-PLAN.md, docs/ANDROID-APK-SPEC.md
README.md               (Gospel 相关则搬并改名)
```

### 3.2 不搬（垃圾/无关）
```
_archive/ _overflow_shots/ venv/ node_modules/ dist/ build/
.git/ qdrant_local/ logs/ run_logs/ generated-images/
*.bat (根目录运维脚本) load_test_result*.json test_report*.json
settings_*.png static-site/ docs/ 中除两份计划外的 40 个 md
deliverables/ (朝鲜语策划文档，非代码)
SYSTEM.md / CONTEXT.md (旧架构描述，易过时，不搬)
```

---

## 4. 执行步骤（顺序敏感）

1. **建仓**：`mkdir C:\Desktop\FLOW && cd FLOW && git init`
2. **预览**：`robocopy C:\Desktop\korean-gospel-ai\backend C:\Desktop\FLOW\backend /E /XD venv .git __pycache__ /XF *.pyc /L` → 列出将搬运文件，用户过目
3. **真搬**：去掉 `/L`，执行 robocopy（对每个必搬目录重复：mobile / android / backend / scripts / 配置）
4. **装依赖**：FLOW 内 `pip install -r backend/requirements.txt` + 根 `npm install` + `cd mobile && npm install`
5. **安全改名**（§2.2 定向）：只改 UI 文案，标识符不动
6. **包名决策**（§2.3）：默认方案 A（包名不变）
7. **校验启动**：`cd backend && uvicorn app.main:app --port 8000` → `/health` 200
8. **校验前端契约**：确认 `window.GOSPEL_API_BASE` 占位符在 index.html / services/index.js / build-config.js 三处一致（应原样，未动）
9. **校验构建**：`npm run build:apk-debug -- --market=cn --api=https://<tunnel>`（阶段2前）
10. **首提交**：`git add -A && git commit -m "chore: init FLOW repo (branded UI only, identifiers frozen)"`

---

## 5. 阶段 0 部署前置（Caddy 改造）

当前 `Caddyfile` 仅 `reverse_proxy localhost:8501`（UI）。安卓需连后端 → 必须加后端路径：
```
handle_path /api/*     { reverse_proxy localhost:8000 }
handle_path /mobile/*  { reverse_proxy localhost:8000 }
handle_path /auth/*    { reverse_proxy localhost:8000 }
handle_path /chat/*    { reverse_proxy localhost:8000 }
# 其余 → UI:8501
```
（详见 ANDROID-APK-SPEC.md 阶段 0）

---

## 6. 验证清单（搬运完成必勾）

- [ ] FLOW 后端 `uvicorn` 启动，`/health` 返回 200（证明 media/ads/ccp 保留正确）
- [ ] `grep -rn "GOSPEL_API_BASE" mobile/index.html mobile/services/index.js scripts/build-config.js` 三处都存在且一致（标识符未动）
- [ ] `grep -rn "gospel_" mobile/utils/state.js | wc -l` 仍约 40（localStorage 键未动，用户数据不丢）
- [ ] `grep -rn "<video" mobile/` 结果为 0（无视频入口）
- [ ] FLOW 内 `npm install` + `pip install` 无缺失依赖
- [ ] `mobile/data/` 下 bible/hymns/sermons/meditation json 非空
- [ ] 原仓 `korean-gospel-ai` 未改动（搬运全程只读原仓）
- [ ] UI 文案 "Gospel AI" 在 portal/邮件/关于页已改为 "FLOW"（如执行了 §2.2）

---

## 7. 风险矩阵与回滚

| 风险 | 等级 | 触发 | 缓解 |
|---|---|---|---|
| 标识符误改导致 API 404 | 高 | 全局替换 GOSPEL_ | §2.1 冻结标识符，只改 UI 文案 |
| localStorage 键改导致用户数据丢 | 高 | 改 gospel_* 键 | §2.1 冻结，绝不改键名 |
| 包名改导致签名/上架冲突 | 中 | 改 com.gospelai→com.flow | §2.3 方案 A：包名不变 |
| 后端启动崩（误删 media/ads/ccp） | 高 | 真删模块 | 保留不删；启动失败先查 main.py import |
| 原仓污染 | 低 | 误写原仓 | 搬运全程只读原仓，写仅 FLOW |

**回滚**：FLOW 独立新仓，原仓完全不动。失败直接删 FLOW 重来，零风险。

---

## 8. 待用户最终确认

1. 文件夹 `C:\Desktop\FLOW` ✅
2. 视频模块后端保留、前端不接 ✅
3. 标识符冻结、仅改 UI 文案 ✅（承你的担心）
4. **包名方案**：默认 A（保持 `com.gospelai.app`），是否同意？还是坚持改成 `com.flow.app`（方案 B，需重签名）？
5. **是否现在执行搬运**？建议先用 `robocopy /L` 预览清单给你过目，再真搬。
