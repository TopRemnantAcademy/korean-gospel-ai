"""설교 텍스트 파일 정제 + Qdrant 인덱싱 스크립트.

기존 data/documents 폴더의 txt 파일들을:
1. 통역/영어 내용 제거하고 한국어 설교 본문만 추출
2. 청킹 + 임베딩
3. Qdrant에 일괄 인덱싱

사용법:
  python -m scripts.index_sermons
  python -m scripts.index_sermons --reset
  python -m scripts.index_sermons --embedder bge_m3
"""
from __future__ import annotations

import argparse
import re
import sys
import uuid
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.app.config import settings
from backend.app.services.chunker import chunk_text
from backend.app.services.embedding.factory import get_embedder
from backend.app.services.vector_store import QdrantStore


_TEXT_SUFFIXES = {".txt", ".md"}


def extract_korean_content(text: str, filename: str) -> str:
    """텍스트에서 한국어 설교 본문만 추출.

    통역 스크립트 형식의 경우 Attendees 1 (한국어) 라인만 추출.
    일반 텍스트는 그대로 사용.
    """
    lines = text.split('\n')
    korean_lines = []
    current_is_korean = False
    found_attendees = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if current_is_korean and korean_lines and korean_lines[-1] != '':
                korean_lines.append('')
            continue

        if stripped.startswith('Attendees 1'):
            found_attendees = True
            current_is_korean = True
            content = stripped[len('Attendees 1'):].strip()
            if content:
                korean_lines.append(content)
            continue
        elif stripped.startswith('Attendees 2'):
            found_attendees = True
            current_is_korean = False
            continue

        if found_attendees:
            if current_is_korean:
                korean_lines.append(stripped)
        else:
            korean_lines.append(stripped)

    result = '\n'.join(korean_lines).strip()

    result = re.sub(r'\d{4}\.\d{2}\.\d{2}.*?(\n|$)', '\n', result)
    result = re.sub(r'^\s*rt\s*$', '', result, flags=re.MULTILINE)
    result = re.sub(r'\d+분\s*\d+초', '', result)
    result = re.sub(r'\n{3,}', '\n\n', result)

    if len(result) < len(text) * 0.3:
        return text.strip()

    return result.strip()


def extract_sermon_metadata(filename: str, text: str) -> dict:
    """설교 파일에서 메타데이터 추출."""
    meta = {
        "title": filename,
        "source_file": filename,
        "doc_type": "sermon",
        "sermon_series": "",
        "sermon_date": "",
    }

    date_match = re.search(r'(\d{2,4})년\s*(\d{1,2})월', filename)
    if date_match:
        year = date_match.group(1)
        if len(year) == 2:
            year = '20' + year
        meta["sermon_date"] = f"{year}-{date_match.group(2).zfill(2)}"

    if '제주' in filename or '제주집중훈련' in filename:
        meta["sermon_series"] = "제주집중훈련"
        meta["sermon_location"] = "제주"

    if '구원' in filename or '축복' in filename:
        meta["gospel_core_tag"] = "salvation_blessing"
        meta["target_salvation_stage"] = "S2"

    if '창세기' in text or '근본' in text:
        meta["gospel_core_tag"] = meta.get("gospel_core_tag", "") + ",genesis3"
        if not meta.get("target_salvation_stage"):
            meta["target_salvation_stage"] = "S1"

    addiction_keywords = ['중독', '알콜', '마약', '도박', '성중독', '음란', '죄책감', '수치심']
    addiction_count = sum(1 for kw in addiction_keywords if kw in text[:5000])
    if addiction_count >= 2:
        meta["addiction_related"] = True
        meta["addiction_keywords_count"] = addiction_count

    return meta


def _chunk_uuid(source: str, chunk_seq: int) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"sermon:{source}:{chunk_seq}"))


