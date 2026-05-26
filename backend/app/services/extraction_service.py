"""파일에서 텍스트 추출 + 품질 점수 + 노이즈 경고.

사용자가 "완성본"을 올린다고 했지만, 추출 자체는 안전하게 처리해야 한다.
- PDF: pypdf
- DOCX: python-docx
- TXT/MD: utf-8
- 한국어 인코딩 깨짐 감지
- 설교 transcript 노이즈([박수], [아멘] 등) 자동 제거 + 경고
"""
from __future__ import annotations
import io
import re
from dataclasses import dataclass

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


def extract(filename: str, raw: bytes) -> ExtractionResult:
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    warnings: dict = {}

    if suffix == "pdf":
        text = _extract_pdf(raw, warnings)
    elif suffix == "docx":
        text = _extract_docx(raw, warnings)
    elif suffix in {"txt", "md"}:
        text = _extract_text(raw, warnings)
    else:
        # fallback: try utf-8
        text = raw.decode("utf-8", errors="replace")
        warnings["unknown_suffix"] = suffix

    # ---- 2) 노이즈 패턴 제거 + 기록 ----
    noise_hits: list[str] = []
    for pattern, code in NOISE_PATTERNS:
        for m in pattern.finditer(text):
            noise_hits.append(f"{code}:{m.group(0)[:30]}")
        text = pattern.sub("", text)
    if noise_hits:
        warnings["noise_removed"] = noise_hits[:20]

    # ---- 3) 정규화 ----
    text = re.sub(r"\r\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)   # 연속 빈줄 정리
    text = re.sub(r"[ \t]+", " ", text)      # 연속 공백
    text = text.strip()

    # ---- 4) 품질 점수 산정 ----
    score = _score(text, warnings)

    return ExtractionResult(
        text=text,
        quality_score=score,
        warnings=warnings,
        char_count=len(text),
    )


def _extract_pdf(raw: bytes, warnings: dict) -> str:
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(raw))
        pages = []
        for i, p in enumerate(reader.pages):
            try:
                pages.append(p.extract_text() or "")
            except Exception as e:
                warnings.setdefault("pdf_page_errors", []).append({"page": i, "err": str(e)[:80]})
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
    - 길이 + 한글 비율 + 노이즈/에러 없음
    """
    if not text:
        return 0
    score = 100

    # 길이
    if len(text) < 200:
        score -= 30
    elif len(text) < 500:
        score -= 10

    # 한글 비율 (한국어 문서 가정)
    han = sum(1 for c in text if 0xAC00 <= ord(c) <= 0xD7A3)
    ratio = han / max(len(text), 1)
    if ratio < 0.2:
        score -= 30   # 한국어 거의 없음
    elif ratio < 0.4:
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
