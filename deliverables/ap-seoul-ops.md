# AI Gospel (korean-gospel-ai) → 腾讯云韩国首尔 (ap-seoul) 运营交接、文档归档与云业务培训方案

> 角色：运营交接及培训专家（ops-engineer）
> 范围：korean-gospel-ai 迁移到腾讯云 ap-seoul 后的**运营交接(Handover)、文档归档与知识库、可观测(SLO/监控/告警)、云业务培训、成本治理、运营风险与完成标准**。
> 输入：综合 product-expert `ap-seoul-product-mapping.md`、landing-zone `ap-seoul-landing-zone.md`、cloud-architect `ap-seoul-architecture.md`、delivery `ap-seoul-delivery.md`。
> 约束：本环境无法调用 MigraQ，基于标准腾讯云运营知识；不确定项标「⚠️待复核（控制台/MigraQ）」；沿用前序架构/实施，**不重画架构、不重列实施步骤**。

---

## 0. 运营交接范围总览（沿用上游关键事实）

| 维度 | 上游结论（直接沿用） |
|------|----------------------|
| 区域 / 形态 | `ap-seoul` 单地域；先 **CVM(Docker Compose)+CLB**，演进 **TKE**；容器化已具备 |
| 网络 | VPC `10.0.0.0/16`；仅 **CLB 公网入口**；私有子网经 **NAT** 出网 |
| 账号 | 主账号(仅计费/紧急) + 子账号 `ops-deploy`/`db-admin`/`readonly`/`cicd-role`/`security-audit` + CAM 实例角色 |
| 密钥 | 全部入 **SSM**，运行时经 CAM 实例角色/External Secrets 拉取，禁 `.env`/镜像明文 |
| 有状态 | TencentDB PostgreSQL(主备跨 AZ)、自托管 Qdrant server(副本≥2)、Redis(主从)、COS(备份/静态) |
| 割接 | W1~W5 波次 + W6 观察；蓝绿+DNS 切换；T0~T0+4w 上线 |
| 合规 | PIPA：数据驻留 ap-seoul、TLS+KMS、CLS/CloudAudit 审计、保留/撤回策略 |

> 本文件交付物**不重复**上述细节，仅定义「如何把这套系统**可独立地交给运营团队接管**」。

---

## 1. 运营交接计划（Handover）

### 1.1 交接目标
将系统从「本地/开发自管（ssh + .env + 单机 Docker）」平稳移交给「ap-seoul 云上运营（CAM 角色、SSM、CLS、云监控、TKE/CVM 声明式）」。核心判据：**无原开发人员在场时，运营可在 SLO 内完成日常运维、应急、升级、回滚**。

### 1.2 交接内容清单（移交物）

| # | 交接项 | 来源 / 落点 | 接收方 |
|---|--------|------------|--------|
| H1 | **架构与网络文档**：VPC 拓扑、子网/CIDR、安全组互信、CLB/NAT 规则、跨 AZ 分布 | `ap-seoul-landing-zone.md` §2、§3.1 | ops-deploy + readonly |
| H2 | **应用架构与 HA/DR 文档**：无状态多副本、Qdrant 副本、PG 主备、RPO/RTO 档位 | `ap-seoul-architecture.md` §2/§3 | ops-deploy + SRE |
| H3 | **Runbook / 应急预案**：部署、扩缩、故障摘流、PG PITR 恢复、Qdrant 回灌、ingest 停滞处理 | 本文 §2 + 本文 §3 | ops-deploy + on-call |
| H4 | **SSM 密钥与凭证清单**：ADMIN_API_KEY、各类 API KEY、PG 密码、Qdrant api_key、轮换计划 | `ap-seoul-delivery.md` §2.1.6 | security-audit + db-admin |
| H5 | **CLS / CloudAudit 审计**：日志集、检索语法、审计保留策略、禁删策略 | `ap-seoul-landing-zone.md` §3.4 | security-audit + readonly |
| H6 | **监控告警配置**：CLB 5xx、CVM/DB/Qdrant 指标、NAT 出流量、ingest 失败、WAF/审计告警 | 本文 §3 | ops-deploy + on-call |
| H7 | **升级与回滚权限（CAM 角色）**：ops-deploy / db-admin / readonly / security-audit 策略边界 | `ap-seoul-landing-zone.md` §1.2 | 全部角色 |
| H8 | **上报与升级链路**：on-call 排班、告警路由、升级到人（Escalation）、供应商(腾讯云)工单入口 | 本文 §3.5 + §1.4 | on-call + team-lead |
| H9 | **IaC / 部署物**：docker-compose.prod.yml、TCR 镜像、TKE 清单、CI/CD 流水线定义 | `ap-seoul-delivery.md` §2.4 | cicd-role + ops-deploy |
| H10 | **数据字典 / Alembic 版本**：表结构、迁移顺序、SQLite→PG 脚本、DEFAULT_TABLE_ORDER | `ap-seoul-delivery.md` §2.2 | db-admin + 开发 |
| H11 | **成本与预算基线**：NAT 出流量成本模型、预算告警阈值、标签规范 | 本文 §5 | ops-deploy + 财务对接人 |
| H12 | **PIPA 合规材料**：数据驻留举证、加密清单、DPIA（如适用）、保留/撤回机制 | `ap-seoul-landing-zone.md` §4 | security-audit + 法务 |

