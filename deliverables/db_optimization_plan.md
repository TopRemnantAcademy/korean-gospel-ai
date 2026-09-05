# AI Gospel Korean 后端数据库优化方案

> 范围：用户指定「AI Gospel Korean 后端 PostgreSQL」，覆盖 慢查询/索引、表结构/迁移、连接池/并发、表膨胀/分区 四个方向。
> 原则：**先测量、后优化**。本方案所有结论均来自**代码级静态证据**（未建索引的 FK、全表扫描 `ILIKE`、N+1 代码路径、迁移链漂移）。
> **我没有生产库访问权，也未执行 `EXPLAIN (ANALYZE, BUFFERS)`。所有索引/分区建议在上线前必须用 `EXPLAIN ANALYZE` 复核收益，本文不臆造执行计划或索引收益数字。**

---

## 0. 必须先知道的三个现状事实（决定方案怎么落地）

1. **引擎当前默认是 SQLite，不是 Postgres。**
   `backend/app/db.py:56-63` 的 `create_engine` 在 `DATABASE_URL` 未设置时回落到 `sqlite:///...`，且**完全没有连接池参数**（`pool_size` / `max_overflow` / `pool_pre_ping` / `pool_recycle` / `pool_timeout` 全部缺失），也无 async 层。代码注释声称"一行切 Postgres"，但在现有配置下直接切会有：连接泄漏/僵死连接、无连接上限、JSON 无法 GIN、无分区能力等问题。**切 PG 前必须先做第 2 节（连接池 + 引擎改造）。**

2. **迁移链存在重复列漂移（R3 审计 A3 已确认）。**
   - `c2fbb2654cf3_baseline_all_tables.py:41-77` 在 `document_version` / `subscriber` 上加了一批列，并建了 `ix_interaction_trace_id`。
   - `00b32788914f_e_a_token_quota_and_subscription_fields.py:23-59` **原样重复**了同一批列 + `ix_interaction_trace_id`，且名为"token quota"却一个 token/订阅列都没加。
   - 后果：在「`init_db()` 用 `create_all` 先建表 → `alembic upgrade head`」这个实际启动顺序下，`upgrade` 会对**已存在**的列再次 `ADD` → `OperationalError: duplicate column`。

3. **Alembic 不是单一事实来源。**
   16/22 张表（`source_artifact`、`document`、`document_version`、`index_snapshot`、`subscriber`、`interaction`、`audit_log`、`prompt_template`、`category`、`app_error_log`、`background_job`、`content_link`、`media_asset`、`qa_trend_snapshot`、`qa_admin_edit_log`、`qa_edit_draft`）根本不是迁移建的，而是 `db.py:128-136` 的 `Base.metadata.create_all` 建的。迁移只覆盖其余 6 张表。**这导致 `alembic upgrade head` 在全新库上会因 `batch_alter_table('document_version')` 找不到表而失败。**

---

## 优先级总览

| 优先级 | 项目 | 类型 | 适用环境 | 停机窗口 |
|---|---|---|---|---|
| **P0** | 迁移漂移修复 + Alembic 成为单一事实来源（或 stamp 对齐） | 迁移 | SQLite / PG 均适用 | 零停机（stamp） |
| **P0** | 连接池 / 并发配置（切 PG 前置条件） | 引擎配置 | 切 PG 后 | 仅重启 |
| **P1** | 补齐未建索引的 FK / 过滤列 | 索引 | SQLite / PG 均适用 | `CONCURRENTLY`（PG）/ 在线（SQLite） |
| **P1** | 修复 N+1 与无 `LIMIT` 全表扫描 | 代码 | SQLite / PG 均适用 | 零停机 |
| **P2** | `ILIKE` 全扫描 → PG `pg_trgm` GIN 三元组索引 | 索引 | 仅 PG | `CONCURRENTLY` |
| **P2** | `JSON` → `JSONB` + GIN（按需） | 迁移 | 仅 PG | 在线（注意锁） |
| **P3** | 大表范围分区 + 保留/清理策略 | 分区 | 仅 PG | 在线建分区（表交换） |
| **P3** | 运行时监控（pg_stat_statements / 连接 / 膨胀） | 监控 | 仅 PG | — |

---

## P0-1. 迁移漂移修复

### 诊断（先在非生产库执行）
```bash
cd backend
alembic history          # 看完整 revision 链
alembic current          # 看 alembic_version 当前 stamp
python -c "from app.db import engine; print(engine.url)"  # 确认实际用哪个库
```

