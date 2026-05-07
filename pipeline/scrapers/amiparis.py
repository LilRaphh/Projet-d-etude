from pipeline.scrapers.shopify_base import ShopifyBaseScraper


class AmiParisScraper(ShopifyBaseScraper):
    BASE_URL      = "https://www.amiparis.com"
    BRAND_SOURCE  = "AMI Paris"
    DEFAULT_GENRE = "Adulte"
    DEFAULT_SEXE  = "Mixte"  # menswear + collections femme + unisex
