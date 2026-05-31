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
  "primary_color": "main color in French: noir, blanc, gris, beige, marron, camel, rouge, rose, orange, jaune, vert, bleu, violet, bleu marine, bordeaux, kaki, rouille, or other. IMPORTANT: use the actual hue for pastel/light colors — a pale pink is 'rose' NOT 'beige', a pale lavender is 'violet' NOT 'gris', a light mint is 'vert' NOT 'blanc'. Only use 'beige' for tan/sand/nude tones with no chromatic hue.",
  "secondary_color": "secondary color in French or null",
  "style": "one of: casual, chic, streetwear, sport, boheme, minimaliste, vintage, business",
  "season": "one of: printemps, été, automne, hiver, toutes saisons",
  "formality": 2,
  "pattern": "one of: uni, rayures, carreaux, fleurs, imprimé, autre, or null",
  "material_guess": "primary material: coton, jean, laine, polyester, cuir, lin, soie, synthétique, or other",
  "fit": "one of: slim, regular, oversize, ajuste",
  "thickness": "one of: léger, moyen, épais",
  "length": "one of: court, mi-long, long, or null if not applicable (e.g. shoes)",
  "description": "one sentence in French describing this item naturally, e.g. 'Sneakers blanches en cuir au style minimaliste et épuré.'"
}

formality scale: 1=très casual (plage, pyjama), 2=casual (quotidien), 3=smart casual, 4=business, 5=formel (costume, robe de soirée)
thickness: léger=t-shirt/chemise fine, moyen=pull léger/chemise épaisse, épais=manteau/doudoune/jean
length: court=au-dessus du genou ou crop top, mi-long=genou ou chemise standard, long=cheville ou manteau long
Return only the JSON object, nothing else."""

_SHOE_PROMPT = """You are a footwear specialist analyzing a shoe photo for AI image generation.
Describe this shoe in precise visual terms so an AI model can reproduce it accurately.
Return ONLY valid JSON, no markdown, no explanation.

{
  "silhouette": "exact shoe type: e.g. low-top sneaker, mid-top sneaker, high-top sneaker, chelsea boot, ankle boot, combat boot, oxford, derby, loafer, mule, sandal, espadrille, moccasin, running shoe, basketball shoe, skate shoe",
  "upper_material": "main upper material: e.g. smooth leather, suede, canvas, mesh, knit, patent leather, nubuck, synthetic leather",
  "upper_details": "visible construction details on the upper: e.g. perforated toe box, brogue detailing, quilted panels, color-block panels, embossed texture, overlays, stitching lines, side stripe, logo patch",
  "toe_shape": "toe box shape: round, almond, square, pointed, or cap-toe",
  "closure": "lacing or fastening: e.g. flat white laces, round waxed laces, velcro strap, elastic gusset, side zip, buckle strap, slip-on, no closure",
  "collar": "ankle collar style: e.g. padded collar, low-cut collar, high ankle collar, no collar",
  "tongue": "tongue description: e.g. padded tongue, flat tongue, pull tab, no tongue",
  "sole_profile": "sole visual description: e.g. thick chunky rubber sole, thin leather sole, vulcanized flat sole, platform sole, wedge sole, cupped rubber sole, translucent gum sole",
  "sole_color": "sole color(s): e.g. white, black, gum brown, translucent, two-tone white and black",
  "heel": "heel type and height: e.g. flat heel, slight heel, block heel 3cm, wedge heel, no heel",
  "colorway": "complete colorway description listing each part: e.g. white leather upper with navy blue side stripe and red heel tab, white midsole, white outsole",
  "branding": "visible branding elements (describe visually, not by brand name): e.g. three parallel stripes on side panel, circular logo on tongue, embossed logo on heel counter, swoosh logo on lateral side",
  "overall_style": "one of: athletic, casual, formal, streetwear, workwear, outdoor",
  "image_gen_prompt": "A single English sentence (max 40 words) optimized for Flux image generation describing this shoe with enough visual detail to reproduce it. Focus on silhouette, colorway, sole, and key visual identifiers. No brand names."
}

