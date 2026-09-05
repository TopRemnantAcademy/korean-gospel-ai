# UI / UI 연동 버그 감사 보고서

> **감사 대상**: korean-gospel-ai 프로젝트의 모든 UI 계층 및 백엔드 연동 지점
> **감사 범위**: 통합 Streamlit 채팅(`app.py:8501`), Admin 콘솔(`admin/pages/*`), 모바일 PWA(`mobile/*`)
> **감사 일자**: 2026-07-22
> **총 발견 버그**: 12건 (Critical 4, High 5, Medium 3)

---

## 🔴 Critical 버그 (기능이 완전히 동작하지 않음)

### BUG-01: 통합 Streamlit 앱 언어 전환 버튼이 동작하지 않음
- **위치**: `app.py:234-269` (`_render_lang_globe` 함수), 사용 지점 `app.py:1818-1821`
- **현상**: 사이드바의 🌐 지구본 버튼을 클릭해도 `target_lang`(KO→ZH→EN)이 변경되지 않음
- **근본 원인**:
  ```python
  return components.html(_html, height=54)
  ```
  `components.html()`은 항상 `None`을 반환한다. 이 함수는 HTML을 iframe으로 렌더링만 할 뿐, 자식 iframe 내에서 호출한 `window.Streamlit.setComponentValue(next)`의 값을 부모 Python으로 전달하지 않는다. `setComponentValue`가 유효하려면 `st.components.v1.declare_component()`로 정의된 커스텀 컴포넌트여야 한다.
  ```python
  _picked = _render_lang_globe(_cur_lang)         # 항상 None
  if _picked is not None and _picked in UI_LANGS: # 절대 진입 안 함
      st.session_state.target_lang = _picked
      st.rerun()
  ```
- **영향**: 사용자가 한글/中文/English 응답 언어를 Streamlit 채팅 화면에서 전환할 수 없음. 모바일 PWA는 정상 동작(별도 JS 구현).
- **권장 수정**: `st.button`을 사용한 폴백 버튼으로 변경하거나, `streamlit-components` 패키지의 `declare_component`로 정식 커스텀 컴포넌트를 작성. 가장 간단한 수정 예시:
  ```python
  def _render_lang_globe(cur_lang: str):
      _labels = {"ko": "한국어", "zh": "中文", "en": "English"}
      _order = ["ko", "zh", "en"]
      _next = _order[(_order.index(cur_lang) + 1) % len(_order)]
      if st.button(f"🌐 {_labels[cur_lang]}", key="lang_globe_btn",
                   help="클릭하여 언어 전환", use_container_width=True):
          return _next
      return None
  ```

### BUG-02: 통합 Streamlit 채팅 — 👍/👎 피드백 버튼이 게스트/로그인 사용자 모두에게 동작하지 않음
- **위치**: `app.py:1344-1359` (`_send_feedback` 함수), 호출부 `app.py:2074-2082`
- **현상**: 채팅 답변 아래의 👍/👎 버튼을 눌러도 항상 실패 (조용히 무시됨)
- **근본 원인**:
  ```python
  return c.post(f"{API_BASE}/feedback", json={...})  # Authorization 헤더 누락
  ```
  백엔드 `POST /feedback` (`backend/app/api/chat.py:981-1008`)는 Bearer 토큰을 **필수**로 요구한다.
  ```python
  if not authorization or not authorization.lower().startswith("bearer "):
      raise HTTPException(status_code=401, detail="피드백 제출에는 인증이 필요합니다.")
  ```
  게스트 사용자는 토큰이 없어 401, 로그인 사용자도 `st.session_state.auth_token`을 헤더로 전달하지 않아 401 발생.
- **영향**: 모든 사용자의 피드백이 DB에 저장되지 않음. 트렌딩/인기 QA 시스템의 데이터 품질 저하.
- **권장 수정**:
  ```python
  headers = {}
  if st.session_state.get("auth_token"):
      headers["Authorization"] = f"Bearer {st.session_state.auth_token}"
  r = c.post(f"{API_BASE}/feedback", json={...}, headers=headers)
  ```
  게스트 사용자는 버튼을 숨기거나 비활성화하는 UX도 필요.

