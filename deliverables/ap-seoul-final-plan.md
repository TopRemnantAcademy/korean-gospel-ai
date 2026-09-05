# AI Gospel (korean-gospel-ai) → 腾讯云韩国首尔 (ap-seoul) 整体迁移方案（综合最终版）

> 主理人综合输出（Phase 6）
> 输入：product-expert、landing-zone-expert、cloud-architect、delivery-engineer-2、ops-engineer 五份阶段产出
> 范围：仅 korean-gospel-ai 项目（FastAPI + Streamlit 聊天/管理 + Qdrant + 移动端 PWA），本地 → 腾讯云 ap-seoul 首尔区
> 约束：本环境无法调用 MigraQ，基于标准腾讯云知识；所有不确定项以「⚠️待复核」标注，需控制台 / MigraQ 二次确认

---

## 0. 执行摘要（一页结论）

**目标**：把当前本地 Windows 单机运行（venv + 本地 embedded Qdrant + SQLite + PWA `:4174`）的系统，迁移到腾讯云韩国首尔区（ap-seoul），获得跨 AZ 高可用、托管数据层、可观测与合规底座。

**形态决策（硬约束 + 节奏）**
- 容器化是硬约束（仓库已具备 `Dockerfile` / `Dockerfile.ui` / `docker-compose.prod.yml`）。
- 上线节奏：**先 CVM(Docker Compose) + CLB 在 1 个月内快速上线，再演进到 TKE**。不为过度工程提前引入 K8s。
- 向量库：**自托管 Qdrant server 模式**（非 VectorDB），沿用现有 prod compose，零 SDK 改造，解除 embedded 单锁。
- 关系库：**TencentDB for PostgreSQL**（托管、跨 AZ 主备），替换 SQLite。
- 静态站：**COS + CDN（HTTPS）**，替换本地 `:4174`。
- 密钥：**SSM + KMS + CAM 实例角色**（临时凭证），禁止 `.env` / 镜像明文。

**时间线**：准备期 P0 + W1~W5 共 **T0~T0+4 周**完成割接上线，W6 观察期 +1 周。满足「1 个月内启动」要求（启动即可排期）。

**最大不确定项（决定规格/成本）**：① LLM 端点能否从 ap-seoul 直连及延迟；② 임베딩(KURE 1024)/리랭크(bge_m3) 本地推理 vs 托管 API；③ Qdrant 集合规模；④ 是否实际收集韩国居民 PII（PIPA 适用性）；⑤ 预算上限。

---

## 1. 目标架构总览

### 1.1 组件拓扑（单 VPC，跨 2 AZ）

