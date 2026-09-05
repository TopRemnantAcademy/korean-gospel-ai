# 업그레이드 실행 스펙 v3-IMPL — 코딩 즉시 진행용 (file:line 단위)

> 기반: `docs/upgrade_plan_v3.md` (전략) + 코드로 재검증한 사실 반영
> 작성: 2026-07-16 / 목적: "바로 바이브 코딩해도 최소 오류"를 위한 유일한 실행 문서
> ⚠️ 모든 편집은 이 파일의 코드 스니펫을 그대로 따를 것. 추측 금지.

---

## ⚠️ 정정 이력 (2026-07-16 더블체크 — 코드로 재검증)

초안 작성 후 코드를 대조해 다음 9건을 정정했다. 이대로 안 하면 코딩 중 사고난다.

| # | 초안 오류 | 정정 |
|---|---|---|
| 1 | `rag_engine`가 `chat_pipeline:8,11`에 미사용 import로 존재 → 거기서 제거 | **아님.** `rag_engine`은 `chat_pipeline` 어디에도 import 안 됨(전체 백엔드에서 외부 참조 0건, 자기 자신만 self-reference). → `rag_engine.py` 파일만 삭제하면 됨(chat_pipeline 수정 불필요) |
| 2 | enhanced_rag 비활성 = `config.py:20 enabled=False` | **불충분.** `get_pipeline()`가 `settings.rag_bilingual_enabled` 값으로 `cfg.bilingual.enabled`를 강제 덮어씀(config.py:125 기본 True). → 실제 스위치는 **`.env: RAG_BILINGUAL_ENABLED=false`** |
| 3 | 재인덱스 = `python -m backend.app.services.publish_service --reingest-all` | **그런 CLI 없음.** 재인덱스는 반드시 `ingest_pipeline.build_index_chunks` 경로(여기서 `normalizer.normalize_text` 호출, ingest_pipeline:81)를 거쳐야 함. → 신규 `scripts/reindex_published.py` 사용. `scripts/index_sermons.py --reset`은 normalizer를 안 쓰므로 P1 재인덱스에 부적합 |
| 4 | `requirements.txt` 수정 (경로 `backend/requirements.txt`) | 실제 경로는 **루트 `requirements.txt`**. `kiwipiepy`는 아직 미설치 → 추가 + `pip install` 필요(설치 전까지 spacing fail-open) |
| 5 | P5 관측 스니펫이 `r.dense_score`/`r.sparse_score` 사용 | 실제 필드는 `raw_dense_score`/`raw_sparse_score`이고 `raw_sparse_score`는 **항상 None**(search_v4:406). 비교 시 TypeError. → 수정 스니펫 사용 |
| 6 | P0.5 offline: 무조건 `HF_HUB_OFFLINE=1` 추가 | KURE는 로컬 캐시에 실제 존재(2.1GB, 여러 blob). `main.py` lifespan이 이미 KURE를 기동 시 프리로드함(100-101행). → 기동 로그로 로드 확인 먼저, offline은 air-gap 필요 시에만(Windows 심링크 캐시면 offline 로드 실패 가능 주의) |
| 7 | enhanced_rag 비활성 = `.env: RAG_BILINGUAL_ENABLED=false` 만으로 충분 | **아님.** `get_pipeline()`(enhanced_rag/__init__.py:48-49)가 `if settings.rag_bilingual_enabled: cfg.bilingual.enabled=True` — **False면 분기 스킵돼 `RAGConfig()` 기본 True(config.py:20)가 그대로 남음**. env=false만으론 비활성화 안 됨 → `cfg.bilingual.enabled = settings.rag_bilingual_enabled`(1줄 무조건 대입)로 **코드 수정 필수** |
| 8 | 평가 매칭 = `source_title` vs gold `expected_doc`(파일명) | **키 불일치라 절대 매칭 안 됨.** `source_title`=문서 제목(search_v4:408), gold는 doc_id. → eval이 `x.metadata.get("doc_id")` 로 비교(+title 폴백)하도록 §5.2 수정 |
| 9 | kiwipiepy.space 안전 + 골드셋 존재 | `space()`는 실제 ASR/무공백 입력에선 정상 복원이나, **이미 공백 있는 텍스트에선 '독생자'→'독 생자' 미세 분해** 발생 → 정제 가드(공백비율 낮을 때만 호출) 권장. `data/eval_sets/ko_sermon_eval.jsonl`은 **존재하지 않음** → run_eval 즉시 FileNotFoundError, 20~30행 수동 라벨링 선행 필수 |

