"""data/documents → Qdrant 일괄 인덱싱 (DB publish 없이 MVP 검색용)."""
from __future__ import annotations

import uuid
from pathlib import Path

from ..config import settings
from .chunker import chunk_text
from .embedding.factory import get_embedder
from .vector_store import QdrantStore


_TEXT_SUFFIXES = {".txt", ".md"}


def _chunk_uuid(source: str, chunk_seq: int) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"docfile:{source}:{chunk_seq}"))


def index_text_file(
    path: Path,
    *,
    embedder_name: str | None = None,
    reset_collection: bool = False,
) -> dict:
    """단일 텍스트/md 파일 인덱싱."""
    embedder_name = embedder_name or settings.embedder
    embedder = get_embedder(embedder_name)
    store = QdrantStore(embedder_name, dim=embedder.dim)
    if reset_collection:
        store.reset()

    text = path.read_text(encoding="utf-8", errors="replace").strip()
    if len(text) < 30:
        return {"file": path.name, "chunks": 0, "points": 0, "skipped": "too_short"}

    chunks = chunk_text(text)
    if not chunks:
        return {"file": path.name, "chunks": 0, "points": 0, "skipped": "no_chunks"}

    title = path.name
    ids = [_chunk_uuid(title, c.chunk_id) for c in chunks]
    texts = [c.text for c in chunks]
    vectors = embedder.embed_documents(texts)
    metadatas = [
        {
            "title": title,
            "source_file": title,
            "chunk_seq": c.chunk_id,
            "doc_type": "corpus",
        }
        for c in chunks
    ]
    store.upsert(ids=ids, texts=texts, dense_vectors=vectors.tolist(), metadatas=metadatas)
    return {"file": path.name, "chunks": len(chunks), "points": len(chunks)}


def index_documents_folder(
    *,
    doc_dir: str | None = None,
    embedders: list[str] | None = None,
    reset: bool = False,
) -> dict:
    """data/documents 내 txt/md 전체 인덱싱."""
    root = settings.root_dir / (doc_dir or settings.data_dir)
    if not root.exists():
        return {"ok": False, "reason": f"folder not found: {root}"}

    paths = sorted(
        p for p in root.iterdir()
        if p.is_file() and p.suffix.lower() in _TEXT_SUFFIXES
    )
    if not paths:
        return {"ok": False, "reason": "no .txt/.md files"}

    embedders = embedders or [settings.embedder]
    summary: dict = {"ok": True, "root": str(root), "embedders": {}}

    for emb in embedders:
        files_out = []
        for i, path in enumerate(paths):
            files_out.append(
                index_text_file(
                    path,
                    embedder_name=emb,
                    reset_collection=reset and i == 0,
                )
            )
        store = QdrantStore(emb, dim=get_embedder(emb).dim)
        count = store.client.get_collection(store.collection).points_count
        summary["embedders"][emb] = {
            "files": files_out,
            "points_in_collection": count,
        }
    return summary