```
                         ┌─────────────────────────────────────────────────────────┐
   모바일 PWA             │                    腾讯云 ap-seoul  (单 VPC)                │
   (手机/浏览器)          │                                                           │
        │ HTTPS           │   公有子网 (AZ-a)              公有子网 (AZ-b)            │
        │                 │   ┌──────────────┐            ┌──────────────┐          │
        ├─────────────────┼──▶│   CLB        │◀──健康│────│   CLB        │          │
        │                 │   │ (SSL终止/CORS)│  检查 ├────│ (跨AZ/多AZ)  │          │
        │                 │   └──────┬───────┘            └──────┬───────┘          │
        │                 │          │ 内网转发                   │                  │
        │                 │   私有子网 (AZ-a)              私有子网 (AZ-b)            │
        │                 │   ┌──────────────┐            ┌──────────────┐          │
        │                 │   │ CVM/TKE 节点  │            │ CVM/TKE 节点  │          │
        │                 │   │ ┌──────────┐ │            │ ┌──────────┐ │          │
        │                 │   │ │Streamlit│ │            │ │Streamlit│ │          │
        │                 │   │ │ (:8501)  │ │            │ │ (:8501)  │ │          │
        │                 │   │ ├──────────┤ │            │ ├──────────┤ │          │
        │                 │   │ │FastAPI  │ │            │ │FastAPI  │ │          │
        │                 │   │ │ (:8000)  │ │            │ │ (:8000)  │ │          │
        │                 │   │ └──────────┘ │            │ └──────────┘ │          │
        │                 │   │ ┌──────────┐ │            │ ┌──────────┐ │          │
        │                 │   │ │Qdrant srv│ │ 副本/集群  │ │Qdrant srv│ │          │
        │                 │   │ │ (:6333)  │◀─(自托管HA)─▶│ │ (:6333)  │ │          │
        │                 │   │ └──────────┘ │            │ └──────────┘ │          │
        │                 │   │ ┌──────────┐ │            │              │          │
        │                 │   │ │ingest   │ │ (常驻/Job)  │              │          │
        │                 │   │ └──────────┘ │            │              │          │
        │                 │   └──────┬───────┘            └──────────────┘          │
        │                 │          │                          │                    │
        │                 │   私有-数据子网                私有-数据子网               │
        │                 │   ┌──────────────┐            ┌──────────────┐          │
        │                 │   │ TencentDB PG │ 主备跨AZ   │ (备/只读副本) │          │
        │                 │   │  主(AZ-a)    │◀──同步───▶│   (AZ-b)     │          │
        │                 │   └──────────────┘            └──────────────┘          │
        │                 │   ┌──── NAT 网关(公有) ─▶ 公网 ─▶ LLM/임베딩/리랭크/Langfuse│
        │                 │   ┌──────────────┐   ┌──────────────┐  ┌──────────────┐│
        │                 │   │   COS 桶     │   │   CDN        │  │ CLS/云监控   ││
        │                 │   │ (静态+备份)  │──▶│ (PWA加速)    │  │ KMS/CAM/SSL  ││
        └─────────────────┼──▶└──────────────┘   └──────────────┘  └──────────────┘│
                         └─────────────────────────────────────────────────────────┘
```

### 1.2 部署位置与暴露方式

| 组件 | 部署层 | 暴露 | 互联 |
|------|--------|------|------|
| CLB（应用型） | 公有子网（跨 AZ） | 公网 EIP + HTTPS | 对内转发 443→8000/8501，SSL 终止/CORS/健康检查 |
| Streamlit UI (:8501) | 私有-应用子网 | 仅经 CLB | 调 `http://backend:8000`（内网） |
| FastAPI (:8000) | 私有-应用子网 | 仅经 CLB | 调 Qdrant(:6333)/PG(:5432)/Redis(:6379) 内网 |
| Qdrant server (:6333) | 私有子网 | 仅内网（SG 限 app 层） | 副本/集群跨 AZ，WAL 同步 |
| TencentDB PostgreSQL | 私有-数据子网 | 内网 VPC | 主备跨 AZ 同步，连接串不变 |
| TencentDB Redis（可选） | 私有子网 | 内网 | 限流/缓存/Celery broker |
| COS + CDN | 托管 | 公网 HTTPS | PWA 静态 + 备份桶 |
| NAT 网关 | 公有子网 | 私有子网统一出网 | 出站到 LLM/임베딩/리랭크/Langfuse |
| ingest 执行体 | 私有-应用子网 | 内网 | 常驻(supervisor/Deployment) 或 Job/CronJob |

> **关键**：PWA 与后端解耦——PWA 纯静态走 COS+CDN(HTTPS)；FastAPI/Streamlit 经 CLB 唯一公网入口。CORS `allow_origins` 由 `127.0.0.1:4174` 改为生产域名（如 `https://m.gospel.ai`）。SSL 在 CLB 终止，后端/UI 仅内网。

---

## 2. Landing Zone / 网络 / 安全

### 2.1 账号与权限模型
- 主账号：仅计费 / 紧急恢复（break-glass 凭证物理保管，日常禁用 AK/SK）。
- 子账号（强制 MFA）：`ops-deploy`(部署)、`db-admin`(数据库)、`readonly`(审计)、`cicd-role`(CI/CD)、`security-audit`(合规审计)。
- CAM 策略最小权限 + 显式 `Deny` 删除 CloudAudit/CLS 审计日志。
- **CAM 实例角色**（CVM/TKE 节点用）：授予访问 COS(备份桶)/CLS/KMS/SSM 的权限；**禁止静态 AK/SK 注入容器**。

