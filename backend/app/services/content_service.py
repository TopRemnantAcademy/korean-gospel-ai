"""영성훈련 콘텐츠 링크 서비스.

관리자가 YouTube 강의, Spotify 찬양, 기타 외부 미디어 링크를 등록하면
모바일 앱의 영성훈련 탭에서 embed 재생.

지원 소스:
  - youtube  → YouTube 영상 (youtu.be/xxx, watch?v=xxx → embed/xxx)
  - spotify  → Spotify 트랙/앨범/플레이리스트 (open.spotify.com → embed)
  - other    → 기타 (원본 URL 그대로)
"""
from __future__ import annotations

import logging
import re
from typing import Optional
from urllib.parse import urlparse, parse_qs

from ..db import get_session
from ..models.orm import ContentLink

log = logging.getLogger("gospel-api.content")

# embed URL 변환을 지원하는 도메인 화이트리스트 (보안)
_ALLOWED_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "youtu.be",
    "open.spotify.com",
    "soundcloud.com",
    "vimeo.com",
}

# 소스 감지용 도메인 → source 매핑
_DOMAIN_TO_SOURCE = {
    "youtube.com": "youtube",
    "www.youtube.com": "youtube",
    "youtu.be": "youtube",
    "open.spotify.com": "spotify",
    "soundcloud.com": "other",
    "vimeo.com": "other",
}


def detect_source(url: str) -> str:
    """URL에서 소스(youtube/spotify/other) 자동 감지."""
    try:
        host = urlparse(url).hostname or ""
        return _DOMAIN_TO_SOURCE.get(host, "other")
    except Exception:
        return "other"


def is_allowed_url(url: str) -> bool:
    """허용된 도메인인지 + https 인지 검증 (보안)."""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("https",):
            return False
        host = parsed.hostname or ""
        return host in _ALLOWED_HOSTS
    except Exception:
        return False


def normalize_url(url: str, source: Optional[str] = None) -> tuple[str, Optional[str]]:
    """원본 URL을 (원본, embed_url) 로 변환.

    반환: (url, embed_url 또는 None — 변환 불가 시)
    """
    url = (url or "").strip()
    src = source or detect_source(url)

    if src == "youtube":
        embed = _youtube_embed(url)
        return url, embed

    if src == "spotify":
        embed = _spotify_embed(url)
        return url, embed

    # other — embed 변환 없음
    return url, None


def _youtube_embed(url: str) -> Optional[str]:
    """YouTube URL → embed URL 변환."""
    try:
        parsed = urlparse(url)
        host = parsed.hostname or ""

        # youtu.be/VIDEO_ID
        if host == "youtu.be":
            video_id = parsed.path.strip("/")
            if video_id:
                return f"https://www.youtube.com/embed/{video_id}"
            return None

        # youtube.com/watch?v=VIDEO_ID
        if "youtube.com" in host:
            if parsed.path == "/watch":
                video_id = parse_qs(parsed.query).get("v", [None])[0]
                if video_id:
                    return f"https://www.youtube.com/embed/{video_id}"
            # youtube.com/embed/VIDEO_ID (이미 embed)
            if parsed.path.startswith("/embed/"):
                return url
            # youtube.com/shorts/VIDEO_ID
            m = re.match(r"^/shorts/([A-Za-z0-9_-]+)", parsed.path)
            if m:
                return f"https://www.youtube.com/embed/{m.group(1)}"

        return None
    except Exception:
        return None


def _spotify_embed(url: str) -> Optional[str]:
    """Spotify URL → embed URL 변환."""
    try:
        parsed = urlparse(url)
        host = parsed.hostname or ""

        if host == "open.spotify.com":
            path = parsed.path or ""  # /track/xxx, /album/xxx, /playlist/xxx
            if path:
                return f"https://open.spotify.com/embed{path}"

        return None
    except Exception:
        return None


# ── CRUD ──────────────────────────────────────────────────────────────────────

def list_content(
    category: Optional[str] = None,
    source: Optional[str] = None,
    lang: Optional[str] = None,
    active_only: bool = True,
) -> list[dict]:
    """콘텐츠 링크 목록 조회 (lang 지정 시 해당 언어만 노출 — 중국어 앱은 한글 안 읽음)."""
    with get_session() as s:
        q = s.query(ContentLink)
        if category:
            q = q.filter(ContentLink.category == category)
        if source:
            q = q.filter(ContentLink.source == source)
        if lang:
            q = q.filter(ContentLink.lang == lang)
        if active_only:
            q = q.filter(ContentLink.active.is_(True))
        rows = q.order_by(ContentLink.order_index, ContentLink.created_at.desc()).all()
        return [_row_to_dict(r) for r in rows]


