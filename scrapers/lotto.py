# =============================================================
#  scrapers/lotto.py -- Scraper Lotto Sport (Shopify)
#
#  Site : lottosport.com (catalogue global EN)
#  API  : /collections/{handle}/products.json
#
#  Specificite : tailles standard Shopify (XS, S, M, L, XL…)
#  Couleur     : option Shopify "Color" native + extraction titre
#  Sexe        : infere depuis le titre (tags vides chez Lotto)
# =============================================================

import re
import logging
from typing import List, Optional

from scrapers.base import BaseScraper
from models import Product

logger = logging.getLogger(__name__)

BASE_URL  = "https://www.lottosport.com"
PAGE_SIZE = 250

SIZE_LABELS = {
    "XXS", "XS", "S", "M", "L", "XL", "XXL", "XXXL", "3XL", "4XL", "5XL", "2XL",
    "34", "36", "38", "40", "42", "44", "46", "48", "50", "52",
    "2Y", "4Y", "6Y", "8Y", "10Y", "12Y", "14Y", "16Y",
    "3M", "6M", "9M", "12M", "18M", "24M",
    "39", "40", "41", "42", "43", "44", "45", "46",
}

COLOR_KEYWORDS = sorted([
    "black beauty", "brilliant white", "optical white", "off white",
    "navy blue", "royal blue", "sky blue", "light blue", "dark blue", "electric blue",
    "forest green", "olive green", "dark green", "bright green",
    "bright red", "dark red", "all black", "all white",
    "bright cyan", "safety yellow", "fiesta red", "ultra marine",
    "heather blue", "pine green", "clay red",
    "black", "white", "navy", "blue", "red", "green",
    "grey", "gray", "charcoal", "anthracite",
    "orange", "yellow", "pink", "purple", "violet", "bordeaux", "burgundy",
    "beige", "cream", "ivory", "ecru", "camel",
    "brown", "tan", "khaki", "olive",
    "multicolor", "colorblock",
], key=len, reverse=True)

EXCLUDED_TYPES = {
    "ball", "balls", "soccer ball", "football", "boot", "boots", "shoe", "shoes",
    "sneaker", "sneakers", "bag", "bags", "backpack", "sock", "socks",
    "cap", "hat", "glove", "gloves", "scarf", "wristband",
    "bottle", "towel", "umbrella", "flip flop", "sandal", "shin guard",
    "goalkeeper", "shin",
}

# Catalogue : (genre, sexe, handle)
# NB : seules "all" et "sale" retournent des produits sur lottosport.com.
# Le sexe est infere depuis le titre car les tags ne l'indiquent pas.
LOTTO_CATALOG = [
    ("Adulte", "Mixte", "all"),
    ("Adulte", "Mixte", "sale"),
]