def index_single_file(
    path: Path,
    store: QdrantStore,
    embedder,
    *,
    reset_collection: bool = False,
) -> dict:
    """단일 설교 파일을 정제하고 인덱싱."""
    if reset_collection:
        store.delete_collection()

    raw_text = path.read_text(encoding='utf-8', errors='replace').strip()
    if len(raw_text) < 30:
        return {"file": path.name, "status": "skipped", "reason": "too_short"}

    korean_text = extract_korean_content(raw_text, path.name)
    if len(korean_text) < 100:
        return {"file": path.name, "status": "skipped", "reason": "korean_too_short"}

    chunks = chunk_text(korean_text)
    if not chunks:
        return {"file": path.name, "status": "skipped", "reason": "no_chunks"}

    meta_base = extract_sermon_metadata(path.name, korean_text)

    texts = [c.text for c in chunks]
    ids = [_chunk_uuid(path.name, c.chunk_id) for c in chunks]

    vectors = embedder.embed_documents(texts)

    metadatas = []
    for c in chunks:
        m = dict(meta_base)
        m["chunk_seq"] = c.chunk_id
        m["chunk_size"] = len(c.text)
        metadatas.append(m)

    store.upsert(
        ids=ids,
        texts=texts,
        dense_vecs=vectors.tolist(),
        metadatas=metadatas,
    )

    return {
        "file": path.name,
        "status": "ok",
        "raw_chars": len(raw_text),
        "korean_chars": len(korean_text),
        "chunks": len(chunks),
    }


def index_all_sermons(
    doc_dir: Optional[str] = None,
    embedder_name: Optional[str] = None,
    *,
    reset: bool = False,
) -> dict:
    """폴더 내 모든 설교 파일 인덱싱."""
    root = Path(doc_dir) if doc_dir else settings.root_dir / settings.data_dir
    if not root.exists():
        return {"ok": False, "reason": f"folder not found: {root}"}

    embedder_name = embedder_name or settings.embedder
    embedder = get_embedder(embedder_name)
    store = QdrantStore(embedder_name, dim=embedder.dim)

    paths = sorted(
        p for p in root.iterdir()
        if p.is_file() and p.suffix.lower() in _TEXT_SUFFIXES
    )
    if not paths:
        return {"ok": False, "reason": "no .txt/.md files"}

    results = []
    for i, path in enumerate(paths):
        try:
            r = index_single_file(
                path, store, embedder,
                reset_collection=reset and i == 0,
            )
            results.append(r)
            print(f"  [{i+1}/{len(paths)}] {r['status']:8s} {path.name}")
        except Exception as e:
            results.append({"file": path.name, "status": "error", "error": str(e)})
            print(f"  [{i+1}/{len(paths)}] ERROR    {path.name}: {e}")

    count = store.count()

    return {
        "ok": True,
        "root": str(root),
        "embedder": embedder_name,
        "collection": store.collection,
        "total_files": len(paths),
        "total_points": count,
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser(description="설교 파일 인덱싱")
    parser.add_argument("--dir", default=None, help="문서 디렉토리 경로")
    parser.add_argument("--embedder", default=None, help="임베더 이름")
    parser.add_argument("--reset", action="store_true", help="컬렉션 리셋 후 인덱싱")
    args = parser.parse_args()

    print(f"설교 파일 인덱싱 시작...")
    print(f"  디렉토리: {args.dir or '기본 data/documents'}")
    print(f"  임베더: {args.embedder or '기본 설정'}")
    print(f"  리셋: {args.reset}")
    print()

    result = index_all_sermons(
        doc_dir=args.dir,
        embedder_name=args.embedder,
        reset=args.reset,
    )

    print()
    if result["ok"]:
        print(f"✅ 완료!")
        print(f"   총 파일: {result['total_files']}")
        print(f"   총 벡터: {result['total_points']}")
        print(f"   컬렉션: {result['collection']}")
    else:
        print(f"❌ 실패: {result.get('reason', 'unknown')}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
