# AI Gospel (korean-gospel-ai) → 腾讯云韩国 (ap-seoul) 目标解决方案架构

> 角色：解决方案架构师（cloud-architect）
> 范围：仅 korean-gospel-ai 项目，本地 → 腾讯云韩国首尔区（ap-seoul），非跨云。
> 输入：依据 product-expert 交付的 `ap-seoul-product-mapping.md`，以及仓库内 `docker-compose.prod.yml`、ingest 脚本（`./scripts/index_sermons.py`、`./scripts/ingest_documents.py`）等实际部署形态。
> 约束：本环境无法调用 MigraQ，基于标准腾讯云知识；网络拓扑沿用 Landing Zone 专家给出的 2 AZ 标准假设，**不重画 VPC**；所有不确定项标注「⚠️待复核」。

---

## 0. 设计基线（沿用假设）

| 项 | 假设 | 来源 |
|----|------|------|
| 区域 / AZ | ap-seoul，**2 个可用区**（AZ-a / AZ-b） | Landing Zone 标准假设 |
| VPC / 子网 | 1 个 VPC；**公有子网**（放 CLB、NAT）、**私有子网**（放 app / Qdrant / DB），跨 2 AZ | Landing Zone 标准假设 |
| 出网 | NAT 网关在公有子网，私有子网经 NAT 出站（调 LLM / 嵌入 / 重排 / Langfuse） | 同上 |
| 安全组 | 按层隔离：web（CLB）→ app（FastAPI/Streamlit）→ data（PostgreSQL）→ qdrant | 同上 |
| 容器形态 | 已 docker 化；节奏 **CVM(Docker Compose)+CLB 先上线 → 演进 TKE** | product-expert 决策 A |
| 向量库 | 自托管 Qdrant server 模式（优先）；VectorDB 备选 | product-expert 决策 B |
| 关系库 | TencentDB for PostgreSQL（托管，跨 AZ 主备） | product-expert 决策 D |
| 静态 | COS + CDN（HTTPS） | product-expert 决策 C |

---

## 1. 目标架构总览

### 1.1 组件拓扑与部署位置（ASCII 图）