Return only the JSON object, nothing else."""

_SHOE_CATEGORIES = {"shoes", "sneakers", "boots"}


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


def _call_ollama(img_b64: str, prompt: str, model: Optional[str] = None) -> Optional[dict]:
    """Appelle Qwen2.5-VL avec une image et un prompt, retourne le JSON parsé ou None."""
    payload = {
        "model": model if model else VISION_MODEL,
        "messages": [{"role": "user", "content": prompt, "images": [img_b64]}],
        "stream": False,
        "options": {"temperature": 0.05, "seed": 42},
    }
    try:
        resp = requests.post(f"{OLLAMA_BASE}/api/chat", json=payload, timeout=120)
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
    return _parse_json(raw), raw


def _analyze_shoe_detail(img_b64: str, model: Optional[str] = None) -> Optional[dict]:
    """
    Deuxième passe spécialisée chaussure.
    Retourne le dict JSON du prompt _SHOE_PROMPT, ou None si échec.
    """
    result, raw = _call_ollama(img_b64, _SHOE_PROMPT, model=model)
    if not result:
        log.warning("Shoe detail analysis — JSON invalide : %.200s", raw)
    return result


def analyze_garment(image_path: str, vision_model: Optional[str] = None) -> dict:
    """
    Analyse une photo de vêtement avec Qwen2.5-VL via Ollama.

    Pour les chaussures, effectue une deuxième passe spécialisée afin de
    générer une description visuelle détaillée utilisable par Flux/kontext.

    Returns:
        dict avec les attributs extraits (category, primary_color, style, etc.)

    Raises:
        RuntimeError si Ollama est inaccessible ou si l'analyse échoue.
    """
    try:
        img_b64 = _encode_image(image_path)
    except (OSError, IOError) as e:
        raise RuntimeError(f"Impossible de lire l'image : {e}")

    effective_model = vision_model if vision_model else None
    data, raw = _call_ollama(img_b64, _PROMPT, model=effective_model)

    if not data:
        log.warning("Qwen2.5-VL — JSON invalide reçu : %.200s", raw)
        raise RuntimeError("Le modèle n'a pas retourné un JSON valide. Relancez l'analyse.")

    category_raw = str(data.get("category", "")).lower().strip()
    season_raw = str(data.get("season", "")).lower().strip()

    result = {
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
        "thickness": str(data.get("thickness", "")).strip().lower() or None,
        "length": str(data.get("length", "")).strip().lower() or None,
        "description": str(data.get("description", "")).strip() or None,
        "shoe_detail": None,
    }

    # Deuxième passe spécialisée pour les chaussures
    if category_raw in _SHOE_CATEGORIES:
        log.info("Chaussure détectée — analyse détaillée en cours…")
        shoe_data = _analyze_shoe_detail(img_b64, model=effective_model)
        if shoe_data:
            result["shoe_detail"] = shoe_data
            # Remplace la description générique par le prompt image-gen optimisé
            image_gen_prompt = str(shoe_data.get("image_gen_prompt", "")).strip()
            if image_gen_prompt:
                result["description"] = image_gen_prompt
            # Enrichit les champs standards avec les données shoe si absents
            if not result["subcategory"]:
                result["subcategory"] = str(shoe_data.get("silhouette", "")).strip() or None
            if not result["material_guess"]:
                result["material_guess"] = str(shoe_data.get("upper_material", "")).strip() or None

    return result


def check_ollama() -> dict:
    """
    Vérifie si Ollama est accessible et si le modèle vision est disponible.

    Returns:
        {"running": bool, "model_available": bool, "available_models": list}
    """
    try:
        resp = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=2)
        resp.raise_for_status()
        models = [m["name"] for m in resp.json().get("models", [])]
        model_available = any(VISION_MODEL.split(":")[0] in m for m in models)
        return {"running": True, "model_available": model_available, "available_models": models}
    except Exception:
        return {"running": False, "model_available": False, "available_models": []}
