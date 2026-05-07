from pipeline.scrapers.shopify_base import ShopifyBaseScraper


class CabaiaScraper(ShopifyBaseScraper):
    BASE_URL      = "https://www.cabaia.fr"
    BRAND_SOURCE  = "Cabaïa"
    DEFAULT_GENRE = "Adulte"
    DEFAULT_SEXE  = "Mixte"  # accessoires et mode mixte
