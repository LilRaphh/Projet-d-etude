from typing import List, Tuple

from pipeline.scrapers.shopify_base import ShopifyBaseScraper


class FillingPiecesScraper(ShopifyBaseScraper):
    BASE_URL     = "https://fillingpieces.com"
    BRAND_SOURCE = "Filling Pieces"
    CURRENCY     = "USD"

    def _infer_sexe(self, tags: List[str], title: str, product_type: str) -> Tuple[str, str]:
        # Tags du type "Gender: Men" / "Gender: Women" ou "Male" / "Female"
        tags_lower = {t.lower() for t in tags}
        if any("women" in t or t in ("female", "femme") for t in tags_lower):
            return "Adulte", "Femme"
        if any(("men" in t and "women" not in t) or t in ("male", "homme") for t in tags_lower):
            return "Adulte", "Homme"
        return super()._infer_sexe(tags, title, product_type)
