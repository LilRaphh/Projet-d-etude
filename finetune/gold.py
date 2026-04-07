#!/usr/bin/env python3
"""
finetune/gold.py  —  Couche Gold
Enrichissement et sélection qualité depuis silver.jsonl :
  - Score de complétude (0.0 → 1.0) sur 9 champs clés
  - Enrichissement : price_tier, description_quality, size_coverage
  - Augmentation minimale des descriptions manquantes (règle déterministe, sans LLM)
  - Filtre qualité : seulement les produits avec score >= MIN_COMPLETENESS
  - Rapport de distribution (prix, complétude, marques, styles)

Usage :
    python -m finetune.gold
    python -m finetune.gold --input finetune/data/silver.jsonl --min-score 0.5
"""
import argparse
import json
import logging
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional, Tuple

OUTPUT_DIR = Path(__file__).parent / "data"
SILVER_IN  = OUTPUT_DIR / "silver.jsonl"
GOLD_OUT   = OUTPUT_DIR / "gold.jsonl"

logging.basicConfig(level=logging.INFO, format="[Gold] %(message)s")
log = logging.getLogger("gold")

# ── Seuil de qualité ───────────────────────────────────────────────────────
MIN_COMPLETENESS = 0.45   # au moins 45% des champs clés renseignés

# ── Champs utilisés pour le score de complétude ────────────────────────────
COMPLETENESS_FIELDS = [
    "name",         # 1
    "brand_source", # 2
    "type",         # 3
    "categorie",    # 4
    "style",        # 5
    "sexe",         # 6
    "price_value",  # 7
    "description",  # 8
    "color",        # 9
]

# ── Seuils price_tier ──────────────────────────────────────────────────────
PRICE_TIERS = [
    (30.0,   "budget"),
    (80.0,   "mid-range"),
    (150.0,  "premium"),
    (float("inf"), "luxe"),
]


# ═══════════════════════════════════════════════════════════════════════════
#  Calculs d'enrichissement
# ═══════════════════════════════════════════════════════════════════════════

def completeness_score(record: dict) -> float:
    """Score entre 0.0 et 1.0 : fraction des champs clés non nuls/non vides."""
    filled = sum(
        1 for f in COMPLETENESS_FIELDS
        if record.get(f) not in (None, "", [], 0)
    )
    return round(filled / len(COMPLETENESS_FIELDS), 3)


def price_tier(price: Optional[float]) -> Optional[str]:
    if price is None:
        return None
    for threshold, tier in PRICE_TIERS:
        if price < threshold:
            return tier
    return "luxe"


def description_quality(description: Optional[str]) -> str:
    if not description:
        return "absente"
    length = len(description)
    if length >= 120:
        return "riche"
    if length >= 40:
        return "moyenne"
    return "pauvre"


def size_coverage(record: dict) -> str:
    """Évalue la couverture des tailles disponibles."""
    tailles = record.get("taille") or []
    sizes   = record.get("sizes") or []
    total   = len(tailles) + len(sizes)
    if total == 0:
        return "aucune"
    if total <= 2:
        return "partielle"
    if total <= 4:
        return "bonne"
    return "complète"


def augment_description(record: dict) -> Tuple[Optional[str], bool]:
    """
    Génère une description minimale déterministe si elle est absente.
    Retourne (description, was_augmented).
    Aucun appel LLM — règles pures sur les champs existants.
    """
    if record.get("description"):
        return record["description"], False

    parts = []
    style    = record.get("style")
    cat      = record.get("categorie")
    color    = record.get("color")
    sexe     = record.get("sexe")
    brand    = record.get("brand_source")
    tailles  = record.get("taille") or []
    price    = record.get("price_value")

    if style:
        parts.append(style)
    if cat and cat != style:
        parts.append(f"de type {cat.lower()}")
    if color:
        parts.append(f"coloris {color.lower()}")
    if sexe:
        parts.append(f"pour {sexe.lower()}")
    if brand:
        parts.append(f"— {brand}")
    if tailles:
        parts.append(f"Tailles : {', '.join(tailles)}")
    if price:
        parts.append(f"Prix : {price:.2f} €")

    if not parts:
        return None, False

    desc = ". ".join(parts).capitalize() + "."
    return desc, True


