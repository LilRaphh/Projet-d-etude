from pipeline.scrapers.shopify_base import ShopifyBaseScraper


class RoujeScraper(ShopifyBaseScraper):
    BASE_URL      = "https://www.rouje.com"
    BRAND_SOURCE  = "Rouje"
    DEFAULT_GENRE = "Adulte"
    DEFAULT_SEXE  = "Femme"  # marque exclusivement féminine
