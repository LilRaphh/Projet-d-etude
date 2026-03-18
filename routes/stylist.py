"""
routes/stylist.py — Page Styliste IA
"""
import json
import os

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

from models import ClothingItem, Outfit, User, UserSetting
from extensions import db
from utils.weather import WeatherService


stylist_bp = Blueprint("stylist", __name__)

# ── Compatibilité paramètres appli ────────────────────────────────────────────

class AppSetting:
    @staticmethod
    def get(key, default=""):
        uid = session.get("user_id")
        if not uid:
            return default
        return UserSetting.get(uid, key, default)

    @staticmethod
    def set(key, value):
        uid = session.get("user_id")
        if not uid:
            return
        UserSetting.set(uid, key, value)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _uid():
    return session.get("user_id")


def _me():
    uid = _uid()
    return User.query.get(uid) if uid else None


def _api_key():
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if key:
        return key
    uid = _uid()
    return UserSetting.get(uid, "anthropic_key", "") if uid else ""


def _city():
    uid = _uid()
    return UserSetting.get(uid, "city", "") if uid else ""


def _save_city(city):
    uid = _uid()
    if uid and city:
        UserSetting.set(uid, "city", city)

# ── Claude ────────────────────────────────────────────────────────────────────

def suggest_outfits(items, weather, prompt):
    key = _api_key()
    if not key:
        return None, "Clé API Anthropic manquante — ajoutez-la dans les Paramètres (⚙️)."

    lines = []
    for item in items:
        parts = [f"ID:{item.id}", item.name, item.category]
        if item.color:
            parts.append(item.color)
        if item.brand:
            parts.append(item.brand)
        if item.season:
            parts.append(f"saison:{item.season}")
        if item.notes:
            parts.append(f"({item.notes[:50]})")
        lines.append(" | ".join(parts))

    weather_text = ""
    if weather:
        weather_text = (
            f"\nMétéo à {weather['city']} : {weather['temp']}°C "
            f"(ressenti {weather['feels']}°C), {weather['desc']}, vent {weather['wind']} km/h.\n"
            f"Conseil : {weather['layer']}"
        )

    try:
        import anthropic

        from config import ANTHROPIC_MODEL
        msg = anthropic.Anthropic(api_key=key).messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=1400,
            system=(
                "Tu es un styliste personnel. Tu proposes des tenues uniquement avec les pièces listées. "
                "Tu réponds UNIQUEMENT en JSON valide, sans texte ni balises markdown."
            ),
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Garde-robe (utilise UNIQUEMENT ces IDs) :\n{chr(10).join(lines)}\n"
                        f"{weather_text}\n\n"
                        f'Demande : "{prompt}"\n\n'
                        "Propose 3 tenues variées. JSON :\n"
                        '{"suggestions":[{"name":"...","vibe":"Casual/Chic/etc.",'
                        '"reasoning":"2-3 phrases","weather_note":"ou vide","item_ids":[1,2]}]}'
                    ),
                }
            ],
        )

        raw = msg.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        return json.loads(raw.strip()).get("suggestions", []), None

    except json.JSONDecodeError:
        return None, "Réponse IA invalide. Réessayez."
    except Exception as exc:
        return None, str(exc)

# ── Routes ────────────────────────────────────────────────────────────────────

@stylist_bp.route("/stylist", methods=["GET", "POST"])
def stylist():
    if not _uid():
        return redirect(url_for("auth.login"))

    city = _city()
    weather = WeatherService.get_current(city) if city else None
    suggestions = None
    user_prompt = ""
    error = None

    items = ClothingItem.query.filter_by(user_id=_uid()).order_by(
        ClothingItem.category,
        ClothingItem.name,
    ).all()

    if request.method == "POST":
        user_prompt = request.form.get("prompt", "").strip()
        new_city = request.form.get("city", "").strip()

        if new_city and new_city != city:
            _save_city(new_city)
            city = new_city
            weather = get_weather(city)

        if not user_prompt:
            error = "Décrivez l'occasion ou le style souhaité."
        elif not items:
            error = "Ajoutez d'abord des vêtements à votre garde-robe."
        else:
            suggestions, error = suggest_outfits(items, weather, user_prompt)

    return render_template(
        "stylist.html",
        me=_me(),
        weather=weather,
        city=city,
        user_prompt=user_prompt,
        suggestions=suggestions,
        items_map={item.id: item for item in items},
        item_count=len(items),
        error=error,
        has_api_key=bool(_api_key()),
        app_name=AppSetting.get("app_name", "Wardrobe"),
        accent=AppSetting.get("accent", "#C8956C"),
        currency=AppSetting.get("currency", "€"),
    )


@stylist_bp.route("/api/stylist/save", methods=["POST"])
def stylist_save():
    if not _uid():
        return jsonify(ok=False, error="Non connecté"), 401

    try:
        data = request.get_json(force=True)
        uid = _uid()
        item_ids = [int(item_id) for item_id in data.get("item_ids", [])]

        items = [
            ClothingItem.query.filter_by(id=item_id, user_id=uid).first()
            for item_id in item_ids
        ]
        items = [item for item in items if item]

        outfit = Outfit(
            name=data.get("name", "Tenue suggérée").strip(),
            description=data.get("reasoning", ""),
            user_id=uid,
            items=items,
        )

        db.session.add(outfit)
        db.session.commit()

        return jsonify(ok=True, outfit_id=outfit.id)

    except Exception as exc:
        return jsonify(ok=False, error=str(exc)), 400