# =============================================================
#  scrapers/tacchini.py — Scraper Sergio Tacchini (Shopify)
#
#  Site US officiel : sergiotacchini.com
#  API Shopify : /collections/{handle}/products.json
#  Devise : USD (le site est US-only)
# =============================================================

import re
import logging
from typing import List, Optional

from pipeline.scrapers.base import BaseScraper
from pipeline.models import Product

logger = logging.getLogger(__name__)

BASE_URL  = "https://www.sergiotacchini.com"
PAGE_SIZE = 250

SIZE_LABELS = {
    "XXS", "XS", "S", "M", "L", "XL", "XXL", "XXXL", "3XL", "4XL",
    "34", "36", "38", "40", "42", "44", "46", "48", "50",
    "T1", "T2", "T3", "T4",
}

COLOR_KEYWORDS = sorted([
    "navy blue", "royal blue", "sky blue", "light blue", "dark blue",
    "forest green", "olive green", "dark green", "light green",
    "dark red", "bright red", "burnt orange",
    "jet black", "off white", "ivory white",
    "black", "white", "navy", "blue", "red", "green",
    "grey", "gray", "charcoal", "anthracite",
    "orange", "yellow", "pink", "purple", "burgundy", "bordeaux",
    "beige", "cream", "ivory", "ecru", "camel",
    "brown", "tan", "khaki", "olive",
    "multicolor", "colorblock", "stripe",
    # francais aussi au cas ou
    "noir", "blanc", "bleu", "rouge", "vert", "gris", "rose",
], key=len, reverse=True)

# Catalogue : (genre, sexe, handle)
ST_CATALOG = [
    ("Adulte", "Homme", "mens-jackets"),
    ("Adulte", "Homme", "mens-sweaters-and-hoodies"),
    ("Adulte", "Homme", "mens-pants-and-joggers"),
    ("Adulte", "Homme", "polos-and-shirts"),
    ("Adulte", "Homme", "mens-t-shirts"),
    ("Adulte", "Homme", "mens-shorts"),
    ("Adulte", "Femme", "womens-jackets"),
    ("Adulte", "Femme", "womens-sweaters-and-hoodies"),
    ("Adulte", "Femme", "womens-pants-and-joggers"),
    ("Adulte", "Femme", "leggings"),
    ("Adulte", "Femme", "womens-t-shirts"),
    ("Adulte", "Femme", "womens-shorts"),
]