```
                         ┌─────────────────────────────────────────────────────────┐
   모바일 PWA             │                    腾讯云 ap-seoul  (单 VPC)                │
   (手机/浏览器)          │                                                           │
        │ HTTPS           │   公有子网 (AZ-a)              公有子网 (AZ-b)            │
        │                 │   ┌──────────────┐            ┌──────────────┐          │
        ├─────────────────┼──▶│   CLB        │◀──健康│────│   CLB        │          │
        │                 │   │ (应用型/SSL终│  检查 ├────│ (跨AZ/多AZ)  │          │
        │                 │   │  止/CORS)    │            │              │          │
        │                 │   └──────┬───────┘            └──────┬───────┘          │
        │                 │          │ 内网转发(HTTPS/HTTP)        │                  │
        │                 │   私有子网 (AZ-a)              私有子网 (AZ-b)            │
        │                 │   ┌──────────────┐            ┌──────────────┐          │
        │                 │   │ CVM/TKE 节点  │   CLB 分发  │ CVM/TKE 节点  │          │
        │                 │   │ ┌──────────┐ │            │ ┌──────────┐ │          │
        │                 │   │ │Streamlit│ │            │ │Streamlit│ │          │
        │                 │   │ │ (UI:8501)│ │            │ │ (UI:8501)│ │          │
        │                 │   │ ├──────────┤ │            │ ├──────────┤ │          │
        │                 │   │ │FastAPI  │ │            │ │FastAPI  │ │          │
        │                 │   │ │(:8000)  │ │            │ │(:8000)  │ │          │
        │                 │   │ └──────────┘ │            │ └──────────┘ │          │
        │                 │   │ ┌──────────┐ │            │ ┌──────────┐ │          │
        │                 │   │ │Qdrant srv│ │ 副本/集群  │ │Qdrant srv│ │          │
        │                 │   │ │(:6333/..│ │◀─(自托管HA)─▶│ │(:6333)  │ │          │
        │                 │   │ └──────────┘ │            │ └──────────┘ │          │
        │                 │   │ ┌──────────┐ │            │              │          │
        │                 │   │ │ingest   │ │ (后台常驻/  │              │          │
        │                 │   │ │executor │ │  Job/Cron)  │              │          │
        │                 │   │ └──────────┘ │            │              │          │
        │                 │   └──────┬───────┘            └──────────────┘          │
        │                 │          │                          │                    │
        │                 │   私有子网 DB 子网                私有子网 DB 子网         │
        │                 │   ┌──────────────┐            ┌──────────────┐          │
        │                 │   │ TencentDB PG │ 主备跨AZ   │ (备节点/     │          │
        │                 │   │ 主节点 (AZ-a)│◀──同步───▶│  只读副本)   │          │
        │                 │   └──────────────┘            └──────────────┘          │
        │                 │                                                           │
        │                 │   ┌──── NAT 网关 (公有子网) ────▶ 公网 ──▶ LLM/임베딩/   │
        │                 │   │   (私有子网出网统一走 NAT)      리랭크 API · Langfuse │
        │                 │   └──────────────────────────────────────────────────  │
        │                 │                                                           │
   설교 PDF / 성경 /      │   ┌──────────────┐   ┌──────────────┐  ┌──────────────┐ │
   suggestion_questions   │   │   COS 桶     │   │   CDN        │  │ CLS/云监控   │ │
   .json / Qdrant快照 /  │   │ (静态+备份)  │──▶│ (PWA加速/    │  │ KMS/CAM/SSL  │ │
   DB 备份                │   │             │   │  HTTPS)      │  │             │ │
        └─────────────────┼──▶│  (COS+CDN)  │   └──────────────┘  └──────────────┘ │
                         └─────────────────────────────────────────────────────────┘

   图例：实线=同步/请求流；虚线=复制/备份流；---▶=出站公网调用。
```

### 1.2 部署位置明细

| 组件 | 部署位置（层） | 暴露方式 | 互联 |
|------|----------------|----------|------|
| **CLB（应用型）** | 公有子网（跨 2 AZ 部署/多 AZ 可用） | 公网 EIP + HTTPS | 对内转发到后端/UI，做 SSL 终止、CORS、健康检查 |
| **Streamlit UI** (:8501) | 私有子网（app 层，CVM/TKE） | 仅经 CLB（不直连公网） | 调 `http://backend:8000`（内网） |
| **FastAPI** (:8000) | 私有子网（app 层） | 仅经 CLB | 调 Qdrant(内网:6333)、PostgreSQL(内网)、Redis(内网) |
| **Qdrant server** (:6333/:6334) | 私有子网（data 层，独立或同机） | 仅内网（安全组限 app 层） | 被 FastAPI/ingest 访问；副本/集群跨 AZ |
| **TencentDB for PostgreSQL** | 私有 DB 子网，主备跨 AZ | 内网 VPC 地址 | 被 FastAPI 访问；备节点跨 AZ 同步 |
| **TencentDB for Redis**（可选） | 私有子网 | 内网 | 缓存/限流/Celery broker |
| **COS + CDN** | 托管（对象存储+加速） | 公网 HTTPS | PWA 静态 + 备份桶 |
| **NAT 网关** | 公有子网 | 私有子网出网统一出口 | 出站到 LLM/임베딩/리랭크/Langfuse |
| **ingest 执行体** | 私有子网 app 层 | 内网访问 Qdrant/DB | 常驻 supervisor 或 K8s Job/CronJob |

### 1.3 用户请求全链路

