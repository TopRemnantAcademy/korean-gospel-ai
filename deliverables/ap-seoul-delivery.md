# AI Gospel (korean-gospel-ai) → 腾讯云韩国首尔 (ap-seoul) 迁移实施方案

> 角色：交付实施工程师（delivery-engineer）
> 范围：本地 → 腾讯云 ap-seoul 的**实施步骤 / 割接 / 排期**（网络、DBA、云产品）
> 输入：product-expert `ap-seoul-product-mapping.md`、landing-zone `ap-seoul-landing-zone.md`、cloud-architect `ap-seoul-architecture.md`、仓库既有 `docker-compose.prod.yml` / `Dockerfile` / `Dockerfile.ui` / `scripts/migrate_sqlite_to_postgres.py` / `backend/app/config.py`
> 形态硬约束：**容器化**；节奏 **先 CVM(Docker Compose)+CLB 快速上线，再演进 TKE**。
> ⚠️ 本环境无法调用 MigraQ；所有「⚠️待复核」项需控制台 / MigraQ 二次确认。

---

## 0. 关键约束与既有事实（实施基线）

| 项 | 取值 / 事实（来自仓库与上游产出） |
|----|-----------------------------------|
| 容器形态 | 已具备 `docker-compose.prod.yml`：服务 `qdrant`(server v1.13.4) + `backend`(FastAPI :8000) + `ui`(Streamlit :8501)；CLI 演进 TKE |
| 关系库现状 | 当前 SQLite `.gospel.db`（WAL 模式）；代码 `backend/app/db.py` 以 `DATABASE_URL` 环境变量优先，设 `postgresql://...` 即切 PG |
| SQLite→PG 工具 | 已存在 `scripts/migrate_sqlite_to_postgres.py`（依赖 Alembic `upgrade head` 先建表） |
| Qdrant 现状 | 当前 **embedded**（`.qdrant_local` 单进程锁）；prod compose 已为 **server 模式**（`QDRANT_URL=http://qdrant:6333`，`qdrant_config.yaml` 带 `api_key`） |
| 配置加载 | `backend/app/config.py` 用 pydantic-settings，默认读仓库根 `.env`，但**操作系统环境变量优先**；密钥现经 compose `environment` 注入 |
| CORS | `cors_origins` 当前含 `http://127.0.0.1:4174`；上线须改为生产域名 |
| 静态 | PWA 构建产物（当前 `:4174` 服务），迁 COS+CDN(HTTPS) |
| 出站 | LLM(DeepSeek/混元)、임베딩(KURE)/리랭크(bge_m3)、Langfuse 经 NAT 出网 |
| ingest | `scripts/index_sermons.py` / `ingest_documents.py` 等；需常驻执行体（CVM: systemd/supervisor；TKE: Job/CronJob） |

> 实施中不重画 VPC/网络/架构，直接沿用 Landing Zone 与架构师产出（CIDR `10.0.0.0/16`、2 AZ、仅 CLB 公网入口、NAT 出网）。

---

## 1. 迁移总体阶段划分（Wave）

采用 **6 波次 + 准备期** 推进。每波独立可验证、可回退；波次间依赖已在「关键依赖」标注。

| Wave | 名称 | 目标 | 核心产出 | 退出标准（Definition of Done） |
|------|------|------|----------|--------------------------------|
| **P0** | 准备与复核 | 账户/权限就绪，待确认项闭环 | 主账号+子账号；复核清单结论；生产域名/证书预案 | 所有 ⚠️待复核项已确认或有临时决策；域名/证书计划锁定 |
| **W1** | 基础环境 | 网络、安全、可观测、密钥底座 | VPC/子网/路由/NAT/CLB/SG、CAM 角色、SSM、KMS、CLS、WAF | 私有子网互通、NAT 出网可达、`SSM GetSecret` 在节点成功、CLS 收到测试日志 |
| **W2** | 数据层 | 关系库 PG + 向量库 Qdrant 落地 | TencentDB for PostgreSQL(主备跨AZ)、自托管 Qdrant server(副本≥2)、备份桶 | PG `alembic upgrade head` 通过；Qdrant 集合 `gospel_kure` 恢复且 `count` 一致；备份到 COS 验证 |
| **W3** | 应用容器化 | 后端/UI 上云、经 CLB 暴露 | 镜像推送 TCR、CVM×2(Docker Compose)或 TKE、CLB 挂接、SSM 注入密钥 | `/health` 通过；CLB 转发 443→8000/8501 成功；端到端 `/chat` 返回 |
| **W4** | PWA / CDN | 静态站上线 | COS 桶 + CDN + HTTPS 证书、CORS/域名切换 | PWA 经 CDN(HTTPS) 加载；CORS 生产域名放行；API 调用成功 |
| **W5** | 割接切换 (Cutover) | 流量切换、旧环境下线 | DNS 切换/停机窗口、最终数据同步、回滚预案 | 100% 流量到 ap-seoul；冒烟测试全绿；旧环境保留只读备份 |
| **W6** | 观察期 | 稳定与调优 | 监控告警、性能基线、DR 演练 | 7 天无 P1 故障；指标基线建立；回滚预案已验证 |

