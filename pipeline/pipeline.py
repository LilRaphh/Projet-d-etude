# =============================================================
#  pipeline/pipeline.py — Normalisation et sauvegarde SmartWear
# =============================================================
import os
import json
import logging
from typing import List

from pipeline.config import OUTPUT_DIR
from pipeline.models import Product

logger = logging.getLogger(__name__)


class SmartWearPipeline:
    """Reçoit une liste de Product, normalise et sauvegarde en JSON + MongoDB."""

    @staticmethod
    def _to_dicts(products: List[Product]) -> List[dict]:
        return [p.to_dict() for p in products]

    @staticmethod
    def _save_json(data: List[dict], filename: str) -> str:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        path = os.path.join(OUTPUT_DIR, filename)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info("[Pipeline] Sauvegardé → %s (%d produits)", path, len(data))
        return path

    @staticmethod
    def _insert_mongo(data: List[dict]):
        mongo_uri = os.environ.get("MONGO_URI")
        if not mongo_uri:
            logger.warning("[Pipeline] MONGO_URI non défini → insertion MongoDB ignorée.")
            return
        try:
            from pymongo import MongoClient, UpdateOne
            client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
            collection = client["smartwear"]["products"]
            ops = [
                UpdateOne({"url": p["url"]}, {"$set": p}, upsert=True)
                for p in data if p.get("url")
            ]
            if ops:
                result = collection.bulk_write(ops)
                logger.info(
                    "[Pipeline] MongoDB : %d insérés, %d mis à jour.",
                    result.upserted_count, result.modified_count,
                )
        except Exception as exc:
            logger.error("[Pipeline] Erreur MongoDB : %s", exc)

    def run(self, products: List[Product], output_filename: str = "SmartWear_DB.json") -> List[dict]:
        logger.info("[Pipeline] Démarrage — %d produits reçus", len(products))
        data = self._to_dicts(products)
        logger.info("[Pipeline] Normalisation terminée")
        self._save_json(data, output_filename)
        self._insert_mongo(data)
        logger.info("[Pipeline] Terminé — %d produits traités", len(data))
        return data
