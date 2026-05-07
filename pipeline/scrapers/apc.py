# =============================================================
#  scrapers/apc.py — Scraper A.P.C. (Shopify)
#
#  Site : apc.fr (catalogue France, EUR)
#  API  : /products.json (Shopify public)
# =============================================================

from pipeline.scrapers.shopify_base import ShopifyBaseScraper


class ApcScraper(ShopifyBaseScraper):
    BASE_URL     = "https://www.apc.fr"
    BRAND_SOURCE = "A.P.C."
