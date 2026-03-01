import logging
import time
from typing import Any, Optional

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
    Range,
)

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_RETRY_DELAY = 2.0  # saniye


def _retry(fn):
    """Bağlantı hatalarında otomatik tekrar dene."""
    def wrapper(self, *args, **kwargs):
        last_err = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                return fn(self, *args, **kwargs)
            except Exception as e:
                last_err = e
                logger.warning(
                    f"Qdrant hata (deneme {attempt}/{_MAX_RETRIES}): {e}"
                )
                if attempt < _MAX_RETRIES:
                    time.sleep(_RETRY_DELAY)
                    self._reconnect()
        raise last_err
    return wrapper


class QdrantService:
    """
    Qdrant bağlantısını yönetir.
    Bağlantı kopması durumunda otomatik yeniden bağlanır.
    """

    def __init__(self, host: str, port: int, grpc_port: int, collection_name: str):
        self._host            = host
        self._port            = port
        self._grpc_port       = grpc_port
        self.collection_name  = collection_name
        self._connect()

    def _connect(self) -> None:
        self.client = QdrantClient(
            host=self._host,
            port=self._port,
            grpc_port=self._grpc_port,
            prefer_grpc=True,
        )

    def _reconnect(self) -> None:
        logger.info("Qdrant yeniden bağlanılıyor...")
        try:
            self._connect()
        except Exception as e:
            logger.error(f"Qdrant yeniden bağlantı başarısız: {e}")

    # ─── Collection Yönetimi ─────────────────────────────────────────────────

    @_retry
    def create_collection(self, vector_size: int, recreate: bool = False) -> None:
        """
        Collection oluşturur.
        recreate=True → varsa siler, yeniden oluşturur.
        """
        existing = [c.name for c in self.client.get_collections().collections]

        if self.collection_name in existing:
            if recreate:
                self.client.delete_collection(self.collection_name)
                print(f"🗑️  '{self.collection_name}' silindi.")
            else:
                print(f"ℹ️  '{self.collection_name}' zaten mevcut, atlandı.")
                return

        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
        )
        print(f"✅ '{self.collection_name}' oluşturuldu. (vector_size={vector_size})")

    # ─── Veri Ekleme ─────────────────────────────────────────────────────────

    @_retry
    def insert(self, point_id: str, vector: list[float], payload: dict) -> None:
        """Tek bir vektör nokta ekler."""
        self.client.upsert(
            collection_name=self.collection_name,
            points=[PointStruct(id=point_id, vector=vector, payload=payload)],
        )

    @_retry
    def insert_batch(self, points: list[dict]) -> None:
        """
        Toplu vektör ekler.
        points → [{"id": str, "vector": [...], "payload": {...}}, ...]
        """
        structs = [
            PointStruct(id=p["id"], vector=p["vector"], payload=p["payload"])
            for p in points
        ]
        self.client.upsert(collection_name=self.collection_name, points=structs)

    # ─── Arama ───────────────────────────────────────────────────────────────

    @_retry
    def search(
        self,
        query_vector: list[float],
        limit: int = 10,
        contract_name_filter: Optional[str] = None,
    ) -> list[dict]:
        """
        Vektör benzerlik araması yapar.
        contract_name_filter → sadece belirli sözleşme içinde arar.
        """
        qdrant_filter = None
        if contract_name_filter:
            qdrant_filter = Filter(
                must=[FieldCondition(key="contract_name", match=MatchValue(value=contract_name_filter))]
            )

        response = self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            limit=limit,
            query_filter=qdrant_filter,
            with_payload=True,
        )

        return [
            {
                "score":         r.score,
                "contract_name": r.payload.get("contract_name"),
                "chunk_index":   r.payload.get("chunk_index"),
                "text":          r.payload.get("text"),
            }
            for r in response.points
        ]

    @_retry
    def search_on_spesific_contract(
        self,
        contract_name: str,
        query_vector: list[float],
        limit: int = 10,
    ) -> list[dict]:
        """
        Belirli bir sözleşme içinde vektör benzerlik araması yapar.
        """
        qdrant_filter = Filter(
            must=[FieldCondition(key="contract_name", match=MatchValue(value=contract_name))]
        )

        response = self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            limit=limit,
            query_filter=qdrant_filter,
            with_payload=True,
        )

        return [
            {
                "score":         r.score,
                "contract_name": r.payload.get("contract_name"),
                "chunk_index":   r.payload.get("chunk_index"),
                "text":          r.payload.get("text"),
            }
            for r in response.points
        ]

    @_retry
    def get_chunks_of_contract(
        self,
        contract_name: str,
        start_index: int,
        end_index: int,
    ) -> list[dict]:
        """
        Belirli bir sözleşmenin chunk_index aralığını sıralı döner.
        """
        if end_index < start_index:
            return []

        results, _ = self.client.scroll(
            collection_name=self.collection_name,
            scroll_filter=Filter(
                must=[
                    FieldCondition(key="contract_name", match=MatchValue(value=contract_name)),
                    FieldCondition(key="chunk_index",   range=Range(gte=start_index, lte=end_index)),
                ]
            ),
            limit=end_index - start_index + 1,
            with_payload=True,
            with_vectors=False,
        )

        chunks = [
            {
                "contract_name": r.payload.get("contract_name"),
                "chunk_index":   r.payload.get("chunk_index"),
                "text":          r.payload.get("text"),
            }
            for r in results
        ]
        return sorted(chunks, key=lambda x: x["chunk_index"])

    # ─── İstatistik ──────────────────────────────────────────────────────────

    @_retry
    def stats(self) -> dict:
        info = self.client.get_collection(self.collection_name)
        return {
            "collection":    self.collection_name,
            "total_vectors": info.points_count,
            "vector_size":   info.config.params.vectors.size,
        }


# ─── Singleton ────────────────────────────────────────────────────────────────

_instance: Optional[QdrantService] = None


def get_qdrant_service() -> QdrantService:
    global _instance
    if _instance is None:
        from app.config import secrets
        _instance = QdrantService(
            host=secrets.qdrant_config.host,
            port=secrets.qdrant_config.port,
            grpc_port=secrets.qdrant_config.grpc_port,
            collection_name=secrets.qdrant_config.collection_name,
        )
    return _instance
