"""파일에서 텍스트 추출 + 품질 점수 + 노이즈 경고.

사용자가 "완성본"을 올린다고 했지만, 추출 자체는 안전하게 처리해야 한다.
- PDF: pypdf
- DOCX: python-docx
- TXT/MD: utf-8
- 한국어 인코딩 깨짐 감지
- 설교 transcript 노이즈([박수], [아멘] 등) 자동 제거 + 경고

progress_cb(current, total, detail) — 진행 콜백 (None 이면 무시).
  current: 처리 완료 페이지/항목 수
  total: 전체 수
  detail: 화면에 표시할 짧은 텍스트
"""
from __future__ import annotations
import io
import re
from dataclasses import dataclass
from typing import Callable, Optional as Opt

# 설교/강의 transcript 노이즈 패턴
NOISE_PATTERNS = [
    (re.compile(r"\[(박수|아멘|할렐루야|환호|웃음|침묵)\]"), "transcript_noise"),
    (re.compile(r"\(\s*\d+:\d+\s*\)"), "timestamp"),                      # (00:32)
    (re.compile(r"<<\s*[^>]+\s*>>"), "stage_direction"),                  # <<무대 지시>>
    (re.compile(r"­"), "soft_hyphen"),                                # 소프트 하이픈
]


@dataclass
class ExtractionResult:
    text: str
    quality_score: int          # 0~100
    warnings: dict              # {"noise": [...], "encoding": "...", ...}
    char_count: int


ProgressCb = Opt[Callable[[int, int, str], None]]


def extract(filename: str, raw: bytes, progress_cb: ProgressCb = None) -> ExtractionResult:
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    warnings: dict = {}

    if suffix == "pdf":
        text = _extract_pdf(raw, warnings, progress_cb=progress_cb)
    elif suffix == "docx":
        text = _extract_docx(raw, warnings)
    elif suffix in {"txt", "md"}:
        text = _extract_text(raw, warnings)
    else:
        # fallback: try utf-8
        text = raw.decode("utf-8", errors="replace")
        warnings["unknown_suffix"] = suffix

    # ---- 2) 영어 제거 (맨 먼저! 설교문은 한국어 전용, 통역 영어는 무조건 삭제) ----
    text, eng_removed = _strip_english(text)
    if eng_removed:
        warnings["english_removed"] = eng_removed

    # ---- 3) 노이즈 패턴 제거 + 기록 ----
    noise_hits: list[str] = []
    for pattern, code in NOISE_PATTERNS:
        for m in pattern.finditer(text):
            noise_hits.append(f"{code}:{m.group(0)[:30]}")
        text = pattern.sub("", text)
    if noise_hits:
        warnings["noise_removed"] = noise_hits[:20]

    # ---- 4) 정규화 ----
    text = re.sub(r"\r\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)   # 연속 빈줄 정리
    text = re.sub(r"[ \t]+", " ", text)      # 연속 공백
    text = text.strip()

    # ---- 5) 품질 점수 산정 ----
    score = _score(text, warnings)

    return ExtractionResult(
        text=text,
        quality_score=score,
        warnings=warnings,
        char_count=len(text),
    )


_PDF_PAGE_LIMIT = 150   # 150p 초과 시 잘라서 경고 — 타임아웃 방지


def _extract_pdf(raw: bytes, warnings: dict, progress_cb: ProgressCb = None) -> str:
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(raw))
        total_pages = len(reader.pages)
        extract_limit = min(total_pages, _PDF_PAGE_LIMIT)
        if total_pages > _PDF_PAGE_LIMIT:
            warnings["pdf_truncated"] = {
                "total_pages": total_pages,
                "extracted_pages": _PDF_PAGE_LIMIT,
                "reason": f"페이지 상한({_PDF_PAGE_LIMIT}p) 초과 — 나머지 {total_pages - _PDF_PAGE_LIMIT}p 건너뜀",
            }
        pages = []
        for i, p in enumerate(reader.pages[:extract_limit]):
            try:
                pages.append(p.extract_text() or "")
            except Exception as e:
                warnings.setdefault("pdf_page_errors", []).append({"page": i, "err": str(e)[:80]})
            # 진행 콜백 — 5페이지마다 또는 마지막 페이지에서 호출
            if progress_cb and (i % 5 == 0 or i == extract_limit - 1):
                progress_cb(i + 1, extract_limit, f"{i + 1}/{extract_limit} 페이지 완료")
        return "\n\n".join(pages)
    except Exception as e:
        warnings["pdf_error"] = str(e)[:200]
        return ""


def _extract_docx(raw: bytes, warnings: dict) -> str:
    try:
        import docx
        d = docx.Document(io.BytesIO(raw))
        return "\n".join(p.text for p in d.paragraphs)
    except Exception as e:
        warnings["docx_error"] = str(e)[:200]
        return ""