### 修复路径 A（推荐，对**已上线/已有数据**的库零停机）
现状库其实已由 `create_all` 建好全部表与列，迁移相当于"已经应用"。因此不必再跑会报错的 `upgrade`，直接把版本表对齐：
```bash
# 确认列已存在（避免误 stamp 到不完整的库）
alembic stamp head
```
`stamp` **不执行任何 DDL**，只写 `alembic_version`，零风险、零停机。

同时把重复的 `00b32788914f` 改为**空操作**（保留 revision id，不动下游链），避免未来任何 `upgrade` 再次触发重复 ADD：

**Up**
```python
# 00b32788914f_e_a_token_quota_and_subscription_fields.py
# 修复：该 revision 原样重复了 baseline 的列/索引 ADD（A3 漂移）。
# 实际 schema 已由 baseline + create_all 建立，此处降级为空操作。
def upgrade() -> None:
    # 不再重复添加 document_version / subscriber 列与 ix_interaction_trace_id
    pass

def downgrade() -> None:
    pass
```

### 修复路径 B（全新环境 / CI，让 `alembic upgrade head` 真正可用）
要让 Alembic 成为单一事实来源，需要 baseline 自己**建表**而非只 ALTER。这是较大的重写，建议放在维护窗口作为后续任务：
1. 备份现有库。
2. 在空库上 `alembic revision --autogenerate` 重新生成自包含的 baseline（含全部 22 张表），替换当前分散的 6 个迁移。
3. 在已有库上 `alembic upgrade head` 验证（应先 stamp 到新 baseline 之前的状态，或直接对迁移表做一次性对齐）。
4. 保留 `init_db()` 仅作开发回退，生产只走 `alembic upgrade head`。

> ⚠️ 路径 B 涉及 revision 链重建，必须先在非生产库完整演练，并准备 `alembic downgrade` 回滚脚本。

---

## P0-2. 连接池 / 并发配置（切 PG 前置）

当前 `db.py:56-63` 无池参数。切 PG 前改造为：

```python
# backend/app/db.py (Postgres 路径)
from sqlalchemy import create_engine
from sqlalchemy.pool import QueuePool

def _make_engine(url: str):
    common = dict(
        echo=False,
        future=True,
        pool_pre_ping=True,        # 探测僵死连接，避免 PG 侧超时后拿到死连接
        pool_recycle=1800,         # 30min 回收，避开 PG 默认 8h 空闲断连
        pool_timeout=30,           # 取连接最长等待
    )
    if url.startswith("sqlite"):
        return create_engine(url, future=True,
                             connect_args={"check_same_thread": False})
    # Postgres
    return create_engine(
        url,
        poolclass=QueuePool,
        pool_size=10,              # 按 worker 数×每 worker 并发调；4 worker → 可 10~20
        max_overflow=20,           # 突发上限
        **common,
        connect_args={"options": "-c timezone=utc"},
    )

engine = _make_engine(DATABASE_URL)
```
迁移引擎仍用 `NullPool`（`env.py` 已是），保持短连接，正确。

**验证**：切 PG 后观察 `pg_stat_activity` 中 `state='idle in transaction'` 数量与连接总数是否稳定；`pool_pre_ping` 上线后僵死连接报错应消失。

---

## P1-1. 补齐缺失索引（代码级证据）

以下列被 JOIN / 过滤但**无索引**（证据见 `orm.py` 与各 service 的查询）：

| 表 | 缺失索引列 | 用途 / 调用点 |
|---|---|---|
| `index_snapshot` | `artifact_id` | `dedup_service.py:100` JOIN |
| `document_version` | `artifact_id` | 仅 `doc_id` 有索引 |
| `salvation_journey` | `interaction_id` | FK，无索引 |
| `subscriber` | `is_darakbang_member` | `subscriber.py:273` 全扫描过滤 |
| `subscriber` | `is_believer` / `salvation_status` | 分群查询 |
| `document` | `archived_at` / `doc_type` | `admin.py:190` 过滤 |
| `audit_log` | `action` / `entity_type` | 审计检索 |
| `qa_trend_snapshot` | `is_hidden` / `category` | `trending_service.py:294,297` 过滤 |

