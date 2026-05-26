"""공통 롤백 유틸리티 — DB 스냅샷 생성 + 복원."""
from __future__ import annotations

import os
import shutil
from datetime import datetime
from pathlib import Path


_BACKUP_DIR = Path(".upgrade_snapshots")


def _ensure_dir() -> Path:
    _BACKUP_DIR.mkdir(exist_ok=True)
    return _BACKUP_DIR


def snapshot_db(db_path: str = ".gospel.db") -> str:
    """SQLite DB를 타임스탬프 경로로 복사. 스냅샷 ID 반환."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    snap_id = f"db_{ts}"
    dest = _ensure_dir() / f"{snap_id}.db"
    if os.path.exists(db_path):
        shutil.copy2(db_path, dest)
    return snap_id


def restore_db(snap_id: str, db_path: str = ".gospel.db") -> bool:
    """스냅샷 ID로 DB 복원. 성공 시 True."""
    src = _BACKUP_DIR / f"{snap_id}.db"
    if not src.exists():
        return False
    shutil.copy2(src, db_path)
    return True


def snapshot_env(env_path: str = ".env") -> str:
    """현재 .env를 백업. 스냅샷 ID 반환."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    snap_id = f"env_{ts}"
    dest = _ensure_dir() / f"{snap_id}.env"
    if os.path.exists(env_path):
        shutil.copy2(env_path, dest)
    return snap_id


def restore_env(snap_id: str, env_path: str = ".env") -> bool:
    src = _BACKUP_DIR / f"{snap_id}.env"
    if not src.exists():
        return False
    shutil.copy2(src, env_path)
    return True


def full_snapshot() -> str:
    """DB + .env 동시 스냅샷. 복합 snap_id 반환."""
    db_id = snapshot_db()
    env_id = snapshot_env()
    return f"{db_id}|{env_id}"


def full_restore(snap_id: str) -> bool:
    """full_snapshot() 으로 만든 스냅샷 복원."""
    parts = snap_id.split("|")
    ok = True
    for part in parts:
        if part.startswith("db_"):
            ok = restore_db(part) and ok
        elif part.startswith("env_"):
            ok = restore_env(part) and ok
    return ok


def list_snapshots() -> list[dict]:
    """저장된 스냅샷 목록."""
    d = _ensure_dir()
    items = []
    for f in sorted(d.iterdir()):
        items.append({"name": f.name, "size_kb": round(f.stat().st_size / 1024, 1),
                      "created": datetime.fromtimestamp(f.stat().st_mtime).isoformat()})
    return items


def cleanup_old_snapshots(keep: int = 5) -> int:
    """오래된 스냅샷 정리. 삭제 수 반환."""
    d = _ensure_dir()
    files = sorted(d.iterdir(), key=lambda f: f.stat().st_mtime)
    to_delete = files[:-keep] if len(files) > keep else []
    for f in to_delete:
        f.unlink()
    return len(to_delete)
