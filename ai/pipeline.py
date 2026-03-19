"""
ai/pipeline.py — Orchestration des briques IA.

Deux fonctions principales :
  - analyze_and_store_item(item, image_path) : ingestion complète d'un vêtement
  - recommend_outfits(user_id, weather, occasion, n) : génération de recommandations
"""
import hashlib
import itertools
import logging
import os
from typing import List, Optional, Tuple

from ai.embeddings import (
    collection_count,
    encode_image,
    get_user_items_with_embeddings,
    store_item,
)
from ai.explainer import explain_outfit
from ai.rules import current_season, filter_items, group_by_slot, need_outer
from ai.scoring import score_outfit
from ai.vision import analyze_garment

log = logging.getLogger(__name__)

# Limite le produit cartésien pour éviter O(n³) sur de grandes gardes-robes
_MAX_COMBINATIONS = 200


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------

def analyze_and_store_item(item, image_full_path: str) -> dict:
    """
    Pipeline d'ingestion complet pour un vêtement.

    1. Analyse visuelle via Qwen2.5-VL (Ollama)
    2. Encodage FashionCLIP
    3. Stockage ChromaDB

    Args:
        item  : instance SQLAlchemy ClothingItem
        image_full_path : chemin absolu vers l'image

    Returns:
        dict des attributs extraits par l'IA

    Raises:
        RuntimeError si Ollama est inaccessible ou l'analyse échoue
    """
    log.info("Analyse visuelle item %d (%s)…", item.id, item.name)
    ai_attrs = analyze_garment(image_full_path)

    log.info("Encodage FashionCLIP item %d…", item.id)
    embedding = encode_image(image_full_path)

    # Métadonnées stockées dans ChromaDB (doivent être des types primitifs)
    metadata = {
        "category": ai_attrs.get("category") or item.category or "Autre",
        "item_name": item.name,
        "primary_color": ai_attrs.get("primary_color") or item.color or "",
        "season": ai_attrs.get("season") or item.season or "Toutes saisons",
        "ai_style": ai_attrs.get("style") or "",
        "ai_formality": ai_attrs.get("formality") or 2,
        "ai_material": ai_attrs.get("material_guess") or "",
        "ai_fit": ai_attrs.get("fit") or "regular",
        "ai_pattern": ai_attrs.get("pattern") or "",
        "ai_subcategory": ai_attrs.get("subcategory") or "",
    }

    description = _build_description(ai_attrs, item)

    store_item(
        item_id=item.id,
        user_id=item.user_id,
        embedding=embedding,
        metadata=metadata,
        description=description,
    )

    log.info("Item %d indexé avec succès.", item.id)
    return ai_attrs


def _build_description(ai_attrs: dict, item) -> str:
    """Construit une description textuelle pour le champ document ChromaDB."""
    parts = []
    for val in [
        ai_attrs.get("primary_color"),
        ai_attrs.get("style"),
        ai_attrs.get("subcategory"),
        ai_attrs.get("category"),
        ai_attrs.get("material_guess"),
        ai_attrs.get("pattern"),
        ai_attrs.get("fit"),
        getattr(item, "brand", None),
    ]:
        if val:
            parts.append(str(val))
    return ", ".join(parts)


# ---------------------------------------------------------------------------
# Recommandation
# ---------------------------------------------------------------------------

