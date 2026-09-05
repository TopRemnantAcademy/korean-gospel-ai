"""Qdrant 어댑터.

주요 기능:
1. Qdrant 클라이언트 캐시
2. 지수 백오프 재시도
3. 컬렉션 보장 처리
4. sparse vector 지원
5. 타임아웃 설정
6. 에러 로깅
"""
from __future__ import annotations
import logging
import threading
import time
from dataclasses import dataclass
from typing import Optional, Sequence
import uuid

try:
    from qdrant_client import QdrantClient
    from qdrant_client.http import models as qm
except ImportError:
    QdrantClient = None
    qm = None

from ..config import settings

logger = logging.getLogger(__name__)

_QDRANT_TIMEOUT = 30.0  # 기본 타임아웃 (초)
_QDRANT_RETRY_COUNT = 3  # 최대 재시도 횟수
_QDRANT_RETRY_DELAY = 0.1  # 초기 재시도 딜레이 (지수 백오프 적용)


@dataclass(slots=True)
class RetrievedPoint:
    id: str
    score: float
    text: str
    metadata: dict


_BM42_MODEL = "Qdrant/bm42-all-minilm-l6-v2-attentions"


def _schema_type(name: str):
    """qdrant-client 버전 호환: 신버전은 PayloadSchemaType.KEYWORD, 구버전은 FieldType.Keyword."""
    st = getattr(qm, "PayloadSchemaType", None)
    if st is not None and hasattr(st, name.upper()):
        return getattr(st, name.upper())
    return getattr(qm.FieldType, name)


def _index_params(cls_name: str, type_val, **extra):
    """IndexParams 모델이 실제로 받아들이는 필드만 전달 (버전 호환)."""
    cls = getattr(qm, cls_name)
    accepted = set(getattr(cls, "model_fields", {}).keys())
    kwargs = {"type": type_val}
    for k, v in extra.items():
        if k in accepted:
            kwargs[k] = v
    return cls(**kwargs)

# ─── Qdrant 클라이언트 싱글톤 + 연결 풀링 ──────────────────────────────────
_client_instance: tuple | None = None
_client_lock = threading.RLock()  # 재진입 가능 락으로 데드락 방지
# embedded Qdrant 전용 프로세스 격리 락 핸들 (프로세스 종료 시 해제됨)
_EMBEDDED_LOCK_HANDLES: list = []


def _retry_qdrant_call(func, *args, **kwargs):
    """지수 백오프 재시도 래퍼.
    네트워크 일시 오류, 연결 타임아웃 등을 자동 복구합니다.
    """
    last_exc = None
    for attempt in range(_QDRANT_RETRY_COUNT):
        try:
            return func(*args, **kwargs)
        except (ConnectionError, TimeoutError) as e:
            last_exc = e
            if attempt < _QDRANT_RETRY_COUNT - 1:
                delay = _QDRANT_RETRY_DELAY * (2 ** attempt)
                logger.debug(
                    "[vector_store] Qdrant 호출 실패, %0.2f초 후 재시도 (%d/%d): %s",
                    delay, attempt + 1, _QDRANT_RETRY_COUNT, e
                )
                time.sleep(delay)
        except Exception as e:
            # 그 외 오류는 즉시 전파
            logger.error("[vector_store] Qdrant 오류: %s", e)
            raise

    logger.warning(
        "[vector_store] Qdrant 최대 재시도 %d회 모두 실패", _QDRANT_RETRY_COUNT
    )
    raise last_exc or Exception("Qdrant 호출 실패")


