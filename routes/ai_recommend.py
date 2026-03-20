"""
routes/ai_recommend.py — Routes Flask pour les briques IA locales.

Endpoints :
  GET  /ai/status              — état Ollama + stats d'indexation
  POST /ai/analyze/<item_id>   — analyser un vêtement (vision + embedding)
  POST /ai/analyze-all         — analyser tous les vêtements non encore indexés
  GET|POST /ai/recommend       — page de recommandation de tenues
"""
import logging
import os
from typing import Optional

from flask import Blueprint, jsonify, redirect, request, url_for

from extensions import db
from utils.auth import current_user, login_required

log = logging.getLogger(__name__)

ai_bp = Blueprint("ai", __name__, url_prefix="/ai")


def _image_full_path(item) -> Optional[str]:
    """Chemin absolu vers la meilleure image disponible d'un item."""
    from config import BASE_DIR
    path = item.thumb_path or item.image_path
    if not path:
        return None
    return os.path.join(BASE_DIR, "static", path)


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

@ai_bp.route("/status")
@login_required
def status():
    from ai.vision import VISION_MODEL, check_ollama
    from ai.embeddings import collection_count

    me = current_user()
    ollama_info = check_ollama()
    indexed = collection_count(me.id)
    total = me.items.count()
    analyzed = me.items.filter_by(ai_analyzed=True).count()

    return jsonify(
        {
            "ollama_running": ollama_info["running"],
            "model_available": ollama_info["model_available"],
            "vision_model": VISION_MODEL,
            "available_models": ollama_info["available_models"],
            "indexed_in_chroma": indexed,
            "total_items": total,
            "ai_analyzed_in_db": analyzed,
        }
    )


# ---------------------------------------------------------------------------
# Analyse d'un vêtement
# ---------------------------------------------------------------------------

@ai_bp.route("/analyze/<int:item_id>", methods=["POST"])
@login_required
def analyze_item(item_id):
    from models import UserSetting

    me = current_user()
    item = me.items.filter_by(id=item_id).first()

    if not item:
        return jsonify({"error": "Vêtement introuvable."}), 404

    img_path = _image_full_path(item)
    if not img_path or not os.path.exists(img_path):
        return jsonify({"error": "Ce vêtement n'a pas de photo — ajoutez-en une pour l'analyser."}), 400

    vision_model = UserSetting.get(me.id, 'vision_model', '').strip() or None

    try:
        from ai.pipeline import analyze_and_store_item

        ai_attrs = analyze_and_store_item(item, img_path, vision_model=vision_model)

        # Persistance des attributs IA dans la base SQLite
        item.ai_subcategory = ai_attrs.get("subcategory")
        item.ai_style = ai_attrs.get("style")
        item.ai_formality = ai_attrs.get("formality")
        item.ai_pattern = ai_attrs.get("pattern")
        item.ai_material = ai_attrs.get("material_guess")
        item.ai_fit = ai_attrs.get("fit")
        item.ai_secondary_color = ai_attrs.get("secondary_color")
        item.ai_thickness = ai_attrs.get("thickness")
        item.ai_length = ai_attrs.get("length")
        item.ai_description = ai_attrs.get("description")
        item.ai_analyzed = True

        # Auto-complétion des champs vides dans l'app
        if not item.color:
            item.color = ai_attrs.get("primary_color")
        if not item.season:
            item.season = ai_attrs.get("season")

        db.session.commit()
        return jsonify({"ok": True, "attrs": ai_attrs})

    except RuntimeError as e:
        log.error("analyze_item %d: %s", item_id, e)
        return jsonify({"error": str(e)}), 500
    except Exception:
        log.exception("analyze_item %d unexpected error", item_id)
        return jsonify({"error": "Erreur interne lors de l'analyse. Consultez les logs."}), 500


# ---------------------------------------------------------------------------
# Analyse en lot
# ---------------------------------------------------------------------------

@ai_bp.route("/analyze-all", methods=["POST"])
@login_required
def analyze_all():
    from models import UserSetting

    me = current_user()
    pending = me.items.filter_by(ai_analyzed=False).all()
    vision_model = UserSetting.get(me.id, 'vision_model', '').strip() or None

    results = {"success": 0, "skipped": 0, "failed": 0, "errors": []}

    for item in pending:
        img_path = _image_full_path(item)
        if not img_path or not os.path.exists(img_path):
            results["skipped"] += 1
            continue

        try:
            from ai.pipeline import analyze_and_store_item

            ai_attrs = analyze_and_store_item(item, img_path, vision_model=vision_model)

            item.ai_subcategory = ai_attrs.get("subcategory")
            item.ai_style = ai_attrs.get("style")
            item.ai_formality = ai_attrs.get("formality")
            item.ai_pattern = ai_attrs.get("pattern")
            item.ai_material = ai_attrs.get("material_guess")
            item.ai_fit = ai_attrs.get("fit")
            item.ai_secondary_color = ai_attrs.get("secondary_color")
            item.ai_thickness = ai_attrs.get("thickness")
            item.ai_length = ai_attrs.get("length")
            item.ai_description = ai_attrs.get("description")
            item.ai_analyzed = True

            if not item.color:
                item.color = ai_attrs.get("primary_color")
            if not item.season:
                item.season = ai_attrs.get("season")

            db.session.commit()
            results["success"] += 1

        except Exception as e:
            log.error("analyze_all item %d (%s): %s", item.id, item.name, e)
            results["failed"] += 1
            results["errors"].append(f"{item.name}: {str(e)[:120]}")

    return jsonify(results)


# ---------------------------------------------------------------------------
# Recommandation de tenues
# ---------------------------------------------------------------------------

@ai_bp.route("/recommend", methods=["GET", "POST"])
@login_required
def recommend():
    return redirect(url_for("stylist.stylist", mode="local"))
