"""
ai/scoring.py — Brique scoring : évalue la cohérence d'un outfit candidat.

Trois critères :
  - Harmonie des couleurs  (30 %)
  - Cohérence stylistique via embeddings FashionCLIP cosinus  (40 %)
  - Cohérence de formalisme  (20 %)
  - Adéquation à l'occasion  (10 %)
"""
import math
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Groupes de couleurs
# ---------------------------------------------------------------------------
_NEUTRALS = {
    "noir", "blanc", "gris", "beige", "crème", "creme", "camel",
    "marron", "taupe", "ivoire", "écru", "ecru", "bleu marine",
    "marine", "navy", "chocolat", "anthracite", "nude",
}
_WARM = {
    "rouge", "orange", "jaune", "bordeaux", "rouille", "terracotta",
    "corail", "brique", "ocre", "or", "doré",
}
_COOL = {
    "bleu", "vert", "violet", "turquoise", "menthe", "indigo",
    "cyan", "lavande", "bleu ciel", "kaki",
}
_PASTEL = {
    "rose", "rose pâle", "rose pale", "lilas", "menthe pâle",
    "mint", "pêche", "peche", "saumon",
}


def _color_group(color: Optional[str]) -> str:
    if not color:
        return "neutral"
    c = color.lower().strip()
    if c in _NEUTRALS:
        return "neutral"
    if c in _WARM:
        return "warm"
    if c in _COOL:
        return "cool"
    if c in _PASTEL:
        return "pastel"
    # Correspondance partielle pour couleurs composées (ex : "bleu nuit")
    for n in _NEUTRALS:
        if n in c:
            return "neutral"
    for n in _WARM:
        if n in c:
            return "warm"
    for n in _COOL:
        if n in c:
            return "cool"
    return "other"


_COLOR_COMPAT: Dict[Tuple[str, str], float] = {
    ("neutral", "neutral"): 1.00,
    ("neutral", "warm"):    0.92,
    ("neutral", "cool"):    0.92,
    ("neutral", "pastel"):  0.90,
    ("neutral", "other"):   0.80,
    ("warm",    "warm"):    0.72,   # monochromatique chaud
    ("warm",    "pastel"):  0.68,
    ("warm",    "cool"):    0.45,   # souvent un clash
    ("cool",    "cool"):    0.72,
    ("cool",    "pastel"):  0.70,
    ("pastel",  "pastel"):  0.75,
    ("other",   "other"):   0.55,
}


def _pair_color_score(g1: str, g2: str) -> float:
    key = tuple(sorted([g1, g2]))
    return _COLOR_COMPAT.get(key, 0.55)


def color_harmony_score(colors: List[Optional[str]]) -> float:
    """Score d'harmonie chromatique moyen sur toutes les paires."""
    valid = [c for c in colors if c]
    if len(valid) <= 1:
        return 0.80
    groups = [_color_group(c) for c in valid]
    pairs = [
        (groups[i], groups[j])
        for i in range(len(groups))
        for j in range(i + 1, len(groups))
    ]
    return sum(_pair_color_score(a, b) for a, b in pairs) / len(pairs)


# ---------------------------------------------------------------------------
# Similarité cosinus
# ---------------------------------------------------------------------------

def _cosine(v1: List[float], v2: List[float]) -> float:
    dot = sum(a * b for a, b in zip(v1, v2))
    n1 = math.sqrt(sum(a * a for a in v1))
    n2 = math.sqrt(sum(b * b for b in v2))
    if n1 == 0 or n2 == 0:
        return 0.0
    return dot / (n1 * n2)


def style_embedding_score(embeddings: List[List[float]]) -> float:
    """
    Score de cohérence stylistique = moyenne des similarités cosinus pairwise.
    Les embeddings FashionCLIP ont déjà été normalisés L2 à l'encodage.
    """
    valid = [e for e in embeddings if e]
    if len(valid) <= 1:
        return 0.75
    pairs = [
        _cosine(valid[i], valid[j])
        for i in range(len(valid))
        for j in range(i + 1, len(valid))
    ]
    # Les similarités cosinus CLIP sont dans [−1, 1] mais en pratique [0.1, 0.9]
    # On normalise pour obtenir un score [0, 1]
    raw = sum(pairs) / len(pairs)
    return max(0.0, min(1.0, (raw + 1) / 2))


# ---------------------------------------------------------------------------
# Cohérence de formalisme
# ---------------------------------------------------------------------------

def formality_score(formalities: List[int]) -> float:
    """Score = 1 − écart-type/2 (pénalise les mélanges costume + tongs)."""
    valid = [f for f in formalities if f]
    if len(valid) <= 1:
        return 0.85
    mean = sum(valid) / len(valid)
    variance = sum((f - mean) ** 2 for f in valid) / len(valid)
    std = math.sqrt(variance)
    return max(0.0, 1.0 - std / 2.0)


# ---------------------------------------------------------------------------
# Adéquation occasion
# ---------------------------------------------------------------------------

def occasion_fit_score(formalities: List[int], occasion: Optional[str]) -> float:
    """Bonus si le formalisme moyen de la tenue correspond à l'occasion."""
    from ai.rules import OCCASION_FORMALITY
    if not occasion or not formalities:
        return 0.5
    valid = [f for f in formalities if f]
    if not valid:
        return 0.5
    mean = sum(valid) / len(valid)
    f_min, f_max = OCCASION_FORMALITY.get(occasion, (1, 5))
    target = (f_min + f_max) / 2
    delta = abs(mean - target)
    return max(0.0, 1.0 - delta / 2.5)


# ---------------------------------------------------------------------------
# Score global d'un outfit
# ---------------------------------------------------------------------------

def score_outfit(items: List[dict], occasion: Optional[str] = None) -> Tuple[float, dict]:
    """
    Calcule le score global d'un outfit candidat.

    Args:
        items: liste de dicts avec clés 'embedding' et 'metadata'
        occasion: occasion cible (optionnel)

    Returns:
        (score_total, breakdown_dict)
    """
    colors = [i.get("metadata", {}).get("primary_color") for i in items]
    formalities = [
        int(i.get("metadata", {}).get("ai_formality") or 2)
        for i in items
    ]
    embeddings = [i.get("embedding", []) for i in items if i.get("embedding")]

    s_color = color_harmony_score(colors)
    s_style = style_embedding_score(embeddings)
    s_formality = formality_score(formalities)
    s_occasion = occasion_fit_score(formalities, occasion)

    total = (
        0.30 * s_color
        + 0.40 * s_style
        + 0.20 * s_formality
        + 0.10 * s_occasion
    )

    return total, {
        "color": round(s_color, 3),
        "style": round(s_style, 3),
        "formality": round(s_formality, 3),
        "occasion": round(s_occasion, 3),
        "total": round(total, 3),
    }