def _extract_text(raw: bytes, warnings: dict) -> str:
    # 한국어 인코딩 자동 시도
    for enc in ("utf-8", "utf-8-sig", "cp949", "euc-kr"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    warnings["encoding"] = "fallback_replace"
    return raw.decode("utf-8", errors="replace")


def _score(text: str, warnings: dict) -> int:
    """0~100 휴리스틱.
    - 길이 + 노이즈/에러 없음
    """
    if not text:
        return 0
    score = 100

    # 길이
    if len(text) < 200:
        score -= 30
    elif len(text) < 500:
        score -= 10

    # 경고/에러 차감
    if warnings.get("pdf_error") or warnings.get("docx_error"):
        score -= 40
    if warnings.get("pdf_page_errors"):
        score -= min(len(warnings["pdf_page_errors"]) * 3, 20)
    if warnings.get("noise_removed"):
        score -= min(len(warnings["noise_removed"]), 10)
    if warnings.get("encoding") == "fallback_replace":
        score -= 15

    return max(0, min(100, score))


def _strip_english(text: str) -> tuple[str, dict]:
    """설교문에서 영어(통역문, 성경 인용 등)를 무조건 제거.

    4-Pass 접근:
      Pass 1 — 괄호 영어 제거: "사랑(love)은" → "사랑은" (한국어 보존)
      Pass 2 — 줄 단위 제거: 영문 비율 70% 초과 줄 통째 삭제
      Pass 3 — 단어 단위 제거: 남은 줄에서 연속 라틴 알파벳 제거
      Pass 4 — 문법 cleanup: 고아 조사 정리("하나님의 는" → "하나님의"),
               이중 공백, 빈 줄 정리

    Returns:
        (정제된 텍스트, 제거 통계 dict)
    """
    latin_re = re.compile(r"[A-Za-z]")

    # ============================================================
    # Pass 1: 괄호 영어 제거 — 한국어는 그대로, 영어만 삭제
    # ============================================================
    # "하나님의 사랑(love)은" → "하나님의 사랑은"
    # "하나님의 사랑（love）은" → "하나님의 사랑은"
    # "하나님의 사랑 (love) 은혜" → "하나님의 사랑  은혜" (→ Pass 4에서 정리)
    # "(John 3:16) 하나님이..." → " 하나님이..." (→ Pass 4에서 정리)
    #
    # 핵심: 괄호 안에 라틴 알파벳이 하나라도 있으면 괄호 전체 제거.
    # 괄호 밖의 한국어는 건드리지 않는다.
    paren_eng_re = re.compile(
        r"[\(\（]\s*"                       # 여는 괄호
        r"[A-Za-z][A-Za-z\s.,;:!?\-\'\"]*" # 영문 내용 (최소 1자 라틴)
        r"[A-Za-z]?"                        # 마지막 글자 (숫자 허용)
        r"\s*[\)\）]"                       # 닫는 괄호
    )
    text, paren_count = paren_eng_re.subn("", text)

    # ============================================================
    # Pass 2: 줄 단위 제거
    # ============================================================
    latin_word_re = re.compile(r"\b[A-Za-z]{2,}\b")
    verse_ref_re = re.compile(r"[A-Za-z]+(?=\s*\d+:\d+)")

    lines = text.split("\n")
    kept_lines: list[str] = []
    removed_lines = 0
    removed_words = 0

    for line in lines:
        stripped = line.strip()
        if not stripped:
            kept_lines.append(line)
            continue

        # 라틴 비율 70% 초과 → 줄 전체 삭제
        latin_count = len(latin_re.findall(stripped))
        total_chars = max(len(stripped), 1)
        if latin_count / total_chars > 0.7:
            removed_lines += 1
            continue

        # ============================================================
        # Pass 3: 단어 단위 제거
        # ============================================================
        before = len(stripped)
        stripped = verse_ref_re.sub("", stripped)    # "Jn 3:16" → " 3:16"
        stripped = latin_word_re.sub("", stripped)   # "love", "grace" 등 제거
        after = len(stripped)

        if before != after:
            removed_words += 1

        # ============================================================
        # Pass 4: 문법 cleanup
        # ============================================================
        # 이중 공백
        stripped = re.sub(r"\s{2,}", " ", stripped)
        # 선행/후행 공백
        stripped = stripped.strip()

        if stripped:
            kept_lines.append(stripped)

    cleaned = "\n".join(kept_lines)

    # --- 전역 문법 cleanup ---

    # 연속 빈줄을 최대 2줄로
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

    # 고아 조사 정리: 영문 제거 후 "하나님의 는" → "하나님의"
    # 패턴: 한글+조사 + 공백 + 조사 → 한글+조사
    _KOREAN_JOSA = r"[은는을를이가에도로와과]"
    orphan_josa_re = re.compile(
        r"([가-힣]+" + _KOREAN_JOSA + r")\s+" + _KOREAN_JOSA
    )
    cleaned = orphan_josa_re.sub(r"\1", cleaned)

    # 줄바꿈 직후에 오는 고아 조사도 정리
    # "사랑\n는" → "사랑\n" (줄바꿈 앞 조사가 한글 단어 뒤에 있을 때만)
    orphan_josa_newline_re = re.compile(
        r"([가-힣]+" + _KOREAN_JOSA + r")\n+" + _KOREAN_JOSA
    )
    cleaned = orphan_josa_newline_re.sub(r"\1", cleaned)

    # --- 통계 ---
    stats: dict = {}
    if paren_count:
        stats["paren_english_removed"] = paren_count
    if removed_lines:
        stats["removed_lines"] = removed_lines
    if removed_words:
        stats["removed_word_sequences"] = removed_words

    return cleaned, stats
