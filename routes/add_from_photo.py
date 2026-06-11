"""
routes/add_from_photo.py — Ajout de vêtements depuis une photo entière.

Détection via OWL-ViT (local, HuggingFace transformers) avec fallback Ollama.

Routes :
  GET  /add-from-photo                       → page de la fonctionnalité
  POST /api/add-from-photo/analyze           → analyse la photo, renvoie les items détectés (JSON)
  POST /api/add-from-photo/save             → enregistre les items sélectionnés (JSON)
  POST /api/add-from-photo/download-model   → lance le téléchargement OWL-ViT en arrière-plan
  GET  /api/add-from-photo/model-status     → état du téléchargement {status, progress, error}
"""

import logging
import os
import uuid

from flask import Blueprint, jsonify, render_template, request

from config import BASE_DIR, CATEGORIES, COLORS, SEASONS
from extensions import csrf, db
from models import ClothingItem, UserSetting
from utils.auth import current_user, get_ctx, login_required
from utils.images import allowed

log = logging.getLogger(__name__)

photo_bp = Blueprint('add_from_photo', __name__)

_CROP_PREFIX  = 'uploads/extractions/crops/'
_THUMB_PREFIX = 'uploads/extractions/crops/thumbs/'


def _is_safe_path(path: str, prefix: str) -> bool:
    """Vérifie qu'un chemin relatif est dans le dossier attendu et que le fichier existe."""
    if not path or '..' in path:
        return False
    if not path.startswith(prefix):
        return False
    return os.path.isfile(os.path.join(BASE_DIR, 'static', path))


def _get_vision_model(user_id: int) -> str:
    """Retourne le modèle vision configuré pour l'utilisateur, ou le modèle par défaut."""
    from ai.vision import VISION_MODEL
    return UserSetting.get(user_id, 'vision_model', '') or VISION_MODEL


# ─── Routes ──────────────────────────────────────────────────────────────────

@photo_bp.route('/add-from-photo')
@login_required
def add_from_photo_page():
    from ai.vision import check_ollama, VISION_MODEL
    from utils.photo_item_extractor import is_owlvit_cached, get_download_state, start_owlvit_download
    ctx = get_ctx()
    me  = ctx['me']

    # ── Sous-actions JSON via ?action=… (même route, pas de CSRF) ──────────────
    action = request.args.get('action')
    if action == 'start-download':
        try:
            if is_owlvit_cached():
                return jsonify(status='already_cached')
            state = get_download_state()
            if state.get('status') == 'downloading':
                return jsonify(status='already_downloading')
            start_owlvit_download()
            return jsonify(status='started')
        except Exception as exc:
            log.exception("Erreur start-download")
            return jsonify(error=str(exc)), 500

    if action == 'model-status':
        try:
            if is_owlvit_cached():
                return jsonify(status='ready')
            state = get_download_state()
            return jsonify(
                status=state.get('status', 'idle'),
                progress=state.get('progress', 0),
                current_file=state.get('current_file'),
                error=state.get('error'),
            )
        except Exception as exc:
            log.exception("Erreur model-status")
            return jsonify(error=str(exc)), 500

    # ── Rendu normal de la page ─────────────────────────────────────────────────
    ollama_status      = check_ollama()
    vision_model       = _get_vision_model(me.id)
    owlvit_cached      = is_owlvit_cached()
    dl_state           = get_download_state()
    owlvit_downloading = dl_state.get('status') == 'downloading'

    return render_template(
        'add_from_photo.html',
        cats=CATEGORIES,
        colors=COLORS,
        seasons=SEASONS,
        ollama_ok=ollama_status.get('running', False),
        vision_model=vision_model,
        owlvit_available=owlvit_cached,
        owlvit_downloading=owlvit_downloading,
        **ctx,
    )


@photo_bp.route('/api/add-from-photo/download-model', methods=['GET', 'POST'])
@csrf.exempt
@login_required
def download_model():
    try:
        from utils.photo_item_extractor import is_owlvit_cached, start_owlvit_download, get_download_state
        if is_owlvit_cached():
            return jsonify(status='already_cached')
        state = get_download_state()
        if state.get('status') == 'downloading':
            return jsonify(status='already_downloading')
        start_owlvit_download()
        return jsonify(status='started')
    except Exception as exc:
        log.exception("Erreur route download-model")
        return jsonify(error=str(exc)), 500