---

## 0. 검증된 실제 아키텍처

코드로 확인한 라이브 경로:

| 경로 | 실제 엔진 | 증거 |
|---|---|---|
| `api/chat_pipeline.py:252` | **search_v4** `AdvancedSearchEngine` | `get_search_engine(retriever).search(...)` |
| `api/retrieval.py:96-117` | **search_v4** | `get_retriever()` + `get_search_engine()` |
| `api/mobile.py:255-257` | **search_v4** | `get_retriever()` + `get_search_engine()` |
| `services/rag_engine.py` | **데드 코드** | 외부 import 0건(자기 자신만 self-reference). 라이브 미호출 |
| `services/enhanced_rag` | **중복·중국어 secondary** | `chat_pipeline:184` `bilingual.enabled` 게이트로 병합. 실제 게이트는 `settings.rag_bilingual_enabled`(config.py:125) |

**핵심 결론:**
- 실제 단일 엔진 = `search_v4`(이미 hybrid BM25+dense+RRF+cross-encoder rerank+MMR, search_v4.py:347-419). 이것만 KEEP.
- `rag_engine.py` = 데드 → **파일 삭제만**(chat_pipeline 등 수정 불필요).
- `enhanced_rag` = 중복 + 중국어 오염 → **`.env: RAG_BILINGUAL_ENABLED=false`** 로 즉시 비활성, 이후 모듈 삭제.
- 라이브 임베더 기본 = **`kure`**(config.py:44), 컬렉션 `gospel_kure`. bge_m3도 캐시됨. → 임베더 교체 금지(재인덱스 위험), offline 로딩만 강화.

> v3의 "enhanced_rag 승격"은 **폐기**. search_v4가 이미 더 좋고 라이브임.

---

## 1. 최종 KILL / KEEP / BUILD

**KEEP (단일 소스)**
- `services/search_v4.py` (`AdvancedSearchEngine`), `services/retriever.py` (`HybridRetriever`)
- `services/normalizer.py` (수정), `services/chunker.py` (수정 — rag_engine·enhanced_rag·ingest 전부가 이걸 공유함)
- `services/ingest_pipeline.py` (정규화→청킹 파이프라인, 재인덱스 경로)
- `services/quality_gate.py`, `services/llm/fallback.py`, `services/cleanup_pipeline.py`

**KILL**
- `services/rag_engine.py` — 외부 참조 없음 확인됨 → **파일 직접 삭제**(chat_pipeline 수정 불필요)
- `services/enhanced_rag/` — `RAG_BILINGUAL_ENABLED=false` 후 즉시 비활성, 안정화되면 삭제
- rule-based 어절빈도 사전 (Kiwi로 대체)

**BUILD (신규)**
- `services/spacing.py` (Kiwi 싱글턴, fail-open)
- `scripts/reindex_published.py` (발행 문서 전체 재인덱스 — normalizer+chunker 경유)
- `scripts/run_eval.py` + `data/eval_sets/ko_sermon_eval.jsonl` (경량 문서레벨 평가)
- 관측 로깅 (search_v4 내 rerank/source_type 카운터)

---

## 2. P0.5 — 임베더 신뢰성 (가장 먼저, 첫 런타임 장애 지점)

