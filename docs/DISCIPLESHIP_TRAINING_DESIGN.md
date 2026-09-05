# 제자훈련 시스템 — 상세 기획 설계서

> **상태**: 기획 완료 (구현 대기)
> **목적**: 녹취한 훈련 내용을 이미지로 업로드 → 운영자 검토 → 다음 단계로 넘어가는 단계별 제자훈련 시스템
> **대상**: 다락방 식구, 사역자, 집사 등 체계적 영적 성장이 필요한 사용자

## 1. 개요

현재 는 상담 중심의 '일상용' 서비스입니다. 제자훈련 시스템은 체계적인 영적 성장 경로를 제공하여, 사용자가 단계별 과제를 수행하고 운영자의 검토를 거쳐 다음 단계로 진행하도록 돕습니다.

```
사용자                        운영자(목사/인도자)
  │                              │
  ├─ 단계 목록 조회 ──────────────┤
  ├─ 현재 단계 가이드 확인 ──────┤
  ├─ 녹취본 이미지 업로드 ───────┤
  │                              ├─ 제출물 검토
  │                              ├─ 승인 또는 반려(피드백)
  │  ◀── 검토 결과 알림(Push) ───┤
  ├─ 다음 단계 잠금 해제 ────────┤
  └─ 영적 성장 추적 ─────────────┘
```

## 2. 데이터 모델 설계

### 2.1 DiscipleshipLesson (단계/레슨 정의)

```python
class DiscipleshipLesson(Base):
    """제자훈련 단계 정의 — 관리자가 커리큘럼을 구성."""
    __tablename__ = "discipleship_lesson"

    lesson_id: str (PK, uuid)
    step: int (unique, indexed)              # 단계 번호 (1, 2, 3...) — 진행 순서
    title: str                               # 예: "1단계: 복음의 확신"
    description: str                         # 단계 설명
    guide: Text                              # 마크다운 가이드 (과제 방법, 참고 성경구절)
    scripture_refs: list (JSON)              # ["요일 5:13", "롬 8:1"]
    target_salvation_stage: list (JSON)      # ["uncertain", "assured"] (기존 패턴 재사용)
    completion_criteria: str                 # 완료 조건 설명 (예: "핵심 구절 3개 암송")
    requires_image: bool (default True)      # 이미지 제출 필수 여부
    estimated_days: int (default 7)          # 예상 소요 일수
    order_index: int (default 0)
    active: bool (default True)
    created_at, updated_at
```

**초기 커리큘럼 예시**:
| Step | 제목 | 완료 조건 |
|------|------|-----------|
| 1 | 복음의 확신 | 요일 5:13, 요 5:24 암송 |
| 2 | 회개와 죄사함 | 요일 1:9, 회개 기도 녹취 |
| 3 | 성령의 인도 | 갈 5:22-23, 성령 열매 묵상 |
| 4 | 교제와 헌신 | 행 2:42, 다락방 모임 참여 |
| 5 | 사역과 전도 | 마 28:19-20, 복음 전하기 |

### 2.2 DiscipleshipSubmission (사용자 제출)

```python
class DiscipleshipSubmission(Base):
    """사용자의 단계별 제출물 — 녹취본 이미지 + 검토 상태."""
    __tablename__ = "discipleship_submission"

    submission_id: str (PK, uuid)
    subscriber_id: str (FK → subscriber, indexed)
    lesson_id: str (FK → discipleship_lesson)
    step: int (indexed)                      # 제출 시점의 단계 (이력 보존용)
    image_path: str                          # data/discipleship/{sub_id}/{step}/{uuid}.jpg
    image_thumbnail_path: Optional[str]      # 리사이즈된 썸네일 (Pillow)
    note: Optional[str]                      # 사용자 메모 (선택)
    status: str (default "pending")          # pending | approved | rejected
    # pending  — 운영자 검토 대기
    # approved — 승인됨 (다음 단계 잠금 해제)
    # rejected — 반려됨 (피드백과 함께 재제출)
    reviewer_id: Optional[str]               # 검토한 운영자
    review_note: Optional[str]               # 운영자 피드백
    reviewed_at: Optional[datetime]
    submitted_at: datetime (default now)
    created_at, updated_at
```