### PG 建索引（必须 `CONCURRENTLY`，且**不能**在事务块内执行）
```sql
-- 逐个执行，每条独立会话、不在 BEGIN 内
CREATE INDEX CONCURRENTLY ix_index_snapshot_artifact_id
  ON index_snapshot (artifact_id);

CREATE INDEX CONCURRENTLY ix_document_version_artifact_id
  ON document_version (artifact_id);

CREATE INDEX CONCURRENTLY ix_salvation_journey_interaction_id
  ON salvation_journey (interaction_id);

CREATE INDEX CONCURRENTLY ix_subscriber_darakbang_member
  ON subscriber (is_darakbang_member)
  WHERE is_darakbang_member = TRUE;   -- 部分索引：只覆盖真值，体积更小

CREATE INDEX CONCURRENTLY ix_document_archived_at
  ON document (archived_at) WHERE archived_at IS NULL;

CREATE INDEX CONCURRENTLY ix_audit_log_action_entity
  ON audit_log (action, entity_type, "when");
```

**SQLite 等价**（无 `CONCURRENTLY`、无部分索引）：
```sql
CREATE INDEX ix_index_snapshot_artifact_id ON index_snapshot (artifact_id);
CREATE INDEX ix_document_version_artifact_id ON document_version (artifact_id);
CREATE INDEX ix_salvation_journey_interaction_id ON salvation_journey (interaction_id);
CREATE INDEX ix_subscriber_darakbang_member ON subscriber (is_darakbang_member);
CREATE INDEX ix_document_archived_at ON document (archived_at);
CREATE INDEX ix_audit_log_action_entity ON audit_log (action, entity_type, "when");
```

**验证 / 回滚**：上线后用 `EXPLAIN (ANALYZE, BUFFERS)` 跑对应查询，确认从 Seq Scan → Index Scan；回滚即 `DROP INDEX [CONCURRENTLY]`（PG）/ `DROP INDEX`（SQLite）。

---

## P1-2. 修复 N+1 与无 LIMIT 全表扫描（代码层，零停机）

| 文件:行 | 问题 | 修复 |
|---|---|---|
| `app/services/glossary_service.py:283` | `for aid in alias_ids: query(GlossaryTerm).filter(id==aid).first()` → N 次查询 | 改为一次 `s.query(GlossaryTerm).filter(GlossaryTerm.id.in_(alias_ids)).all()` |
| `app/api/admin.py:190-200` | `Document.all()` 后循环懒加载 `d.versions` → 每文档一次 SELECT | 查询加 `joinedload(Document.versions)` |
| `app/api/documents.py:733-740` | `for doc_id in doc_ids: get_document(doc_id)` → N 次 | 改为 `s.query(Document).filter(Document.id.in_(doc_ids)).all()` |
| `app/services/push_service.py:93` | `s.query(Subscriber).all()` 无过滤无 limit → 每次推送全表载入内存 | 加状态过滤 + 分页（`yield_per` / `limit`+offset），或游标分页 |

示例（glossary_service）：
```python
# before
for aid in alias_ids:
    term = s.query(GlossaryTerm).filter(GlossaryTerm.id == aid).first()
# after
terms = s.query(GlossaryTerm).filter(GlossaryTerm.id.in_(alias_ids)).all()
```
示例（admin.py joinedload）：
```python
from sqlalchemy.orm import joinedload
docs = s.query(Document).options(joinedload(Document.versions)).all()
```

---

## P2-1. `ILIKE` 全扫描 → PG `pg_trgm` GIN（仅 PG）

`memory_service.py:69-70` 对 `interaction.question` / `answer` 做 `ILIKE('%'+search+'%')`，列无索引 → 大表全扫描。PG 用三元组索引：

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX CONCURRENTLY ix_interaction_question_trgm
  ON interaction USING gin (question gin_trgm_ops);
CREATE INDEX CONCURRENTLY ix_interaction_answer_trgm
  ON interaction USING gin (answer gin_trgm_ops);
```
> SQLite 无等价能力；如在 SQLite 下也要优化，需改 FTS5 虚拟表（`question`/`answer` 建 FTS5 索引，用 `MATCH` 查询）。属较大改造，单列后续任务。

**回滚**：`DROP INDEX CONCURRENTLY ix_interaction_question_trgm;`（同 answer）。

---

## P2-2. `JSON` → `JSONB` + GIN（仅 PG，按需）

当前所有 JSON 列用 `sa.JSON()`，PG 下是 `JSON` 类型，**无法 GIN 索引**（`topic_tags`、`scripture_refs`、`cited_versions` 等数组列全无索引）。切 PG 后，将需过滤的数组列改为 `postgresql.JSONB`：

```python
# orm.py 模型侧
from sqlalchemy.dialects.postgresql import JSONB
topic_tags = mapped_column(JSONB, nullable=True)
```
```sql
-- 迁移（在线，但 ALTER TYPE 取 ACCESS EXCLUSIVE 短锁，大表挑低峰）
ALTER TABLE document_version
  ALTER COLUMN target_stage TYPE JSONB USING target_stage::jsonb;