class TacchiniScraper(BaseScraper):
    BRAND_SOURCE = "Sergio Tacchini"

    # ------------------------------------------------------------------
    def _fetch_collection(self, handle: str) -> List[dict]:
        all_items: List[dict] = []
        page = 1
        while True:
            url = f"{BASE_URL}/collections/{handle}/products.json?limit={PAGE_SIZE}&page={page}"
            try:
                resp = self.session.get(url, timeout=20)
                if resp.status_code != 200:
                    logger.warning(f"[ST] {handle} p{page} -> HTTP {resp.status_code}")
                    break
                data = resp.json()
            except Exception as e:
                logger.warning(f"[ST] Erreur {handle} p{page} : {e}")
                break
            products = data.get("products", [])
            if not products:
                break
            all_items.extend(products)
            logger.info(f"[ST] {handle} page {page} -> {len(products)} produits")
            if len(products) < PAGE_SIZE:
                break
            page += 1
            self.sleep(0.5, 1.0)
        return all_items

    # ------------------------------------------------------------------
    def _is_size(self, val: str) -> bool:
        if not val:
            return False
        return val.upper() in SIZE_LABELS or (val.replace('.', '').isdigit() and 28 <= float(val) <= 54)

    # ------------------------------------------------------------------
    def _find_color_in_text(self, text: str) -> Optional[str]:
        text_lower = text.lower()
        for color in COLOR_KEYWORDS:
            if re.search(r'\b' + re.escape(color) + r'\b', text_lower):
                return color.capitalize()
        return None

    # ------------------------------------------------------------------
    def _extract_color(self, description: str, title: str, options: List[dict]) -> Optional[str]:
        """
        Priorite :
        1. Option Shopify nommee "Color" ou "Colour"
        2. Titre du produit (ex: "Club Tech Track Jacket - Navy/White")
           -> prend la partie apres le tiret
        3. Description
        """
        # Priorite 1 : option Color Shopify
        for opt in options:
            if opt.get("name", "").lower() in ("color", "colour", "couleur"):
                vals = opt.get("values", [])
                if vals:
                    # Prend le premier coloris (le principal)
                    return vals[0].strip().capitalize()

        # Priorite 2 : apres le tiret dans le titre ex: "Track Jacket - Navy/White"
        if title and ' - ' in title:
            color_part = title.split(' - ', 1)[1].strip()
            # Prend le premier coloris si format "Navy/White"
            first_color = color_part.split('/')[0].strip()
            color = self._find_color_in_text(first_color)
            if color:
                return color

        # Priorite 3 : scan de la description
        if description:
            color = self._find_color_in_text(description)
            if color:
                return color

        return None

    # ------------------------------------------------------------------
    def _parse_product(self, item: dict, genre: str, sexe: str) -> Optional[Product]:
        name         = item.get("title", "Inconnu").strip()
        description  = re.sub(r'<[^>]+>', '', item.get("body_html", "") or "").strip()
        product_type = item.get("product_type", "")
        handle       = item.get("handle", "")
        url          = f"{BASE_URL}/products/{handle}"
        options      = item.get("options", [])

        images     = item.get("images", [])
        main_image = images[0].get("src") if images else None

        # Extraction couleur
        color = self._extract_color(description, name, options)

        # Index option taille
        size_idx = None
        for i, opt in enumerate(options):
            if opt.get("name", "").lower() in ("size", "taille", "sizes"):
                size_idx = i

        # Collecte tailles + prix
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
                if self._is_size(val):
                    size = val
            elif size_idx is None and len(options) == 1 and opts[0]:
                val = opts[0].strip()
                if self._is_size(val):
                    size = val

            if size and size not in all_tailles:
                all_tailles.append(size)

        # Type produit
        is_shoe = any(
            k in name.lower() or k in product_type.lower()
            for k in ["shoe", "sneaker", "boot", "chaussure", "basket"]
        )
        p_type = "Chaussures" if is_shoe else "V\u00eatement"

        if is_shoe:
            sizes_out  = [int(float(re.search(r'(\d+\.?\d*)', s).group(1)))
                          for s in all_tailles if re.search(r'(\d+\.?\d*)', s)]
            taille_out = []
        else:
            sizes_out  = []
            valid      = {"XS", "S", "M", "L", "XL", "XXL", "XXXL"}
            taille_out = [s.upper() for s in all_tailles if s.upper() in valid] or all_tailles

        return Product(
            name         = name,
            price_value  = price,
            currency     = "USD",
            description  = description,
            genre        = genre,
            sexe         = sexe,
            sizes        = sizes_out,
            taille       = taille_out,
            color        = color,
            rating       = None,
            type         = p_type,
            categorie    = self.infer_categorie(name, description, p_type),
            style        = self.infer_style(name, description),
            image        = main_image,
            url          = url,
            brand_source = self.BRAND_SOURCE,
        )

    # ------------------------------------------------------------------
    def run(self) -> List[Product]:
        all_products: List[Product] = []
        seen_handles = set()

        for genre, sexe, handle in ST_CATALOG:
            logger.info(f"[ST] -- Catalogue : {genre} / {sexe} ({handle}) --")
            raw_items = self._fetch_collection(handle)
            logger.info(f"[ST] {len(raw_items)} produits bruts recuperes")

            for item in raw_items:
                h = item.get("handle", "")
                if h in seen_handles:
                    continue  # evite les doublons inter-collections
                seen_handles.add(h)

                try:
                    product = self._parse_product(item, genre, sexe)
                    if product:
                        all_products.append(product)
                        logger.info(
                            f"  OK {product.name[:55]} | "
                            f"color={product.color} | taille={product.taille} | {product.price_value} USD"
                        )
                except Exception as e:
                    logger.warning(f"[ST] Erreur parsing '{item.get('title')}' : {e}")

            self.sleep(1.0, 2.0)

        logger.info(f"[ST] -- Total : {len(all_products)} produits --")
        return all_products