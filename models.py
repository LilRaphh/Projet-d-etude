# =============================================================
#  models.py — Dataclass + validation du schéma produit
# =============================================================

from dataclasses import dataclass, field, asdict
from typing import Optional, List
import re

from config import (
    GENRE_VALUES, SEXE_VALUES, TYPE_VALUES,
    CATEGORIE_VALUES, STYLE_VALUES, CURRENCY_VALUES,
)

# ------------------------------------------------------------------
# Helpers de normalisation
# ------------------------------------------------------------------

def _normalize_sizes_shoes(raw: list) -> List[int]:
    """Extrait uniquement les pointures numériques (ex: 36, 37 …)."""
    result = []
    for s in raw:
        m = re.search(r'\b(3[0-9]|4[0-9]|5[0-9])\b', str(s))
        if m:
            result.append(int(m.group(1)))
    return sorted(set(result))


def _normalize_sizes_clothing(raw: list) -> List[str]:
    """Extrait uniquement les tailles textuelles (XS/S/M/L/XL/XXL)."""
    valid = {"XS", "S", "M", "L", "XL", "XXL", "XXXL"}
    result = []
    for s in raw:
        token = str(s).upper().strip()
        if token in valid and token not in result:
            result.append(token)
    return result


def _clean_rating(raw) -> Optional[float]:
    """Normalise le rating sur 5."""
    if raw is None:
        return None
    try:
        v = float(str(raw).replace(',', '.'))
        return round(min(max(v, 1.0), 5.0), 1)
    except (ValueError, TypeError):
        return None


def _first_valid(value, allowed: list):
    """Retourne value si elle est dans allowed, sinon None."""
    if value is None:
        return None
    value = str(value).strip()
    return value if value in allowed else None


# ------------------------------------------------------------------
# Dataclass principale
# ------------------------------------------------------------------

@dataclass
class Product:
    # --- Champs scrappés ---
    name:         str             = "Inconnu"
    price_value:  Optional[float] = None
    currency:     Optional[str]   = None     # "EUR" | "USD"
    description:  Optional[str]   = None
    genre:        Optional[str]   = None     # "Enfant" | "Adolescent" | "Adulte"
    sexe:         Optional[str]   = None     # "Femme" | "Homme" | "Fille" | "Garçon"
    sizes:        List[int]       = field(default_factory=list)  # pointures
    taille:       List[str]       = field(default_factory=list)  # S/M/L…
    color:        Optional[str]   = None
    rating:       Optional[float] = None
    type:         Optional[str]   = None     # "Vêtement" | "Chaussures" | "Autre"
    categorie:    Optional[str]   = None     # "Haut" | "Bas" | …
    style:        Optional[str]   = None     # "Jean" | "Pull" | …
    image:        Optional[str]   = None
    url:          Optional[str]   = None
    brand_source: Optional[str]   = None

    # ------------------------------------------------------------------
    def validate_and_clean(self) -> "Product":
        self.currency  = _first_valid(self.currency,  CURRENCY_VALUES)
        self.genre     = _first_valid(self.genre,     GENRE_VALUES)
        self.sexe      = _first_valid(self.sexe,      SEXE_VALUES)
        self.type      = _first_valid(self.type,      TYPE_VALUES)
        self.categorie = _first_valid(self.categorie, CATEGORIE_VALUES)
        self.style     = _first_valid(self.style,     STYLE_VALUES)
        self.rating    = _clean_rating(self.rating)

        # Sépare les tailles selon le type
        if self.type == "Chaussures":
            self.sizes  = _normalize_sizes_shoes(self.sizes)
            self.taille = []
        else:
            self.taille = _normalize_sizes_clothing(self.taille)
            self.sizes  = []

        # Nettoie le prix
        if self.price_value is not None:
            try:
                self.price_value = round(float(self.price_value), 2)
            except (ValueError, TypeError):
                self.price_value = None

        return self

    def to_dict(self) -> dict:
        """Convertit en dict prêt pour MongoDB / JSON."""
        self.validate_and_clean()
        return asdict(self)