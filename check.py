#!/usr/bin/env python3
# =============================================================
#  check.py — Vérification des incohérences style/catégorie
#
#  Usage :
#    python check.py
#    python check.py --input output/SmartWear_DB.json
# =============================================================

import argparse
import json
import os
import sys

INPUT_FILE = "output/SmartWear_DB.json"

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


def main():
    parser = argparse.ArgumentParser(description="Vérification incohérences SmartWear_DB.json")
    parser.add_argument("--input", default=INPUT_FILE, help="Fichier JSON source")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"Fichier introuvable : {args.input}")
        sys.exit(1)

    with open(args.input, encoding="utf-8") as f:
        products = json.load(f)

    print(f"\n{'='*55}")
    print(f"  🔍 VÉRIFICATION — {len(products)} produits")
    print(f"{'='*55}")

    anomalies_found = False
    for check in CHECKS:
        flagged = [p for p in products if check["fn"](p)]
        if flagged:
            anomalies_found = True
            print(f"\n  ⚠️  {check['label']} ({len(flagged)}) :")
            for p in flagged[:5]:
                print(f"      - [{p.get('brand_source')}] {p.get('name')[:45]}"
                      f" | style={p.get('style')} | cat={p.get('categorie')}"
                      f" | type={p.get('type')}")
            if len(flagged) > 5:
                print(f"      ... et {len(flagged) - 5} autres")

    if not anomalies_found:
        print("  ✅ Aucune anomalie détectée !")

    print(f"\n{'='*55}\n")


if __name__ == "__main__":
    main()