CREATE INDEX CONCURRENTLY ix_document_version_target_stage
  ON document_version USING gin (target_stage);
```
> ⚠️ `ALTER COLUMN ... TYPE` 对大表会锁表并重写；如 `document_version` 很大，先在非高峰用 `pg_repack` 或表交换方案。

---

## P3-1. 大表范围分区 + 保留策略（仅 PG）

写入密集、会无限增长、且有 `created_at`/`timestamp` 的表：`interaction`（聊天主表）、`app_error_log`、`audit_log`、`qa_trend_snapshot`（含软删除行堆积）。

以 `interaction` 按 `created_at` 年/月范围分区为例（表交换零停机）：
```sql
-- 1) 建分区父表（结构与现 interaction 一致，PK 含分区键）
CREATE TABLE interaction_new (LIKE interaction INCLUDING ALL)
  PARTITION BY RANGE (created_at);

-- 2) 建当前+未来分区
CREATE TABLE interaction_2026 PARTITION OF interaction_new
  FOR VALUES FROM ('2026-01-01') TO ('2027-01-01');
-- 自动建分区函数见下

-- 3) 低峰回填历史 + 重命名交换（用 CONCURRENTLY 思路：先 rename 旧表，再 ATTACH）
ALTER TABLE interaction RENAME TO interaction_old;
ALTER TABLE interaction_new RENAME TO interaction;
-- 旧数据按年 ATTACH 为独立分区，或归档后 DROP interaction_old

-- 自动建未来分区的函数（每月调度）
CREATE OR REPLACE FUNCTION ensure_interaction_partition()
RETURNS void LANGUAGE plpgsql AS $$
DECLARE
  start_date date := date_trunc('month', now()) + interval '1 month';
  end_date   date := start_date + interval '1 month';
  pname text := 'interaction_' || to_char(start_date,'YYYYMM');
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_class WHERE relname = pname) THEN
    EXECUTE format('CREATE TABLE %I PARTITION OF interaction_new
                    FOR VALUES FROM (%L) TO (%L)', pname, start_date, end_date);
  END IF;
END $$;
```
保留策略：对 `app_error_log` / `qa_trend_snapshot` 中 `deleted_at` 非空或超 N 天的行，定时 `DELETE`（或移到历史表）并 `VACUUM`。

---

## P3-2. 运行时监控（仅 PG）

```sql
-- 慢查询（需提前 CREATE EXTENSION pg_stat_statements）
SELECT query, calls, mean_exec_time, rows
FROM pg_stat_statements ORDER BY mean_exec_time DESC LIMIT 20;

-- 未使用 / 冗余索引
SELECT schemaname, relname, indexrelname, idx_scan
FROM pg_stat_user_indexes WHERE idx_scan = 0 ORDER BY relname;

-- 长事务 / 空闲事务
SELECT pid, state, age(clock_timestamp(), xact_start) AS xact_age, query
FROM pg_stat_activity WHERE state <> 'idle' AND xact_start IS NOT NULL
ORDER BY xact_age DESC;

-- 表膨胀（需 pgstattuple 或 pgstattuple 近似）
SELECT relname, n_dead_tup, n_live_tup,
       round(n_dead_tup::numeric / NULLIF(n_live_tup,0) * 100,1) AS dead_pct
FROM pg_stat_user_tables ORDER BY dead_pct DESC NULLS LAST;
```

---

## 落地顺序建议

1. **P0-1**（stamp 对齐 + 重复迁移降级为空操作）→ 立即做，零停机，消除启动报错风险。
2. **P1-2**（N+1 / 全表 `.all()` 代码修复）→ 纯代码，零停机，先拿稳定收益。
3. **P1-1** 索引补齐 → 在目标库（先 SQLite 后 PG）用 `EXPLAIN ANALYZE` 验证后 `CONCURRENTLY` 建。
4. 决定切 PG → 先做 **P0-2** 引擎/池改造，再上 **P2 / P3**（trigram、JSONB、分区、监控）。
5. 路径 B（Alembic 单一事实来源重建）作为独立维护窗口任务，先于任何破坏性 schema 变更完成。

> 所有 `DROP` / `TRUNCATE` / `ALTER ... DROP COLUMN` / 分区交换均**先在非生产库演练并准备回滚脚本**，绝不在生产连接上直接执行未确认语句。
