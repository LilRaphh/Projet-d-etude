from pipeline.scrapers.shopify_base import ShopifyBaseScraper


class MerciScraper(ShopifyBaseScraper):
    BASE_URL               = "https://www.merci-merci.com"
    BRAND_SOURCE           = "Merci"
    DEFAULT_GENRE          = "Adulte"
    DEFAULT_SEXE           = "Mixte"   # concept store multi-genre
    STRICT_CLOTHING        = True      # filtre déco, cuisine, beauté, etc.
    EXTRACT_BRAND_FROM_NAME = True     # "Carhartt WIP – Bonnet – Noir" → brand=Carhartt WIP