### 1.3 交接检查单（Handover Checklist）

**账户与权限**
- [ ] 主账号 AK/SK 已停用日常使用，仅保留一个 break-glass 凭证（物理/保险库保管）
- [ ] 子账号 `ops-deploy`/`db-admin`/`readonly`/`cicd-role`/`security-audit` 已创建并强制 **MFA**
- [ ] CAM 策略已应用，且 `Deny` 删除 CloudAudit/CLS 审计日志已显式写入
- [ ] CAM 实例角色已绑定 CVM/TKE 节点，节点能经临时凭证访问 COS/CLS/KMS/SSM
- [ ] 运营已实测各角色权限边界（如 readonly 无法写、db-admin 无法碰网络）

**密钥与配置**
- [ ] SSM 中全部密钥已录入且无明文 `.env`/镜像残留（仓库 + 镜像扫描确认）
- [ ] 密钥轮换计划已设（默认 90 天），下次轮换日期已登记
- [ ] 节点启动能从 SSM 拉取密钥并 `export`（已实操验证，日志无缺密钥告警）

**网络与安全**
- [ ] 仅 CLB 暴露公网；所有 CVM/DB/Qdrant 无公网 IP（资产核查）
- [ ] 安全组互信端口连通性已 `nc`/`telnet` 验证（app↔data↔qdrant）
- [ ] NAT 出网可达 LLM/임베딩/리랭크/Langfuse（curl 实测）
- [ ] WAF 已挂 CLB，`/admin/*`、`/chat` 防护与 CC 限流生效

**数据与备份**
- [ ] PG `alembic upgrade head` 通过；SQLite→PG 行数校验一致
- [ ] Qdrant `gospel_kure` `vectors_count` 与源一致；副本跨 AZ count 一致
- [ ] PG 自动备份(日备+WAL PITR) 与 Qdrant snapshot → COS 已验证落桶
- [ ] COS 备份桶 SSE-KMS 已开；保留周期已设（如 30/90 天）

**可观测与应急**
- [ ] CLS 收到应用/容器/CLB/ingest 日志；CloudAudit 已开
- [ ] 监控告警规则已按 §3 配置并**触发演练**（人为制造一次指标越界验证通知可达）
- [ ] Runbook 已编写并至少 **1 次桌面演练**（drill）通过
- [ ] on-call 排班与升级链路已生效，告警能触达人

**文档与知识库**
- [ ] §2 文档集已归档到指定位置（COS/CFS + Wiki），ownership 已指派
- [ ] 团队已完成 §4 培训并考核通过（开发/运维/SRE 分级）

### 1.4 上报与升级链路（Escalation）