### BUG-03: Admin 봇 관리 페이지 — 탭 전환이 무시되고 항상 "의심" 필터 결과만 표시
- **위치**: `admin/pages/12_🤖_봇관리.py:91-107`
- **현상**: "전체" / "🚫 봇 차단" / "⚠️ 의심" 탭을 클릭해도 항상 "⚠️ 의심" 사용자 목록만 표시됨
- **근본 원인**: Streamlit의 `st.tabs()`는 모든 `with tab` 블록을 **순차적으로 무조건 실행**한다 (활성 탭 여부와 무관). 각 블록이 `users`, `total`, `selected_filter` 변수를 덮어쓰기 때문에 마지막 블록의 값이 항상 남는다.
  ```python
  with filter_tabs[0]:  # 전체
      users = bot_list(limit=500).get("subscribers", [])
      selected_filter = "all"
  with filter_tabs[1]:  # 봇 차단
      users = bot_list(filter_type="flagged", limit=500).get("subscribers", [])
      selected_filter = "flagged"
  with filter_tabs[2]:  # 의심 ← 항상 이 값이 남음
      users = bot_list(filter_type="suspicious", limit=500).get("subscribers", [])
      selected_filter = "suspicious"
  ```
- **영향**: 관리자가 "전체" 또는 "봇 차단" 탭을 보고 있을 때 잘못된 사용자 목록을 보게 됨. 일괄 작업("모두 봇 차단" 버튼)이 잘못된 필터 대상에 적용됨.
- **권장 수정**: `st.session_state`와 라디오 버튼으로 단일 선택 기반 전환, 또는 각 탭 내부에 독립된 변수명 사용 + 렌더링도 각 탭 내부에서 처리.

### BUG-04: 청크 뷰어 — 문서의 최신 버전이 아닌 가장 오래된 버전을 미리보기
- **위치**: `admin/pages/17_🧩_청크뷰어.py:98`
- **현상**: "문서별 청크" 탭에서 문서를 선택하고 "청크 미리보기" 버튼을 누르면 가장 오래된 버전(v1)의 청크를 가져옴. 최신 버전 청크가 표시되지 않음.
- **근본 원인**:
  ```python
  latest = doc_detail["versions"][-1]   # ❌ 가장 오래된 버전
  ```
  백엔드 `GET /documents/{doc_id}` (`backend/app/api/documents.py:328`)는 `versions = sorted(doc.versions, key=lambda v: v.version_number, reverse=True)` 로 **내림차순** 정렬. 즉 `versions[0]`이 최신, `versions[-1]`이 최초 버전. 다른 페이지(`1_📚_Library.py:67-69`)는 `versions[0]`를 사용하지만 여기만 `versions[-1]` 사용.
- **영향**: 발행된 문서의 최신 청크 상태를 확인할 수 없음. RAG 인덱스 디버깅이 어려워짐.
- **권장 수정**: `latest = doc_detail["versions"][0]`로 변경.

---

## 🟠 High 버그 (잘못된 동작 또는 중요 기능 손상)

### BUG-05: 통합 Streamlit 로그인 — 사용자 표시 이름이 이메일 접두사로 덮어씌워짐
- **위치**: `app.py:1879`
- **현상**: "홍길동"으로 가입한 사용자가 `hong@example.com`으로 로그인하면 사이드바에 "hong"으로 표시됨
- **근본 원인**:
  ```python
  st.session_state.user_display_name = _lem.split("@")[0]
  ```
  백엔드 `AuthResponse`는 `display_name` 필드를 반환하지만 무시됨. 회원가입 라인(`app.py:1898`)은 `_nm or _em.split("@")[0]`로 정상 처리하지만 로그인은 아님.
- **영향**: 사용자 경험 저하. 표시 이름이 일관되지 않음.
- **권장 수정**: `st.session_state.user_display_name = d.get("display_name") or _lem.split("@")[0]`