**사실 확인(코드 기반):**
- KURE 모델은 로컬 HF 캐시에 실제 존재: `C:/Users/piaoy/.cache/huggingface/hub/models--nlpai-lab--KURE-v1` (blob 다수). bge-m3 / bge-reranker-v2-m3 도 캐시됨.
- `backend/app/main.py` lifespan이 기동 시 KURE를 프리로드함(`:100-101` `[STARTUP] ✅ KURE 임베딩 모델 사전 로딩 완료`). 즉 임베더는 이미 "기동 시 로드 실패 시 명확히 드러남".

**조치**
1. **(필수) 기동 로그 확인**: 백엔드 기동 시 `[STARTUP] ✅ KURE 임베딩 모델 사전 로딩 완료` 가 뜨는지 확인. 안 �우면 임베더 로드 실패 → 아래 env 보완.
2. **(선택, air-gap 시에만) offline 강제**: `.env`에 추가
   ```env
   HF_HUB_OFFLINE=1
   TRANSFORMERS_OFFLINE=1
   ```
   ⚠️ 단, Windows HF 캐시는 심링크라 `Length`가 0으로 보일 수 있음(실제 파일은 정상). offline 모드에서 로드 실패하면 캐시가 깨진 것 → `python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('nlpai-lab/KURE-v1')"` 로 재다운로드 후 시도.
3. 헬스체크 추가(기존 프리로드와 중복되나 명시적 확인용). `main.py` lifespan 내, 라우터 등록 전:
   ```python
   try:
       from app.services.embedding.factory import get_embedder
       get_embedder(settings.embedder)  # kure 로드 시도
       log.info("[boot] embedder '%s' loaded OK", settings.embedder)
   except Exception as e:
       log.error("[boot] CRITICAL: embedder load failed: %s", e)
   ```

---

## 3. P1 — 상류 Kiwi 정제 (측정 게이트 없이 즉시, 이미 실측 검증)

### 3.1 신규 `backend/app/services/spacing.py` (전체 코드)
```python
"""ASR 띄어쓰기 복원 + 문장분리 (Kiwi 기반, 오프라인·fail-open).

- Kiwi 싱글턴: 프로세스당 1회 로드.
- kiwipiepy 미설치/로드실패 → fail-open: 원문 반환 + regex 폴백.
- normalizer 최선단 + chunker 문장분리에서 호출.
"""
from __future__ import annotations

import re
import logging

logger = logging.getLogger(__name__)

# fail-open regex 폴백: 종결어미 뒤에서만 분리, 바로 뒤 연결어미(가/고/면/는/도…)면 분리 안 함
_FALLBACK_SPLIT_RE = re.compile(
    r"(?<=[다까죠네라요이며름수겠군께십니까다요])(?=\s|[.!?。…?!]|$)"
    r"|(?<=[.!?。…?!])\s*"
    r"|\n{2,}"
)


def _regex_split(text: str) -> list[str]:
    return [p.strip() for p in _FALLBACK_SPLIT_RE.split(text) if p.strip()]


_KIWI = None
_KIWI_TRIED = False


def _get_kiwi():
    global _KIWI, _KIWI_TRIED
    if _KIWI_TRIED:
        return _KIWI
    _KIWI_TRIED = True
    try:
        from kiwipiepy import Kiwi
        _KIWI = Kiwi()
        logger.info("[spacing] Kiwi loaded (singleton)")
    except Exception as e:
        _KIWI = None
        logger.warning("[spacing] Kiwi unavailable, fail-open to regex: %s", e)
    return _KIWI


def restore_spacing(text: str, min_space_ratio: float = 0.04) -> str:
    """ASR 띄어쓰기 파괴 복원. 실패 시 원문 반환.

    guard: 이미 공백이 충분한(정제된) 텍스트는 원문 유지. kiwi.space 가
    '독생자'→'독 생자' 처럼 이미 공백 있는 텍스트에 미세 분해를 유발하므로,
    공백비율이 임계값 이상이면 호출하지 않는다(ASR 무공백 입력만 정제).
    """
    if not text:
        return ""
    if len(text) and (text.count(" ") + text.count("\n")) / len(text) >= min_space_ratio:
        return text
    kiwi = _get_kiwi()
    if kiwi is None:
        return text
    try:
        return kiwi.space(text)
    except Exception as e:
        logger.warning("[spacing] kiwi.space failed, return original: %s", e)
        return text


def split_sentences(text: str) -> list[str]:
    """문장 분리. Kiwi 우선, 부재/실패 시 regex 폴백."""
    if not text:
        return []
    kiwi = _get_kiwi()
    if kiwi is not None:
        try:
            return [s for s in kiwi.split_into_sents(text) if s.strip()]
        except Exception as e:
            logger.warning("[spacing] kiwi.split failed, regex fallback: %s", e)
    return _regex_split(text)
```