```
L0 自动化自愈 / 告警自愈脚本
   │ (无法自愈)
L1 一线 on-call（ops-deploy / SRE，7x24 轮值）
   │ ├─ 应用层故障 → Runbook §3 处置；15min 内升级
   │ └─ 数据层故障 → 联动 db-admin
L2 专家 on-call：db-admin（PG/Qdrant/Redis）、security-audit（合规/审计）、
               cloud-architect（架构/容量）、product-expert（产品/密钥归属）
   │ (跨团队 / 平台级)
L3 供应商：腾讯云工单（ap-seoul 区域支持）+ 账户经理
   │ (业务影响 / 法规)
L4 业务负责人 / team-lead（对外沟通、PIPA 事件上报）
```

- **告警渠道**：企业微信/钉钉机器人 + 电话（P1/P0）；IM 群仅用于 P2/P3 知会。
- **升级时限**：P0（全站不可用）→ 立即电话 + 5min 内响应；P1（核心功能降级）→ 15min；P2/P3 → 工作时间处理。
- **PIPA 安全事件**（密钥泄露、PII 出境、审计缺失）→ 直接 L4 + security-audit，不走常规排队。

### 1.5 交接验收标准（Acceptance）
1. 交接检查单（§1.3）**全部勾选**，并有实操记录/截图。
2. 运营独立完成一次**模拟故障 drill**（关停一个 AZ 的后端副本 → CLB 摘流、业务无感）并复盘通过。
3. 运营独立完成一次 **PG PITR 恢复演练** + 一次 **Qdrant snapshot 回灌演练**（演练库，不影响生产）。
4. 任意角色在**无原开发人员协助**下，能按 Runbook 完成：发布、回滚、扩容、密钥轮换、告警响应。
5. 培训考核（§4）各角色通过率 ≥ 80%。

---

## 2. 文档归档与知识库

### 2.1 需沉淀的文档集

| 文档 | 内容 | 主要 owner | 消费者 |
|------|------|-----------|--------|
| 架构图 / 网络拓扑 | VPC、子网、安全组、CLB/NAT、跨 AZ 分布（沿用上游图） | cloud-architect | 全员 |
| Runbook（运维手册） | 部署/发布/回滚/扩缩/日常巡检步骤（本文 §3.2） | ops-deploy | on-call |
| 事故 Playbook | P0~P3 分级处置流程、升级链路、沟通模板 | SRE/ops-deploy | on-call |
| 数据字典 | 表结构、字段含义、Alembic 版本、迁移顺序 | db-admin | 开发/db-admin |
| API 文档 | `/chat`、`/suggestions`、`/admin/*`、`/trending` 等接口、鉴权 | 开发 | 开发/ops |
| Onboarding 指南 | 新成员环境准备、CAM 角色申请、SSM 读取演练、控制台导航 | ops-deploy | 新成员 |
| 安全与合规手册 | PIPA 落地项、密钥管理、审计查询、DPIA（如适用） | security-audit | 全员 |
| 容量与成本手册 | 规格档、NAT 成本模型、预算告警、标签规范（本文 §5） | ops-deploy | 全员/财务 |
| 备份与 DR 手册 | PG PITR、Qdrant snapshot、RPO/RTO、演练记录 | db-admin | on-call |

### 2.2 归档位置建议

| 类型 | 归档位置 | 说明 |
|------|----------|------|
| **结构化 Wiki / 知识库** | 内部 Wiki（如 Confluence/TAPD 文档/腾讯云 CODING Wiki） | 架构图、Runbook、Playbook、Onboarding、合规手册的**可读版本**；支持全文检索与版本历史 |
| **不可变源文件 / 大文件** | **COS（首尔桶，SSE-KMS）** + 可选 **CFS** 挂载 | docker-compose、TKE YAML、IaC、数据库迁移脚本、Qdrant snapshot、PG 备份、PDF/성경 资源；版本化（prefix 或对象版本控制） |
| **运行日志 / 审计** | **CLS** 日志集 + 检索 | 实时日志、事故复盘检索；与 Wiki 通过链接互引 |
| **代码与部署物** | 代码仓库（Git）+ **TCR** 镜像仓库 | 源码、CI/CD 定义、镜像；与文档通过 commit/ tag 关联 |

