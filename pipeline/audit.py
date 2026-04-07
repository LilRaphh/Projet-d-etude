# =============================================================
#  pipeline/audit.py — Vérification et correction automatique du JSON
# =============================================================
import argparse
import json
import logging
import os
import re
import sys

from pipeline.config import OUTPUT_DIR

logger = logging.getLogger(__name__)

INPUT_FILE  = os.path.join(OUTPUT_DIR, "SmartWear_DB.json")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "SmartWear_DB.json")

STYLE_TO_CATEGORIE = {
    "T-shirt": "Haut", "Pull": "Haut", "Sweat": "Haut", "Hoodie": "Haut",
    "Chemise": "Haut", "Débardeur": "Haut", "Crop-top": "Haut",
    "Cardigan": "Haut", "Polo": "Haut",
    "Jean": "Bas", "Pantalon": "Bas", "Short": "Bas", "Legging": "Bas", "Jupe": "Bas",
    "Veste": "Manteau/Veste", "Blazer": "Manteau/Veste", "Manteau": "Manteau/Veste",
    "Doudoune": "Manteau/Veste", "Parka": "Manteau/Veste",
    "Robe": "Robe/Combinaison", "Combinaison": "Robe/Combinaison",
    "Sneakers": "Autre", "Bottines": "Autre", "Sandales": "Autre",
    "Mocassins": "Autre", "Derbies": "Autre",
}


def _infer_sexe(name: str) -> str:
    n = name.lower()
    if any(k in n for k in ["men's", "mens ", "man's", " men ", " homme", "uomo", "hombre"]):
        return "Homme"
    if any(k in n for k in ["women's", "womens ", "woman's", " women ", " femme", "donna", "mujer"]):
        return "Femme"
    if any(k in n for k in ["kid", "kids", "youth", "junior", "baby", "boy", "girl",
                              "enfant", "fille", "garçon"]):
        return "Mixte"
    return "Mixte"


def _clean_description(text: str) -> str:
    if not text:
        return text
    text = re.sub(r'[\r\n]+', ' ', text)
    text = re.sub(r' {2,}', ' ', text)
    return text.strip()


def _deduplicate(products: list) -> tuple:
    seen, unique, dupes = set(), [], 0
    for p in products:
        key = (
            (p.get("name") or "").strip().lower(),
            (p.get("color") or "").strip().lower(),
            (p.get("brand_source") or "").strip().lower(),
        )
        if key in seen:
            dupes += 1
        else:
            seen.add(key)
            unique.append(p)
    return unique, dupes


def _fix_categorie(p: dict) -> tuple:
    style = p.get("style")
    if not style or style not in STYLE_TO_CATEGORIE:
        return p, False
    expected = STYLE_TO_CATEGORIE[style]
    if p.get("categorie") != expected:
        p["categorie"] = expected
        return p, True
    return p, False


def run_audit(input_file: str = INPUT_FILE) -> dict:
    """Point d'entrée réutilisable (Airflow, CLI, tests)."""
    if not os.path.exists(input_file):
        logger.error("[Audit] Fichier introuvable : %s", input_file)
        return {}

    with open(input_file, encoding="utf-8") as f:
        products = json.load(f)

    total = len(products)
    logger.info("[Audit] %d produits chargés", total)

    products, dupes_removed = _deduplicate(products)

    desc_fixed = 0
    for p in products:
        original = p.get("description") or ""
        cleaned = _clean_description(original)
        if cleaned != original:
            p["description"] = cleaned
            desc_fixed += 1

    sexe_fixed = 0
    for p in products:
        if not p.get("sexe"):
            p["sexe"] = _infer_sexe(p.get("name", ""))
            sexe_fixed += 1

    cat_fixed = 0
    for p in products:
        p, fixed = _fix_categorie(p)
        if fixed:
            cat_fixed += 1

    stats = {
        "total_initial":    total,
        "dupes_removed":    dupes_removed,
        "desc_fixed":       desc_fixed,
        "sexe_fixed":       sexe_fixed,
        "cat_fixed":        cat_fixed,
        "total_final":      len(products),
    }

    logger.info(
        "[Audit] Doublons: %d | Descriptions: %d | Sexe: %d | Catégories: %d | Final: %d",
        dupes_removed, desc_fixed, sexe_fixed, cat_fixed, len(products),
    )

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(products, f, indent=2, ensure_ascii=False)
    logger.info("[Audit] Sauvegardé → %s", OUTPUT_FILE)

    return stats


def main():
    parser = argparse.ArgumentParser(description="Audit & correction SmartWear_DB.json")
    parser.add_argument("--input", default=INPUT_FILE)
    args = parser.parse_args()

    stats = run_audit(args.input)
    if stats:
        print(f"\n{'='*55}")
        print(f"  Produits initiaux      : {stats['total_initial']}")
        print(f"  Doublons supprimés     : {stats['dupes_removed']}")
        print(f"  Descriptions nettoyées : {stats['desc_fixed']}")
        print(f"  Sexe inférés           : {stats['sexe_fixed']}")
        print(f"  Catégories corrigées   : {stats['cat_fixed']}")
        print(f"  Produits finaux        : {stats['total_final']}")
        print(f"{'='*55}\n")


if __name__ == "__main__":
    main()