```
PWA(手机) --HTTPS--> CDN --(命中/回源静态)--> 用户直接加载 PWA 壳
PWA 运行时 API 调用:
  PWA --HTTPS--> CLB(SSL终止/CORS) --内网--> Streamlit UI(:8501)
                                      (UI 仅做渲染/代理, 重逻辑在后端)
  PWA/UI --HTTPS--> CLB --内网--> FastAPI(:8000)
        FastAPI 处理:
          ├─ 鉴权/限流(Redis) 
          ├─ 召回 ──内网──▶ Qdrant(:6333)  [dense+sparse 混合检索]
          ├─ 重排 / LLM 生成 ──NAT──▶ 公网 LLM/임베딩/리랭크 API
          ├─ 关系数据 ──内网──▶ TencentDB PostgreSQL (users/subscribers/interactions)
          └─ 可观测 ──▶ Langfuse(出站) + CLS(日志)
```

- **PWA 与后端解耦**：PWA 纯静态走 COS+CDN（HTTPS 强制）；FastAPI/Streamlit 经 CLB 统一入口。
- **CORS**：FastAPI `allow_origins` 由 `127.0.0.1:4174` 改为生产域名（如 `https://m.gospel.ai`）；PWA 同源/跨域策略与 CLB CORS 一致。
- **SSL 终止在 CLB**，后端/UI 在私有子网仅内网 HTTP（或内网 TLS），降低证书管理面。

### 1.4 ingest（설교 인제스트 / 임베딩 생성）后台作业链路

```
触发方式（三选一，见 §5）：
  A. 定时: 每日新增 설교 → CronJob / systemd timer / APScheduler
  B. 事件: Admin UI 上传 → 消息/队列 → ingest worker 消费
  C. 手动: 运维执行 python -m scripts.index_sermons [--reset]

ingest 执行体(常驻/Job) 流程:
  读取 data/documents/(설교 PDF/성경/.txt/.md)
    → 清洗/채킹(chunk)                              [CPU]
    → 임베딩 생성 (KURE 1024维 / bge_m3)            [本地推理 or 托管API→NAT出网]
    → 写 Qdrant collection(gospel_kure)             [内网 :6333, dense+sparse]
    → 重建 BM25 sparse 인덱스                       [内网]
    → 关系数据落 TencentDB PostgreSQL               [内网, users/subscribers 等]
    → 日志/指标 → CLS; 失败 → 告警(云监控/CLS)
  产出物: Qdrant snapshot → COS 备份桶; DB 变更 → PG 自动备份
```

- **关键**：ingest 是"常驻执行体"而非一次性脚本。CVM 形态用 `supervisor`/`systemd` 守护；TKE 形态用 `Deployment`（常驻）+ `CronJob`/`Job`（批量重索）。否则索引停滞（product-expert 风险#2）。
- **资源**：嵌入/重排 CPU 密集；若 KURE/bge_m3 本地推理，ingest 节点建议 **计算型 C6** 或独立 worker 节点，避免抢占在线推理资源。

---

## 2. 高可用（HA）设计

### 2.1 消除单点（SPOF）总览

| 层 | 单点风险 | HA 方案 |
|----|----------|---------|
| 入口 | 单 CLB 实例 | CLB 跨 AZ 多可用区部署（或多 AZ 实例），健康探测自动摘流 |
| app（FastAPI/Streamlit） | 单 CVM/单副本 | **无状态 + 多副本（≥2，跨 AZ）+ CLB 轮询/最小连接**；滚动发布零中断 |
| Qdrant | 单节点 / embedded 单锁 | 自托管：副本(replication) 或集群(sharding)；或托管 VectorDB 多 AZ |
| 关系库 | SQLite / 单节点 | TencentDB PostgreSQL **主备跨 AZ**，自动故障切换（秒级~分钟级） |
| Redis | 单点 | 标准主从（1 主 1 备），故障自动切换 |
| 出网 | 单 NAT | NAT 网关本身高可用（多 AZ），无需手动多实例 |
| 静态 | 单点 | COS 多 AZ + CDN 天然多节点 |

