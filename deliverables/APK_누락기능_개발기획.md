# APK 누락 기능 진단 + 개발 기획

> 목적: 현재 모바일 APK(PWA 기반)의 보유 기능을 전수 파악하고, 동종 앱(성경·신앙·AI 채팅)이 표준으로 제공하지만 우리에게 없는 기능을 도출해 우선순위 개발 기획을 제시.
> 근거: 실제 코드를 읽어 확인(mobile/screens/index.js, services/index.js, backend/api/mobile.py 등). 일시 2026-08-14.

---

## 1. 현재 보유 기능 (확인된 것)

**5개 탭** (`components/index.js:25`): 圣经(Bible) · 诗歌(Hymns) · 今日(Today) · 话语(Word/Sermon) · 设置(Settings)

| 영역 | 보유 기능 |
|------|-----------|
| 성경 | 장/절 네비, 폰트 크기(볼륨키), 검색, 구절 참조(`/bible/refs`) |
| 찬송가 | 목록·즐겨찾기·가사·재생·EQ·재생목록·오프라인 다운로드 |
| 설교 | 카테고리 분류·즐겨찾기·공유·하이라이트·재생 |
| 오늘 | 일일 말씀 카드(`/verse/daily`)·AI 채팅·인기질문·광고배너 |
| 설정 | 계정·멤버십/구독·다크모드·언어(KO/ZH/EN)·로그인(구글/이메일) |
| 기타 | 웹푸시(미디어 갱신)·결제(PortOne)·QT 콘텐츠(`/content?category=devotion`) |

---

## 2. 유사 앱 대비 누락 기능 (벤치마크)

벤치마크 대상: YouVersion, 갓피플/포도나무(한국 교회앱), Pray.com/Echo(기도), Glorify/Abide(묵상), ChatGPT/Claude(AI 채팅).

| # | 누락 기능 | 벤치마크(어디서 쓰는지) | 현재 상태 | 우선순위 |
|---|-----------|------------------------|-----------|:---:|
| 1 | **채팅 대화 히스토리 관리** | ChatGPT(목록/삭제/검색/이어하기) | **백엔드 `/history`(search 지원) 이미 존재**, 프론트 미사용·chatMessages 메모리only(미영속) | P0 |
| 2 | **음성 입력** | ChatGPT(음성 질문) | 전무. Web Speech API로 프론트만으로 구현 가능 | P0 |
| 3 | **TTS 음성 답변** | ChatGPT(답변 읽어주기) | 전무. Web SpeechSynthesis로 프론트만으로 가능 | P0 |
| 4 | **기도 기능** | Pray.com(기도목록·응답체크·리마인더) | 전무(인사말에만 "기도" 언급) | P1 |
| 5 | **말씀 하이라이트/북마크/메모** | YouVersion(구절 형광펜·책갈피·노트) | 전무(검색어 강조용 `_highlight`만 존재) | P1 |
| 6 | **성경 읽기 계획(통독)** | YouVersion(1년통독/90일/테마) | 전무 | P1 |
| 7 | **구절 공유 이미지 카드** | YouVersion(스타일링된 말씀 카드) | 텍스트 `navigator.share`만 존재 | P1 |
| 8 | **연속 출석/스트릭 + 보상** | YouVersion(게이미피케이션) | 전무 | P2 |
| 9 | **말씀/기도 알림(리마인더)** | YouVersion/Pray.com(정기 푸시) | 웹푸시는 미디어 갱신용만, 정기 알림 없음 | P2 |
| 10 | **헌금/온라인헌금** | 한국 교회앱(온라인 헌금) | 전무(단 PortOne 결제 인프라 이미 구축) | P2 |
| 11 | **오디오 성경/TTS 성경** | YouVersion(음성 성경) | 전무 | P3 |
| 12 | **커뮤니티/소그룹** | 교회앱(기도제목·소그룹) | 전무 | P3 |
| 13 | **다중 번역** | YouVersion(개역/새번역/NIV 등) | 단일 번역 | P3 |

---

## 3. 개발 기획 (우선순위 + 구체 스펙)

### P0 — 즉시 가치 (프론트 위주, 백엔드 일부 준비됨)

