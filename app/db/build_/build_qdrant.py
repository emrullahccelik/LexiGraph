"""
build_qdrant.py
---------------
TXT sözleşmelerini okur, RecursiveCharacterTextSplitter ile chunk'lara böler,
embed eder ve Qdrant'a yükler.

Payload (her chunk için):
    contract_name : Neo4j Contract.contract_name ile eşleşen bağ anahtarı
    chunk_index   : sözleşme içindeki chunk sırası (0'dan başlar)
    text          : chunk metni
"""

import csv
import sys
import uuid
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # LexiGraph/ root
from app.config import secrets, APP_DIR
from app.services.embedding_service import EmbeddingService
from app.services.qdrant_service import QdrantService

# ─── Ayarlar ─────────────────────────────────────────────────────────────────

TXT_DIR:       Path = APP_DIR / "db" / "data" / "full_contract_txt"
CSV_PATH:      Path = APP_DIR / "db" / "data" / "master_clauses.csv"
CHUNK_SIZE:    int  = 512
CHUNK_OVERLAP: int  = 64
EMBED_BATCH:   int  = 32
INSERT_BATCH:  int  = 100


# ─── Yardımcılar ─────────────────────────────────────────────────────────────

def build_filename_to_contract_name(csv_path: Path) -> dict[str, str]:
    """
    CSV'den filename_stem → contract_name eşleşmesi oluşturur.
    Örnek: "2ThemartComInc_..._Co-Branding Agreement" → "CO-BRANDING AND ADVERTISING AGREEMENT"
    """
    mapping: dict[str, str] = {}
    with open(csv_path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            raw = row.get("Filename", "").strip()
            name = (row.get("Document Name-Answer") or row.get("Document Name", "")).strip()
            if raw and name:
                stem = raw.removesuffix(".pdf").removesuffix(".txt")
                mapping[stem] = name
    return mapping


def _make_point_id(contract_name: str, chunk_index: int) -> str:
    """Deterministik UUID — aynı veriyi iki kez yüklersen duplicate olmaz."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{contract_name}::{chunk_index}"))


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 55)
    print("  LexiGraph — Qdrant Build Script")
    print("=" * 55)
    print(f"📌 Host       : {secrets.qdrant_config.host}:{secrets.qdrant_config.port}")
    print(f"📌 Collection : {secrets.qdrant_config.collection_name}")
    print(f"📌 TXT Dir    : {TXT_DIR}")
    print(f"📌 Chunk size : {CHUNK_SIZE} karakter (overlap={CHUNK_OVERLAP})\n")

    if not TXT_DIR.exists():
        print(f"❌ TXT klasörü bulunamadı: {TXT_DIR}")
        sys.exit(1)

    # ── CSV'den filename → contract_name mapping ─────────────────────────────
    print("📄 CSV okunuyor (contract_name mapping)...")
    name_map = build_filename_to_contract_name(CSV_PATH)
    print(f"   {len(name_map)} sözleşme eşleştirildi.\n")

    # ── Servisleri başlat ────────────────────────────────────────────────────
    embedder = EmbeddingService()
    qdrant   = QdrantService(
        host=secrets.qdrant_config.host,
        port=secrets.qdrant_config.port,
        grpc_port=secrets.qdrant_config.grpc_port,
        collection_name=secrets.qdrant_config.collection_name,
    )
    qdrant.create_collection(vector_size=EmbeddingService.VECTOR_SIZE, recreate=False)

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    # ── TXT dosyalarını işle ─────────────────────────────────────────────────
    txt_files = sorted(TXT_DIR.glob("*.txt"))
    print(f"📂 {len(txt_files)} TXT dosyası bulundu.\n")
    print("📥 Chunk'lanıp embed ediliyor...\n")

    total_chunks = 0
    pending_chunks: list[dict] = []

    for file_idx, path in enumerate(txt_files, start=1):
        stem          = path.stem
        contract_name = name_map.get(stem, stem)  # CSV'de yoksa stem'i kullan

        text = path.read_text(encoding="utf-8", errors="ignore").strip()
        if not text:
            continue

        chunks = splitter.split_text(text)

        for i, chunk in enumerate(chunks):
            pending_chunks.append({
                "contract_name": contract_name,
                "chunk_index":   i,
                "text":          chunk,
            })

        # Embed batch dolunca yaz
        while len(pending_chunks) >= EMBED_BATCH:
            batch   = pending_chunks[:EMBED_BATCH]
            pending_chunks = pending_chunks[EMBED_BATCH:]
            _embed_and_insert(batch, embedder, qdrant)
            total_chunks += len(batch)

        print(f"  ✔ [{file_idx}/{len(txt_files)}] {path.name}  ({len(chunks)} chunk)")

    # Kalan chunk'ları işle
    if pending_chunks:
        _embed_and_insert(pending_chunks, embedder, qdrant)
        total_chunks += len(pending_chunks)

    # ── İstatistik ───────────────────────────────────────────────────────────
    print(f"\n🎉 Toplam {total_chunks} chunk yüklendi.")
    print("\n📊 Qdrant İstatistikleri:")
    for key, val in qdrant.stats().items():
        print(f"   {key:<20}: {val}")

    print("\n✅ Build tamamlandı!")


def _embed_and_insert(batch: list[dict], embedder: EmbeddingService, qdrant: QdrantService) -> None:
    texts   = [c["text"] for c in batch]
    vectors = embedder.embed_batch(texts)

    points = [
        {
            "id":     _make_point_id(c["contract_name"], c["chunk_index"]),
            "vector": vectors[j],
            "payload": {
                "contract_name": c["contract_name"],
                "chunk_index":   c["chunk_index"],
                "text":          c["text"],
            },
        }
        for j, c in enumerate(batch)
    ]

    for k in range(0, len(points), INSERT_BATCH):
        qdrant.insert_batch(points[k : k + INSERT_BATCH])


if __name__ == "__main__":
    main()
