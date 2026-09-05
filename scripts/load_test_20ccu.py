"""동시 접속 20명 부하 테스트 시나리오 — 동시 사용자(CCU) 기반 성능 검증.

목적:
  - 20명의 가상 사용자가 주요 기능(채팅/말씀/성경/음악/앱설정)을 동시에 실행할 때
    응답 시간(p50/p95/p99), 처리량(RPS), 에러율을 측정.
  - SQLite 커넥션 풀 경합, BEGIN IMMEDIATE 배타 락, 동기 블로킹 경로 등 병목 지점 식별.

실행:
  python scripts/load_test_20ccu.py --base-url http://127.0.0.1:8000 --users 20 --requests 10

의존성:
  - aiohttp 권장 (없으면 httpx → urllib 폴백). 측정만 하므로 HTTP 클라이언트는 범용 래퍼 사용.

출력:
  - 터미널 요약 리포트 (엔드포인트별 p50/p95/p99, RPS, error%)
  - 결과 JSON 저장 (load_test_result.json)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


# ── HTTP 클라이언트 래퍼 (aiohttp > httpx > urllib 폴백) ──────────────────────
async def _make_session(base_url: str):
    try:
        import aiohttp

        return "aiohttp", aiohttp.ClientSession(base_url=base_url, timeout=aiohttp.ClientTimeout(total=120))
    except Exception:
        pass
    try:
        import httpx

        return "httpx", httpx.AsyncClient(base_url=base_url, timeout=120)
    except Exception:
        pass
    return "urllib", None


async def _get(kind, sess, path: str, headers: Optional[dict] = None) -> tuple[int, float, bytes]:
    t0 = time.time()
    status = 0
    body = b""
    try:
        if kind == "aiohttp":
            async with sess.get(path, headers=headers or {}) as r:
                status = r.status
                body = await r.read()
        elif kind == "httpx":
            r = await sess.get(path, headers=headers or {})
            status = r.status_code
            body = r.content
        else:
            import urllib.request

            req = urllib.request.Request(base_url_dummy + path, headers=headers or {})
            with urllib.request.urlopen(req, timeout=120) as resp:
                status = resp.status
                body = resp.read()
    except Exception as e:
        status = -1
        body = str(e).encode()
    dt = (time.time() - t0) * 1000.0
    return status, dt, body


async def _post(kind, sess, path: str, json_body: dict, headers: Optional[dict] = None) -> tuple[int, float, bytes]:
    t0 = time.time()
    status = 0
    body = b""
    hdrs = dict(headers or {})
    try:
        if kind == "aiohttp":
            async with sess.post(path, json=json_body, headers=hdrs) as r:
                status = r.status
                body = await r.read()
        elif kind == "httpx":
            r = await sess.post(path, json=json_body, headers=hdrs)
            status = r.status_code
            body = r.content
        else:
            import urllib.request
            import json as _json

            data = _json.dumps(json_body).encode()
            req = urllib.request.Request(base_url_dummy + path, data=data, headers={**hdrs, "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=120) as resp:
                status = resp.status
                body = resp.read()
    except Exception as e:
        status = -1
        body = str(e).encode()
    dt = (time.time() - t0) * 1000.0
    return status, dt, body


base_url_dummy = ""


# ── 시나리오: 1명의 사용자 행동 프로필 ───────────────────────────────────────
async def _user_session(kind, sess, user_idx: int, per_user: int, auth_header: str, results: dict):
    """한 가상 사용자가 per_user 라운드 동안 수행하는 작업."""
    for i in range(per_user):
        round_tag = f"u{user_idx}-r{i}"

        # 1) 앱 설정 (정적, 캐시 대상)
        st, dt, _ = await _get(kind, sess, "/mobile/app-config")
        results["/mobile/app-config"].append((st, dt))

        # 2) 오늘의 말씀 (정적, 캐시 대상)
        st, dt, _ = await _get(kind, sess, "/mobile/verse/daily")
        results["/mobile/verse/daily"].append((st, dt))

        # 3) 음악 카탈로그 (정적, 캐시 대상)
        st, dt, _ = await _get(kind, sess, "/mobile/music")
        results["/mobile/music"].append((st, dt))

        # 4) 성경 읽기 (DB 조회)
        book, chapter = 43, 3  # 요한복음 3장
        st, dt, _ = await _get(kind, sess, f"/mobile/bible/read?book={book}&chapter={chapter}")
        results["/mobile/bible/read"].append((st, dt))

        # 5) 채팅 (주요 부하 경로 — LLM + 검색 + DB)
        #    각 가상 사용자는 고유 X-Forwarded-For 로 RateLimit(IP 기반)을 per-user 로 우회(테스트 정당성).
        #    또한 고유 user_id 를 전달해 쿼터 카운트를 per-user 로 분리.
        xff = f"203.0.113.{user_idx + 1}"  # TEST-NET-3 예약대역, 테스트용 시뮬레이션 IP
        chat_headers = {"X-Forwarded-For": xff}
        if auth_header:
            chat_headers["Authorization"] = auth_header
        chat_payload = {
            "query": f"하나님의 사랑을 어떻게 이해하면 좋을까요? (사용자 {user_idx} 라운드 {i})",
            "target_lang": "ko",
            "user_id": f"loadtest-guest-{user_idx}",
        }
        st, dt, _ = await _post(kind, sess, "/chat", chat_payload, headers=chat_headers)
        results["/chat"].append((st, dt))


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * pct
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return s[f]
    return s[f] + (s[c] - s[f]) * (k - f)


def _summarize(results: dict) -> dict:
    report = {}
    total_req = 0
    total_err = 0
    for ep, samples in results.items():
        dts = [dt for _, dt in samples]
        errs = [1 for st, _ in samples if st < 200 or st >= 400]
        total_req += len(samples)
        total_err += len(errs)
        report[ep] = {
            "count": len(samples),
            "errors": len(errs),
            "error_pct": round(100.0 * len(errs) / len(samples), 2) if samples else 0.0,
            "p50_ms": round(_percentile(dts, 0.50), 1),
            "p95_ms": round(_percentile(dts, 0.95), 1),
            "p99_ms": round(_percentile(dts, 0.99), 1),
            "min_ms": round(min(dts), 1) if dts else 0.0,
            "max_ms": round(max(dts), 1) if dts else 0.0,
            "mean_ms": round(statistics.mean(dts), 1) if dts else 0.0,
        }
    report["_aggregate"] = {
        "total_requests": total_req,
        "total_errors": total_err,
        "overall_error_pct": round(100.0 * total_err / total_req, 2) if total_req else 0.0,
    }
    return report


async def main():
    global base_url_dummy
    ap = argparse.ArgumentParser(description="20 CCU 부하 테스트")
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--users", type=int, default=20, help="동시 사용자 수")
    ap.add_argument("--requests", type=int, default=10, help="사용자당 라운드 수")
    ap.add_argument("--auth", default="", help="Bearer 토큰 (미설정 시 빈값)")
    ap.add_argument("--out", default="load_test_result.json")
    args = ap.parse_args()
    base_url_dummy = args.base_url

    kind, sess = await _make_session(args.base_url)
    auth_header = f"Bearer {args.auth}" if args.auth else ""
    print(f"[load-test] client={kind} base={args.base_url} users={args.users} rounds/user={args.requests}")

    results: dict[str, list] = defaultdict(list)
    t_start = time.time()

    # 20명의 사용자를 동시에 실행 (진짜 동시성)
    tasks = [
        _user_session(kind, sess, idx, args.requests, auth_header, results)
        for idx in range(args.users)
    ]
    await asyncio.gather(*tasks)

    wall = time.time() - t_start

    if sess is not None:
        try:
            await sess.close()
        except Exception:
            pass

    report = _summarize(results)
    total_req = report["_aggregate"]["total_requests"]
    rps = total_req / wall if wall > 0 else 0.0
    report["_aggregate"]["wall_seconds"] = round(wall, 2)
    report["_aggregate"]["throughput_rps"] = round(rps, 2)
    report["_meta"] = {
        "base_url": args.base_url,
        "users": args.users,
        "rounds_per_user": args.requests,
        "client": kind,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # 터미널 리포트
    print("\n" + "=" * 72)
    print(f"  부하 테스트 결과 — {args.users} CCU / 사용자당 {args.requests} 라운드")
    print("=" * 72)
    print(f"  총 요청: {total_req}  |  벽시계: {report['_aggregate']['wall_seconds']}s  |  처리량: {report['_aggregate']['throughput_rps']} RPS")
    print(f"  전체 에러율: {report['_aggregate']['overall_error_pct']}%")
    print("-" * 72)
    print(f"  {'엔드포인트':<26}{'cnt':>5}{'err%':>7}{'p50':>8}{'p95':>9}{'p99':>9}{'max':>9}")
    for ep, r in report.items():
        if ep.startswith("_"):
            continue
        print(f"  {ep:<26}{r['count']:>5}{r['error_pct']:>6}%{r['p50_ms']:>8}{r['p95_ms']:>9}{r['p99_ms']:>9}{r['max_ms']:>9}")
    print("=" * 72)
    print("\n  병목 해석 가이드:")
    print("   - /chat p95/p99 가 압도적으로 높으면 LLM 폴백 체인 + SQLite 쓰기(BEGIN IMMEDIATE) 가 병목")
    print("   - 정적 엔드포인트(/mobile/*) p95 가 100ms 초과면 커넥션 풀 경합 또는 캐시 미적용")
    print("   - 에러율 > 0 이면 커넥션 풀 고갈(busy_timeout 초과) 또는 레이트리밋(rate_limit) 가능성")

    Path(args.out).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n  결과 저장: {args.out}")


if __name__ == "__main__":
    asyncio.run(main())