**#1 채팅 히스토리 관리** (백엔드 준비 완료 — 최고 ROI)
- 백엔드 `/mobile/history`(limit·search)는 이미 구현됨. 프론트에서 미사용이 핵심 갭.
- 기획: 설정 탭 또는 채팅 화면 상단에 "대화 기록" 진입 → 목록(타이틀/시간) → 탭하여 이어하기 → 길게 눌러 삭제 → 검색창.
- `screens/index.js`의 `renderChat` + `renderMy`에 히스토리 패널 추가. `chatMessages`는 `localStorage`(gospel_chat)에 영속화.
- 삭제 API는 필요 시 `mobile.py`에 `DELETE /history/{id}` 추가(현재 GET만 존재).

**#2 음성 입력** (프론트만, ~0 의존성)
- `webkitSpeechRecognition`/`SpeechRecognition`(Web Speech API)으로 채팅 입력창에 마이크 버튼.
- 중국 Android WebView 호환 고려: 미지원 시 버튼 숨김(feature detect). `lang`은 현재 `targetLang` 매핑.

**#3 TTS 음성 답변** (프론트만, ~0 의존성)
- `speechSynthesis`(Web Speech API)로 AI 답변 메시지에 "듣기" 버튼. 재생/중단 토글.
- 한국어/중국어 음성은 OS TTS 엔진 의존(오프라인 패키지 필요 가능성 명시).

### P1 — 핵심 신앙 기능 (풀스택)

**#4 기도 기능**
- 백엔드: `prayer.py` 신설 — `POST/GET/DELETE /mobile/prayers`(제목·내용·응답여부·리마인더시각), Subscriber 연동.
- 프론트: "今日" 탭에 기도 카드 → 기도목록 CRUD, "응답받음 ✓" 토글, 반복 리마인더.
- 데이터: `prayers` 테이블(subscriber_id FK, title, body, answered, remind_at).

**#5 말씀 하이라이트/북마크/메모**
- 백엔드: `annotations.py` — `POST/GET/DELETE /mobile/annotations`(verse_ref, color, note).
- 프론트: 성경 본문 절을 길게 눌러 하이라이트 색 선택 + 메모. "设置"에 내 메모/하이라이트 모음.
- 데이터: `verse_annotations`(subscriber_id, book, chapter, verse, color, note).

**#6 성경 읽기 계획**
- 백엔드: `plans.py` — 정적 계획 템플릿(1년통독/90일/신약 30일) + 진행도(`plan_progress`).
- 프론트: "今日" 탭에 "오늘 읽을 분량" 카드 → 완료 체크 → 진행률 막대.
- 데이터: `reading_plans`(템플릿 JSON) + `plan_progress`(subscriber_id, plan_id, day, done).

**#7 구절 공유 이미지 카드**
- 프론트: `<canvas>`로 배경색/폰트 조합의 말씀 카드 생성 → `toDataURL` → 공유/저장. 백엔드 불필요.

### P2 — 참여/수익화

**#8 연속 출석/스트릭**: 백엔드 `streak`(last_date, count) 갱신, 프론트 "今日" 상단 스트릭 배지.
**#9 말씀/기도 알림**: 백엔드 스케줄러(APScheduler/Celery beat)로 정기 푸시, 프론트 알림 시간 설정.
**#10 헌금**: PortOne 결제 인프라 재사용 — `offering` 금액 선택 → 결제 → 영수증. (채널키 발급 선행 필요 — 기존 결제 503 이슈와 연동).

### P3 — 대규모(데이터/자산 의존)

**#11 오디오 성경**: TTS 엔진(오프라인) 또는 라이선스 오디오. **#12 커뮤니티**: 별도 실시간 인프라 필요. **#13 다중 번역**: 저작권 있는 성경 데이터 확보 필요.

---

## 4. 권고

**최우선 추천: #1(채팅 히스토리) + #2(음성 입력) + #3(TTS)** — 백엔드가 이미 준비됐거나 프론트만으로 구현 가능해 **비용 대비 가치가 가장 높습니다**. 다음으로 **#4 기도 + #5 하이라이트**가 신앙 앱 정체성(단순 AI챗봇과 차별화)을 강화합니다.

정직 고지: #10(헌금)은 기존에 발견된 `PORTONE_CHANNEL_KEY` 미설정(결제 503)이 선행 해결돼야 하며, #11/#12/#13은 외부 데이터/인프라·라이선스가 필요합니다.