### 2.2 网络规划（VPC 10.0.0.0/16，2 AZ）
| 子网 | CIDR | 用途 |
|------|------|------|
| 公有 | 10.0.0.0/24 (az1) / 10.0.1.0/24 (az2) | NAT / （可选跳板） |
| 私有-应用 | 10.0.10.0/24 (az1) / 10.0.11.0/24 (az2) | FastAPI / Streamlit / Qdrant 节点 |
| 私有-数据 | 10.0.20.0/24 (az1,master) / 10.0.21.0/24 (az2,standby) | PostgreSQL / Redis |
| 私有-Vector（可选独立） | 10.0.30.0/24 (az1) / 10.0.31.0/24 (az2) | 或并入应用子网 |

- 路由：公有 `0.0.0.0/0 → IGW`；各私有子网 `0.0.0.0/0 → NAT 网关`。
- **仅 CLB 公网入口**；所有 CVM/DB/Qdrant 无公网 IP。NAT 为私有子网统一出网。

### 2.3 安全组（最小端口）
- `SG-CLB`：入 443/80 ← 0.0.0.0/0；出到 `SG-App` 的 8000/8501/8502。
- `SG-App`：入 8000/8501/8502 ← SG-CLB；6333/6334 ← SG-App；22 ← SG-Bastion；出 5432/6379 → SG-Data；0.0.0.0/0 → NAT。
- `SG-Data`：5432 ← SG-App；6379 ← SG-App；**拒绝公网**。
- `SG-Bastion`（可选）：22 ← 企业出口固定 CIDR（**勿写 0.0.0.0/0**）。

### 2.4 加密 / 可观测 / 防护
- TLS + KMS：KMS 密钥限本项目 CAM 角色；SSM 托管全部密钥，90 天轮换；SSL 证书由证书服务托管自动续期。
- 可观测：CLS 采集容器/应用/CLB/ingest 日志；CloudAudit 操作审计（禁删）；TencentDB SQL 审计。
- WAF 挂 CLB：`/admin/*`、`/chat` 防 SQLi/XSS + CC 限流，配合应用层 `RATE_LIMIT_ENABLED`。
- NACL：子网层额外防线（公网仅放行 443/80）。

### 2.5 PIPA（韩国个人信息保护法）
- users/subscribers 属个人数据；全部资源驻留 ap-seoul 利于合规。
- 落实：传输/存储加密（SSL+KMS）、最小权限、访问审计（CLS/CloudAudit）、备份保留策略、必要时 DPIA 与用户撤回同意机制。
- ⚠️ 需用户确认是否实际收集韩国居民 PII 及合规要求（见 §9）。

---

## 3. 产品映射与规格

### 3.1 源 → 腾讯云产品映射

| 本地组件 | 腾讯云目标产品 | 决策 |
|----------|----------------|------|
| FastAPI / Streamlit（Docker） | CVM（Docker Compose）→ TKE | 决策 A：先 CVM 后 TKE |
| Qdrant embedded（单锁） | **自托管 Qdrant server 模式**（CVM/TKE） | 决策 B：非 VectorDB，避免 SDK/重灌 |
| SQLite（.gospel.db） | **TencentDB for PostgreSQL**（主备跨 AZ） | 决策 D |
| Redis（可选，限流/缓存） | TencentDB for Redis（主从） | 保留，MVP 可省 |
| 移动端 PWA（:4174 静态） | **COS + CDN（HTTPS）** | 决策 C |
| LLM / 임베딩 / 리랭크 / Langfuse | 经 NAT 出站公网调用 | 沿用现有 provider |
| 密钥（.env） | SSM + KMS + CAM 实例角色 | 零明文 |
| 日志/监控 | CLS + 云监控 + CloudAudit | — |
| 备份/静态资产 | COS（SSE-KMS，备份桶） | — |