class LottoScraper(BaseScraper):
    BRAND_SOURCE = "Lotto"

    # ------------------------------------------------------------------
    def _fetch_collection(self, handle: str) -> List[dict]:
        all_items: List[dict] = []
        page = 1
        while True:
            url = f"{BASE_URL}/collections/{handle}/products.json?limit={PAGE_SIZE}&page={page}"
            try:
                resp = self.session.get(url, timeout=20)
                if resp.status_code != 200:
                    logger.warning(f"[Lotto] {handle} p{page} -> HTTP {resp.status_code}")
                    break
                data = resp.json()
            except Exception as e:
                logger.warning(f"[Lotto] Erreur {handle} p{page} : {e}")
                break
            products = data.get("products", [])
            if not products:
                break
            all_items.extend(products)
            logger.info(f"[Lotto] {handle} page {page} -> {len(products)} produits")
            if len(products) < PAGE_SIZE:
                break
            page += 1
            self.sleep(0.5, 1.0)
        return all_items

    # ------------------------------------------------------------------
    def _is_size(self, val: str) -> bool:
        if not val:
            return False
        clean = val.strip().upper()
        if clean in SIZE_LABELS:
            return True
        if re.match(r'^\d{1,2}[-\/]\d{1,2}[YA]?$', clean):
            return True
        return False

    # ------------------------------------------------------------------
    def _is_clothing(self, item: dict) -> bool:
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
            "trousers", "jogger", "chino", "overcoat", "tee shirt",
            "training", "sport top", "sport pant", "sweater", "sweatpant",
        ]
        return any(k in combined for k in clothing_keywords)

    # ------------------------------------------------------------------
    def _infer_sexe_from_title(self, name: str, default_sexe: str) -> str:
        """Infere le sexe depuis le titre — les tags Lotto sont vides."""
        name_lower = name.lower()
        if any(k in name_lower for k in ["men's", "mens ", "man's", " men "]):
            return "Homme"
        if any(k in name_lower for k in ["women's", "womens ", "woman's", " women "]):
            return "Femme"
        if any(k in name_lower for k in ["kid", "youth", "junior", "baby", "boy", "girl"]):
            return "Mixte"
        return default_sexe

    # ------------------------------------------------------------------
    def _infer_sexe_from_tags(self, tags: List[str], default_sexe: str) -> str:
        tags_lower = [t.lower() for t in tags]
        if any(t in tags_lower for t in ["man", "men", "mens", "homme", "uomo"]):
            return "Homme"
        if any(t in tags_lower for t in ["woman", "women", "womens", "femme", "donna"]):
            return "Femme"
        if any(t in tags_lower for t in ["kid", "kids", "child", "children",
                                          "junior", "baby", "enfant"]):
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
        2. Apres le tiret dans le titre  ex: "Delta Jacket - Black/White" -> "Black"
        3. Description
        """
        options     = item.get("options", [])
        title       = item.get("title", "")
        description = re.sub(r'<[^>]+>', '', item.get("body_html", "") or "").strip()

        for opt in options:
            if opt.get("name", "").lower() in ("color", "colour", "colore", "couleur"):
                vals = opt.get("values", [])
                if vals and vals[0].upper() not in ("DEFAULT TITLE", ""):
                    return vals[0].strip().capitalize()

        if ' - ' in title:
            color_part = title.split(' - ', 1)[1].strip()
            first = color_part.split('/')[0].strip()
            color = self._find_color_in_text(first)
            if color:
                return color
            if first and len(first) < 30:
                return first.capitalize()

        if description:
            color = self._find_color_in_text(description)
            if color:
                return color

        return None

    # ------------------------------------------------------------------
    def _infer_style_lotto(self, name: str, description: str = "") -> str:
        """
        Regles de style specifiques Lotto (titres EN).
        On travaille uniquement sur le NOM du produit pour eviter les
        faux positifs depuis la description (ex: 'wardrobe' → 'Robe').
        Ordre : du plus specifique au plus general.
        """
        n = name.lower()

        # Hauts
        if any(k in n for k in ["t-shirt", "tee", "short sleeve", "long sleeve"]):
            return "T-shirt"
        if any(k in n for k in ["hoodie", "hoody", "full zip hooded", "pullover hood",
                                  "zip hoodie", "zip hoody"]):
            return "Hoodie"
        if any(k in n for k in ["crewneck", "crew neck", "crew", "1/4 zip", "quarter zip"]):
            return "Sweat"
        if any(k in n for k in ["sweater", "sweatshirt"]):
            return "Sweat"
        if "pullover" in n:
            return "Pull"

        # Bas
        if any(k in n for k in ["sweatpant", "sweat pant", "track pant", "jogger",
                                  "trouser", "pant"]) and "short" not in n:
            return "Pantalon"
        if any(k in n for k in ["short", "sweatshort"]):
            return "Short"

        # Vestes
        if any(k in n for k in ["track jacket", "zip jacket", "jacket", "windbreaker"]):
            return "Veste"

        # Fallback sur base.py SANS description pour eviter wardrobe/robe
        return self.infer_style(name, "")

    # ------------------------------------------------------------------
    def _infer_categorie_lotto(self, name: str, p_type: str) -> str:
        """
        Regles de categorie specifiques Lotto (titres EN).
        Travaille uniquement sur le nom pour eviter les faux positifs description.
        """
        n = name.lower()

        if p_type == "Chaussures":
            return "Autre"

        # Manteau/Veste
        if any(k in n for k in ["jacket", "windbreaker", "parka", "coat"]):
            return "Manteau/Veste"

        # Bas
        if any(k in n for k in ["pant", "short", "jogger", "trouser", "legging"]):
            return "Bas"

        # Haut — tout le reste des vetements
        if any(k in n for k in ["tee", "t-shirt", "shirt", "hoodie", "hoody",
                                  "sweater", "sweatshirt", "crewneck", "crew neck",
                                  "crew", "pullover", "1/4 zip", "quarter zip", "top",
                                  "jersey", "vest", "polo", "long sleeve"]):
            return "Haut"

        return "Autre"

    # ------------------------------------------------------------------
    def _parse_product(self, item: dict, genre: str, sexe: str) -> Optional[Product]:
        name        = item.get("title", "Inconnu").strip()
        description = re.sub(r'<[^>]+>', '', item.get("body_html", "") or "").strip()
        ptype       = item.get("product_type", "")
        tags        = item.get("tags", [])
        handle      = item.get("handle", "")
        url         = f"{BASE_URL}/products/{handle}"
        options     = item.get("options", [])

        # Infer sexe : d'abord depuis le titre, puis les tags
        if sexe == "Mixte":
            sexe = self._infer_sexe_from_title(name, "Mixte")
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
                    size = val.upper()
            elif size_idx is None and len(options) == 1 and opts[0]:
                val = opts[0].strip()
                if self._is_size(val):
                    size = val.upper()

            if size and size not in all_tailles:
                all_tailles.append(size)

        is_shoe = any(
            k in name.lower() or k in ptype.lower()
            for k in ["shoe", "sneaker", "boot", "chaussure", "basket", "footwear", "cleats"]
        )
        p_type = "Chaussures" if is_shoe else "Vêtement"

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
            sizes        = [],
            taille       = taille_out,
            color        = color,
            rating       = None,
            type         = p_type,
            categorie    = self._infer_categorie_lotto(name, p_type),
            style        = self._infer_style_lotto(name),
            image        = main_image,
            url          = url,
            brand_source = self.BRAND_SOURCE,
        )

    # ------------------------------------------------------------------
    def run(self) -> List[Product]:
        all_products: List[Product] = []
        seen_handles: set = set()

        for genre, sexe, handle in LOTTO_CATALOG:
            logger.info(f"[Lotto] -- {genre} / {sexe} ({handle}) --")
            raw_items = self._fetch_collection(handle)
            logger.info(f"[Lotto] {len(raw_items)} produits bruts")

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
                    logger.warning(f"[Lotto] Erreur '{item.get('title')}' : {e}")

            self.sleep(1.0, 2.0)

        logger.info(f"[Lotto] -- Total : {len(all_products)} produits --")
        return all_products