**关键依赖 / 可并行项**
- 依赖链：`W1 → W2 → W3 → W4 → W5` 主线串行；`W2 的 Qdrant 恢复` 依赖 `W1 NAT 出网`（仅当 임베딩 走 API）；`W4(PWA)` 可与 `W3` **并行**（静态与后端解耦）。
- 可并行：`W1` 内「CAM/SSM/KMS/CLS 配置」与「VPC/网络搭建」并行；`W2` 内「PG 建库」与「Qdrant 节点就绪」并行；`W4` 与 `W3` 并行；`W6` 观察期与日常运营并行。

---

## 2. 逐组件实施步骤（可执行级）

### 2.1 网络 / 基础底座（W1）

> 以下步骤兼容「CVM+Compose」与后续「TKE」两种形态。可用控制台、CLI（`tccli`）或 Terraform（`tencentcloud` provider，⚠️需确认 provider 版本支持 ap-seoul）。

**2.1.1 账号与权限（沿用 Landing Zone §1）**
1. 主账号仅保留计费/紧急恢复；创建子账号：`ops-deploy`(部署)、`db-admin`(数据库)、`readonly`(审计)、`cicd-role`(CI/CD)、`security-audit`。
2. 所有子账号强制 **MFA**；CAM 策略遵循最小权限 + 显式 `Deny` 删除审计日志。
3. 创建 **CAM 实例角色**（CVM/TKE 节点用）：授予访问 `COS(备份桶)`、`CLS(写日志)`、`KMS(解密)`、`SSM(读密钥)` 的权限；**禁止静态 AK/SK 注入容器**。

**2.1.2 VPC / 子网 / 路由（沿用 LZ §2，CIDR 固定）**
1. 建 VPC `10.0.0.0/16`（ap-seoul）。
2. 公有子网：`10.0.0.0/24`(az1)、`10.0.1.0/24`(az2) — 放 NAT/跳板。
3. 私有-应用：`10.0.10.0/24`(az1)、`10.0.11.0/24`(az2) — 放 FastAPI/Streamlit/Qdrant 节点。
4. 私有-数据：`10.0.20.0/24`(az1,master)、`10.0.21.0/24`(az2,standby) — 放 PostgreSQL/Redis。
5. 私有-Vector（可选独立）：`10.0.30.0/24`(az1)、`10.0.31.0/24`(az2)；或并入应用子网。
6. 路由表：公有 `0.0.0.0/0 → IGW`；各私有子网 `0.0.0.0/0 → NAT 网关`。
7. ⚠️确认 ap-seoul 实际 AZ 数量与命名（对齐 LZ 假设 2–3 个）。

**2.1.3 NAT 网关 + EIP（出网统一出口）**
1. 在公有子网建 **NAT 网关**并绑定 **EIP**，承载所有私有子网出向（LLM/임베딩/리랭크/Langfuse/包下载/DB 补丁）。
2. 成本注意：NAT 出流量按量计费（主要变动成本），开通**流量告警**。

**2.1.4 安全组（最小端口，沿用 LZ §3.1）**
- `SG-CLB`：入 `443/80 ← 0.0.0.0/0`；出到 `SG-App` 的 `8000/8501/8502`。
- `SG-App`：入 `8000/8501/8502 ← SG-CLB`、`6333/6334 ← SG-App`(Qdrant 同层)、`22 ← SG-Bastion`、健康检查 `← 10.0.0.0/16`；出 `5432/6379 → SG-Data`、`0.0.0.0/0 → NAT`。
- `SG-Data`：`5432 ← SG-App`、`6379 ← SG-App`、**拒绝公网**。
- `SG-Bastion`（可选）：`22 ← 企业出口固定 CIDR`（**勿写 0.0.0.0/0**）。

**2.1.5 CLB（唯一公网入口）+ WAF**
1. 建**公网型应用型 CLB**（跨 AZ 多可用区），监听 `443`(HTTPS，SSL 终止) + `80`(仅 301 跳转)。
2. 两个监听器/转发规则：`/` → backend `:8000`；`/ui`、`/admin` 或独立域名 → ui `:8501`；健康检查路径 `/health`（后端已提供）。
3. CLB 前挂 **WAF**：防 SQLi/XSS（尤其 `/admin/*`、`/chat`）；CC 限流；配合应用层 `RATE_LIMIT_ENABLED`。
4. ⚠️确认 ap-seoul CLB 跨 AZ 分发能力与 WAF 规则模板粒度。

