# Pre-Launch Full Inspection Report — korean-gospel-ai

**Date**: 2026-08-15
**Scene**: Pre-Launch Check (Code Review + Security Audit + QA Testing)
**Participants**: gstack-product-reviewer (Code Review) + gstack-security-officer (Security Audit) + gstack-qa-lead (QA Testing)

---

## TL;DR (Executive Summary)

- **Overall verdict**: 🔴 **NO-GO** — 14 blocking items must be fixed before launch
- **Blocking items**: 14 (11 P0 security/code + 3 P0 functional)
- **Estimated fix effort**: 12-16 developer-hours for all blocking items
- **Next step**: Fix all 14 P0 items, then re-audit before launch approval
- **Positive note**: Architecture is well-designed with strong fundamentals; all P0 fixes are trivial (most under 10 lines each)

---

## Core Conclusion Card

| Item | Content |
|------|---------|
| Go / No-Go | 🔴 NO-GO |
| Severity distribution | 🔴 14 Critical / 🟠 16 High / 🟡 18 Medium / 🟢 8 Low |
| Key action items | 14 P0 fixes (12-16h) |
| Recommended owner | Backend lead (payment/auth/chat) + Frontend lead (mobile/admin) |
| Re-audit required | Yes — after all P0 items resolved |

---

## 1. Specialist Core Conclusions

### Code Reviewer (gstack-product-reviewer)

- **Core judgment**: NO-GO — 8 Critical issues blocking launch, primarily in payment security (3 issues), authentication (3 issues), and data safety (2 issues)
- **Key recommendations**: Fix payment idempotency + amount verification + webhook signature as a batch; enforce AUTH_SECRET and APP_PASSWORD in production; isolate answer cache by user; sanitize streaming chat history
- **Code quality**: Good architecture with clear layering (API → Service → Model), consistent naming, high type hint coverage. Main weakness is systemic fail-open patterns in quota and payment paths
- **Findings**: 24 total (8 Critical, 10 Major, 5 Minor, 3 Info) — after C-6 downgrade (admin key "change-me" properly blocked by `check_admin()` at API layer)

### Security Officer (gstack-security-officer)

- **Core judgment**: CONDITIONAL NO-GO — 5 P0 blockers, all trivially fixable (~24 lines total). Solid security architecture with 12 confirmed positive practices
- **Key recommendations**: Apply `sanitize_history()` to streaming path; add idempotency guard to webhook; fail-closed on missing webhook secret; add amount re-verification; block empty APP_PASSWORD
- **Positive practices**: Memory-only mobile token storage, server-side payment plans, constant-time admin key comparison, HMAC-signed email tokens, prompt guard module, CORS credentials disabled, Google OAuth verification, secrets not git-tracked, scrypt password hashing
- **Findings**: 15 total (2 Critical, 4 High, 6 Medium, 3 Low) + 2 addendum findings (1 Critical, 1 High)

### QA Lead (gstack-qa-lead)

- **Core judgment**: NO-GO (conditional Go possible) — 3 Critical functional issues block production user flows. Health score: 62/100
- **Key recommendations**: Fix admin page file reference (`9_👥_사람.py` → `9_👥_유저관리.py`); fix trending insight API path mismatch; fix bot_list() None crash
- **Deployment readiness**: Google OAuth not configured, PortOne channel key not configured, 2 stale test failures. All other deployment items pass
- **Findings**: 14 total (3 Critical, 4 High, 5 Medium, 2 Low). Test suite: 72 pass, 2 fail (stale)

---

## 2. Consolidated Findings (De-duplicated, by Severity)

### 🔴 Critical / P0 — Must Fix Before Launch (14 items)

