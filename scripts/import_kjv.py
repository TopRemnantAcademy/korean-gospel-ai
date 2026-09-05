"""KJV(영어) 성경 변환 스크립트 (2026-08-18)
소스: https://github.com/arleym/kjv-markdown (공개 도메인)
- 마크다운 66권을 다운로드해 파싱
- mobile/data/bible_kjv/ (1.json~66.json + bible_meta.json) 생성 — 간체/번체와 동일 형식
- data/bible/kjv/ (책명.txt) 생성 — 서버용 (장:절별)
"""
import json
import os
import re
import sys
import urllib.parse
import urllib.request

BASE = r"c:/Desktop/korean-gospel-ai"
SRC = "https://raw.githubusercontent.com/arleym/kjv-markdown/master"

# KJV 책명 (66권, 표준 순서). 파일명은 "NN - BookName - KJV.md"
BOOKS = [
    "Genesis", "Exodus", "Leviticus", "Numbers", "Deuteronomy", "Joshua",
    "Judges", "Ruth", "1 Samuel", "2 Samuel", "1 Kings", "2 Kings",
    "1 Chronicles", "2 Chronicles", "Ezra", "Nehemiah", "Esther", "Job",
    "Psalms", "Proverbs", "Ecclesiastes", "The Song of Solomon", "Isaiah",
    "Jeremiah", "Lamentations", "Ezekiel", "Daniel", "Hosea", "Joel",
    "Amos", "Obadiah", "Jonah", "Micah", "Nahum", "Habakkuk", "Zephaniah",
    "Haggai", "Zechariah", "Malachi", "Matthew", "Mark", "Luke", "John",
    "Acts", "Romans", "1 Corinthians", "2 Corinthians", "Galatians",
    "Ephesians", "Philippians", "Colossians", "1 Thessalonians",
    "2 Thessalonians", "1 Timothy", "2 Timothy", "Titus", "Philemon",
    "Hebrews", "James", "1 Peter", "2 Peter", "1 John", "2 John",
    "3 John", "Jude", "Revelation",
]

TESTAMENTS = ["old"] * 39 + ["new"] * 27

# 저장소 파일명과 표준 책명이 다른 경우 매핑 (파일명 → 표준 책명)
FNAME_OVERRIDES = {
    "The Song of Solomon": "Song of Solomon",
}


def slug(name: str) -> str:
    return name.replace(" ", "").replace("'", "")


def download(name: str) -> str:
    # BOOKS 항목은 실제 저장소 파일명과 동일 (예: "The Song of Solomon")
    fname = f"{BOOKS.index(name)+1:02d} - {name} - KJV.md"
    url = f"{SRC}/{urllib.parse.quote(fname)}"
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read().decode("utf-8")
        except Exception as e:
            print(f"    재시도 {attempt+1}: {e}")
            import time
            time.sleep(2)
    raise RuntimeError(f"다운로드 실패: {fname}")


def parse_md(text: str):
    """마크다운 파싱 → {장번호: {절번호: 본문}}

    - "## Genesis Chapter 1" 헤더 → 장 구분
    - 헤더 없는 한 장짜리 서신(2 John 등) → chapter 1로 처리
    """
    chapters = {}
    cur = None
    seen_header = False
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("#"):
            m = re.match(r"^##?\s+.*Chapter\s+(\d+)", line, re.IGNORECASE)
            if m:
                cur = int(m.group(1))
                chapters.setdefault(cur, {})
                seen_header = True
            continue
        m = re.match(r"^(\d+)\s+(.+)$", line)
        if m:
            if cur is None:
                # 장 헤더가 없는 한 장짜리 책 → chapter 1
                cur = 1
                chapters.setdefault(cur, {})
            chapters[cur][int(m.group(1))] = m.group(2).strip()
    return chapters


def main():
    os.makedirs(f"{BASE}/mobile/data/bible_kjv", exist_ok=True)
    os.makedirs(f"{BASE}/data/bible/kjv", exist_ok=True)

    books_meta = []
    total_verses = 0
    for i, name in enumerate(BOOKS, start=1):
        md = download(name)
        chapters = parse_md(md)
        n_verses = sum(len(v) for v in chapters.values())
        total_verses += n_verses
        std_name = FNAME_OVERRIDES.get(name, name)  # 표준 책명 (예: Song of Solomon)
        print(f"[{i:02d}] {name}: {len(chapters)}장 {n_verses}절")

        # 모바일 JSON (표준 책명 사용)
        ch_json = {str(c): [{"v": v, "t": txt} for v, txt in sorted(ch.items())]
                   for c, ch in sorted(chapters.items())}
        with open(f"{BASE}/mobile/data/bible_kjv/{i}.json", "w", encoding="utf-8") as f:
            json.dump({"book": std_name, "chapters": ch_json}, f, ensure_ascii=False)

        # 서버 txt — bible_service._parse_text의 형식 A:
        #   "1:" 단독 줄 = 장 마커, 이후 "절:본문" 라인
        with open(f"{BASE}/data/bible/kjv/{std_name}.txt", "w", encoding="utf-8") as f:
            for c, ch in sorted(chapters.items()):
                f.write(f"{c}:\n")
                for v, txt in sorted(ch.items()):
                    f.write(f"{v}:{txt}\n")

        books_meta.append({
            "id": std_name, "name": std_name, "short": std_name.split()[-1][:1],
            "chapters": len(chapters), "testament": TESTAMENTS[i - 1],
        })

    meta = {
        "version": "King James Version (KJV)",
        "source": "github.com/arleym/kjv-markdown (Public Domain)",
        "bible_books": books_meta,
    }
    with open(f"{BASE}/mobile/data/bible_kjv/bible_meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)

    print(f"\n총 {len(BOOKS)}권 / {total_verses}절 생성 완료")


if __name__ == "__main__":
    main()
