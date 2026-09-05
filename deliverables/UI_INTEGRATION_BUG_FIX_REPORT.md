# UI/연동 버그 수정 보고서

> **수정 일자**: 2026-07-22
> **수정 대상**: `deliverables/UI_INTEGRATION_BUG_AUDIT.md` 에서 발견된 12건 전부
> **검증**: Python 10개 파일 `py_compile` 통과, JavaScript `node --check` 통과, HTML 파서 통과

---

## 수정 내역

### BUG-01 (Critical): Streamlit 언어 전환 버튼 동작 안 함
- **파일**: `app.py:234-269` (`_render_lang_globe` 함수)
- **변경**: `components.html()` + `setComponentValue` 조합 → `st.button` 기반 폴백
- **상세**: `components.html()`은 반환값이 항상 `None`이므로 `setComponentValue(next)`가 부모로 전달되지 않았음. `st.button("🌐 한국어")` 형태로 변경 후 클릭 시 다음 언어 코드(`ko`→`zh`→`en`)를 반환하도록 수정. 반환 타입 `Optional[str]` 명시.

### BUG-02 (Critical): Streamlit 👍/👎 피드백 401 실패
- **파일**: `app.py:1327-1352` (`_send_feedback`), `app.py:2060-2073` (버튼 렌더링)
- **변경**: 
  1. `_send_feedback`에서 `st.session_state.auth_token`을 읽어 `Authorization: Bearer <token>` 헤더로 전송
  2. 게스트 사용자(토큰 없음)는 피드백 버튼 자체를 숨김 (`_can_feedback` 조건 추가)
- **상세**: 백엔드 `POST /feedback`이 Bearer 인증을 필수로 요구하지만 헤더가 없어 401이 발생하던 문제. 게스트는 UI에서 버튼이 보이지 않으므로 혼란 방지.

### BUG-03 (Critical): Admin 봇 관리 탭 전환 무시
- **파일**: `admin/pages/12_🤖_봇관리.py:87-251`
- **변경**: 헬퍼 함수 3개 분리 (`_user_label_of`, `_render_user_detail`, `_render_bulk_actions`) + 각 탭이 독립 변수 사용
- **상세**: Streamlit `st.tabs()`의 모든 `with` 블록이 순차 실행되어 마지막 블록의 값으로 덮어쓰이던 문제. 각 탭(`_users_all`/`_users_flagged`/`_users_suspicious`)이 독립적으로 데이터를 로드하고 자체 UI를 렌더링하도록 구조화. 폼/버튼 키 충돌 방지를 위해 `_form_suffix`/`_btn_suffix` 접미어 추가.

### BUG-04 (Critical): 청크 뷰어 최신 버전 미표시
- **파일**: `admin/pages/17_🧩_청크뷰어.py:98`
- **변경**: `versions[-1]` → `versions[0]`
- **상세**: 백엔드 `GET /documents/{doc_id}`는 `version_number` 역순 정렬(`reverse=True`)하므로 `versions[0]`이 최신. 기존 `versions[-1]`은 가장 오래된 v1을 미리보기하던 버그.

### BUG-05 (High): Streamlit 로그인 display_name 무시
- **파일**: `app.py:1879`
- **변경**: `_lem.split("@")[0]` → `d.get("display_name") or _lem.split("@")[0]`
- **상세**: 백엔드 `AuthResponse.display_name`을 우선 사용하고, 누락 시 이메일 접두사로 폴백. 회원가입 라인과 동일한 패턴 적용.

### BUG-06 (High): Admin 사람 관리 metric 중복
- **파일**: `admin/pages/9_👥_사람.py:76-87`
- **변경**: m4 metric을 "총 질문"(중복) → "회원가입 사용자"(`auth_status in [email, google]`)로 교체
- **상세**: m2와 동일한 "총 질문"이 2개 표시되던 문제. 의미 있는 다른 지표로 교체.

### BUG-07 (High): Admin 검색 테스트 target_lang/user_id 미전달
- **파일**: `admin/lib/api_client.py:422-455` (`chat()`), `admin/pages/3_🔎_Search.py:67-86, 171-178`
- **변경**: 
  1. `chat()` 시그니처에 `target_lang="ko"`, `user_id=None`, `user_context=None` 파라미터 추가
  2. Search 페이지 사이드바에 "응답 언어" selectbox + "사용자 ID (테스트)" text_input 추가
  3. `chat()` 호출 시 선택된 값 전달
- **상세**: 기존에는 항상 한국어 고정 + DEFAULT_USER 귀속이었던 것을 다국어 테스트 + 특정 사용자 컨텍스트 테스트가 가능하도록 확장.

### BUG-08 (High): 모바일 채팅 실패 시 user message 잔류
- **파일**: `mobile/screens/index.js:1024-1036`
- **변경**: 응답 실패 분기에 `AppState.set('chatMessages', history)` 롤백 추가
- **상세**: 실패한 user message가 chatMessages에 남아 다음 질문의 history에 포함되어 LLM 컨텍스트를 오염시키던 문제. 실패 시 이전 상태로 복원.