**2.1.6 密钥 / 加密（SSM + KMS）**
1. 在 **ap-seoul** 建 KMS 密钥（限定仅本项目 CAM 角色使用）。
2. 将以下密钥全部录入 **SSM（密钥管理）**，**禁止写入 `.env`/镜像/仓库**：
   `ADMIN_API_KEY`、`APP_PASSWORD`、`DIFY_API_KEY`、`QDRANT_API_KEY`、`DEEPSEEK_API_KEY`(或 `TENCENT_API_KEY`)、`GOOGLE_API_KEY`、`OPENAI_API_KEY`、`ANTHROPIC_API_KEY`、`LANGFUSE_PUBLIC_KEY`、`LANGFUSE_SECRET_KEY`、PostgreSQL 密码。
3. 设置 SSM 密钥**定期轮换**（如 90 天）；SSL 证书由证书服务托管自动续期。
4. **CVM 注入方式**：节点绑定 CAM 实例角色，部署时由 `ssm-agent`/引导脚本拉取并 `export` 为环境变量（或写运行时 `.env`，权限 600，不入库）。**TKE 方式**：`Secret` + KMS 加密 etcd，或用 External Secrets Operator 从 SSM 同步。

**2.1.7 可观测（CLS + 云监控）**
1. 建 CLS 日志集：采集 CVM/TKE 容器日志、Qdrant/后端应用日志、CLB 访问日志、ingest 失败日志。
2. 告警：CLB 5xx、CVM CPU/内存、PG 连接数、Qdrant 内存、NAT 出流量突增、ingest 失败。
3. 开启 **CloudAudit**（操作审计，禁止子账号删审计）+ TencentDB SQL 审计。

**退出验证**：从私有子网节点 `curl https://api.deepseek.com` 经 NAT 可达；节点 `tccli ssm GetSecret` 成功；CLS 收到一条测试日志；SG 互信端口连通性测试通过。

---

### 2.2 DBA：SQLite → TencentDB for PostgreSQL（W2）

> 代码已支持：`backend/app/db.py` 中 `DATABASE_URL` 环境变量优先；仓库已有 Alembic 迁移（`backend/migrations/versions/*`）与 `scripts/migrate_sqlite_to_postgres.py`。

**2.2.1 建库（W2 起）**
1. 建 **TencentDB for PostgreSQL**：生产档 **4C8G~8C16G 双节点（一主一备，跨 AZ）**，版本 ⚠️确认 ap-seoul 支持 15/16；开启 **KMS 存储加密 + SSL 连接 + 自动备份（日备+WAL 归档 PITR）**。
2. 建 **TencentDB for Redis**（1–4GB 标准主从，跨 AZ）：用于限流/缓存/Celery broker；开启密码/ACL。
3. 建 COS **备份桶**（首尔，SSE-KMS），用于 DB 快照、Qdrant snapshot、PDF/성경 数据。

**2.2.2 Schema 迁移（Alembic）**
```bash
# 在任意可连 PG 的节点/本地
export DATABASE_URL="postgresql+psycopg2://<user>:<pwd>@<pg-internal-endpoint>:5432/<db>"
cd backend
pip install alembic psycopg2-binary
alembic upgrade head        # 在空 PG 上跑通，验证方言/类型无差异（架构师 R7）
```
- ⚠️复核：PostgreSQL 与 SQLite 字段类型差异（如 JSON/布尔/自增）、`server_default` 行为，确保 `alembic upgrade head` 零报错。

**2.2.3 数据迁移（SQLite → PG）**
```bash
# 本地/跳板机执行，源为 .gospel.db，目标为云 PG
pip install sqlalchemy psycopg2-binary
python scripts/migrate_sqlite_to_postgres.py \
    --sqlite .gospel.db \
    --postgres "$DATABASE_URL" \
    --batch 500
# 先用 --dry-run 确认行数，再正式执行
```
- 该脚本按外键依赖顺序（category→subscriber→token_usage→conversation_history→salvation_journey→audit_log→document_chunk→glossary_entry→draft）迁移；对目标表先 `TRUNCATE ... CASCADE`（幂等，但**生产执行前务必备份目标库**）。
- 注意：脚本目标表清单为当前默认；若后续 Alembic 新增表（如 `support_ticket`、`e_glossary_terms`、`token_quota`/`subscription`、`crisis_bypass`/`eval`、`document_drafts`），需**同步更新 `DEFAULT_TABLE_ORDER`** 再跑。