### 2.3 DiscipleshipProgress (사용자별 진행 상태)

```python
class DiscipleshipProgress(Base):
    """사용자별 제자훈련 진행 상태 — 한 사용자당 1행."""
    __tablename__ = "discipleship_progress"

    progress_id: str (PK, uuid)
    subscriber_id: str (FK → subscriber, unique, indexed)
    current_step: int (default 1)            # 현재 진행 중인 단계
    completed_steps: list (JSON)             # [1, 2, 3] 완료한 단계들
    started_at: datetime (default now)
    last_activity_at: datetime (default now, onupdate)
    total_submissions: int (default 0)
    approved_count: int (default 0)
    rejected_count: int (default 0)
```

> **설계 근거**: `SalvationJourney` 모델(`orm.py:340`)의 시계열 추적 패턴을 참고. Progress는 현재 상태 스냅샷, Submission은 이력.

## 3. API 엔드포인트 명세

### 3.1 모바일 (회원 전용)

| 메서드 | 경로 | 설명 | 요청 | 응답 |
|--------|------|------|------|------|
| GET | `/mobile/discipleship/lessons` | 단계 목록 + 내 진행 상태 | — | `{ lessons: [...], progress: { current_step, completed_steps } }` |
| GET | `/mobile/discipleship/lessons/{step}` | 특정 단계 상세 | — | `{ lesson, my_submission, can_submit }` |
| POST | `/mobile/discipleship/lessons/{step}/submit` | 이미지 업로드 제출 | multipart: `file`, `note` | `{ submission_id, status: "pending" }` |
| GET | `/mobile/discipleship/submissions/{id}` | 내 제출 상태 조회 | — | `{ status, review_note, reviewed_at }` |

**이미지 업로드 상세**:
```
POST /mobile/discipleship/lessons/{step}/submit
Authorization: Bearer {token}
Content-Type: multipart/form-data

file: (binary image)
note: "이번 주 암송 완료했습니다"
```

**검증 규칙**:
- 이미지 포맷: JPEG, PNG, WebP (`Pillow`로 검증)
- 최대 크기: 10MB
- 썸네일 자동 생성: 400px 너비 (`Pillow.thumbnail()`)
- 저장 경로: `data/discipleship/{subscriber_id}/{step}/{uuid}.jpg`

