"""Alembic drift regression guard (A3 class of bug).

Prevents two migrations from adding the SAME column to the SAME table, or
creating the SAME table twice — the exact defect that made
`alembic upgrade head` fail with a "duplicate column" OperationalError
(c2fbb2654cf3 baseline and 00b32788914f both added identical subscriber /
document_version / interaction columns).

This is a static parse of the migration files; it needs no database.
"""
from __future__ import annotations

from pathlib import Path

import pytest

VERSIONS_DIR = (
    Path(__file__).resolve().parents[1] / "backend" / "migrations" / "versions"
)

# The migration that was demoted to a no-op to fix the drift — it must stay empty.
NOOP_MIGRATION = "00b32788914f"


def _iter_migration_files() -> list[Path]:
    return sorted(VERSIONS_DIR.glob("*.py"))


def _scan(text: str) -> tuple[set[tuple[str, str]], set[str], bool]:
    """Return (added (table,col) pairs, created tables, has_body)."""
    added: set[tuple[str, str]] = set()
    created: set[str] = set()
    has_body = False
    current_table: str | None = None

    for line in text.splitlines():
        if "create_table(" in line:
            # op.create_table('name', ...)
            import re

            m = re.search(r"create_table\(\s*'([^']+)'", line)
            if m:
                created.add(m.group(1))
                has_body = True
        if "batch_alter_table(" in line:
            import re

            m = re.search(r"batch_alter_table\(\s*'([^']+)'", line)
            if m:
                current_table = m.group(1)
        if "add_column(" in line:
            import re

            m = re.search(r"add_column\(\s*sa\.Column\(\s*'([^']+)'", line)
            if m and current_table is not None:
                added.add((current_table, m.group(1)))
                has_body = True
    return added, created, has_body


def test_no_duplicate_column_adds_across_migrations():
    seen: dict[tuple[str, str], set[str]] = {}
    tables: dict[str, set[str]] = {}

    for path in _iter_migration_files():
        added, created, _ = _scan(path.read_text(encoding="utf-8"))
        fname = path.stem
        for pair in added:
            seen.setdefault(pair, set()).add(fname)
        for t in created:
            tables.setdefault(t, set()).add(fname)

    dup_cols = {p: fs for p, fs in seen.items() if len(fs) > 1}
    dup_tables = {t: fs for t, fs in tables.items() if len(fs) > 1}

    assert not dup_cols, f"중복 컬럼 ADD 발견 (drift): {dup_cols}"
    assert not dup_tables, f"중복 테이블 CREATE 발견: {dup_tables}"


def test_demoted_migration_is_empty_noop():
    target = VERSIONS_DIR / f"{NOOP_MIGRATION}_e_a_token_quota_and_subscription_fields.py"
    assert target.exists(), f"{NOOP_MIGRATION} 마이그레이션 파일이 없습니다"
    _, _, has_body = _scan(target.read_text(encoding="utf-8"))
    assert not has_body, (
        f"{NOOP_MIGRATION} 는 no-op 이어야 하나 DDL 본문이 다시 들어왔습니다 "
        "(A3 드리프트 재발 위험)"
    )


@pytest.mark.parametrize("path", _iter_migration_files(), ids=lambda p: p.stem)
def test_migration_files_parse(path):
    # Ensure files are at least syntactically importable as modules.
    import importlib.util

    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    assert hasattr(mod, "revision")
    assert hasattr(mod, "upgrade")
    assert hasattr(mod, "downgrade")