**2.2.4 一致性校验**
```sql
-- 源(SQLite) 与目标(PG) 逐表行数比对
SELECT 'subscriber', count(*) FROM subscriber
UNION ALL SELECT 'conversation_history', count(*) FROM conversation_history
-- ... 覆盖全部迁移表
```
- 行数一致 + 抽样关键记录（如最近订阅者、audit_log 最新条）内容一致 → 通过。
- 将 `.gospel.db` 原始文件与导出的 SQL 各存一份到 COS 备份桶，作为回滚底稿。

**退出验证**：PG 连接串下应用 `init_db()` 不报错；`/health` 或 `/admin` 读取 PG 数据成功；备份任务将 PG 自动备份落到 COS。

---

### 2.3 Qdrant：embedded → 自托管 server（W2）

> 决策：自托管 Qdrant server（CVM/TKE），沿用 `docker-compose.prod.yml` 的 `qdrant/qdrant:v1.13.4` server 模式；集合 `gospel_kure`（KURE 1024 维）。解除 embedded 单锁。

**2.3.1 解除单锁的核心动作（snapshot 迁移）**
embedded 模式不暴露 API，无法在线 snapshot，标准路径是**临时起一个 Qdrant server 指向 embedded 存储目录，再经 API 导出 snapshot**：

```bash
# (A) 本地临时起 server，把 embedded 存储挂为 server 存储
docker run -d --name qdrant-bridge -p 6333:6333 \
  -v "$PWD/.qdrant_local:/qdrant/storage" \
  qdrant/qdrant:v1.13.4

# (B) 对集合做 snapshot（在 bridge 实例上）
curl -X POST http://localhost:6333/collections/gospel_kure/snapshots
# 记下返回 snapshot 名，下载
curl -o gospel_kure.snapshot \
  http://localhost:6333/collections/gospel_kure/snapshots/<snapshot_name>

# (C) 上传到云上 Qdrant server（先确保云实例已起、集合已建）
#    方式一：recover 接口
curl -X PUT http://<cloud-qdrant>:6333/collections/gospel_kure/snapshots/recover \
  -H "Content-Type: application/json" \
  -H "api-key: $QDRANT_API_KEY" \
  -d '{"location":"<cos-or-http-url-of-snapshot>"}'
#    方式二：先 upload 再 recover（大文件推荐先传 COS 再给 location）
docker stop qdrant-bridge
```
- 若版本一致且集合不大，也可直接将 `.qdrant_local` 目录**整体拷贝**到云 server 的 `/qdrant/storage` 后启动（同磁盘格式）；但 snapshot 方式更干净、可校验，优先采用。
- ⚠️核对 `gospel_kure` 向量条数 / 存储量（架构师 R8）→ 定 Qdrant 节点内存（**M5 内存型优先**）。

**2.3.2 云端 Qdrant 部署（server 模式）**
1. 节点置于私有-应用 / 私有-Vector 子网（SG-App/SG-Qdrant 仅放行 `6333/6334 ← SG-App`）。
2. 挂载**云硬盘（SSD/高性能）**到 `/qdrant/storage`，开定期**快照**。
3. HA：Qdrant `replication_factor≥2`（2 节点跨 AZ 各持副本）；或后续 `cluster` 模式分片。**副本同步走内网**，不开公网。
4. 启用 `qdrant_config.yaml` 的 `api_key` + 内网 TLS（后端 `QDRANT_URL=http://qdrant:6333` 已就绪）。
5. 后端/ingest 通过内网 `:6333` 访问；副本间 `6333` 互信。

**退出验证**：`GET /collections/gospel_kure` 返回 `status=green` 且 `vectors_count` 与源一致；一次 `/search` 返回合理结果；副本节点 `count` 一致；snapshot 已落 COS 备份桶。

---

### 2.4 应用容器化：FastAPI / Streamlit（W3）

> 沿用仓库 `Dockerfile` / `Dockerfile.ui` / `docker-compose.prod.yml`。关键改造：**密钥改 SSM 注入、SQLite 改 PG、CORS 改生产域名、data 目录改 COS 来源**。

**2.4.1 镜像构建与推送（TCR）**
```bash
# 在 CI/CD 或本地，登录 TCR（ap-seoul 地域）
docker build -f Dockerfile -t ccr.ccs.tencentyun.com/<ns>/korean-gospel-backend:prod .
docker build -f Dockerfile.ui -t ccr.ccs.tencentyun.com/<ns>/korean-gospel-ui:prod .
docker push ccr.ccs.tencentyun.com/<ns>/korean-gospel-backend:prod
docker push ccr.ccs.tencentyun.com/<ns>/korean-gospel-ui:prod
```
- **禁止** `COPY .env` 进镜像；镜像仅含代码（`Dockerfile.ui` 已最小化，不挂后端 `.env`/DB，符合安全基线）。
- Qdrant 用官方镜像 `qdrant/qdrant:v1.13.4`，不自制。

