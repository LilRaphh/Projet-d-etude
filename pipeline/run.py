#!/usr/bin/env python3
# =============================================================
#  pipeline/run.py — Point d'entrée CLI SmartWear Scraper
#
#  Usage :
#    python -m pipeline.run                         → tous les scrapers
#    python -m pipeline.run --scrapers mango nike   → scrapers choisis
#    python -m pipeline.run --log-level DEBUG        → plus verbeux
# =============================================================
import argparse
import sys
from datetime import datetime, timezone
from typing import List

from pipeline import logging_config
from pipeline.scrapers import (
    MangoScraper,
    NikeScraper, JulesScraper, GymsharkScraper,
    LeCoqSportifScraper, TacchiniScraper, KappaScraper, LottoScraper,
    ApcScraper, BalzacScraper, MaisonLabicheScraper,
    RoujeScraper, CabaiaScraper,
    BonneGueuleScraper, MerciScraper, IsabelMarantScraper, AmiParisScraper,
    _PLAYWRIGHT_AVAILABLE,
)
from pipeline.models import Product
from pipeline.pipeline import SmartWearPipeline
from pipeline.audit import run_audit
from pipeline.check import run_check
from pipeline.stats import generate as generate_stats

SCRAPERS = {
    "mango":           MangoScraper,
    "lecoqsportif":    LeCoqSportifScraper,
    "tacchini":        TacchiniScraper,
    "kappa":           KappaScraper,
    "lotto":           LottoScraper,
    "apc":             ApcScraper,
    "balzac":          BalzacScraper,
    "maisonlabiche":   MaisonLabicheScraper,
    "rouje":           RoujeScraper,
    "cabaia":          CabaiaScraper,
    "bonnegueule":     BonneGueuleScraper,
    "merci":           MerciScraper,
    "isabelmarant":    IsabelMarantScraper,
    "amiparis":        AmiParisScraper,
}
if _PLAYWRIGHT_AVAILABLE:
    SCRAPERS["nike"]     = NikeScraper
    SCRAPERS["jules"]    = JulesScraper
    SCRAPERS["gymshark"] = GymsharkScraper


def run(scraper_names: List[str], log_level: str = "INFO") -> dict:
    """
    Exécute le pipeline complet et retourne un dict de statistiques.
    Appelable depuis Airflow, un script, ou la CLI.
    """
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    logging_config.setup(level=log_level, run_id=run_id)

    import logging
    logger = logging.getLogger(__name__)

    all_products: List[Product] = []
    scraper_stats = {}

    for name in scraper_names:
        cls = SCRAPERS[name]
        logger.info("=" * 50)
        logger.info("Lancement : %s", name.upper())
        logger.info("=" * 50)
        try:
            products = cls().run()
            all_products.extend(products)
            scraper_stats[name] = {"status": "ok", "count": len(products)}
            logger.info("%s terminé — %d produits", name.upper(), len(products))
        except Exception as exc:
            scraper_stats[name] = {"status": "error", "error": str(exc)}
            logger.error("%s échoué : %s", name.upper(), exc)

    if not all_products:
        logger.warning("Aucun produit collecté. Fin du programme.")
        return {"run_id": run_id, "scrapers": scraper_stats, "total": 0}

    logger.info("Total collecté : %d produits", len(all_products))

    pipeline = SmartWearPipeline()
    pipeline.run(all_products)

    audit_stats = run_audit()
    run_check()
    generate_stats()

    return {
        "run_id":   run_id,
        "scrapers": scraper_stats,
        "total":    len(all_products),
        "audit":    audit_stats,
    }


def main():
    parser = argparse.ArgumentParser(description="SmartWear Scraper Pipeline")
    parser.add_argument(
        "--scrapers",
        nargs="+",
        choices=list(SCRAPERS.keys()),
        default=list(SCRAPERS.keys()),
        help="Scrapers à lancer (défaut : tous)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    args = parser.parse_args()

    stats = run(args.scrapers, args.log_level)
    print(f"\nRun {stats['run_id']} — {stats['total']} produits collectés")
    sys.exit(0 if stats["total"] > 0 else 1)


if __name__ == "__main__":
    main()
