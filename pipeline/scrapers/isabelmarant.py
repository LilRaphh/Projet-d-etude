from pipeline.scrapers.shopify_base import ShopifyBaseScraper


class IsabelMarantScraper(ShopifyBaseScraper):
    BASE_URL      = "https://www.isabelmarant.com"
    BRAND_SOURCE  = "Isabel Marant"
    DEFAULT_GENRE = "Adulte"
    DEFAULT_SEXE  = "Femme"  # marque majoritairement féminine
