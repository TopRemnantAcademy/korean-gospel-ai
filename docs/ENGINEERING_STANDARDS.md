# 工程规范与架构基线（Engineering Standards）

> 团队技术提升的"单一事实来源"。新人照此即可上手，减少对个别核心成员的依赖。
> 本文件基于本项目真实架构与已审计问题（R1–R3、A1–A3）编写。

## 0. 技术栈与版本基线
- 后端：FastAPI + Streamlit（管理/聊天整合应用）+ Qdrant（embedded 模式）。
- 移动端：React Native / PWA。
- **Python 版本统一 3.12**（CI 与本地 venv 对齐，消除 3.11/3.12/3.13 漂移）。
- 包管理：依赖锁在 `requirements-deploy.txt`，禁止随意 `pip install` 到生产路径。

## 1. 架构核心约束
### 1.1 双存储 RAG（HybridRetriever）
- dense 向量（KURE 1024 维）+ BM25 应用层兜底 + RRF 融合。
- 韩语原文为 **immutable source of truth**，中文等为派生。
- Qdrant 使用 **embedded 模式**（`local:./.qdrant_local`），单进程独占锁：
  - ⚠️ **ingest 与 API 严禁并发**，否则锁等待卡死。运维脚本必须先清残留进程。

### 1.2 LLM 调用
- Provider：`tencent`（deepseek reasoning 模型），答案在 `reasoning_content` 字段。
- 单次推理 ~78s 属正常 → 前端必须流式/thinking 态，严禁"点了没反应"的同步等待。

### 1.3 多语言响应
- `target_lang` ∈ {ko, en, zh, ja} → `prompts/system.py` 按语言切换系统提示。

## 2. API 契约纪律（A2 教训）
- 路由必须声明 `response_model`，且返回值结构**严格一致**。
- 契约变更 = 破坏性变更，需评估前端/移动端影响并文档化。
- 错误统一封装，禁止裸 dict 返回。

## 3. 并发与资源纪律
- 异步函数内禁止同步重 IO（DB/HTTP/文件）阻塞事件循环。
- SSE 输出换行正确转义、带心跳（A1 教训）。
- Qdrant embedded 单进程锁 → ingest/API 互斥。

## 4. 数据迁移纪律（A3 教训）
- **迁移唯一来源 = `alembic revision --autogenerate`**，禁止手改迁移文件。
- 迁移须可前向/后向执行，不在迁移内做破坏性数据处理。
- 定期 `alembic check` 防止模型与迁移 drift。

## 5. 安全与合规（强制）
- PIPL 生物识别：授权前置，未授权不采集。
- 自定义域名 SSRF：白名单 + 内网地址拦截。
- 积分/额度钱包：操作满足不变量（无负额、无超额）。
- 多租户：`WORKSPACE_SCOPED_MODELS` 隔离，无越权。

## 6. 质量门禁（见 ci.yml / pre-commit）
- 本地 pre-commit 强制：`ruff` lint + format。
- CI 渐进式：ruff + 安全扫描（先报告后阻断）→ mypy 类型健康度 → 测试覆盖率。
- 存量基线清理：一次 `ruff check --fix && ruff format` 后翻阻断。

## 7. 评审与知识沉淀
- 所有 PR 走 `PULL_REQUEST_TEMPLATE.md` + `CODE_REVIEW_CHECKLIST.md`。
- 同类问题（如 A1–A3）修复后必须补回归测试，防止复发。
- 定期 lunch-and-learn 沉淀编码模式与常见坑（见 knowledge/ 目录规划）。