def create_content(
    *,
    title: str,
    url: str,
    source: Optional[str] = None,
    category: str = "lecture",
    description: Optional[str] = None,
    tags: Optional[list] = None,
    target_salvation_stage: Optional[list] = None,
    lang: str = "ko",
    order_index: int = 0,
    active: bool = True,
) -> dict:
    """콘텐츠 링크 생성. URL 보안 검증 + embed 변환 포함."""
    url = url.strip()
    if not is_allowed_url(url):
        raise ValueError(f"허용되지 않은 URL (https + 화이트리스트 도메인만 가능): {url}")

    detected_source = source or detect_source(url)
    # source/URL 불일치 검증 — 관리자 실수 방지 (spotify 선택 + youtube URL 등)
    auto_detected = detect_source(url)
    if source and auto_detected != "other" and source != auto_detected:
        raise ValueError(
            f"source({source})가 URL에서 감지된 소스({auto_detected})와 일치하지 않습니다."
        )
    final_url, embed_url = normalize_url(url, detected_source)

    link = ContentLink(
        title=title.strip(),
        description=description,
        url=final_url,
        embed_url=embed_url,
        lang=lang,
        source=detected_source,
        category=category,
        tags=tags or [],
        target_salvation_stage=target_salvation_stage or [],
        order_index=order_index,
        active=active,
    )
    with get_session() as s:
        s.add(link)
        s.flush()
        return _row_to_dict(link)


def update_content(link_id: str, fields: dict) -> dict:
    """콘텐츠 링크 부분 수정. url 변경 시 embed_url 재변환.

    보안: link_id/created_at/updated_at/embed_url 등은 화이트리스트로 보호.
    """
    # 수정 허용 필드 화이트리스트 — PK/timestamp/embed_url은 절대 외부 입력으로 덮어쓰지 않음
    _UPDATABLE_FIELDS = {
        "title", "description", "category", "tags",
        "target_salvation_stage", "order_index", "active",
    }
    # 명시적으로 null로 클리어 허용하는 필드
    _NULLABLE_FIELDS = {"description"}

    with get_session() as s:
        link = s.query(ContentLink).filter(ContentLink.link_id == link_id).first()
        if not link:
            raise ValueError("콘텐츠를 찾을 수 없습니다.")

        # url이 변경되면 source 재감지 + embed 재변환 (embed_url은 여기서만 설정)
        new_url = fields.get("url")
        if new_url and new_url != link.url:
            if not is_allowed_url(new_url):
                raise ValueError(f"허용되지 않은 URL: {new_url}")
            source = fields.get("source") or detect_source(new_url)
            final_url, embed_url = normalize_url(new_url, source)
            link.url = final_url
            link.embed_url = embed_url
            link.source = source

        # 화이트리스트 필드만 setattr — False/빈리스트/빈문자열은 정상 처리
        # description 등 _NULLABLE_FIELDS는 명시적 null 클리어 허용
        for key in (_UPDATABLE_FIELDS & fields.keys()):
            value = fields[key]
            if value is not None or key in _NULLABLE_FIELDS:
                setattr(link, key, value)

        s.flush()
        return _row_to_dict(link)


def delete_content(link_id: str) -> bool:
    """콘텐츠 링크 삭제."""
    with get_session() as s:
        link = s.query(ContentLink).filter(ContentLink.link_id == link_id).first()
        if not link:
            return False
        s.delete(link)
        s.flush()
        return True


def reorder_content(link_id: str, new_order: int) -> dict:
    """콘텐츠 정렬 순서 변경."""
    with get_session() as s:
        link = s.query(ContentLink).filter(ContentLink.link_id == link_id).first()
        if not link:
            raise ValueError("콘텐츠를 찾을 수 없습니다.")
        link.order_index = new_order
        s.flush()
        return _row_to_dict(link)


def _row_to_dict(row: ContentLink) -> dict:
    """ORM row → safe dict."""
    return {
        "link_id": row.link_id,
        "title": row.title,
        "description": row.description,
        "url": row.url,
        "embed_url": row.embed_url,
        "source": row.source,
        "lang": row.lang,
        "category": row.category,
        "tags": row.tags or [],
        "target_salvation_stage": row.target_salvation_stage or [],
        "order_index": row.order_index,
        "active": row.active,
        "created_at": str(row.created_at) if row.created_at else None,
        "updated_at": str(row.updated_at) if row.updated_at else None,
    }
