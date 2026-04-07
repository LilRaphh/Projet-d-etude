# =============================================================
#  pipeline/stats.py — Agrégation des métriques produits
#  Génère pipeline/output/stats.json après chaque run.
# =============================================================
import json
import logging
import os
from collections import defaultdict

from pipeline.config import OUTPUT_DIR

logger = logging.getLogger(__name__)

OUTPUT_FILE = os.path.join(OUTPUT_DIR, "stats.json")
INPUT_FILE  = os.path.join(OUTPUT_DIR, "SmartWear_DB.json")


def _price_bucket(price) -> str:
    if price is None:
        return "N/A"
    if price < 20:
        return "< 20€"
    if price < 50:
        return "20–50€"
    if price < 100:
        return "50–100€"
    if price < 200:
        return "100–200€"
    return "> 200€"


def generate(input_file: str = INPUT_FILE) -> dict:
    if not os.path.exists(input_file):
        logger.error("[Stats] Fichier introuvable : %s", input_file)
        return {}

    with open(input_file, encoding="utf-8") as f:
        products = json.load(f)

    total = len(products)

    by_brand      = defaultdict(int)
    by_category   = defaultdict(int)
    by_sex        = defaultdict(int)
    by_genre      = defaultdict(int)
    by_style      = defaultdict(int)
    by_type       = defaultdict(int)
    by_price      = defaultdict(int)
    prices_brand  = defaultdict(list)

    for p in products:
        brand = p.get("brand_source") or "Inconnu"
        by_brand[brand]    += 1
        by_category[p.get("categorie") or "N/A"] += 1
        by_sex[p.get("sexe") or "N/A"]           += 1
        by_genre[p.get("genre") or "N/A"]        += 1
        by_style[p.get("style") or "N/A"]        += 1
        by_type[p.get("type") or "N/A"]          += 1
        by_price[_price_bucket(p.get("price_value"))] += 1
        if p.get("price_value"):
            prices_brand[brand].append(p["price_value"])

    avg_price_by_brand = {
        brand: round(sum(prices) / len(prices), 2)
        for brand, prices in prices_brand.items()
        if prices
    }

    # Format attendu par Grafana Infinity (liste de records)
    def to_records(d: dict, key: str, value: str) -> list:
        return [{key: k, value: v} for k, v in sorted(d.items(), key=lambda x: -x[1])]

    stats = {
        "total":             total,
        "by_brand":          to_records(by_brand,    "brand",    "count"),
        "by_category":       to_records(by_category, "category", "count"),
        "by_sex":            to_records(by_sex,      "sex",      "count"),
        "by_genre":          to_records(by_genre,    "genre",    "count"),
        "by_style":          to_records(by_style,    "style",    "count"),
        "by_type":           to_records(by_type,     "type",     "count"),
        "by_price_bucket":   to_records(by_price,    "range",    "count"),
        "avg_price_by_brand": [
            {"brand": b, "avg_price": p}
            for b, p in sorted(avg_price_by_brand.items(), key=lambda x: -x[1])
        ],
    }

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)

    logger.info("[Stats] Généré → %s (%d produits)", OUTPUT_FILE, total)
    return stats
