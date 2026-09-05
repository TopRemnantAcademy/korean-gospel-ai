# DB 优化方案 — 概览

为 AI Gospel Korean 后端数据库产出优化方案，覆盖用户指定的四个方向：慢查询/索引、表结构/迁移、连接池/并发、表膨胀/分区。

## 最重要的前提发现
- 后端引擎**实际默认 SQLite**（`db.py:56-63`），无连接池配置、无 async 层。"一行切 Postgres" 当前不安全 → 方案分成「SQLite/PG 通用」与「切 PG 后生效」两层。
- 迁移链**重复列漂移已代码核对确认**（R3 A3）：`c2fbb2654cf3` 与 `00b32788914f` 重复 ADD 同批列 + 索引；16/22 表由 `create_all` 建，Alembic 非单一事实来源。

## 方案优先级
- **P0** 迁移漂移修复（`stamp head` 对齐 + 重复迁移降级为空操作，零停机）+ 连接池/并发配置（切 PG 前置）。
- **P1** 补齐未建索引的 FK/过滤列（`CONCURRENTLY`）+ 修复 N+1 与无 `LIMIT` 全表 `.all()`（纯代码，零停机）。
- **P2** PG `pg_trgm` GIN 解决 `ILIKE` 全扫描；`JSON` → `JSONB` + GIN（按需）。
- **P3** 大表范围分区 + 保留策略；运行时监控（pg_stat_statements / 连接 / 膨胀）。

## 关键约束
所有索引 PG 侧用 `CREATE INDEX CONCURRENTLY`（不在事务块内）。未跑 `EXPLAIN ANALYZE`（无生产库访问），索引收益须上线前用 `EXPLAIN (ANALYZE, BUFFERS)` 复核，不臆造数字。破坏性 DDL 先在非生产库演练并备回滚。

## 交付物
- `deliverables/db_optimization_plan.md` — 完整方案（含诊断命令、Up/Down 脚本、验证/回滚、落地顺序）。
