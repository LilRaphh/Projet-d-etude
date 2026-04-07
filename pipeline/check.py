# =============================================================
#  pipeline/check.py — Vérification des incohérences style/catégorie
# =============================================================
import argparse
import json
import logging
import os
import sys

from pipeline.config import OUTPUT_DIR

logger = logging.getLogger(__name__)

INPUT_FILE = os.path.join(OUTPUT_DIR, "SmartWear_DB.json")

CHECKS = [
    {
        "label": "T-shirt avec catégorie != Haut",
        "fn": lambda p: p.get("style") == "T-shirt" and p.get("categorie") != "Haut",
    },
    {
        "label": "Pantalon/Short/Jean/Legging avec catégorie != Bas",
        "fn": lambda p: p.get("style") in ("Pantalon", "Short", "Jean", "Legging")
                        and p.get("categorie") != "Bas",
    },
    {
        "label": "Veste/Manteau avec catégorie != Manteau/Veste",
        "fn": lambda p: p.get("style") in ("Veste", "Manteau", "Blazer", "Doudoune", "Parka")
                        and p.get("categorie") != "Manteau/Veste",
    },
    {
        "label": "Sneakers/Bottines avec type != Chaussures",
        "fn": lambda p: p.get("style") in ("Sneakers", "Bottines")
                        and p.get("type") != "Chaussures",
    },
]


def run_check(input_file: str = INPUT_FILE) -> list:
    """Retourne la liste des anomalies trouvées."""
    if not os.path.exists(input_file):
        logger.error("[Check] Fichier introuvable : %s", input_file)
        return []

    with open(input_file, encoding="utf-8") as f:
        products = json.load(f)

    logger.info("[Check] %d produits analysés", len(products))
    anomalies = []
    for check in CHECKS:
        flagged = [p for p in products if check["fn"](p)]
        if flagged:
            anomalies.append({"label": check["label"], "count": len(flagged), "samples": flagged[:5]})
            logger.warning("[Check] %s : %d anomalies", check["label"], len(flagged))

    if not anomalies:
        logger.info("[Check] Aucune anomalie détectée.")
    return anomalies


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=INPUT_FILE)
    args = parser.parse_args()

    anomalies = run_check(args.input)
    print(f"\n{'='*55}")
    if not anomalies:
        print("  Aucune anomalie détectée !")
    else:
        for a in anomalies:
            print(f"\n  {a['label']} ({a['count']}) :")
            for p in a["samples"]:
                print(f"      - [{p.get('brand_source')}] {p.get('name', '')[:45]}"
                      f" | style={p.get('style')} | cat={p.get('categorie')}")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    main()
