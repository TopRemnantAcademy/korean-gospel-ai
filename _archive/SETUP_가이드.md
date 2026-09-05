# 🙏 한국어  — 설치/사용 가이드 (Windows)

**완성된 자료를 안전하게 받아 RAG로 운영하는 한국어 AI 시스템**

---

## ⏱ 흐름 요약 (총 25~35분)

| 단계 | 작업 | 시간 |
|---|---|---|
| 사전 | Python 3.10~3.12 확인 | 1분 |
| **STEP 1** | 패키지 설치 (1회) | 15~25분 |
| **STEP 2** | DB 초기화 (1회) | 5~10초 |
| **STEP 3** | 웹 시작 (매번) | 즉시 |
| 첫 Publish | 임베딩 모델 다운로드 (1.3GB, 1회) | 5~10분 |

---

## 0. Python 확인

`Win+R` → `cmd` → `python --version`
- 3.10/3.11/3.12 → OK
- 없으면 https://www.python.org → 설치 시 **"Add Python to PATH"** 체크

## 1. STEP1_INSTALL.bat 더블클릭
패키지 설치 (15~25분, 1회만)

## 2. STEP2_INDEX.bat 더블클릭
DB 테이블 + 폴더 생성 (5~10초)

## 3. STEP3_START.bat 더블클릭
검정창 3개 → 브라우저 자동 2개 (Admin 8501, User 8502)

---

## 🖥 두 가지 화면

| 화면 | URL | 누구를 위해 |
|---|---|---|
| **Admin** | http://127.0.0.1:8501 | 운영자 (자료 관리·검증·공개) |
| **User** | http://127.0.0.1:8502 | 일반 사용자 (단순 채팅, streaming 답변) |

---

## 📑 Admin 8개 페이지

| 페이지 | 역할 |
|---|---|
| 🏠 **Hub** | 운영 허브, 통계, Gemini 한도, 작업함 |
| 📚 **Library** | 자료 목록 + 검토 + 공개 + 아카이브 + 일괄작업 |
| 📥 **Upload** | 새 자료 올리기 (중복 자동 감지) |
| 🔎 **Search** | 채팅 + 출처 + 👍/👎 피드백 + 🔬 디버그 모드 |
| 📊 **Status** | 자료/인덱스 통계 + 평가셋 회귀 실행 |
| 💭 **대화기록** | 모든 Q/A 검색·조회·삭제 |
| 📝 **프롬프트** | AI 어조 직접 편집 (코드 수정 X) |
| 🏷 **분류관리** | 태그/시리즈/화자/구절 통계 |

💡 **각 버튼에 마우스를 올리면 기능 설명이 표시됩니다.**

---

## 🚀 첫 사용 5단계

1. **Admin → 📥 Upload**: PDF/TXT/DOCX 1개 + 제목/유형 입력 → 업로드
2. **Admin → 📚 Library**: 자료 클릭 → 체크리스트 4개 → 🟢 **검색에 공개하기**
   - 첫 공개 시 5~10분 (KURE-v1 모델 1.3GB 다운로드)
3. **Admin → 🔎 Search**: 한국어로 질문 → 답변+출처
4. **User UI (8502)**: 단순 채팅, 답이 한 글자씩 흘러나옴
5. **🏠 Hub**: 통계·작업함·Gemini 한도 확인

---

## 🛡 안전망 (운영자도 못 끔)

응답에 자동 추가:
- "자살/자해" 키워드 → 한국생명의전화 **1588-9191**
- "중독/약물" 키워드 → 중독상담 **1577-0199** + 의료 권유
- "구원받지 못합니다" 같은 정죄 표현 → 응답 차단

---

## 🔒 보안

- 모두 `127.0.0.1` 로컬 only — 외부에서 접근 불가
- 다른 사람과 공유 시: `.env`에 `APP_PASSWORD` 설정 + STEP3.bat 의 127.0.0.1 → 0.0.0.0 + 본인 IP 알려주기

---

## 💾 백업/복원

| 파일 | 역할 |
|---|---|
| `BACKUP.bat` | SQLite + Qdrant + 업로드 원본을 zip으로 묶음 |
| `RESTORE.bat` | 가장 최근 백업 복원 |
| `SCHEDULE_BACKUP.bat` | (관리자 권한 실행) 매일 새벽 3시 자동 백업 등록 |
| `UNSCHEDULE_BACKUP.bat` | 자동 백업 해제 |
| `RESET_ALL.bat` | 모든 데이터 초기화 (확인 필요) |
| `DIAGNOSE.bat` | 에러 발생 시 진단 |

---

## 📂 파일 구조

```
korean-gospel-ai/
├── STEP1_INSTALL.bat / STEP2_INDEX.bat / STEP3_START.bat
├── BACKUP.bat / RESTORE.bat / SCHEDULE_BACKUP.bat / UNSCHEDULE_BACKUP.bat
├── DIAGNOSE.bat / RESET_ALL.bat
├── .env / .env.example / requirements.txt
├── SETUP_가이드.md / USAGE_사용법.md / README.md / BETA_FLOW.md / deploy.md
│
├── backend/app/
│   ├── main.py / config.py / db.py
│   ├── api/         chat (+ /chat/stream) · retrieval · documents · memory · prompts · eval · admin
│   ├── services/    rag · qdrant · parser · chunker · tagger · bible · llm · embedding
│   │                · reranker · policy · safety · memory · prompt · dedup · eval · audit · tracing
│   ├── models/      orm.py (9 tables) · schemas.py
│   └── prompts/system.py
│
├── admin/                 (Admin UI: 8501)
│   ├── app.py (Hub) + pages/0~7
│   └── lib/api_client.py · auth.py
│
├── user/                  (User UI: 8502)
│   └── app.py
│
├── data/
│   ├── documents/         (기본 샘플 4개)
│   ├── uploads/           (업로드된 원본 파일)
│   └── eval/              (policy_rules.yaml + questions.json)
│
├── scripts/
│   ├── init_db.py / diagnose.py / ab_test.py / backup.py / restore.py
│
└── (자동 생성)
    ├── venv/              (가상환경)
    ├── .gospel.db         (SQLite — Document/Version/Subscriber/Interaction/Prompt 등)
    ├── .qdrant_local/     (벡터 DB)
    └── backups/           (zip 백업)
```

---

## 🆘 자주 만나는 문제

| 증상 | 해결 |
|---|---|
| `API 연결 실패` | Gospel API 검정창 확인. 5~10초 대기 |
| Publish 시 첫 응답 느림 | 정상. KURE 1.3GB + Reranker 600MB 1회 다운로드 |
| 답변이 영어로 나옴 | 같은 질문 다시. 또는 자료 부족 |
| `Gemini 한도 초과` | 잠시 대기 (분당 15, 일일 1500) 또는 새 키 발급 |
| 그 외 모든 에러 | `DIAGNOSE.bat` 실행 → `diagnose_result.txt` 공유 |

---

## 🧭 다음 단계 (현재 상태에서)

내부 운영 1인 사용에 필요한 모든 기능 완료. 자료 5~10개 실제로 올려보며 운영해보세요.

**준비됐을 때**: 사용자가 *"초기버전 완성"* 신호 → 베타 분리 (`BETA_FLOW.md`).