**2.4.2 生产 `docker-compose.prod.yml` 改造（CVM 阶段）**
相对现有 compose，需调整：
1. `backend.environment` 中：
   - `DATABASE_URL=postgresql+psycopg2://<pg-user>:<pwd>@<pg-internal>:5432/<db>`（**值从 SSM 注入，不写死**）；
   - `QDRANT_URL=http://qdrant:6333`（同网络，已就绪）；
   - `CORS_ORIGINS` 改为 `https://m.gospel.ai,https://<api-domain>`（去掉 `127.0.0.1:4174`）；
   - `APP_ENV=prod`；
   - LLM/임베딩/Langfuse/密钥类变量从 SSM 注入（见 2.1.6）。
2. **去掉** `.gospel.db:/app/gospel.db` 挂载（改 PG 后不再需要本地 SQLite）。
3. `data` 目录：설교 PDF/성경 等由 **COS 下载到本地卷** 或挂 **CFS**；ingest 从该路径读取（见 2.6）。
4. `ui.environment`：`API_BASE=http://backend:8000`（内网，已就绪）。
5. 节点绑定 CAM 实例角色；启动前由引导脚本从 SSM 拉密钥并 `export`，再 `docker compose up -d`。

**2.4.3 CVM 部署 + CLB 挂接**
1. 起 **2 台 CVM**（S5.2XLARGE16，跨 AZ：az1/az2），各自 `docker compose up -d`，均注册到同一 CLB 后端（健康检查 `/health`）。
2. CLB 监听 `443` → 后端 `8000`；`/ui` 或独立域名 → `8501`；`80` 仅 301。
3. 滚动发布：停一台 → 拉新镜像 → 起 → 切另一台（零中断）。
4. ⚠️如 Qdrant 与 backend 同机，注意内存争抢；规模大时 Qdrant 独立内存型节点。

**2.4.4 TKE 阶段（演进，可选/后续）**
- 用 `Deployment` 部署 backend/ui（replicas≥2 + `PodDisruptionBudget` + `maxUnavailable=1`）；Qdrant 用 `StatefulSet`（含 PVC 云硬盘）。
- 密钥用 `Secret`（KMS 加密）+ External Secrets Operator 从 SSM 同步；配置用 `ConfigMap`。
- CLB 用 **CLB 型 Ingress / Service** 暴露 443。
- 触发时机见架构师 §2.5（弹性需求、ingest 编排、多服务治理、团队 K8s 能力）。

**退出验证**：`curl -k https://<clb>/health` 返回 200；`/chat` 端到端返回（检索→LLM→答案）；UI 经 CLB 可达；CLB 健康检查全绿；SSM 注入的密钥被正确读取（日志无 `None`/缺密钥告警）。

---

### 2.5 PWA 静态站：COS + CDN（W4，可与 W3 并行）

1. 构建 PWA：仓库内 `mobile`/前端构建产物（当前 `:4174` 服务），产出静态文件。
2. 上传至 **COS 首尔桶**（标准存储 + 静态网站托管），开启 **SSE-KMS**。
3. 配 **CDN** 加速（韩国/全球节点），绑定**自定义域名 + SSL 证书（免费 DV）**，强制 HTTPS + HSTS。
4. **CORS**：将 `http://127.0.0.1:4174` 改为生产域名（如 `https://m.gospel.ai`），并同步 FastAPI `cors_origins`。
5. ⚠️确认 COS 首尔桶多 AZ、CDN 加速区域、自定义域名与韩国合规/备案要求。

**退出验证**：`https://<cdn-domain>/` 加载 PWA；浏览器控制台无 CORS 错误；API 调用（经 CLB）成功；HTTPS 证书有效（A+ 评级）。

---

### 2.6 ingest 后台作业编排（W3 内，常驻执行体）

> 风险：ingest 必须常驻/可调度，否则索引停滞（product-expert 风险#2）。

**CVM 阶段（supervisor / systemd）**
1. ingest 节点复用应用 CVM 或独立 worker 节点（若 임베딩/리랭크 本地推理，建议 **C6 计算型** 或独立节点，避免抢占在线）。
2. 用 `systemd` 守护常驻进程；定时用 `systemd timer` 或应用内 `APScheduler` 触发 `scripts/index_sermons.py`。
3. 触发三选一：A. 每日 Cron（新增 설교）；B. Admin 上传事件 → 队列（Redis/Celery）；C. 手动 `python -m scripts.index_sermons [--reset]`。
4. 数据来源：`data/documents` 由 COS 同步到本地卷（或挂 CFS）；임베딩/리랭크 走 API 则经 NAT 出网（成本监控）。
5. 日志落 CLS；失败触发云监控告警；定期校验 `gospel_kure` `vectors_count` 增长。

