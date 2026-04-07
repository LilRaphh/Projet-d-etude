#!/usr/bin/env python3
"""
finetune/bronze.py  —  Couche Bronze
Ingestion brute de SmartWear_DB.json :
  - Aucune transformation des données
  - Ajout de métadonnées (_id, _source, _ingested_at, _raw_hash)
  - Sauvegarde JSONL avec rapport d'ingestion

Usage :
    python -m finetune.bronze
    python -m finetune.bronze --db pipeline/output/SmartWear_DB.json
"""
import argparse
import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

ROOT       = Path(__file__).parent.parent
DB_PATH    = ROOT / "pipeline" / "output" / "SmartWear_DB.json"
OUTPUT_DIR = Path(__file__).parent / "data"
BRONZE_OUT = OUTPUT_DIR / "bronze.jsonl"

logging.basicConfig(level=logging.INFO, format="[Bronze] %(message)s")
log = logging.getLogger("bronze")


def _hash_record(record: dict) -> str:
    """Hash déterministe d'un produit (URL en priorité, sinon nom+marque)."""
    key = record.get("url") or f"{record.get('name','')}|{record.get('brand_source','')}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def ingest(db_path: Path, output_path: Path) -> dict:
    """
    Charge le JSON brut, enrichit chaque enregistrement avec des métadonnées
    et écrit le JSONL Bronze.
    Retourne un dict de statistiques.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ingested_at = datetime.now(timezone.utc).isoformat()

    log.info("Lecture de %s …", db_path)
    with open(db_path, encoding="utf-8") as f:
        raw_products = json.load(f)

    total = len(raw_products)
    log.info("%d produits trouvés", total)

    seen_hashes: set = set()
    duplicates_raw = 0
    written = 0

    with open(output_path, "w", encoding="utf-8") as out:
        for i, product in enumerate(raw_products):
            record_hash = _hash_record(product)

            # Détection des doublons dès le niveau bronze (même URL exacte)
            if record_hash in seen_hashes:
                duplicates_raw += 1
                continue
            seen_hashes.add(record_hash)

            bronze_record = {
                # ── Métadonnées Bronze ──────────────────────────────────────
                "_id":           record_hash,
                "_source":       str(db_path.name),
                "_ingested_at":  ingested_at,
                "_seq":          i,
                "_layer":        "bronze",
                # ── Données brutes (intactes) ───────────────────────────────
                **product,
            }
            out.write(json.dumps(bronze_record, ensure_ascii=False) + "\n")
            written += 1

    stats = {
        "layer":          "bronze",
        "input_path":     str(db_path),
        "output_path":    str(output_path),
        "total_read":     total,
        "duplicates_raw": duplicates_raw,
        "written":        written,
        "ingested_at":    ingested_at,
    }

    log.info("Ingestion terminée")
    log.info("  Lus           : %d", total)
    log.info("  Doublons bruts: %d", duplicates_raw)
    log.info("  Écrits        : %d", written)
    log.info("  Sortie        : %s", output_path)

    return stats


def main():
    parser = argparse.ArgumentParser(description="Couche Bronze — ingestion brute")
    parser.add_argument("--db",     default=str(DB_PATH),    help="SmartWear_DB.json")
    parser.add_argument("--output", default=str(BRONZE_OUT), help="Fichier bronze.jsonl")
    args = parser.parse_args()

    stats = ingest(Path(args.db), Path(args.output))
    print(json.dumps(stats, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