### 3.2 规格档（ap-seoul）

| 产品 | 最小（验证/预发） | 生产建议 |
|------|-------------------|----------|
| CVM（应用） | S5.LARGE8（4C8G）×2 跨 AZ | S5.2XLARGE16（8C16G）×2；本地推理则需 C6 计算型 |
| TencentDB PG | 2C4G 双节点 | 4C8G ~ 8C16G 双节点（主备跨 AZ） |
| Redis | 1GB 标准主从 | 2–4GB 标准主从 |
| Qdrant 节点 | 内存型 M5（依集合规模） | M5 ×≥2（replication_factor≥2） |
| NAT / CLB / COS / CDN / WAF / KMS / CLS | 按量 | 按量 + 流量告警 |

---

## 4. 高可用（HA）与容灾（DR）

### 4.1 消除单点
| 层 | 方案 |
|----|------|
| 入口 | CLB 跨 AZ 多可用区，健康检查自动摘流 |
| app | 无状态 + 多副本（≥2，跨 AZ）+ CLB 轮询；TKE 用 PDB + HPA |
| Qdrant | 自托管 replica（replication_factor≥2）跨 AZ；或 cluster 分片 |
| 关系库 | TencentDB PG 主备跨 AZ 自动切换（秒~分钟级） |
| Redis | 标准主从，故障自动切换 |
| 出网 | NAT 网关本身多 AZ 高可用 |
| 静态 | COS 多 AZ + CDN 天然多节点 |

### 4.2 DR 档位（单地域内，同地域跨 AZ）
> ⚠️ **单区域限制**：ap-seoul 为单一地域，本方案为「同地域跨 AZ」高可用，**不提供地域级容灾**。整地域故障需另建异地（ap-tokyo / ap-singapore）复制，成本与 PIPA 出境合规显著上升——属后续可选项。

| 档位 | RPO | RTO | 手段 |
|------|-----|-----|------|
| 基础档（默认推荐） | DB ≤15min（PITR）；Qdrant ≤6h（日/定频快照） | ≤30–60min | PG 主备+自动备份；Qdrant 副本+日快照；CLB 跨 AZ |
| 增强档 | DB ≤5min；Qdrant ≤1h | ≤15min | 缩短备份窗口；提高 Qdrant 快照频率；预置热备 |
| 严档（需异地） | ≤5min | 数小时 | ⚠️ COS 跨区域复制 + 异地备用集群，超出单区域默认架构 |

- AZ 级故障：CLB 导向健康 AZ；PG 主备切换；Qdrant 副本接管——基本无感或分钟级恢复。
- **恢复演练**：季度演练 PG PITR、Qdrant 回灌、IaC 重建 app 层。

---

## 5. 分阶段实施（Wave）与时间排期

### 5.1 波次与退出标准

| Wave | 目标 | 核心产出 | 退出标准（DoD） |
|------|------|----------|------------------|
| **P0** 准备 | 账户/权限就绪，待确认项闭环 | 主/子账号；复核清单结论；域名/证书预案 | ⚠️项有结论或临时决策；域名/证书锁定 |
| **W1** 基础 | 网络/安全/可观测/密钥底座 | VPC/子网/NAT/CLB/SG、CAM、SSM、KMS、CLS、WAF | 私网互通+NAT 出网可达+SSM 拉取成功+CLS 收日志 |
| **W2** 数据 | PG + Qdrant 落地 | PG(主备跨AZ)、Qdrant server(副本≥2)、备份桶 | PG `alembic upgrade head` 通过；Qdrant count 一致；备份落 COS |
| **W3** 应用 | 后端/UI 上云 | 镜像推 TCR、CVM×2 Compose、CLB 挂接、SSM 注入 | `/health` 通过；端到端 `/chat` 返回 |
| **W4** PWA/CDN | 静态站上线 | COS+CDN+HTTPS、CORS/域名切换 | PWA 经 CDN(HTTPS) 加载；CORS 放行；API 成功 |
| **W5** 割接 | 流量切换 | DNS 切换/停机窗口、最终同步、回滚预案 | 100% 流量到 ap-seoul；冒烟全绿；旧环境保留只读 |
| **W6** 观察 | 稳定调优 | 监控告警、性能基线、DR 演练 | 7 天无 P1；基线建立；回滚预案验证 |

