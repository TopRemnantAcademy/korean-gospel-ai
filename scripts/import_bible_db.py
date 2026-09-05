"""중국어 성경 DB(简体中文和合本) → 프로젝트 성경 포맷 변환기.

원본 DB 형식 (bible_简体中文和合本.db):
  BibleID(SN, KindSN, ChapterNumber, NewOrOld, PinYin, ShortName, FullName)  -- 66권
  Bible(ID, VolumeSN, ChapterSN, VerseSN, Lection, SoundBegin, SoundEnd)     -- 절 본문

변환 결과:
  1) data/bible/{FullName}.txt  -- bible_service 가 읽는 권별 본문 (형식 A: '장:' 마커 + '절:본문')
  2) mobile/data/bible.json      -- APK 오프라인 번들 (bible_books + passages)

사용:
  python scripts/import_bible_db.py
  python scripts/import_bible_db.py --source path/to.db --bible-dir data/bible --mobile-json mobile/data/bible.json

추후 다른 번역본(예: KRV, ESV) 추가 시 이 스크립트를 재사용.
권명 충돌을 피하려면 버전별 하위디렉터리 또는 id 접두사 전략이 필요(현재 APK는 단일 버전 가정).
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 한자 ideographic space 를 일반 space 로 치환 후 정리
_IDEO_SPACE = "\u3000"


def _clean(text: str) -> str:
    if text is None:
        return ""
    return text.replace(_IDEO_SPACE, " ").strip()


def import_bible(source_db: Path, bible_dir: Path, mobile_json: Path) -> dict:
    assert source_db.exists(), f"소스 DB 없음: {source_db}"
    bible_dir.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(source_db))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    books = cur.execute(
        "SELECT SN, ChapterNumber, NewOrOld, ShortName, FullName "
        "FROM BibleID ORDER BY SN"
    ).fetchall()

    stats = {"books": 0, "chapters": 0, "verses": 0}
    bible_books = []
    passages: dict[str, dict] = {}

    for b in books:
        sn = b["SN"]
        full = (b["FullName"] or "").strip()
        short = (b["ShortName"] or "").strip()
        if not full:
            print(f"  [skip] SN={sn} 책명 없음")
            continue

        rows = cur.execute(
            "SELECT ChapterSN, VerseSN, Lection FROM Bible "
            "WHERE VolumeSN=? ORDER BY ChapterSN, VerseSN",
            (sn,),
        ).fetchall()

        # 장별 절 묶기
        by_chapter: dict[int, list[tuple[int, str]]] = {}
        for r in rows:
            ch = int(r["ChapterSN"])
            vs = int(r["VerseSN"])
            txt = _clean(r["Lection"])
            by_chapter.setdefault(ch, []).append((vs, txt))

        # txt 파일 (형식 A: '장:' 마커 + '절:본문')
        lines: list[str] = []
        for ch in sorted(by_chapter.keys()):
            lines.append(f"{ch}:")
            for vs, txt in by_chapter[ch]:
                lines.append(f"{vs}:{txt}")
            stats["chapters"] += 1
            stats["verses"] += len(by_chapter[ch])

        (bible_dir / f"{full}.txt").write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )

        chapter_count = len(by_chapter)
        bible_books.append(
            {
                "id": full,
                "name": full,
                "short": short,
                "chapters": chapter_count,
                "testament": "old" if b["NewOrOld"] == 0 else "new",
            }
        )

        # 오프라인 번들 passages
        for ch in sorted(by_chapter.keys()):
            verses = [{"v": vs, "t": txt} for vs, txt in by_chapter[ch]]
            passages[f"{full}-{ch}"] = {
                "book": full,
                "chapter": ch,
                "verses": verses,
            }

        stats["books"] += 1

    conn.close()

    # 오프라인 번들 JSON 작성
    mobile_json.parent.mkdir(parents=True, exist_ok=True)
    bundle = {
        "version": "简体中文和合本 (CUV Simplified)",
        "source": source_db.name,
        "bible_books": bible_books,
        "passages": passages,
        "bookmarks": [],
    }
    mobile_json.write_text(
        json.dumps(bundle, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    print(
        f"[OK] {stats['books']}권 / {stats['chapters']}장 / {stats['verses']}절 변환 완료\n"
        f"     txt  → {bible_dir}\n"
        f"     json → {mobile_json} ({mobile_json.stat().st_size:,} bytes)"
    )
    return stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--source",
        default=str(ROOT / "data" / "bible_sources" / "bible_简体中文和合本.db"),
        help="원본 성경 DB 경로",
    )
    ap.add_argument("--bible-dir", default=str(ROOT / "data" / "bible"))
    ap.add_argument("--mobile-json", default=str(ROOT / "mobile" / "data" / "bible.json"))
    args = ap.parse_args()

    import_bible(
        Path(args.source), Path(args.bible_dir), Path(args.mobile_json)
    )


if __name__ == "__main__":
    main()