@photo_bp.route('/api/add-from-photo/model-status')
@csrf.exempt
@login_required
def model_status():
    try:
        from utils.photo_item_extractor import is_owlvit_cached, get_download_state
        if is_owlvit_cached():
            return jsonify(status='ready')
        state = get_download_state()
        return jsonify(
            status=state.get('status', 'idle'),
            progress=state.get('progress', 0),
            current_file=state.get('current_file'),
            error=state.get('error'),
        )
    except Exception as exc:
        log.exception("Erreur route model-status")
        return jsonify(error=str(exc)), 500


@photo_bp.route('/api/add-from-photo/analyze', methods=['POST'])
@login_required
def analyze_photo():
    """Reçoit une photo, appelle qwen2.5vl via Ollama, retourne les vêtements détectés."""
    me           = current_user()
    vision_model = _get_vision_model(me.id)

    file_obj = request.files.get('photo')
    if not file_obj or not file_obj.filename:
        return jsonify(error='Aucun fichier fourni.'), 400

    if not allowed(file_obj.filename, file_obj.stream):
        return jsonify(error='Format non supporté. Utilisez JPG, PNG ou WEBP.'), 400

    session_id = uuid.uuid4().hex

    from utils.photo_item_extractor import extract_items_from_photo, save_source_photo

    source_path = save_source_photo(file_obj, session_id)
    if not source_path:
        return jsonify(error='Impossible de sauvegarder la photo. Vérifiez le format et réessayez.')

    try:
        items = extract_items_from_photo(source_path, session_id, vision_model)
    except RuntimeError as exc:
        msg = str(exc)
        log.warning("Erreur analyse photo user %s : %s", me.id, msg)
        return jsonify(error=msg)
    except Exception:
        log.exception("Erreur inattendue lors de l'analyse photo pour user %s", me.id)
        return jsonify(error='Erreur interne lors de l\'analyse. Réessayez.')

    if not items:
        return jsonify(
            session_id=session_id,
            items=[],
            message=(
                'Aucun vêtement détecté. '
                'Essayez avec une photo où les vêtements sont bien visibles et la personne est en pied.'
            ),
        )

    return jsonify(
        session_id=session_id,
        items=[
            {
                'name':            it.name,
                'category':        it.category,
                'color':           it.color,
                'crop_path':       it.crop_path,
                'crop_thumb_path': it.crop_thumb_path,
            }
            for it in items
        ],
    )


@photo_bp.route('/api/add-from-photo/save', methods=['POST'])
@login_required
def save_photo_items():
    """Enregistre les items sélectionnés par l'utilisateur comme ClothingItem."""
    me         = current_user()
    data       = request.get_json(silent=True) or {}
    items_data = data.get('items', [])

    if not items_data:
        return jsonify(error='Aucun élément à sauvegarder.'), 400

    created: list = []
    errors:  list = []

    for i, item_data in enumerate(items_data):
        name = (item_data.get('name') or '').strip()
        if not name:
            errors.append({'index': i, 'error': 'Nom requis'})
            continue

        crop_path  = item_data.get('crop_path', '') or ''
        thumb_path = item_data.get('crop_thumb_path', '') or ''

        if not _is_safe_path(crop_path, _CROP_PREFIX):
            errors.append({'index': i, 'error': 'Image de découpe introuvable'})
            continue

        if not _is_safe_path(thumb_path, _THUMB_PREFIX):
            thumb_path = None

        category = item_data.get('category') or 'Autre'
        if category not in CATEGORIES:
            category = 'Autre'

        item = ClothingItem(
            user_id    = me.id,
            name       = name,
            category   = category,
            color      = item_data.get('color') or None,
            season     = item_data.get('season') or None,
            image_path = crop_path,
            thumb_path = thumb_path,
        )
        db.session.add(item)
        db.session.flush()
        created.append({'id': item.id, 'name': name})

    db.session.commit()
    return jsonify(created=created, errors=errors)