def _acquire_embedded_lock(path: str) -> None:
    """임베디드 Qdrant dev 격리 가드 (P1-1).

    동일 경로의 embedded DB를 1개 프로세스만 쓰도록 크로스-프로세스
    권고(advisory) 락을 잡는다. 다른 프로세스가 이미 잡고 있으면
    무한 대기하지 않고 즉시 RuntimeError 로 실패한다(인제스트/API 동시
    실행 데드락 방지). 락 핸들은 프로세스 종료까지 유지된다.

    단, Windows에서 force-kill/크래시로 죽은 프로세스가 남긴 STALE 락은
    OS가 자동 해제하지 않아 재기동 시 영원히 막히는 문제가 있어, PID 기반으로
    소유자 생존 여부를 판별한다. 죽은 프로세스의 락은 자동 회수(stale-lock
    recovery)하고, 살아있는 프로세스가 점유 중이면 정당한 충돌로 실패한다.
    """
    import os

    os.makedirs(path, exist_ok=True)
    lock_path = os.path.join(path, ".kggateway_embedded.lock")
    pid_path = os.path.join(path, ".kggateway_embedded.pid")

    def _pid_alive(pid: int) -> bool:
        if pid <= 0:
            return False
        if os.name == "nt":
            import ctypes

            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if h:
                kernel32.CloseHandle(h)
                return True
            # ERROR_INVALID_PARAMETER(87): 해당 PID 프로세스 없음 → 죽음
            return ctypes.GetLastError() != 87  # type: ignore[attr-defined]
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    def _read_old_pid() -> int | None:
        try:
            with open(pid_path, "r") as pf:
                return int(pf.read().strip())
        except (OSError, ValueError):
            return None

    def _clear_stale_lock() -> None:
        # 살아있는 프로세스가 없는 락 파일만 제거. 락 바이트가 OS에 남아
        # 있어도 파일을 지우고 새로 열면 신규 핸들로 우회된다.
        for p in (lock_path, pid_path):
            try:
                if os.path.exists(p):
                    os.remove(p)
            except OSError:
                pass

    old_pid = _read_old_pid()
    if old_pid is not None and _pid_alive(old_pid):
        # 실제로 다른 살아있는 프로세스가 점유 중 → 정당한 충돌
        raise RuntimeError(
            "embedded Qdrant가 이미 다른 프로세스에 의해 사용 중입니다 "
            f"(락 파일: {lock_path}, 소유 PID={old_pid}). "
            "인제스트/API 프로세스를 하나만 실행하거나 "
            "QDRANT_URL을 서버 모드(http://...)로 설정하세요."
        )

    # stale(죽은 프로세스) 이거나 최초 실행 → 락 파일 정리 후 점유
    if old_pid is not None:
        _clear_stale_lock()

    try:
        f = open(lock_path, "w+")
    except OSError as e:
        raise RuntimeError(f"embedded Qdrant 락 파일을 열 수 없습니다: {lock_path} ({e})")
    try:
        if os.name == "nt":
            import msvcrt

            try:
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                # 방어: 그래도 실패하면 stale 로 판단해 한 번 더 정리 후 재시도
                _clear_stale_lock()
                try:
                    f.close()
                except OSError:
                    pass
                f = open(lock_path, "w+")
                try:
                    msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                except OSError:
                    raise RuntimeError(
                        "embedded Qdrant가 이미 다른 프로세스에 의해 사용 중입니다 "
                        f"(락 파일: {lock_path}). 인제스트/API 프로세스를 하나만 실행하거나 "
                        "QDRANT_URL을 서버 모드(http://...)로 설정하세요."
                    )
        else:
            import fcntl

            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                _clear_stale_lock()
                try:
                    f.close()
                except OSError:
                    pass
                f = open(lock_path, "w+")
                try:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError:
                    raise RuntimeError(
                        "embedded Qdrant가 이미 다른 프로세스에 의해 사용 중입니다 "
                        f"(락 파일: {lock_path})."
                    )
        # 점유 성공 → 현재 PID 기록 (다음 기동 시 stale 판별용)
        try:
            with open(pid_path, "w") as pf:
                pf.write(str(os.getpid()))
        except OSError:
            pass
        _EMBEDDED_LOCK_HANDLES.append(f)
    except Exception:
        try:
            f.close()
        except Exception:
            pass
        raise