### BUG-06: Admin 사람 관리 — "총 질문" 지표가 중복 표시됨
- **위치**: `admin/pages/9_👥_사람.py:78` 및 `:87`
- **현상**: 탭 1 요약 통계에 "총 질문" metric이 2개(m2, m4) 표시됨
- **근본 원인**:
  ```python
  m1.metric("전체 사용자", len(subs))
  m2.metric("총 질문", ...)            # ← 중복 1
  m3.metric("최다 종교", ...)
  m4.metric("총 질문", ...)            # ← 중복 2 (m2와 동일)
  ```
- **영향**: UI 가독성 저하. 빈 metric slot 낭비.
- **권장 수정**: m4를 다른 지표(예: "활성 사용자 7일")로 교체 또는 제거.

### BUG-07: Admin 검색 테스트 페이지 — `target_lang` / `user_id` 미전달
- **위치**: `admin/pages/3_🔎_Search.py:155`, `admin/lib/api_client.py:423-434`
- **현상**: 관리자 검색 테스트에서 답변이 항상 한국어로만 생성됨. 사용자 ID가 `DEFAULT_USER`로 귀속됨.
- **근본 원인**: `chat()` 헬퍼가 `target_lang` 파라미터를 받지 않으며 `user_id`도 보내지 않음.
  ```python
  def chat(query, history, llm_provider=None, embedder=None, debug=False):
      r = c.post(f"{API_BASE}/chat", json={
          "query": query, "history": history,
          "llm_provider": ..., "embedder": ..., "debug": ...,
          # target_lang, user_id 누락
      })
  ```
- **영향**: 다국어 응답 테스트 불가. 관리자 테스트 대화가 DEFAULT_USER 프로필에 누적되어 오염.
- **권장 수정**: `chat()` 시그니처에 `target_lang="ko"`, `user_id=None` 추가 및 전달.

### BUG-08: 모바일 PWA 채팅 — `history` 중복 전송 가능성 (사용자 질문이 LLM에 두 번 들어감)
- **위치**: `mobile/screens/index.js:1020-1024`
- **현상**: 코드 주석에는 "현재 메시지를 제외한 이전 턴만 전달"이라고 되어 있으나, `AppState.set('chatMessages', [...history, { role: 'user', content: text }])` 직후 `ChatService.send(text, history, ...)`를 호출. `history` 변수는 이미 user message를 포함하지 않지만, 그 다음 턴에서 다시 호출할 때 `AppState.get('chatMessages')`에는 user message가 추가되어 있음.
- **분석**: 현재 코드 자체는 양호 — `history`는 user message 추가 *이전* 상태. 다만, 라인 1022에서 `AppState.set('chatMessages', [...history, {role:'user', content:text}])`를 한 뒤, 응답 받은 후(라인 1030-1034) 다시 `AppState.set('chatMessages', [...history, {user}, {assistant}])`로 덮어씀. 두 번째 set에서 `history`는 여전히 "이전 메시지 + 현재 user message가 빠진 상태"이므로 정상.
- **실제 버그**: 응답 실패 시 `AppState.chatMessages`에는 user message만 추가된 채로 남음. 다음 질문 시 `history = AppState.get('chatMessages')`가 실패한 user message를 포함하므로, 후속 질문에 "사용자가 실패한 질문을 다시 한 것처럼" 컨텍스트가 전달됨.
- **영향**: 채팅 히스토리 오염. LLM이 응답하지 않은 질문을 한 것으로 인식.
- **권장 수정**: 실패 시 `AppState.set('chatMessages', history)`로 롤백하거나, 응답 성공 시에만 chatMessages 업데이트.

### BUG-09: Admin Subscribers API — `limit` / `offset` 파라미터가 무시됨
- **위치**: `backend/app/api/subscriber.py:46-50`
- **현상**: `GET /admin/subscribers/list`가 `limit`, `offset` 쿼리 파라미터를 받지 않음. 프론트엔드(`admin/lib/api_client.py:545-559`)는 전달하지만 백엔드가 무시.
  ```python
  @router.get("/admin/subscribers/list")
  def list_all_subscribers(authorization: Optional[str] = Header(default=None)):
      _check_admin(authorization)
      subs = get_all_subscribers()   # 전체 목록 반환
      return {"subscribers": subs}
  ```