### 2.2 app 层：无状态多副本 + CLB

- FastAPI / Streamlit **无状态**（会话/缓存外置到 Redis；向量与关系数据在外部存储），因此可任意水平扩容、跨 AZ 部署 ≥2 副本。
- CLB 后端绑多 CVM/TKE 节点，**健康检查**（`/health`）失败自动摘流，实现副本级容错与滚动升级。
- **CVM(Docker Compose) 阶段**：至少 2 台 CVM（AZ-a + AZ-b），各自 `docker compose up`，均注册到同一 CLB。滚动发布：先停一台→拉新镜像→起→再切另一台。
- **TKE 阶段**：Deployment `replicas≥2`，配合 `PodDisruptionBudget` 与 `maxUnavailable=1`，天然跨节点/AZ 调度。

### 2.3 Qdrant 高可用（自托管时）

- **副本模式（推荐起步）**：Qdrant 1.13+ 支持 replica（配置 `replication_factor≥2`），2 个 Qdrant 节点跨 AZ 各持一份副本，写经 leader、读可分散；单节点故障不影响检索。
- **集群模式（规模更大）**：`cluster` 模式做分片 + 副本，横向扩展吞吐与容量。
- **存储**：每个 Qdrant 节点挂载**云硬盘（SSD/高性能）**，开启定期**快照**到 COS；副本间 WAL 同步。
- **解除 embedded 单锁**：本地 `./.qdrant_local` → `snapshot` 导出 → 灌入 server 模式（compose 已就绪 `QDRANT_URL=http://qdrant:6333`）。⚠️确认 collection 规模（gospel_kure 向量条数）以定内存（见 product-expert §3）。
- **若改用腾讯云 VectorDB（⚠️需确认 ap-seoul 可用 + Qdrant 兼容 API）**：直接获得托管多 AZ、免运维 HA；但需改 `qdrant-client` 调用为 VectorDB SDK 并重新灌库（迁移风险更高，见决策 B）。

### 2.4 TencentDB 跨 AZ

- PostgreSQL 选 **双节点（一主一备，跨 AZ）**，同步/半同步复制；主节点故障自动切备，连接串（VIP/只读地址）不变，应用无感知。
- 开启**自动备份**（日备 + WAL 归档），保留策略对齐 PIPA/合规要求。

### 2.5 CVM vs TKE 演进建议与触发时机

| 维度 | 阶段一：CVM + Docker Compose + CLB | 阶段二：TKE 容器 |
|------|-----------------------------------|------------------|
| 时间 | 上线 0–3 月（快） | 业务稳定 / 流量增长后 |
| 适用 | 1 月内上线窗口、团队 K8s 经验少 | 需弹性扩缩、滚动发布、隔离、ingest 编排优雅 |
| HA | CLB + 跨 AZ 2 CVM + 托管 DB 主备 | Deployment 多副本 + PDB + HPA + 节点池跨 AZ |
| 运维 | systemd/supervisor 守护；发布手工 | 声明式、GitOps、自动自愈、Job/CronJob |
| 成本 | 低（少控制面） | 集群管理费 + 节点费，但弹性省闲置 |

**触发 TKE 的时机信号**：
1. 在线副本需频繁扩缩（活动/布道高峰）；
2. ingest 批量作业需与在线服务资源隔离、定时/重试/可观测；
3. 多服务（UI/Backend/Qdrant/worker）需命名空间、网络策略、配置/密钥统一管理；
4. 团队具备 K8s 运维能力。
**若团队已熟 K8s，可跳过阶段一直接 TKE。**

---

## 3. 容灾（DR）与 RPO/RTO（单区域）

> ⚠️ **单区域限制**：ap-seoul 为**单一地域**，本方案为"同地域跨 AZ"高可用，**不提供地域级容灾**（整地域故障无法在本方案内恢复）。若需地域级 DR，需另建异地（如 ap-tokyo / ap-singapore）复制，成本与合规（数据出境）显著上升——属后续可选项，不在本目标架构默认范围。

