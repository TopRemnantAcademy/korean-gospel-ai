"""D-C24: 구원 핵심 자료 큐레이션 가이드 스크립트.

실행:
    python scripts/seed_gospel_core.py

동작:
1. 현재 published 자료 중 gospel_core_tag=False 인 항목 목록 출력
2. 운영자가 직접 Admin Library 페이지에서 gospel_core_tag=True 로 설정 안내
3. (선택) --auto 플래그 시 DeepSeek로 자동 분류 제안
"""
# =============================================================================
# 🔧 AI-AGENT-WORK
# Agent: Claude (Cowork)
# Timestamp: 2026-05-26 00:00
# Task: D-C24 — 구원 핵심 자료 큐레이션 스크립트
# Reason: ORDERS.md EPIC D-C24
# Status: COMPLETED
# =============================================================================
from __future__ import annotations
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")


def list_published_without_core_tag() -> list[dict]:
    from backend.app.db import get_session
    from backend.app.models.orm import DocumentVersion

    with get_session() as s:
        versions = s.query(DocumentVersion).filter(
            DocumentVersion.state == "published",
        ).all()
        return [
            {
                "version_id": v.version_id,
                "doc_id": v.doc_id,
                "title": v.title,
                "gospel_core_tag": v.gospel_core_tag,
                "salvation_focus_score": v.salvation_focus_score,
                "target_salvation_stage": v.target_salvation_stage,
            }
            for v in versions
        ]


async def auto_tag_with_llm(version_id: str, title: str, body_excerpt: str) -> dict:
    """DeepSeek로 구원 핵심 자료 여부 + target_salvation_stage 자동 제안."""
    try:
        from backend.app.services.llm.fallback import chat_with_fallback
        from backend.app.services.llm.base import Message

        prompt = (
            f"다음 기독교 자료를 분석하세요.\n\n"
            f"제목: {title}\n"
            f"본문 발췌:\n{body_excerpt[:500]}\n\n"
            "JSON으로만 응답:\n"
            "{\n"
            '  "gospel_core_tag": true/false,  // 구원의 핵심 자료 (요한복음 3:16, 로마서 길 등)\n'
            '  "salvation_focus_score": 0.0,   // 0.0~1.0 구원 집중도\n'
            '  "target_salvation_stage": [],   // ["seeker"|"uncertain"|"assured"|"mature"|"gospel_core"|"assurance"|"discipleship"]\n'
            '  "darakbang_tier": null           // null|"darakbang_general"|"darakbang_deep"|"darakbang_leader"\n'
            "}"
        )
        import json
        messages = [Message(role="user", content=prompt)]
        resp, _, _ = await chat_with_fallback(messages, temperature=0.1, max_tokens=200)
        raw = resp.text.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        return json.loads(raw)
    except Exception as e:
        print(f"  ⚠️  LLM 분류 실패: {e}")
        return {}


async def apply_tags(version_id: str, tags: dict) -> None:
    from backend.app.db import get_session
    from backend.app.models.orm import DocumentVersion

    with get_session() as s:
        v = s.query(DocumentVersion).filter(DocumentVersion.version_id == version_id).first()
        if not v:
            return
        if "gospel_core_tag" in tags:
            v.gospel_core_tag = tags["gospel_core_tag"]
        if "salvation_focus_score" in tags:
            v.salvation_focus_score = float(tags["salvation_focus_score"])
        if "target_salvation_stage" in tags:
            v.target_salvation_stage = tags["target_salvation_stage"]
        if "darakbang_tier" in tags:
            v.darakbang_tier = tags["darakbang_tier"]


def main():
    parser = argparse.ArgumentParser(description="D-C24: 구원 핵심 자료 큐레이션")
    parser.add_argument("--auto", action="store_true", help="DeepSeek 자동 분류 제안")
    parser.add_argument("--apply", action="store_true", help="--auto 제안을 실제로 DB에 반영")
    args = parser.parse_args()

    versions = list_published_without_core_tag()
    if not versions:
        print("[seed_gospel_core] published 자료 없음.")
        return

    print(f"\n[seed_gospel_core] published 자료 {len(versions)}개 발견\n")

    gospel_core = [v for v in versions if v["gospel_core_tag"]]
    not_tagged = [v for v in versions if not v["gospel_core_tag"]]

    print(f"  ✅ gospel_core_tag=True: {len(gospel_core)}개")
    print(f"  ⬜ gospel_core_tag=False: {len(not_tagged)}개\n")

    if not args.auto:
        print("─" * 60)
        print("📋 gospel_core_tag 미설정 자료:")
        for v in not_tagged[:20]:
            score = v.get("salvation_focus_score", 0.0)
            stages = v.get("target_salvation_stage") or []
            print(f"  [{v['version_id'][:8]}...] {v['title'][:50]}  score={score:.2f}  stages={stages}")
        if len(not_tagged) > 20:
            print(f"  ... 외 {len(not_tagged) - 20}개")
        print("\n👉 Admin Library 페이지에서 gospel_core_tag=True 로 설정하거나")
        print("   --auto --apply 플래그로 자동 분류할 수 있습니다.")
        return

    # --auto 모드: LLM 분류
    import asyncio

    async def run_auto():
        from backend.app.db import get_session
        from backend.app.models.orm import DocumentVersion, SourceArtifact

        print("🤖 DeepSeek 자동 분류 시작...\n")
        for v in not_tagged:
            with get_session() as s:
                ver = s.query(DocumentVersion).filter(
                    DocumentVersion.version_id == v["version_id"]
                ).first()
                if not ver:
                    continue
                # body_patch 또는 artifact 본문 발췌
                body_excerpt = (ver.body_patch or "")[:500]
                if not body_excerpt and ver.artifact_id:
                    art = s.query(SourceArtifact).filter(
                        SourceArtifact.artifact_id == ver.artifact_id
                    ).first()
                    if art:
                        body_excerpt = art.extracted_text[:500]

            print(f"  분석 중: {v['title'][:50]}")
            tags = await auto_tag_with_llm(v["version_id"], v["title"], body_excerpt)
            if tags:
                print(f"    → gospel_core={tags.get('gospel_core_tag')}  score={tags.get('salvation_focus_score', 0):.2f}  stages={tags.get('target_salvation_stage', [])}")
                if args.apply:
                    await apply_tags(v["version_id"], tags)
                    print("    ✅ DB 반영 완료")
            else:
                print("    ⚠️  분류 실패 (건너뜀)")

        print("\n완료.")

    asyncio.run(run_auto())


if __name__ == "__main__":
    main()
