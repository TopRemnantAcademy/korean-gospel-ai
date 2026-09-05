"""D34 回归：download_to_temp (app/storage/s3.py) 必须先用 SSRF 守卫检查
song.audio_url（用户影响值）这一服务端抓取出口，与 routers/flow.py:50 同一标准。

IP 字面量由 getaddrinfo 在本地确定性解析，无需网络。
"""
import httpx
import pytest

from app.storage.s3 import download_to_temp


class _FakeResp:
    content = b"audio-bytes"

    def raise_for_status(self):
        return None


def test_d34_download_to_temp_blocks_loopback():
    with pytest.raises(ValueError):
        download_to_temp("http://127.0.0.1:8080/evil.wav")


def test_d34_download_to_temp_blocks_cloud_metadata():
    with pytest.raises(ValueError):
        download_to_temp("http://169.254.169.254/latest/meta-data/")


def test_d34_download_to_temp_proceeds_when_guard_allows(monkeypatch):
    # 守卫放行时，必须到达 httpx.get —— 证明守卫在出口处做闸门，而非无条件放行。
    from app.security.ssrf import ssrf_guard

    monkeypatch.setattr(ssrf_guard, "is_safe", lambda url: True)
    calls = {}

    def _fake_get(url, **kwargs):
        calls["url"] = url
        return _FakeResp()

    monkeypatch.setattr(httpx, "get", _fake_get)
    path = download_to_temp("http://public.example/ok.wav")
    assert calls.get("url") == "http://public.example/ok.wav"
    assert isinstance(path, str) and path