### 3.2 `backend/app/services/normalizer.py` 수정
상단 import 추가:
```python
from .spacing import restore_spacing
```
`normalize_text` 본문을 다음으로 교체 (성경정규화 **이전**에 Kiwi를 최선단에 둠. Kiwi가 성경표기에 공백을 넣어도 `_SCRIPTURE_KOR_RE`는 `\s*`를 허용하므로 정상 변환됨 — normalizer.py:62 패턴 확인):
```python
def normalize_text(text: str, *, remove_fillers: bool = True) -> str:
    if not text:
        return ""

    # 0) ASR 띄어쓰기 복원 (Kiwi, fail-open)
    text = restore_spacing(text)

    # 1) 한글 성경표기 → 숫자표기
    text = _SCRIPTURE_KOR_RE.sub(_replace_kor_scripture, text)

    # 2) 구어체 정리 (옵션)
    if remove_fillers:
        text = _FILLER_TRAIL_RE.sub("", text)
        text = _REPEAT_WORD_RE.sub(r"\1", text)

    # 3) 공백·줄바꿈
    text = _normalize_whitespace(text)
    return text
```

### 3.3 `backend/app/services/chunker.py` 수정
`split_korean_sentences` 본문을 Kiwi 경로로 교체 (이 함수는 rag_engine·enhanced_rag·ingest 전부가 공유 → 한 곳만 고치면 3경로 동시 수정):
```python
from .spacing import split_sentences as _kiwi_split_sentences


def split_korean_sentences(text: str) -> list[str]:
    """한국어 문장 분리. Kiwi 우선(fail-open), 폴백 regex."""
    return _kiwi_split_sentences(text)
```
기존 `_SENT_SPLIT_RE` / `_regex_split_sentences` / `_USE_KSS` 블록은 방치(무해). Kiwi가 있으면 미사용.

### 3.4 `requirements.txt`(루트) 수정 + 설치
```
kiwipiepy
```
위치를 `backend/requirements.txt`(존재 안 함)가 아니라 **루트 `requirements.txt`**(line 30~31 주변 "Korean text" 섹션)에 추가.
설치(현재 미설치 확인됨):
```bash
pip install kiwipiepy
# 또는: pip install -r requirements.txt
```
설치 전까지 `spacing`은 fail-open으로 동작(정제 품질 저하, 시스템 정지 없음).

### 3.5 기존 인덱스 재구축 (필수 — 이걸 빼면 새 문서만 고침)
P1 적용 후 이미 인제스트된 설교는 깨진 청크/미정제 본문 그대로 → **전체 재인덱스 필요**.
⚠️ 반드시 `ingest_pipeline.build_index_chunks` 경로(→ `normalizer.normalize_text` 적용, ingest_pipeline:81)를 거쳐야 Kiwi 정제가 반영됨.
- ❌ `scripts/index_sermons.py --reset` 은 `normalize_text`를 **안 씀**(자체 `extract_korean_content`만 사용, index_sermons.py:140) → P1 정제 미반영. 사용 금지.
- ✅ 신규 `scripts/reindex_published.py` 사용(발행 문서를 build_index_chunks로 재청킹+재임베딩, 기존 청크는 doc_id로 교체):
```bash
python scripts/reindex_published.py --limit 3   # 먼저 소량 테스트
python scripts/reindex_published.py             # 전체
```
→ 컬렉션 `gospel_kure` 청크가 교체됨(동일 임베더라 재인덱스만 해당).

