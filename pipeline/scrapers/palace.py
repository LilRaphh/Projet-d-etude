from typing import List, Tuple

from pipeline.scrapers.shopify_base import ShopifyBaseScraper


class PalaceScraper(ShopifyBaseScraper):
    BASE_URL     = "https://www.palaceskateboards.com"
    BRAND_SOURCE = "Palace"
    CURRENCY     = "USD"

    def _infer_sexe(self, tags: List[str], title: str, product_type: str) -> Tuple[str, str]:
        tags_lower = {t.lower() for t in tags}
        if tags_lower & {"mens", "men", "man", "homme"}:
            return "Adulte", "Homme"
        if tags_lower & {"womens", "women", "woman", "femme"}:
            return "Adulte", "Femme"
        return super()._infer_sexe(tags, title, product_type)
