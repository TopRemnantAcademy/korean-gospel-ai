# 🤖 AI Agent 협업 가이드

> 한국어로만 소통 / Communicate only in Korean

## 🤝 협업 규칙 (2026-05-19 강화)

### 규칙 1. 코드 *수정 또는 신규 생성* 시 반드시 추가

> 이전 규칙은 "수정 시" 였으나, 실제로는 신규 파일에만 적용되고 *수정된 파일* (chat.py, retriever.py, orm.py 등) 에는 누락됨. 이제 *둘 다* 강제.

```python
# =============================================================================
# 🔧 AI-AGENT-WORK
# Agent: [이름]                      # Claude | Cursor | Antigravity 등
# Timestamp: [YYYY-MM-DD HH:MM]
# Task: [수행한 작업 한 줄]
# Reason: [왜 이렇게 했는지]
# Related: [관련 파일 또는 ORDERS 항목 번호]
# Status: [COMPLETED/IN_PROGRESS/PENDING]
# =============================================================================
```

### 규칙 2. 헤더 이미 있으면 *덧붙이기* (덮어쓰기 금지)

기존 파일에 헤더가 있으면 **두 번째 헤더를 그 아래에 추가**:

```python
# =============================================================================
# 🔧 AI-AGENT-WORK
# Agent: Cursor
# Timestamp: 2026-05-18 23:00
# Task: subscriber_service.py 신규 생성
# Status: COMPLETED
# =============================================================================
# 🔧 AI-AGENT-WORK
# Agent: Cursor
# Timestamp: 2026-05-19 02:30
# Task: get_or_create 가 dict 반환하도록 변경 (B5 fix)
# Reason: chat.py 의 DetachedInstanceError 방지
# Related: ORDERS B5
# Status: COMPLETED
# =============================================================================
```

### 규칙 3. 변경 라인마다 코드 내 주석

```python
# ✏️ AI-CHANGE 2026-05-19 [Cursor]: trace.generation 위치 이동 (B1 fix)
# ⚠️ AI-WARNING: 이 import 는 chat.py 안에서 *지연 import* 임. 순환 참조 방지.
# ❌ AI-REMOVE 2026-05-18 [Antigravity]: 멘토링 모듈 완전 삭제 (C9)
```

### 규칙 4. ORDERS 항목과 1:1 매핑

모든 작업은 ORDERS.md 항목 번호 (B1, C2, D-C12 등) 를 *반드시* `Related:` 에 기록.

ORDERS 에 없는 자발적 추가? → 작업 *전* ORDERS 에 항목 신설 + 기획자 승인.

### 규칙 5. 보고 양식 (ORDERS.md 맨 아래 참조)

작업 완료 시 정해진 보고 양식 사용 — 검증 결과 + CHANGELOG 1줄 + PROCESS_MAP 영향 모듈.

## 📝 CHANGELOG 기록
- 모든 중요 작업은 `CHANGELOG.md`에 한국어로 기록

## ✅ 협업 원칙
1. 한국어로만 소통
2. 코드 수정 시 AI-AGENT-WORK 헤더 필수
3. Claude가 볼 수 있도록 명확하게 기록
