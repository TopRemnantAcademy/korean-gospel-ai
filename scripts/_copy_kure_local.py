"""임시: HF Windows 심링크 캐시를 실제 파일로 복사.
snapshot 파일들이 깨진 심링크(ReparsePoint)라 열리지 않음 → os.readlink 로 blob 타깃을
얻어 실제 blob 파일을 직접 열어 복사. 완료 후 이 파일은 삭제함.
"""
import os
import shutil

SNAP = r"C:\Users\piaoy\.cache\huggingface\hub\models--nlpai-lab--KURE-v1\snapshots\d14c8a9423946e268a0c9952fecf3a7aabd73bd9"
DST = r"c:\Desktop\korean-gospel-ai\.models\KURE-v1-real"


def resolve_target(sym_path: str, target: str) -> str:
    # target 은 snapshot 파일 기준 상대 경로 (예: ..\..\blobs\<hash>)
    return os.path.normpath(os.path.join(os.path.dirname(sym_path), target))


def main():
    if os.path.exists(DST):
        shutil.rmtree(DST)
    total = 0
    n = 0
    for root, dirs, files in os.walk(SNAP):
        rel = os.path.relpath(root, SNAP)
        out_root = os.path.join(DST, rel) if rel != "." else DST
        os.makedirs(out_root, exist_ok=True)
        for f in files:
            sf = os.path.join(root, f)
            if os.path.islink(sf):
                tgt = os.readlink(sf)
                real = resolve_target(sf, tgt)
            else:
                real = sf
            df = os.path.join(out_root, f)
            sz = os.path.getsize(real)
            shutil.copyfile(real, df)
            total += sz
            n += 1
    print(f"COPIED files={n} bytes={total} ({total/1e9:.2f} GB) -> {DST}")


if __name__ == "__main__":
    main()
