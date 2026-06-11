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

# Product types Shopify clairement non-vestimentaires (case-insensitive substring match)
_NON_CLOTHING_TYPES = frozenset([
    # Maison & déco
    "maison", "home", "deco", "déco", "decoration", "décoration",
    "lighting", "luminaire", "furniture", "meuble", "objet", "objet déco",
    "bougie", "candle", "vase", "cadre", "frame",
    # Cuisine & table
    "cuisine", "kitchen", "table", "vaisselle", "tableware", "cookware",
    "ustensile", "couvert", "cutlery", "casserole", "poêle", "plat",
    "tasse", "mug", "assiette", "verre", "carafe",
    # Beauté & soin
    "beaute", "beauté", "beauty", "soin", "skincare", "parfum", "fragrance",
    "cosmetique", "cosmétique",
    # Papeterie & livres
    "papeterie", "stationery", "livre", "book", "carnet", "notebook",
    # Divers non-vêtement
    "jouet", "toy", "jeu", "game", "plant", "plante", "art", "print",
    "poster", "affiche", "outil", "tool",
])

# Si le product_type est vide mais que la catégorie inférée est "Autre" et qu'il
# n'y a aucune taille vestimentaire, c'est probablement du non-vestimentaire.
# Les sous-classes peuvent activer ce filtrage strict avec STRICT_CLOTHING = True.
SIZE_LABELS = {
    "XXS", "XS", "S", "M", "L", "XL", "XXL", "XXXL",
    "34", "36", "38", "40", "42", "44", "46", "48",
    "50", "52",
    "T1", "T2", "T3", "T4",
}

# Mots-clés présents dans les NOMS de produits non-vestimentaires —
# liste intentionnellement courte et précise pour éviter les faux positifs.
_NON_CLOTHING_NAME_KEYWORDS = frozenset([
    # Éclairage / déco murale
    "applique en", "applique murale", "applique porcelaine",
    "abat-jour", "lustre", "luminaire",
    # Rideaux / quincaillerie
    "anneaux de rideaux", "anneau de rideau", "rideau ",
    "tringle à rideaux", "patère", "porte-manteau",
    # Maison / déco
    "bougie", "candle", "vase", "coussin", "plaid", "nappe",
    "torchon", "plateau", "miroir", "cadre photo",
    # Cuisine / table
    "vaisselle", "assiette", "tasse", "mug", "carafe",
    "casserole", "théière", "cafetière", "saladier", "bowl ",
    # Entretien textile & soin — les descriptions mentionnent "pull/veste"
    # donc le double-Autre ne suffit pas, le nom est la seule source fiable
    "rasoir anti", "rasoir ", "défriseur", "détachant ",
    "brosse anti", "brosse à habits",
    # Beauté / cosmétiques
    "eau de toilette", "huile essentielle", "crème hydratante",
    "sérum ", "élixir ", "masque visage", "baume lèvres",
    # Pins & bijoux
    "badge ", "badge merci", "broche ",
    "médaille ", "médaille merci",
    # Maroquinerie & accessoires non-vestimentaires
    "porte-clé", "porte-clés", "porte clé", "keychain",
    "mallette", "valise", "sac à dos", "sac bandoulière",
    "portefeuille", "porte-monnaie",
    # Papeterie / édition
    "stylo", "agenda", "cahier de",
    # Plantes / jardinage
    "pot de fleurs", "plante verte",
])

