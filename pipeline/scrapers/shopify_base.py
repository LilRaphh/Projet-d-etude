# =============================================================
#  scrapers/shopify_base.py — Base commune pour les scrapers Shopify
#
#  Tous les stores Shopify publics exposent /products.json.
#  Les sous-classes n'ont qu'à définir BASE_URL, BRAND_SOURCE,
#  et éventuellement surcharger _infer_sexe().
# =============================================================

import re
import logging
import time
from typing import List, Optional, Tuple

from pipeline.scrapers.base import BaseScraper, COLOR_KEYWORDS
from pipeline.models import Product

logger = logging.getLogger(__name__)

PAGE_SIZE = 250

SIZE_LABELS = {
    "XXS", "XS", "S", "M", "L", "XL", "XXL", "XXXL",
    "34", "36", "38", "40", "42", "44", "46", "48",
    "50", "52",
    "T1", "T2", "T3", "T4",
}

SHOE_KEYWORDS = [
    "chaussure", "sneaker", "bottine", "mocassin", "boot",
    "shoe", "derby", "espadrille", "sandale", "loafer", "mule",
    "trainer", "basket", "pump", "heel",
]


class ShopifyBaseScraper(BaseScraper):
    BASE_URL: str = ""
    BRAND_SOURCE: str = ""

    # Sexe par défaut — surcharger dans la sous-classe si la marque est mono-genre
    DEFAULT_GENRE: str = "Adulte"
    DEFAULT_SEXE: str = "Mixte"

    # Devise par défaut — surcharger si le store est en USD, GBP…
    CURRENCY: str = "EUR"

    # ------------------------------------------------------------------
    def _infer_sexe(self, tags: List[str], title: str, product_type: str) -> Tuple[str, str]:
        """Infère (genre, sexe) depuis les métadonnées Shopify."""
        combined = [t.lower() for t in tags] + [title.lower(), product_type.lower()]

        if any(t in combined for t in ["garcon", "garçon", "boy", "boys"]):
            return "Enfant", "Garçon"
        if any(t in combined for t in ["fille", "girl", "girls"]):
            return "Enfant", "Fille"
        if any(t in combined for t in ["enfant", "kid", "kids", "junior", "child", "bébé", "bebe", "baby"]):
            return "Enfant", "Mixte"
        if any(t in combined for t in ["homme", "man", "men", "masculin", "menswear"]):
            return "Adulte", "Homme"
        if any(t in combined for t in ["femme", "woman", "women", "féminin", "womenswear"]):
            return "Adulte", "Femme"
        return self.DEFAULT_GENRE, self.DEFAULT_SEXE

    def _extract_color(self, item: dict) -> Optional[str]:
        options = item.get("options", [])
        title   = item.get("title", "")
        desc    = re.sub(r'<[^>]+>', '', item.get("body_html", "") or "").strip()

        for opt in options:
            if opt.get("name", "").lower() in ("couleur", "color", "colour"):
                vals = opt.get("values", [])
                if vals and vals[0].upper() not in ("DEFAULT TITLE", ""):
                    return vals[0].strip().capitalize()

        if ' - ' in title:
            part = title.split(' - ', 1)[1].split('/')[0].strip()
            c = self._find_color(part)
            if c:
                return c
            if part and len(part) < 30:
                return part.capitalize()

        return self._find_color(desc) or self._find_color(title)

    @staticmethod
    def _is_valid_size(val: str) -> bool:
        """Accepte les tailles lettrées (S/M/L…) et numériques entières ou demi (39, 39.5, 39½)."""
        if val.upper() in SIZE_LABELS:
            return True
        cleaned = val.replace('½', '.5').replace(',', '.')
        try:
            n = float(cleaned)
            return 28.0 <= n <= 54.0
        except ValueError:
            return False

    # ------------------------------------------------------------------
    def _fetch_all_products(self) -> List[dict]:
        all_items: List[dict] = []
        page = 1
        brand = self.BRAND_SOURCE
        while True:
            url = f"{self.BASE_URL}/products.json?limit={PAGE_SIZE}&page={page}"
            try:
                resp = self.session.get(url, timeout=20)
                if resp.status_code == 429:
                    logger.warning("[%s] Rate limit (429) — pause 10s", brand)
                    time.sleep(10)
                    continue
                if resp.status_code != 200:
                    logger.warning("[%s] HTTP %d page %d", brand, resp.status_code, page)
                    break
                products = resp.json().get("products", [])
                if not products:
                    break
                all_items.extend(products)
                logger.info("[%s] page %d → %d produits", brand, page, len(products))
                if len(products) < PAGE_SIZE:
                    break
                page += 1
                self.sleep(1.0, 2.0)
            except Exception as e:
                logger.warning("[%s] Erreur page %d : %s", brand, page, e)
                break
        return all_items

    # ------------------------------------------------------------------
    def _parse_product(self, item: dict) -> Optional[Product]:
        name       = item.get("title", "Inconnu").strip()
        desc       = re.sub(r'<[^>]+>', '', item.get("body_html", "") or "").strip()
        handle     = item.get("handle", "")
        url        = f"{self.BASE_URL}/products/{handle}"
        tags       = item.get("tags", [])
        p_type_raw = item.get("product_type", "") or ""
        options    = item.get("options", [])

        genre, sexe = self._infer_sexe(tags, name, p_type_raw)

        images     = item.get("images", [])
        main_image = images[0].get("src") if images else None
        color      = self._extract_color(item)

        # Index option taille
        size_idx = None
        for i, opt in enumerate(options):
            if opt.get("name", "").lower() in ("taille", "size", "pointure", "sizes", "size (fr)"):
                size_idx = i

        all_tailles: List[str] = []
        price: Optional[float] = None

        for variant in item.get("variants", []):
            if price is None:
                try:
                    price = round(float(variant.get("price", "0")), 2)
                except (ValueError, TypeError):
                    pass

            opts = [variant.get("option1"), variant.get("option2"), variant.get("option3")]
            size = None
            if size_idx is not None and opts[size_idx]:
                val = opts[size_idx].strip()
                if self._is_valid_size(val):
                    size = val.upper()
            elif size_idx is None and len(options) == 1 and opts[0]:
                val = opts[0].strip()
                if self._is_valid_size(val):
                    size = val.upper()

            if size and size not in all_tailles:
                all_tailles.append(size)

        is_shoe = any(
            k in name.lower() or k in p_type_raw.lower()
            for k in SHOE_KEYWORDS
        )
        p_type = "Chaussures" if is_shoe else "Vêtement"

        return Product(
            name         = name,
            price_value  = price,
            currency     = self.CURRENCY,
            description  = desc,
            genre        = genre,
            sexe         = sexe,
            sizes        = all_tailles if is_shoe else [],
            taille       = [] if is_shoe else all_tailles,
            color        = color,
            rating       = None,
            type         = p_type,
            categorie    = self.infer_categorie(name, desc, p_type),
            style        = self.infer_style(name, desc),
            image        = main_image,
            url          = url,
            brand_source = self.BRAND_SOURCE,
        )

    # ------------------------------------------------------------------
    def run(self) -> List[Product]:
        brand = self.BRAND_SOURCE
        logger.info("[%s] Démarrage — récupération catalogue complet", brand)
        raw_items = self._fetch_all_products()
        logger.info("[%s] %d produits bruts", brand, len(raw_items))

        all_products: List[Product] = []
        for item in raw_items:
            try:
                p = self._parse_product(item)
                if p:
                    all_products.append(p)
                    logger.info(
                        "  OK %s | %s | %s | %s EUR",
                        p.name[:50], p.sexe, p.color, p.price_value,
                    )
            except Exception as e:
                logger.warning("[%s] Erreur '%s' : %s", brand, item.get("title"), e)

        logger.info("[%s] Total : %d produits", brand, len(all_products))
        return all_products