**关键依赖**：W1→W2→W3→W4→W5 主线串行；W2 Qdrant 恢复依赖 W1 NAT（仅当 임베딩 走 API）；**W4 与 W3 可并行**（静态与后端解耦）。

### 5.2 时间排期（T0 = 项目启动日）

| 周次 | 阶段 | 主要任务 | 里程碑 |
|------|------|----------|--------|
| W0 (T0–T0+3d) | P0 | 账号/CAM；⚠️复核闭环；域名/证书预案 | 复核有结论；域名锁定 |
| W1 (T0+3d–T0+1.5w) | 基础 | VPC/NAT/CLB/SG；SSM/KMS/CLS/WAF；CAM 角色 | 网络+NAT+SSM+CLS 通过 |
| W2 (T0+1.5w–T0+2.5w) | 数据 | 建 PG/Redis/COS；Alembic；SQLite→PG；Qdrant snapshot | PG upgrade head；Qdrant count 一致 |
| W3 (T0+2.5w–T0+3.5w) | 应用 | 镜像推 TCR；CVM×2 Compose；CLB；ingest 常驻 | 端到端 `/chat` 成功 |
| W4 (T0+2.5w–T0+3.5w) | PWA/CDN | 构建上传 COS；CDN+HTTPS；CORS | PWA 经 CDN 加载 |
| W5 (T0+3.5w–T0+4w) | 割接 | 冻结写→最终同步→DNS 切换→去只读 | 100% 流量到 ap-seoul |
| W6 (T0+4w–T0+5w) | 观察 | 监控/告警/基线；DR 演练 | 7 天无 P1 |

### 5.3 关键技术动作（可执行级要点）
- **SQLite→PG**：`DATABASE_URL=postgresql+psycopg2://...`；先空库 `alembic upgrade head` 验证方言/类型；再用 `scripts/migrate_sqlite_to_postgres.py --dry-run` → 正式 `--batch 500`；逐表行数校验；`.gospel.db` 存 COS 作回滚底稿。注意同步 `DEFAULT_TABLE_ORDER` 与新增 Alembic 表。
- **Qdrant embedded→server**：本地临时起 `qdrant-bridge` 指向 `.qdrant_local` → `POST /collections/gospel_kure/snapshots` → 下载 → 云端 server `recover`。挂云硬盘，副本跨 AZ，定期 snapshot 到 COS。⚠️核对 `vectors_count`/存储定内存（M5）。
- **应用容器化**：构建 backend/ui 镜像推 TCR，**禁止 COPY .env**；compose 改 `DATABASE_URL`(SSM 注入)、`CORS_ORIGINS`(生产域名)、`APP_ENV=prod`、去掉 SQLite 挂载、data 改 COS/CFS 来源；2 台 CVM 跨 AZ 注册同一 CLB；滚动发布零中断。
- **PWA**：构建产物传 COS(首尔, SSE-KMS) + CDN(自定义域名+DV 证书, 强制 HTTPS)；同步 CORS 改生产域名。
- **ingest**：必须常驻/可调度执行体（CVM: systemd/supervisor；TKE: Deployment+CronJob/Job），失败告警 + 定期 `vectors_count` 健康校验，否则索引停滞。

---

## 6. 割接（Cutover）方案

- **策略**：蓝绿 + 短停机窗口（数据最终同步）。PWA 静态与后端解耦，可先切静态、再切 API。
- **步骤（建议韩国时间低峰 02:00–04:00）**：
  1. 冻结写（应用层限流/只读，停源站 ingest）。
  2. 最终增量同步：PG（WAL/逻辑增量或重跑迁移）、Qdrant（再 snapshot recover）、COS（同步最新 PDF/성경）。
  3. 切换 DNS：生产域名 CNAME/解析指向 CLB/CDN；**TTL 提前调小至 60s**。
  4. 去只读，启动云上 ingest 常驻。
  5. 旧环境保留只读 7~30 天作回滚底稿（先不删）。
