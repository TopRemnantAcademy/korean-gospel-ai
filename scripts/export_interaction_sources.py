"""백데이터(interaction) 소스 분석 → CSV/JSON 내보내기 (콜라보 파일 V-2).

서버 없이 SQLite(.gospel.db)를 직접 읽어 집계한다.
  python scripts/export_interaction_sources.py --limit 200 --out data/analytics_export

참고: V-1 원안의 `GROUP BY target_lang`(언어별 분포)은 `interaction` 테이블에
해당 컬럼이 없어 제외 (할루시네이션 보정).
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / ".gospel.db"
if not DB_PATH.exists():
    # 폴백: 하위 탐색
    hits = list(ROOT.rglob(".gospel.db"))
    DB_PATH = hits[0] if hits else DB_PATH


def _aggregate(limit: int):
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT question, cited_versions, feedback FROM interaction "
            "ORDER BY rowid DESC LIMIT ?",
            (limit * 5,),
        ).fetchall()
        total_docs = conn.execute("SELECT count(*) FROM document").fetchone()[0]
    finally:
        conn.close()

    q_counter: Counter = Counter()
    doc_counter: Counter = Counter()
    kw_counter: Counter = Counter()
    feedback = {"positive": 0, "negative": 0, "none": 0}
    total = 0

    for r in rows:
        total += 1
        q = (r["question"] or "").strip()
        if q:
            q_counter[q] += 1
            for tok in re.findall(r"[가-힣A-Za-z0-9]+", q):
                if len(tok) >= 2:
                    kw_counter[tok] += 1
        cvs = r["cited_versions"]
        if isinstance(cvs, str):
            try:
                cvs = json.loads(cvs)
            except Exception:
                cvs = []
        if isinstance(cvs, list):
            for c in cvs:
                if isinstance(c, dict) and c.get("doc_id"):
                    doc_counter[c["doc_id"]] += 1
        fb = r["feedback"]
        if fb == 1:
            feedback["positive"] += 1
        elif fb == -1:
            feedback["negative"] += 1
        else:
            feedback["none"] += 1

    cited = len(doc_counter)
    return {
        "total_interactions": total,
        "sampled": len(rows),
        "question_trends": [{"question": k, "count": v} for k, v in q_counter.most_common(limit)],
        "doc_citation_ranking": [{"doc_id": k, "citations": v} for k, v in doc_counter.most_common(limit)],
        "keyword_trends": [{"keyword": k, "count": v} for k, v in kw_counter.most_common(limit)],
        "feedback": feedback,
        "coverage": {
            "total_documents": total_docs,
            "cited_documents": cited,
            "uncited_documents": max(total_docs - cited, 0),
        },
        "language_distribution": {
            "available": False,
            "reason": "interaction 테이블에 target_lang 컬럼이 없어 언어별 분포 제공 불가",
        },
    }


def _csv(rows, fields):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields)
    w.writeheader()
    for r in rows:
        w.writerow({k: r.get(k, "") for k in fields})
    return buf.getvalue()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--out", default="data/analytics_export")
    args = ap.parse_args()

    if not DB_PATH.exists():
        print(f"[ERR] DB 없음: {DB_PATH}", file=sys.stderr)
        sys.exit(1)

    data = _aggregate(args.limit)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    (out / "question_trends.csv").write_text(
        _csv(data["question_trends"], ["question", "count"]), encoding="utf-8"
    )
    (out / "doc_citation_ranking.csv").write_text(
        _csv(data["doc_citation_ranking"], ["doc_id", "citations"]), encoding="utf-8"
    )
    (out / "keyword_trends.csv").write_text(
        _csv(data["keyword_trends"], ["keyword", "count"]), encoding="utf-8"
    )
    (out / "interaction_analytics.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"[OK] 분석 완료 → {out}")
    print(f"  표본={data['total_interactions']}  질문종류={len(data['question_trends'])}  "
          f"인용문서={data['coverage']['cited_documents']}/{data['coverage']['total_documents']}  "
          f"피드백 +{data['feedback']['positive']}/-{data['feedback']['negative']}")


if __name__ == "__main__":
    main()
