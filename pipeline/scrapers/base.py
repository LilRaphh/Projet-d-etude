# =============================================================
#  pipeline/scrapers/base.py — Classe abstraite commune
# =============================================================
import re
import time
import random
import logging
from abc import ABC, abstractmethod
from typing import List, Optional
from html import unescape

import requests
from bs4 import BeautifulSoup

from pipeline.config import DEFAULT_HEADERS
from pipeline.models import Product

logger = logging.getLogger(__name__)

# Liste de couleurs partagée par tous les scrapers — du plus long au plus court
# pour garantir "bleu marine" avant "bleu", "navy blue" avant "navy", etc.
COLOR_KEYWORDS = sorted({
    # Français multi-mots
    "bleu electrique", "bleu marine", "bleu ciel", "bleu nuit", "bleu roi",
    "gris chine clair", "gris chine", "gris chiné", "gris clair", "gris foncé",
    "vert kaki", "rouge electro", "new optical white",
    # Anglais multi-mots
    "black beauty", "brilliant white", "optical white", "ivory white", "off white",
    "electric blue", "dark blue", "light blue", "navy blue", "royal blue", "sky blue",
    "ultra marine", "heather blue", "dress blues",
    "dark green", "bright green", "forest green", "light green", "olive green", "pine green",
    "bright red", "dark red", "clay red", "fiesta red", "rio red",
    "burnt orange", "safety yellow", "bright cyan",
    "all black", "all white", "jet black", "sky captain",
    # Français simple
    "anthracite", "bordeaux", "terracotta", "lavande", "parme",
    "caramel", "chocolat", "cognac", "rouille", "charbon",
    "naturel", "corail", "univert", "safari",
    "crème", "creme", "écru", "ivoire",
    "marine", "rouge", "blanc", "noir",
    "kaki", "khaki", "olive", "beige",
    "camel", "rose", "gris", "vert", "bleu",
    "marron", "violet", "orange", "jaune",
    # Anglais simple
    "multicolor", "multicolore", "colorblock", "burgundy", "turquoise",
    "charcoal", "ivory", "cream", "ecru", "nude", "sand", "stripe",
    "purple", "yellow", "pink", "green", "navy",
    "red", "grey", "gray", "blue",
    "brown", "tan", "beige",
    "black", "white",
}, key=len, reverse=True)


