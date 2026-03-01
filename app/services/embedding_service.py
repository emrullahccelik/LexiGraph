import logging
import os
from pathlib import Path

import torch
from sentence_transformers import SentenceTransformer

logging.getLogger("sentence_transformers").setLevel(logging.ERROR)
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

_APP_DIR  = Path(__file__).resolve().parents[1]
_CACHE_DIR = _APP_DIR / ".cache"
_CACHE_DIR.mkdir(exist_ok=True)
_DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


class EmbeddingService:
    """
    Metni embedding vektörüne dönüştürür.
    Model: all-MiniLM-L6-v2  (384 boyut, hızlı, hukuki metin için yeterli)
    Model app/.cache altına indirilir ve cache'lenir.
    GPU (CUDA) mevcutsa otomatik olarak ekran kartında çalışır.
    """

    MODEL_NAME  = "all-MiniLM-L6-v2"
    VECTOR_SIZE = 384

    def __init__(self, model_name: str = MODEL_NAME):
        print(f"🔧 Embedding modeli yükleniyor: {model_name}")
        print(f"   Cache  : {_CACHE_DIR}")
        print(f"   Device : {_DEVICE}" + (" (GPU ✅)" if _DEVICE == "cuda" else " (CPU)"))
        if _DEVICE == "cuda":
            print(f"   GPU    : {torch.cuda.get_device_name(0)}")

        self._model = SentenceTransformer(
            model_name,
            cache_folder=str(_CACHE_DIR),
            device=_DEVICE,
        )
        self._model.max_seq_length = 512
        print(f"   Max seq length : {self._model.max_seq_length}")
        print("✅ Model hazır.")

    def embed(self, text: str) -> list[float]:
        """Tek bir metni embedding'e çevirir."""
        return self._model.encode(
            text,
            show_progress_bar=False,
            convert_to_numpy=True,
        ).tolist()

    def embed_batch(self, texts: list[str], batch_size: int = 64) -> list[list[float]]:
        """Metin listesini toplu embedding'e çevirir."""
        vectors = self._model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return vectors.tolist()


# ─── Singleton ────────────────────────────────────────────────────────────────
# import eden herkes aynı model nesnesini kullanır (her seferinde yeniden yüklenmez)

_instance: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    global _instance
    if _instance is None:
        _instance = EmbeddingService()
    return _instance