---

## 4. P2 — 스택 단일화 (search_v4 단일 소스, rag_engine/enhanced_rag 비활성)

### 4.1 `services/rag_engine.py` 삭제
- 외부 참조 0건 확인됨(`grep -rn "rag_engine" backend` 결과 rag_engine.py 자기 자신만).
- **chat_pipeline 수정 불필요.** `rag_engine.py` 파일만 삭제.

### 4.2 enhanced_rag 비활성 — 코드 1줄 수정 필수 (`.env`만으론 안 먹힘!)
⚠️ 정밀검증(2026-07-16)으로 발견한 치명 버그. `enhanced_rag/__init__.py:47-50` 원리:
```python
cfg = RAGConfig()                    # bilingual.enabled 기본 True (config.py:20)
if settings.rag_bilingual_enabled:   # 기본 True (config.py:125)
    cfg.bilingual.enabled = True     # False여도 분기 스킵 → 기본 True 그대로!
```
`settings.rag_bilingual_enabled` 기본값은 **True**(config.py:125). 따라서 `.env`를 `false`로 바꿔도
`if False:`라 분기 스킵 → `cfg.bilingual.enabled`는 `RAGConfig()` 기본 **True**가 유지됨.
→ **env=false만으로는 비활성화되지 않음.** 중국어 primary 이중저장이 계속 살아있음.

**반드시 `get_pipeline()`를 다음 1줄로 수정** (enhanced_rag/__init__.py:48-49):
```python
# ─ 기존 ─
# if settings.rag_bilingual_enabled:
#     cfg.bilingual.enabled = True
# ─ 수정 ─
cfg.bilingual.enabled = settings.rag_bilingual_enabled   # env 값을 그대로 반영(무조건 대입)
```
이렇게 하면 `.env: RAG_BILINGUAL_ENABLED=false` 가 즉시 적용된다.

효과(수정 후):
- `chat_pipeline._search_enhanced`(line 184) `if not pipeline.config.bilingual.enabled: return []` → 중국어 오염 + 이중인덱스 병합 **자동 중단**.
- `pipeline.py:50 if cfg.bilingual.enabled:` 게이트로 `publish_service` 이중 저장도 중단.

### 4.3 안정화 후 삭제(별도 PR)
- `chat_pipeline.py` `_search_enhanced` / `_merge_enhanced` + 호출부(line 173-283) 제거
- `publish_service.py` `_ingest_to_enhanced_rag` + 호출부(48-77, 259-263, 466-470) 제거
- `backend/app/api/enhanced_rag.py` + `main.py` 라우터 등록 제거
- `services/enhanced_rag/` 패키지 삭제

---

## 5. P0 — 경량 평가 (P1 직후, 문서레벨, 저비용)

### 5.1 골드셋 `data/eval_sets/ko_sermon_eval.jsonl` (20~30행) — ⚠️ 파일 미존재, 수동 생성 선행
> **시작 전 블로커**: 이 파일은 **존재하지 않음**. `scripts/run_eval.py` 실행 시 `FileNotFoundError`.
> 반드시 아래 형식으로 20~30행을 **수동 라벨링**해 먼저 생성해야 함.
```jsonl
{"query": "은혜에 대해 말씀한 부분", "expected_doc": "20260531_금토일의기준"}
{"query": "창세기 1장 1절 어떻게 해석했나", "expected_doc": "..."}
```
- `expected_doc` = 문서 **doc_id**(우선) 또는 문서 **제목**(§5.2가 둘 다 매칭). 청킹 변화에 안 깨짐.
- 6유형(주제/구절/적용/예화/신학/화자) 골고루.
- 청킹 의존 `expected_chunk_ids` **절대 쓰지 말 것**.