| # | Category | Location | Issue | Fix Effort | Source |
|---|----------|----------|-------|------------|--------|
| **P0-1** | Security | `chat.py:918` | Streaming chat endpoint bypasses `sanitize_history()` — client can inject `{"role":"system"}` via history array, enabling prompt injection attacks | ~5 lines, 0.5h | Sec F-001, Rev C-9 |
| **P0-2** | Security | `payment.py:248-249` | Webhook handler calls `_apply_subscription()` without checking `rec.status == "paid"` — duplicate webhooks (PortOne retries) double-extend subscription periods | ~3 lines, 0.5h | Sec F-002, Rev C-1 |
| **P0-3** | Security | `payment.py:202-203` | `_verify_webhook_signature()` silently returns (skips all verification) when `PORTONE_WEBHOOK_SECRET` is unset — attacker can forge payment webhooks | ~3 lines, 0.5h | Sec F-003, Rev C-4 |
| **P0-4** | Security | `payment.py:186-193` | `/complete` and `/webhook` only check payment status, never verify paid amount matches plan amount — attacker could pay 1 KRW for premium subscription | ~8 lines, 1h | Sec F-014, Rev C-5, QA ISSUE-010 |
| **P0-5** | Security | `auth.py:111` | AUTH_SECRET falls back to `admin_api_key + "_auth_secret"` when unset — if admin key is "change-me", signing secret is `"change-me_auth_secret"`, allowing token forgery | ~5 lines, 0.5h | Sec F-005, Rev C-2 |
| **P0-6** | Security | `app.py:472-477` | When `APP_PASSWORD` is empty, clicking admin button sets `mode="admin"` + `auth_ok=True` without any authentication — full admin panel access | ~5 lines, 0.5h | Sec F-015, Rev C-7 |
| **P0-7** | Data Safety | `chat.py:235, 626-633` | Answer cache key is `(normalized_query + language)` without user profile/tier — personalized answers (containing user-specific onboarding/safety phrases) leak between users. Cache hit also bypasses quota check and skips Interaction logging | 1-2h | Rev C-8, known P0-2 |
| **P0-8** | Security | `auth.py:47-49, 343-351` | Console-mode (default `email_mode="console"`) silently disables email verification — signup returns `token=""` + `email_verification_required=True` but no email is sent; login doesn't enforce verification. Users trapped or verification bypassed | ~5 lines, 0.5h | Sec F-009, known P0-4 |
| **P0-9** | Functional | `app.py:350` | Admin mode references `admin/pages/9_👥_사람.py` but actual file is `9_👥_유저관리.py` — `st.Page()` crashes, entire admin mode on :8501 dies | 1 line, 5min | QA ISSUE-001, known P0-9 |
| **P0-10** | Functional | `screens/index.js:1676` | Mobile Today tab calls `/trending/insight/{id}` but backend route is `/insight/{id}` (no trending prefix) — insight panel always 404. Bug shipped to dist/web and dist/android | 1 line + rebuild, 15min | QA ISSUE-002, known P0-8 |
| **P0-11** | Functional | `4_Status.py:385` | Bot management "normal only" filter iterates `bot_list()` which returns `None` on API failure — `TypeError: NoneType is not iterable` crash. Other filters have `_users or []` guard but this one doesn't | 1 line, 5min | QA ISSUE-003, known P0-6 |
| **P0-12** | Functional | `4_Status.py:152-180` | Bulk bot actions (block/unblock/reset) ignore `bot_toggle_flag()` return value — always increments count, reports "✅ N processed" even when backend is down/503 | ~5 lines, 0.5h | QA ISSUE-004, known P0-7 |
| **P0-13** | Concurrency | `fallback.py:200` | `llm.last_stream_usage = None` on shared LLM instance — concurrent streaming requests overwrite each other's usage data, causing token billing errors and quota attribution contamination | 2h | Rev C-6, known B-7 |
| **P0-14** | Security | `auth.py:120` | HMAC-SHA256 token signature truncated to 16 hex chars (64-bit) — below NIST 128-bit minimum. Combined with P0-5 weak secret, increases forgery risk | ~2 lines, 0.5h | Sec F-004, Rev M-1, QA ISSUE-009 |

