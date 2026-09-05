"""DB 자동 마이그레이션 — ORM 모델과 실제 DB를 비교해서 빠진 컬럼을 추가한다.

사용:
    python scripts/migrate_db.py

Alembic 없이 간단히 ALTER TABLE ADD COLUMN 으로 빠진 컬럼을 채운다.
컬럼 삭제·이름변경은 지원 안 함 (안전 우선).
"""
from __future__ import annotations
import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import inspect, text

from backend.app.db import engine, Base
from backend.app.models import orm  # noqa — ORM 모델 등록


def _sqlite_type(col_type) -> str:
    t = str(col_type).upper()
    if t.startswith("VARCHAR") or t.startswith("STRING") or t.startswith("TEXT"):
        return t if t.startswith("VARCHAR") else "TEXT"
    if "INT" in t:
        return "INTEGER"
    if "FLOAT" in t or "NUMERIC" in t or "REAL" in t:
        return "REAL"
    if "BOOL" in t:
        return "INTEGER"   # SQLite boolean = integer
    if "DATE" in t or "TIME" in t:
        return "DATETIME"
    if "JSON" in t:
        return "TEXT"
    return "TEXT"


def _default_literal(col_type) -> str:
    """NOT NULL 컬럼 추가 시 기존 행용 기본값(타입별 적절한 리터럴).

    기존: 항상 DEFAULT '' → 숫자/불린 컬럼에 빈 문자열이 들어가 데이터 오염.
    """
    t = str(col_type).upper()
    if "INT" in t or "BOOL" in t:
        return "0"
    if "FLOAT" in t or "REAL" in t or "NUMERIC" in t:
        return "0.0"
    if "DATE" in t or "TIME" in t:
        return "'1970-01-01 00:00:00'"
    return "''"  # TEXT / VARCHAR / JSON



def run():
    insp = inspect(engine)
    existing_tables = set(insp.get_table_names())

    added_tables = []
    added_cols   = []
    added_idx    = []
    errors       = []

    with engine.connect() as conn:
        for table in Base.metadata.sorted_tables:
            tname = table.name

            if tname not in existing_tables:
                # 테이블 자체가 없으면 create_all 로 생성
                table.create(bind=engine)
                added_tables.append(tname)
                print(f"  [NEW TABLE] {tname}")
                continue

            # 기존 테이블 — 빠진 컬럼만 ADD COLUMN
            existing_cols = {c["name"] for c in insp.get_columns(tname)}
            for col in table.columns:
                if col.name not in existing_cols:
                    dtype = _sqlite_type(col.type)
                    nullable = (
                        "NULL"
                        if col.nullable
                        else f"NOT NULL DEFAULT {_default_literal(col.type)}"
                    )
                    sql = f'ALTER TABLE "{tname}" ADD COLUMN "{col.name}" {dtype} {nullable}'
                    try:
                        conn.execute(text(sql))
                        conn.commit()
                        added_cols.append(f"{tname}.{col.name} ({dtype})")
                        print(f"  [ADD COL] {tname}.{col.name}  {dtype}")
                    except Exception as e:
                        errors.append(f"{tname}.{col.name}: {e}")
                        print(f"  [SKIP] {tname}.{col.name}: {e}")

        # 기존 테이블에 새로 추가된 인덱스 생성 (index=True 컬럼 등)
        for table in Base.metadata.sorted_tables:
            tname = table.name
            if tname not in existing_tables:
                continue
            existing_idx = {i["name"] for i in insp.get_indexes(tname)}
            for idx in table.indexes:
                if idx.name in existing_idx:
                    continue
                cols = ", ".join(f'"{c.name}"' for c in idx.columns)
                unique = "UNIQUE " if idx.unique else ""
                sql = (
                    f'CREATE {unique}INDEX IF NOT EXISTS "{idx.name}" '
                    f'ON "{tname}" ({cols})'
                )
                try:
                    conn.execute(text(sql))
                    conn.commit()
                    added_idx.append(idx.name)
                    print(f"  [ADD IDX] {idx.name}")
                except Exception as e:
                    errors.append(f"{idx.name}: {e}")
                    print(f"  [SKIP IDX] {idx.name}: {e}")

    print("\n=== 결과 ===")
    print(f"신규 테이블: {len(added_tables)}개  {added_tables}")
    print(f"추가된 컬럼: {len(added_cols)}개")
    for c in added_cols:
        print(f"  + {c}")
    if errors:
        print(f"오류 {len(errors)}개:")
        for e in errors:
            print(f"  ! {e}")
    else:
        print("오류 없음 ✅")


if __name__ == "__main__":
    print("DB 마이그레이션 시작...")
    run()
    print("완료.")