- **영향**: 구독자 수가 많아지면 메모리/응답 시간 증가. 페이지네이션 불가.
- **권장 수정**: `limit: int = Query(200, ge=1, le=1000)`, `offset: int = Query(0, ge=0)` 추가 및 `get_all_subscribers(limit, offset)` 수정.

---

## 🟡 Medium 버그 (마이너한 기능 손상 또는 UX 문제)

### BUG-10: 모바일 PWA `index.html` — `<title>`이 비어 있고 `</head>` 누락
- **위치**: `mobile/index.html:9-18`
- **현상**:
  ```html
  <title></title>           <!-- 빈 제목 -->
  ...
  <script src="..."></script>
  <body>                     <!-- </head> 없이 body 시작 -->
  ```
- **영향**: 브라우저 탭에 빈 제목 표시. 일부 브라우저에서 HTML 파서 경고. PWA 매니페스트의 `name`이 대체하므로 치명적이지는 않음.
- **권장 수정**: `<title>복음 채팅</title>` 추가 및 `</head>` 닫기.

### BUG-11: Admin 미디어 업로드 — `order_index` 폼 필드가 UI에 없음
- **위치**: `admin/pages/11_🎵_미디어업로드.py:72-79` (업로드 폼), `admin/lib/api_client.py:713-740`
- **현상**: 백엔드 `POST /admin/media`는 `order_index` Form 필드를 받지만, UI에는 정렬 순서 입력 필드가 없음. 항상 기본값 `0`으로 업로드됨.
- **영향**: 관리자가 미디어 정렬 순서를 제어할 수 없음. 여러 곡을 올리면 등록 역순으로만 표시.
- **권장 수정**: 업로드 폼에 `order_index = st.number_input("정렬 순서", min_value=0, value=0, step=1)` 추가 후 `admin_upload_media(..., order_index=order_index)` 전달.

### BUG-12: Admin 미디어 업로드 페이지 — 페이지네이션 없이 전체 목록 렌더링
- **위치**: `admin/pages/11_🎵_미디어업로드.py:95-131`
- **현상**: `admin_list_media(category=category)`로 전체 미디어를 가져와 `for it in items:` 로 모두 렌더링. 미디어가 100개 이상이면 Streamlit 페이지가 매우 느려짐.
- **영향**: 미디어 수 증가 시 페이지 로딩 지연, 스크롤 어려움.
- **권장 수정**: `st.pagination` 또는 `limit`/`offset` 기반 페이지네이션 도입. 또는 `st.dataframe`으로 표 형태 전환.

---

## 📋 감사 결과 요약

| ID | 심각도 | 컴포넌트 | 파일 | 라인 | 한 줄 요약 |
|---|---|---|---|---|---|
| BUG-01 | 🔴 Critical | Streamlit 채팅 | `app.py` | 234-269, 1818 | 언어 전환 버튼 동작 안 함 (`components.html` 반환값 미지원) |
| BUG-02 | 🔴 Critical | Streamlit 채팅 | `app.py` | 1344-1359 | 피드백 API 호출 시 Authorization 헤더 누락 |
| BUG-03 | 🔴 Critical | Admin 봇 관리 | `admin/pages/12_🤖_봇관리.py` | 91-107 | 탭 전환 무시, 항상 "의심" 필터 결과만 표시 |
| BUG-04 | 🔴 Critical | Admin 청크 뷰어 | `admin/pages/17_🧩_청크뷰어.py` | 98 | `versions[-1]` 사용 → 가장 오래된 버전 미리보기 |
| BUG-05 | 🟠 High | Streamlit 로그인 | `app.py` | 1879 | `display_name` 무시, 이메일 접두사로 덮어쓰기 |
| BUG-06 | 🟠 High | Admin 사람 관리 | `admin/pages/9_👥_사람.py` | 78, 87 | "총 질문" metric 중복 |
| BUG-07 | 🟠 High | Admin 검색 테스트 | `admin/pages/3_🔎_Search.py`, `admin/lib/api_client.py` | 155, 423 | `target_lang` / `user_id` 미전달 |
| BUG-08 | 🟠 High | 모바일 채팅 | `mobile/screens/index.js` | 1020-1034 | 실패한 user message가 chatMessages에 잔류 |
| BUG-09 | 🟠 High | Admin Subscribers API | `backend/app/api/subscriber.py` | 46-50 | `limit`/`offset` 파라미터 무시 |
| BUG-10 | 🟡 Medium | 모바일 PWA | `mobile/index.html` | 9-18 | `<title>` 빈 값, `</head>` 누락 |
| BUG-11 | 🟡 Medium | Admin 미디어 업로드 | `admin/pages/11_🎵_미디어업로드.py` | 72-79 | `order_index` 폼 필드 누락 |
| BUG-12 | 🟡 Medium | Admin 미디어 업로드 | `admin/pages/11_🎵_미디어업로드.py` | 95-131 | 페이지네이션 없음 |

