# =============================================================
#  pipeline.py — Normalisation et sauvegarde SmartWear
# =============================================================

import os
import json
import logging
from typing import List

from config import OUTPUT_DIR
from models import Product

logger = logging.getLogger(__name__)


class SmartWearPipeline:
    """
    Reçoit une liste de Product, les normalise,
    puis sauvegarde en JSON (et optionnellement dans MongoDB).
    """

    # ── Normalisation ──────────────────────────────────────────────
    @staticmethod
    def _to_dicts(products: List[Product]) -> List[dict]:
        return [p.to_dict() for p in products]

    # ── Sauvegarde JSON ────────────────────────────────────────────
    @staticmethod
    def _save_json(data: List[dict], filename: str):
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        path = os.path.join(OUTPUT_DIR, filename)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info(f"[Pipeline] Sauvegardé → {path} ({len(data)} produits)")
        return path

    # ── Insertion MongoDB ──────────────────────────────────────────
    @staticmethod
    def _insert_mongo(data: List[dict]):
        mongo_uri = os.environ.get("MONGO_URI")
        if not mongo_uri:
            logger.warning("[Pipeline] MONGO_URI non défini → insertion MongoDB ignorée.")
            return

        try:
            from pymongo import MongoClient, UpdateOne
            client     = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
            db         = client["smartwear"]
            collection = db["products"]

            ops = [
                UpdateOne({"url": p["url"]}, {"$set": p}, upsert=True)
                for p in data
                if p.get("url")
            ]
            if ops:
                result = collection.bulk_write(ops)
                logger.info(
                    f"[Pipeline] MongoDB : {result.upserted_count} insérés, "
                    f"{result.modified_count} mis à jour."
                )
        except Exception as exc:
            logger.error(f"[Pipeline] Erreur MongoDB : {exc}")

    # ── Point d'entrée ─────────────────────────────────────────────
    def run(self, products: List[Product], output_filename: str = "SmartWear_DB.json"):
        logger.info(f"[Pipeline] Démarrage — {len(products)} produits reçus")

        # 1. Normalisation
        data = self._to_dicts(products)
        logger.info("[Pipeline] Normalisation terminée")

        # 2. Sauvegarde JSON
        self._save_json(data, output_filename)

        # 3. Insertion MongoDB
        self._insert_mongo(data)

        logger.info(f"[Pipeline] ✅ Terminé — {len(data)} produits traités")
        return data