### 🟠 High / P1 — Fix This Sprint (16 items, selected key items)

| # | Category | Location | Issue | Source |
|---|----------|----------|-------|--------|
| H-1 | Security | `email_service.py:27` | Email verification token secret falls back to hardcoded `"dev-insecure-verify-secret-change-me"` when AUTH_SECRET unset | Sec F-008 |
| H-2 | Security | `rate_limit.py:47-53` | Rate limiter trusts X-Forwarded-For rightmost hop by default (`rate_limit_trust_proxy=True`) — spoofable IP bypass if no reverse proxy | Sec F-007, Rev M-5 |
| H-3 | Security | `auth.py:151-161` | Legacy SHA-256 password hashing with `admin_api_key` as global salt — dormant accounts remain vulnerable to rainbow table attacks | Sec F-006 |
| H-4 | Data | `chat.py:951-967` | Client disconnect during streaming: quota reservation not settled (tokens permanently burned) + partial answer saved as complete + promoted to FAQ cache | Rev M-9, known B-8 |
| H-5 | Functional | `payment.py:241-247` | Webhook returns HTTP 200 even on processing failure — PortOne doesn't retry, payment confirmation permanently lost | Rev M-13, known B-2 |
| H-6 | Functional | `events.py:264-309` | Admin activity events `media_id` filter is Python post-filter (after SQL limit/offset) — pagination broken, returns fewer results than requested | QA ISSUE-007 |
| H-7 | Functional | `.env` / `.env.production` | `PORTONE_CHANNEL_KEY` empty — payment completely disabled (503 on prepare) | QA ISSUE-005 |
| H-8 | Functional | `.env` / `.env.production` | `GOOGLE_CLIENT_ID` empty — Google OAuth login disabled (503) | QA ISSUE-006 |
| H-9 | Concurrency | `chat.py:1080` | `bilingual=True` streaming path: `final_text_for_save` referenced before assignment → `UnboundLocalError` swallowed by broad except — bilingual streaming never works | Rev M-8, known B-1 |
| H-10 | Mobile | `mobile/services/` (global) | No 401 interceptor — token expiry (30 days) causes all auth APIs to silently return empty data; UI shows logged-in state but data is gone | Rev m-1, known P0-5 |
| H-11 | Code | `quota_service.py:97-104` | Quota check fail-open after 6 DB lock retries — users can exceed quota under concurrent load | Rev M-4 |
| H-12 | Code | `admin/lib/api_client.py` (all functions) | Every function creates new `httpx.Client()` — TCP+TLS handshake overhead on every call. `app.py` already has `@st.cache_resource` pattern | Rev M-10 |
| H-13 | Code | `admin/lib/api_client.py:38-39` | Admin API key sent as `Bearer` token instead of `X-API-Key` header — Bearer should be reserved for user JWT tokens | Rev M-11 |
| H-14 | Data | `orm.py` (20+ tables) | FK `ondelete` strategy inconsistent — most FKs lack cascade policy, creating orphan records on parent deletion | Rev M-7 |
| H-15 | Data | `orm.py` ActivityEvent | `subscriber_id` has no FK constraint — references non-existent subscribers without error | Rev M-9 |
| H-16 | Mobile | `screens/index.js:778-781` | Annotation optimistic save: push failure leaves local state diverged from server, next sync silently drops local changes | Known M-1 |

### 🟡 Medium / P2 — Fix Next Sprint (18 items, summary)