- **检索联动**：Wiki 中每个 Runbook 步骤附 CLS 检索示例链接；事故复盘在 Wiki 留档并挂 CLS 时间范围。
- ⚠️ **待复核**：腾讯云是否在 ap-seoul 提供 **CODING Wiki / 文档服务**区域可用性；若无则用现有内部 Wiki，COS/CLS 仍落在 ap-seoul 满足数据驻留。

### 2.3 版本与 Ownership 规则
- **版本化**：所有文档带 `版本 + 最后更新日期 + owner` 头；IaC/compose/YAML 用 Git tag（如 `env/prod-2026xxxx`）标记已上线版本。
- **Ownership**：每份文档单一 owner（见 §2.1 表），reviewer 为对口专家；变更需 MR/PR + 评审。
- **变更通知**：架构/网络/密钥/告警阈值变更须在 on-call 群公告并更新 Wiki，避免「文档过时」（风险 R-doc，见 §6）。
- **生命周期**：下线/迁移的资源，其文档 30 天内标记 `Deprecated` 并链接替代文档，而非直接删除。

---

## 3. 监控 / 告警 / SLO（基于 CLS + 云监控）

### 3.1 SLI / SLO 建议

> 注：具体阈值需结合 W3 性能基线（delivery §5）校准；下表为**建议初值**，上线后按观测微调。

| 服务 | SLI | SLO 目标（月度） | 测量方式 |
|------|-----|------------------|----------|
| **API 可用性** | `/health` + `/chat` 成功比例（非 5xx/超时） | **≥ 99.9%**（P0 链路） | CLB 5xx 率 + 后端探活（云监控/CLS） |
| **API 延迟 (P95)** | `/chat` 端到端 P95 延迟（含 LLM 出网） | **≤ 3s**（⚠️待基线复核；LLM 延迟敏感） | APM/CLS 访问日志耗时字段 |
| **错误率** | 5xx / 总请求 | **≤ 0.5%** | CLB 访问日志聚合 |
| **Qdrant 检索** | `/search` 成功率 + P95 延迟 | 成功率 ≥ 99.5%；P95 ≤ 200ms | Qdrant 指标 + 应用日志 |
| **PostgreSQL** | 连接成功率 + 主备同步延迟 | 可用性 ≥ 99.9%；复制延迟 ≤ 10s | TencentDB 监控 + SQL 审计 |
| **PWA 静态** | CDN 命中率 + 可加载率 | CDN 命中率 ≥ 95%；HTTPS 可用 | CDN 监控 + 拨测 |
| **ingest** | 定时任务成功率 + collection 条数增长 | 成功率 ≥ 99%；日更无停滞 | CLS ingest 日志 + Qdrant count 监控 |

### 3.2 健康探针（Health Probe）
- **CLB 健康检查**：`GET /health`（后端提供）→ 失败自动摘流副本（跨 AZ）。
- **应用层探针**：`/health` 校验 DB/Redis/Qdrant 连通（返回依赖状态，便于区分**局部故障**）。
- **依赖探活**：独立探 Qdrant(`:6333`)、PG(`:5432`)、Redis(`:6379`)、NAT 出网(LLM 端点可达) → 任一失败在 CLS 打独立告警而非笼统 5xx。
- **TKE 阶段**：`livenessProbe`/`readinessProbe` 绑 `/health`；`PodDisruptionBudget` 保副本数。

### 3.3 告警规则（云监控 + CLS）

| 类别 | 告警项 | 建议阈值 | 级别 | 路由 |
|------|--------|----------|------|------|
| 入口 | CLB 5xx 率 | > 0.5% 持续 5min | P1 | on-call |
| 入口 | CLB 后端全不健康 | 任一 AZ 后端 0 健康 | P0 | on-call + 架构 |
| 计算 | CVM CPU | > 85% 持续 10min | P2 | on-call |
| 计算 | CVM 内存 | > 90% | P2 | on-call |
| 成本 | **NAT 出流量** | 日流量 > 预算 ×110% 或突增 50% | P1 | on-call + 财务 |
| 数据 | PG 连接数 | > 实例上限 80% | P2 | db-admin |
| 数据 | PG 复制延迟 | > 10s | P1 | db-admin |
| 向量 | Qdrant 内存 | > 85% | P2 | ops-deploy |
| 向量 | Qdrant 副本 count 不一致 | 任一副本落后 | P1 | ops-deploy |
| 任务 | **ingest 失败** | 任意失败日志 | P1 | on-call |
| 任务 | Qdrant collection 条数停滞 | 预期日更未增长 | P2 | on-call |
| 安全 | **WAF 拦截激增 / CC 触发** | 同 IP 短时超阈 | P2 | security-audit |
| 安全 | **CloudAudit 密钥读取异常** | 非预期主体读 SSM / 策略变更 | P1 | security-audit |
| 安全 | 公网暴露检测 | 任何 CVM/DB 出现公网 IP | P0 | security-audit |
| 合规 | 审计日志删除尝试 | 任何 Deny 命中 | P0 | security-audit |

