import logging
import time
from typing import Any, Optional

from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable, SessionExpired

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_RETRY_DELAY = 2.0  # saniye


def _retry(fn):
    """Neo4j bağlantı hatalarında otomatik tekrar dene."""
    def wrapper(self, *args, **kwargs):
        last_err = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                return fn(self, *args, **kwargs)
            except (ServiceUnavailable, SessionExpired) as e:
                last_err = e
                logger.warning(
                    f"Neo4j hata (deneme {attempt}/{_MAX_RETRIES}): {e}"
                )
                if attempt < _MAX_RETRIES:
                    time.sleep(_RETRY_DELAY)
                    self._reconnect()
        raise last_err
    return wrapper


class Neo4jService:
    """
    Neo4j bağlantısını yönetir.
    Bağlantı kopması durumunda otomatik yeniden bağlanır.
    """

    def __init__(self, uri: str, username: str, password: str, database: str = "neo4j"):
        self._uri      = uri
        self._username = username
        self._password = password
        self._database = database
        self._connect()

    def _connect(self) -> None:
        self._driver = GraphDatabase.driver(
            self._uri,
            auth=(self._username, self._password),
        )

    def _reconnect(self) -> None:
        logger.info("Neo4j yeniden bağlanılıyor...")
        try:
            self._driver.close()
        except Exception:
            pass
        try:
            self._connect()
        except Exception as e:
            logger.error(f"Neo4j yeniden bağlantı başarısız: {e}")

    def close(self):
        self._driver.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    # ─── Temel Sorgu Metodları ───────────────────────────────────────────────

    @_retry
    def execute_write(self, query: str, **params) -> None:
        """Yazma sorgusu çalıştırır (INSERT / MERGE / CREATE)."""
        with self._driver.session(database=self._database) as session:
            session.run(query, **params)

    @_retry
    def execute_read(self, query: str, **params) -> list[dict]:
        """Okuma sorgusu çalıştırır ve sonuçları dict listesi olarak döner."""
        with self._driver.session(database=self._database) as session:
            result = session.run(query, **params)
            return [record.data() for record in result]

    @_retry
    def execute_write_batch(self, fn, *args, **kwargs) -> None:
        """Tek bir transaction içinde batch yazma yapar."""
        with self._driver.session(database=self._database) as session:
            session.execute_write(fn, *args, **kwargs)

    # ─── Arama Metodları ─────────────────────────────────────────────────────

    def find_contracts_by_party(self, party_name: str) -> list[dict]:
        """Belirtilen tarafa ait sözleşmeleri döner."""
        query = """
        MATCH (c:Contract)-[:SIGNED_BY]->(p:Party)
        WHERE toLower(p.name) CONTAINS toLower($name)
        RETURN c.contract_name AS contract_name,
               c.agreement_date AS agreement_date, p.name AS party
        ORDER BY c.agreement_date
        """
        return self.execute_read(query, name=party_name)

    def find_contracts_by_type(self, contract_type: str) -> list[dict]:
        """Belirtilen türdeki sözleşmeleri döner."""
        query = """
        MATCH (c:Contract)-[:IS_TYPE]->(t:ContractType)
        WHERE toLower(t.name) CONTAINS toLower($type)
        RETURN c.contract_name AS contract_name,
               t.name AS contract_type, c.expiration_date AS expiration_date
        ORDER BY c.agreement_date
        """
        return self.execute_read(query, type=contract_type)

    def find_contracts_by_jurisdiction(self, jurisdiction: str) -> list[dict]:
        """Belirtilen hukuk alanındaki sözleşmeleri döner."""
        query = """
        MATCH (c:Contract)-[:GOVERNED_BY]->(g:GoverningLaw)
        WHERE toLower(g.jurisdiction) CONTAINS toLower($jurisdiction)
        RETURN c.contract_name AS contract_name,
               g.jurisdiction AS jurisdiction
        ORDER BY c.agreement_date
        """
        return self.execute_read(query, jurisdiction=jurisdiction)

    def search_contracts(
        self,
        party: Optional[str] = None,
        contract_type: Optional[str] = None,
        jurisdiction: Optional[str] = None,
        filters: Optional[dict[str, Any]] = None,
    ) -> list[dict]:
        """
        Esnek sözleşme arama.
        filters → {'license_grant': True, 'non_compete': True} gibi boolean filtreler.
        """
        conditions = ["1=1"]
        params: dict[str, Any] = {}

        if party:
            conditions.append("EXISTS { MATCH (c)-[:SIGNED_BY]->(p:Party) WHERE toLower(p.name) CONTAINS toLower($party) }")
            params["party"] = party

        if contract_type:
            conditions.append("EXISTS { MATCH (c)-[:IS_TYPE]->(t:ContractType) WHERE toLower(t.name) CONTAINS toLower($contract_type) }")
            params["contract_type"] = contract_type

        if jurisdiction:
            conditions.append("EXISTS { MATCH (c)-[:GOVERNED_BY]->(g:GoverningLaw) WHERE toLower(g.jurisdiction) CONTAINS toLower($jurisdiction) }")
            params["jurisdiction"] = jurisdiction

        if filters:
            for field, value in filters.items():
                conditions.append(f"c.{field} = ${field}")
                params[field] = value

        where_clause = " AND ".join(conditions)
        query = f"""
        MATCH (c:Contract)
        WHERE {where_clause}
        RETURN c.contract_name AS contract_name,
               c.agreement_date AS agreement_date, c.expiration_date AS expiration_date
        ORDER BY c.agreement_date
        """
        return self.execute_read(query, **params)

    # ─── İstatistik ──────────────────────────────────────────────────────────

    def stats(self) -> dict:
        """Graph istatistiklerini döner."""
        queries = {
            "contracts":      "MATCH (c:Contract) RETURN count(c) AS n",
            "parties":        "MATCH (p:Party) RETURN count(p) AS n",
            "contract_types": "MATCH (t:ContractType) RETURN count(t) AS n",
            "jurisdictions":  "MATCH (g:GoverningLaw) RETURN count(g) AS n",
        }
        return {key: self.execute_read(q)[0]["n"] for key, q in queries.items()}

    def get_contract(self, contract_name: str) -> Optional[dict]:
        """contract_name'e göre tek sözleşme döner (Qdrant sonuçlarını zenginleştirmek için)."""
        query = """
        MATCH (c:Contract {contract_name: $contract_name})
        OPTIONAL MATCH (c)-[:IS_TYPE]->(t:ContractType)
        OPTIONAL MATCH (c)-[:GOVERNED_BY]->(g:GoverningLaw)
        OPTIONAL MATCH (c)-[:SIGNED_BY]->(p:Party)
        RETURN c,
               t.name AS contract_type,
               g.jurisdiction AS jurisdiction,
               collect(p.name) AS parties
        """
        results = self.execute_read(query, contract_name=contract_name)
        return results[0] if results else None

    # ─── Şema Keşif ──────────────────────────────────────────────────────────

    def get_schema(self) -> dict:
        """Graph'taki tüm label'lar, ilişki türleri ve property key'lerini döner."""
        labels = self.execute_read(
            "CALL db.labels() YIELD label RETURN collect(label) AS labels"
        )
        rel_types = self.execute_read(
            "CALL db.relationshipTypes() YIELD relationshipType "
            "RETURN collect(relationshipType) AS types"
        )
        props = self.execute_read(
            "CALL db.propertyKeys() YIELD propertyKey "
            "RETURN collect(propertyKey) AS keys"
        )
        return {
            "node_labels": labels[0]["labels"] if labels else [],
            "relationship_types": rel_types[0]["types"] if rel_types else [],
            "property_keys": props[0]["keys"] if props else [],
        }

    def get_node_labels(self) -> list[dict]:
        """Her label ve karşılık gelen node sayısını döner."""
        return self.execute_read(
            """
            CALL db.labels() YIELD label
            CALL apoc.cypher.run(
                'MATCH (n:`' + label + '`) RETURN count(n) AS count', {}
            ) YIELD value
            RETURN label, value.count AS count
            ORDER BY count DESC
            """
        )

    def get_node_properties(self, label: str) -> list[dict]:
        """Belirli bir label için property şemasını döner."""
        return self.execute_read(
            """
            MATCH (n)
            WHERE $label IN labels(n)
            UNWIND keys(n) AS key
            RETURN key AS property,
                   count(*) AS nodes_with_value,
                   collect(DISTINCT substring(toString(n[key]), 0, 60))[0..3]
                       AS sample_values
            ORDER BY nodes_with_value DESC
            """,
            label=label,
        )

    def get_relationships(
        self, label: str, property_key: str, property_value: str
    ) -> list[dict]:
        """Belirli bir node'un tüm ilişkilerini döner."""
        return self.execute_read(
            """
            MATCH (n)-[r]-(m)
            WHERE $label IN labels(n) AND n[$property_key] = $property_value
            RETURN type(r) AS relationship_type,
                   labels(m) AS target_labels,
                   properties(m) AS target_properties
            ORDER BY relationship_type
            """,
            label=label,
            property_key=property_key,
            property_value=property_value,
        )

    # ─── Güvenli Cypher Çalıştırma ───────────────────────────────────────────

    _BLOCKED_TOKENS = {"CREATE", "MERGE", "DELETE", "DETACH", "SET", "REMOVE", "DROP"}

    def safe_execute_read(self, query: str, **params) -> list[dict]:
        """Yazma komutlarını engelleyerek salt-okunur Cypher sorgusu çalıştırır."""
        tokens = query.upper().split()
        for token in tokens:
            if token in self._BLOCKED_TOKENS:
                raise ValueError(
                    f"Yazma komutu '{token}' izin verilmiyor. "
                    "Bu metod sadece salt-okunur (READ) sorguları destekler."
                )
        return self.execute_read(query, **params)


# ─── Singleton ────────────────────────────────────────────────────────────────

_instance: Optional[Neo4jService] = None


def get_neo4j_service() -> Neo4jService:
    global _instance
    if _instance is None:
        from app.config import secrets
        _instance = Neo4jService(
            uri=secrets.neo4j_config.uri,
            username=secrets.neo4j_config.username,
            password=secrets.neo4j_config.password,
            database=secrets.neo4j_config.database,
        )
    return _instance