### 3.1 单区域内的 DR 资产与手段

| 资产 | 备份/容灾手段 | 恢复点 |
|------|---------------|--------|
| TencentDB PostgreSQL | 自动日备 + WAL 连续归档；可恢复到任意时间点(PITR) | RPO 秒级~分钟级 |
| Qdrant 向量 | 定期 `snapshot` → COS 备份桶；副本跨 AZ | 快照间隔决定 RPO |
| COS 静态/数据 | COS 多 AZ 冗余；**可选 COS 跨区域复制（CRR）到同云其他地域** | 多 AZ 内几乎无损；CRR 异步有延迟 |
| 关系/配置 | Alembic 迁移脚本版本化；`.env`/密钥在 SSM，可重建 | — |

### 3.2 RPO / RTO 建议档位

| 档位 | RPO | RTO | 适用 | 手段 |
|------|-----|-----|------|------|
| **基础档（默认推荐）** | ≤ 15 min（DB PITR）；Qdrant ≤ 6 h（日/定频快照） | ≤ 30–60 min（AZ 级故障自动切换；节点恢复） | 大多数场景 | PG 主备跨 AZ 自动切换 + 自动备份；Qdrant 副本 + 日快照；CLB 跨 AZ |
| **增强档** | ≤ 5 min（DB）；Qdrant ≤ 1 h | ≤ 15 min | 高可用要求 | PG 缩短备份/PITR 窗口；Qdrant 提高快照频率 + 副本；预置热备节点；启动脚本/ IaC 一键拉起 |
| **严档（需异地）** | ≤ 5 min | ≤ 数小时 | 法规/合同要求地域级 DR | **⚠️需 COS 跨区域复制 + 异地备用集群/预案**，超出单区域默认架构，需另行评估与合规审批 |

- **AZ 级故障**（单可用区不可用）：CLB 将流量导向健康 AZ；PG 主备切换；Qdrant 副本接管——业务基本无感或分钟级恢复（落入基础/增强档 RTO）。
- **实例级故障**：CLB 摘流 + 托管 DB 自动切换 + 副本 Qdrant；CVM 由 CLB 重新路由，TKE 由控制器重建 Pod。

### 3.3 恢复演练

- 定期（季度）演练：PG PITR 恢复、Qdrant snapshot 回灌、IaC 重建 app 层，验证 RPO/RTO 可达。

---

## 4. 可扩展性（流量增长路径）

### 4.1 在线服务（FastAPI / Streamlit）
- **水平扩容**：
  - CVM 阶段：手动/脚本加 CVM 节点并注册 CLB；或升级规格纵向扩。
  - TKE 阶段：**HPA（基于 CPU / 自定义指标如 QPS、并发）** 自动扩缩副本；节点池 **CA（Cluster Autoscaler）** 扩节点。
- **纵向扩容**：无状态服务升级 CVM 规格（S5→C6 计算型，若本地推理重）。
- **瓶颈外置**：限流/会话/缓存走 Redis，避免副本间状态耦合，便于无限水平扩展。

### 4.2 向量检索（Qdrant）
- 读多写少：副本数↑（读扩展）；写/容量瓶颈：集群分片（sharding）横向扩。
- 内存型节点（M5）常驻向量，提升检索吞吐；规模再大切托管 VectorDB 弹性。

### 4.3 关系库
- 读扩展：PostgreSQL 加**只读副本**（跨 AZ），将趋势/统计类查询（/trending）分流只读。
- 写瓶颈：升规格或后续分库（当前规模多无需）。

### 4.4 静态 / 边缘
- PWA 经 CDN 天然横向扩展；流量增长仅增 CDN 流量包，无计算负担。

### 4.5 ingest 作业
- 批量重索引（--reset / reindex）与大语料导入，用独立 worker 节点/专用 TKE 节点池，避免与在线推理争抢；TKE 下用 `Job` + 资源 limit 隔离。