**TKE 阶段（推荐，Job / CronJob）**
- 常驻：`Deployment`（带 `restartPolicy`）+ 定时批量 `CronJob`；大重索引用 `Job`（backoff/retry），设 `resources.limits` 隔离，避免与在线争抢。

**退出验证**：手动触发一次 ingest，新 문서出现在 `gospel_kure`；定时任务按预期运行；失败场景产生告警且可重试。

---

## 3. 割接（Cutover）方案（W5）

### 3.1 切换策略
- **推荐：蓝绿 + 短停机窗口**（数据最终同步）。理由：有状态数据（PG/Qdrant）需保证 RPO，纯停机风险高；PWA 静态与后端解耦，可先切静态、再切 API。
- 前置：W1–W4 全部完成且验证通过；生产域名与 SSL 就绪；回滚预案演练过。

### 3.2 割接步骤（建议维护窗口，如韩国时间低峰 02:00–04:00）
1. **冻结写（短暂）**：进入维护态，应用层将写接口限流/只读（或在源站暂停 ingest 与写），确保最终同步窗口 RPO 内。
2. **最终增量同步**：
   - PG：停止源写后，做一次 **WAL/逻辑增量** 或重新 `migrate_sqlite_to_postgres.py`（仅变更表）；或依赖托管 PG 持续复制（若源也在云则 DTS，⚠️源在本地则用导出导入）。
   - Qdrant：对 `gospel_kure` 再打一次 **snapshot** 并 recover 到云（增量仅新增向量，量小可直接全量重做）。
   - COS：同步最新 PDF/성경 数据到首尔桶。
3. **切换 DNS / 域名**：将生产域名（API + PWA）CNAME/解析指向 **CLB 公网地址 / CDN 域名**。TTL 提前调小（如 60s）以加速传播。
4. **去只读**：放开云上写接口；启动云上 ingest 常驻执行体。
5. **旧环境**：保留只读/下线，先不删（保留 7~30 天作回滚底稿）。

### 3.3 回滚预案
- **触发条件**：割接后核心链路（/health、/chat、PWA 加载、PG 读写、Qdrant 检索）任一 P0/P1 失败且 15 分钟内无法修复。
- **回滚动作**：DNS 解析切回旧环境（因 TTL 已调小，分钟级生效）；云上停写、旧环境恢复写；数据以旧环境为准（割接窗口短，云上新增数据量少，可接受丢弃或补同步）。
- **关键**：回滚只切流量，不动云上数据；云资源保留便于二次割接。

### 3.4 验证清单（割接后冒烟）
- [ ] `https://<api-domain>/health` = 200（CLB 多 AZ 全绿）
- [ ] `/chat` 端到端：检索(Qdrant)→LLM(经 NAT)→返回，含 한국어
- [ ] PWA `https://<pwa-domain>/` 加载无 CORS/证书错误
- [ ] PG 读写：订阅/对话历史落库并可查
- [ ] Qdrant `vectors_count` 与割接前一致
- [ ] Redis 限流生效（高频请求被拦）
- [ ] WAF/CLB 5xx < 阈值；CLS 收到正常日志
- [ ] 出站 LLM/임베딩/Langfuse 经 NAT 可达且延迟可接受

---

## 4. 时间排期（用户要求 1 个月内启动）

> 甘特式里程碑（按「周」排期，T0 = 项目启动日）。假设并行人力充分；准备期可压缩。

