#!/usr/bin/env python3
# =============================================================
#  audit.py — Vérification et correction automatique du JSON
#
#  Usage :
#    python audit.py
#    python audit.py --input output/SmartWear_DB.json
# =============================================================

import argparse
import json
import logging
import os
import re
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

INPUT_FILE  = "output/SmartWear_DB.json"
OUTPUT_FILE = "output/SmartWear_DB.json"  # écrase avec la version corrigée

# ------------------------------------------------------------------
# Règles style → catégorie attendue
# ------------------------------------------------------------------
STYLE_TO_CATEGORIE = {
    # Hauts
    "T-shirt":   "Haut",
    "Pull":      "Haut",
    "Sweat":     "Haut",
    "Hoodie":    "Haut",
    "Chemise":   "Haut",
    "Débardeur": "Haut",
    "Crop-top":  "Haut",
    "Cardigan":  "Haut",
    "Polo":      "Haut",
    # Bas
    "Jean":      "Bas",
    "Pantalon":  "Bas",
    "Short":     "Bas",
    "Legging":   "Bas",
    "Jupe":      "Bas",
    # Manteau/Veste
    "Veste":     "Manteau/Veste",
    "Blazer":    "Manteau/Veste",
    "Manteau":   "Manteau/Veste",
    "Doudoune":  "Manteau/Veste",
    "Parka":     "Manteau/Veste",
    # Robe/Combinaison
    "Robe":        "Robe/Combinaison",
    "Combinaison": "Robe/Combinaison",
    # Chaussures → Autre
    "Sneakers":  "Autre",
    "Bottines":  "Autre",
    "Sandales":  "Autre",
    "Mocassins": "Autre",
    "Derbies":   "Autre",
}

# ------------------------------------------------------------------
# Inférence du sexe depuis le nom du produit
# ------------------------------------------------------------------
def _infer_sexe(name: str) -> str:
    n = name.lower()
    if any(k in n for k in ["men's", "mens ", "man's", " men ", " homme", "uomo", "hombre"]):
        return "Homme"
    if any(k in n for k in ["women's", "womens ", "woman's", " women ", " femme", "donna", "mujer"]):
        return "Femme"
    if any(k in n for k in ["kid", "kids", "youth", "junior", "baby",
                              "boy", "girl", "enfant", "fille", "garçon"]):
        return "Mixte"
    return "Mixte"  # fallback neutre


# ------------------------------------------------------------------
# Nettoyage description
# ------------------------------------------------------------------
def _clean_description(text: str) -> str:
    if not text:
        return text
    # Remplace \r\n, \r, \n par un espace
    text = re.sub(r'[\r\n]+', ' ', text)
    # Supprime les espaces multiples
    text = re.sub(r' {2,}', ' ', text)
    # Supprime les espaces en début/fin
    return text.strip()


# ------------------------------------------------------------------
# Dédoublonnage
# ------------------------------------------------------------------
def _deduplicate(products: list) -> tuple[list, int]:
    seen = set()
    unique = []
    dupes = 0
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


# ------------------------------------------------------------------
# Correction catégorie vs style
# ------------------------------------------------------------------
def _fix_categorie(p: dict) -> tuple[dict, bool]:
    style = p.get("style")
    if not style or style not in STYLE_TO_CATEGORIE:
        return p, False
    expected = STYLE_TO_CATEGORIE[style]
    if p.get("categorie") != expected:
        p["categorie"] = expected
        return p, True
    return p, False


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Audit & correction SmartWear_DB.json")
    parser.add_argument("--input", default=INPUT_FILE, help="Fichier JSON source")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        logger.error(f"Fichier introuvable : {args.input}")
        sys.exit(1)

    with open(args.input, encoding="utf-8") as f:
        products = json.load(f)

    total = len(products)
    logger.info(f"[Audit] {total} produits chargés depuis {args.input}")

    # ── 1. Dédoublonnage ──────────────────────────────────────────
    products, dupes_removed = _deduplicate(products)
    logger.info(f"[Audit] Doublons supprimés     : {dupes_removed}")

    # ── 2. Description ────────────────────────────────────────────
    desc_fixed = 0
    for p in products:
        original = p.get("description") or ""
        cleaned  = _clean_description(original)
        if cleaned != original:
            p["description"] = cleaned
            desc_fixed += 1
    logger.info(f"[Audit] Descriptions nettoyées : {desc_fixed}")

    # ── 3. Sexe null → inférence depuis le nom ───────────────────
    sexe_fixed = 0
    for p in products:
        if not p.get("sexe"):
            p["sexe"] = _infer_sexe(p.get("name", ""))
            sexe_fixed += 1
    logger.info(f"[Audit] Sexe inférés           : {sexe_fixed}")

    # ── 4. Catégorie incohérente avec le style ────────────────────
    cat_fixed = 0
    for p in products:
        p, fixed = _fix_categorie(p)
        if fixed:
            cat_fixed += 1
    logger.info(f"[Audit] Catégories corrigées   : {cat_fixed}")

    # ── Résumé ────────────────────────────────────────────────────
    total_fixes = dupes_removed + desc_fixed + sexe_fixed + cat_fixed
    print(f"\n{'='*55}")
    print(f"  Produits initiaux      : {total}")
    print(f"  Doublons supprimés     : {dupes_removed}")
    print(f"  Descriptions nettoyées : {desc_fixed}")
    print(f"  Sexe inférés           : {sexe_fixed}")
    print(f"  Catégories corrigées   : {cat_fixed}")
    print(f"  ─────────────────────────────────────────────")
    print(f"  Total corrections      : {total_fixes}")
    print(f"  Produits finaux        : {len(products)}")
    print(f"{'='*55}\n")

    # ── Sauvegarde ────────────────────────────────────────────────
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(products, f, indent=2, ensure_ascii=False)
    logger.info(f"[Audit] ✅ Sauvegardé → {OUTPUT_FILE}")


if __name__ == "__main__":
    main()