---

## 5. 关键技术决策

### 5.1 TKE 采用时机
- **默认**：先用 **CVM(Docker Compose)+CLB** 在 1 月内上线（契合现有 compose，运维简单）。
- **切 TKE**：见 §2.5 触发信号（弹性需求、ingest 编排、多服务治理、团队能力）。若已具备 K8s 能力可直接上。
- 决策原则：**容器化是硬约束（已具备）**，形态按节奏演进，不为过度工程提前引入 TKE。

### 5.2 Qdrant 自托管 vs VectorDB（落地取舍）
- **默认落地：自托管 Qdrant server 模式**（CVM/TKE）。
  - 理由：prod compose 已是 server 模式，单锁天然解除；沿用 `qdrant_config.yaml`；切换 VectorDB 需改 SDK + 重灌库，风险/工作量更高。
  - HA：副本（replication_factor≥2）跨 AZ；规模更大上集群。
- **何时选 VectorDB**：⚠️**确认 ap-seoul 提供 VectorDB 且支持 1024 维 + dense/sparse 混合检索 + Qdrant 兼容 API**，且愿卸下向量运维。否则默认自托管。

### 5.3 Redis 是否必要
- **建议保留（1–4 GB 标准主从）**，角色：
  1. 限流（`RATE_LIMIT_ENABLED` 已启用）；
  2. 缓存（热门问答/ suggestion_questions / 检索结果）；
  3. Celery broker（若 ingest 走队列）；
  4. 会话/临时状态外置（支撑无状态扩容）。
- **可省场景**：若 ingest 走 K8s Job（无 Celery）、且限流/缓存暂不必须，MVP 阶段可省 Redis，待需要再加；但强烈建议保留限流以防御 LLM 成本与滥用。

### 5.4 ingest 作业编排：supervisor vs K8s Job
- **CVM 阶段**：`supervisor`/`systemd` 守护常驻 ingest 进程；定时用 `systemd timer` 或 `APScheduler`；日志落 CLS。
- **TKE 阶段（推荐）**：常驻用 `Deployment`（带 `restartPolicy`）+ 定时批量用 `CronJob`；大型重索引用 `Job`（带 backoff/retry）；资源 limit 隔离。
- **统一要求**：ingest 必须常驻/可调度执行体，失败告警（CLS + 云监控），否则索引停滞（product-expert 风险#2）。

---

## 6. 风险与缓解

| # | 风险 | 缓解 |
|---|------|------|
| R1 | **LLM 延迟 / 可用性**（DeepSeek/混元端点从 ap-seoul 可达性与延迟不确定） | ⚠️确认端点区域与延迟；利用项目已有 openai/anthropic **fallback 链**；CLB/后端加超时与重试退避；关键路径降级（无 LLM 时返回检索摘要） |
| R2 | **CORS / HTTPS** | PWA 必须 HTTPS（COS+CDN+SSL）；`allow_origins` 由 `127.0.0.1:4174` 改生产域名；CLB 做 SSL 终止与 CORS 统一策略 |
| R3 | **密钥管理** | `.env`（ADMIN_API_KEY、各类 API KEY）移入 **SSM/密钥管理**，KMS 加密；镜像/仓库零硬编码；CAM 最小权限、子账号/角色；TKE 用 Secret/外部密钥 CSI |
| R4 | **成本驱动：NAT 出流量 + 임베딩** | LLM/임베딩/리랭크/Langfuse 均走 NAT 按流量计费，是主要变动成本；建议：①评估 임베딩/리랭크 改本地推理（C6/GPU）以省出网费；②限流防滥用；③缓存命中降调用；④监控 NAT 流量告警 |
| R5 | **PIPA 个人信息（韩国）** | users/subscribers 属个人数据；ap-seoul 数据驻留韩国利于合规；落实：传输/存储加密（SSL+KMS）、最小权限、访问审计（CLS/审计日志）、备份保留策略、必要时 DPIA 与用户撤回同意机制。⚠️请用户确认是否实际收集韩国居民 PII 及合规要求 |
| R6 | **单 CVM 单点** | CLB + 跨 AZ 多实例 + 托管 DB 主备 + Qdrant 副本（见 §2） |
| R7 | **SQLite→Postgres 切换** | 先在 ap-seoul 空库 `alembic upgrade head` 验证方言/类型无差异；用 `migrate_sqlite_to_postgres.py` 灰度迁移 |
| R8 | **Qdrant 规模误判** | ⚠️核对 gospel_kure 向量条数/存储量以定内存与实例规格（M5 优先） |
| R9 | **PWA 后台推送（可选）** | 若启用 pywebpush/FCM，需 VAPID/SW/FCM 项目，属额外出站依赖，单独评估 |
| R10 | **ingest 停滞** | 常驻执行体 + 失败告警 + 定期健康校验（collection 条数监控） |

