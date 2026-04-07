# =============================================================
#  scrapers/kappa.py -- Scraper Kappa (Shopify)
#
#  Site : kappa.com (catalogue global EN)
#  API  : /collections/{handle}/products.json
#
#  Specificite : tailles au format "Adult | S", "Kid | 10Y"
#  Couleur     : option Shopify "Color" native
# =============================================================

import re
import logging
from typing import List, Optional

from pipeline.scrapers.base import BaseScraper
from pipeline.models import Product

logger = logging.getLogger(__name__)

BASE_URL  = "https://www.kappa.com"
PAGE_SIZE = 250

SIZE_LABELS = {
    "XXS", "XS", "S", "M", "L", "XL", "XXL", "XXXL", "3XL", "4XL", "5XL",
    "2XL", "6XL",
    "34", "36", "38", "40", "42", "44", "46", "48", "50", "52",
    "T1", "T2", "T3", "T4",
    # Tailles enfant
    "2", "4", "6", "8", "10", "12", "14", "16",
    "2Y", "4Y", "6Y", "8Y", "10Y", "12Y", "14Y", "16Y",
    "3M", "6M", "9M", "12M", "18M", "24M",
}

COLOR_KEYWORDS = sorted([
    "black beauty", "brilliant white", "optical white", "off white",
    "navy blue", "royal blue", "sky blue", "light blue", "dark blue", "electric blue",
    "forest green", "olive green", "dark green", "bright green",
    "bright red", "dark red",
    "black", "white", "navy", "blue", "red", "green",
    "grey", "gray", "charcoal", "anthracite",
    "orange", "yellow", "pink", "purple", "violet", "bordeaux", "burgundy",
    "beige", "cream", "ivory", "ecru", "camel",
    "brown", "tan", "khaki", "olive",
    "multicolor", "colorblock",
    # francais
    "noir", "blanc", "bleu", "rouge", "vert", "gris", "rose",
    "marine", "turquoise", "corail",
], key=len, reverse=True)

# Mots-cles pour filtrer les produits non-vetements
EXCLUDED_TYPES = {
    "ball", "balls", "soccer ball", "football", "boot", "boots", "shoe", "shoes",
    "sneaker", "sneakers", "bag", "bags", "backpack", "sock", "socks",
    "cap", "hat", "glove", "gloves", "scarf", "wristband", "paddle",
    "bottle", "towel", "umbrella", "flip flop", "sandal",
}

# Catalogue : (genre, sexe, handle)
KAPPA_CATALOG = [
    # Homme - collections specifiques
    ("Adulte", "Homme", "back-to-gym-men"),
    ("Adulte", "Homme", "active-jersey-man"),
    ("Adulte", "Homme", "black-friday-selection-man"),
    # Femme - collections specifiques
    ("Adulte", "Femme", "back-to-gym-women"),
    # Mixte adulte - sexe infere depuis tags
    ("Adulte", "Mixte", "athleisure"),
    ("Adulte", "Mixte", "athleisure-sportswear-collection"),
    ("Adulte", "Mixte", "basics"),
    ("Adulte", "Mixte", "banda"),
    ("Adulte", "Mixte", "basketball"),
    ("Adulte", "Mixte", "alpine-f1"),
    # Enfant
    ("Enfant", "Mixte", "baby-3-24-months"),
]