- **回滚**：割接后任一 P0/P1 15min 内不可修 → DNS 切回旧环境（分钟级）；云上停写、旧环境恢复写；数据以旧环境为准（窗口短，增量可接受丢弃/补同步）；云资源保留便于二次割接。

---

## 7. 运营交接 / 培训 / SLO

### 7.1 交接清单（H1–H12）
架构/网络文档、应用 HA/DR 文档、Runbook/应急预案、SSM 密钥清单、CLS/CloudAudit、监控告警、CAM 角色权限、升级链路(on-call 排班/L1–L4)、IaC/部署物、数据字典/Alembic、成本基线、PIPA 合规材料。

**验收（Go/No-Go）**：交接检查单全勾 + 实操记录；运营独立完成 **AZ 副本关停 drill**（业务无感）、**PG PITR 恢复**、**Qdrant 回灌** 三次演练；任意角色无原开发协助下能完成发布/回滚/扩容/密钥轮换/告警响应；培训考核通过率 ≥80%。未达成则 No-Go，延长 ≥2 周并肩 on-call。

### 7.2 SLO / SLI 建议初值（上线后按 W3 基线校准）
| 服务 | SLO |
|------|-----|
| API 可用性（/health+/chat） | ≥99.9% |
| API P95 延迟（/chat 含 LLM 出网） | ≤3s（⚠️待基线复核） |
| 错误率（5xx） | ≤0.5% |
| Qdrant 检索 | 成功率 ≥99.5%；P95 ≤200ms |
| PostgreSQL | 可用性 ≥99.9%；复制延迟 ≤10s |
| PWA 静态 | CDN 命中率 ≥95%；HTTPS 可用 |
| ingest | 成功率 ≥99%；日更无停滞 |

### 7.3 告警要点（云监控 + CLS）
CLB 5xx / 后端全不健康(P0)、CVM CPU/内存、NAT 出流量(P1, 成本)、PG 连接数/复制延迟、Qdrant 内存/副本 count 不一致、ingest 失败(P1)、WAF 拦截激增、CloudAudit 密钥异常读(P1)、公网暴露检测(P0)、审计删除尝试(P0)。

### 7.4 培训（C1–C7）
C1 控制台概览 / C2 CAM+SSM 实操 / C3 TKE-K8s 基础 / C4 应用与数据字典 / C5 故障应急 Drill（关停 AZ 副本）/ C6 备份恢复演练 / C7 PIPA 合规操作。节奏：W1 起 C1/C2；W3 前 C3/C4；W6 完成 C5/C6/C7。通过率 ≥80%，未过禁独立 on-call。

---

## 8. 成本治理（TCO 模型，⚠️为估算需控制台复核）

> 以下是**成本结构与驱动因子**分析，非精确报价（本环境无价格 API）。实际数字需控制台 / MigraQ 复核；以下量级以"月"估算，币种以当地计费为准（USD/KRW）。

### 8.1 成本结构
| 类别 | 形态 | 成本性质 | 量级提示 |
|------|------|----------|----------|
| 计算 CVM | 2× S5.2XLARGE16（或视本地推理改 C6） | 包年包月/按量 | 中 |
| TencentDB PG | 4C8G~8C16G 双节点 | 包年包月 | 中~高（双节点≈2×单节点） |
| Redis | 1–4GB 主从 | 包年包月 | 低 |
| Qdrant | M5 ×≥2（内存型，依集合规模） | 包年包月 | 中（内存型贵） |
| NAT 网关 + 出流量 | 网关费 + **流量计费** | **按量（头号变动成本）** | 波动大，依赖 LLM/임베딩/리랭크/Langfuse 调用量 |
| COS + CDN | 存储 + 流量 + 请求 | 按量 | 低~中 |
| CLB + WAF + KMS + CLS + CAM/SSM | 网关/规则/密钥/日志 | 按量 | 低~中 |

