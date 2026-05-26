"""백업 - SQLite DB + Qdrant + 업로드 원본을 zip으로 묶음.

사용:  python scripts/backup.py
출력:  backups/gospel_YYYY-MM-DD_HHMM.zip
"""
from __future__ import annotations
import sys
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    backup_dir = ROOT / "backups"
    backup_dir.mkdir(exist_ok=True)

    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    out = backup_dir / f"gospel_{stamp}.zip"

    targets = []
    # SQLite DB (+ journal/wal)
    for p in ROOT.glob(".gospel.db*"):
        targets.append(p)
    # Qdrant local
    qd = ROOT / ".qdrant_local"
    if qd.exists():
        for p in qd.rglob("*"):
            if p.is_file():
                targets.append(p)
    # 업로드된 원본 파일들
    up = ROOT / "data" / "uploads"
    if up.exists():
        for p in up.rglob("*"):
            if p.is_file():
                targets.append(p)
    # 정책 룰북
    pol = ROOT / "data" / "eval" / "policy_rules.yaml"
    if pol.exists():
        targets.append(pol)

    if not targets:
        print("[X] 백업할 데이터가 없습니다.")
        sys.exit(1)

    print(f"[i] {len(targets)}개 파일 압축 중 -> {out.name}")
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in targets:
            arcname = p.relative_to(ROOT)
            z.write(p, arcname=str(arcname))

    size_mb = out.stat().st_size / 1024 / 1024
    print(f"[OK] {out}")
    print(f"     {size_mb:.1f} MB")

    # 5개 이상이면 오래된 것 삭제 (디스크 보호)
    backups = sorted(backup_dir.glob("gospel_*.zip"))
    if len(backups) > 10:
        for old in backups[:-10]:
            print(f"     ↳ 오래된 백업 삭제: {old.name}")
            old.unlink()


if __name__ == "__main__":
    main()
