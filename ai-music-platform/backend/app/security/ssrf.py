"""음악 플랫폼 SSRF 가드 (자체 완결 — FLOW ``backend/app/security/ssrf.py`` 와 동일 설계).

용도:
  - ``routers/flow.py::_ensure_cdn_url`` 가 ``song.audio_url``(사용자 영향 값) 을
    서버 측 fetch 하기 전 내부/링크로컬/클라우드 메타데이터 주소 인출을 차단.
  - DNS-rebinding(TOCTOU) 방지를 위해 가드 통과 호스트를 한 번만 해석해 검증된 IP 로
    직접 연결(safe_ip_for + 호출처 핀닝).

음악 repo 는 FLOW 와 별개 ``app`` 패키지라 FLOW 의 ``ssrf.py`` 를 import 할 수 없으므로
동일 로직을 자체 모듈로 복사·유지한다(단일 소스 불일치 리스크는 문서로 고정).
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

import httpx

_ALLOWED_SCHEMES = {"http", "https"}


class SSRFGuard:
    def __init__(self, allow_private: bool = False, allowlist: set[str] | None = None):
        self.allow_private = allow_private
        self.allowlist = set(allowlist or set())

    def _resolved_ips(self, host: str) -> list[str]:
        try:
            return [info[4][0] for info in socket.getaddrinfo(host, None)]
        except Exception:
            return []

    def is_safe(self, url: str) -> bool:
        try:
            parsed = urlparse(url)
            if parsed.scheme not in _ALLOWED_SCHEMES:
                return False
            host = (parsed.hostname or "").lower()
            if not host:
                return False
            if host in self.allowlist:
                return True
            if self.allow_private:
                return True
            ips = self._resolved_ips(host)
            if not ips:
                return False
            for ip_str in ips:
                try:
                    addr = ipaddress.ip_address(ip_str)
                except ValueError:
                    return False
                if (
                    addr.is_loopback
                    or addr.is_private
                    or addr.is_link_local
                    or addr.is_reserved
                    or addr.is_multicast
                ):
                    return False
            return True
        except Exception:
            return False

    def guard(self, url: str) -> str:
        """안전하지 않으면 ValueError, 안전하면 url 반환."""
        if not self.is_safe(url):
            raise ValueError(f"SSRF guard: URL not allowed: {url}")
        return url

    def safe_ip_for(self, host: str) -> str:
        """호스트를 한 번 해석해 검증된 안전 IP 1개 반환(DNS-rebinding 방지용 핀닝).

        없으면 ValueError(가드를 이미 통과한 호스트여도 재검증 — 방어적).
        """
        for ip_str in self._resolved_ips(host):
            try:
                addr = ipaddress.ip_address(ip_str)
            except ValueError:
                continue
            if not (
                addr.is_loopback
                or addr.is_private
                or addr.is_link_local
                or addr.is_reserved
                or addr.is_multicast
            ):
                return ip_str
        raise ValueError(f"SSRF guard: no safe IP for {host}")

    async def safe_fetch(self, url: str, timeout: float = 60, **kwargs) -> httpx.Response:
        """httpx 래퍼 — 가드 + IP 핀닝 후 GET. DNS-rebinding(TOCTOU) 차단."""
        self.guard(url)
        parsed = urlparse(url)
        host = parsed.hostname or ""
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        safe_ip = self.safe_ip_for(host)
        pinned_netloc = f"[{safe_ip}]:{port}" if ":" in safe_ip else f"{safe_ip}:{port}"
        pinned_url = parsed._replace(netloc=pinned_netloc).geturl()
        headers = dict(kwargs.pop("headers", {}))
        headers.setdefault("Host", host)
        transport = httpx.AsyncHTTPTransport(server_name=host)
        async with httpx.AsyncClient(transport=transport, timeout=timeout) as c:
            r = await c.get(pinned_url, **kwargs)
            r.raise_for_status()
            return r


ssrf_guard = SSRFGuard()