### 3.4 值班（on-call）与告警路由
- **排班**：7x24 轮值，至少 2 人互为备份；使用排班工具（如 PagerDuty/腾讯云 woni/内部轮值表）。
- **路由**：P0/P1 → 电话 + IM；P2 → IM；P3 → 日报汇总。告警直接带 Runbook 链接（减少 MTTR）。
- **告警疲劳治理**（风险 R-alert，见 §6）：合并同类告警、设「静默期」、去重、按指纹分组；每周复盘误报并降噪。

### 3.5 SLO 偏差处置
- 月度 SLO 未达标 → 生成**事后复盘（Postmortem）** 入 Wiki；连续 2 月不达标触发容量/架构评审（联动 cloud-architect）。
- **错误预算（Error Budget）**：用于审批高风险变更（如大版本发布）——预算耗尽则冻结非紧急变更。

---

## 4. 云业务培训方案

### 4.1 角色与课程矩阵

| 角色 | 重点 | 课程 |
|------|------|------|
| **开发** | 控制台导航、SSM 使用、TKE/K8s 基础、API/数据字典、本地调试 | C1/C2/C3/C4 |
| **运维 (ops-deploy)** | 控制台、CAM/SSM、CVM/TKE 运维、Runbook、发布回滚、成本 | C1/C2/C3/C5/C6 |
| **SRE / on-call** | 可观测、告警、事故 Playbook、DR 演练、容量 | C3/C5/C6/C7 |

### 4.2 课程大纲（建议）

| 课 | 名称 | 时长 | 对象 | 大纲 | Hands-on | 考核 |
|----|------|------|------|------|----------|------|
| **C1** | 腾讯云控制台与 ap-seoul 概览 | 1h | 全员 | 区域/AZ、VPC 概念、资源地图、费用中心 | 登录控制台定位本项目全部资源 |  Quiz 90% |
| **C2** | CAM 与 SSM 安全实操 | 2h | 开发/运维 | 子账号/MFA、最小权限、实例角色、SSM 录入/读取/轮换 | 用 readonly 读资源；节点经实例角色 `GetSecret`；轮换一次密钥 |  实操检核 |
| **C3** | TKE/K8s 基础 | 3h | 开发/运维/SRE | Pod/Deployment/Service/Ingress、ConfigMap/Secret、HPA/PDB、CLB Ingress | 在测试集群部署 backend/ui，滚动发布、扩缩副本 |  部署成功+探活 |
| **C4** | 应用与数据字典 | 1.5h | 开发 | FastAPI/Streamlit 接口、Alembic、PG 表结构、Qdrant 集合 | 本地连云 PG 跑一条查询；读数据字典 |  Quiz |
| **C5** | 故障应急 Drill | 3h | 运维/SRE | Runbook、CLB 摘流、Pod 驱逐、PG 切换、ingest 停滞处置 | **模拟关停一个 AZ 副本**（业务无感）；处理一次 5xx 突增 |  演练复盘 |
| **C6** | 备份/恢复演练 | 2.5h | 运维/SRE/db-admin | PG PITR、Qdrant snapshot 回灌、COS 备份校验 | 演练库执行 PG 时间点恢复 + Qdrant 回灌并验证 count |  恢复成功 |
| **C7** | PIPA 合规操作 | 1.5h | 全员(侧重 security-audit) | 数据驻留举证、TLS/KMS、审计查询、保留/撤回、DPIA(如适用) | 在 CLS/CloudAudit 检索一次 PII 访问；核对加密清单 |  Quiz + 检核 |

