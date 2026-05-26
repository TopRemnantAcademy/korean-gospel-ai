"""복원 - 가장 최근 백업(또는 지정 zip)을 복원.

사용:  python scripts/restore.py                  # 가장 최근 zip
       python scripts/restore.py backups/foo.zip  # 지정
"""
from __future__ import annotations
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    if len(sys.argv) > 1:
        zpath = Path(sys.argv[1])
        if not zpath.is_absolute():
            zpath = ROOT / zpath
    else:
        backups = sorted((ROOT / "backups").glob("gospel_*.zip"))
        if not backups:
            print("[X] 백업 파일이 없습니다.")
            sys.exit(1)
        zpath = backups[-1]

    if not zpath.exists():
        print(f"[X] 백업 파일 없음: {zpath}")
        sys.exit(1)

    print(f"[i] 복원 대상: {zpath.name}")
    print("[!] 기존 .gospel.db / .qdrant_local / data/uploads 를 덮어씁니다.")
    if input("정말 복원하시겠습니까? (YES 입력): ").strip() != "YES":
        print("취소됨")
        return

    with zipfile.ZipFile(zpath, "r") as z:
        z.extractall(ROOT)

    print(f"[OK] 복원 완료. STEP3_START.bat 으로 재시작하세요.")


if __name__ == "__main__":
    main()
