from pipeline.scrapers.shopify_base import ShopifyBaseScraper


class LeSlipFrancaisScraper(ShopifyBaseScraper):
    BASE_URL      = "https://www.leslipfrancais.fr"
    BRAND_SOURCE  = "Le Slip Français"
    DEFAULT_GENRE = "Adulte"
    DEFAULT_SEXE  = "Mixte"
