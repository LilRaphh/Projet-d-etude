# =============================================================
#  scrapers/lecoqsportif.py -- Scraper Le Coq Sportif (Shopify)
#
#  API Shopify publique : /collections/{handle}/products.json
#  Structure LCS : 1 option "Taille" seulement, couleur dans description
# =============================================================

import re
import logging
from typing import List, Optional

from scrapers.base import BaseScraper
from models import Product

logger = logging.getLogger(__name__)

BASE_URL  = "https://www.lecoqsportif.com"
PAGE_SIZE = 250

SIZE_LABELS = {
    "XXS", "XS", "S", "M", "L", "XL", "XXL", "XXXL", "3XL", "4XL", "5XL",
    "34", "36", "38", "40", "42", "44", "46", "48", "50", "52",
    "36 2/3", "37 1/3", "38 2/3", "39 1/3", "40 2/3",
    "41 1/3", "42 2/3", "43 1/3", "44 2/3", "45 1/3",
    "T1", "T2", "T3", "T4",
}

# Couleurs triees du plus long au plus court pour matcher "bleu marine" avant "bleu"
COLOR_KEYWORDS = sorted([
    "new optical white", "optical white", "sky captain", "dress blues",
    "bleu electrique", "bleu marine", "bleu ciel", "bleu nuit", "bleu roi",
    "gris chine", "gris chine clair", "rouge electro", "rio red",
    "noir", "black", "blanc", "white",
    "bleu", "blue", "marine", "navy",
    "rouge", "red",
    "vert", "green", "kaki", "khaki", "olive", "safari", "univert",
    "gris", "grey", "gray", "anthracite",
    "beige", "camel", "ecru", "creme",
    "rose", "pink",
    "jaune", "yellow", "orange",
    "violet", "purple", "bordeaux", "burgundy",
    "multicolore", "colorblock",
], key=len, reverse=True)

# Zones a masquer avant la recherche de couleur (couleurs du logo, pas du vetement)
NOISE_PATTERNS = [
    r'couleurs?\s+\w+(?:[,\s/]+\w+)+',   # "couleurs rouge, vert et jaune"
    r'logo.*?(?:rouge|vert|jaune|bleu|noir|blanc)',
    r'imprim[eé].*?(?:rouge|vert|jaune|bleu|noir|blanc)',
]

LCS_CATALOG = [
    ("Adulte", "Homme", "vetements-homme"),
    ("Adulte", "Femme", "vetements-femme"),
    ("Enfant", "Fille", "vetements-enfant"),
]


