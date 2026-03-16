"""
agno_agent.py
─────────────
LexiGraph Legal Assistant — Agno Agent implementation.

Two MCP tool servers (Neo4j + Qdrant) are connected via Streamable HTTP.
The agent uses these tools to answer legal contract questions by
cross-referencing graph relationships and semantic text search.
"""

import asyncio
from typing import Optional

from agno.agent import Agent
from agno.models.openai import OpenAIChat
from agno.db.sqlite import SqliteDb
from agno.tools.mcp import MCPTools

from app.config import APP_DIR, secrets
from app.agent.agent_prompt import system_prompt


# ─── Storage ──────────────────────────────────────────────────────────────────

STORAGE_DIR = APP_DIR / "storage"
STORAGE_DIR.mkdir(parents=True, exist_ok=True)
STORAGE_DB = STORAGE_DIR / "agent.db"


# ─── Agent Factory ────────────────────────────────────────────────────────────

def _build_mcp_tools() -> list[MCPTools]:
    """MCP tool server bağlantılarını oluşturur."""
    qdrant_mcp = MCPTools(
        transport="streamable-http",
        url=f"http://{secrets.mcp_config.host}:{secrets.mcp_config.qdrant_port}/mcp",
    )
    neo4j_mcp = MCPTools(
        transport="streamable-http",
        url=f"http://{secrets.mcp_config.host}:{secrets.mcp_config.neo4j_port}/mcp",
    )
    return [qdrant_mcp, neo4j_mcp]


def _build_model() -> OpenAIChat:
    """LLM modelini yapılandırır."""
    return OpenAIChat(
        id=secrets.llm_config.model_id,
        base_url=secrets.llm_config.base_url,
        api_key=secrets.llm_config.api_key,
    )


def create_agent(
    user_id: str = "default",
    session_id: Optional[str] = None,
) -> Agent:
    """
    Yeni bir LexiGraph Legal Assistant agent'ı oluşturur.

    Args:
        user_id    : Kullanıcı kimliği (memory yönetimi için)
        session_id : Oturum kimliği (sohbet geçmişi için, None ise yeni oturum)

    Returns:
        Yapılandırılmış Agent nesnesi
    """
    return Agent(
        session_id=session_id,
        user_id=user_id,
        name="LexiGraph Legal Assistant",
        model=_build_model(),
        instructions=system_prompt,
        tools=_build_mcp_tools(),
        db=SqliteDb(db_file=STORAGE_DB),
        update_memory_on_run=True,
        add_history_to_context=True,
        reasoning=False,
    )


# ─── Runner Helpers ───────────────────────────────────────────────────────────

async def ask(
    query: str,
    user_id: str = "default",
    session_id: Optional[str] = None,
    stream: bool = True,
) -> None:
    """
    Tek bir sorgu gönderir ve yanıtı terminale yazdırır.
    Test/debug amaçlı kullanılır.
    """
    agent = create_agent(user_id=user_id, session_id=session_id)
    await agent.aprint_response(
        query,
        stream=stream,
        markdown=True,
        show_full_reasoning=True,
    )


# ─── Standalone Entry ────────────────────────────────────────────────────────

if __name__ == "__main__":
    asyncio.run(
        ask("Veritabanında kaç sözleşme var? Neo4j istatistiklerini göster.")
    )
