# =============================================================
#  scrapers/base.py — Classe abstraite commune
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

from config import DEFAULT_HEADERS
from models import Product

logger = logging.getLogger(__name__)


class BaseScraper(ABC):
    """
    Classe de base pour tous les scrapers SmartWear.
    Chaque scraper hérite de cette classe et implémente `run()`.
    """

    BRAND_SOURCE: str = "Unknown"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    # ------------------------------------------------------------------
    # Méthodes utilitaires communes
    # ------------------------------------------------------------------

    def get(self, url: str, timeout: int = 15) -> Optional[BeautifulSoup]:
        """GET avec gestion d'erreur. Retourne un BeautifulSoup ou None."""
        try:
            resp = self.session.get(url, timeout=timeout)
            if resp.status_code == 200:
                return BeautifulSoup(resp.text, "html.parser")
            logger.warning(f"[{self.BRAND_SOURCE}] HTTP {resp.status_code} → {url}")
        except requests.RequestException as e:
            logger.warning(f"[{self.BRAND_SOURCE}] Erreur réseau : {e}")
        return None

    def sleep(self, min_s: float = 0.8, max_s: float = 2.0):
        """Pause aléatoire pour ne pas surcharger les serveurs."""
        time.sleep(random.uniform(min_s, max_s))

    # ------------------------------------------------------------------
    # Helpers de parsing partagés
    # ------------------------------------------------------------------

    @staticmethod
    def parse_price(text: str) -> tuple[Optional[float], Optional[str]]:
        """
        Extrait (valeur, devise) depuis un texte de prix.
        Ex: "59,99 €" → (59.99, "EUR")
        """
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
        """Déduit le style depuis le nom et la description du produit."""
        text = f"{name} {description}".lower()
        text = text.replace("robe di kappa", "")

        rules = [
            (["jean", "denim"],                          "Jean"),
            (["polo"],                                   "Polo"),
            (["pull", "cardigan", "gilet tricot","gilet"],"Pull"),
            (["t-shirt", "tee-shirt", "tee shirt"],      "T-shirt"),
            (["crop", "brassière"],                      "Crop-top"),
            (["robe"],                                   "Robe"),
            (["combinaison"],                            "Combinaison"),
            (["chemise","shirt"],                        "Chemise"),
            (["sweat", "sweatshirt"],                    "Sweat"),
            (["hoodie", "capuche"],                      "Hoodie"),
            (["veste", "blazer", "costume"],         "Veste"),
            (["blouson", "doudoune"],                "Blouson"),
            (["jogging"],                            "Pantalon"),
            (["basket", "baskets", "running"],       "Sneakers"),
            (["derby", "derbies"],                   "Derbies"),
            (["sweat"],                              "Sweat"),
            (["blouson", "bomber","vest","jacket","track jacket"],"Veste"),
            (["manteau", "parka", "anorak"],             "Manteau"),
            (["sweat", "sweatshirt"],                    "Sweat"),
            (["doudoune"],                               "Doudoune"),
            (["court", "short", "bermuda"],              "Short"),
            (["pantalon", "chino", "cargo"],             "Pantalon"),
            (["legging"],                                "Legging"),
            (["jupe"],                                   "Jupe"),
            (["débardeur", "débardeur"],                 "Débardeur"),
            (["blazer"],                                 "Blazer"),
            (["sneaker", "baskets", "basket","air max",
              "dunk", "force 1","running", "espadrille"],"Sneakers"),
            (["bottines", "boots"],                      "Bottines"),
            (["derby", "derbies"],                       "Derbies"),
            (["sandales"],                               "Sandales"),
            (["mocassins"],                              "Mocassins"),
        ]

        for keywords, style in rules:
            if any(k in text for k in keywords):
                return style
        return "Autre"

    @staticmethod
    def infer_categorie(name: str, description: str = "", type_: str = "") -> str:
        """Déduit la catégorie (Haut / Bas / …)."""
        name_lower = name.lower()
        text = f"{name} {type_}".lower()

        # Chaussures
        if any(k in text for k in ["chaussure", "bottine", "sneaker", "sandal",
                                "mocassin", "derby", "air max", "jordan",
                                "shoe", "boot"]):
            return "Autre"   # géré par type=Chaussures
        
        # Manteau/Veste
        if any(k in name_lower for k in ["manteau", "veste", "blouson", "parka",
                                "anorak", "doudoune", "trench", "blazer",
                                "jacket", "vest", "bomber", "windbreaker",
                                "track jacket"]):
            return "Manteau/Veste"
        
        # Bas
        if any(k in name_lower for k in ["pantalon", "jean", "jupe", "legging",
                                "short", "bermuda", "jogger", "trouser",
                                "track pant", "sweatpant"]):
            return "Bas"
        
        # Robe/Combinaison
        if any(k in name_lower for k in ["robe", "combinaison", "dress"]) \
            and "robe di kappa" not in name_lower:
                return "Robe/Combinaison"
        
        # Haut
        if any(k in text for k in ["pull", "t-shirt", "tee shirt", "tee-shirt",
                                "chemise", "sweat", "hoodie", "haut", "top",
                                "débardeur", "polo", "cardigan", "gilet",
                                "brassière", "crop", "maillot",
                                "shirt", "tee", "tank", "sweater",           # ← EN
                                "hoodie", "knitwear", "knit"]):
             return "Haut"
        return "Autre"

    @staticmethod
    def infer_genre_sexe(raw_genre: str) -> tuple[str, str]:
        """
        Convertit un genre brut en (genre, sexe) normalisés.
        Ex: "Enfants Fille" → ("Enfant", "Fille")
        """
        raw = raw_genre.lower().strip()

        if "garçon" in raw or "garcon" in raw:
            return "Enfant", "Garçon"
        if "fille" in raw:
            return "Enfant", "Fille"
        if "enfant" in raw:
            return "Enfant", "Fille"   # fallback
        if "teen" in raw or "adolescent" in raw:
            # Teen → on garde le sexe ambigu, à préciser dans chaque scraper
            return "Adolescent", "Femme"
        if "femme" in raw:
            return "Adulte", "Femme"
        if "homme" in raw:
            return "Adulte", "Homme"

        return "Adulte", "Homme"  # fallback

    # ------------------------------------------------------------------
    # Interface obligatoire
    # ------------------------------------------------------------------

    @abstractmethod
    def run(self) -> List[Product]:
        """Lance le scraping et retourne une liste de Product."""
        ...