### 3.2 관리자 (운영자 전용)

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/admin/discipleship/lessons` | 전체 커리큘럼 관리 |
| POST | `/admin/discipleship/lessons` | 단계 생성 |
| PATCH | `/admin/discipleship/lessons/{id}` | 단계 수정 |
| GET | `/admin/discipleship/submissions` | 대기 중 제출물 목록 (`status=pending`) |
| GET | `/admin/discipleship/submissions/{id}/image` | 제출 이미지 조회 |
| POST | `/admin/discipleship/submissions/{id}/review` | 검토 (승인/반려 + 피드백) |

**검토 액션**:
```json
POST /admin/discipleship/submissions/{id}/review
{
  "action": "approve",        // approve | reject
  "note": "잘했습니다! 다음 단계로 진행하세요."
}
```

승인 시:
1. `Submission.status = "approved"`
2. `Progress.completed_steps`에 단계 추가
3. `Progress.current_step` 다음 단계로 증가
4. Push 알림 발송 (기존 `push_service` 재사용): "🎉 {step}단계 승인! 다음 단계가 열렸습니다."
5. 영적 여정 `SalvationJourney`에 전환 기록 (선택)

반려 시:
1. `Submission.status = "rejected"`
2. Push: "📝 {step}단계 피드백이 있습니다. 확인해 주세요."
3. 재제출 가능 (같은 단계)

## 4. UI 흐름도

### 4.1 모바일 — 제자훈련 탭 (신규 6번째 탭)

```
┌─────────────────────────────────────┐
│  상담 성경 찬양 영성 기록 제자       │  ← 6개 탭
├─────────────────────────────────────┤
│                                     │
│  📋 제자훈련                         │
│                                     │
│  ┌─────────────────────────────┐   │
│  │ ✅ 1단계: 복음의 확신         │   │  완료 (초록)
│  │    제출: 2026-07-01 승인됨    │   │
│  └─────────────────────────────┘   │
│  ┌─────────────────────────────┐   │
│  │ 🔄 2단계: 회개와 죄사함       │   │  검토 대기 (노랑)
│  │    제출 검토 중...            │   │
│  └─────────────────────────────┘   │
│  ┌─────────────────────────────┐   │
│  │ ▶️ 3단계: 성령의 인도         │   │  진행 가능 (강조)
│  │    [가이드 보기] [제출하기]   │   │
│  └─────────────────────────────┘   │
│  ┌─────────────────────────────┐   │
│  │ 🔒 4단계: 교제와 헌신         │   │  잠김 (회색)
│  └─────────────────────────────┘   │
│  ┌─────────────────────────────┐   │
│  │ 🔒 5단계: 사역과 전도         │   │  잠김
│  └─────────────────────────────┘   │
│                                     │
└─────────────────────────────────────┘
```

**단계 카드 상태**:
- ✅ 완료: `border-left: 4px solid var(--accent)`, 체크 아이콘, 제출일/승인일 표시
- 🔄 검토 중: `border-left: 4px solid var(--gold)`, 회전 아이콘, "검토 중" 표시
- ▶️ 진행 가능: `border-left: 4px solid var(--accent-dark)`, 강조 배경, [제출하기] 버튼
- 🔒 잠김: 회색, 자물쇠 아이콘, 클릭 불가

**제출 화면** (진행 가능 단계 클릭 시):
```
┌─────────────────────────────────────┐
│  3단계: 성령의 인도                   │
├─────────────────────────────────────┤
│                                     │
│  📖 가이드                           │
│  갈라디아서 5:22-23을 묵상하고,       │
│  성령의 9가지 열매 중 오늘 가장       │
│  강하게 느낀 것을 기록해 보세요.      │
│                                     │
│  참고 구절: 갈 5:22-23               │
│                                     │
│  📷 녹취본 이미지 업로드              │
│  ┌─────────────────────────────┐   │
│  │     [📷 사진 선택]            │   │
│  │     또는 끌어다 놓기          │   │
│  └─────────────────────────────┘   │
│                                     │
│  📝 메모 (선택)                      │
│  ┌─────────────────────────────┐   │
│  │                             │   │
│  └─────────────────────────────┘   │
│                                     │
│         [제출하기]                   │
│                                     │
└─────────────────────────────────────┘
```

**이미지 업로드**:
- `<input type="file" accept="image/*" capture="environment">` — 카메라 직접 촬영 지원
- 미리보기 표시 후 제출
- 업로드 중 진행률 표시
- multipart/form-data (기존 `authHeaders()`에서 Content-Type 오버라이드 필요)

### 4.2 관리자 — 제자훈련 관리 (신규 Streamlit 페이지)

**`admin/pages/17_🎓_제자훈련.py`**

```
[탭 1: 대기 중 제출물]
  ┌──────────────────────────────────────────┐
  │ 👤 홍길동 · 3단계: 성령의 인도             │
  │ 📷 [이미지 미리보기]                       │
  │ 메모: "오늘 기쁨의 열매를 묵상했습니다"     │
  │ 제출: 2026-07-04 10:30                    │
  │ [✅ 승인] [❌ 반려] [피드백 입력창]         │
  └──────────────────────────────────────────┘

[탭 2: 전체 진행 현황]
  pandas DataFrame: 사용자별 current_step, completed_steps, 마지막 활동일

[탭 3: 커리큘럼 관리]
  단계 추가/수정/삭제 (DiscipleshipLesson CRUD)