| 周次 | 阶段 | 主要任务 | 里程碑（退出标准） | 依赖 / 并行 |
|------|------|----------|--------------------|-------------|
| **W0 (T0–T0+3d)** | P0 准备 | 主账号/子账号/CAM；⚠️复核清单闭环；域名/证书预案 | 复核项有结论；域名锁定 | 可并行：域名注册/证书申请 |
| **W1 (T0+3d–T0+1.5w)** | W1 基础环境 | VPC/子网/路由/NAT/CLB/SG；SSM/KMS/CLS/WAF；CAM 角色 | 网络互通+NAT 出网+SSM 拉取+CLS 日志 | 并行：CAM 与网络搭建 |
| **W2 (T0+1.5w–T0+2.5w)** | W2 数据层 | 建 PG/Redis/COS；Alembic 建表；SQLite→PG 迁移+校验；Qdrant server+snapshot 恢复 | PG `upgrade head` 通过；Qdrant count 一致；备份到 COS | 并行：PG 建库 与 Qdrant 节点就绪 |
| **W3 (T0+2.5w–T0+3.5w)** | W3 应用 | 镜像构建推送 TCR；CVM×2 Compose；CLB 挂接；SSM 注入；ingest 常驻 | 端到端 `/chat` 成功；CLB 绿 | 并行：W4 |
| **W4 (T0+2.5w–T0+3.5w)** | W4 PWA/CDN | 构建上传 COS；CDN+HTTPS；CORS/域名切换 | PWA 经 CDN(HTTPS) 加载成功 | 与 W3 并行 |
| **W5 (T0+3.5w–T0+4w)** | W5 割接 | 维护窗口：冻结写→最终同步→DNS 切换→去只读→旧环境保留 | 100% 流量到 ap-seoul；冒烟全绿 | 依赖 W1–W4 |
| **W6 (T0+4w–T0+5w)** | W6 观察 | 监控/告警/性能基线；DR 演练；回滚预案验证 | 7 天无 P1；基线建立 | 与运营并行 |

- **关键依赖**：W2 依赖 W1（网络/SSM）；W3/W4 依赖 W2（数据）；W5 依赖全部。
- **可并行**：W4 与 W3 并行；W1 内部 CAM/网络并行；W2 内 PG 与 Qdrant 并行。
- **1 个月内启动**含义：T0+4w 完成割接上线；观察期顺延 1 周。若 K8s 经验充足，可把 W3 直接定为 TKE（省 CVM 阶段）。

---

## 5. 每阶段验证 / QA

| Wave | 验证维度 | 具体方法 / 工具 |
|------|----------|-----------------|
| W1 | 连通性 | 私有子网 `curl` NAT 出网；节点 `tccli ssm GetSecret`；SG 端口 `nc`/`telnet` 互信测试；CLS 测试日志 |
| W2 | 数据一致性 | Alembic 无报错；`migrate` 行数比对脚本；`gospel_kure` `vectors_count` 源=云；备份落 COS 校验 |
| W3 | 功能/性能基线 | `/health`、端到端 `/chat` 返回；`wrk`/`locust` 压测取基线 QPS/延迟；CLB 多 AZ 健康检查 |
| W4 | 静态/CORS | 浏览器加载 PWA 无报错；CORS 生产域名放行；CDN 命中率；SSL 评级 |
| W5 | 割接冒烟 | §3.4 清单逐项勾选；DNS 传播检查（`dig`/多地）；回滚演练 |
| W6 | 稳定/DR | 7 天告警趋势；PG PITR 恢复演练；Qdrant snapshot 回灌演练；IaC 一键拉起验证 |

> 性能基线（W3）务必在割接前建立，作为 W6 对比基准与容量决策依据。

---

## 6. 割接风险与缓解

| # | 风险 | 触发/表现 | 缓解措施 |
|---|------|-----------|----------|
| C1 | **数据不一致**（PG/Qdrant 割接窗口增量丢失） | 最终同步遗漏写 | 割接前冻结写 + 短窗口；PG 增量重跑 / Qdrant 再 snapshot；校验 count 一致后才去只读 |
| C2 | **DNS  propagation 慢** | 部分用户仍命中旧环境 | 提前将 TTL 调小(60s)；分批解析/灰度；保留旧环境只读 |
| C3 | **SSL 证书问题** | 证书未签发/域名不匹配→PWA 无法 HTTPS | W1/P0 提前申请 DV 证书并校验；CLB/WAF 绑定前 `openssl` 校验 |
| C4 | **密钥缺失 / 注入失败** | 云上读不到 SSM → 应用启动报缺密钥 | W1 验证 `GetSecret`；compose 启动前 `export` 检查；日志告警缺密钥 |
| C5 | **LLM 出网中断 / 高延迟** | NAT 到 DeepSeek/混元 不可达或超时 | 用项目已有 openai/anthropic **fallback 链**；后端超时+重试退避；关键路径降级（无 LLM 返回检索摘要）；⚠️确认端点区域与延迟 |
| C6 | **Qdrant 恢复失败 / 规模误判** | snapshot recover 报错或内存不足 OOM | W2 先小集合演练；⚠️核对 `vectors_count`/存储定内存(M5)；副本跨 AZ |
| C7 | **回滚触发** | 割接后 P0/P1 15min 内不可修 | 见 §3.3：DNS 切回旧环境（分钟级），云上数据保留便于二次割接 |
| C8 | **CORS 未改全** | PWA 调 API 被拦 | W4 同步改 `cors_origins` 生产域名 + CLB CORS；浏览器实测 |
| C9 | **NAT 成本激增** | 出站 LLM/임베딩 流量超预期 | W1 开流量告警；限流；评估 임베딩/리랭크 本地推理降本 |
| C10 | **PIPA 合规（韩国 PII）** | users/subscribers 出境/无加密/无审计 | 全部资源 ap-seoul；TLS+KMS；CLS/CloudAudit；保留/撤回策略；⚠️确认是否需 DPIA |

