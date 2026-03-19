"""
ai/vision.py — Brique vision : analyse d'un vêtement via Qwen2.5-VL (Ollama local).

Modèle requis : ollama pull qwen2.5vl:7b
"""
import base64
import json
import logging
import os
import re
from typing import Optional

import requests

log = logging.getLogger(__name__)

OLLAMA_BASE = os.environ.get("OLLAMA_URL", "http://localhost:11434")
VISION_MODEL = os.environ.get("VISION_MODEL", "qwen2.5vl:7b")

# Mapping catégories AI -> catégories app
CATEGORY_MAP = {
    "tops": "Hauts",
    "t-shirts": "T-shirts",
    "shirts": "Hauts",
    "sweaters": "Pulls & Sweats",
    "hoodies": "Pulls & Sweats",
    "jackets": "Vestes & Manteaux",
    "coats": "Vestes & Manteaux",
    "blazers": "Vestes & Manteaux",
    "pants": "Pantalons",
    "jeans": "Jeans",
    "shorts": "Shorts",
    "dresses": "Robes & Jupes",
    "skirts": "Robes & Jupes",
    "shoes": "Chaussures",
    "sneakers": "Chaussures",
    "boots": "Chaussures",
    "accessories": "Accessoires",
    "underwear": "Sous-vêtements",
    "sportswear": "Sport",
}

SEASON_MAP = {
    "printemps": "Printemps",
    "ete": "Été",
    "été": "Été",
    "automne": "Automne",
    "hiver": "Hiver",
    "toutes saisons": "Toutes saisons",
    "all seasons": "Toutes saisons",
}

_PROMPT = """You are analyzing a clothing item photo. Return ONLY valid JSON, no markdown, no explanation.

{
  "category": "one of: tops, t-shirts, shirts, sweaters, hoodies, jackets, coats, blazers, pants, jeans, shorts, dresses, skirts, shoes, sneakers, boots, accessories, underwear, sportswear",
  "subcategory": "specific type e.g. bomber jacket, crewneck sweater, straight jeans",
  "primary_color": "main color in French: noir, blanc, gris, beige, marron, camel, rouge, rose, orange, jaune, vert, bleu, violet, bleu marine, bordeaux, kaki, rouille, or other",
  "secondary_color": "secondary color or null",
  "style": "one of: casual, chic, streetwear, sport, boheme, minimaliste, vintage, business",
  "season": "one of: printemps, été, automne, hiver, toutes saisons",
  "formality": 2,
  "pattern": "one of: uni, rayures, carreaux, fleurs, imprimé, autre, or null",
  "material_guess": "primary material: coton, jean, laine, polyester, cuir, lin, soie, synthétique, or other",
  "fit": "one of: slim, regular, oversize, ajuste"
}

formality scale: 1=très casual (plage, pyjama), 2=casual (quotidien), 3=smart casual, 4=business, 5=formel (costume, robe de soirée)
Return only the JSON object, nothing else."""


def _encode_image(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def _parse_json(text: str) -> Optional[dict]:
    """Extrait et parse le JSON depuis la réponse du LLM."""
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass
    # Recherche d'un bloc JSON dans la réponse
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return None


def _clamp(value, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(value)))
    except (TypeError, ValueError):
        return lo


def analyze_garment(image_path: str) -> dict:
    """
    Analyse une photo de vêtement avec Qwen2.5-VL via Ollama.

    Returns:
        dict avec les attributs extraits (category, primary_color, style, etc.)

    Raises:
        RuntimeError si Ollama est inaccessible ou si l'analyse échoue.
    """
    try:
        img_b64 = _encode_image(image_path)
    except (OSError, IOError) as e:
        raise RuntimeError(f"Impossible de lire l'image : {e}")

    payload = {
        "model": VISION_MODEL,
        "messages": [
            {
                "role": "user",
                "content": _PROMPT,
                "images": [img_b64],
            }
        ],
        "stream": False,
        "options": {"temperature": 0.05, "seed": 42},
    }

    try:
        resp = requests.post(
            f"{OLLAMA_BASE}/api/chat",
            json=payload,
            timeout=120,
        )
        resp.raise_for_status()
    except requests.ConnectionError:
        raise RuntimeError(
            "Ollama inaccessible. Lancez `ollama serve` puis vérifiez que le modèle est bien installé."
        )
    except requests.Timeout:
        raise RuntimeError("Délai d'attente dépassé pour Qwen2.5-VL (120 s). Réessayez.")
    except requests.RequestException as e:
        raise RuntimeError(f"Erreur réseau Ollama : {e}")

    raw = resp.json().get("message", {}).get("content", "")
    data = _parse_json(raw)

    if not data:
        log.warning("Qwen2.5-VL — JSON invalide reçu : %.200s", raw)
        raise RuntimeError("Le modèle n'a pas retourné un JSON valide. Relancez l'analyse.")

    category_raw = str(data.get("category", "")).lower().strip()
    season_raw = str(data.get("season", "")).lower().strip()

    return {
        "category": CATEGORY_MAP.get(category_raw, "Autre"),
        "subcategory": str(data.get("subcategory", "")).strip() or None,
        "primary_color": str(data.get("primary_color", "")).strip() or None,
        "secondary_color": data.get("secondary_color") or None,
        "style": str(data.get("style", "casual")).strip().lower(),
        "season": SEASON_MAP.get(season_raw, "Toutes saisons"),
        "formality": _clamp(data.get("formality", 2), 1, 5),
        "pattern": data.get("pattern") or None,
        "material_guess": str(data.get("material_guess", "")).strip() or None,
        "fit": str(data.get("fit", "regular")).strip().lower(),
    }


def check_ollama() -> dict:
    """
    Vérifie si Ollama est accessible et si le modèle vision est disponible.

    Returns:
        {"running": bool, "model_available": bool, "available_models": list}
    """
    try:
        resp = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=4)
        resp.raise_for_status()
        models = [m["name"] for m in resp.json().get("models", [])]
        model_available = any(VISION_MODEL.split(":")[0] in m for m in models)
        return {"running": True, "model_available": model_available, "available_models": models}
    except Exception:
        return {"running": False, "model_available": False, "available_models": []}
