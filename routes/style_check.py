"""
routes/style_check.py
Page "Vérifier mon style" – analyse vestimentaire via Groq Vision (1 seul appel REST)
"""
import base64
import json
import os

import requests
from flask import Blueprint, jsonify, render_template, request

from utils.auth import get_ctx, login_required

style_check_bp = Blueprint('style_check', __name__)

GROQ_MODEL = os.environ.get('GROQ_MODEL', 'meta-llama/llama-4-scout-17b-16e-instruct')
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

STYLE_CATEGORIES = [
    "Sportif", "Décontracté", "Streetwear", "Urbain",
    "Minimaliste", "Élégant", "Professionnel", "Classique",
    "Vintage", "Bohème", "Avant-garde"
]

COLOR_KEYS = [
    "Blanc", "Noir", "Gris", "Rouge", "Bleu", "Vert",
    "Jaune", "Marron", "Beige", "Violet", "Rose", "Orange",
    "Doré", "Argenté", "Bordeaux", "Turquoise"
]

COLOR_TEMPLATE = {k: 0 for k in COLOR_KEYS}

FULL_PROMPT = f"""Tu es un expert en analyse vestimentaire et mode.
Analyse cette image et retourne UN SEUL JSON avec exactement cette structure.
Réponds UNIQUEMENT avec le JSON, sans texte autour, sans balises markdown.

{{
  "analyse": {{
    "personne": {{
      "age_tranche": "",
      "genre_apparent": "",
      "couleur_peau": ""
    }},
    "tenue": {{
      "haut": {{"type": "", "couleur": "", "teinte": "", "marque": "", "style": ""}},
      "bas": {{"type": "", "couleur": "", "teinte": "", "marque": "", "style": ""}},
      "chaussures": {{"type": "", "couleur": "", "marque": ""}},
      "accessoires": {{
        "echarpe": 0, "chapeau": 0, "sac": 0, "ceinture": 0,
        "bijoux": 0, "lunettes": 0, "montre": 0, "autre": 0,
        "style_general": "", "couleur_generale": ""
      }}
    }},
    "style_global": "",
    "saison_vetement": "",
    "taille_estimee": "",
    "occasion": ""
  }},
  "radar": {{
    "Sportif": 0, "Décontracté": 0, "Streetwear": 0, "Urbain": 0,
    "Minimaliste": 0, "Élégant": 0, "Professionnel": 0, "Classique": 0,
    "Vintage": 0, "Bohème": 0, "Avant-garde": 0
  }},
  "couleurs": {{
    "haut": {json.dumps(COLOR_TEMPLATE)},
    "bas": {json.dumps(COLOR_TEMPLATE)},
    "chaussures": {json.dumps(COLOR_TEMPLATE)},
    "accessoires": {json.dumps(COLOR_TEMPLATE)}
  }}
}}

Règles :
- age_tranche : "0-9" "10-19" "20-29" "30-39" "40-49" "50-59" "60-69" "70-79" "80-89" "90+"
- couleur_peau : "Très clair" "Clair" "Moyen clair" "Moyen" "Moyen foncé" "Foncé" "Très foncé" "Non déterminé"
- saison_vetement : "Printemps" "Été" "Automne" "Hiver" "Toute saison" "Non déterminé"
- marque : essaie de deviner parmi Nike Adidas Puma Zara H&M Uniqlo Levi's Tommy Hilfiger Calvin Klein Lacoste Ralph Lauren The North Face Converse Vans Gucci, sinon "Autre"
- style : "Décontracté" "Sportif" "Professionnel" "Élégant" "Streetwear" "Vintage" "Minimaliste" "Bohème" "Urbain" "Classique" "Avant-garde"
- couleur : "Blanc" "Noir" "Gris" "Rouge" "Bleu" "Vert" "Jaune" "Marron" "Beige" "Violet" "Rose" "Orange" "Doré" "Argenté" "Bordeaux" "Turquoise"
- teinte : "Pâle" "Claire" "Normal" "Foncé" "Très foncé" "Vive" "Pastel" "Métallique"
- taille_estimee : "XS" "S" "M" "L" "XL" "XXL"
- occasion : "Quotidien" "Travail" "Soirée" "Sport" "Voyage" "Cérémonie" "Autre"
- accessoires : 0 ou 1
- radar : valeur entre 0.0 et 1.0 pour chaque style
- couleurs : pourcentages (total = 100 par catégorie, 0 si non visible)
"""


def _groq_call(image_b64: str, mime_type: str):
    """Appel REST Groq avec vision. Retourne (json_dict, erreur)."""
    api_key = os.environ.get('GROQ_API_KEY', '').strip()
    if not api_key:
        return None, "Clé API Groq manquante (GROQ_API_KEY dans .env)"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": GROQ_MODEL,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": FULL_PROMPT},
                {"type": "image_url", "image_url": {
                    "url": f"data:{mime_type};base64,{image_b64}"
                }}
            ]
        }],
        "max_tokens": 2000,
        "temperature": 0.1
    }

    try:
        resp = requests.post(GROQ_API_URL, headers=headers, json=payload, timeout=60)
    except requests.exceptions.Timeout:
        return None, "Timeout – Groq met trop de temps à répondre."
    except requests.exceptions.RequestException as e:
        return None, f"Erreur réseau : {str(e)[:200]}"

    if resp.status_code != 200:
        try:
            msg = resp.json().get('error', {}).get('message', resp.text)[:300]
        except Exception:
            msg = resp.text[:300]
        if resp.status_code == 429:
            return None, f"Quota Groq dépassé. Attends quelques secondes. ({msg})"
        if resp.status_code in (401, 403):
            return None, "Clé API Groq invalide. Vérifie GROQ_API_KEY dans ton .env."
        return None, f"Erreur Groq {resp.status_code} : {msg}"

    try:
        text = resp.json()['choices'][0]['message']['content'].strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        return json.loads(text), None
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        return None, f"Réponse Groq invalide : {str(e)}"


@style_check_bp.route('/style-check', methods=['GET'])
@login_required
def style_check():
    ctx = get_ctx()
    groq_ok = bool(os.environ.get('GROQ_API_KEY', '').strip())
    return render_template('style_check.html', gemini_ok=groq_ok, gemini_model=GROQ_MODEL, **ctx)


@style_check_bp.route('/style-check/analyze', methods=['POST'])
@login_required
def style_check_analyze():
    data = request.get_json(silent=True)
    if not data or 'image' not in data:
        return jsonify(error="Aucune image reçue."), 400

    result, err = _groq_call(data['image'], data.get('mime_type', 'image/jpeg'))
    if err:
        status = 429 if ('429' in err or 'Quota' in err) else 500
        return jsonify(error=err), status

    return jsonify(result)
