import re
from typing import List, Tuple

from pipeline.scrapers.shopify_base import ShopifyBaseScraper


class KarhuScraper(ShopifyBaseScraper):
    BASE_URL     = "https://karhu.com"
    BRAND_SOURCE = "Karhu"
    CURRENCY     = "EUR"

    def _infer_sexe(self, tags: List[str], title: str, product_type: str) -> Tuple[str, str]:
        t = title.lower()
        # "women's", "womens", "woman", "femme" → Femme
        if re.search(r"\bwomen", t) or "femme" in t:
            return "Adulte", "Femme"
        # "men's", "men", "homme" mais pas "women"
        if re.search(r"\bmen\b", t) or "homme" in t:
            return "Adulte", "Homme"
        return super()._infer_sexe(tags, title, product_type)