class BaseScraper(ABC):
    BRAND_SOURCE: str = "Unknown"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def get(self, url: str, timeout: int = 15) -> Optional[BeautifulSoup]:
        try:
            resp = self.session.get(url, timeout=timeout)
            if resp.status_code == 200:
                return BeautifulSoup(resp.text, "html.parser")
            logger.warning("[%s] HTTP %s → %s", self.BRAND_SOURCE, resp.status_code, url)
        except requests.RequestException as e:
            logger.warning("[%s] Erreur réseau : %s", self.BRAND_SOURCE, e)
        return None

    def sleep(self, min_s: float = 0.8, max_s: float = 2.0):
        time.sleep(random.uniform(min_s, max_s))

    def _find_color(self, text: str) -> Optional[str]:
        """Cherche la première couleur connue dans un texte (du plus long au plus court)."""
        t = text.lower()
        for c in COLOR_KEYWORDS:
            if re.search(r'\b' + re.escape(c) + r'\b', t):
                return c.capitalize()
        return None

    @staticmethod
    def parse_price(text: str) -> tuple:
        if not text:
            return None, None
        text = text.replace('\xa0', ' ').replace('\u202f', ' ').strip()
        currency = "EUR" if "€" in text else ("USD" if "$" in text else None)
        m = re.search(r'(\d[\d\s]*(?:[.,]\d+)?)', text)
        if m:
            try:
                val = float(m.group(1).replace(' ', '').replace(',', '.'))
                return val, currency
            except ValueError:
                pass
        return None, currency

    @staticmethod
    def infer_style(name: str, description: str = "") -> str:
        text = f"{name} {description}".lower()
        text = text.replace("robe di kappa", "")
        rules = [
            (["jean", "denim"],                                          "Jean"),
            (["polo"],                                                   "Polo"),
            (["pull", "cardigan", "gilet tricot", "gilet"],             "Pull"),
            (["t-shirt", "tee-shirt", "tee shirt"],                     "T-shirt"),
            (["crop", "brassière"],                                      "Crop-top"),
            (["robe"],                                                   "Robe"),
            (["combinaison"],                                            "Combinaison"),
            (["crewneck", "crew neck", "1/4 zip", "quarter zip"],               "Sweat"),
            (["sweat", "sweatshirt"],                                            "Sweat"),
            (["hoodie", "hoody", "capuche"],                                     "Hoodie"),
            (["chemise", "shirt"],                                               "Chemise"),
            (["veste", "blazer", "costume"],                                     "Veste"),
            (["blouson", "bomber", "vest", "jacket", "track jacket",
              "windbreaker"],                                                     "Veste"),
            (["manteau", "parka", "anorak"],                                     "Manteau"),
            (["doudoune"],                                                        "Doudoune"),
            (["court", "short", "bermuda"],                                      "Short"),
            (["sweatpant", "sweat pant", "track pant", "jogger", "trouser"],    "Pantalon"),
            (["jogging", "pantalon", "chino", "cargo"],                         "Pantalon"),
            (["legging"],                                                "Legging"),
            (["jupe"],                                                   "Jupe"),
            (["débardeur"],                                              "Débardeur"),
            (["blazer"],                                                 "Blazer"),
            (["sneaker", "baskets", "basket", "air max", "dunk",
              "force 1", "running", "espadrille"],                      "Sneakers"),
            (["bottines", "boots"],                                      "Bottines"),
            (["derby", "derbies"],                                       "Derbies"),
            (["sandales"],                                               "Sandales"),
            (["mocassins"],                                              "Mocassins"),
        ]
        for keywords, style in rules:
            if any(k in text for k in keywords):
                return style
        return "Autre"

    @staticmethod
    def infer_categorie(name: str, description: str = "", type_: str = "") -> str:
        name_lower = name.lower()
        text = f"{name} {type_}".lower()
        if any(k in text for k in ["chaussure", "bottine", "sneaker", "sandal",
                                    "mocassin", "derby", "air max", "jordan",
                                    "shoe", "boot"]):
            return "Autre"
        if any(k in name_lower for k in ["manteau", "veste", "blouson", "parka",
                                          "anorak", "doudoune", "trench", "blazer",
                                          "jacket", "vest", "bomber", "windbreaker",
                                          "track jacket"]):
            return "Manteau/Veste"
        if any(k in name_lower for k in ["pantalon", "jean", "jupe", "legging",
                                          "short", "bermuda", "jogger", "trouser",
                                          "track pant", "sweatpant"]):
            return "Bas"
        if any(k in name_lower for k in ["robe", "combinaison", "dress"]) \
                and "robe di kappa" not in name_lower:
            return "Robe/Combinaison"
        if any(k in text for k in ["pull", "t-shirt", "tee shirt", "tee-shirt",
                                    "chemise", "sweat", "hoodie", "haut", "top",
                                    "débardeur", "polo", "cardigan", "gilet",
                                    "brassière", "crop", "maillot", "shirt", "tee",
                                    "tank", "sweater", "knitwear", "knit",
                                    "jersey", "crewneck", "crew neck", "long sleeve"]):
            return "Haut"
        return "Autre"

    @staticmethod
    def infer_genre_sexe(raw_genre: str) -> tuple:
        raw = raw_genre.lower().strip()
        if "garçon" in raw or "garcon" in raw:
            return "Enfant", "Garçon"
        if "fille" in raw:
            return "Enfant", "Fille"
        if "enfant" in raw:
            return "Enfant", "Fille"
        if "teen" in raw or "adolescent" in raw:
            return "Adolescent", "Femme"
        if "femme" in raw:
            return "Adulte", "Femme"
        if "homme" in raw:
            return "Adulte", "Homme"
        return "Adulte", "Homme"

    @abstractmethod
    def run(self) -> List[Product]:
        ...
