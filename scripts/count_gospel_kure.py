"""Count vectors in the local embedded Qdrant collection `gospel_kure`.

Run AFTER stopping the app (to release the embedded storage lock):
    PYTHONPATH=. venv/Scripts/python.exe scripts/count_gospel_kure.py
"""
from __future__ import annotations

import os

from qdrant_client import QdrantClient

STORAGE = "./.qdrant_local"
COLLECTION = "gospel_kure"


def main() -> None:
    if not os.path.exists(STORAGE):
        raise SystemExit(
            f"[ERR] embedded storage not found at: {STORAGE!r}\n"
            f"      Run this from the project root with the app stopped."
        )
    client = QdrantClient(path=STORAGE)
    cols = client.get_collections().collections
    print(f"collections found: {[c.name for c in cols]}")
    target = next((c.name for c in cols if c.name == COLLECTION), None)
    if target is None:
        print(f"[WARN] collection {COLLECTION!r} not found.")
        return
    res = client.count(COLLECTION)
    # qdrant_client >= 1.x: CountResult.count ; older: vector_count
    _cnt = getattr(res, "count", None)
    if _cnt is None:
        _cnt = getattr(res, "vector_count", None)
    print(f"{COLLECTION}: vectors_count = {_cnt}")
    try:
        total = sum(
            os.path.getsize(os.path.join(dp, f))
            for dp, _, fs in os.walk(STORAGE)
            for f in fs
        )
        print(f"storage size on disk: {total / 1024 / 1024:.1f} MB")
    except Exception as e:  # noqa: BLE001
        print(f"[info] could not measure storage size: {e}")


if __name__ == "__main__":
    main()
