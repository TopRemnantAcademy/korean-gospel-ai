# AI Gospel (korean-gospel-ai) → 腾讯云韩国 (ap-seoul) 产品映射与规格对标

> 角色：腾讯云产品专家（product-expert）
> 范围：仅 korean-gospel-ai 项目，本地 → 腾讯云韩国首尔区（ap-seoul），非跨云
> 说明：本环境无法调用 MigraQ 实时技能，以下基于腾讯云标准产品既有知识给出；**所有标注「⚠️待复核」项需控制台 / MigraQ 二次确认**。
> 合规提示：用户称无特殊要求，但韩国 **PIPA（个人信息保护法）** 对 users / subscribers 等个人数据仍可能适用，相关建议在风险与依赖中标注。

---

## 1. 源栈 → 腾讯云韩国产品映射表

| # | 本地组件 | 推荐腾讯云产品 | 推荐规格 / 类型 | 部署形态 | 关键理由 | ⚠️待复核 |
|---|----------|----------------|----------------|----------|----------|----------|
| 1 | FastAPI 后端 `:8000`（/chat、/suggestions、/admin/*、/trending 等常驻 REST） | **CVM**（通用型 S5）或 **TKE** 容器 | S5.LARGE8 起；生产 2×S5.2XLARGE16 | CVM 单机多容器 / TKE Deployment | 已 docker 化（Dockerfile），有常驻 uvicorn 进程；与 Qdrant/UI 同仓库，适合同集群 | 实例族在 ap-seoul 的具体在售型号 |
| 2 | Streamlit 双应用（채팅 `:8501` + 관리자 `:8502`，常驻 HTTP） | 同上（与 FastAPI 同宿主） | 随 #1 | 同上 | 项目已合并为单 `ui` 服务（:8501），管理员 UI 可同容器或多副本；CPU 型负载 | UI 是否需独立扩缩容 |
| 3 | Qdrant 向量库（当前 **embedded** `local:./.qdrant_local`，单进程锁；集合 gospel_kure，KURE 1024 维，RAG 混合检索） | **首选：CVM/TKE 上自托管 Qdrant server 模式**；备选：**腾讯云 VectorDB（向量数据库）** | 自托管：M5（内存型）2XLARGE16 起 | CVM 容器 / TKE StatefulSet | 项目 `docker-compose.prod.yml` 已用 `qdrant/qdrant:v1.13.4` **server 模式**，单锁问题天然解除；改托管 VectorDB 需换 SDK/迁移数据，风险更高 | **VectorDB 是否在 ap-seoul 可用、是否提供 Qdrant 兼容 API** |
| 4 | 移动端 PWA 静态站 `:4174`（http.server，含 bible/media/chat；CORS 含 `127.0.0.1:4174`） | **COS（对象存储）+ CDN** | 标准存储 + 静态网站托管 + CDN 加速 | 托管（无需 CVM） | 纯静态资源，COS+CDN 最低成本、天然 HTTPS、全球加速；替换 CORS origin 为生产域名 | 自定义域名与备案/韩国要求 |
| 5 | LLM（`LLM_PROVIDER=tencent`，deepseek-v4-flash-202605，reasoning） | **腾讯云大模型 API（混元 / DeepSeek 原子能力）** | 按 token 计费，无实例 | SaaS API（出站调用） | 本就属腾讯系，迁移后直接可用；走公网/内网 API 端点 | **该端点是否可从 ap-seoul 直接调用、延迟与配额、是否走私有网络** |
| 6 | 关系型数据（SQLAlchemy + Alembic；users/subscribers/interaction 等表，当前 SQLite gospel.db） | **TencentDB for PostgreSQL**（或 MySQL） | 开发 2C4G 单节点；生产 4C8G 双节点（一主一备，跨 AZ） | 托管 DB | 已用 Alembic 且计划迁 Postgres；托管 DB 免运维、自动备份、主备高可用 | PostgreSQL 与 MySQL 的取舍、版本（15/16）在 ap-seoul 支持 |
| 7 | 配置 / 静态数据（`data/suggestion_questions.json`、설교 PDF、성경 데이터等文件资源） | **COS（对象存储）** | 标准存储，按量 | 托管 | 与代码解耦、可版本化、供 CVM/TKE 挂载或下载；亦作 Qdrant/DB 备份桶 | — |
| 8 | i18n（ko/zh/en/ja 多语响应）；管理员鉴权 `Authorization: Bearer <ADMIN_API_KEY>` | 无独立产品（应用层处理）；密钥用 **SSM（密钥管理/Secrets Manager）** | — | 应用内 + 密钥托管 | 多语为代码逻辑；密钥应从 `.env` 移入 SSM，避免镜像/仓库泄露 | SSM 在 ap-seoul 可用性 |
| 9 | 其他：CORS、静态文件服务、长期后台 인제스트（ingest）任务 | **CLB（应用型负载均衡）+ NAT 网关 + CLS（日志服务）**；后台任务用 **Celery+Redis 或 K8s Job/CronJob** | CLB 标准/应用型；NAT 小型；Redis 1–4GB | 托管 | 见第 4 节风险与依赖 | — |

### 重点决策 A：FastAPI + Streamlit 用 CVM 还是 TKE？
- **推荐（默认）：先用 CVM（单机 Docker Compose）+ CLB 快速落地，生产演进到 TKE。**
- 取舍：
  - **CVM + Docker Compose**：1 个月内上线最快，运维简单，契合现有 `docker-compose.prod.yml`（qdrant/backend/ui 三服务）。缺点：多实例扩缩、滚动发布、隔离性弱；需 systemd/supervisor 守护进程；单 CVM 有单点风险（用 CLB + 多 AZ 两实例缓解）。
  - **TKE（容器）：** 服务隔离、弹性扩缩、声明式部署、后台 ingest 用 Job/CronJob 更优雅；适合长期。缺点：学习/运维成本高、1 个月窗口偏紧。
  - **结论**：把"容器化"作为硬约束（项目已具备），形态按节奏选 CVM→TKE；若团队有 K8s 经验则直接 TKE。

### 重点决策 B：Qdrant embedded → VectorDB 还是自托管 Qdrant？
- **推荐：自托管 Qdrant server 模式（CVM/TKE 上）**，腾讯云 VectorDB 作为后续可选项。
- 理由：① 项目 prod compose 已是 server 模式，**单进程锁约束天然解除**；② 切换 VectorDB 需改 `qdrant-client` 调用为 VectorDB SDK 并重新灌库，迁移风险与工作量更高；③ 自托管沿用既有 `qdrant_config.yaml`（api_key、memmap、WAL、性能线程），平滑。
- 解除 embedded 单锁的具体动作：本地 embedded `./.qdrant_local` → 导出（snapshot/export）→ 灌入 server 模式 Qdrant（独立容器/实例），后端改 `QDRANT_URL=http://qdrant:6333`（compose 已就绪）。
- 何时选 VectorDB：若 **⚠️确认 ap-seoul 提供 VectorDB 且支持 1024 维 + 混合（dense/sparse）检索 + Qdrant 兼容 API**，且希望彻底卸下向量库运维，则可评估切换；否则默认自托管。

### 重点决策 C：PWA 静态 → COS + CDN（明确）
- 纯静态、无后端逻辑，COS 静态网站托管 + CDN 加速是标准做法；**PWA 要求 HTTPS**，用自定义域名 + SSL 证书（腾讯云 SSL 证书服务，免费 DV）。
- 必须更新 CORS：`http://127.0.0.1:4174` → 生产域名（如 `https://m.gospel.ai`），并在 FastAPI 的 CORS allow_origins 同步调整。

### 重点决策 D：关系型 DB → TencentDB for PostgreSQL（明确）
- 当前 SQLite 不可用于生产（并发/备份/高可用弱）。SQLAlchemy+Alembic 已就绪，切换 Postgres 仅需改连接串（`DATABASE_URL=postgresql+psycopg2://...`）。若团队更熟 MySQL 也可，但项目文档倾向 Postgres。

### 配套必选组件（逐一给出）
- **VPC + 子网 + 安全组 + 路由表**：所有资源置于私有 VPC；后端/Qdrant 放私有子网，仅 CLB 暴露公网。
- **CLB（应用型）**：统一对外暴露 FastAPI(:8000) 与 Streamlit UI(:8501)，做 SSL 终止、CORS、健康检查、多可用区流量分发。
- **NAT 网关 + EIP**：私有子网 CVM/TKE 出公网访问 LLM API、嵌入/重排 API、Langfuse、包下载。**成本注意：LLM API 出流量走 NAT，按流量计费。**
- **Redis（TencentDB for Redis）**：缓存、限流（`RATE_LIMIT_ENABLED`）、Celery broker（后台 ingest 队列）；1GB 起，生产 2–4GB 主从。若不用 Celery 也可省，但强烈建议保留作限流/缓存。
- **COS**：静态资源 + 备份桶（DB 快照、Qdrant snapshot、PDF/성경数据）。
- **SSL 证书服务**：PWA/UI/API 全站 HTTPS。
- **CAM**：最小权限账号、子账号、角色；密钥不下发到镜像。
- **CLS（日志服务）+ 云监控**：进程/容器日志、Qdrant/DB/CLB 指标告警；后台 ingest 失败告警。

---

## 2. ap-seoul 区域能力核对清单

| 项目 | 假设 / 说明 | ⚠️待复核 |
|------|-------------|----------|
| 可用区数量 | 通常 **2–3 个**（ap-seoul-1 / 2 / 3） | 控制台确认实际 AZ 数与命名 |
| CVM（S5/M5/C6/SA2 等） | 应可用 | 具体到售型号与库存 |
| TencentDB for PostgreSQL / MySQL | 应可用，支持主备跨 AZ | 版本与 HA 架构 |
| TencentDB for Redis | 应可用 | 架构（标准/集群） |
| COS（多 AZ） | 应可用，首尔桶 | 多 AZ 开关 |
| CDN | 全球加速，韩国节点 | 域名/加速区域 |
| CLB / NAT 网关 | 应可用 | — |
| TKE | 应可用 | 集群版本 |
| **腾讯云 VectorDB** | **不确定是否在 ap-seoul 上线** | **需确认是否可用及 Qdrant 兼容性** |
| **大模型 API（DeepSeek/混元）** | 应可用，但端点区域/私有网络接入需确认 | **ap-seoul 调用路径、延迟、配额** |
| SSM / KMS / CLS / CAM / 云监控 | 应可用 | — |
| 网络拓扑假设 | 单 VPC，2 个私有子网跨 2 AZ + 1 个公有子网放 NAT/CLB；DB 主备跨 AZ；Qdrant 可主备或单节点+快照 | 实际 AZ 打通 |

---

## 3. 规格对标草案（最小可用 / 推荐生产 两档）

> 说明：Qdrant 内存取决于向量条数（1024 维 × 条数 × 副本）。以下按"中等语料（数十万~百万级片段）"估算，**⚠️需按实际 collection 规模复核**。

### 计算（CVM）
| 档位 | 形态 | 规格 | 说明 |
|------|------|------|------|
| 最小可用 | 单 CVM + Docker Compose | **S5.LARGE8（4C / 8GB）×1** | 验证/内测；Qdrant+Backend+UI 同机，内存偏紧 |
| 推荐生产 | 2 CVM + CLB（跨 AZ） | **S5.2XLARGE16（8C / 16GB）×2**（或 1×S5.4XLARGE32） | 前端与后端分离、滚动发布；若本地 embedding/reranker 重，可升 C6（计算型） |
| 内存型（若自托管 Qdrant 独立） | 独立节点 | **M5.2XLARGE16 / M5.4XLARGE32（内存型）** | 向量常驻内存，提升检索吞吐 |

- 嵌入（KURE）与重排（bge_m3）若本地推理：CPU 密集，建议计算型 C6 或加 **GPU（GN 系列）可选加速**；若走托管 API 则仅出站调用，CVM 不必大。
- ⚠️ KURE 是本地推理还是托管 API 需确认（见待确认问题）。

### 关系型 DB（TencentDB）
| 档位 | 规格 | 架构 |
|------|------|------|
| 最小可用 | **2C4G** | 单节点（开发） |
| 推荐生产 | **4C8G ~ 8C16G** | 双节点（一主一备，跨 AZ），自动备份 |

### 缓存 / 任务队列（Redis）
| 档位 | 规格 | 架构 |
|------|------|------|
| 最小可用 | **1GB** | 标准主从 |
| 推荐生产 | **2–4GB** | 标准主从（缓存 + 限流 + Celery broker） |

### 向量库
- 自托管 Qdrant：随计算节点（见上，内存型优先），挂 COS/云盘做 snapshot 备份。
- 托管 VectorDB（若可用）：按节点规格选购，**⚠️需确认 ap-seoul 规格档与单价**。

### 网络 / 存储
- CLB：标准/应用型，按流量或固定带宽。
- NAT：小型（约 100 万并发连接）起步。
- COS：标准存储，按量；CDN 流量包。
- 云盘：Qdrant 存储、DB 数据盘用**云硬盘（高性能/SSD）**，开定期快照。

---

## 4. 风险与依赖

1. **embedded Qdrant 单锁 → 已解**：项目 prod compose 已是 server 模式；迁移需把 `./.qdrant_local` 导出 snapshot 灌入 server 实例。⚠️验证 collection 规模以定内存。
2. **长期后台 인제스트（ingest）进程**：当前 compose 未含 ingest 服务（疑似脚本/Celery/APScheduler）。需在云上提供常驻执行体——CVM 用 systemd/supervisor，TKE 用 Deployment/CronJob/Job；并用 CLS 收集日志、失败告警。否则索引会停滞。
3. **CORS / 静态托管**：PWA 必须 HTTPS；上线前将 `127.0.0.1:4174` 改为生产域名，并同步 FastAPI 的 allow_origins；CLB 做 SSL 终止。
4. **出站依赖（NAT 成本）**：LLM API、嵌入/重排 API、Langfuse 均出公网，走 NAT 按流量计费——是主要变动成本项之一；建议评估是否将嵌入/重排改为本地推理或同地域托管 API 以降本。
5. **LLM 延迟与可用性**：`LLM_PROVIDER=tencent`（DeepSeek）应从 ap-seoul 可达；⚠️确认端点区域与延迟，必要时配置 fallback（项目已有 openai/anthropic fallback 链）。
6. **单点风险**：单 CVM 故障即全停；用 CLB + 跨 AZ 多实例 + 托管 DB 主备缓解。
7. **密钥与配置**：`.env` 含 ADMIN_API_KEY、各类 API KEY；迁移到云须移入 **SSM/密钥管理**，禁止打包进镜像或提交仓库。
8. **PIPA 合规（韩国个人信息保护法）**：users/subscribers 属个人数据。ap-seoul 数据驻留韩国，利于合规；仍需：传输/存储加密（SSL+KMS）、最小权限访问、访问审计（CLS/审计日志）、备份保留策略、必要时 DPIA。⚠️请用户确认是否实际收集韩国居民个人信息及合规要求。
9. **SQLite → Postgres 切换**：确认 Alembic 迁移在 Postgres 上完整跑通、字段类型/方言无差异；先在 ap-seoul 空库 `alembic upgrade head` 验证。
10. **PWA 后台推送（可选）**：requirements 注释了 pywebpush/firebase-admin（FCM）；若启用需配置 VAPID/Service Worker 与 FCM 项目，属额外出站依赖。

---

## 5. 待确认问题清单（回传用户 / 下一阶段）

1. **VectorDB 是否在 ap-seoul 可用？** 若可用，是否提供 Qdrant 兼容 API（决定能否零改造切换）？
2. **LLM 端点调用路径**：`LLM_PROVIDER=tencent` 的 DeepSeek 端点能否从 ap-seoul 直接调用？延迟、配额、是否支持私有网络接入？
3. **嵌入与重排部署方式**：KURE（1024 维）与 bge_m3 是本地推理还是托管 API？决定 CVM 规格与 NAT 出流量成本。
4. **Qdrant collection 规模**：gospel_kure 向量条数 / 存储量，用于定内存与实例规格。
5. **PostgreSQL 还是 MySQL**？当前 SQLAlchemy+Alembic 两者皆可，需定夺。
6. **预算上限**？影响多 AZ、多实例、托管 vs 自托管、Redis 规格取舍。
7. **域名与 SSL 计划**？PWA 必须 HTTPS，需自定义域名 + 证书。
8. **是否启用 Langfuse / 其他外部 SaaS**？这些也走 NAT 出网。
9. **灾难恢复 RPO/RTO**？决定 DB 备份频率、跨 AZ、Qdrant snapshot 策略。
10. **PIPA 适用性确认**：是否收集韩国居民个人数据？是否需 DPIA、数据保留期限、用户撤回同意机制？
11. **后台 ingest 触发方式**：Celery / APScheduler / 定时脚本？决定云上常驻进程形态（supervisor vs K8s Job）。
12. **是否需要 GPU**：本地推理 KURE/bge_m3 是否需要 GPU 加速，或纯 CPU 可接受？

---
*注：以上为产品评估与映射，不含完整架构图与实施步骤（交由对口架构/实施专家）。所有 ⚠️项请以腾讯云控制台或 MigraQ 复核为准。*