---

## 7. 待确认 / 待复核项（⚠️）

> 以下均需 **腾讯云控制台 / MigraQ** 二次确认；本环境无法调用 MigraQ，基于标准知识给出假设。

1. ⚠️ **VectorDB 在 ap-seoul 是否可用？是否提供 Qdrant 兼容 API（零改造切换前提）？** —— 决定 §5.2 最终落地（自托管 vs 托管）。
2. ⚠️ **LLM 端点调用路径**：`LLM_PROVIDER=tencent`（DeepSeek/混元）能否从 ap-seoul 直接调用？延迟、配额、是否支持私有网络接入（影响 R1/R4）。
3. ⚠️ **임베딩(KURE 1024) / 리랭크(bge_m3) 部署方式**：本地推理还是托管 API？决定 CVM 规格（C6/GPU）与 NAT 出流量成本（R4）。
4. ⚠️ **Qdrant collection 规模**（gospel_kure 向量条数 / 存储量）—— 定内存与实例规格（R8）。
5. ⚠️ **PostgreSQL vs MySQL、版本（15/16）** 在 ap-seoul 的支持与 HA 架构。
6. ⚠️ **SSM / KMS / CLS / CAM / 云监控 / TKE / Redis** 在 ap-seoul 的可用性、版本与配额。
7. ⚠️ **COS 多 AZ 开关、CDN 韩国/全球加速节点、自定义域名与韩国合规/备案要求**（PWA HTTPS 必须）。
8. ⚠️ **ap-seoul 实际 AZ 数量与命名**（假设 2 AZ：AZ-a/AZ-b），需与 Landing Zone 专家最终对齐。
9. ⚠️ **COS 跨区域复制（CRR）目标地域与数据出境合规**——仅当需要严档地域级 DR（§3.3）时评估。
10. ⚠️ **预算上限** —— 影响多 AZ / 多实例 / 托管 vs 自托管 / Redis / GPU 取舍。
11. ⚠️ **PIPA 适用性** —— 是否收集韩国居民个人数据？是否需 DPIA、数据保留期限、撤回同意机制（R5）。
12. ⚠️ **ingest 触发方式（Celery / APScheduler / 定时脚本）** —— 决定常驻进程形态（supervisor vs K8s Job，§5.4）。
13. ⚠️ **是否需要 GPU** —— 本地推理 KURE/bge_m3 是否需 GPU 加速，或纯 CPU 可接受。

---

### 附录：与 product-expert 映射的对应关系
- 组件映射（§1 表 1）→ 本文 §1.1/§1.2 拓扑与位置。
- 决策 A/B/C/D → 本文 §2.5 / §5.2 / §1.3(CORS+CDN) / §2.4。
- 规格对标（prod 4C8G~8C16G PG、Redis 1–4GB、M5 Qdrant）→ 本文 §2/§4 容量与扩缩依据。
- 风险 #1–#10 → 本文 §6 + 待确认 #1–#13。
