# =============================================================
#  scrapers/balzac.py — Scraper Balzac Paris (Shopify)
#
#  Site : balzac-paris.fr (catalogue France, EUR)
#  API  : /products.json (Shopify public)
#  Marque majoritairement féminine → DEFAULT_SEXE = "Femme"
# =============================================================

from pipeline.scrapers.shopify_base import ShopifyBaseScraper


class BalzacScraper(ShopifyBaseScraper):
    BASE_URL     = "https://www.balzac-paris.fr"
    BRAND_SOURCE = "Balzac Paris"
    DEFAULT_SEXE = "Femme"