> ⚠️ **待复核**：TKE 训练需 ap-seoul 集群实际可用；若团队直接上 TKE，C3 提前到 W1 前完成。

### 4.3 培训节奏与考核
- **时间窗**：W1 启动同步开 C1/C2（基础）；W3 前完成 C3/C4；W6 观察期完成 C5/C6/C7（实战演练）。
- **考核方式**：Quiz（客观题）+ Hands-on 实操检核 + 一次**结业 Drill**（独立处置模拟故障）。
- **达标线**：各角色考核通过率 ≥ 80%；未通过者补训并重考，禁止独立 on-call。
- **持续培训**：每季度 DR 演练 + 每半年合规复训；新人按 Onboarding 指南自学 C1/C2 后跟岗。

---

## 5. 成本治理

### 5.1 预算告警
- **预算基线**：以 delivery §4 规格（S5.2XLARGE16×2、PG 4C8G~8C16G 双节点、Redis 1–4GB、NAT、COS/CDN/WAF/KMS/CLS）为月度基线。
- **告警层级**：⚠️ 80% 预警（IM）、❌ 100% 拦截评审（电话）；**NAT 出流量单独设日/周预算**（主要变动成本，delivery C9）。
- **责任人**：ops-deploy 接收 + 财务对接人；超预算需 team-lead 审批扩容。

### 5.2 资源标签（Tag）规范
统一打标，支撑成本分摊与权限隔离：

| 标签 Key | 取值示例 | 用途 |
|----------|----------|------|
| `Project` | `korean-gospel-ai` | 项目归属 |
| `Env` | `prod` / `staging` | 环境隔离（联动 CAM 条件） |
| `Owner` | `ops-deploy` / `db-admin` | 责任到人 |
| `CostCenter` | `gospel-prod` | 财务分摊 |
| `Component` | `app` / `qdrant` / `pg` / `redis` / `nat` / `cos` | 成本归因 |
| `Tier` | `critical` / `standard` | 优先级/SLO |

- **强制**：新建设资源必须带 `Project`+`Env`+`Owner`；费用中心按标签出账单。
- ⚠️ **待复核**：ap-seoul 费用标签配额与「标签策略」强制能力（控制台确认）。

### 5.3 闲置资源清理
- **定期巡检**（周/月）：关机 CVM、未挂载云盘、空 CLB 监听器、过期快照、未用 EIP、低频 COS 对象（转低频/归档存储）。
- **生命周期规则**：COS 备份桶设过期（如 30/90 天滚动删）；云盘快照保留 N 份。
- **回收机制**：staging 环境非工作时段自动停机（若独立 VPC）。

### 5.4 NAT 出流量优化（核心降本动作）
NAT 出流量是**头号变动成本**（LLM/임베딩/리랭크/Langfuse 出站），运营动作：
1. **限流**：应用层 `RATE_LIMIT_ENABLED` + WAF CC 防护，防滥用与成本失控（delivery C9）。
2. **缓存命中**：提升 Redis 缓存命中率（热门问答/检索结果），减少重复 LLM/임베딩 调用。
3. **本地推理评估**：评估将 KURE(1024) / bge_m3 **改为本地推理**（C6 计算型或 GPU 节点）→ 省 NAT 出网费、降延迟（product-expert 决策待确认 #3；架构师 R4）。⚠️待确认本地推理规格与成本权衡。
4. **同地域端点**：确认 LLM/임베딩 API 是否支持 ap-seoul 私有网络接入（降延迟+可能降本，架构师 R1）。
5. **流量监控**：NAT 出流量按目标域名细分（CLS 解析出站日志），识别异常高成本调用。

---

## 6. 运营风险与完成标准

### 6.1 运营风险与缓解