### 8.2 降本关键动作
1. **NAT 出流量是头号变动成本**：`RATE_LIMIT_ENABLED` + WAF CC 防滥用；提升 Redis 缓存命中减少重复 LLM/임베딩 调用；NAT 出流量按目标域名细分监控 + 日/周预算告警。
2. **本地推理评估**：若 KURE(1024)/bge_m3 改本地推理（C6 或 GPU 节点），可省 NAT 出网费、降延迟——但增加 CVM 规格成本，需权衡（⚠️待确认是否需 GPU）。
3. **多 AZ / 多实例取舍**：受预算上限约束；若预算紧，可先单 AZ 上线（牺牲跨 AZ HA）后续补。
4. **标签与闲置清理**：统一 `Project/Env/Owner/CostCenter/Component/Tier` 标签，按组件归因；周/月巡检关机 CVM、未挂载云盘、过期快照、低频 COS 转归档。

### 8.3 TCO 对比结论
- **CVM+Compose 阶段** vs **TKE 阶段**：CVM 控制面成本低但弹性差、运维手工；TKE 增加集群管理费但弹性省闲置、自动自愈。业务稳定后 TKE 长期更省。
- **自托管 Qdrant vs VectorDB**：自托管零额外产品费但需运维内存型节点；VectorDB 免运维但单价+潜在重灌成本。默认自托管。
- **SQLite vs PG**：PG 双节点为新增固定成本，但换来跨 AZ HA 与 PITR，迁移必要。

---

## 9. 风险清单与缓解（ Consolidated ）

| # | 风险 | 类别 | 缓解 |
|---|------|------|------|
| R1/C5 | LLM 端点延迟/可用性（DeepSeek/混元从 ap-seoul 可达性） | 架构/割接 | ⚠️确认端点区域与延迟；用项目已有 openai/anthropic fallback 链；超时+重试退避；关键路径降级（无 LLM 返回检索摘要） |
| R2/C8 | CORS / HTTPS | 架构/割接 | PWA 必须 HTTPS；`allow_origins` 改生产域名；CLB 统一 CORS |
| R3/C4 | 密钥管理 | 架构/割接 | 全部入 SSM/KMS；镜像零硬编码；CAM 最小权限；节点经实例角色拉取；W1 验证 GetSecret |
| R4/C9 | NAT 出流量 + 임베딩 成本激增 | 架构/成本 | 限流+缓存+流量告警；评估本地推理降本 |
| R5/C10 | PIPA（韩国 PII） | 架构/合规 | 全部资源 ap-seoul；TLS+KMS；CLS/CloudAudit；保留/撤回策略；⚠️确认是否收集 PII、是否需 DPIA |
| R6 | 单 CVM 单点 | 架构 | CLB + 跨 AZ 多实例 + PG 主备 + Qdrant 副本 |
| R7 | SQLite→PG 切换 | 架构 | 空库 `alembic upgrade head` 验证；`migrate_sqlite_to_postgres.py` 灰度 |
| R8/C6 | Qdrant 规模误判 / 恢复失败 | 架构/割接 | ⚠️核对 `vectors_count`/存储定内存(M5)；W2 先小集合演练 |
| R9 | PWA 后台推送(FCM) 额外依赖 | 架构 | 单独评估 VAPID/SW/FCM |
| R10 | ingest 停滞 | 架构 | 常驻执行体 + 失败告警 + `vectors_count` 健康校验 |
| C1 | 数据不一致（割接窗口增量丢失） | 割接 | 冻结写+短窗口；PG 增量重跑/Qdrant 再 snapshot；count 一致才去只读 |
| C2 | DNS 传播慢 | 割接 | TTL 提前 60s；分批/灰度；旧环境保留只读 |
| C3 | SSL 证书问题 | 割接 | P0/W1 提前申请 DV 并校验；CLB/WAF 绑定前 openssl 校验 |
| C7 | 回滚触发 | 割接 | DNS 切回旧环境（分钟级）；云上数据保留便于二次割接 |
| ops: R-hand/R-doc/R-alert/R-secret/R-slo/R-drift/R-cost/R-know | 交接遗漏/文档过时/告警疲劳/密钥泄露/SLO无基线/配置漂移/成本失控/知识单点 | 运营 | §7 检查单全勾+验收演练；变更即更新 Wiki；告警去重降噪；SSM+镜像扫描+90天轮换；W3 建基线；优先 IaC；预算告警+NAT 监控；双人 on-call+交叉培训 |

