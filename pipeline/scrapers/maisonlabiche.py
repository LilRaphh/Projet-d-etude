# =============================================================
#  scrapers/maisonlabiche.py — Scraper Maison Labiche (Shopify)
#
#  Site : maisonlabiche.com (catalogue international, EUR)
#  API  : /products.json (Shopify public)
#  Marque mixte par nature (broderies sur basiques)
# =============================================================

from pipeline.scrapers.shopify_base import ShopifyBaseScraper


class MaisonLabicheScraper(ShopifyBaseScraper):
    BASE_URL     = "https://www.maisonlabiche.com"
    BRAND_SOURCE = "Maison Labiche"