def _build_qdrant_client() -> tuple[QdrantClient, bool]:
    """실제 QdrantClient 생성. 실패 시 예외 발생."""
    if QdrantClient is None or qm is None:
        raise RuntimeError("qdrant-client 패키지가 설치되어 있지 않습니다. 검색 기능을 사용하려면 requirements.txt 의존성을 설치하세요.")
    url = (settings.qdrant_url or "").strip()
    if url.startswith("local:"):
        raw_path = url.split(":", 1)[1] or "./.qdrant_local"
        from pathlib import Path as _Path
        path = str((_Path(settings.root_dir) / raw_path).resolve())
        # prod/staging 에서는 embedded 사용 금지 → 서버 모드 강제 (P1-1 fail-closed)
        _env = (settings.app_env or "dev").strip().lower()
        if _env in ("prod", "production", "staging"):
            raise RuntimeError(
                f"embedded Qdrant(local:)는 prod/staging에서 사용할 수 없습니다. "
                f"QDRANT_URL을 서버 URL(http://...)로 설정하세요. (현재 app_env={settings.app_env})"
            )
        # dev 격리 가드: 다른 프로세스가 쓰고 있으면 즉시 실패 (무한 대기 방지)
        _acquire_embedded_lock(path)
        logger.info("[vector_store] Qdrant embedded 모드: %s", path)
        return QdrantClient(path=path, timeout=_QDRANT_TIMEOUT), False
    if url in {"memory:", ":memory:", "memory"}:
        logger.info("[vector_store] Qdrant memory 모드")
        return QdrantClient(location=":memory:", timeout=_QDRANT_TIMEOUT), False
    # prod/staging 서버 모드에서는 인증 키 필수 (빈 키 fail-closed, #4)
    _env = (settings.app_env or "dev").strip().lower()
    if _env in ("prod", "production", "staging") and not settings.qdrant_api_key:
        raise RuntimeError(
            f"prod/staging Qdrant 서버 모드에는 QDRANT_API_KEY 가 필수입니다 "
            f"(현재 app_env={settings.app_env}, 키 미설정). 인증 없는 Qdrant 기동을 거부합니다."
        )
    logger.info("[vector_store] Qdrant server 모드: %s", url)
    # gRPC는 설정에서 활성화 (기본 REST, PREFER_GRPC=true 시 gRPC)
    use_grpc = str(settings.qdrant_grpc or "").lower() == "true"
    return QdrantClient(
        url=url,
        api_key=settings.qdrant_api_key or None,
        prefer_grpc=use_grpc,
        timeout=_QDRANT_TIMEOUT,
    ), True


def _make_client() -> tuple[QdrantClient | None, bool]:
    """(QdrantClient | None, is_server: bool) 반환."""
    global _client_instance
    # 캐시된 클라이언트가 있으면 바로 반환
    if _client_instance is not None:
        return _client_instance

    with _client_lock:
        # Double-check: 락 대기 중 다른 쓰레드가 초기화했을 수 있음
        if _client_instance is not None:
            return _client_instance
        try:
            result = _build_qdrant_client()
            _client_instance = result
            return result
        except Exception as exc:
            logger.warning("[vector_store] Qdrant 초기화 실패 (재시도 가능): %s", exc)
            return (None, False)  # 캐시 안 함 → 다음 호출에서 재시도


_sparse_encoder_instance = None

def _sparse_encoder():
    """Sparse 인코더 싱글톤. 메모리 절약 + 중복 로딩 방지."""
    global _sparse_encoder_instance
    if _sparse_encoder_instance is None:
        from fastembed import SparseTextEmbedding
        _sparse_encoder_instance = SparseTextEmbedding(model_name=_BM42_MODEL)
    return _sparse_encoder_instance


_sparse_cache: dict[str, qm.SparseVector] = {}
_sparse_cache_lock = threading.Lock()  # [FIX] to_thread 병렬 호출 대응
_SPARSE_CACHE_MAX = 2000


