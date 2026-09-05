"""xuan9/ChineseBibleSearchJS 번체(繁體) 화합본 → 프로젝트 성경 포맷 변환기.

원본: bibleText.js (UMD 배열, '약어장:절 본문' 형식, 총 31,103절 — 66권 완전본)
출처: https://github.com/xuan9/ChineseBibleSearchJS

산출물:
  1) mobile/data/bible_trad/bible_meta.json + {idx}.json (1~66)
     — APK 오프라인 번들. 기존 간체(mobile/data/bible/)는 그대로 유지.
  2) data/bible/화합본번체/{책명}.txt 66권
     — 서버 bible_service fallback 용 (형식 A: '장:' 마커 + '절:본문').

사용:
  venv/Scripts/python scripts/import_bible_traditional.py [--src /tmp/bibleText.js]

책명은 번체 정본(和合本) 풀네임을 사용. 약어 순서가 표준 정경 순(구약 39 → 신약 27)이므로
testament 분류는 인덱스 기준.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 약어 → 번체 풀네임 (표준 정경 순서)
TRAD_BOOKS: list[tuple[str, str]] = [
    ("創", "創世記"), ("出", "出埃及記"), ("利", "利未記"), ("民", "民數記"), ("申", "申命記"),
    ("書", "約書亞記"), ("士", "士師記"), ("得", "路得記"), ("撒上", "撒母耳記上"), ("撒下", "撒母耳記下"),
    ("王上", "列王紀上"), ("王下", "列王紀下"), ("代上", "歷代志上"), ("代下", "歷代志下"),
    ("拉", "以斯拉記"), ("尼", "尼希米記"), ("斯", "以斯帖記"), ("伯", "約伯記"), ("詩", "詩篇"),
    ("箴", "箴言"), ("傳", "傳道書"), ("歌", "雅歌"), ("賽", "以賽亞書"), ("耶", "耶利米書"),
    ("哀", "耶利米哀歌"), ("結", "以西結書"), ("但", "但以理書"), ("何", "何西阿書"), ("珥", "約珥書"),
    ("摩", "阿摩司書"), ("俄", "俄巴底亞書"), ("拿", "約拿書"), ("彌", "彌迦書"), ("鴻", "那鴻書"),
    ("哈", "哈巴谷書"), ("番", "西番雅書"), ("該", "哈該書"), ("亞", "撒迦利亞書"), ("瑪", "瑪拉基書"),
    ("太", "馬太福音"), ("可", "馬可福音"), ("路", "路加福音"), ("約", "約翰福音"), ("徒", "使徒行傳"),
    ("羅", "羅馬書"), ("林前", "哥林多前書"), ("林後", "哥林多後書"), ("加", "加拉太書"), ("弗", "以弗所書"),
    ("腓", "腓立比書"), ("西", "歌羅西書"), ("帖前", "帖撒羅尼迦前書"), ("帖後", "帖撒羅尼迦後書"),
    ("提前", "提摩太前書"), ("提後", "提摩太後書"), ("多", "提多書"), ("門", "腓利門書"), ("來", "希伯來書"),
    ("雅", "雅各書"), ("彼前", "彼得前書"), ("彼後", "彼得後書"), ("約一", "約翰一書"), ("約二", "約翰二書"),
    ("約三", "約翰三書"), ("猶", "猶大書"), ("啟", "啟示錄"),
]
OLD_TESTAMENT_COUNT = 39
ABBR_TO_NAME = {a: n for a, n in TRAD_BOOKS}


def parse_bible_text(src: Path) -> dict[str, dict[int, list[tuple[int, str]]]]:
    """bibleText.js → {풀네임: {장: [(절, 본문), ...]}}"""
    text = src.read_text(encoding="utf-8")
    books: dict[str, dict[int, list[tuple[int, str]]]] = {n: {} for _, n in TRAD_BOOKS}

    pat = re.compile(r"'([^']+)'")
    total = 0
    skipped = 0
    for m in pat.finditer(text):
        s = m.group(1)
        mm = re.match(r"^([^\d]+?)(\d+):(\d+)\s+(.+)$", s)
        if not mm:
            continue
        abbr, ch, vs, body = mm.group(1), int(mm.group(2)), int(mm.group(3)), mm.group(4).strip()
        name = ABBR_TO_NAME.get(abbr)
        if name is None:
            skipped += 1
            continue
        books[name].setdefault(ch, []).append((vs, body))
        total += 1

    # 절 정렬 (원본 순서가 이미 정렬되어 있으나 안전하게)
    for name in books:
        for ch in books[name]:
            books[name][ch].sort(key=lambda x: x[0])
    print(f"[parse] 총 {total}절, 미매핑 {skipped}절")
    return books


def _chapter_count(book_chapters: dict[int, list]) -> int:
    return max(book_chapters.keys()) if book_chapters else 0


def write_mobile_bundle(books: dict, mobile_dir: Path) -> dict:
    """mobile/data/bible_trad/ — bible_meta.json + {idx}.json 분권."""
    mobile_dir.mkdir(parents=True, exist_ok=True)
    bible_books = []
    passages_count = 0
    for i, (abbr, name) in enumerate(TRAD_BOOKS, start=1):
        book_chapters = books.get(name, {})
        ch_count = _chapter_count(book_chapters)
        testament = "old" if i - 1 < OLD_TESTAMENT_COUNT else "new"
        bible_books.append({
            "id": name,
            "name": name,
            "short": abbr,
            "chapters": ch_count,
            "testament": testament,
        })
        # 분권 JSON: { book, chapters: {"1": [{v,t}...]} }
        chapters_obj = {}
        for ch in sorted(book_chapters.keys()):
            chapters_obj[str(ch)] = [{"v": v, "t": t} for v, t in book_chapters[ch]]
            passages_count += 1
        (mobile_dir / f"{i}.json").write_text(
            json.dumps({"book": name, "chapters": chapters_obj}, ensure_ascii=False),
            encoding="utf-8",
        )
    meta = {
        "version": "繁體中文和合本 (CUV Traditional)",
        "source": "xuan9/ChineseBibleSearchJS (bibleText.js, springbible.fhl.net)",
        "bible_books": bible_books,
    }
    (mobile_dir / "bible_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"[mobile] {mobile_dir} — {len(bible_books)}권 / {passages_count}장")
    return meta


def write_server_txt(books: dict, bible_dir: Path) -> None:
    """data/bible/화합본번체/{책명}.txt — 형식 A('장:' 마커 + '절:본문')."""
    out_dir = bible_dir / "화합본번체"
    out_dir.mkdir(parents=True, exist_ok=True)
    for _, name in TRAD_BOOKS:
        book_chapters = books.get(name, {})
        lines = []
        for ch in sorted(book_chapters.keys()):
            lines.append(f"{ch}:")
            for vs, body in book_chapters[ch]:
                lines.append(f"{vs}:{body}")
        (out_dir / f"{name}.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[server] {out_dir} — {len(TRAD_BOOKS)}권 txt 저장")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(ROOT / "tmp" / "bibleText.js"), help="bibleText.js 경로")
    args = ap.parse_args()

    src = Path(args.src)
    if not src.exists():
        # /tmp (WSL/시스템) 대체 경로
        alt = Path("/tmp") / "bibleText.js"
        if alt.exists():
            src = alt
    if not src.exists():
        print(f"❌ bibleText.js 없음: {args.src}")
        raise SystemExit(1)

    books = parse_bible_text(src)
    write_mobile_bundle(books, ROOT / "mobile" / "data" / "bible_trad")
    write_server_txt(books, ROOT / "data" / "bible")
    print("\n✅ 번체 화합본 변환 완료 (간체는 그대로 유지됨)")


if __name__ == "__main__":
    main()
