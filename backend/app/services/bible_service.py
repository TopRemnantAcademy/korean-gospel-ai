"""성경 본문 서비스.

공개 도메인 성경 텍스트(개역개정 1998 등)를 data/bible/ 에서 로드.
운영자가 성경 텍스트 파일을 data/bible/{책명}.txt 형태로 넣으면 읽기 가능.

파일 형식 (절별):
  1:태초에 하나님이 천지를 창조하시니라
  2:땅이 혼돈하고 공허하며 흑암이 깊음 위에 있고 ...
  ...

또는 단순 텍스트 (장 구분 없이 전체):
  태초에 하나님이 천지를 창조하시니라...
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from ..config import settings

log = logging.getLogger("gospel-api.bible")

BIBLE_DIR = settings.root_dir / "data" / "bible"

# 캐시: { "창세기": {1: "본문...", 2: ...}, ... }
# version 별로 분리 (간체/번체 같은 책명 충돌 방지): key = f"{version}:{책명}"
_book_cache: dict[str, dict[int, str]] = {}

# 성경 버전 → 데이터 하위 디렉토리 매핑.
# - simpl (기본): 루트 + 개역개정/ + 화합본/ (간체)
# - trad: 화합본번체/ (번체 화합본)
# - kjv: kjv/ (영어 KJV — github.com/arleym/kjv-markdown)
VERSION_DIRS = {
    "simpl": ["", "개역개정", "화합본"],
    "trad": ["화합본번체"],
    "kjv": ["kjv"],
}
DEFAULT_VERSION = "simpl"

# 한글 성경 책명 정규화 (약자 → 풀네임)
_BOOK_ALIASES = {
    "창": "창세기", "출": "출애굽기", "레": "레위기", "민": "민수기", "신": "신명기",
    "수": "여호수아", "삿": "사사기", "룻": "룻기", "삼상": "사무엘상", "삼하": "사무엘하",
    "왕상": "열왕기상", "왕하": "열왕기하", "대상": "역대상", "대하": "역대하",
    "스": "에스라", "느": "느헤미야", "에": "에스더", "욥": "욥기", "시": "시편",
    "잠": "잠언", "전": "전도서", "아": "아가", "사": "이사야", "렘": "예레미야",
    "애": "예레미야 애가", "겔": "에스겔", "단": "다니엘", "호": "호세아", "욜": "요엘",
    "암": "아모스", "옵": "오바댜", "욘": "요나", "미": "미가", "나": "나훔",
    "합": "하박국", "습": "스바냐", "학": "학개", "슥": "스가랴", "말": "말라기",
    "마": "마태복음", "막": "마가복음", "눅": "누가복음", "요": "요한복음",
    "행": "사도행전", "롬": "로마서", "고전": "고린도전서", "고후": "고린도후서",
    "갈": "갈라디아서", "엡": "에베소서", "빌": "빌립보서", "골": "골로새서",
    "살전": "데살로니가전서", "살후": "데살로니가후서", "딤전": "디모데전서",
    "딤후": "디모데후서", "딛": "디도서", "몬": "빌레몬서", "히": "히브리서",
    "약": "야고보서", "벧전": "베드로전서", "벧후": "베드로후서",
    "요일": "요한일서", "요이": "요한이서", "요삼": "요한삼서",
    "유": "유다서", "계": "요한계시록",
}


def _normalize_book(book: str) -> str:
    """책명 정규화. '요' → '요한복음', '창세기' → '창세기'.

    보안: 한글/알파벳/숫자/공백/-/_ 외의 문자는 거부 (경로 순회 방지).
    """
    book = (book or "").strip()
    if not re.fullmatch(r"[가-힣一-鿿A-Za-z0-9 _-]{1,30}", book):
        return ""  # 유효하지 않은 책명
    if book in _BOOK_ALIASES:
        return _BOOK_ALIASES[book]
    return book


def _load_book(book: str, version: str = DEFAULT_VERSION) -> dict[int, str]:
    """특정 책 파일을 로드해 {장번호: 본문} 딕셔너리 반환.

    version: 'simpl'(간체/기본) 또는 'trad'(번체). 같은 책명이라도
    버전별 디렉토리에서 읽으므로 충돌하지 않는다.
    """
    # 유효하지 않은 책명 (경로 순회 시도 등) 즉시 거부
    if not book or not re.fullmatch(r"[가-힣一-鿿A-Za-z0-9 _-]{1,30}", book):
        return {}

    cache_key = f"{version}:{book}"
    if cache_key in _book_cache:
        return _book_cache[cache_key]

    # 가능한 파일명 패턴 시도 — 버전별 하위 디렉토리 검색
    subdirs = VERSION_DIRS.get(version, VERSION_DIRS[DEFAULT_VERSION])
    candidates = []
    for sub in subdirs:
        candidates.append(BIBLE_DIR / sub / f"{book}.txt")
        candidates.append(BIBLE_DIR / sub / f"{book}.json")
    candidates.append(BIBLE_DIR / f"{book}.json")
    path = next((p for p in candidates if p.exists()), None)

    if not path:
        # 빈 결과는 캐시하지 않음 — 런타임 파일 추가 시 즉시 반영되도록
        return {}

    # 추가 경로 검증: resolved 경로가 BIBLE_DIR 하위인지 확인
    try:
        resolved = path.resolve()
        bible_root = BIBLE_DIR.resolve()
        if bible_root not in resolved.parents and resolved != bible_root:
            log.warning("[bible] 경로 순회 차단: %s", book)
            return {}
    except Exception:
        return {}

    try:
        text = path.read_text(encoding="utf-8-sig")  # BOM 자동 제거
        chapters = _parse_text(text)
        if chapters:  # 성공한 결과만 캐시
            _book_cache[cache_key] = chapters
        return chapters
    except Exception as exc:
        log.warning("[bible] %s 로드 실패: %s", path.name, exc)
        return {}


def _parse_text(text: str) -> dict[int, str]:
    """텍스트를 파싱해 {장: 본문} 딕셔너리 반환.

    지원 형식:
      형식 A (권장): '장번호:' 가 단독 줄로 장 구분, 이후 줄마다 '절:본문'
        1:
        1:태초에 ...
        2:그가 ...
        2:
        1:...
      형식 B: 장 마커 없이 '절:본문' 만 있으면 전체를 1장으로
    """
    chapters: dict[int, str] = {}

    # 형식 A: '숫자:' 가 단독으로 한 줄을 차지하면 장 마커
    # 줄이 ':' 로 끝나고 앞이 숫자만 있으면 장 구분자
    chapter_only = re.compile(r"^(\d+)\s*:\s*$", re.MULTILINE)
    chap_matches = list(chapter_only.finditer(text))

    if chap_matches:
        for i, m in enumerate(chap_matches):
            chap_num = int(m.group(1))
            start = m.end()
            end = chap_matches[i + 1].start() if i + 1 < len(chap_matches) else len(text)
            # 중복 장 마커 시 첫 번째 내용 보존(조용한 덮어쓰기로 인한 본문 유실 방지)
            if chap_num not in chapters:
                chapters[chap_num] = text[start:end].strip()
    else:
        chapters[1] = text.strip()

    return chapters


def get_passage(book: str, chapter: int, verse: Optional[int] = None, version: str = DEFAULT_VERSION) -> Optional[str]:
    """특정 장/절의 본문 반환. 없으면 None."""
    norm_book = _normalize_book(book)
    chapters = _load_book(norm_book, version=version)
    if not chapters or chapter not in chapters:
        return None

    chapter_text = chapters[chapter]
    if verse is None:
        return chapter_text

    # 특정 절 추출: 다중행 절 지원 — 본문은 다음 절 마커 또는 장 끝까지
    verse_pattern = re.compile(rf"(?:^|\n){verse}\s*:\s*(.+?)(?=\n\d+\s*:|\Z)", re.DOTALL)
    m = verse_pattern.search(chapter_text)
    if m:
        return m.group(1).strip()
    return None


def _parse_verses(chapter_text: str) -> list[dict]:
    """장 본문에서 절 리스트 [{v:int, t:str}] 추출 (다중행 절 포함)."""
    out: list[dict] = []
    # 각 절: '숫자: 본문' 시작 ~ 다음 '숫자:' 마커 또는 장 끝 (DOTALL 로 다중행 포착)
    pat = re.compile(r"^(\d+)\s*:\s*(.+?)(?=\n\d+\s*:|\Z)", re.DOTALL | re.MULTILINE)
    for m in pat.finditer(chapter_text):
        out.append({"v": int(m.group(1)), "t": m.group(2).strip()})
    out.sort(key=lambda x: x["v"])
    return out


def get_passage_verses(book: str, chapter: int, version: str = DEFAULT_VERSION) -> Optional[list[dict]]:
    """장 전체의 절 리스트 [{v, t}] 반환. 없으면 None."""
    norm_book = _normalize_book(book)
    chapters = _load_book(norm_book, version=version)
    if not chapters or chapter not in chapters:
        return None
    return _parse_verses(chapters[chapter])


def get_verse_range(
    book: str, chapter: int, verse_start: Optional[int], verse_end: Optional[int],
    version: str = DEFAULT_VERSION,
) -> Optional[list[dict]]:
    """특정 절 범위 [verse_start, verse_end] 의 절 리스트. 범위 생략 시 장 전체."""
    verses = get_passage_verses(book, chapter, version=version)
    if not verses:  # None 이거나 빈 장(내용 없음) — IndexError 방지
        return None
    if verse_start is None and verse_end is None:
        return verses
    lo = verse_start if verse_start is not None else verses[0]["v"]
    hi = verse_end if verse_end is not None else verses[-1]["v"]
    return [v for v in verses if lo <= v["v"] <= hi]


def get_book_structure(book: str, version: str = DEFAULT_VERSION) -> Optional[dict]:
    """책의 구조: 총 장 수 + 장별 절 수.

    반환: {"book": str, "total_chapters": int,
            "chapters": [{"chapter": int, "verse_count": int}, ...]}
    없으면 None.
    """
    norm_book = _normalize_book(book)
    chapters = _load_book(norm_book, version=version)
    if not chapters:
        return None

    struct = []
    for ch in sorted(chapters.keys()):
        verses = _parse_verses(chapters[ch])
        struct.append({"chapter": ch, "verse_count": len(verses)})
    return {
        "book": norm_book,
        "total_chapters": len(struct),
        "chapters": struct,
    }


# ── 정본(和合本/CUV) 책 순서 + 구약·신약 구분 ───────────────────────────────────
# SN(정본) 순서 기준. list_available_books 가 이 순서로 정렬하며, 이 목록에 없는
# 책은 알파벳 순으로 뒤에 배치(추후 다른 번역본 추가 대비).
CANONICAL_BOOKS: list[str] = [
    # 구약 (39권) — 간체
    "创世记", "出埃及记", "利未记", "民数记", "申命记", "约书亚记", "士师记", "路得记",
    "撒母耳记上", "撒母耳记下", "列王纪上", "列王纪下", "历代志上", "历代志下", "以斯拉记",
    "尼希米记", "以斯帖记", "约伯记", "诗篇", "箴言", "传道书", "雅歌", "以赛亚书", "耶利米书",
    "耶利米哀歌", "以西结书", "但以理书", "何西阿书", "约珥书", "阿摩司书", "俄巴底亚书",
    "约拿书", "弥迦书", "那鸿书", "哈巴谷书", "西番雅书", "哈该书", "撒迦利亚书", "玛拉基书",
    # 신약 (27권) — 간체
    "马太福音", "马可福音", "路加福音", "约翰福音", "使徒行传", "罗马书", "哥林多前书",
    "哥林多后书", "加拉太书", "以弗所书", "腓立比书", "歌罗西书", "帖撒罗尼迦前书",
    "帖撒罗尼迦后书", "提摩太前书", "提摩太后书", "提多书", "腓利门书", "希伯来书", "雅各书",
    "彼得前书", "彼得后书", "约翰壹书", "约翰贰书", "约翰叁书", "犹大书", "启示录",
]
# 번체 정본 (화합본번체/) — 동일 정경 순서
CANONICAL_BOOKS_TRAD: list[str] = [
    # 구약 (39권)
    "創世記", "出埃及記", "利未記", "民數記", "申命記", "約書亞記", "士師記", "路得記",
    "撒母耳記上", "撒母耳記下", "列王紀上", "列王紀下", "歷代志上", "歷代志下", "以斯拉記",
    "尼希米記", "以斯帖記", "約伯記", "詩篇", "箴言", "傳道書", "雅歌", "以賽亞書", "耶利米書",
    "耶利米哀歌", "以西結書", "但以理書", "何西阿書", "約珥書", "阿摩司書", "俄巴底亞書",
    "約拿書", "彌迦書", "那鴻書", "哈巴谷書", "西番雅書", "哈該書", "撒迦利亞書", "瑪拉基書",
    # 신약 (27권)
    "馬太福音", "馬可福音", "路加福音", "約翰福音", "使徒行傳", "羅馬書", "哥林多前書",
    "哥林多後書", "加拉太書", "以弗所書", "腓立比書", "歌羅西書", "帖撒羅尼迦前書",
    "帖撒羅尼迦後書", "提摩太前書", "提摩太後書", "提多書", "腓利門書", "希伯來書", "雅各書",
    "彼得前書", "彼得後書", "約翰一書", "約翰二書", "約翰三書", "猶大書", "啟示錄",
]
# KJV (영어) 책 순서 — 표준 정경 순서 (구약 39 + 신약 27)
CANONICAL_BOOKS_KJV: list[str] = [
    "Genesis", "Exodus", "Leviticus", "Numbers", "Deuteronomy", "Joshua",
    "Judges", "Ruth", "1 Samuel", "2 Samuel", "1 Kings", "2 Kings",
    "1 Chronicles", "2 Chronicles", "Ezra", "Nehemiah", "Esther", "Job",
    "Psalms", "Proverbs", "Ecclesiastes", "Song of Solomon", "Isaiah",
    "Jeremiah", "Lamentations", "Ezekiel", "Daniel", "Hosea", "Joel",
    "Amos", "Obadiah", "Jonah", "Micah", "Nahum", "Habakkuk", "Zephaniah",
    "Haggai", "Zechariah", "Malachi", "Matthew", "Mark", "Luke", "John",
    "Acts", "Romans", "1 Corinthians", "2 Corinthians", "Galatians",
    "Ephesians", "Philippians", "Colossians", "1 Thessalonians",
    "2 Thessalonians", "1 Timothy", "2 Timothy", "Titus", "Philemon",
    "Hebrews", "James", "1 Peter", "2 Peter", "1 John", "2 John",
    "3 John", "Jude", "Revelation",
]
_OLD_TESTAMENT_COUNT = 39  # [구약 39권] → 나머지 = 신약
_CANONICAL_INDEX = {name: i for i, name in enumerate(CANONICAL_BOOKS)}
_CANONICAL_INDEX_TRAD = {name: i for i, name in enumerate(CANONICAL_BOOKS_TRAD)}
_CANONICAL_INDEX_KJV = {name: i for i, name in enumerate(CANONICAL_BOOKS_KJV)}


def _testament_of(book: str, version: str = DEFAULT_VERSION) -> str:
    """'old'(구약) / 'new'(신약) 반환. 목록에 없으면 'old'로 분류."""
    if version == "trad":
        index = _CANONICAL_INDEX_TRAD
    elif version == "kjv":
        index = _CANONICAL_INDEX_KJV
    else:
        index = _CANONICAL_INDEX
    idx = index.get(book)
    if idx is None:
        return "old"
    return "old" if idx < _OLD_TESTAMENT_COUNT else "new"


def list_book_summaries(version: str = DEFAULT_VERSION) -> list[dict]:
    """색인된 책 목록 + 구조 요약 (total_chapters, total_verses, testament)."""
    books = list_available_books(version=version)
    out = []
    for b in books:
        struct = get_book_structure(b, version=version)
        if not struct:
            continue
        out.append({
            "id": b,
            "name": b,
            "testament": _testament_of(b, version=version),
            "total_chapters": struct["total_chapters"],
            "total_verses": sum(c["verse_count"] for c in struct["chapters"]),
        })
    return out


def list_books_grouped(version: str = DEFAULT_VERSION) -> dict:
    """{"old": [...], "new": [...]} — 구약/신약별 정본 순서 목록."""
    summaries = list_book_summaries(version=version)
    return {
        "old": [s for s in summaries if s["testament"] == "old"],
        "new": [s for s in summaries if s["testament"] == "new"],
    }


def delete_book(book: str) -> bool:
    """책 파일 삭제. 경로 순회 방지 — 정규화 후 BIBLE_DIR 하위인지 검증."""
    norm_book = _normalize_book(book)
    if not norm_book:
        return False
    path = BIBLE_DIR / f"{norm_book}.txt"
    try:
        resolved = path.resolve()
        bible_root = BIBLE_DIR.resolve()
        if bible_root not in resolved.parents and resolved != bible_root:
            log.warning("[bible] 경로 순회 차단(삭제): %s", book)
            return False
        if resolved.exists():
            resolved.unlink()
            # 캐시 무효화 (버전 전체)
            for key in [k for k in _book_cache if k.endswith(f":{norm_book}")]:
                _book_cache.pop(key, None)
            return True
    except OSError as exc:
        log.warning("[bible] 삭제 실패: %s — %s", book, exc)
    return False


def list_available_books(version: str = DEFAULT_VERSION) -> list[str]:
    """색인된(사용 가능한) 책 목록 반환. 정본(SN) 순서 우선, 미등록은 알파벳 순.

    version 별로 해당 하위 디렉토리만 수집한다.
    - simpl: 루트 + 개역개정/ + 화합본/
    - trad: 화합본번체/
    """
    if not BIBLE_DIR.exists():
        return []
    subdirs = VERSION_DIRS.get(version, VERSION_DIRS[DEFAULT_VERSION])
    books: set[str] = set()
    for sub in subdirs:
        d = BIBLE_DIR / sub if sub else BIBLE_DIR
        if not d.is_dir():
            continue
        for f in d.iterdir():
            if f.is_file() and f.suffix.lower() == ".txt":
                books.add(f.stem)
    # 정본 순서 우선, 목록에 없는 책은 알파벳 순으로 뒤에 배치
    if version == "trad":
        index, canonical = _CANONICAL_INDEX_TRAD, CANONICAL_BOOKS_TRAD
    elif version == "kjv":
        index, canonical = _CANONICAL_INDEX_KJV, CANONICAL_BOOKS_KJV
    else:
        index, canonical = _CANONICAL_INDEX, CANONICAL_BOOKS
    return sorted(books, key=lambda b: index.get(b, len(canonical)))
