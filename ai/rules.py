"""
ai/rules.py — Brique règles métier : filtres saison / météo / occasion.

Aucun ML ici : logique déterministe pure, explicable et maintenable.
"""
from datetime import date
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Mapping catégorie → slot dans une tenue
# ---------------------------------------------------------------------------
CATEGORY_TO_SLOT: Dict[str, Optional[str]] = {
    "Hauts": "top",
    "T-shirts": "top",
    "Pulls & Sweats": "top",
    "Vestes & Manteaux": "outer",
    "Pantalons": "bottom",
    "Jeans": "bottom",
    "Shorts": "bottom",
    "Robes & Jupes": "bottom",
    "Chaussures": "shoes",
    "Accessoires": "accessory",
    "Sous-vêtements": None,      # jamais dans une tenue recommandée
    "Sport": "top",
    "Autre": None,
}

# ---------------------------------------------------------------------------
# Formalisme cible par occasion : (min, max) sur échelle 1-5
# ---------------------------------------------------------------------------
OCCASION_FORMALITY: Dict[str, Tuple[int, int]] = {
    "Quotidien": (1, 3),
    "Travail": (3, 4),
    "Soirée": (3, 5),
    "Sport": (1, 1),
    "Voyage": (1, 3),
    "Cérémonie": (4, 5),
    "Autre": (1, 5),
}

# ---------------------------------------------------------------------------
# Saisons compatibles : saison courante → ensemble de saisons acceptées
# ---------------------------------------------------------------------------
_SEASON_COMPAT: Dict[str, set] = {
    "Printemps": {"Printemps", "Toutes saisons"},
    "Été": {"Été", "Toutes saisons"},
    "Automne": {"Automne", "Toutes saisons"},
    "Hiver": {"Hiver", "Toutes saisons"},
}

# ---------------------------------------------------------------------------
# Exclusions météo : (catégories à exclure, condition sur température)
# ---------------------------------------------------------------------------
_WEATHER_EXCLUSIONS = [
    ({"T-shirts", "Shorts"}, lambda t: t < 10),         # trop froid pour items légers
    ({"Pulls & Sweats"}, lambda t: t > 22),             # trop chaud pour pulls
    ({"Vestes & Manteaux"}, lambda t: t > 28),          # trop chaud pour manteaux
]


def current_season() -> str:
    """Retourne la saison courante basée sur le mois du calendrier."""
    month = date.today().month
    if month in (3, 4, 5):
        return "Printemps"
    if month in (6, 7, 8):
        return "Été"
    if month in (9, 10, 11):
        return "Automne"
    return "Hiver"


def assign_slot(category: str) -> Optional[str]:
    """Retourne le slot de tenue correspondant à une catégorie."""
    return CATEGORY_TO_SLOT.get(category)


def filter_items(
    items: List[dict],
    season: Optional[str] = None,
    weather_temp: Optional[float] = None,
    occasion: Optional[str] = None,
) -> List[dict]:
    """
    Applique les filtres durs (saison, météo, formalisme occasion).

    Chaque item doit avoir une clé 'metadata' avec au minimum :
        category, season, ai_formality

    Retourne les items valides avec la clé 'slot' ajoutée.
    """
    current_s = season or current_season()
    allowed_seasons = _SEASON_COMPAT.get(current_s, {"Toutes saisons"})
    formality_range = OCCASION_FORMALITY.get(occasion or "Autre", (1, 5))

    filtered = []
    for item in items:
        meta = item.get("metadata", {})
        category = meta.get("category", "")
        item_season = meta.get("season", "Toutes saisons") or "Toutes saisons"
        formality = _safe_int(meta.get("ai_formality"), default=2)
        slot = assign_slot(category)

        # Items sans slot valide (sous-vêtements, autre) : exclus
        if slot is None:
            continue

        # Filtre saison
        if item_season not in allowed_seasons:
            continue

        # Filtre formalisme (tolérance ±1)
        f_min, f_max = formality_range
        if not (f_min - 1 <= formality <= f_max + 1):
            continue

        # Filtre météo
        if weather_temp is not None:
            excluded = False
            for cats, condition_fn in _WEATHER_EXCLUSIONS:
                if category in cats and condition_fn(weather_temp):
                    excluded = True
                    break
            if excluded:
                continue

        filtered.append({**item, "slot": slot})

    return filtered


def group_by_slot(items: List[dict]) -> Dict[str, List[dict]]:
    """Regroupe les items par slot de tenue."""
    groups: Dict[str, List[dict]] = {
        "top": [],
        "bottom": [],
        "shoes": [],
        "outer": [],
        "accessory": [],
    }
    for item in items:
        slot = item.get("slot") or assign_slot(item.get("metadata", {}).get("category", ""))
        if slot and slot in groups:
            groups[slot].append(item)
    return groups


def need_outer(weather_temp: Optional[float]) -> bool:
    """True si la météo justifie de recommander un layer extérieur."""
    return weather_temp is not None and weather_temp < 15


def _safe_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