# ═══════════════════════════════════════════════════════════════════════════
#  Pipeline Gold
# ═══════════════════════════════════════════════════════════════════════════

def enrich(input_path: Path, output_path: Path, min_score: float = MIN_COMPLETENESS) -> dict:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    total = written = filtered_low_score = augmented = 0
    score_dist: Counter  = Counter()
    price_dist: Counter  = Counter()
    brand_dist: Counter  = Counter()
    style_dist: Counter  = Counter()
    desc_quality_dist: Counter = Counter()

    with open(input_path, encoding="utf-8") as inp, \
         open(output_path, "w", encoding="utf-8") as out:

        for line in inp:
            line = line.strip()
            if not line:
                continue
            total += 1
            record = json.loads(line)

            # ── Score de complétude ───────────────────────────────────────
            score = completeness_score(record)
            score_bucket = f"{int(score * 10) * 10}%"
            score_dist[score_bucket] += 1

            # ── Filtre qualité ────────────────────────────────────────────
            if score < min_score:
                filtered_low_score += 1
                continue

            # ── Augmentation description ──────────────────────────────────
            desc, was_augmented = augment_description(record)
            if was_augmented:
                record["description"] = desc
                augmented += 1

            # ── Enrichissements ───────────────────────────────────────────
            record["_completeness_score"] = score
            record["_price_tier"]         = price_tier(record.get("price_value"))
            record["_desc_quality"]       = description_quality(record.get("description"))
            record["_size_coverage"]      = size_coverage(record)
            record["_desc_augmented"]     = was_augmented
            record["_layer"]              = "gold"

            # ── Distributions pour le rapport ─────────────────────────────
            price_dist[record["_price_tier"] or "N/A"] += 1
            brand_dist[record.get("brand_source") or "N/A"] += 1
            style_dist[record.get("style") or "N/A"] += 1
            desc_quality_dist[record["_desc_quality"]] += 1

            out.write(json.dumps(record, ensure_ascii=False) + "\n")
            written += 1

    retention = f"{written/total*100:.1f}%" if total else "0%"

    stats = {
        "layer":               "gold",
        "input_path":          str(input_path),
        "output_path":         str(output_path),
        "min_completeness":    min_score,
        "total_read":          total,
        "written":             written,
        "filtered_low_score":  filtered_low_score,
        "descriptions_augmented": augmented,
        "retention_rate":      retention,
        "distributions": {
            "completeness_score": dict(sorted(score_dist.items())),
            "price_tier":         dict(price_dist.most_common()),
            "description_quality": dict(desc_quality_dist.most_common()),
            "brands":             dict(brand_dist.most_common()),
            "top_styles":         dict(style_dist.most_common(10)),
        },
    }

    log.info("Enrichissement terminé")
    log.info("  Lus             : %d", total)
    log.info("  Écrits (Gold)   : %d  (%s conservés)", written, retention)
    log.info("  Filtrés (score) : %d  (seuil %.0f%%)", filtered_low_score, min_score * 100)
    log.info("  Desc. augmentées: %d", augmented)
    log.info("  Distribution des prix :")
    for tier, count in price_dist.most_common():
        log.info("    %-12s %d", tier or "N/A", count)
    log.info("  Qualité des descriptions :")
    for q, count in desc_quality_dist.most_common():
        log.info("    %-12s %d", q, count)
    log.info("  Complétude par tranche :")
    for bucket, count in sorted(score_dist.items()):
        log.info("    %-6s %d", bucket, count)

    return stats


def main():
    parser = argparse.ArgumentParser(description="Couche Gold — enrichissement & sélection qualité")
    parser.add_argument("--input",     default=str(SILVER_IN),  help="silver.jsonl")
    parser.add_argument("--output",    default=str(GOLD_OUT),   help="gold.jsonl")
    parser.add_argument("--min-score", default=MIN_COMPLETENESS, type=float,
                        help=f"Score minimum de complétude (défaut {MIN_COMPLETENESS})")
    args = parser.parse_args()

    stats = enrich(Path(args.input), Path(args.output), args.min_score)
    print(json.dumps(stats, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
