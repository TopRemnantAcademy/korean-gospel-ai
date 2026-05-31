# 🗑️ 핸드오프 ⑤ 삭제 명령서 (불필요 파일·코드·기능)

> 대상 모델에게: 아래를 **위에서부터 순서대로** 처리하라.
> 각 항목 = [확신도][대상][근거][명령][검증]. 🟢=즉시삭제 🟡=확인후 🔴=보류.
> **모든 삭제 후 `python -c "import backend.app.main"` + admin/user 기동 확인 필수.**
> ⚠️ 이 문서는 실제 grep 스캔(2026-05-31)에 근거함. 추측 아님.

---

## 🟢 GROUP A — 즉시 삭제 (참조 0 확인됨, 위험 0)

### A1. 모든 `__pycache__` + 버전 혼재 .pyc
- **근거**: 캐시 15개 디렉토리. Python 3.10(5)/3.12(91)/3.14(31) .pyc 혼재. 전부 재생성됨.
- **명령**:
  ```bash
  find . -type d -name "__pycache__" -not -path "./venv/*" -exec rm -rf {} + 2>/dev/null
  find . -name "*.pyc" -not -path "./venv/*" -delete 2>/dev/null
  ```
- **검증**: `python -c "import backend.app.main"` 정상.
- **재발방지**: `.gitignore`에 `__pycache__/`, `*.pyc` 확인.

### A2. Orphan .pyc (소스 삭제된 기능 잔재) — A1에 포함되나 명시
- **대상**: `admin_agent.cpython-312.pyc`, `ingest.cpython-312.pyc`, `mentoring.cpython-312.pyc`, `mentoring_schemas.cpython-312.pyc`, `pdf_vision_indexer.cpython-312.pyc`
- **근거**: **.py 소스 전부 없음**(GONE), main.py import 참조 **0건** 확인. 삭제된 기능(admin_agent/ingest/mentoring/pdf_vision)의 캐시 잔재.
- **명령**: A1으로 함께 제거됨. 별도 작업 불필요.
- **검증**: 재import 시 재생성 안 됨(소스 없으니).

---

## 🟡 GROUP B — 死코드 (확인 후 삭제)

### B1. `cleanup_pipeline.run_cleanup()` + `CleanupResult` — 진짜 死코드 ✅
- **위치**: `cleanup_pipeline.py:79(CleanupResult), :155(run_cleanup)`
- **⚠️ 확인된 사실**: `/cleanup` 엔드포인트(`run_cleanup_endpoint`, documents.py:680)는 `extract_terms()`를 **직접** 호출함. `run_cleanup()`을 **전혀 안 씀**. → `run_cleanup()`/`CleanupResult`는 참조 0의 死코드.
- **명령**:
  1. `grep -rn "run_cleanup\b\|CleanupResult" backend admin --include="*.py" | grep -v "def run_cleanup\|class CleanupResult"` → 0건 재확인.
  2. `run_cleanup()`, `CleanupResult` 삭제.
  3. `extract_terms()`, `extract_metadata()`는 **반드시 유지**(INGEST·glossary·/cleanup 엔드포인트 사용).
- **검증**: admin 자료흐름 cleanup 버튼 정상 + import 통과.
- **참고**: `/cleanup` 엔드포인트 자체는 admin이 쓰므로 **유지**.

### B2. `document_indexer.py` — MVP 잔재 격리
- **위치**: `backend/app/services/document_indexer.py`
- **참조**: `api/eval.py:21,123`, `scripts/ingest_documents.py:18,32` (개발/평가 전용, **프로덕션 아님**)
- **근거**: DB publish 없이 폴더→Qdrant 직접 인덱싱. 정식 경로(publish_service→ingest_pipeline)와 청킹·메타 정책 불일치 → 같은 컬렉션 오염 위험.
- **명령** (택1):
  - **권장**: eval.py·ingest_documents.py를 정식 publish 경로로 전환 후 `document_indexer.py` 삭제.
  - **차선**: 파일 상단에 "⚠️ EVAL 전용, 프로덕션 컬렉션 금지" 주석 + 별도 컬렉션(`gospel_eval_*`) 강제.
- **검증**: 프로덕션 검색이 publish 청크만 보는지.

---

## 🟡 GROUP C — inbox 기능 완전 제거 (사용자가 이미 폐기 결정)

> ⚠️ inbox는 **루트 파일이 아니라** documents.py 안 + admin이 import 중. 3곳을 함께 처리해야 안 깨짐.

### C1. inbox 기능 3곳 동시 제거
- **위치**:
  - `backend/app/api/documents.py:124~180` — `_INBOX_DIR`, `@router.get("/inbox") list_inbox()`, `@router.post("/ingest-inbox") ingest_inbox_async()`
  - `admin/lib/api_client.py:114` — `ingest_inbox_async()` 클라이언트 함수 + `list_inbox`
  - `admin/pages/2_📥_Upload.py:19` — `import ... list_inbox, ingest_inbox_async`