# Mots qui, présents N'IMPORTE OÙ dans le candidat avant " – ",
# signalent un nom de produit plutôt qu'une marque.
_MERCI_NON_BRAND_WORDS = frozenset([
    # ── Vêtements (types, pas des marques) ───────────────────────────
    "bonnet", "bob", "casquette", "chapeau", "béret", "beanie",
    "chemise", "chemisier", "crewneck", "sweat", "pull", "pullover",
    "hoodie", "cardigan", "débardeur", "polo", "top",
    "t-shirt", "tee-shirt", "tee",
    "jean", "jeans", "pantalon", "chinos", "short", "legging", "jupe",
    "veste", "blazer", "manteau", "doudoune", "parka", "trench",
    "robe", "combinaison", "salopette", "kimono",
    "chaussettes", "chaussons", "chaussures", "sneakers", "basket",
    "bottines", "mocassins", "sandales", "escarpins",
    # ── Éclairage / luminaires ────────────────────────────────────────
    "lampe", "lampadaire", "applique", "lustre", "plafonnier",
    "spot", "liseuse", "veilleuse", "luminaire", "abat-jour",
    # ── Literie / linge de maison ─────────────────────────────────────
    "drap", "housse", "taie", "couette", "traversin", "oreiller",
    "plaid", "coussin", "serviette", "torchon", "nappe",
    # ── Vaisselle & cuisine ───────────────────────────────────────────
    "verre", "assiette", "bol", "tasse", "mug", "coupe", "flûte",
    "carafe", "pichet", "théière", "cafetière", "saladier", "plateau",
    "casserole", "poêle", "moule", "passoire", "fouet", "spatule",
    "couteau", "fourchette", "cuillère",
    # ── Déco / maison ────────────────────────────────────────────────
    "vase", "bougie", "bougeoir", "miroir", "cadre", "tableau",
    "sculpture", "objet", "panier", "corbeille",
    # ── Papeterie / édition ───────────────────────────────────────────
    "carnet", "cahier", "stylo", "crayon", "livre", "affiche",
    "poster", "calendrier", "agenda",
    # ── Audio / tech ─────────────────────────────────────────────────
    "enceinte", "casque",
    # ── Beauté / cosmétiques / parfumerie ─────────────────────────────
    "parfum", "cologne", "toilette",
    "crème", "sérum", "huile", "baume", "gel",
    "masque", "exfoliant", "lotion", "savon",
    "vernis", "fond", "rouge", "mascara",
    "diffuseur",
    # ── Alimentation ─────────────────────────────────────────────────
    "chocolat", "biscuit", "confiture", "café", "thé",
    "épices", "sel", "poivre", "miel", "sauce", "vinaigre",
    "barre",
    # ── Accessoires non-vestimentaires ───────────────────────────────
    "badge", "broche", "médaille", "bandana",
    "étole", "châle", "foulard",
    "bague", "collier", "bracelet", "pendentif", "boucles",
    "cabas", "sac", "pochette", "tote",
    "bouteille", "gourde", "thermos",
    "carte", "chariot", "banane",
])

# Un vrai nom de marque ne contient JAMAIS de prépositions/articles français au milieu.
_FRENCH_FUNCTION_WORDS = frozenset([
    "en", "de", "du", "des", "au", "aux",
    "la", "le", "les", "un", "une",
    "à", "par", "pour", "sur", "sous", "avec", "d",
])

_BRAND_CASING_MAP = {
    "carhartt wip":   "Carhartt WIP",
    "a.p.c":          "A.P.C.",
    "a.p.c.":         "A.P.C.",
    "apc":            "A.P.C.",
    "ami paris":      "AMI Paris",
    "amiparis":       "AMI Paris",
    "maison kitsune": "Maison Kitsuné",
    "maison kitsuné": "Maison Kitsuné",
    "épice":          "Épice",
    "epice":          "Épice",
}


def _normalize_brand(brand: str) -> str:
    return _BRAND_CASING_MAP.get(brand.lower(), brand)


def _looks_like_product_name(candidate: str) -> bool:
    """Retourne True si le candidat ressemble à un nom de produit (pas une marque)."""
    words = candidate.lower().split()
    if any(w in _MERCI_NON_BRAND_WORDS for w in words):
        return True
    if any(w in _FRENCH_FUNCTION_WORDS for w in words if w != "x"):
        return True
    return False


SHOE_KEYWORDS = [
    # Français
    "chaussure", "sneaker", "bottine", "mocassin", "botte", "espadrille",
    "sandale", "derby", "loafer", "mule", "sabot", "tong", "ballerine",
    "basket", "tennis",
    # Anglais (Shopify product_type courants)
    "shoe", "boot", "trainer", "pump", "heel", "footwear", "sneakers",
    "trainers", "sandal", "clog", "slipper", "oxford", "runner",
    # Termes running/sport
    "running shoe", "athletic shoe",
]


