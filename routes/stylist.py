"""
routes/stylist.py — Styliste unifié : Aujourd'hui · Claude · IA Locale
"""
import json
import logging
import os
from datetime import date
from typing import Optional

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

from config import ANTHROPIC_MODEL, OCCASIONS
from extensions import db
from models import ClothingItem, Outfit, User, UserSetting
from utils.auth import get_ctx
from utils.weather import WeatherService

log = logging.getLogger(__name__)
stylist_bp = Blueprint("stylist", __name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _uid() -> Optional[int]:
    return session.get("user_id")


def _api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if key:
        return key
    uid = _uid()
    return UserSetting.get(uid, "anthropic_key", "") if uid else ""


def _city() -> str:
    uid = _uid()
    return UserSetting.get(uid, "city", "") if uid else ""


def _save_city(city: str) -> None:
    uid = _uid()
    if uid and city:
        UserSetting.set(uid, "city", city)


# ---------------------------------------------------------------------------
# Brique Aujourd'hui (1 tenue ciblée)
# ---------------------------------------------------------------------------

def _suggest_today(items, weather, occasion: str):
    key = _api_key()
    if not key:
        return None, "Clé API Anthropic manquante — ajoutez-la dans les Paramètres ⚙️."
    if not items:
        return None, "Ajoutez d'abord des vêtements à votre garde-robe."

    lines = []
    for item in items:
        parts = [f"ID:{item.id}", item.name, item.category]
        if item.color:            parts.append(item.color)
        if item.brand:            parts.append(item.brand)
        if item.season:           parts.append(f"saison:{item.season}")
        if item.ai_style:         parts.append(f"style:{item.ai_style}")
        if item.ai_formality:     parts.append(f"formalite:{item.ai_formality}")
        parts.append(f"portee:{item.times_worn or 0}x")
        lines.append(" | ".join(parts))

    weather_ctx = (
        f"Météo : {weather['temp']}°C (ressenti {weather['feels']}°C), "
        f"{weather['desc']}, vent {weather['wind']} km/h. Conseil : {weather['layer']}"
    ) if weather else ""

    try:
        import anthropic

        msg = anthropic.Anthropic(api_key=key).messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=900,
            system=(
                "Tu es un styliste personnel expert. Propose UNE seule tenue parfaite pour aujourd'hui "
                "en utilisant UNIQUEMENT les IDs listés. Favorise les pièces peu portées et adaptées à la météo. "
                "Réponds UNIQUEMENT en JSON valide, sans markdown."
            ),
            messages=[{"role": "user", "content": (
                f"Aujourd'hui : {date.today().strftime('%A %d %B %Y')}\n"
                f"Occasion : {occasion or 'Quotidien'}\n{weather_ctx}\n\n"
                f"Garde-robe :\n{chr(10).join(lines)}\n\n"
                'JSON : {"name":"...","vibe":"Casual/Chic/etc.",'
                '"reasoning":"2-3 phrases","weather_note":"ou vide","item_ids":[1,2,3]}'
            )}],
        )
        raw = msg.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw.strip())
        data["item_ids"] = [int(i) for i in data.get("item_ids", [])]
        return data, None
    except json.JSONDecodeError:
        return None, "Réponse IA invalide. Réessayez."
    except Exception as exc:
        log.exception("_suggest_today")
        return None, str(exc)


# ---------------------------------------------------------------------------
# Brique Claude (3 tenues, prompt libre)
# ---------------------------------------------------------------------------