def recommend_outfits(
    user_id: int,
    weather: Optional[dict] = None,
    occasion: Optional[str] = None,
    n: int = 3,
) -> Tuple[List[dict], str]:
    """
    Génère des recommandations de tenues pour un utilisateur.

    Returns:
        (outfits, error_message)
        outfits : liste de dicts {items, score, breakdown, explanation}
        error_message : chaîne non-vide en cas d'erreur
    """
    # 1. Charger tous les items indexés de l'utilisateur
    all_items = get_user_items_with_embeddings(user_id)
    if not all_items:
        return [], (
            "Aucun vêtement indexé. "
            "Ouvrez la page d'un vêtement et cliquez sur 'Analyser avec l'IA'."
        )

    # 2. Filtres durs (saison / météo / formalisme)
    season = current_season()
    weather_temp = weather.get("temp") if weather else None

    filtered = filter_items(
        all_items,
        season=season,
        weather_temp=weather_temp,
        occasion=occasion,
    )

    if not filtered:
        return [], (
            "Aucun vêtement compatible avec la météo / saison / occasion sélectionnée. "
            "Essayez sans occasion ou ajoutez plus de vêtements."
        )

    # 3. Grouper par slot
    by_slot = group_by_slot(filtered)
    tops = by_slot["top"]
    bottoms = by_slot["bottom"]
    shoes_list = by_slot["shoes"]
    outers = by_slot["outer"]

    missing = []
    if not tops:
        missing.append("hauts")
    if not bottoms:
        missing.append("bas")
    if not shoes_list:
        missing.append("chaussures")

    if missing:
        return [], (
            f"Pas assez de vêtements indexés dans les catégories : {', '.join(missing)}. "
            "Analysez plus de vêtements pour obtenir des recommandations complètes."
        )

    # 4. Générer les combinaisons
    include_outer = need_outer(weather_temp)
    if include_outer and outers:
        raw_combos = list(itertools.product(tops, bottoms, shoes_list, outers))
    else:
        raw_combos = [
            (t, b, s, None)
            for t, b, s in itertools.product(tops, bottoms, shoes_list)
        ]

    # Limiter le nombre de combinaisons (tri pseudo-aléatoire mais reproductible)
    if len(raw_combos) > _MAX_COMBINATIONS:
        raw_combos = sorted(
            raw_combos,
            key=lambda c: hashlib.md5(
                "".join(x["chroma_id"] if x else "" for x in c).encode()
            ).hexdigest(),
        )[:_MAX_COMBINATIONS]

    # 5. Scorer chaque combinaison
    scored = []
    for combo in raw_combos:
        outfit_items = [c for c in combo if c is not None]
        total, breakdown = score_outfit(outfit_items, occasion=occasion)
        scored.append({"combo": combo, "items": outfit_items, "score": total, "breakdown": breakdown})

    scored.sort(key=lambda x: x["score"], reverse=True)

    # 6. Sélection diversifiée (éviter les doublons top+bas)
    selected = _select_diverse(scored, n)

    # 7. Générer les explications
    results = []
    for entry in selected:
        explanation = explain_outfit(
            items=entry["items"],
            weather=weather,
            occasion=occasion,
            score_breakdown=entry["breakdown"],
        )
        results.append(
            {
                "items": [
                    {
                        "item_id": it["metadata"].get("item_id"),
                        "name": it["metadata"].get("item_name", ""),
                        "category": it["metadata"].get("category", ""),
                        "color": it["metadata"].get("primary_color", ""),
                        "style": it["metadata"].get("ai_style", ""),
                        "slot": it.get("slot", ""),
                    }
                    for it in entry["items"]
                ],
                "score": round(entry["score"], 3),
                "breakdown": entry["breakdown"],
                "explanation": explanation,
            }
        )

    return results, ""


def _select_diverse(scored: list, n: int) -> list:
    """
    Sélectionne n outfits en maximisant la diversité.
    On n'accepte pas deux outfits avec le même couple (top, bas).
    """
    selected = []
    seen_pairs = set()

    for entry in scored:
        combo = entry["combo"]
        top_id = combo[0]["chroma_id"] if combo[0] else ""
        bottom_id = combo[1]["chroma_id"] if len(combo) > 1 and combo[1] else ""
        pair = (top_id, bottom_id)

        if pair not in seen_pairs:
            selected.append(entry)
            seen_pairs.add(pair)

        if len(selected) >= n:
            break

    return selected
