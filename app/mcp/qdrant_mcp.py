
import sys
from pathlib import Path
from fastmcp import FastMCP
from app.services.embedding_service import get_embedding_service
from app.services.qdrant_service import get_qdrant_service

# ─── Servisleri Önden Yükle (Eager Loading) ──────────────────────────────────
# Sunucu başlar başlamaz model RAM'e yüklenir ve bağlantılar kurulur.
print("🚀 Servisler hazırlanıyor (Model yükleniyor...)...")
_embedder = get_embedding_service()
_qdrant   = get_qdrant_service()
print("✅ Servisler hazır.")

# ─── MCP Sunucusu ─────────────────────────────────────────────────────────────

mcp = FastMCP(
    name="LexiGraph Qdrant",
    instructions="Hukuki sözleşme veritabanında anlamsal arama yapan araçları sağlar."
)

# ─── Tools ────────────────────────────────────────────────────────────────────

@mcp.tool(
    description=(
        "Sözleşme veritabanında anlamsal (semantic) arama yapar. "
        "Sorguyu embedding'e çevirir ve en alakalı metin parçalarını döner. "
        "Sonuç: score, contract_name, chunk_index, text."
    )
)
def search(query: str, limit: int = 10) -> list[dict]:
    """
    Args:
        query : Aranacak doğal dil sorgusu
        limit : Sonuç sayısı (max 50)
    """
    vector = _embedder.embed(query)
    return _qdrant.search(query_vector=vector, limit=min(limit, 50))



@mcp.tool(
    description=(
        "Belirli bir sözleşme içinde anlamsal (semantic) arama yapar. "
        "Sorguyu embedding'e çevirir ve o sözleşmeye ait en alakalı metin parçalarını döner. "
        "Sonuç: score, contract_name, chunk_index, text."
    )
)
def search_on_spesific_contract(contract_name: str, query: str, limit: int = 10) -> list[dict]:
    """
    Args:
        contract_name : Veritabanındaki sözleşme adı
        query : Aranacak doğal dil sorgusu
        limit : Sonuç sayısı (max 50)
    """
    vector = _embedder.embed(query)
    return _qdrant.search_on_spesific_contract(contract_name, vector, limit=min(limit, 50))




@mcp.tool(
    description=(
        "Belirli bir sözleşmenin chunk aralığını (sayfa/bölüm gibi) sıralı döner. "
        "Sonuç: contract_name, chunk_index, text."
    )
)
def get_chunks_of_contract(
    contract_name: str,
    start_index: int,
    end_index: int,
) -> list[dict]:
    """
    Args:
        contract_name : Veritabanındaki sözleşme adı
        start_index   : Başlangıç indexi
        end_index     : Bitiş indexi
    """
    return _qdrant.get_chunks_of_contract(contract_name, start_index, end_index)


# ─── Entry point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from app.config import secrets
    mcp.run(transport="streamable-http", host=secrets.mcp_config.host, port=secrets.mcp_config.qdrant_port)
    # 1- npx @modelcontextprotocol/inspector
    # 2- python -m app.mcp.qdrant_mcp
    # 3- Transport Type -> Streamable HTTP
    # 4- SET URL: http://127.0.0.1:8080/mcp
