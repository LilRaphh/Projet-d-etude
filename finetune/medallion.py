#!/usr/bin/env python3
"""
finetune/medallion.py  —  Orchestrateur Bronze → Silver → Gold → Dataset
Exécute la pipeline complète de nettoyage et génère les JSONL d'entraînement.

Usage :
    python -m finetune.medallion                        # pipeline complète
    python -m finetune.medallion --only bronze          # une seule couche
    python -m finetune.medallion --only silver gold     # deux couches
    python -m finetune.medallion --min-score 0.6        # filtre qualité plus strict
    python -m finetune.medallion --skip-dataset         # sans générer le JSONL final
"""
import argparse
import json
import time
from pathlib import Path

from finetune.bronze import ingest
from finetune.silver import clean
from finetune.gold   import enrich

DATA_DIR   = Path(__file__).parent / "data"
DB_PATH    = Path(__file__).parent.parent / "pipeline" / "output" / "SmartWear_DB.json"

BRONZE_OUT = DATA_DIR / "bronze.jsonl"
SILVER_OUT = DATA_DIR / "silver.jsonl"
GOLD_OUT   = DATA_DIR / "gold.jsonl"

LAYERS = ["bronze", "silver", "gold"]


def _section(title: str):
    print(f"\n{'─'*60}")
    print(f"  {title}")
    print(f"{'─'*60}")


def _print_stats(stats: dict):
    """Affiche un résumé compact des stats d'une couche."""
    layer = stats.get("layer", "?").upper()
    total   = stats.get("total_read", 0)
    written = stats.get("written", 0)
    rate    = stats.get("retention_rate", "?")

    print(f"  [{layer}] {total} → {written} enregistrements  ({rate} conservés)")

    if "rejection_reasons" in stats and stats["rejection_reasons"]:
        print("  Rejets :")
        for reason, count in sorted(stats["rejection_reasons"].items(), key=lambda x: -x[1]):
            print(f"    {reason:<40} {count}")

    if "distributions" in stats:
        dist = stats["distributions"]
        if "price_tier" in dist:
            print("  Prix :", "  ".join(f"{k}={v}" for k, v in dist["price_tier"].items()))
        if "description_quality" in dist:
            print("  Desc :", "  ".join(f"{k}={v}" for k, v in dist["description_quality"].items()))


def run_pipeline(
    layers,
    min_score,
    skip_dataset,
    db_path,
):
    # type: (list, float, bool, Path) -> dict
    results  = {}
    t_start  = time.time()

    # ── Bronze ────────────────────────────────────────────────────────────
    if "bronze" in layers:
        _section("Bronze  —  Ingestion brute")
        t = time.time()
        stats = ingest(db_path, BRONZE_OUT)
        stats["duration_s"] = round(time.time() - t, 2)
        results["bronze"] = stats
        _print_stats(stats)

    # ── Silver ────────────────────────────────────────────────────────────
    if "silver" in layers:
        _section("Silver  —  Nettoyage & validation")
        t = time.time()
        stats = clean(BRONZE_OUT, SILVER_OUT)
        stats["duration_s"] = round(time.time() - t, 2)
        results["silver"] = stats
        _print_stats(stats)

    # ── Gold ──────────────────────────────────────────────────────────────
    if "gold" in layers:
        _section("Gold  —  Enrichissement & sélection qualité")
        t = time.time()
        stats = enrich(SILVER_OUT, GOLD_OUT, min_score)
        stats["duration_s"] = round(time.time() - t, 2)
        results["gold"] = stats
        _print_stats(stats)

    # ── Dataset (JSONL entraînement) ──────────────────────────────────────
    if not skip_dataset and "gold" in layers:
        _section("Dataset  —  Génération des exemples d'entraînement")
        from finetune.prepare_dataset import build_dataset, split_and_save
        t = time.time()
        examples = build_dataset(GOLD_OUT)
        train_path, val_path = split_and_save(examples, DATA_DIR)
        results["dataset"] = {
            "total_examples": len(examples),
            "train_path":     str(train_path),
            "val_path":       str(val_path),
            "duration_s":     round(time.time() - t, 2),
        }
        print(f"  Dataset : {len(examples)} exemples  →  train={train_path.name}  val={val_path.name}")

    # ── Rapport final ─────────────────────────────────────────────────────
    total_duration = round(time.time() - t_start, 2)
    results["total_duration_s"] = total_duration

    _section(f"Pipeline terminée en {total_duration:.1f}s")
    if "bronze" in results:
        print(f"  Bronze  : {results['bronze']['written']} produits ingérés")
    if "silver" in results:
        print(f"  Silver  : {results['silver']['written']} produits propres  "
              f"({results['silver']['rejected']} rejetés)")
    if "gold" in results:
        print(f"  Gold    : {results['gold']['written']} produits Gold  "
              f"({results['gold'].get('descriptions_augmented',0)} descriptions augmentées)")
    if "dataset" in results:
        print(f"  Dataset : {results['dataset']['total_examples']} exemples d'entraînement")

    # Sauvegarde du rapport complet
    report_path = DATA_DIR / "medallion_report.json"
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n  Rapport complet → {report_path}")

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Pipeline Medallion Bronze→Silver→Gold + Dataset",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples :
  python -m finetune.medallion                         # tout
  python -m finetune.medallion --only bronze silver    # deux couches
  python -m finetune.medallion --min-score 0.6         # qualité stricte
  python -m finetune.medallion --skip-dataset          # sans JSONL final
        """,
    )
    parser.add_argument(
        "--only", nargs="+", choices=LAYERS,
        help="Couches à exécuter (défaut : toutes)",
    )
    parser.add_argument(
        "--min-score", default=0.45, type=float,
        help="Score minimum Gold (défaut 0.45)",
    )
    parser.add_argument(
        "--skip-dataset", action="store_true",
        help="Ne pas générer le JSONL d'entraînement",
    )
    parser.add_argument(
        "--db", default=str(DB_PATH),
        help="Chemin vers SmartWear_DB.json",
    )
    args = parser.parse_args()

    layers = args.only if args.only else LAYERS

    # Vérification de l'ordre logique
    if "silver" in layers and "bronze" not in layers:
        if not BRONZE_OUT.exists():
            parser.error("Silver nécessite bronze.jsonl. Lance d'abord --only bronze.")
    if "gold" in layers and "silver" not in layers:
        if not SILVER_OUT.exists():
            parser.error("Gold nécessite silver.jsonl. Lance d'abord --only silver.")

    run_pipeline(
        layers=layers,
        min_score=args.min_score,
        skip_dataset=args.skip_dataset,
        db_path=Path(args.db),
    )


if __name__ == "__main__":
    main()
