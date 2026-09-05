"""Mureka provider 契约测试（不依赖真实网络，mock _post/_get）。

覆盖：prompt 强制注入 gospel + 声线；create 提交体字段；get 对 succeeded/failed/processing 的映射；
错误包体抽取与 429 双义重试判定（platform.mureka.ai/docs/en/error-codes.html，2026-09-03 抓取）。
请求/响应字段以 platform.mureka.ai 官方文档（2026-09-03 抓取）为准。
"""
import asyncio

import httpx

from app.orchestrator.base import GenerateRequest
from app.orchestrator.mureka import MurekaProvider


def _fake_resp(status: int, json_body: dict) -> httpx.Response:
    return httpx.Response(status_code=status, json=json_body)


def _make_provider() -> MurekaProvider:
    p = MurekaProvider.__new__(MurekaProvider)
    p.base = "https://api.mureka.ai/v1"
    p.api_key = "test-key"
    p.model = "mureka-9"
    p.n = 1
    p._sem = asyncio.Semaphore(1)
    p._timeout = None
    return p


def test_build_prompt_injects_gospel_and_gender():
    p = _make_provider()
    req = GenerateRequest(lyric="x", style="worship, piano", vocal_gender="female")
    prompt = p._build_prompt(req)
    assert "gospel" in prompt
    assert "female" in prompt
    assert "worship" in prompt


def test_create_submits_lyrics_model_gospel_and_gender():
    p = _make_provider()
    captured: dict = {}

    async def fake_post(path, json):
        captured["path"] = path
        captured["json"] = json
        return {"id": "1436211", "status": "preparing", "model": "mureka-9", "trace_id": "t1"}

    p._post = fake_post
    req = GenerateRequest(lyric="v1", style="piano", vocal_gender="male")
    res = asyncio.run(p.create(req))
    assert res.status == "processing"
    assert res.external_id == "1436211"
    assert res.model_version == "mureka-9"
    assert captured["path"] == "/song/generate"
    assert captured["json"]["lyrics"] == "v1"
    assert captured["json"]["model"] == "mureka-9"
    assert captured["json"]["n"] == 1
    assert "gospel" in captured["json"]["prompt"]
    assert captured["json"]["gender"] == "male"


def test_get_maps_succeeded_choice():
    p = _make_provider()

    async def fake_get(path):
        return {
            "id": "1", "status": "succeeded", "model": "mureka-9",
            "choices": [{"audio_url": "http://a.mp3", "cover_url": "http://c.png",
                         "lyrics": "ly", "title": "T", "duration": 120, "id": "clip1"}],
        }

    p._get = fake_get
    res = asyncio.run(p.get("1"))
    assert res.status == "completed"
    assert res.audio_url == "http://a.mp3"
    assert res.cover_url == "http://c.png"
    assert res.lyric == "ly"
    assert res.title == "T"
    assert res.duration == 120
    assert res.model_version == "mureka-9"
    assert res.custom_id == "clip1"


def test_get_maps_failed():
    p = _make_provider()

    async def fake_get(path):
        return {"id": "1", "status": "failed", "failed_reason": "content rejected"}

    p._get = fake_get
    res = asyncio.run(p.get("1"))
    assert res.status == "failed"
    # 失败原因作为审核提示落库（P2），不再误写入 lyric
    assert res.moderation_note == "content rejected"
    assert res.lyric is None


def test_get_maps_processing():
    p = _make_provider()

    async def fake_get(path):
        return {"id": "1", "status": "running"}

    p._get = fake_get
    res = asyncio.run(p.get("1"))
    assert res.status == "processing"


def test_extract_error_pulls_message_from_envelope():
    p = _make_provider()
    resp = _fake_resp(429, {"error": {"message": "You exceeded your current quota"}, "trace_id": "t"})
    assert p._extract_error(resp) == "You exceeded your current quota"


def test_should_retry_quota_exhausted_is_false():
    # error-codes 文档：429 额度耗尽不可重试（等也白等）
    p = _make_provider()
    resp = _fake_resp(429, {"error": {"message": "You exceeded your current quota, please check your plan and billing details"}})
    assert p._should_retry(resp) is False


def test_should_retry_rate_limit_is_true():
    # error-codes 文档：429 限流(Rate limit reached) 可退避重试
    p = _make_provider()
    resp = _fake_resp(429, {"error": {"message": "Rate limit reached, please retry later"}})
    assert p._should_retry(resp) is True


def test_should_retry_5xx_is_true():
    p = _make_provider()
    resp = _fake_resp(503, {"error": {"message": "engine overloaded"}})
    assert p._should_retry(resp) is True


def test_should_retry_non_retryable_status_is_false():
    p = _make_provider()
    resp = _fake_resp(401, {"error": {"message": "Invalid Authentication"}})
    assert p._should_retry(resp) is False


def test_create_does_not_send_title():
    # 官方 generate 请求体无 title 字段（歌名由 choices[].title 回传），锁定删除
    p = _make_provider()
    captured: dict = {}

    async def fake_post(path, json):
        captured["json"] = json
        return {"id": "1436211", "status": "preparing", "model": "mureka-9", "trace_id": "t1"}

    p._post = fake_post
    req = GenerateRequest(lyric="v1", style="piano", vocal_gender="male")
    asyncio.run(p.create(req))
    assert "title" not in captured["json"]


def test_create_truncates_prompt_to_1024():
    # 官方约束 prompt ≤1024（post-v1-song-generate.html）；超长截断避免 400
    p = _make_provider()
    captured: dict = {}

    async def fake_post(path, json):
        captured["json"] = json
        return {"id": "1436211", "status": "preparing", "model": "mureka-9", "trace_id": "t1"}

    p._post = fake_post
    long_prompt = "x" * 2000
    req = GenerateRequest(lyric="v1", style=long_prompt, vocal_gender="male")
    asyncio.run(p.create(req))
    assert len(captured["json"]["prompt"]) <= 1024
    assert captured["json"]["prompt"].startswith("gospel")


def test_get_billing_parses_fields():
    # GET /v1/account/billing（2026-09-03 核对）：查余额/并发上限，提前诊断 429 quota
    p = _make_provider()

    async def fake_get(path):
        return {
            "account_id": 123, "balance": 0, "total_recharge": 20000,
            "total_spending": 20000, "concurrent_request_limit": 1,
        }

    p._get = fake_get
    billing = asyncio.run(p.get_billing())
    assert billing["balance"] == 0
    assert billing["total_recharge"] == 20000
    assert billing["concurrent_request_limit"] == 1
    # 余额 0 → 即我们曾遇到的 "You exceeded your current quota" 根因