def _suggest_claude(items, weather, prompt):
    key = _api_key()
    if not key:
        return None, "Clé API Anthropic manquante — ajoutez-la dans les Paramètres ⚙️."

    lines = []
    for item in items:
        parts = [f"ID:{item.id}", item.name, item.category]
        if item.color:  parts.append(item.color)
        if item.brand:  parts.append(item.brand)
        if item.season: parts.append(f"saison:{item.season}")
        if item.notes:  parts.append(f"({item.notes[:50]})")
        lines.append(" | ".join(parts))

    weather_text = (
        f"\nMétéo à {weather['city']} : {weather['temp']}°C "
        f"(ressenti {weather['feels']}°C), {weather['desc']}, vent {weather['wind']} km/h.\n"
        f"Conseil : {weather['layer']}"
    ) if weather else ""

    try:
        import anthropic

        msg = anthropic.Anthropic(api_key=key).messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=1400,
            system=(
                "Tu es un styliste personnel. Tu proposes des tenues uniquement avec les pièces listées. "
                "Tu réponds UNIQUEMENT en JSON valide, sans texte ni balises markdown."
            ),
            messages=[{"role": "user", "content": (
                f"Garde-robe (utilise UNIQUEMENT ces IDs) :\n{chr(10).join(lines)}\n"
                f"{weather_text}\n\n"
                f'Demande : "{prompt}"\n\n'
                "Propose 3 tenues variées. JSON :\n"
                '{"suggestions":[{"name":"...","vibe":"Casual/Chic/etc.",'
                '"reasoning":"2-3 phrases","weather_note":"ou vide","item_ids":[1,2]}]}'
            )}],
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


# ---------------------------------------------------------------------------
# Brique IA Locale
# ---------------------------------------------------------------------------

def _suggest_local(user_id, weather, occasion):
    try:
        from ai.pipeline import recommend_outfits
        return recommend_outfits(user_id=user_id, weather=weather, occasion=occasion or None, n=3)
    except ImportError:
        return [], "Les dépendances IA locale (torch, transformers) ne sont pas installées."
    except Exception as e:
        log.exception("_suggest_local user %d", user_id)
        return [], f"Erreur IA locale : {e}"


def _local_ai_status(user_id):
    try:
        from ai.vision import check_ollama, VISION_MODEL
        from ai.embeddings import collection_count
        info = check_ollama()
        return {
            "ollama_running": info["running"],
            "model_available": info["model_available"],
            "vision_model": VISION_MODEL,
            "indexed": collection_count(user_id),
        }
    except ImportError:
        return {"ollama_running": False, "model_available": False, "vision_model": "qwen2.5vl:7b", "indexed": 0}


# ---------------------------------------------------------------------------
# Route principale
# ---------------------------------------------------------------------------

@stylist_bp.route("/stylist", methods=["GET", "POST"])
def stylist():
    if not _uid():
        return redirect(url_for("auth.login"))

    ctx = get_ctx()
    me = ctx["me"]
    city = _city()
    weather = WeatherService.get_current(city) if city else None

    # Mode actif : today (défaut) | claude | local
    active_mode = request.form.get("mode", request.args.get("mode", "today"))

    suggestions_claude = None
    suggestions_local  = None
    error       = None
    user_prompt = ""
    occasion    = ""

    items = ClothingItem.query.filter_by(user_id=_uid()).order_by(
        ClothingItem.category, ClothingItem.name
    ).all()

    if request.method == "POST":
        new_city = request.form.get("city", "").strip()
        if new_city and new_city != city:
            _save_city(new_city)
            city = new_city
            weather = WeatherService.get_current(city)

        if active_mode == "claude":
            user_prompt = request.form.get("prompt", "").strip()
            if not user_prompt:
                error = "Décrivez l'occasion ou le style souhaité."
            elif not items:
                error = "Ajoutez d'abord des vêtements à votre garde-robe."
            else:
                suggestions_claude, error = _suggest_claude(items, weather, user_prompt)

        elif active_mode == "local":
            occasion = request.form.get("occasion", "").strip()
            if not items:
                error = "Ajoutez d'abord des vêtements à votre garde-robe."
            else:
                suggestions_local, error = _suggest_local(_uid(), weather, occasion)

    ai_status      = _local_ai_status(_uid())
    analyzed_count = me.items.filter_by(ai_analyzed=True).count()

    return render_template(
        "stylist.html",
        weather=weather,
        city=city,
        active_mode=active_mode,
        occasions=OCCASIONS,
        # Claude
        user_prompt=user_prompt,
        suggestions_claude=suggestions_claude,
        has_api_key=bool(_api_key()),
        items_map={item.id: item for item in items},
        item_count=len(items),
        # Local
        occasion=occasion,
        suggestions_local=suggestions_local,
        ai_status=ai_status,
        analyzed_count=analyzed_count,
        total_items=len(items),
        error=error,
        **ctx,
    )