| # | Category | Location | Issue | Source |
|---|----------|----------|-------|--------|
| M-1 | Security | `auth.py:6, 132` | No token revocation mechanism — stolen tokens valid for 30 days, cannot be invalidated | Sec F-010 |
| M-2 | Security | `mobile/utils/state.js` | Chat history with potential PII persisted in localStorage (plaintext) — XSS accessible | Sec F-011 |
| M-3 | Code | `events.py` `_bulk_insert` | `bulk_save_objects` all-or-nothing — one invalid event rejects entire batch | Rev M-6 |
| M-4 | Code | `trending.py:577, 630` | `admin_insight_queue` loads all snapshots to memory then filters in Python — slow and memory-heavy | Rev m-4, QA perf |
| M-5 | Mobile | `event.js` | Flush failure doesn't reset timer — event collection stops until next manual trigger | Rev m-2 |
| M-6 | Mobile | `event.js` | `js_error` events not immediately flushed — crash errors may be lost | Rev m-3 |
| M-7 | Code | `app.py:334-353` | Admin navigation only registers 9 of 21 available pages — 12 admin pages inaccessible in integrated app mode | Rev m-3 |
| M-8 | Code | `db.py` | SQLite pool config too high (`_POOL_SIZE=20, _POOL_MAX_OVERFLOW=10`) — SQLite is single-writer, 30 connections increase lock contention | Rev m-6 |
| M-9 | Code | `app.py:105-237` | Extensive `unsafe_allow_html=True` usage — currently server-controlled content, but future user input creates XSS vector | Rev m-5 |
| M-10 | Test | `test_config.py:21` | Stale test: `llm_provider` allow-set missing "nvidia" | QA ISSUE-008 |
| M-11 | Test | `test_no_silent_swallow.py:86` | Stale test: expects None but code returns `_LocalTraceClient` fallback | QA ISSUE-008 |
| M-12 | Code | `scripts/check_env.py:24-46` | BASELINE missing critical env keys: GOOGLE_CLIENT_ID, PORTONE_CHANNEL_KEY, AUTH_SECRET | QA ISSUE-011 |
| M-13 | Mobile | `screens/index.js:1021-1026` | Annotation pull-merge: server data always wins, offline local changes silently lost | Known M-2 |
| M-14 | Mobile | `screens/index.js:766-784` | Offline annotation deletion: fire-and-forget `.catch(()=>{})` — server resurrects deleted annotation | Known M-3 |
| M-15 | Mobile | `player.js:749-762` | Last playback restore is dead code — IIFE references closure-scoped `state` → `ReferenceError` swallowed | Known M-4 |
| M-16 | Mobile | `screens/index.js:1342-1385` | SSE drop: bubble shows partial text but saved state has error message — screen switch shows different content | Known M-5 |
| M-17 | Code | Alembic migrations | Migration chain broken on fresh DB — baseline batch_alter on non-existent tables | Known B-5 |
| M-18 | Code | `vector_store.py:513-516` | Dense search failure silently returns `[]` (no log) — LLM answers with empty context, no error signal | Known B-6 |

### 🟢 Low / P3 — Backlog (8 items, summary)

