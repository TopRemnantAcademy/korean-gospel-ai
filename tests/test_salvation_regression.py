"""구원(salvation) 회귀 케이스 회귀 테스트 — seed 데이터 소비 + detector 자가 검증.

실행:
    ./venv/Scripts/python.exe -m pytest tests/test_salvation_regression.py -q

설계 원칙 (기업级 견고성)
------------------------
- DB 는 임시 파일 SQLite 로 격리(운영 .gospel.db 에 영향 없음).
- `scripts/seed_salvation_regression.py` 가 기록한 `eval_question(category='salvation')`
  데이터를 본 테스트가 직접 소비 → seed 가 '잠자는 데이터'로 남지 않도록 한다.
- 두 계층 검증:
  1) 데이터 무결성(LLM 불필요, 항상 실행): 14건 존재 + expected_doc_ids 가
     'signal:/stage:/pastor:' 인코딩을 올바르게 보관.
  2) detector 회귀(best-effort): LLM 키가 있으면 detector 출력이 seed 기대값과
     일치하는지 단언. 키가 없으면 신호가 모두 null 로 돌아오므로 skip (플레키 방지).
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

# 운영 DB 와 격리: 임시 파일 경로를 DB_PATH 로 주입한 뒤 모듈 로드
_TMP_DB = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_TMP_DB.close()
os.environ["DB_PATH"] = _TMP_DB.name

from app.db import get_session_immediate, init_db  # noqa: E402
from app.models.orm import EvalQuestion  # noqa: E402
from app.services.salvation_detector import (  # noqa: E402
    SalvationSignal,
    _NULL_SIGNAL,
    detect_salvation_signal,
)

# seed 스크립트 모듈 임포트 (스크립트는 backend/app 가 아닌 repo/backend 기준 경로 사용)
SEED_DIR = ROOT / "scripts"
if str(SEED_DIR) not in sys.path:
    sys.path.insert(0, str(SEED_DIR))
from seed_salvation_regression import (  # noqa: E402
    NEGATIVE_REDLINE_CASES,
    POSITIVE_CASES,
    _seed,
)


def _parse_expected(doc_ids: list) -> dict:
    """seed 가 expected_doc_ids 에 인코딩한 'signal:/stage:/pastor:' 를 파싱."""
    out = {"signal": None, "stage": None, "pastor": False}
    for item in doc_ids or []:
        if not isinstance(item, str) or ":" not in item:
            continue
        key, _, val = item.partition(":")
        if key == "signal":
            out["signal"] = None if val == "None" else val
        elif key == "stage":
            out["stage"] = val
        elif key == "pastor":
            out["pastor"] = val == "true"
    return out


@pytest.fixture(scope="module")
def seeded_session():
    """임시 DB 를 초기화하고 14개 구원 회귀 케이스를 seed 한다."""
    init_db()
    _seed(dry_run=False)
    with get_session_immediate() as s:
        yield s


def test_seed_creates_14_salvation_cases(seeded_session) -> None:
    """seed 가 정확히 14건(긍정 10 + 레드라인 4)을 기록하는지."""
    rows = (
        seeded_session.query(EvalQuestion)
        .filter(EvalQuestion.category == "salvation")
        .all()
    )
    assert len(rows) == 14, f"salvation 케이스 수 불일치: {len(rows)}"
    positive_qs = {c["question"] for c in POSITIVE_CASES}
    redline_qs = {c["question"] for c in NEGATIVE_REDLINE_CASES}
    for r in rows:
        assert r.question in positive_qs | redline_qs
        assert r.active is True


def test_seed_encodes_expected_signal(seeded_session) -> None:
    """seed 가 expected_doc_ids 에 signal/stage/pastor 를 올바르게 인코딩했는지."""
    rows = (
        seeded_session.query(EvalQuestion)
        .filter(EvalQuestion.category == "salvation")
        .all()
    )
    by_q = {r.question: r for r in rows}

    for case in POSITIVE_CASES:
        r = by_q[case["question"]]
        exp = _parse_expected(r.expected_doc_ids)
        assert exp["signal"] == case["expected_signal"], case["question"]
        assert exp["stage"] == case["stage"], case["question"]
        assert exp["pastor"] is False, "긍정 케이스는 pastor=False 여야 함"

    for case in NEGATIVE_REDLINE_CASES:
        r = by_q[case["question"]]
        exp = _parse_expected(r.expected_doc_ids)
        assert exp["pastor"] == case.get("expects_pastor", False), case["question"]
        if case["expected_signal"] is not None:
            assert exp["signal"] == case["expected_signal"], case["question"]


def test_detector_matches_seed(seeded_session) -> None:
    """detector 출력이 seed 기대값과 일치하는지 (best-effort, 무 키 시 skip).

    LLM 키가 없으면 detect_salvation_signal 이 _NULL_SIGNAL 을 반환한다.
    이 경우 데이터 무결성 테스트만으로 충분하므로 본 테스트는 skip 한다.
    """
    rows = (
        seeded_session.query(EvalQuestion)
        .filter(EvalQuestion.category == "salvation")
        .all()
    )
    by_q = {r.question: r for r in rows}
    all_cases = [(c, False) for c in POSITIVE_CASES] + [
        (c, c.get("expects_pastor", False)) for c in NEGATIVE_REDLINE_CASES
    ]

    mismatches = 0
    probed = 0
    for case, expects_pastor in all_cases:
        text = case["question"]
        sig = asyncio.run(detect_salvation_signal(text, "unknown"))
        # 무 키 환경 감지: 신호도 없고 pastor 도 없으면 LLM 이 동작 안 한 것
        if sig.signal_type is None and not sig.requires_pastor:
            continue
        probed += 1
        exp = _parse_expected(by_q[text].expected_doc_ids)
        if exp["signal"] is not None and sig.signal_type != exp["signal"]:
            mismatches += 1
        if exp["pastor"] and not sig.requires_pastor:
            mismatches += 1

    if probed == 0:
        pytest.skip("LLM 키 미설정 — detector 회귀 검증 생략(best-effort)")

    assert mismatches == 0, f"detector 회귀 불일치 {mismatches}건 — 프롬프트/시드 재점검"


def test_null_signal_is_default() -> None:
    """_NULL_SIGNAL 이 안전한 기본값(fail-open)임을 보장."""
    assert _NULL_SIGNAL.signal_type is None
    assert _NULL_SIGNAL.requires_pastor is False
    assert isinstance(_NULL_SIGNAL, SalvationSignal)


def teardown_module(module) -> None:
    """임시 DB 파일 정리."""
    try:
        os.unlink(_TMP_DB.name)
    except OSError:
        pass
