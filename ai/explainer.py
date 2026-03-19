"""
ai/explainer.py — Brique explication : génère une justification de tenue via LLM local.

Utilise le même modèle Qwen2.5-VL déjà téléchargé pour l'analyse vision (économie de VRAM).
Fallback automatique sur un texte template si Ollama est indisponible.

Modèle configurable : TEXT_MODEL (défaut : qwen2.5vl:7b)
"""
import logging
import os
from typing import List, Optional

import requests

log = logging.getLogger(__name__)

OLLAMA_BASE = os.environ.get("OLLAMA_URL", "http://localhost:11434")
# Par défaut, réutilise le modèle vision (déjà chargé, pas de second modèle à charger).
# Si tu veux des explications plus rapides, installe qwen2.5:7b et change cette variable.
TEXT_MODEL = os.environ.get("TEXT_MODEL", "qwen2.5vl:7b")

_EXPLAIN_PROMPT = """Tu es un styliste personnel. Justifie en 2 phrases courtes et naturelles en français pourquoi cette tenue est bien choisie pour le contexte donné.

Tenue :
{items_text}

Contexte :
{context}

Réponse (2 phrases max, ton direct et bienveillant) :"""


def explain_outfit(
    items: List[dict],
    weather: Optional[dict] = None,
    occasion: Optional[str] = None,
    score_breakdown: Optional[dict] = None,
) -> str:
    """
    Génère une explication naturelle pour une tenue recommandée.
    Retourne toujours une chaîne non-vide (fallback template si Ollama indisponible).
    """
    # Construction du contexte pour le prompt
    item_lines = []
    for item in items:
        meta = item.get("metadata", {})
        name = meta.get("item_name", "vêtement")
        parts = [
            p for p in [
                meta.get("primary_color"),
                meta.get("category"),
                meta.get("ai_style") or meta.get("style"),
            ]
            if p
        ]
        desc = f"  - {name}" + (f" ({', '.join(parts)})" if parts else "")
        item_lines.append(desc)

    items_text = "\n".join(item_lines)

    context_parts = []
    if occasion:
        context_parts.append(f"Occasion : {occasion}")
    if weather:
        temp = weather.get("temp", "")
        label = weather.get("label", "")
        layer = weather.get("layer", "")
        if temp != "":
            context_parts.append(f"Météo : {temp}°C, {label}. {layer}")
    if not context_parts:
        context_parts.append("Usage quotidien")

    prompt = _EXPLAIN_PROMPT.format(
        items_text=items_text,
        context="\n".join(context_parts),
    )

    try:
        resp = requests.post(
            f"{OLLAMA_BASE}/api/generate",
            json={
                "model": TEXT_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.65, "num_predict": 100, "seed": 0},
            },
            timeout=45,
        )
        resp.raise_for_status()
        explanation = resp.json().get("response", "").strip()
        if explanation:
            return explanation
    except Exception as e:
        log.warning("Explainer LLM indisponible (%s), fallback template.", e)

    return _template_explanation(items, weather, occasion)


def _template_explanation(
    items: List[dict],
    weather: Optional[dict],
    occasion: Optional[str],
) -> str:
    """Explication basée sur des règles — fallback sans LLM."""
    parts = []

    if occasion:
        parts.append(f"Tenue choisie pour : {occasion.lower()}.")

    colors = list({
        i.get("metadata", {}).get("primary_color")
        for i in items
        if i.get("metadata", {}).get("primary_color")
    })
    if colors:
        palette = ", ".join(colors)
        parts.append(f"La palette {palette} offre une harmonie visuelle cohérente.")

    if weather:
        temp = weather.get("temp")
        if temp is not None:
            if temp < 10:
                parts.append("Les pièces choisies conviennent aux températures fraîches.")
            elif temp > 22:
                parts.append("La tenue légère est adaptée à la chaleur du moment.")
            else:
                parts.append("La tenue est appropriée pour la météo actuelle.")

    return " ".join(parts) if parts else "Tenue équilibrée et cohérente pour cette occasion."