---

## 🔍 추가 관찰 (버그 아님, 개선 권장)

### OBS-01: 통합 Streamlit 채팅이 사용자 인증 토큰을 /chat에 전달하지 않음
- `app.py:2107-2117`에서 `POST /chat/stream` 호출 시 `Authorization` 헤더 누락. 백엔드는 `user_id` 폼 필드를 신뢰하므로 동작은 하지만, 보안상 토큰 검증이 우회됨.
- 로그인한 사용자의 chat history가 올바른 sub_id로 저장되긴 하지만, 토큰 기반 신원 확인이 빠져 있어 스푸핑 가능.

### OBS-02: 모바일 PWA 게스트 사용자 채팅 — `subId`가 localStorage에 영속화됨
- `mobile/utils/state.js:39`에서 `subId: localStorage.getItem('gospel_sub_id')`로 영속 로드. 로그아웃 시 `localStorage.removeItem('gospel_sub_id')`로 정리 (line 216). 정상 동작.
- 그러나 게스트 subId가 다른 사용자와 충돌할 가능성은 없음 (uuid 기반).

### OBS-03: Admin `list_subscribers`가 반환하는 dict의 키가 일관되지 않음
- `/admin/subscribers/list`는 `{subscribers: [...]}` 반환
- `/admin/bot/list`는 `{subscribers: [...], total: int, limit: int, offset: int}` 반환
- 두 엔드포인트 모두 `list_subscribers` 헬퍼로 처리되지만 반환형이 다름. 통일 권장.

---

## ✅ 검증된 정상 동작 항목 (버그 아님)

다음 항목들은 감사 과정에서 확인되었으나 정상 동작함:

1. **모바일 PWA `/mobile/bible/books` 연동** — 백엔드 `bible.py`에 정의됨, 폴백 로직 정상
2. **모바일 PWA `/mobile/media` 연동** — 백엔드 `media.py`에 정의됨, `mapMedia` 매핑 정상
3. **모바일 PWA 채팅 `/chat` 연동** — `target_lang` 전달, `AbortController` 타임아웃 처리 정상
4. **Admin 추천 질문 페이지** — `GET/PUT/POST /admin/suggestions` 모두 연동 정상
5. **Admin 미디어/성경 업로드** — 폼 필드 매핑 정상 (단, `order_index`는 BUG-11 참조)
6. **Admin 자료 Library/Publish 폴링** — 비동기 job_id 기반 폴링 로직 정상
7. **Admin 에러 로그 모니터링** — `/admin/errors`, `/admin/error-stats` 정상 연동
8. **Admin 영성훈련 콘텐츠 CRUD** — `/admin/content/links` 정상 동작
9. **모바일 Player (Web Audio + Media Session)** — 오프라인 다운로드, EQ, A-B 반복 정상 동작

---

## 🛠 수정 우선순위 권장

1. **1차 (Critical 4건)**: BUG-01, BUG-02, BUG-03, BUG-04 — 사용자 경직적 기능 손상
2. **2차 (High 5건)**: BUG-05, BUG-06, BUG-07, BUG-08, BUG-09 — UX 저하 및 데이터 무결성
3. **3차 (Medium 3건)**: BUG-10, BUG-11, BUG-12 — 마이너 개선

수정 후에는 각 버그에 대한 회귀 테스트 케이스 추가를 권장함.
