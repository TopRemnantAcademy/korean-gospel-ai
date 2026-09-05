"""성경 텍스트 다운로드 스크립트.

개역개정 (Korean Revised New Korean Version) 66권 + 화합본 (Chinese Union Version) 66권.

공개 API 출처:
  - 개역개정(KorRV): scrollmapper/bible_databases (GitHub raw, 번역별 단일 JSON)
  - 화합본(ChiUn, 和合本): scrollmapper/bible_databases (GitHub raw)
  - 참고: getbible.net은 Gatekeeper로 자동화 요청을 차단하여 현재 사용 불가
    (download_kr_getbible / download_zh_getbible 에 보관)

사용:
  python scripts/download_bible.py                    # 전체 (개역개정 + 화합본)
  python scripts/download_bible.py --kr               # 개역개정만
  python scripts/download_bible.py --zh               # 화합본만
  python scripts/download_bible.py --kr --test        # 테스트 (요한복음 1장만)

저장 위치:
  data/bible/개역개정/{책명}.txt   — 장별 "장번호:" 마커 + "절:본문" 형식
  data/bible/화합본/{책명}.txt     — 동일 포맷

bible_service.py가 자동으로 읽음 (BIBLE_DIR 하위).

주의: 성경 텍스트는 각 번역의 라이선스를 준수해야 합니다.
  - 개역개정: 대한성서공회 저작권 (비상업적 용도 허용, 출처 표기 필요)
  - 화합본 (和合本): 1919년 공역, 공개 도메인
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

BIBLE_DIR = ROOT / "data" / "bible"
KR_DIR = BIBLE_DIR / "개역개정"
ZH_DIR = BIBLE_DIR / "화합본"

# ── 성경 66권 책 목록 (개역개정 한국어 / 화합본 중국어) ─────────────────────

KR_BOOKS = [
    ("창세기", 50), ("출애굽기", 40), ("레위기", 27), ("민수기", 36), ("신명기", 34),
    ("여호수아", 24), ("사사기", 21), ("룻기", 4), ("사무엘상", 31), ("사무엘하", 24),
    ("열왕기상", 22), ("열왕기하", 25), ("역대상", 29), ("역대하", 36),
    ("에스라", 10), ("느헤미야", 13), ("에스더", 10), ("욥기", 42), ("시편", 150),
    ("잠언", 31), ("전도서", 12), ("아가", 8), ("이사야", 66), ("예레미야", 52),
    ("예레미야애가", 5), ("에스겔", 48), ("다니엘", 12), ("호세아", 14), ("요엘", 3),
    ("아모스", 9), ("오바댜", 1), ("요나", 4), ("미가", 7), ("나훔", 3),
    ("하박국", 3), ("스바냐", 3), ("학개", 2), ("스가랴", 14), ("말라기", 4),
    ("마태복음", 28), ("마가복음", 16), ("누가복음", 24), ("요한복음", 21),
    ("사도행전", 28), ("로마서", 16), ("고린도전서", 16), ("고린도후서", 13),
    ("갈라디아서", 6), ("에베소서", 6), ("빌립보서", 4), ("골로새서", 4),
    ("데살로니가전서", 5), ("데살로니가후서", 3), ("디모데전서", 6), ("디모데후서", 4),
    ("디도서", 3), ("빌레몬서", 1), ("히브리서", 13), ("야고보서", 5),
    ("베드로전서", 5), ("베드로후서", 3), ("요한일서", 5), ("요한이서", 1), ("요한삼서", 1),
    ("유다서", 1), ("요한계시록", 22),
]

# 화합본 (和合本) — 중국어 약자 (bible-api.com에서 사용)
ZH_BOOKS = [
    ("Gen", "创世记", 50), ("Ex", "出埃及记", 40), ("Lev", "利未记", 27),
    ("Num", "民数记", 36), ("Deut", "申命记", 34), ("Josh", "约书亚记", 24),
    ("Judg", "士师记", 21), ("Ruth", "路得记", 4), ("1Sam", "撒母耳记上", 31),
    ("2Sam", "撒母耳记下", 24), ("1Kgs", "列王纪上", 22), ("2Kgs", "列王纪下", 25),
    ("1Chr", "历代志上", 29), ("2Chr", "历代志下", 36), ("Ezra", "以斯拉记", 10),
    ("Neh", "尼希米记", 13), ("Esth", "以斯帖记", 10), ("Job", "约伯记", 42),
    ("Ps", "诗篇", 150), ("Prov", "箴言", 31), ("Eccl", "传道书", 12),
    ("Song", "雅歌", 8), ("Isa", "以赛亚书", 66), ("Jer", "耶利米书", 52),
    ("Lam", "耶利米哀歌", 5), ("Ezek", "以西结书", 48), ("Dan", "但以理书", 12),
    ("Hos", "何西阿书", 14), ("Joel", "约珥书", 3), ("Amos", "阿摩司书", 9),
    ("Obad", "俄巴底亚书", 1), ("Jonah", "约拿书", 4), ("Mic", "弥迦书", 7),
    ("Nah", "那鸿书", 3), ("Hab", "哈巴谷书", 3), ("Zeph", "西番雅书", 3),
    ("Hag", "哈该书", 2), ("Zech", "撒迦利亚书", 14), ("Mal", "玛拉基书", 4),
    ("Matt", "马太福音", 28), ("Mark", "马可福音", 16), ("Luke", "路加福音", 24),
    ("John", "约翰福音", 21), ("Acts", "使徒行传", 28), ("Rom", "罗马书", 16),
    ("1Cor", "哥林多前书", 16), ("2Cor", "哥林多后书", 13), ("Gal", "加拉太书", 6),
    ("Eph", "以弗所书", 6), ("Phil", "腓立比书", 4), ("Col", "歌罗西书", 4),
    ("1Thess", "帖撒罗尼迦前书", 5), ("2Thess", "帖撒罗尼迦后书", 3),
    ("1Tim", "提摩太前书", 6), ("2Tim", "提摩太后书", 4), ("Titus", "提多书", 3),
    ("Phlm", "腓利门书", 1), ("Heb", "希伯来书", 13), ("Jas", "雅各书", 5),
    ("1Pet", "彼得前书", 5), ("2Pet", "彼得后书", 3), ("1John", "约翰一书", 5),
    ("2John", "约翰二书", 1), ("3John", "约翰三书", 1), ("Jude", "犹大书", 1),
    ("Rev", "启示录", 22),
]


def _save_book(filepath: Path, book_name: str, chapters: dict[int, list[tuple[int, str]]]):
    """bible_service 호환 포맷으로 저장.

    포맷:
      장번호:
      절:본문
      절:본문
      ...
      다음장번호:
    """
    filepath.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for chap_num in sorted(chapters.keys()):
        lines.append(f"{chap_num}:")
        for verse_num, verse_text in chapters[chap_num]:
            lines.append(f"{verse_num}:{verse_text}")
    filepath.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"  ✅ {book_name}: {len(chapters)}장 저장 → {filepath.name}")


def _fetch_json(url: str, timeout: int = 60) -> dict:
    """단일 JSON 파일 다운로드 (scrollmapper 형태: books[] 구조)."""
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "GospelAI/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _extract_book(book: dict, chapter_limit: int | None = None) -> dict[int, list[tuple[int, str]]]:
    """scrollmapper book(dict) → {chapter: [(verse, text), ...]}."""
    chapters: dict[int, list[tuple[int, str]]] = {}
    for c in book.get("chapters", []):
        ch = c.get("chapter")
        if chapter_limit is not None and ch != chapter_limit:
            if chapter_limit is not None and ch > chapter_limit:
                continue
            if chapter_limit is not None and ch < chapter_limit:
                continue
        verses = [
            (v.get("verse"), str(v.get("text", "")).strip())
            for v in c.get("verses", [])
        ]
        verses = [(n, t) for n, t in verses if n and t]
        if verses:
            chapters[ch] = verses
    return chapters


def download_kr(test_only=False):
    """개역개정(KorRV) 다운로드.

    출처: scrollmapper/bible_databases (GitHub raw) — getbible.net이 Gatekeeper로
    자동화 요청을 차단하여 사용 불가. scrollmapper는 번역별 단일 JSON(전 66권)을
    제공하므로 요청 수를 대폭 줄일 수 있음(전체 1회 호출).
    책 순서는 표준 정경 순(창세기→요한계시록)이므로 KR_BOOKS 인덱스와 1:1 매핑.
    """
    KR_DIR.mkdir(parents=True, exist_ok=True)

    url = "https://raw.githubusercontent.com/scrollmapper/bible_databases/master/formats/json/KorRV.json"
    print(f"  ⬇️  KorRV.json 다운로드 중...")
    try:
        data = _fetch_json(url)
    except Exception as exc:
        print(f"  ⚠️ KorRV 다운로드 실패: {exc}")
        return 0, 1

    books = data.get("books", [])
    if not books or books[0].get("name", "").lower() not in ("genesis", "창세기"):
        print("  ⚠️ 예상치 못한 책 순서 — 인덱스 매핑을 건너뜁니다.")
        return 0, 1

    # 테스트 모드: 요한복음(인덱스 42) 1장만
    if test_only:
        idx = 42  # John = 요한복음
        if idx < len(books):
            b = books[idx]
            chapters = _extract_book(b, chapter_limit=1)
            _save_book(KR_DIR / "요한복음.txt", "요한복음", chapters)
            print(f"\n📊 개역개정(테스트): 1책 성공")
            return 1, 0
        print("  ❌ 요한복음 없음")
        return 0, 1

    success = 0
    failed = 0
    for i, b in enumerate(books):
        if i >= len(KR_BOOKS):
            break
        kr_name = KR_BOOKS[i][0]
        chapters = _extract_book(b)
        if chapters:
            _save_book(KR_DIR / f"{kr_name}.txt", kr_name, chapters)
            success += 1
        else:
            print(f"  ❌ {kr_name}: 데이터 없음")
            failed += 1
        time.sleep(0.02)
    print(f"\n📊 개역개정: {success}책 성공, {failed} 실패")
    return success, failed


def download_zh(test_only=False):
    """화합본(ChiUn, 和合本) 다운로드.

    출처: scrollmapper/bible_databases (GitHub raw). 책 순서 표준 정경 순이므로
    ZH_BOOKS 인덱스와 1:1 매핑.
    """
    ZH_DIR.mkdir(parents=True, exist_ok=True)

    url = "https://raw.githubusercontent.com/scrollmapper/bible_databases/master/formats/json/ChiUn.json"
    print(f"  ⬇️  ChiUn.json 다운로드 중...")
    try:
        data = _fetch_json(url)
    except Exception as exc:
        print(f"  ⚠️ ChiUn 다운로드 실패: {exc}")
        return 0, 1

    books = data.get("books", [])
    if not books or books[0].get("name", "").lower() not in ("genesis", "创世记", "창세기"):
        print("  ⚠️ 예상치 못한 책 순서 — 인덱스 매핑을 건너뜁니다.")
        return 0, 1

    # 테스트 모드: 约翰福音(인덱스 42) 1장만
    if test_only:
        idx = 42  # John = 约翰福音
        if idx < len(books):
            b = books[idx]
            chapters = _extract_book(b, chapter_limit=1)
            _save_book(ZH_DIR / "约翰福音.txt", "约翰福音", chapters)
            print(f"\n📊 化합본(테스트): 1卷成功")
            return 1, 0
        print("  ❌ 约翰福音 不存在")
        return 0, 1

    success = 0
    failed = 0
    for i, b in enumerate(books):
        if i >= len(ZH_BOOKS):
            break
        zh_name = ZH_BOOKS[i][1]
        chapters = _extract_book(b)
        if chapters:
            _save_book(ZH_DIR / f"{zh_name}.txt", zh_name, chapters)
            success += 1
        else:
            print(f"  ❌ {zh_name}: 数据不存在")
            failed += 1
        time.sleep(0.02)
    print(f"\n📊 化합본: {success}卷成功, {failed}失败")
    return success, failed


# ── (보관) getbible.net 원본 방식 — 현재 Gatekeeper 차단으로 미사용 ──
def download_kr_getbible(test_only=False):
    """개역개정 다운로드 (getbible v2 — 현재 차단됨, 참고용)."""
    import urllib.request
    import urllib.error

    KR_DIR.mkdir(parents=True, exist_ok=True)
    book_ids = list(range(1, 67))
    books_to_download = KR_BOOKS if not test_only else [("요한복음", 1)]
    test_chapters = 1 if test_only else None
    success = 0
    failed = 0
    for idx, (book_name, total_chapters) in enumerate(books_to_download):
        book_id = book_ids[idx] if idx < len(book_ids) else idx + 1
        chapters = {}
        max_ch = test_chapters or total_chapters
        for chapter in range(1, max_ch + 1):
            url = f"https://getbible.net/v2/krv/{book_id}/{chapter}.json"
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "GospelAI/1.0"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                verses = [(v.get("verse"), str(v.get("text", "")).strip()) for v in data.get("verses", [])]
                verses = [(n, t) for n, t in verses if n and t]
                if verses:
                    chapters[chapter] = verses
                time.sleep(0.15)
            except Exception as exc:
                print(f"  ⚠️ {book_name} {chapter}장 실패: {exc}")
                failed += 1
                if chapter == 1:
                    break
        if chapters:
            _save_book(KR_DIR / f"{book_name}.txt", book_name, chapters)
            success += 1
        else:
            print(f"  ❌ {book_name}: 데이터 없음")
            failed += 1
    return success, failed


def download_zh_getbible(test_only=False):
    """화합본 다운로드 (getbible v2 — 현재 차단됨, 참고용)."""
    import urllib.request
    import urllib.error

    ZH_DIR.mkdir(parents=True, exist_ok=True)
    book_ids = list(range(1, 67))
    books_to_download = ZH_BOOKS if not test_only else [("John", "约翰福音", 1)]
    success = 0
    failed = 0
    for idx, (api_id, book_name_zh, total_chapters) in enumerate(books_to_download):
        book_id = book_ids[idx] if idx < len(book_ids) else idx + 1
        chapters = {}
        max_ch = 1 if test_only else total_chapters
        for chapter in range(1, max_ch + 1):
            url = f"https://getbible.net/v2/cuv/{book_id}/{chapter}.json"
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "GospelAI/1.0"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                verses = [(v.get("verse"), str(v.get("text", "")).strip()) for v in data.get("verses", [])]
                verses = [(n, t) for n, t in verses if n and t]
                if verses:
                    chapters[chapter] = verses
                time.sleep(0.15)
            except Exception as exc:
                print(f"  ⚠️ {book_name_zh} {chapter}章 失败: {exc}")
                failed += 1
                if chapter == 1:
                    break
        if chapters:
            _save_book(ZH_DIR / f"{book_name_zh}.txt", book_name_zh, chapters)
            success += 1
        else:
            print(f"  ❌ {book_name_zh}: 数据不存在")
            failed += 1
    return success, failed


def main():
    parser = argparse.ArgumentParser(description="성경 텍스트 다운로드 (개역개정 + 화합본)")
    parser.add_argument("--kr", action="store_true", help="개역개정만 다운로드")
    parser.add_argument("--zh", action="store_true", help="화합본만 다운로드")
    parser.add_argument("--test", action="store_true", help="테스트 모드 (요한복음 1장만)")
    args = parser.parse_args()

    do_kr = args.kr or (not args.kr and not args.zh)
    do_zh = args.zh or (not args.kr and not args.zh)

    print("=" * 60)
    print("  성경 텍스트 다운로드")
    print(f"  개역개정: {'ON' if do_kr else 'OFF'}")
    print(f"  화합본:   {'ON' if do_zh else 'OFF'}")
    print(f"  테스트:   {'ON' if args.test else 'OFF'}")
    print("=" * 60)

    if do_kr:
        print("\n📖 개역개정 (Korean Revised Version) 다운로드 중...")
        download_kr(test_only=args.test)

    if do_zh:
        print("\n📖 화합본 (和合本 / Chinese Union Version) 다운로드 중...")
        download_zh(test_only=args.test)

    print("\n✅ 완료!")
    print(f"  저장 위치: {BIBLE_DIR}/")


if __name__ == "__main__":
    main()
