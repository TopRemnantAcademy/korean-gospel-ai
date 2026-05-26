"""평가 질문셋 자동 생성 — 문서 본문에서 LLM이 QA 페어 합성."""
from __future__ import annotations

import json
import re
from pathlib import Path

from ..config import settings
from .llm.base import Message
from .llm.fallback import chat_with_fallback


def _load_doc_text(path: Path, max_chars: int) -> str:
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    if len(text) > max_chars:
        text = text[:max_chars] + "\n…(이하 생략)"
    return text


def _parse_json_array(raw: str) -> list[dict]:
    raw = raw.strip()
    m = re.search(r"\[[\s\S]*\]", raw)
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    out: list[dict] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        q = (item.get("query") or item.get("question") or "").strip()
        if not q:
            continue
        kw = item.get("expected_keywords") or item.get("keywords") or []
        if isinstance(kw, str):
            kw = [k.strip() for k in kw.split(",") if k.strip()]
        out.append({"query": q, "expected_keywords": list(kw)[:8], "source": item.get("source", "")})
    return out


async def generate_questions_from_documents(
    *,
    doc_dir: str | None = None,
    max_per_doc: int = 3,
    max_chars_per_doc: int = 4500,
    glob_pattern: str = "*",
) -> list[dict]:
    """data/documents 등에서 QA 페어 생성."""
    root = settings.root_dir / (doc_dir or settings.data_dir)
    if not root.exists():
        return []

    paths = sorted(root.glob(glob_pattern))
    paths = [p for p in paths if p.is_file() and p.suffix.lower() in (".txt", ".md")]
    if not paths:
        return []

    all_items: list[dict] = []
    for path in paths:
        body = _load_doc_text(path, max_chars_per_doc)
        prompt = f"""다음 한국어 복음/성경 교육 자료를 읽고, 검색 품질 평가용 질문 {max_per_doc}개를 만든다.

자료 제목: {path.name}

--- 자료 본문 ---
{body}
---

규칙:
- 질문은 실제 사용자가 물을 법한 자연스러운 한국어
- expected_keywords 는 답/검색 결과에 반드시 나와야 할 핵심 단어 2~4개 (배열)
- JSON 배열만 출력. 다른 설명 금지.

형식 예:
[
  {{"query": "...", "expected_keywords": ["단어1", "단어2"], "source": "{path.name}"}}
]"""

        resp, _, _ = await chat_with_fallback(
            [Message(role="user", content=prompt)],
            temperature=0.4,
            max_tokens=1200,
        )
        for item in _parse_json_array(resp.text):
            item["source"] = item.get("source") or path.name
            all_items.append(item)

    # query 중복 제거
    seen: set[str] = set()
    deduped: list[dict] = []
    for it in all_items:
        key = it["query"]
        if key in seen:
            continue
        seen.add(key)
        deduped.append(it)
    return deduped


def build_questions_offline(doc_dir: str | None = None) -> list[dict]:
    """LLM 없이 파일명·본문 키워드로 평가 질문 생성."""
    root = settings.root_dir / (doc_dir or settings.data_dir)
    templates = [
        ("01_요한복음", "거듭난다는 것은 무슨 뜻입니까?", ["거듭", "성령", "물"]),
        ("02_로마서", "죄와 구원에 대해 성경은 무엇이라 하나요?", ["죄", "구원", "믿"]),
        ("03_시편", "힘들 때 위로가 되는 말씀은?", ["여호와", "목자", "평안"]),
        ("04_복음", "하나님의 사랑과 복음의 핵심은?", ["사랑", "독생자", "믿"]),
    ]
    out: list[dict] = []
    for path in sorted(root.glob("*")):
        if not path.is_file() or path.suffix.lower() not in (".txt", ".md"):
            continue
        name = path.name
        for prefix, query, kw in templates:
            if prefix in name:
                out.append({"query": query, "expected_keywords": kw, "source": name})
                break
    return out


def save_questions(
    questions: list[dict],
    *,
    out_path: str | None = None,
    merge: bool = False,
) -> Path:
    """questions.json 저장. merge=True면 기존 query 유지하며 append."""
    p = settings.root_dir / (out_path or "data/eval/questions.json")
    p.parent.mkdir(parents=True, exist_ok=True)

    existing: list[dict] = []
    if merge and p.exists():
        try:
            existing = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            existing = []

    if merge:
        seen = {x.get("query") for x in existing}
        for q in questions:
            if q.get("query") not in seen:
                existing.append(q)
                seen.add(q.get("query"))
        questions = existing

    p.write_text(json.dumps(questions, ensure_ascii=False, indent=2), encoding="utf-8")
    return p