---

## 7. 工具与待复核

**实施工具**
- 控制台（Web 控制台）：VPC/CLB/NAT/CAM/SSM/KMS/CLS/TencentDB/Redis/COS/CDN/WAF。
- CLI：`tccli`（推荐脚本化）、`kubectl`（TKE 阶段）、`docker` / `docker compose`。
- IaC（可选）：Terraform `tencentcloud` provider 或腾讯云 **Terraform/Go 编排**（⚠️确认 ap-seoul region 支持度；建议先控制台跑通再固化 IaC）。
- 数据库：`alembic`、`scripts/migrate_sqlite_to_postgres.py`、`pg_dump`/`psql`。
- 向量：Qdrant snapshot API、`qdrant-client`。
- 可观测：CLS、云监控、CloudAudit。

**⚠️待复核（控制台 / MigraQ 二次确认）**
1. **VectorDB 在 ap-seoul 是否可用 + Qdrant 兼容 API**（决定自托管 vs 托管，默认自托管）。
2. **LLM 端点调用路径**：`LLM_PROVIDER=tencent`(DeepSeek/混元) 能否从 ap-seoul 直连、延迟、配额、是否支持私有网络接入（影响 C5/R1/R4）。
3. **임베딩(KURE)/리랭크(bge_m3) 本地推理 vs 托管 API**（决定 CVM 规格与 NAT 成本）。
4. **Qdrant collection 规模**（gospel_kure 向量条数/存储量）→ 内存与实例规格（R8）。
5. **PostgreSQL vs MySQL、版本(15/16)** 在 ap-seoul 支持与 HA 架构；Redis 标准/集群架构。
6. **SSM / KMS / CLS / CAM / 云监控 / TKE / WAF / Redis** 在 ap-seoul 可用性与功能粒度。
7. **COS 首尔桶多 AZ、CDN 韩国/全球加速节点、自定义域名与韩国合规/备案**（PWA HTTPS 必须）。
8. **ap-seoul 实际 AZ 数量与命名**（对齐 LZ 假设 2–3 个）；CLB 跨 AZ 分发能力；NAT 规格与单价。
9. **LLM/임베딩/리랭크/Langfuse 是否跨境传输**（PIPA 出境影响，R5/R10）。
10. **是否需要 GPU**（本地推理 KURE/bge_m3 是否需 GPU 加速）。
11. **预算上限**（影响多 AZ/多实例/托管 vs 自托管/Redis/GPU 取舍）。
12. **PIPA 适用性**（是否收集韩国居民 PII？是否需 DPIA、保留期限、撤回机制）。
13. **ingest 触发方式**（Celery/APScheduler/定时脚本）→ 决定常驻进程形态（supervisor vs K8s Job）。

---

## 附录 A：生产 `docker-compose.prod.yml` 关键改造对照

| 项 | 现状（仓库） | 云上生产 |
|----|--------------|----------|
| DB | `./gospel.db` 挂载 + SQLite | 去掉挂载；`DATABASE_URL=postgresql+psycopg2://...@<pg>:5432/<db>`（SSM 注入） |
| Qdrant | server 模式已就绪 | 同；副本≥2；云硬盘 + snapshot 到 COS |
| 密钥 | compose `environment` 引 `${VAR}`（来自 `.env`） | 引导脚本从 SSM 拉取并 `export`，镜像/compose 不写死 |
| CORS | 含 `127.0.0.1:4174` | `CORS_ORIGINS=https://m.gospel.ai,https://<api>` |
| data | `./data` 绑定挂载 | COS/CFS 同步到本地卷，ingest 读取 |
| APP_ENV | 默认 dev | `prod`（禁 embedded、禁 `/docs` 暴露按需） |

## 附录 B：回滚决策树（简述）
```
割接后冒烟任一 P0/P1 失败
  ├─ 15min 内可修 → 修后复测
  └─ 不可修 → DNS 切回旧环境（TTL 已=60s，分钟级）
             云上停写、旧环境恢复写
             数据以旧环境为准（窗口短，增量可接受丢弃/补同步）
             云资源保留 → 修复后二次割接
```

---
*本文为实施交付文档，网络/架构沿用上游产出，不重画拓扑；所有 ⚠️项以腾讯云控制台 / MigraQ 复核为准。*