| # | 风险 | 表现 | 缓解（运营动作） |
|---|------|------|------------------|
| R-hand | **交接遗漏** | 某组件无 Runbook/无权限，故障时无人能处置 | §1.3 检查单全勾 + 验收演练（§1.5）；逐项签字 |
| R-doc | **文档过时** | 架构/网络已变但 Wiki 未更新 → 误操作 | 变更即更新 Wiki + on-call 群公告；季度文档审计 |
| R-alert | **告警疲劳** | 误报多 → 真告警被忽略（MTTR 升高） | 合并/去重/静默；每周降噪复盘；错误预算治理 |
| R-secret | **密钥泄露** | `.env`/镜像残留、AK/SK 长期不轮换 | SSM 全量托管 + 镜像扫描 + 90 天轮换 + CloudAudit 异常读告警（§3.3） |
| R-pipa | **PIPA 审计缺口** | PII 出境无记录、无加密举证、无保留/撤回 | 全部资源 ap-seoul + TLS/KMS + CLS/CloudAudit + 保留策略 + DPIA（如适用）；security-audit 季度核查 ⚠️待确认 PIPA 适用性 |
| R-slo | **SLO 无基线** | 无法判断是否劣化 | W3 建性能基线（delivery §5）→ §3.1 阈值校准 |
| R-drift | **配置漂移** | 手动改控制台未入 IaC → 环境不一致 | 优先 IaC（Terraform/编排）固化；手动变更登记 |
| R-cost | **成本失控** | NAT 出流量激增无人知 | §5 预算告警 + NAT 日预算 + 流量细分监控 |
| R-know | **知识单点** | 仅 1 人懂某系统，离职即盲区 | 双人 on-call + 交叉培训 + Wiki ownership 不孤立 |

### 6.2 「运营可独立接管」完成判据（Go/No-Go）

全部满足方可宣布交接完成、原开发团队退出日常 on-call：

1. ✅ **文档齐备**：§2 文档集已归档、ownership 已指派、版本受控。
2. ✅ **权限闭环**：5 个 CAM 角色实测边界正确，MFA 强制，审计禁删生效。
3. ✅ **密钥安全**：SSM 全量托管，无明文残留，轮换计划运行，异常读告警可达。
4. ✅ **可观测**：SLI/SLO 已设，告警演练通过，on-call 排班与升级链路生效。
5. ✅ **应急通过**：运营独立完成 **AZ 副本关停 drill**、**PG PITR 恢复**、**Qdrant 回灌** 三次演练。
6. ✅ **成本可知**：预算告警 + 标签 + NAT 监控已运行，月度账单可按组件归因。
7. ✅ **培训达标**：开发/运维/SRE 分级考核通过率 ≥ 80%，结业 Drill 独立处置成功。
8. ✅ **合规落地**：PIPA 落地项（驻留/加密/审计/保留）经 security-audit 核查；DPIA 完成（如适用）。

> 以上任一未达成 → **No-Go**，原团队须延长重叠期（建议至少 2 周并肩 on-call）直至补齐。

---

## 7. ⚠️ 待复核（控制台 / MigraQ）

1. ap-seoul **CODING Wiki/文档服务**区域可用性（§2.2 归档位置）。
2. **CLS / 云监控**在 ap-seoul 的告警渠道（电话/IM 集成）、保留期与配额（§3）。
3. **SLO 阈值**：`/chat` P95 延迟初值（3s）以 W3 性能基线校准（§3.1）。
4. **TKE** 在 ap-seoul 实际可用性与版本，决定 C3 培训时点（§4.2）。
5. **费用标签策略**强制能力、NAT 出流量按域名细分监控能力（§5.2/§5.4）。
6. **PIPA 适用性**：是否收集韩国居民 PII、是否需 DPIA、保留/撤回机制（§6.1 R-pipa）。
7. **本地推理 vs 托管 API**（KURE/bge_m3）成本权衡，决定 NAT 优化动作（§5.4）。
8. **LLM/임베딩/리랭크/Langfuse** 是否跨境传输（PIPA 出境影响，§6.1 R-pipa）。

---

*本文为运营交接/文档/培训/可观测/成本治理方案，沿用前序架构与实施产出，不重画拓扑、不重列实施步骤；所有 ⚠️项以腾讯云控制台 / MigraQ 复核为准。*
