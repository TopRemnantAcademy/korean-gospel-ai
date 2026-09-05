## 变更摘要 / Summary
<!-- 一句话说明这次 PR 做了什么 -->

## 关联问题 / Linked Issues
<!-- 例: 修复 A1 (chat.py:434 SSE newline)、关闭 #123 -->

## 变更类型 / Type
- [ ] Bug fix
- [ ] 新功能 / Feature
- [ ] 重构 / Refactor
- [ ] 文档 / Docs
- [ ] 配置 / Config

## 合并前自检清单 / Self-check (必须全绿)
- [ ] 本地 `ruff check` 与 `ruff format --check` 通过
- [ ] 新增/修改的 API 已用类型标注覆盖 `response_model`（避免 A2 类 500）
- [ ] 涉及 Qdrant 的操作确认**不与 ingest 并发**（embedded 单进程锁）
- [ ] 涉及 LLM 流式输出的，确认 SSE 格式正确（换行转义、心跳保活）
- [ ] 安全相关（PIPL 生物识别授权 / 自定义域名 SSRF / 钱包不变量 / 多租户 WORKSPACE_SCOPED_MODELS）已评审
- [ ] `pytest` 通过，关键路径有测试覆盖

## 测试说明 / Test plan
<!-- 怎么验证这次改动 -->