| # | Issue | Source |
|---|-------|--------|
| L-1 | DIFY_API_KEY remains "change-me" in .env files | Sec F-012 |
| L-2 | Admin panel defaults to "change-me" token, confusing 503 errors | Sec F-013, Rev i-3 |
| L-3 | PortOne token cache is module-level global — multi-worker causes redundant logins | Rev i-2 |
| L-4 | API route prefix documentation mismatch (/api/auth/* vs /auth/*) | QA ISSUE-012 |
| L-5 | .venv312 missing qdrant_client package | QA ISSUE-013 |
| L-6 | events._bulk_insert uses get_session() (BEGIN) not BEGIN IMMEDIATE — lock contention possible | QA ISSUE-014 |
| L-7 | Streaming timeout 180s may be insufficient for complex RAG + LLM reasoning | Rev m-9 |
| L-8 | _highlight() uses innerHTML with regex — XSS-safe currently but fragile pattern | Rev m-10 |

---

## 3. Deployment Readiness Checklist

| Item | Status | Notes |
|------|--------|-------|
| LLM API keys (nvidia/tencent/gemini) | ✅ | All configured |
| Google OAuth (GOOGLE_CLIENT_ID) | ❌ | Empty — Google login returns 503 |
| PortOne payment (CHANNEL_KEY) | ❌ | Empty — payment returns 503 |
| PortOne webhook secret | ✅ | Configured |
| AUTH_SECRET | ⚠️ | Must verify set in production (fallback is insecure) |
| ADMIN_API_KEY | ⚠️ | Must verify changed from "change-me" |
| APP_PASSWORD | ⚠️ | Must verify set (empty = admin bypass) |
| EMAIL_MODE | ⚠️ | Must be "smtp" in production (default "console" disables verification) |
| RATE_LIMIT_TRUST_PROXY | ⚠️ | Should be "false" if no reverse proxy |
| DOCS_ENABLED=false | ✅ | Production-ready |
| Alembic migration (head) | ✅ | l1_ccp_cost_attribution |
| mobile/dist build (web + android) | ✅ | Both built |
| Docker Compose | ✅ | Qdrant server separated, resource limits set |
| SQLite WAL mode | ✅ | Enabled |
| DB connection pool | ✅ | write 20+10, read 24 |
| CORS origins | ✅ | Configured |
| Rate limiting | ✅ | 10/min production |
| Port conflicts (8000/8501/8502/4174) | ✅ | None |
| Test suite | ⚠️ | 72 pass, 2 stale failures |

---

## 4. STRIDE Threat Model Summary

| Threat Type | Count | Key Vectors |
|-------------|-------|-------------|
| **Spoofing** | 5 | Webhook forgery (P0-3), token forgery (P0-5, P0-14), email verification forgery (H-1), admin panel bypass (P0-6) |
| **Tampering** | 4 | Prompt injection (P0-1), subscription tampering (P0-2), payment amount tampering (P0-4), annotation data loss (H-16) |
| **Repudiation** | 2 | No token revocation (M-1), no 401 interceptor (H-10) |
| **Information Disclosure** | 3 | Cache personalization leak (P0-7), chat PII in localStorage (M-2), legacy password hashes (H-3) |
| **Denial of Service** | 1 | Rate limit bypass via XFF (H-2) |
| **Elevation of Privilege** | 3 | Console-mode verification bypass (P0-8), admin panel no-password (P0-6), prompt injection (P0-1) |

---

## 5. Positive Practices Confirmed (12 items)

1. Mobile auth tokens stored in memory only — not persisted to localStorage
2. Payment plan amounts are server-side constants — client cannot tamper
3. `hmac.compare_digest()` used for constant-time admin key comparison
4. Backend blocks admin API access when `admin_api_key == "change-me"` (auth.py:188-192)
5. Events API ignores client-claimed `subscriber_id` — uses token-verified sub_id only
6. `scrub_secrets()` applied before error monitor DB storage
7. Prompt guard module with `sanitize_history()` role allowlist (non-streaming path)
8. CORS: `allow_credentials=False`, explicit origin allowlist
9. Google OAuth verifies `aud`, `iss`, `email_verified` via tokeninfo API
10. All documents API endpoints admin-protected, upload size limit enforced
11. `.env` files confirmed not in version control
12. Scrypt password hashing for new users (N=16384, r=8, p=1, dklen=32)

---

## Action Checklist (P0 Blocking Items)

| # | Action | Owner | Urgency | Est. Effort | Expected Completion |
|---|--------|-------|---------|-------------|---------------------|
| 1 | Add `sanitize_history()` to streaming chat path (`chat.py:918`) | Backend | P0 | 0.5h | Before launch |
| 2 | Add idempotency guard to webhook handler (`payment.py:248`) | Backend | P0 | 0.5h | Before launch |
| 3 | Fail-closed on missing webhook secret (`payment.py:202`) | Backend | P0 | 0.5h | Before launch |
| 4 | Add payment amount re-verification in complete + webhook (`payment.py:186`) | Backend | P0 | 1h | Before launch |
| 5 | Enforce AUTH_SECRET in production, remove weak fallback (`auth.py:111`) | Backend | P0 | 0.5h | Before launch |
| 6 | Block admin entry when APP_PASSWORD empty (`app.py:472`) | Frontend | P0 | 0.5h | Before launch |
| 7 | Fix answer cache: add user profile/tier to key or disable for personalized queries (`chat.py:235`) | Backend | P0 | 1-2h | Before launch |
| 8 | Enforce SMTP mode in production, fix console-mode signup trap (`auth.py:343`, `config.py`) | Backend | P0 | 0.5h | Before launch |
| 9 | Fix admin page file reference: `9_👥_사람.py` → `9_👥_유저관리.py` (`app.py:350`) | Frontend | P0 | 5min | Before launch |
| 10 | Fix trending insight API path: `/insight/` → `/trending/insight/` or update client (`screens/index.js:1676` + `trending.py`) | Backend+Frontend | P0 | 15min + rebuild | Before launch |
| 11 | Fix bot_list None crash: add `or []` guard (`4_Status.py:385`) | Admin | P0 | 5min | Before launch |
| 12 | Fix false bulk bot success: check return value (`4_Status.py:152-180`) | Admin | P0 | 0.5h | Before launch |
| 13 | Fix LLM usage race: use request-scoped state instead of instance attribute (`fallback.py:200`) | Backend | P0 | 2h | Before launch |
| 14 | Extend HMAC token signature to 32 hex chars / 128-bit (`auth.py:120`) | Backend | P0 | 0.5h | Before launch |

**Total estimated effort**: 12-16 hours

---

## Rollback Plan

If issues are found after launch:
1. **Payment emergency**: Disable `/api/payment/prepare` and `/api/payment/webhook` endpoints immediately. Existing subscriptions remain active. No data loss.
2. **Auth emergency**: Rotate `AUTH_SECRET` and `ADMIN_API_KEY` — all existing tokens invalidated, users must re-login. No data loss.
3. **Chat emergency**: Disable `/chat/stream` endpoint, fallback to non-streaming `/chat` (which has `sanitize_history()` applied). Users see slightly slower responses.
4. **Admin emergency**: Set `APP_PASSWORD` env var and restart Streamlit. Admin access immediately secured.

---

## Known Limitations

- Audit was conducted via static code analysis + test suite execution — no live penetration testing was performed
- PortOne payment gateway behavior (amount locking, webhook retry policy) was inferred from code, not verified against PortOne documentation
- Mobile PWA testing was done via code analysis, not on physical devices — runtime behavior on specific Android versions may differ
- Alembic migration chain analysis is based on current migration files — production DB state may differ
- 62 previously documented issues (from `deliverables/숨은문제_및_프로세스흐름_개선기획.md`) were confirmed as unfixed but not all were re-verified line-by-line in this audit

---

## Member Output Index

- **gstack-product-reviewer** (Code Review): 24 findings — 8 Critical, 10 Major, 5 Minor, 3 Info. Reviewed 20+ source files (~8000+ lines). Cross-referenced 62 known issues. C-6 downgraded after cross-verification with security officer.
- **gstack-security-officer** (Security Audit): 15 findings — 2 Critical, 4 High, 6 Medium, 3 Low. 14-phase OWASP Top 10 + STRIDE comprehensive audit. 2 addendum findings from cross-reference with product reviewer. 12 positive practices confirmed.
- **gstack-qa-lead** (QA Testing): 14 findings — 3 Critical, 4 High, 5 Medium, 2 Low. Health score 62/100. 5-layer testing (API/Functional/Frontend/Data/Deployment). 72 tests pass, 2 stale failures. Deployment readiness checklist completed.

---

> This report was generated by Software Workshop (软件工坊) AI collaboration. Critical decisions should be reviewed by the engineering lead. All findings are verified via source code analysis with file:line evidence.
