# P0 待复核项闭环记录 — korean-gospel-ai → 腾讯云 ap-seoul

> 主理人记录（Phase 6 后补的 P0 闭环动作）
> 目的：把 `ap-seoul-final-plan.md` §10 的 ⚠️ 待复核项中「影响规格/成本的 5 项关键项」转为已确认决策；仅剩 Qdrant 集合规模待本地测量。

## 一、已闭环决策（用户提供）

| # | 待复核项 | 决策 | 对方案的影响 |
|---|---------|------|--------------|
| 1 | LLM 端点调用路径（R1/R4/C5） | **先实测再定**：默认 NAT 公网调用，上线前实测端点可达性与延迟 | W1 增加「LLM 端点连通性与延迟实测」门禁（沿用 delivery §2.1.7 退出验证）；保留项目已有 openai/anthropic fallback 链；关键路径降级策略保留 |
| 2 | 임베딩(KURE)/리랭크(bge_m3) 部署 | **先托管 API（走 NAT），稳定后评估本地推理降本** | MVP 用 API；CVM 取 S5 通用型即可，**暂不需 C6/GPU**；NAT 出网成本监控与限流必开；本地推理列为 W6 后优化项（ops §5.4） |
| 3 | PIPA 适用性（R5/C10） | **是，收集韩国居民 PII，需 DPIA** | 合规从「如适用」升为「必须」；security-audit 须在 W1 前启动 DPIA；保留/撤回机制纳入 W3 应用改造与 W6 验收；全部资源驻留 ap-seoul、TLS+KMS、CLS/CloudAudit 不变 |
| 4 | 预算上限 | **硬上限 < $500/月（USD，月度）** | ⚠️ 与「跨 AZ 完整 HA」原设计冲突 → 见第三节主理人决策：启动期收敛为**单 AZ 最小可行集**，跨 AZ HA 作为预算放开后的升级路径 |

## 二、已闭环项（全部完成）

| # | 项 | 决策 / 实测结果 | 对方案的影响 |
|---|----|----------------|--------------|
| 6 | Qdrant `gospel_kure` 集合规模 | **实测：2032 vectors，磁盘 92.1 MB**（脚本 `scripts/count_gospel_kure.py` 停 app 后运行取得）；同实例另有 `enhanced_rag_kure`、`rag_test_e2e` 两个集合（规模相近，均极小） | 向量体积极小 → **Qdrant 可与应用同机共置**（同台 CVM 4C8G 即可），无需独立大内存节点；snapshot→COS 体积也很小；单 AZ MVP 下 Qdrant 规格不再是成本瓶颈 |

> 5 项关键 ⚠️ **全部闭环**（4 项用户拍板 + 预算金额 + Qdrant 规模实测）。P0 阶段结束。

## 三、主理人决策：预算硬上限下的形态取舍（果断推荐）

**冲突点**：最终方案 §4/§9 默认「跨 AZ 完整 HA」（2 台 CVM 跨 AZ + PG 主备跨 AZ + Qdrant 副本跨 AZ），该形态在 ap-seoul 的月度成本**远超 $500**。硬上限 < $500/月 必须牺牲启动期冗余。

**推荐形态（单 AZ 最小可行集，MVP 上线）**：
- **单 AZ 起步**：1 台 CVM（**S5.LARGE8 / 4C8G 足够**，Qdrant 仅 2032 vectors/92MB 可同机共置，无需 M5/GPU）+ 单 NAT + 单 CLB；放弃跨 AZ 双副本（R6 单点风险由「定期快照 + IaC 一键拉起」缓解，非实时 HA）。
- **PostgreSQL**：最小双节点（一主一备**同 AZ** 或仅单节点 + 自动备份 PITR）。在 < $500 约束下推荐**单节点 + 日备 + WAL PITR**（牺牲自动故障切换，换成本）；若坚持主备则选最小 2C4G 同 AZ。
- **Redis**：**MVP 省去**（限流/缓存暂由应用层 + CLB/WAF CC 兜底）；后续预算放开再加 1GB 主从。
- **Qdrant**：单节点 server（replication_factor=1），定期 snapshot → COS；副本跨 AZ 留作升级项。
- **NAT 出网**：严格流量告警（日预算阈值），限流必开，控制 LLM/임베딩 变动成本（头号成本项）。
- **PIPA**：不受影响——单 AZ 仍在 ap-seoul，数据驻留/加密/审计全部满足；DPIA 仍必须。

**升级路径（预算放开或流量验证后）**：
单 AZ MVP → 加第 2 台 CVM 跨 AZ（CLB 多 AZ）→ PG 升跨 AZ 主备 → Qdrant 升 replication_factor≥2 → 可选 Redis 主从。该路径不改动应用（无状态），仅需扩资源 + 调 CLB/PG/Qdrant 配置。

> 此决策为**启动期成本与可用性的权衡**：接受「单 AZ = AZ 级故障需人工恢复（RTO 分钟~小时级，非秒级）」，换取 < $500/月 上线。若业务不允许单 AZ 风险，需上调预算或接受首月超预算。

## 四、对最终方案的影响摘要

- **PIPA = 必须**：security-audit 负责 DPIA、保留/撤回机制、加密举证，纳入 W3 改造与 W6 验收（Go/No-Go 判据加严）。
- **预算 < $500/月**：启动期采用第三节「单 AZ 最小可行集」；`ap-seoul-final-plan.md` 的跨 AZ HA 描述为「目标形态/升级路径」，非 MVP 默认。
- **임베딩 = 先 API**：CVM 取 S5 通用型，暂不需 C6/GPU；本地推理列为 W6 后优化项。
- **LLM = 先实测**：W1 增加端点连通性/延迟实测门禁，未通过前不进入 W3 全量验证。

## 五、关联交付物

- W1 账号/CAM 可执行 runbook：`deliverables/ap-seoul-w1-account-runbook.md`（**已生成**：5 子账号 `tccli cam AddUser` + MFA + 各最小权限策略 JSON + 实例角色信任/权限策略 + 执行前后验证；⚠️ 命令参数以控制台复核为准）
- 最终综合方案：`deliverables/ap-seoul-final-plan.md`
- Qdrant 规模计数脚本：`scripts/count_gospel_kure.py`
- 本闭环记录：`deliverables/ap-seoul-p0-closure.md`
