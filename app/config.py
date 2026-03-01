import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path


# ─── Base Directory ──────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent  # LexiGraph/
APP_DIR = BASE_DIR / "app"
CONFIG_PATH = APP_DIR / "config.json"


# ─── Dataclasses ─────────────────────────────────────────────────
@dataclass
class Neo4jConfig:
    uri: str
    username: str
    password: str
    database: str


@dataclass
class QdrantConfig:
    host: str
    port: int
    grpc_port: int
    collection_name: str



@dataclass
class MCPConfig:
    host: str
    qdrant_port: int
    neo4j_port: int

@dataclass
class LLMConfig:
    base_url: str
    api_key: str
    model_id: str

# ─── Config Loader ───────────────────────────────────────────────
def load_config() -> dict:
    """config.json dosyasını okur ve dict olarak döner."""
    if not CONFIG_PATH.exists():
        print(f"❌ Hata: {CONFIG_PATH} bulunamadı! Lütfen dosyayı oluşturun.")
        sys.exit(1)
    
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"❌ config.json format hatası: {e}")
        sys.exit(1)


class Secrets:
    config = load_config()
    neo4j_config = Neo4jConfig(**config["neo4j"])
    qdrant_config = QdrantConfig(**config["qdrant"])
    mcp_config = MCPConfig(**config.get("mcp", {}))
    llm_config = LLMConfig(**config.get("llm", {}))



secrets = Secrets()


if __name__ == "__main__":
    print(BASE_DIR)
    print(APP_DIR)
    print(secrets.neo4j_config)
    print(secrets.qdrant_config)
    print(secrets.mcp_config)
    print(secrets.llm_config)