### 5.2 `scripts/run_eval.py` (전체 코드)
```python
"""라이브 경로(search_v4) 기준 경량 평가 — 문서/섹션 레벨.
gold: data/eval_sets/ko_sermon_eval.jsonl  ({"query","expected_doc"})
측정: top_k=10 에 expected_doc 이 포함되는지 → Recall@10, hit-rate.
"""
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.config import settings
from backend.app.services.retriever import get_retriever
from backend.app.services.search_v4 import get_search_engine

GOLD = ROOT / "data" / "eval_sets" / "ko_sermon_eval.jsonl"


async def main():
    retriever = get_retriever(settings.embedder)
    engine = get_search_engine(retriever)
    rows = [json.loads(l) for l in GOLD.read_text(encoding="utf-8").splitlines() if l.strip()]
    hits = 0
    for r in rows:
        res = await engine.search(
            query=r["query"], top_k=10,
            enable_mmr=True, enable_compression=False, enable_explain=False,
        )
        hit = False
        for x in res:
            did = x.metadata.get("doc_id") or ""
            title = x.source_title or ""
            # gold `expected_doc` = doc_id(우선) 또는 문서 제목
            if r["expected_doc"] in (did, title):
                hit = True
                break
        if hit:
            hits += 1
    print(f"Queries={len(rows)} Hits={hits} Recall@10={hits/len(rows):.3f}")


if __name__ == "__main__":
    asyncio.run(main())
```
- `get_retriever`(retriever.py:80), `get_search_engine`(search_v4.py:426), `search`는 async·`list[EnrichedSearchResult]` 반환, `.source_title` 필드 존재(search_v4.py:64) → 검증 완료.
- **베이스라인**: P1 이전(현재 깨진 상태)으로 한 번 돌려 수치 기록.
- **After**: P1+재인덱스 후 재측정 → 수치 상승 확인. 상승 안 뜨면 P1 되돌림.

---

## 6. P3/P4 — 베이스라인 이후 고도화 (지표 위에서)

### P3 sentence-window
- `retriever.py`(HybridRetriever)에 문장단위 노드 색인 + `window_text` 추가. 검색 시 문장 후보→윈도우 교체→동일 parent 청크 병합. P0 짧은 질의 부분집합으로 검증.

### P4 구조파싱 + 성경필터
- `restructurer.py`(존재 확인됨, backend/app/services/restructurer.py)에 `section_type`(intro/main_text/illustration/application/prayer/reading/qna) 분류(규칙+LLM).
- `extract_metadata` 확장 → `bible_refs` 블록 메타.
- `contextualizer` 프리픽스 2~4문장 강화(section_type 활용).
- 성경표기 `창 1:1`→`창세기 1:1` 표준화 후 metadata 필터 연결.

---

## 7. P5 — 관측성 (P1 직후로 앞당김)

⚠️ 초안 스니펫(`r.dense_score`/`r.sparse_score`)은 **오류**: 실제 필드는 `raw_dense_score`/`raw_sparse_score`(search_v4.py:61-62)이고 `raw_sparse_score`는 **항상 None**(search_v4.py:406). dense/sparse 우위는 EnrichedSearchResult에서 측정 불가.

`search_v4.py` `AdvancedSearchEngine.search` 내, `enriched` 확정 후:
```python
# search_v4.py search() 내, return enriched 직전
_src = {}
for r in enriched:
    _src[r.source_type] = _src.get(r.source_type, 0) + 1
self._stats = getattr(self, "_stats", {})
self._stats["last_source_hist"] = _src
self._stats["last_mean_final"] = (
    sum(r.final_score for r in enriched) / len(enriched) if enriched else 0.0
)
```
+ rerank 승패, 자주 실패하는 Bible ref 표기 로깅 → P0 골드셋 자동 보강(active learning).