class KappaScraper(BaseScraper):
    BRAND_SOURCE = "Kappa"

    # ------------------------------------------------------------------
    def _fetch_collection(self, handle: str) -> List[dict]:
        all_items: List[dict] = []
        page = 1
        while True:
            url = f"{BASE_URL}/collections/{handle}/products.json?limit={PAGE_SIZE}&page={page}"
            try:
                resp = self.session.get(url, timeout=20)
                if resp.status_code != 200:
                    logger.warning(f"[Kappa] {handle} p{page} -> HTTP {resp.status_code}")
                    break
                data = resp.json()
            except Exception as e:
                logger.warning(f"[Kappa] Erreur {handle} p{page} : {e}")
                break
            products = data.get("products", [])
            if not products:
                break
            all_items.extend(products)
            logger.info(f"[Kappa] {handle} page {page} -> {len(products)} produits")
            if len(products) < PAGE_SIZE:
                break
            page += 1
            self.sleep(0.5, 1.0)
        return all_items

    # ------------------------------------------------------------------
    def _normalize_size(self, val: str) -> str:
        """
        Kappa utilise le format "Adult | S", "Kid | 10Y", "Baby | 6M".
        On extrait uniquement la partie apres le pipe.
        """
        if '|' in val:
            return val.split('|', 1)[1].strip()
        return val.strip()

    # ------------------------------------------------------------------
    def _is_size(self, val: str) -> bool:
        if not val:
            return False
        # Normalise d'abord ("Adult | S" → "S")
        clean = self._normalize_size(val).upper()
        if clean in SIZE_LABELS:
            return True
        # Tailles enfant format "3-4Y", "5-6Y"
        if re.match(r'^\d{1,2}[-\/]\d{1,2}[YA]?$', clean):
            return True
        return False

    # ------------------------------------------------------------------
    def _is_clothing(self, item: dict) -> bool:
        """Filtre les non-vetements (chaussures, accessoires, ballons...)."""
        name  = item.get("title", "").lower()
        ptype = item.get("product_type", "").lower()
        tags  = [t.lower() for t in item.get("tags", [])]
        combined = f"{name} {ptype} " + " ".join(tags)

        for excl in EXCLUDED_TYPES:
            if excl in combined:
                return False

        clothing_keywords = [
            "jacket", "hoodie", "sweatshirt", "t-shirt", "tshirt", "polo",
            "pants", "shorts", "legging", "tracksuit", "jersey", "vest",
            "sweat", "veste", "pantalon", "short", "maillot", "pull",
            "tee", "top", "shirt", "coat", "windbreaker", "parka",
            "trousers", "jogger", "chino", "overcoat",
        ]
        return any(k in combined for k in clothing_keywords)

    # ------------------------------------------------------------------
    def _infer_sexe_from_tags(self, tags: List[str], default_sexe: str) -> str:
        tags_lower = [t.lower() for t in tags]
        if any(t in tags_lower for t in ["man", "men", "homme", "uomo", "hombre"]):
            return "Homme"
        if any(t in tags_lower for t in ["woman", "women", "femme", "donna", "mujer"]):
            return "Femme"
        if any(t in tags_lower for t in ["kid", "kids", "child", "children",
                                          "enfant", "bambino", "junior", "baby"]):
            return "Mixte"
        return default_sexe

    # ------------------------------------------------------------------
    def _find_color_in_text(self, text: str) -> Optional[str]:
        text_lower = text.lower()
        for color in COLOR_KEYWORDS:
            if re.search(r'\b' + re.escape(color) + r'\b', text_lower):
                return color.capitalize()
        return None

    # ------------------------------------------------------------------
    def _extract_color(self, item: dict) -> Optional[str]:
        """
        Priorite :
        1. Option Shopify "Color" / "Colour" / "Colore"
        2. Apres le tiret dans le titre ex: "Track Jacket - Black/White" -> "Black"
        3. Description
        """
        options     = item.get("options", [])
        title       = item.get("title", "")
        description = re.sub(r'<[^>]+>', '', item.get("body_html", "") or "").strip()

        # Priorite 1 : option Color Shopify
        for opt in options:
            if opt.get("name", "").lower() in ("color", "colour", "colore", "couleur"):
                vals = opt.get("values", [])
                if vals and vals[0].upper() not in ("DEFAULT TITLE", ""):
                    return vals[0].strip().capitalize()

        # Priorite 2 : apres tiret dans le titre
        if ' - ' in title:
            color_part = title.split(' - ', 1)[1].strip()
            first = color_part.split('/')[0].strip()
            color = self._find_color_in_text(first)
            if color:
                return color
            if first and len(first) < 30:
                return first.capitalize()

        # Priorite 3 : description
        if description:
            color = self._find_color_in_text(description)
            if color:
                return color

        return None

    # ------------------------------------------------------------------
    def _parse_product(self, item: dict, genre: str, sexe: str) -> Optional[Product]:
        name        = item.get("title", "Inconnu").strip()
        description = re.sub(r'<[^>]+>', '', item.get("body_html", "") or "").strip()
        ptype       = item.get("product_type", "")
        tags        = item.get("tags", [])
        handle      = item.get("handle", "")
        url         = f"{BASE_URL}/products/{handle}"
        options     = item.get("options", [])

        # Infer sexe pour collections mixtes
        if sexe == "Mixte":
            sexe = self._infer_sexe_from_tags(tags, "Mixte")

        images     = item.get("images", [])
        main_image = images[0].get("src") if images else None

        color = self._extract_color(item)

        # Index option taille
        size_idx = None
        for i, opt in enumerate(options):
            if opt.get("name", "").lower() in ("size", "taille", "sizes", "taglia", "talla"):
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
                    size = self._normalize_size(val)
            elif size_idx is None and len(options) == 1 and opts[0]:
                val = opts[0].strip()
                if self._is_size(val):
                    size = self._normalize_size(val)

            if size and size not in all_tailles:
                all_tailles.append(size)

        # Type produit
        is_shoe = any(
            k in name.lower() or k in ptype.lower()
            for k in ["shoe", "sneaker", "boot", "chaussure", "basket", "footwear"]
        )
        p_type = "Chaussures" if is_shoe else "V\u00eatement"

        sizes_out  = []
        taille_out = []
        if is_shoe:
            taille_out = all_tailles
        else:
            valid      = {"XS", "S", "M", "L", "XL", "XXL", "XXXL", "2XL", "3XL", "4XL",
                          "34", "36", "38", "40", "42", "44", "46"}
            taille_out = [s.upper() for s in all_tailles if s.upper() in valid] or all_tailles

        return Product(
            name         = name,
            price_value  = price,
            currency     = "EUR",
            description  = description,
            genre        = "Enfant" if genre == "Enfant" else "Adulte",
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
        seen_handles: set = set()

        for genre, sexe, handle in KAPPA_CATALOG:
            logger.info(f"[Kappa] -- {genre} / {sexe} ({handle}) --")
            raw_items = self._fetch_collection(handle)
            logger.info(f"[Kappa] {len(raw_items)} produits bruts")

            for item in raw_items:
                h = item.get("handle", "")
                if h in seen_handles:
                    continue
                seen_handles.add(h)

                if not self._is_clothing(item):
                    continue

                try:
                    product = self._parse_product(item, genre, sexe)
                    if product:
                        all_products.append(product)
                        logger.info(
                            f"  OK {product.name[:50]} | "
                            f"sexe={product.sexe} | color={product.color} | "
                            f"taille={product.taille[:3]} | {product.price_value} EUR"
                        )
                except Exception as e:
                    logger.warning(f"[Kappa] Erreur '{item.get('title')}' : {e}")

            self.sleep(1.0, 2.0)

        logger.info(f"[Kappa] -- Total : {len(all_products)} produits --")
        return all_products