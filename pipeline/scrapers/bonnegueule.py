from pipeline.scrapers.shopify_base import ShopifyBaseScraper


class BonneGueuleScraper(ShopifyBaseScraper):
    BASE_URL      = "https://www.bonnegueule.fr"
    BRAND_SOURCE  = "BonneGueule"
    DEFAULT_GENRE = "Adulte"
    DEFAULT_SEXE  = "Homme"  # marque exclusivement masculine