def _to_sparse(text: str) -> qm.SparseVector:
    """Sparse 임베딩 — 텍스트를 직접 캐시 키로 사용 (MD5 해싱 제거)."""
    with _sparse_cache_lock:
        if text in _sparse_cache:
            return _sparse_cache[text]
    enc = _sparse_encoder()
    out = next(enc.embed([text]))
    result = qm.SparseVector(indices=out.indices.tolist(), values=out.values.tolist())
    with _sparse_cache_lock:
        if len(_sparse_cache) >= _SPARSE_CACHE_MAX:
            # 간단한 캐시 축소: 절반 삭제
            keys_to_remove = list(_sparse_cache.keys())[:_SPARSE_CACHE_MAX // 2]
            for k in keys_to_remove:
                del _sparse_cache[k]
        _sparse_cache[text] = result
    return result


def _to_sparse_batch(texts: Sequence[str]) -> list[qm.SparseVector]:
    """배치 sparse 임베딩 - 단일 모델 호출로 오버헤드 감소."""
    enc = _sparse_encoder()
    return [
        qm.SparseVector(indices=o.indices.tolist(), values=o.values.tolist())
        for o in enc.embed(list(texts))
    ]


# ─── 컬렉션 보장 락 세분화 ──────────────────────────────────────────────────
# 전역 락 대신 컬렉션별 락을 사용하여 동시 생성시 경합 감소
_ensured_collections: set[str] = set()
_ensured_lock = threading.RLock()


class QdrantStore:
    def __init__(
        self,
        embedder_name: str,
        dim: int,
        collection: str | None = None,
        extra_vectors: dict | None = None,
    ):
        self.embedder_name = embedder_name
        self.dim = dim
        self.collection = collection or settings.collection_name(embedder_name)
        # 이중 저장 등을 위한 추가 명명 벡터 설정 (name -> VectorParams)
        self.extra_vectors = extra_vectors or {}
        self._client, self.use_sparse = _make_client()

    def _recover_client(self) -> bool:
        if self._client:
            return True
        self._client, self.use_sparse = _make_client()
        return bool(self._client)

    def _ensure_collection(self):
        """컬렉션 없으면 생성 - 세분화된 락 + DCL 적용"""
        if self.collection in _ensured_collections:
            return

        with _ensured_lock:
            if self.collection in _ensured_collections:
                return

            if not self._recover_client():
                logger.warning(
                    "[vector_store] 클라이언트 없어 컬렉션 생성 불가: %s",
                    self.collection
                )
                return

            if not self._client.collection_exists(self.collection):
                vectors_config = {
                    "dense": qm.VectorParams(
                        size=self.dim,
                        distance=qm.Distance.COSINE,
                        # HNSW 튜닝: 속도와 정확도 균형
                        hnsw_config=qm.HnswConfigDiff(
                            m=16,
                            ef_construct=128,
                            full_scan_threshold=10000,
                            max_indexing_threads=4,
                        ),
                        quantization_config=qm.ScalarQuantization(
                            scalar=qm.ScalarQuantizationConfig(
                                type=(getattr(qm.ScalarType, "INT8", None)
                                      or getattr(qm.ScalarType, "Int8", None)),
                                always_ram=True,
                            ),
                        ),
                    ),
                }
                # 이중 저장 등을 위한 추가 명명 벡터 병합
                if self.extra_vectors:
                    vectors_config.update(self.extra_vectors)
                sparse_config = (
                    {
                        "sparse": qm.SparseVectorParams(
                            index=qm.SparseIndexConfig(
                                full_scan_threshold=5000,
                                datatype=qm.SparseDatatype.Float32,
                            ),
                            modifier=qm.Modifier.IDF,
                        ),
                    }
                    if self.use_sparse
                    else None
                )

                # 필터에 사용하는 payload index 생성 (qdrant-client 버전 호환:
                # 신버전에서 일부 IndexParams 가 Union 별칭이면 생성 실패 → 인덱스 생략)
                try:
                    payload_schema = {
                        "doc_type": qm.PayloadSchemaParams(
                            schema=_index_params(
                                "KeywordIndexParams", _schema_type("Keyword"),
                                is_optional=True, lookup=True,
                            ),
                        ),
                        "gospel_core_tag": qm.PayloadSchemaParams(
                            schema=_index_params(
                                "BoolIndexParams", _schema_type("Bool"),
                                is_optional=True,
                            ),
                        ),
                        "is_canonical_doc": qm.PayloadSchemaParams(
                            schema=_index_params(
                                "BoolIndexParams", _schema_type("Bool"),
                                is_optional=True,
                            ),
                        ),
                        "target_salvation_stage": qm.PayloadSchemaParams(
                            schema=_index_params(
                                "KeywordIndexParams", _schema_type("Keyword"),
                                is_optional=True, lookup=True,
                            ),
                        ),
                        "darakbang_tier": qm.PayloadSchemaParams(
                            schema=_index_params(
                                "KeywordIndexParams", _schema_type("Keyword"),
                                is_optional=True, lookup=True,
                            ),
                        ),
                    }
                except Exception as _pe:
                    logger.warning(
                        "[vector_store] payload schema 생성 실패 — 인덱스 없이 진행: %s", _pe
                    )
                    payload_schema = {}

                self._client.create_collection(
                    collection_name=self.collection,
                    vectors_config=vectors_config,
                    sparse_vectors_config=sparse_config,
                    optimizers_config=qm.OptimizersConfigDiff(
                        indexing_threshold=1000,  # 즉시 인덱싱
                        max_optimization_threads=2,
                    ),
                )

                # 페이로드 인덱스 생성
                for field_name, params in payload_schema.items():
                    try:
                        self._client.create_payload_index(
                            collection_name=self.collection,
                            field_name=field_name,
                            field_schema=params.schema,
                        )
                    except Exception as e:
                        logger.debug("[vector_store] 인덱스 생성 스킵: %s", e)

            _ensured_collections.add(self.collection)

    # ──────────────────────────────────────────────────────────────────────────
    # 검색 메서드 - 동적 ef_search + 재시도 적용
    # ──────────────────────────────────────────────────────────────────────────

    def search_dense(
        self,
        query_vec: Sequence[float],
        *,
        top_k: int = 20,
        flt: Optional[qm.Filter] = None,
        using: str = "dense",
    ) -> list[RetrievedPoint]:
        if not self._recover_client():
            return []

        # 동적 ef_search: top_k에 비례하여 탐색 범위 확장
        # 최적화: 설정된 상한(기존 256 → ef_search_cap)까지만 사용해 속도 향상
        ef_search = min(settings.ef_search_cap, max(64, top_k * 4 + 32))

        def _search():
            res = self._client.query_points(
                collection_name=self.collection,
                query=list(query_vec),
                using=using,
                limit=top_k,
                with_payload=True,
                with_vectors=False,  # 벡터 반환 안 함으로 대역폭 절약
                query_filter=flt,
                search_params=qm.SearchParams(
                    hnsw_ef=ef_search,
                    exact=False,
                ),
            ).points
            return res

        try:
            points = _retry_qdrant_call(_search)
        except Exception:
            return []

        # 결과 변환
        return [
            RetrievedPoint(
                id=str(p.id),
                score=float(p.score),
                text=str(p.payload.get("text", "")) if p.payload else "",
                metadata=p.payload or {},
            )
            for p in points
        ]

    def search_sparse(
        self,
        query_text: str,
        *,
        top_k: int = 20,
        flt: Optional[qm.Filter] = None,
    ) -> list[RetrievedPoint]:
        if not self._recover_client() or not self.use_sparse:
            return []

        ef_search = min(settings.ef_search_cap, max(64, top_k * 4 + 16))

        try:
            sp = _to_sparse(query_text)
            res = self._client.query_points(
                collection_name=self.collection,
                query=sp,
                using="sparse",
                limit=top_k,
                with_payload=True,
                with_vectors=False,
                query_filter=flt,
                search_params=qm.SearchParams(
                    hnsw_ef=ef_search,
                ),
            ).points
        except Exception as exc:
            logger.warning("[vector_store] sparse 검색 실패 (dense-only fallback): %s", exc)
            return []

        return [
            RetrievedPoint(
                id=str(p.id),
                score=float(p.score),
                text=str(p.payload.get("text", "")) if p.payload else "",
                metadata=p.payload or {},
            )
            for p in res
        ]

    # ──────────────────────────────────────────────────────────────────────────
    # 쓰기 메서드
    # ──────────────────────────────────────────────────────────────────────────

    def upsert(
        self,
        *,
        ids: Sequence[str],
        dense_vecs: Sequence[Sequence[float]],
        texts: Sequence[str],
        metadatas: Sequence[dict],
        sparse_vecs: Sequence[qm.SparseVector] | None = None,
        extra_vecs: dict | None = None,
    ) -> None:
        """배치 업서트 - 단일 쿼리로 다중 문서 처리.

        extra_vecs: name -> list[vector] 형태의 추가 명명 벡터 (이중 저장용).
        """
        if not self._client:
            self._ensure_collection()
            if not self._client:
                raise RuntimeError("Qdrant 클라이언트가 초기화되지 않았습니다")
        else:
            self._ensure_collection()

        points = []
        for i, point_id in enumerate(ids):
            vector_dict = {"dense": list(dense_vecs[i])}
            if sparse_vecs:
                vector_dict["sparse"] = sparse_vecs[i]
            if extra_vecs:
                for name, vecs in extra_vecs.items():
                    vector_dict[name] = list(vecs[i])

            points.append(
                qm.PointStruct(
                    id=point_id,
                    vector=vector_dict,
                    payload={**metadatas[i], "text": texts[i]},
                )
            )

        _retry_qdrant_call(
            self._client.upsert,
            collection_name=self.collection,
            points=points,
        )

    def upsert_single(
        self,
        *,
        dense_vec: Sequence[float],
        text: str,
        metadata: dict,
        doc_id: str | None = None,
        sparse_vec: qm.SparseVector | None = None,
    ) -> str:
        """단일 문서 업서트."""
        point_id = doc_id or str(uuid.uuid4())
        vector_dict = {"dense": list(dense_vec)}
        if sparse_vec:
            vector_dict["sparse"] = sparse_vec

        if not self._client:
            self._ensure_collection()
            if not self._client:
                raise RuntimeError("Qdrant 클라이언트가 초기화되지 않았습니다")
        else:
            self._ensure_collection()

        _retry_qdrant_call(
            self._client.upsert,
            collection_name=self.collection,
            points=[
                qm.PointStruct(
                    id=point_id,
                    vector=vector_dict,
                    payload={**metadata, "text": text},
                ),
            ],
        )
        return point_id

    def delete(self, point_ids: Sequence[str]) -> None:
        """배치 삭제."""
        if not self._recover_client():
            return
        try:
            self._client.delete(
                collection_name=self.collection,
                points_selector=qm.PointIdsList(points=list(point_ids)),
            )
        except Exception as e:
            logger.warning("[vector_store] 삭제 실패: %s", e)

    def delete_where(self, flt: qm.Filter) -> None:
        if not self._recover_client():
            return
        try:
            _retry_qdrant_call(
                self._client.delete,
                collection_name=self.collection,
                points_selector=qm.FilterSelector(filter=flt),
            )
        except Exception as e:
            logger.warning("[vector_store] 조건 삭제 실패: %s", e)

    def delete_collection(self) -> None:
        """컬렉션 삭제 - 주의: 복구 불가."""
        if not self._recover_client():
            return
        try:
            self._client.delete_collection(self.collection)
            with _ensured_lock:
                _ensured_collections.discard(self.collection)
        except Exception as e:
            logger.warning("[vector_store] 컬렉션 삭제 실패: %s", e)

    def count(self) -> int:
        """전체 포인트 수."""
        if not self._recover_client():
            return 0
        try:
            return self._client.count(collection_name=self.collection).count
        except Exception:
            return 0

    def get(self, point_id: str) -> RetrievedPoint | None:
        """단일 포인트 조회."""
        if not self._recover_client():
            return None
        try:
            points = self._client.retrieve(
                collection_name=self.collection,
                ids=[point_id],
                with_payload=True,
                with_vectors=False,
            )
            if not points:
                return None
            p = points[0]
            return RetrievedPoint(
                id=str(p.id),
                score=1.0,
                text=str(p.payload.get("text", "")) if p.payload else "",
                metadata=p.payload or {},
            )
        except Exception:
            return None
