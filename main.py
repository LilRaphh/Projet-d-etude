#!/usr/bin/env python3
# =============================================================
#  main.py — Point d'entrée unique SmartWear Scraper
#
#  Usage :
#    python main.py                        → tous les scrapers
#    python main.py --scrapers mango nike  → scrapers choisis
# =============================================================

import argparse
import logging
import sys
from typing import List

from scrapers import MangoScraper, NikeScraper, JulesScraper, LeCoqSportifScraper, TacchiniScraper, KappaScraper, LottoScraper
from models   import Product
from pipeline import SmartWearPipeline



# ------------------------------------------------------------------
# Logging
# ------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Registre des scrapers disponibles
# ------------------------------------------------------------------
SCRAPERS = {
    "mango":        MangoScraper,
    "nike":         NikeScraper,
    "jules":        JulesScraper,
    "lecoqsportif": LeCoqSportifScraper,
    "Tacchini":     TacchiniScraper,
    "Kappa":        KappaScraper,
    "Lotto":        LottoScraper,
}

# ------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="SmartWear Scraper")
    parser.add_argument(
        "--scrapers",
        nargs="+",
        choices=list(SCRAPERS.keys()),
        default=list(SCRAPERS.keys()),
        help="Scrapers à lancer (défaut : tous)",
    )
    args = parser.parse_args()

    all_products: List[Product] = []

    # ── Lancement des scrapers ─────────────────────────────────────
    for name in args.scrapers:
        scraper_cls = SCRAPERS[name]
        logger.info(f"{'='*50}")
        logger.info(f"🚀 Lancement : {name.upper()}")
        logger.info(f"{'='*50}")
        try:
            scraper  = scraper_cls()
            products = scraper.run()
            all_products.extend(products)
            logger.info(f"✅ {name.upper()} terminé — {len(products)} produits")
        except Exception as exc:
            logger.error(f"❌ {name.upper()} échoué : {exc}")

    if not all_products:
        logger.warning("Aucun produit collecté. Fin du programme.")
        return

    logger.info(f"\n{'='*50}")
    logger.info(f"📦 Total collecté : {len(all_products)} produits")
    logger.info(f"{'='*50}")

    # ── Pipeline normalisation + sauvegarde ───────────────────────
    pipeline = SmartWearPipeline()
    pipeline.run(all_products)

    # ── Audit + correction automatique ────────────────────────────
    logger.info(f"\n{'='*50}")
    logger.info("🔍 Lancement de l'audit...")
    logger.info(f"{'='*50}")
    from audit import main as run_audit
    run_audit()


if __name__ == "__main__":
    main()