### BUG-09 (High): /admin/subscribers/list limit/offset 무시
- **파일**: `backend/app/api/subscriber.py:5, 46-58`, `backend/app/services/subscriber_service.py:179-188`
- **변경**: 
  1. `from fastapi import Query` 임포트 추가
  2. `list_all_subscribers(limit: int = Query(10000, ge=1, le=10000), offset: int = Query(0, ge=0))` 시그니처
  3. `get_all_subscribers(limit=10000, offset=0)` 서비스 함수 시그니처 + `.offset(offset).limit(limit)` 쿼리 적용
  4. 응답에 `total`, `limit`, `offset` 필드 추가
- **상세**: 프론트엔드가 전달하던 limit/offset이 백엔드에서 무시되던 문제. 호환성 유지를 위해 기본 10000(사실상 전체) 사용.

### BUG-10 (Medium): 모바일 index.html title/head 누락
- **파일**: `mobile/index.html:9, 18`
- **변경**: `<title></title>` → `<title>복음 채팅</title>`, `</head>` 닫기 태그 추가
- **상세**: 빈 title과 누락된 `</head>`로 인해 브라우저 탭이 빈 제목이고 일부 파서가 경고하던 문제.

### BUG-11 (Medium): 미디어 업로드 order_index 폼 필드 누락
- **파일**: `admin/pages/11_🎵_미디어업로드.py:56-66, 75-79`
- **변경**: 
  1. col1/col2 레이아웃 → col1/col2/col3 (3열)로 변경, col3에 `order_index` number_input 추가
  2. `admin_upload_media(order_index=int(order_index), ...)` 전달
- **상세**: 백엔드 `POST /admin/media`는 `order_index` Form 필드를 받지만 UI에 없어 항상 0으로 업로드되던 문제.

### BUG-12 (Medium): 미디어 업로드 페이지네이션 없음
- **파일**: `admin/pages/11_🎵_미디어업로드.py:98-145`
- **변경**: 20개/페이지 페이지네이션 도입
  - `_PAGE_SIZE = 20` 상수
  - `st.session_state[f"media_page_{category}"]`로 카테고리별 페이지 상태 분리
  - 이전/다음 버튼 + 페이지 표시 (1/N · 총 M개)
  - 범위 보정 로직 (삭제 후 페이지 초과 방지)
- **상세**: 미디어 100개 이상 시 전체 렌더링으로 Streamlit이 느려지던 문제 해결.

---

## 영향 받은 파일 (11개)

| 파일 | 수정된 BUG |
|---|---|
| `app.py` | BUG-01, BUG-02, BUG-05 |
| `admin/pages/3_🔎_Search.py` | BUG-07 |
| `admin/pages/9_👥_사람.py` | BUG-06 |
| `admin/pages/11_🎵_미디어업로드.py` | BUG-11, BUG-12 |
| `admin/pages/12_🤖_봇관리.py` | BUG-03 |
| `admin/pages/17_🧩_청크뷰어.py` | BUG-04 |
| `admin/lib/api_client.py` | BUG-07 |
| `backend/app/api/subscriber.py` | BUG-09 |
| `backend/app/services/subscriber_service.py` | BUG-09 |
| `mobile/screens/index.js` | BUG-08 |
| `mobile/index.html` | BUG-10 |

---

## 검증 결과

```
$ venv/Scripts/python.exe -m py_compile app.py admin/app.py admin/pages/3_🔎_Search.py \
    admin/pages/9_👥_사람.py admin/pages/11_🎵_미디어업로드.py admin/pages/12_🤖_봇관리.py \
    admin/pages/17_🧩_청크뷰어.py admin/lib/api_client.py backend/app/api/subscriber.py \
    backend/app/services/subscriber_service.py
(Exit Code 0 — 전부 통과)

$ node --check mobile/screens/index.js
screens/index.js OK

$ python -c "from html.parser import HTMLParser; ..."
index.html parse OK
```

---

## 권장 후속 작업

1. **런타임 검증**: Streamlit/uvicorn 서버를 실제 기동하여 각 버그 수정 사항이 의도대로 동작하는지 확인.
2. **회귀 테스트 케이스 추가**:
   - BUG-01: 언어 버튼 3회 클릭 시 ko→zh→en→ko 순환 확인
   - BUG-02: 게스트/로그인 사용자 각각 피드백 버튼 가시성 및 전송 성공 여부
   - BUG-03: 각 탭 전환 시 해당 필터의 사용자 목록이 표시되는지
   - BUG-07: zh/en 선택 후 응답이 해당 언어로 오는지
3. **보안 점검**: BUG-02 수정으로 게스트 피드백이 차단되므로, 게스트 UX에 피드백 수집 대체 수단(예: 익명 로컬 기록)이 필요한지 검토.
4. **DB 마이그레이션**: BUG-09의 limit/offset 지원으로 대량 사용자 환경에서 쿼리 성능 개선. 인덱스(`last_active_at`)가 이미 존재하는지 확인 권장.
