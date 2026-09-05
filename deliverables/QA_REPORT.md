# QA Report: korean-gospel-ai Pre-Launch QA (Exhaustive Tier)

**Date:** 2026-08-15
**Scope:** Full app (5 layers: API / Functional / Frontend / Data / Deployment)
**Method:** Static code analysis + test suite execution
**Test Suite:** 72 passed, 2 failed (stale tests)
**Issues Found:** 14 (Critical 3, High 4, Medium 5, Low 2)

## Health Score: 62/100

| Category | Score |
|----------|-------|
| Console/Errors | 70 |
| Links/Routes | 45 |
| Visual/UI | 85 |
| Functional | 55 |
| UX | 70 |
| Performance | 75 |
| Accessibility | 60 |
| Security | 50 |

---

## Go/No-Go: **NO-GO** (Conditional Go possible)

Fix 3 Critical issues + set PORTONE_CHANNEL_KEY → Go:
1. `app.py:350` — Fix missing admin page file reference (`9_👥_사람.py` → `9_👥_유저관리.py`)
2. `screens/index.js:1676` — Fix trending insight API path mismatch (`/insight/` → `/trending/insight/`)
3. `4_Status.py:385` — Fix bot_list() None iteration crash (`bot_list() or []`)

---

## Issues

### ISSUE-001: Admin mode crash — missing page file (Critical)
- **Location:** `app.py:350`
- `st.Page("admin/pages/9_👥_사람.py")` references non-existent file. Actual file: `9_👥_유저관리.py`

### ISSUE-002: Today tab insight 404 — API path mismatch (Critical)
- **Location:** `mobile/screens/index.js:1676` ↔ `backend/app/api/trending.py:116`
- Frontend calls `/trending/insight/{id}`, backend route is `/insight/{id}` (no prefix)

### ISSUE-003: Bot management "normal only" filter crash (Critical)
- **Location:** `admin/pages/4_📊_Status.py:385`
- `[u for u in bot_list() if ...]` crashes when bot_list() returns None

### ISSUE-004: False bulk bot success (High)
- **Location:** `admin/pages/4_📊_Status.py:152-180`
- count increments regardless of bot_toggle_flag() return value

### ISSUE-005: Payment channel key missing — 503 (High)
- **Location:** `.env` / `.env.production` → `PORTONE_CHANNEL_KEY=` (empty)

### ISSUE-006: Google OAuth not configured — 503 (High)
- **Location:** `.env` / `.env.production` → `GOOGLE_CLIENT_ID=` (empty)

### ISSUE-007: Admin activity events media_id filter breaks pagination (High)
- **Location:** `backend/app/api/events.py:264-309`
- media_id filter applied as post-filter after SQL offset/limit

### ISSUE-008: 2 stale test failures (Medium)
- `tests/test_config.py:21` — nvidia not in allowed provider set
- `tests/test_no_silent_swallow.py:86` — expects None, code returns _LocalTraceClient

### ISSUE-009: Auth token signature truncated to 64 bits (Medium)
- **Location:** `backend/app/api/auth.py:120` — `hexdigest()[:16]`

### ISSUE-010: Payment amount not re-verified (Medium)
- **Location:** `backend/app/api/payment.py:186-193`

### ISSUE-011: check_env.py BASELINE missing critical keys (Medium)
- **Location:** `scripts/check_env.py:24-46`

### ISSUE-012: API route prefix documentation mismatch (Low)
### ISSUE-013: .venv312 missing qdrant_client (Low)
### ISSUE-014: events._bulk_insert concurrency (Low)

---

## Known Issues Status (7 from prior audit)

| # | Issue | Status |
|---|-------|--------|
| 1 | admin bot tab crash | Partial fix (line 388 guard added, line 385 still broken) |
| 2 | false bulk bot success | NOT fixed |
| 3 | Today tab insight 404 | NOT fixed |
| 4 | integrated app admin crash | NOT fixed |
| 5 | mobile PWA overflow | FIXED (min-width:0 applied) |
| 6 | Streamlit venv re-exec | FIXED (PATH + direct exe) |
| 7 | Qdrant embedded lock | MITIGATED (startup cleanup + prod server mode) |