class ShopifyBaseScraper(BaseScraper):
    BASE_URL: str = ""
    BRAND_SOURCE: str = ""

    # Sexe par défaut — surcharger dans la sous-classe si la marque est mono-genre
    DEFAULT_GENRE: str = "Adulte"
    DEFAULT_SEXE: str = "Mixte"

    # Devise par défaut — surcharger si le store est en USD, GBP…
    CURRENCY: str = "EUR"

    # Mettre True pour les concept stores qui mélangent vêtements et non-vêtements.
    # Filtre les produits dont le product_type Shopify est clairement non-vestimentaire,
    # et les produits classés "Autre" sans aucune taille vestimentaire.
    STRICT_CLOTHING: bool = False

    # Mettre True pour les marques 100 % chaussures (Karhu, Filling Pieces…).
    # Tous les produits seront forcés en type "Chaussures" sans passer par SHOE_KEYWORDS.
    FORCE_SHOE: bool = False

    # Mettre True pour les concept stores multi-marques (Merci…).
    # Extrait la vraie marque depuis le titre "Marque – Nom produit – Couleur".
    EXTRACT_BRAND_FROM_NAME: bool = False

    @staticmethod
    def _split_brand_from_name(raw: str) -> tuple:
        """Extrait (brand, clean_name) depuis 'Marque – Produit [– Couleur]'.
        Fonctionne avec – (tiret cadratin) et - (trait d'union entouré d'espaces).
        Retourne (None, raw) si le préfixe ressemble à un nom de produit."""
        for sep in [" – ", " - "]:
            if sep in raw:
                candidate, rest = raw.split(sep, 1)
                candidate = candidate.strip()
                if candidate and len(candidate) <= 50 and candidate[0].isupper():
                    if not _looks_like_product_name(candidate):
                        return _normalize_brand(candidate), rest.strip()
                break
        return None, raw

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
        raw_name   = item.get("title", "Inconnu").strip()
        desc       = re.sub(r'<[^>]+>', '', item.get("body_html", "") or "").strip()
        handle     = item.get("handle", "")
        url        = f"{self.BASE_URL}/products/{handle}"
        tags       = item.get("tags", [])
        p_type_raw = item.get("product_type", "") or ""
        options    = item.get("options", [])

        # Extraction de la vraie marque pour les concept stores multi-marques
        if self.EXTRACT_BRAND_FROM_NAME:
            extracted_brand, name = self._split_brand_from_name(raw_name)
            brand_source = extracted_brand or self.BRAND_SOURCE
        else:
            name         = raw_name
            brand_source = self.BRAND_SOURCE

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

        is_shoe = self.FORCE_SHOE or any(
            k in name.lower() or k in p_type_raw.lower()
            for k in SHOE_KEYWORDS
        )
        p_type = "Chaussures" if is_shoe else "Vêtement"

        if self.STRICT_CLOTHING:
            p_type_lower = p_type_raw.lower()
            # Rejeter si le product_type Shopify correspond à une catégorie non-vestimentaire
            if p_type_lower and any(nct in p_type_lower for nct in _NON_CLOTHING_TYPES):
                logger.debug("[%s] Ignoré (product_type non-vêtement) : %s [%s]", self.BRAND_SOURCE, name, p_type_raw)
                return None
            # Rejeter si le NOM lui-même contient des mots-clés clairement non-vestimentaires
            name_lower = name.lower()
            if any(nct in name_lower for nct in _NON_CLOTHING_NAME_KEYWORDS):
                logger.debug("[%s] Ignoré (nom non-vêtement) : %s", self.BRAND_SOURCE, name)
                return None
            # Rejeter si ni le style ni la catégorie ne sont identifiables (double Autre)
            inferred_cat   = self.infer_categorie(name, desc, p_type)
            inferred_style = self.infer_style(name, desc)
            if inferred_cat == "Autre" and inferred_style == "Autre" and not is_shoe:
                logger.debug("[%s] Ignoré (style+catégorie=Autre) : %s", self.BRAND_SOURCE, name)
                return None
            # Rejeter si catégorie inférée = "Autre" ET aucune taille vestimentaire
            if inferred_cat == "Autre" and not all_tailles and not is_shoe:
                logger.debug("[%s] Ignoré (Autre + sans tailles) : %s", self.BRAND_SOURCE, name)
                return None

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
            brand_source = brand_source,
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
