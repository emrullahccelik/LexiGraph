"""
neo4j_mcp.py
────────────
Neo4j graph veritabanı üzerinde şema keşfi, Cypher sorguları
ve sözleşme aramaları için MCP araçları sağlar.

Tüm Cypher sorguları neo4j_service katmanında tutulur;
bu dosya yalnızca MCP tool tanımlarını içerir.
"""

import sys
from pathlib import Path
from typing import Any, Optional
from fastmcp import FastMCP
from app.services.neo4j_service import get_neo4j_service

# ─── Servis Bağlantısı ───────────────────────────────────────────────────────

print("🚀 Neo4j servisi hazırlanıyor...")
_neo4j = get_neo4j_service()
print("✅ Neo4j bağlantısı hazır.")

# ─── MCP Sunucusu ─────────────────────────────────────────────────────────────

mcp = FastMCP(
    name="LexiGraph Neo4j",
    instructions=(
        "Hukuki sözleşmelerin graph veritabanı (Neo4j) üzerinde "
        "şema keşfi, Cypher sorguları ve yapısal arama yapan araçları sağlar."
    ),
)


# ═══════════════════════════════════════════════════════════════════════════════
# 1 — ŞEMA KEŞİF ARAÇLARI
# ═══════════════════════════════════════════════════════════════════════════════


@mcp.tool(
    description=(
        "Neo4j graph'ının tam şemasını döner: "
        "tüm node label'ları, relationship type'ları ve property key'leri. "
        "Graph yapısını anlamak için ilk çağrılması gereken araçtır."
    )
)
def get_schema() -> dict:
    """Graph'taki label'lar, ilişki türleri ve property'ler."""
    return _neo4j.get_schema()


@mcp.tool(
    description=(
        "Graph'taki tüm node label'larını ve her birinin node sayısını döner. "
        "Hangi varlık türlerinin var olduğunu anlamak için kullanılır."
    )
)
def get_node_labels() -> list[dict]:
    """Her label ve karşılık gelen node sayısı."""
    return _neo4j.get_node_labels()


@mcp.tool(
    description=(
        "Belirli bir node label'ı için property şemasını döner: "
        "hangi alanlar mevcut ve kaç node'da dolu. "
        "Cypher sorgusu yazmadan önce alan adlarını öğrenmek için kullanılır."
    )
)
def get_node_properties(label: str) -> list[dict]:
    """
    Args:
        label: Şeması istenen node label'ı (örn. 'Contract', 'Party')
    """
    return _neo4j.get_node_properties(label)


# ═══════════════════════════════════════════════════════════════════════════════
# 2 — GENEL CYPHER SORGU ARACI
# ═══════════════════════════════════════════════════════════════════════════════


@mcp.tool(
    description=(
        "Verilen Cypher sorgusunu Neo4j üzerinde çalıştırır ve sonuçları döner. "
        "⚠️ Sadece READ sorguları çalıştırılır (MATCH, RETURN, CALL). "
        "Yazma işlemleri (CREATE, MERGE, DELETE, SET) reddedilir."
    )
)
def execute_cypher(query: str, params: Optional[dict[str, Any]] = None) -> list[dict]:
    """
    Args:
        query  : Çalıştırılacak Cypher sorgusu (salt-okunur)
        params : Sorgu parametreleri (opsiyonel), örn. {"name": "Acme"}
    """
    return _neo4j.safe_execute_read(query, **(params or {}))


# ═══════════════════════════════════════════════════════════════════════════════
# 3 — İSTATİSTİK
# ═══════════════════════════════════════════════════════════════════════════════


@mcp.tool(
    description=(
        "Graph genel istatistiklerini döner: "
        "toplam sözleşme, taraf, sözleşme türü ve yargı alanı sayıları."
    )
)
def get_stats() -> dict:
    """Graph istatistikleri (Contract, Party, ContractType, GoverningLaw sayıları)."""
    return _neo4j.stats()


# ═══════════════════════════════════════════════════════════════════════════════
# 4 — SÖZLEŞME ARAMA ARAÇLARI
# ═══════════════════════════════════════════════════════════════════════════════


@mcp.tool(
    description=(
        "Taraf (şirket/kişi) adına göre sözleşme arar. "
        "Kısmi eşleşme destekler (case-insensitive). "
        "Sonuç: contract_name, agreement_date, party."
    )
)
def find_contracts_by_party(party_name: str) -> list[dict]:
    """
    Args:
        party_name: Aranacak taraf adı (örn. 'Acme', 'Google')
    """
    return _neo4j.find_contracts_by_party(party_name)


@mcp.tool(
    description=(
        "Sözleşme türüne göre arar (örn. 'License Agreement', 'Service Agreement'). "
        "Kısmi eşleşme destekler. "
        "Sonuç: contract_name, contract_type, expiration_date."
    )
)
def find_contracts_by_type(contract_type: str) -> list[dict]:
    """
    Args:
        contract_type: Sözleşme türü (örn. 'License', 'Service')
    """
    return _neo4j.find_contracts_by_type(contract_type)


@mcp.tool(
    description=(
        "Belirli bir sözleşmenin tüm detaylarını döner: "
        "sözleşme bilgileri, türü, yargı alanı ve tüm taraflar. "
        "Qdrant'tan gelen sonuçları zenginleştirmek için idealdir."
    )
)
def get_contract_detail(contract_name: str) -> Optional[dict]:
    """
    Args:
        contract_name: Sözleşme adı (tam eşleşme)
    """
    return _neo4j.get_contract(contract_name)


@mcp.tool(
    description=(
        "Belirli bir node'un (sözleşme, taraf, vb.) tüm ilişkilerini döner. "
        "Node'u label ve property_key/property_value ile tanımlarsınız. "
        "Sonuçta bağlı node'lar ve ilişki türleri listelenir."
    )
)
def get_relationships(
    label: str,
    property_key: str,
    property_value: str,
) -> list[dict]:
    """
    Args:
        label          : Node label'ı (örn. 'Contract', 'Party')
        property_key   : Aramada kullanılacak property (örn. 'contract_name', 'name')
        property_value : Property değeri (örn. 'DISTRIBUTOR AGREEMENT')
    """
    return _neo4j.get_relationships(label, property_key, property_value)


# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    from app.config import secrets
    mcp.run(transport="streamable-http", host=secrets.mcp_config.host, port=secrets.mcp_config.neo4j_port)
    # 1- npx @modelcontextprotocol/inspector
    # 2- python -m app.mcp.neo4j_mcp
    # 3- Transport Type -> Streamable HTTP
    # 4- SET URL: http://127.0.0.1:8081/mcp