- **근거**: 사용자가 "임시저장/보관함/inbox 불필요" 명시(이전 세션). 업로드는 직접 발행 방식으로 전환됨.
- **명령** (순서 중요):
  1. `Upload.py`에서 `list_inbox, ingest_inbox_async` import 및 사용 UI 블록 제거.
  2. `api_client.py`에서 `ingest_inbox_async`, `list_inbox` 함수 제거.
  3. `documents.py`에서 inbox 라우트 2개 + `_INBOX_DIR` 헬퍼 제거.
  4. `data/inbox/` 폴더 비었으면 삭제.
- **검증**: admin Upload 페이지 정상 로드 + 직접 업로드 발행 동작 + `import backend.app.main` 통과.

---

## 🟡 GROUP D — 문서·배치 정리 (루트가 너무 산만함)

### D1. 루트 .md 9개 → README 중심 통합
- **대상**: `AGENT_BRIEFING.md`, `AI_COLLABORATION_GUIDE.md`, `PROCESS_MAP.md`, `PROJECT_VISION.md`, `START_HERE.md`, `ORDERS.md`, `ORDERS_COUNSELING.md`
- **근거**: 루트에 안내·기획 문서 9개 난립. 진입점 불명확.
- **명령**:
  - `START_HERE.md` + `README.md` → README 하나로 통합.
  - `ORDERS.md`, `ORDERS_COUNSELING.md`(완료된 작업지시서) → `docs/archive/`로 이동(이력 보존).
  - `AGENT_BRIEFING.md`, `AI_COLLABORATION_GUIDE.md`, `PROCESS_MAP.md`, `PROJECT_VISION.md` → `docs/`로 이동.
- **검증**: 루트엔 README.md, CHANGELOG.md만. 나머지 docs/.

### D2. docs/ 중복 가이드 통합
- **대상**: `docs/TUNNEL_GUIDE.md` + `docs/FREE_TIER_GUIDE.md` (+ STEP4_TUNNEL.bat)
- **근거**: 터널/무료배포 가이드 분산. HANDOFF_1(서버이전)과 주제 겹침.
- **명령**: 서버 배포 관련은 HANDOFF_1로 링크 통합. `MASTER_PROMPT_EPIC_G.md`(완료 EPIC)는 archive로.

### D3. .bat 10개 검토
- **대상**: `BACKUP/DIAGNOSE/RESET_ALL/RESTORE/SCHEDULE_BACKUP/UNSCHEDULE_BACKUP/STEP1~4.bat`
- **근거**: 10개 중 실사용 확인 필요. STEP1~4는 설치/인덱싱/기동/터널 = 유효. BACKUP/RESTORE류는 scripts/*.py 래퍼.
- **명령**: 실사용 안 하는 bat만 제거. STEP1~4 + BACKUP/RESTORE는 보존. **삭제 전 사용자 확인**.

---

## 🔴 GROUP E — 보류 (삭제 금지)

- **`scripts/upgrade/`** (base.py, checks.py, rollback.py, tier_0_to_0_5.py) — **실코드**, tier 업그레이드 시스템. 보존.
- **`scripts/` 운영도구** (backup/restore/migrate/seed/tune/diagnose) — 보존.
- **`gateway_server.py`** — 루트에 없음(이미 정리됨). 해당 없음.
- **requirements 3종** (기본/deploy/mentoring) — 환경별 분리. 보존. 단 기본 requirements.txt에 kiwipiepy/rank-bm25 반영됨(완료).
- **배포 설정** (`fly.toml`, `railway.toml`, `Dockerfile`, `alembic.ini`, `config.yml`) — 보존.

---

## 기능(코드) 중복 통합 — "삭제"가 아니라 "병합", 신중히

### F1. 용어추출 3중복 → 1 코어 (HANDOFF_4 C4)
- `cleanup_pipeline.extract_terms` + `extract_metadata` + `glossary_service.extract_terms_from_text`
- → `term_extraction.py` 공통 코어로 통합, 3개는 얇은 래퍼.

### F2. 분류기 LLM 3회 → 1회 (HANDOFF_4 C8)
- classify_input + classify_user_signal + detect_salvation_signal → 1회 통합 분류.

> F1·F2는 **HANDOFF_3 테스트(P0)가 깔린 뒤** 진행. 회귀 위험.

---

## 실행 순서 & 안전수칙
1. **A** (캐시) — 즉시, 위험 0.
2. **C** (inbox 3곳) — 폐기 결정된 기능, 함께 제거.
3. **B** (死코드) — grep 0 확인 후.
4. **D** (문서/배치) — 기능 영향 없음, 사용자 확인 권장.
5. **F** (기능 통합) — P0 테스트 후.
6. **E는 절대 건드리지 말 것.**
- 모든 삭제는 CHANGELOG.md 기록, git 커밋 단위 분리.
- 각 단계 후 `import backend.app.main` + admin/user 기동 확인.