---

## 10. 待复核项汇总（⚠️，需控制台 / MigraQ）

1. ⚠️ **VectorDB 在 ap-seoul 是否可用 + 是否提供 Qdrant 兼容 API**（决定自托管 vs 托管，默认自托管）。
2. ⚠️ **LLM 端点调用路径**：`LLM_PROVIDER=tencent`(DeepSeek/混元) 能否从 ap-seoul 直连、延迟、配额、是否支持私有网络接入（影响 R1/R4/C5）。
3. ⚠️ **임베딩(KURE)/리랭크(bge_m3) 本地推理 vs 托管 API**（决定 CVM 规格与 NAT 成本）。
4. ⚠️ **Qdrant collection 规模**（gospel_kure 向量条数/存储量）→ 内存与实例规格（R8）。
5. ⚠️ **PostgreSQL vs MySQL、版本(15/16)** 在 ap-seoul 支持与 HA；Redis 架构。
6. ⚠️ **SSM/KMS/CLS/CAM/云监控/TKE/WAF/Redis** 在 ap-seoul 可用性与功能粒度。
7. ⚠️ **COS 首尔桶多 AZ、CDN 韩国/全球加速节点、自定义域名与韩国合规/备案**（PWA HTTPS 必须）。
8. ⚠️ **ap-seoul 实际 AZ 数量与命名**（假设 2–3 个）；CLB 跨 AZ 分发能力；NAT 规格与单价。
9. ⚠️ **LLM/임베딩/리랭크/Langfuse 是否跨境传输**（PIPA 出境影响）。
10. ⚠️ **预算上限**（影响多 AZ/多实例/托管 vs 自托管/Redis/GPU 取舍）。
11. ⚠️ **PIPA 适用性**（是否收集韩国居民 PII？是否需 DPIA、保留期限、撤回机制）。
12. ⚠️ **ingest 触发方式**（Celery/APScheduler/定时脚本）→ 决定常驻进程形态。
13. ⚠️ **是否需要 GPU**（本地推理 KURE/bge_m3 是否需 GPU 加速）。

---

## 11. 主理人决策建议（下一步）

1. **立即闭环 P0 待复核项**：优先确认 #2(LLM 端点)、#3(임베딩 本地 vs API)、#4(Qdrant 规模)、#11(PIPA)、#10(预算)——这五项直接决定规格与成本基线，建议在 T0 前 1 周内由用户在腾讯云控制台确认。
2. **账号先行**：在主账号下创建 5 个子账号 + CAM 实例角色，MFA 强制，作为 W1 前置。
3. **先 CVM+Compose 上线**，满足 1 个月窗口；TKE 作为后续演进（除非团队已熟 K8s，可直接上）。
4. **数据层是最大风险点**：SQLite→PG 与 embedded→server Qdrant 的迁移务必在 W2 用 `--dry-run` + 小集合演练，行数/count 校验通过后再割接。
5. **割接用蓝绿 + DNS TTL 60s + 旧环境保留只读**，回滚分钟级，风险可控。
6. **运营交接是验收关**：No-Go 判据（§7.1）未达成前，原团队延长并肩 on-call ≥2 周。

---

*综合最终版：网络/架构沿用上游产出，不重画拓扑；所有 ⚠️项以腾讯云控制台 / MigraQ 复核为准。*
*阶段产出：ap-seoul-product-mapping.md、ap-seoul-landing-zone.md、ap-seoul-architecture.md、ap-seoul-delivery.md、ap-seoul-ops.md。*