# ---------------------------------------------------------------------------
# API — Aujourd'hui (AJAX)
# ---------------------------------------------------------------------------

@stylist_bp.route("/api/today/suggest", methods=["POST"])
def today_suggest():
    if not _uid():
        return jsonify(ok=False, error="Non connecté"), 401

    data     = request.get_json(force=True) or {}
    occasion = data.get("occasion", "Quotidien").strip()
    city     = _city()
    weather  = WeatherService.get_current(city) if city else None
    items    = ClothingItem.query.filter_by(user_id=_uid()).order_by(
        ClothingItem.times_worn.asc(), ClothingItem.created_at.desc()
    ).all()

    suggestion, error = _suggest_today(items, weather, occasion)
    if error:
        return jsonify(ok=False, error=error)

    items_map = {item.id: item for item in items}
    enriched  = []
    for iid in suggestion.get("item_ids", []):
        item = items_map.get(iid)
        if item:
            enriched.append({
                "id": item.id, "name": item.name, "category": item.category,
                "color": item.color or "", "brand": item.brand or "",
                "thumb": item.thumb_path or item.image_path or "",
                "times_worn": item.times_worn or 0,
            })
    suggestion["items"] = enriched
    return jsonify(ok=True, suggestion=suggestion, weather=weather)


@stylist_bp.route("/api/today/save", methods=["POST"])
def today_save():
    if not _uid():
        return jsonify(ok=False, error="Non connecté"), 401

    data     = request.get_json(force=True) or {}
    uid      = _uid()
    item_ids = [int(i) for i in data.get("item_ids", []) if i is not None]

    if not item_ids:
        return jsonify(ok=False, error="Aucun vêtement."), 400

    items = [ClothingItem.query.filter_by(id=iid, user_id=uid).first() for iid in item_ids]
    items = [it for it in items if it]
    if not items:
        return jsonify(ok=False, error="Aucun vêtement valide."), 400

    outfit = Outfit(
        name=(data.get("name") or f"Tenue du {date.today().strftime('%d/%m/%Y')}").strip(),
        description=data.get("reasoning", ""),
        occasion=data.get("occasion", ""),
        user_id=uid,
        items=items,
    )
    db.session.add(outfit)
    if data.get("mark_worn"):
        for item in items:
            item.times_worn = (item.times_worn or 0) + 1
    db.session.commit()
    return jsonify(ok=True, outfit_id=outfit.id)


# ---------------------------------------------------------------------------
# API — Sauvegarde tenue (Claude / IA Locale)
# ---------------------------------------------------------------------------

@stylist_bp.route("/api/stylist/save", methods=["POST"])
def stylist_save():
    if not _uid():
        return jsonify(ok=False, error="Non connecté"), 401

    try:
        data     = request.get_json(force=True)
        uid      = _uid()
        item_ids = [int(i) for i in data.get("item_ids", []) if i is not None]

        if not item_ids:
            return jsonify(ok=False, error="Aucun vêtement à sauvegarder."), 400

        items = [ClothingItem.query.filter_by(id=iid, user_id=uid).first() for iid in item_ids]
        items = [it for it in items if it]
        if not items:
            return jsonify(ok=False, error="Aucun vêtement valide."), 400

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
        db.session.rollback()
        return jsonify(ok=False, error=str(exc)), 400