```

## 5. 기술 고려사항

### 5.1 이미지 저장
- **경로**: `data/discipleship/{subscriber_id}/{step}/{submission_id}.jpg`
- **패턴**: `source_service.py`의 sha256 중복 감지 방식 참고
- **리사이즈**: Pillow로 업로드 시 썸네일(400px) 자동 생성 → 관리자 미리보기 최적화
- **보안**: 경로 순회 방지 (`subscriber_id`는 UUID 형식 검증, `step`은 정수)
- **백업**: `.gitignore`에 `data/discipleship/` 추가 (이미지 바이너리)

### 5.2 이미지 업로드 엔드포인트 구현 패턴
```python
@router.post("/mobile/discipleship/lessons/{step}/submit")
async def submit_lesson(
    step: int,
    file: UploadFile = File(...),
    note: str = Form(""),
    current_user: str = Depends(get_current_user),
):
    # 1. Pillow로 이미지 검증 (포맷, 크기)
    img_bytes = await file.read()
    if len(img_bytes) > 10 * 1024 * 1024:
        raise HTTPException(413, "이미지는 10MB 이하여야 합니다")
    try:
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(img_bytes))
        img.verify()  # 포맷 검증
    except Exception:
        raise HTTPException(400, "유효한 이미지가 아닙니다")

    # 2. 썸네일 생성
    img = Image.open(io.BytesIO(img_bytes))
    img.thumbnail((400, 400))
    # ... 저장
```

### 5.3 진행 상태 자동 업데이트
- 최초 `/mobile/discipleship/lessons` 호출 시 `DiscipleshipProgress` 행이 없으면 자동 생성 (`get_or_create` 패턴)
- 승인 시 트랜잭션으로 Progress + Submission 동시 업데이트

### 5.4 Push 알림 연동
- 승인/반려 시 `push_service.send_to_subscriber()` 호출
- 제목: "🎉 {step}단계 승인!" / "📝 {step}단계 피드백"
- 기존 푸시 인프라(스케줄러, VAPID) 그대로 재사용

### 5.5 OCR 확장 (선택, 향후)
- `pytesseract` + 시스템 Tesseract 바이너리로 녹취본 텍스트 추출
- 추출된 텍스트를 기존 RAG 파이프라인으로 인덱싱
- AI가 자동으로 제출물을 1차 평가 → 운영자 검토 부담 경감
- 의존성: `requirements.txt`에 `pytesseract` 추가, 배포 환경에 Tesseract 설치

### 5.6 기존 시스템과의 연동
- `salvation_status` 전환: 단계 완료 시 `SalvationJourney`에 기록 (예: 5단계 완료 → `assured` → `mature` 전환 후보)
- `darakbang_role` 연계: 제자훈련 수료자를 `leader` 역할 후보로 표시
- 상담 채팅에 진행 상태 주입: "제자훈련 3단계 진행 중이시네요" 맞춤 안내

## 6. 보안

- 이미지 경로 순회 방지: `subscriber_id` UUID 검증, `step` 정수 강제
- 업로드 파일 검증: Pillow `verify()`로 악성 파일 차단
- 권한: 본인 제출물만 조회 (`subscriber_id` 매칭 검증)
- 관리자 검토 권한: `check_admin` 인증
- 이미지 접근: signed URL 또는 회원 토큰 기반 (직접 URL 공유 차단)

## 7. 구현 우선순위 (향후)

| 단계 | 내용 | 예상 소요 |
|------|------|-----------|
| 1 | 데이터 모델 3개 테이블 + 자동 마이그레이션 | 0.5일 |
| 2 | 백엔드 엔드포인트 (모바일 + 관리자) | 1일 |
| 3 | 관리자 Streamlit 페이지 (검토 + 커리큘럼) | 1일 |
| 4 | 모바일 탭 UI (단계 목록 + 제출 폼) | 1.5일 |
| 5 | Push 알림 연동 | 0.5일 |
| 6 | (선택) OCR 자동 평가 | 2일 |

**총 예상**: 4.5일 (OCR 제외) / 6.5일 (OCR 포함)

## 8. 검증 체크리스트 (구현 시)

- [ ] 3개 테이블 자동 생성 확인 (main.py lifespan `[DB-PATCH]`)
- [ ] 이미지 업로드 → 저장 → 썸네일 생성 확인
- [ ] 모바일에서 단계 목록 + 잠금 상태 올바른 렌더링
- [ ] 운영자 승인 → 다음 단계 잠금 해제 확인
- [ ] Push 알림 발송 확인
- [ ] 경로 순회/악성 파일 업로드 차단 확인
- [ ] 대용량 이미지(10MB+) 거부 확인
