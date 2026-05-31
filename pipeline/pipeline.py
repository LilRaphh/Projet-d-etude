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

_UNDERWEAR_KEYWORDS = [
    "sous-vêtement", "sous vetement", "sousvetement",
    "slip", "boxer", "caleçon", "culotte", "string", "shorty", "tanga", "thong",
    "soutien-gorge", "soutien gorge", "brassière de sport",
    "lingerie", "collant", "body", "nuisette", "déshabillé", "kimono",
    "underwear", "briefs", "knickers", "panties", "bra ",
    "pack boxer", "pack slip", "lot boxer", "lot slip",
]

# Mots-clés qui signalent un produit clairement non vestimentaire
_NON_FASHION_KEYWORDS = [
    # Tabac / papeterie
    "rolling papers", "rolling tray", "rizla", " ashtray",
    # Papeterie / stylos
    "kaweco pen", " ballpoint", " fountain pen",
    # Quincaillerie skate
    " bolts", "grip tape", "skateboard deck", "skate deck",
    # Maison / stockage
    "storage bin", "round bin", "storage box", "trash can",
    # Ustensiles
    " mug", "water bottle", "nalgene", " jug",
    # Loisirs
    " frisbee", "frisbee ",
    # Services
    "gift card", "digital gift",
    # Serviettes / linge de maison
    "beach towel",
    # Bijoux / quincaillerie non portée
    " keychain", "key chain",
    # Bagagerie non vestimentaire (sacs portés, pas portés sur soi)
    " tote bag", "market tote", "extra large tote", " tote ",
    " pouch",
    # Maison / divers
    "air freshener", "dog collar", "dog lead",
    # Skate decks
    "pro s43", " board 8.", " board 7.", " board 9.",
    # Petite quincaillerie / bibelots
    "pin badge", "compact mirror", " zippo", "sticker pack",
    " keyring", "key ring",
    # Bouteilles / contenants
    " bottle ", "moflo bottle",
    # Divers non portables
    "swimming pool float", " float ",
]


def _is_underwear(name: str, description: str = "", product_type: str = "") -> bool:
    text = f"{name} {description} {product_type}".lower()
    return any(k in text for k in _UNDERWEAR_KEYWORDS)


def _is_non_fashion(name: str) -> bool:
    text = f" {name} ".lower()
    return any(k in text for k in _NON_FASHION_KEYWORDS)


class SmartWearPipeline:
    """Reçoit une liste de Product, normalise et sauvegarde en JSON + MongoDB."""

    @staticmethod
    def _filter_underwear(products: List[Product]) -> List[Product]:
        kept, removed = [], []
        for p in products:
            if _is_underwear(p.name, p.description or "", ""):
                removed.append(p.name)
            else:
                kept.append(p)
        if removed:
            logger.info("[Pipeline] Sous-vêtements exclus : %d produits", len(removed))
        return kept

    @staticmethod
    def _filter_non_fashion(products: List[Product]) -> List[Product]:
        kept, removed = [], []
        for p in products:
            if _is_non_fashion(p.name):
                removed.append(p.name)
            else:
                kept.append(p)
        if removed:
            logger.info("[Pipeline] Non-vêtements exclus : %d produits", len(removed))
        return kept

    @staticmethod
    def _to_dicts(products: List[Product]) -> List[dict]:
        return [p.to_dict() for p in products]

    @staticmethod
    def _save_json(data: List[dict], filename: str) -> str:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        path = os.path.join(OUTPUT_DIR, filename)

        # Chargement des données existantes
        existing: List[dict] = []
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception:
                existing = []

        # Marques présentes dans ce run → leurs entrées existantes sont remplacées
        updated_brands = {p.get("brand_source") for p in data if p.get("brand_source")}

        # On garde les produits des autres marques (non relancées ce run)
        kept = [p for p in existing if p.get("brand_source") not in updated_brands]
        merged = kept + data

        with open(path, "w", encoding="utf-8") as f:
            json.dump(merged, f, indent=2, ensure_ascii=False)

        logger.info(
            "[Pipeline] Sauvegardé → %s (%d total : %d conservés + %d nouveaux/mis à jour)",
            path, len(merged), len(kept), len(data),
        )
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
        products = self._filter_underwear(products)
        products = self._filter_non_fashion(products)
        data = self._to_dicts(products)
        logger.info("[Pipeline] Normalisation terminée")
        self._save_json(data, output_filename)
        self._insert_mongo(data)
        logger.info("[Pipeline] Terminé — %d produits traités", len(data))
        try:
            from routes.boutique import reset_boutique_cache
            reset_boutique_cache()
            logger.info("[Pipeline] Cache boutique invalidé")
        except Exception:
            pass
        return data