class LeCoqSportifScraper(BaseScraper):
    BRAND_SOURCE = "Le Coq Sportif"

    # ------------------------------------------------------------------
    def _fetch_collection(self, handle: str) -> List[dict]:
        all_items: List[dict] = []
        page = 1
        while True:
            url = f"{BASE_URL}/collections/{handle}/products.json?limit={PAGE_SIZE}&page={page}"
            try:
                resp = self.session.get(url, timeout=20)
                if resp.status_code != 200:
                    logger.warning(f"[LCS] {handle} p{page} -> HTTP {resp.status_code}")
                    break
                data = resp.json()
            except Exception as e:
                logger.warning(f"[LCS] Erreur {handle} p{page} : {e}")
                break
            products = data.get("products", [])
            if not products:
                break
            all_items.extend(products)
            logger.info(f"[LCS] {handle} page {page} -> {len(products)} produits")
            if len(products) < PAGE_SIZE:
                break
            page += 1
            self.sleep(0.5, 1.0)
        return all_items

    # ------------------------------------------------------------------
    def _infer_sexe_from_tags(self, tags: List[str], default_sexe: str) -> str:
        tags_lower = [t.lower() for t in tags]
        if any(t in tags_lower for t in ["garcon", "boy", "boys"]):
            return "Garcon"
        if any(t in tags_lower for t in ["fille", "girl", "girls"]):
            return "Fille"
        return default_sexe

    # ------------------------------------------------------------------
    def _is_size(self, val: str) -> bool:
        if not val:
            return False
        return val.upper() in SIZE_LABELS or (val.isdigit() and 28 <= int(val) <= 54)

    # ------------------------------------------------------------------
    def _find_color_in_text(self, text: str) -> Optional[str]:
        """Cherche la premiere couleur connue dans un texte (du plus long au plus court)."""
        text_lower = text.lower()
        for color in COLOR_KEYWORDS:
            if re.search(r'\b' + re.escape(color) + r'\b', text_lower):
                return color.capitalize()
        return None

    # ------------------------------------------------------------------
    def _extract_color(self, description: str, title: str) -> Optional[str]:
        """
        Extrait la couleur d'un produit LCS.

        Priorite :
        1. Pattern "Couleur : X" ou "Couleur X" dans les puces techniques
        2. Pattern "coloris X" -- on matche uniquement les couleurs connues
           pour eviter "coloris bordeaux affirme un style..."
        3. Scan ligne par ligne apres masquage des zones logo/impression
        4. Fallback sur le titre (produits avec code SKU)
        """
        if not description:
            return self._find_color_in_text(title) if title else None

        desc_lower = description.lower()

        # Priorite 1 : "Couleur : X" ou "Couleur X" (avec ou sans deux-points)
        m = re.search(r'couleur\s*:?\s*(\S+(?:\s+\S+)?)', desc_lower)
        if m:
            candidate = m.group(1).strip().rstrip('.,;')
            for color in COLOR_KEYWORDS:
                if candidate.startswith(color):
                    return color.capitalize()

        # Priorite 2 : "coloris X" -- capture limitee aux couleurs connues
        m = re.search(r'(?:en\s+)?coloris\s+(\S+(?:\s+\S+)?)', desc_lower)
        if m:
            candidate = m.group(1).strip().rstrip('.,;')
            for color in COLOR_KEYWORDS:
                if candidate.startswith(color):
                    return color.capitalize()

        # Priorite 3 : scan ligne par ligne apres masquage des zones bruitees
        desc_masked = desc_lower
        for pattern in NOISE_PATTERNS:
            desc_masked = re.sub(pattern, ' [MASK] ', desc_masked)

        for line in desc_masked.split('\n'):
            line = line.strip().lstrip('-').strip()
            if not line:
                continue
            color = self._find_color_in_text(line)
            if color:
                return color

        # Priorite 4 : titre produit (codes SKU ex: "sky captain/rio red")
        return self._find_color_in_text(title) if title else None

    # ------------------------------------------------------------------
    def _parse_product(self, item: dict, genre: str, sexe: str) -> List[Product]:
        name         = item.get("title", "Inconnu").strip()
        description  = re.sub(r'<[^>]+>', '', item.get("body_html", "") or "").strip()
        product_type = item.get("product_type", "")
        tags         = item.get("tags", [])
        handle       = item.get("handle", "")
        url          = f"{BASE_URL}/products/{handle}"

        if genre == "Enfant":
            sexe = self._infer_sexe_from_tags(tags, sexe)

        images     = item.get("images", [])
        main_image = images[0].get("src") if images else None

        # Extraction couleur
        color = self._extract_color(description, name)

        # Detection index option taille
        options  = item.get("options", [])
        size_idx = None
        for i, opt in enumerate(options):
            if opt.get("name", "").lower() in ("taille", "size", "pointure", "sizes", "size / taille"):
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

        # Type produit -- avec accent pour correspondre au schema MongoDB
        is_shoe = any(
            k in name.lower() or k in product_type.lower()
            for k in ["chaussure", "basket", "sneaker", "running", "tennis", "spike", "crampons", "boot"]
        )
        p_type = "Chaussures" if is_shoe else "V\u00eatement"

        if is_shoe:
            sizes_out  = [int(float(re.search(r'(\d+\.?\d*)', s).group(1)))
                          for s in all_tailles if re.search(r'(\d+\.?\d*)', s)]
            taille_out = []
        else:
            sizes_out  = []
            valid      = {"XS", "S", "M", "L", "XL", "XXL", "XXXL", "34", "36", "38", "40", "42", "44", "46"}
            taille_out = [s.upper() for s in all_tailles if s.upper() in valid] or all_tailles

        return [Product(
            name         = name,
            price_value  = price,
            currency     = "EUR",
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
        )]

    # ------------------------------------------------------------------
    def run(self) -> List[Product]:
        all_products: List[Product] = []

        for genre, sexe, handle in LCS_CATALOG:
            logger.info(f"[LCS] -- Catalogue : {genre} / {sexe} ({handle}) --")
            raw_items = self._fetch_collection(handle)
            logger.info(f"[LCS] {len(raw_items)} produits bruts recuperes")

            for item in raw_items:
                try:
                    products = self._parse_product(item, genre, sexe)
                    for p in products:
                        all_products.append(p)
                        logger.info(
                            f"  OK {p.name[:50]} | "
                            f"color={p.color} | taille={p.taille} | {p.price_value} EUR"
                        )
                except Exception as e:
                    logger.warning(f"[LCS] Erreur parsing '{item.get('title')}' : {e}")

            self.sleep(1.0, 2.0)

        logger.info(f"[LCS] -- Total : {len(all_products)} produits --")
        return all_products