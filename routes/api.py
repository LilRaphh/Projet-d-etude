import json
import os
import threading
import time

from flask import Blueprint, Response, jsonify, stream_with_context

from config import ANALYSIS_MAX_RETRIES, ANALYSIS_RETRY_DELAY, BASE_DIR
from extensions import db
from models import ClothingItem, Outfit
from utils.auth import current_user, login_required

api_bp = Blueprint('api', __name__, url_prefix='/api')


@api_bp.route('/fav/<int:iid>', methods=['POST'])
@login_required
def api_fav(iid):
    me = current_user()
    item = me.items.filter_by(id=iid).first()
    if not item:
        return jsonify(error='not found'), 404
    item.is_favorite = not item.is_favorite
    db.session.commit()
    return jsonify(id=item.id, is_favorite=item.is_favorite)


@api_bp.route('/worn/<int:iid>', methods=['POST'])
@login_required
def api_worn(iid):
    me = current_user()
    item = me.items.filter_by(id=iid).first()
    if not item:
        return jsonify(error='not found'), 404
    item.times_worn += 1
    db.session.commit()
    return jsonify(id=item.id, times_worn=item.times_worn)


@api_bp.route('/outfit-worn/<int:oid>', methods=['POST'])
@login_required
def api_outfit_worn(oid):
    me = current_user()
    outfit = me.outfits.filter_by(id=oid).first()
    if not outfit:
        return jsonify(error='not found'), 404
    outfit.times_worn += 1
    db.session.commit()
    return jsonify(id=outfit.id, times_worn=outfit.times_worn)


@api_bp.route('/analyze-all', methods=['POST'])
@login_required
def api_analyze_all():
    from ai.pipeline import analyze_and_store_item
    from ai.vision import check_ollama, VISION_MODEL
    from models import UserSetting

    me = current_user()
    vision_model_pref = UserSetting.get(me.id, 'vision_model', '') or None

    items = me.items.filter(
        ClothingItem.image_path.isnot(None),
        ClothingItem.ai_analyzed.isnot(True),
    ).all()

    def generate():
        effective_model = vision_model_pref or VISION_MODEL

        # ── Pré-check Ollama ──────────────────────────────────────────────────
        ollama_status = check_ollama()
        if not ollama_status["running"]:
            yield f"data: {json.dumps({'type': 'error', 'message': 'Ollama est inaccessible. Vérifiez que le service est démarré.'})}\n\n"
            return

        # Vérifie si le modèle effectif (préférence utilisateur ou défaut) est disponible
        model_base = effective_model.split(":")[0]
        if not any(model_base in m for m in ollama_status["available_models"]):
            yield f"data: {json.dumps({'type': 'pulling', 'model': effective_model})}\n\n"

            try:
                from ai.ollama_setup import _pull_model_streaming
                pull_success = False
                for prog in _pull_model_streaming(effective_model):
                    status = prog.get("status", "")
                    total = prog.get("total", 0)
                    completed = prog.get("completed", 0)
                    pct = round(completed / total * 100) if total > 0 else None
                    yield f"data: {json.dumps({'type': 'pulling_progress', 'status': status, 'pct': pct})}\n\n"
                    if status == "success":
                        pull_success = True
                if not pull_success:
                    raise RuntimeError("Fin du stream sans confirmation de succès.")
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'message': f'Impossible de télécharger {effective_model} : {str(e)[:100]}. Changez de modèle dans Paramètres → IA.'})}\n\n"
                return

            yield f"data: {json.dumps({'type': 'pull_done', 'model': effective_model})}\n\n"

        # ── Démarrage de la boucle d'analyse ─────────────────────────────────
        total = len(items)
        yield f"data: {json.dumps({'type': 'start', 'total': total})}\n\n"

        ok = 0
        errors = 0
        model_fatal = False

        for i, item in enumerate(items):
            if model_fatal:
                break
            img_abs = os.path.join(BASE_DIR, 'static', item.image_path)
            last_error = None
            result = None
            result_holder = [None]
            error_holder = [None]

            # Extraire les données SQLAlchemy ici (thread principal, session active)
            # pour éviter un DetachedInstanceError dans le thread après db.session.commit()
            item_id = item.id
            item_name = item.name
            item_category = item.category
            item_color = item.color

            yield f"data: {json.dumps({'type': 'processing', 'done': i, 'total': total, 'item': item_name})}\n\n"

            for attempt in range(ANALYSIS_MAX_RETRIES):
                if attempt > 0:
                    yield f"data: {json.dumps({'type': 'retry', 'done': i, 'total': total, 'item': item_name, 'attempt': attempt + 1})}\n\n"
                    time.sleep(ANALYSIS_RETRY_DELAY)

                result_holder[0] = None
                error_holder[0] = None

                from flask import current_app
                _app = current_app._get_current_object()

                def _run(img_abs=img_abs):
                    try:
                        with _app.app_context():
                            result_holder[0] = analyze_and_store_item(item, img_abs, vision_model=vision_model_pref)
                    except Exception as exc:
                        error_holder[0] = str(exc)[:120]

                t = threading.Thread(target=_run, daemon=True)
                t.start()

                # Keep-alive SSE toutes les 5s pendant l'inférence (évite timeout ngrok/proxy)
                while t.is_alive():
                    t.join(timeout=5)
                    if t.is_alive():
                        yield ": keep-alive\n\n"

                if result_holder[0] is not None:
                    result = result_holder[0]
                    last_error = None
                    break
                last_error = error_holder[0]
                if last_error and last_error.startswith("MODEL_NOT_FOUND:"):
                    model_name = last_error.split(":", 1)[1]
                    last_error = f"Modèle '{model_name}' introuvable dans Ollama."
                    model_fatal = True
                    break

            if result is not None:
                # Re-fetch depuis la session (peut être expired après le dernier commit)
                fresh = db.session.get(ClothingItem, item_id)
                if fresh:
                    fresh.ai_subcategory = result.get('subcategory')
                    fresh.ai_style = result.get('style')
                    fresh.ai_formality = result.get('formality')
                    fresh.ai_pattern = result.get('pattern')
                    fresh.ai_material = result.get('material_guess')
                    fresh.ai_fit = result.get('fit')
                    fresh.ai_secondary_color = result.get('secondary_color')
                    fresh.ai_thickness = result.get('thickness')
                    fresh.ai_length = result.get('length')
                    fresh.ai_description = result.get('description')
                    fresh.ai_color = result.get('primary_color') or None
                    if not item_color and result.get('primary_color'):
                        fresh.color = result['primary_color']
                    fresh.ai_analyzed = True
                    db.session.commit()
                ok += 1
                yield f"data: {json.dumps({'type': 'progress', 'done': i + 1, 'total': total, 'item': item_name, 'ok': True})}\n\n"
            else:
                db.session.rollback()
                errors += 1
                yield f"data: {json.dumps({'type': 'progress', 'done': i + 1, 'total': total, 'item': item_name, 'ok': False, 'error': last_error})}\n\n"

        extra = {}
        if model_fatal:
            extra["fatal"] = f"Le modèle {effective_model} n'est pas disponible dans Ollama. Allez dans Paramètres → IA pour le configurer ou le télécharger."
        yield f"data: {json.dumps({'type': 'done', 'ok': ok, 'errors': errors, 'total': total, **extra})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={'X-Accel-Buffering': 'no', 'Cache-Control': 'no-cache'},
    )