---

## 8. 실행 순서 + 검증 (최소 오류 루틴)

```
[0] P0.5  기동 → "[STARTUP] ✅ KURE 임베딩 모델 사전 로딩 완료" 로그 확인
             (air-gap 필요 시에만 .env 에 HF_HUB_OFFLINE=1 추가, 단 Windows 캐시 심링크 주의)
[1] P0    (먼저 §5.1 골드셋 20~30행 수동 생성) → scripts/run_eval.py 로 현재 베이스라인 수치 기록 (깨진 상태)
[2] P1    spacing.py 신설 → normalizer/chunker 교체 → requirements.txt(루트) kiwipiepy 추가 + pip install
        → scripts/reindex_published.py --limit 3 (소량) → 전체 재인덱스
        → run_eval 재측정(수치 상승 확인)
[3] P2    enhanced_rag/__init__.py:48-49 를 `cfg.bilingual.enabled = settings.rag_bilingual_enabled` 로 수정 → .env: RAG_BILINGUAL_ENABLED=false → rag_engine.py 파일 삭제
        → 기동 후 채팅/검색 정상 응답 확인
[4] P5    search_v4 관측 로깅 추가
[5] P3/P4 베이스라인 대비 지표 개선 확인 후 적용
[6] 정리  enhanced_rag 모듈 삭제 (별도 PR)
```

**매 단계 검증 명령**
```bash
# 임베더/기동
uvicorn backend.app.main:app --port 8000   # [0] 로그에 KURE 프리로드 확인
# 단위 스모크
python -c "from backend.app.services.spacing import restore_spacing, split_sentences; print(restore_spacing('했습니 다 우리 가 함께')); print(split_sentences('말씀하시니라 우리는 기도합니다'))"
# 평가
python scripts/run_eval.py
# API 스모크
curl -X POST localhost:8000/retrieval -H "Authorization: Bearer $DIFY_API_KEY" -d '{"query":"은혜","knowledge_id":"kure","retrieval_setting":{"top_k":5}}'
# 재인덱스
python scripts/reindex_published.py --limit 3
```

---

## 9. 리스크 / 롤백

| 리스크 | 대응 |
|---|---|
| Kiwi 미설치(프로덕션) | `spacing` fail-open → 원문 통과 + 경고 로그. 정제만 저하, 시스템 정지 안 함. `pip install kiwipiepy`로 해결 |
| Kiwi가 성경표기 분해 | `_SCRIPTURE_KOR_RE`가 `\s*` 허용 → 정상 변환. 이상 시 순서 뒤집기(성경→Kiwi) |
| bilingual=False 이후 enhanced_rag 죽음 | 이미 graceful(`return []` / `if cfg.bilingual.enabled` 게이트). 영향 없음 |
| 재인덱스 누락 | [2] 단계 필수. 안 하면 새 문서만 고침(기존은 깨진 채). `index_sermons.py`는 normalizer 미적용이므로 금지 |
| kure 로드 실패 | [0] 프리로드 로그가 기동 시 명확히 실패 → env(`HF_HUB_OFFLINE=1`) 보완 또는 캐시 재다운로드 |
| enhanced_rag 비활성 안 먹힘 | `.env`만으론 안 먹힘(get_pipeline가 False 분기 무시) → 반드시 `enhanced_rag/__init__.py:48-49`를 `cfg.bilingual.enabled = settings.rag_bilingual_enabled` 로 수정 후 `.env: RAG_BILINGUAL_ENABLED=false` |
| rag_engine 삭제 후 누락 참조 | 삭제 전 `grep -rn "rag_engine" backend` 로 자기 자신 외 0건 재확인 (이미 확인됨) |
| P5 관측 스니펫 TypeError | `raw_sparse_score`는 None → dense/sparse 우위 비교 금지. §7 수정 스니펫 사용 |
