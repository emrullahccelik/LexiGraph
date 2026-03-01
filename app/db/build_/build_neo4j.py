"""
build_neo4j.py
--------------
CSV'den Neo4j graph'ını oluşturur.

Birincil anahtar: doc_name (filename uzantısız)
  - Neo4j <-> Qdrant bağ alanı
  - title: CSV'deki "Document Name-Answer" (okunabilir sözleşme adı)
"""

import csv
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # LexiGraph/ root
from app.config import secrets, APP_DIR
from app.services.neo4j_service import Neo4jService

CSV_PATH: Path = APP_DIR / "db" / "data" / "master_clauses.csv"

# ─── Kolon Eşleşme Tabloları ─────────────────────────────────────────────────

DATE_FIELDS: dict[str, str] = {
    "Agreement Date-Answer":                      "agreement_date",
    "Effective Date-Answer":                      "effective_date",
    "Expiration Date-Answer":                     "expiration_date",
    "Renewal Term-Answer":                        "renewal_term",
    "Notice Period To Terminate Renewal- Answer": "notice_period",
    "Warranty Duration-Answer":                   "warranty_duration",
}

BOOL_FIELDS: dict[str, str] = {
    "Most Favored Nation-Answer":                  "most_favored_nation",
    "Competitive Restriction Exception-Answer":    "competitive_restriction_exception",
    "Non-Compete-Answer":                          "non_compete",
    "Exclusivity-Answer":                          "exclusivity",
    "No-Solicit Of Customers-Answer":              "no_solicit_customers",
    "No-Solicit Of Employees-Answer":              "no_solicit_employees",
    "Non-Disparagement-Answer":                    "non_disparagement",
    "Termination For Convenience-Answer":          "termination_for_convenience",
    "Rofr/Rofo/Rofn-Answer":                       "rofr_rofo_rofn",
    "Change Of Control-Answer":                    "change_of_control",
    "Anti-Assignment-Answer":                      "anti_assignment",
    "Revenue/Profit Sharing-Answer":               "revenue_profit_sharing",
    "Price Restrictions-Answer":                   "price_restrictions",
    "Minimum Commitment-Answer":                   "minimum_commitment",
    "Volume Restriction-Answer":                   "volume_restriction",
    "Ip Ownership Assignment-Answer":              "ip_ownership_assignment",
    "Joint Ip Ownership-Answer":                   "joint_ip_ownership",
    "License Grant-Answer":                        "license_grant",
    "Non-Transferable License-Answer":             "non_transferable_license",
    "Affiliate License-Licensor-Answer":           "affiliate_license_licensor",
    "Affiliate License-Licensee-Answer":           "affiliate_license_licensee",
    "Unlimited/All-You-Can-Eat-License-Answer":    "unlimited_license",
    "Irrevocable Or Perpetual License-Answer":     "irrevocable_perpetual_license",
    "Source Code Escrow-Answer":                   "source_code_escrow",
    "Post-Termination Services-Answer":            "post_termination_services",
    "Audit Rights-Answer":                         "audit_rights",
    "Uncapped Liability-Answer":                   "uncapped_liability",
    "Cap On Liability-Answer":                     "cap_on_liability",
    "Liquidated Damages-Answer":                   "liquidated_damages",
    "Insurance-Answer":                            "insurance",
    "Covenant Not To Sue-Answer":                  "covenant_not_to_sue",
    "Third Party Beneficiary-Answer":              "third_party_beneficiary",
}

KNOWN_CONTRACT_TYPES = [
    "Affiliate Agreement", "Agency Agreement", "Collaboration Agreement",
    "Co-Branding Agreement", "Consulting Agreement", "Development Agreement",
    "Distributor Agreement", "Endorsement Agreement", "Franchise Agreement",
    "Hosting Agreement", "IP Agreement", "Joint Venture Agreement",
    "License Agreement", "Maintenance Agreement", "Manufacturing Agreement",
    "Marketing Agreement", "Non-Compete Agreement", "Outsourcing Agreement",
    "Promotion Agreement", "Reseller Agreement", "Service Agreement",
    "Sponsorship Agreement", "Supply Agreement", "Strategic Alliance Agreement",
    "Transportation Agreement",
]


# ─── ContractLoader ───────────────────────────────────────────────────────────

class ContractLoader:

    def __init__(self, service: Neo4jService):
        self.service = service

    @staticmethod
    def _parse_bool(value: str) -> Optional[bool]:
        v = value.strip().lower()
        if v == "yes": return True
        if v == "no":  return False
        return None

    @staticmethod
    def _parse_str(value: str) -> Optional[str]:
        v = value.strip()
        return v if v else None

    @staticmethod
    def _parse_contract_type(raw_filename: str) -> str:
        fn = raw_filename.lower().replace("_", " ").replace("-", " ")
        for t in KNOWN_CONTRACT_TYPES:
            if t.lower().replace("-", " ") in fn:
                return t
        return "Other"

    def create_constraints(self) -> None:
        constraints = [
            "CREATE CONSTRAINT contract_name_unique IF NOT EXISTS FOR (c:Contract) REQUIRE c.contract_name IS UNIQUE",
            "CREATE CONSTRAINT party_name           IF NOT EXISTS FOR (p:Party) REQUIRE p.name IS UNIQUE",
            "CREATE CONSTRAINT gov_law              IF NOT EXISTS FOR (g:GoverningLaw) REQUIRE g.jurisdiction IS UNIQUE",
            "CREATE CONSTRAINT contract_type        IF NOT EXISTS FOR (t:ContractType) REQUIRE t.name IS UNIQUE",
        ]
        for q in constraints:
            self.service.execute_write(q)
        print("✅ Kısıtlamalar oluşturuldu.")

    def load(self, csv_path: Path, batch_size: int = 50) -> None:
        with open(csv_path, encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        total = len(rows)
        print(f"📄 {total} sözleşme okundu.")
        for i in range(0, total, batch_size):
            self.service.execute_write_batch(self._write_batch, rows[i : i + batch_size])
            print(f"  ✔ {min(i + batch_size, total)}/{total}")
        print("🎉 Yükleme tamamlandı.")

    def _write_batch(self, tx, rows: list[dict]) -> None:
        for row in rows:
            raw_filename = self._parse_str(row.get("Filename", ""))
            if not raw_filename:
                continue

            # contract_name: okunabilir sözleşme adı (Document Name-Answer)
            contract_name = self._parse_str(
                row.get("Document Name-Answer") or row.get("Document Name", "")
            )
            if not contract_name:
                contract_name = raw_filename.removesuffix(".pdf").removesuffix(".txt")

            parties_raw   = self._parse_str(row.get("Parties-Answer", ""))
            gov_law       = self._parse_str(row.get("Governing Law-Answer", ""))
            contract_type = self._parse_contract_type(raw_filename)

            props: dict = {"contract_name": contract_name}
            for col, prop in DATE_FIELDS.items():
                props[prop] = self._parse_str(row.get(col, ""))
            for col, prop in BOOL_FIELDS.items():
                props[prop] = self._parse_bool(row.get(col, ""))

            # Contract node
            tx.run(
                "MERGE (c:Contract {contract_name: $contract_name}) SET c += $props",
                contract_name=contract_name, props=props,
            )

            # ContractType
            tx.run(
                """
                MERGE (t:ContractType {name: $name})
                WITH t MATCH (c:Contract {contract_name: $contract_name})
                MERGE (c)-[:IS_TYPE]->(t)
                """,
                name=contract_type, contract_name=contract_name,
            )

            # GoverningLaw
            if gov_law:
                tx.run(
                    """
                    MERGE (g:GoverningLaw {jurisdiction: $jurisdiction})
                    WITH g MATCH (c:Contract {contract_name: $contract_name})
                    MERGE (c)-[:GOVERNED_BY]->(g)
                    """,
                    jurisdiction=gov_law, contract_name=contract_name,
                )

            # Parties
            if parties_raw:
                for party in [p.strip() for p in parties_raw.split(";") if p.strip()]:
                    tx.run(
                        """
                        MERGE (p:Party {name: $name})
                        WITH p MATCH (c:Contract {contract_name: $contract_name})
                        MERGE (c)-[:SIGNED_BY]->(p)
                        """,
                        name=party, contract_name=contract_name,
                    )


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 55)
    print("  LexiGraph — Neo4j Build Script")
    print("=" * 55)
    print(f"📌 URI      : {secrets.neo4j_config.uri}")
    print(f"📌 Database : {secrets.neo4j_config.database}")
    print(f"📌 CSV      : {CSV_PATH}\n")

    if not CSV_PATH.exists():
        print(f"❌ CSV bulunamadı: {CSV_PATH}")
        sys.exit(1)

    svc = Neo4jService(
        uri=secrets.neo4j_config.uri,
        username=secrets.neo4j_config.username,
        password=secrets.neo4j_config.password,
        database=secrets.neo4j_config.database,
    )
    try:
        loader = ContractLoader(svc)
        loader.create_constraints()
        print("\n📥 Veri yükleniyor...")
        loader.load(CSV_PATH, batch_size=50)

        print("\n📊 Graf İstatistikleri:")
        for key, count in svc.stats().items():
            print(f"   {key:<20}: {count}")
    finally:
        svc.close()

    print("\n✅ Build tamamlandı! Arayüz: http://localhost:7474")


if __name__ == "__main__":
    main()
