import json
import os
import time

from flask import Blueprint, Response, jsonify, stream_with_context

from config import BASE_DIR
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
    from models import UserSetting

    me = current_user()
    vision_model_pref = UserSetting.get(me.id, 'vision_model', '') or None

    items = me.items.filter(
        ClothingItem.image_path.isnot(None),
        db.or_(ClothingItem.ai_analyzed == False, ClothingItem.ai_analyzed == None),
    ).all()

    def generate():
        total = len(items)
        yield f"data: {json.dumps({'type': 'start', 'total': total})}\n\n"

        ok = 0
        errors = 0

        for i, item in enumerate(items):
            img_abs = os.path.join(BASE_DIR, 'static', item.image_path)
            last_error = None
            result = None

            # Signal immédiat que l'inférence commence (Qwen + FashionCLIP peuvent durer plusieurs minutes)
            yield f"data: {json.dumps({'type': 'processing', 'done': i, 'total': total, 'item': item.name})}\n\n"

            for attempt in range(3):
                if attempt > 0:
                    yield f"data: {json.dumps({'type': 'retry', 'done': i, 'total': total, 'item': item.name, 'attempt': attempt + 1})}\n\n"
                    time.sleep(3)
                try:
                    # Pipeline complet : Qwen2.5-VL (vision) + FashionCLIP (embedding)
                    result = analyze_and_store_item(item, img_abs, vision_model=vision_model_pref)
                    last_error = None
                    break
                except Exception as e:
                    last_error = str(e)[:120]

            if result is not None:
                item.ai_subcategory = result.get('subcategory')
                item.ai_style = result.get('style')
                item.ai_formality = result.get('formality')
                item.ai_pattern = result.get('pattern')
                item.ai_material = result.get('material_guess')
                item.ai_fit = result.get('fit')
                item.ai_secondary_color = result.get('secondary_color')
                item.ai_thickness = result.get('thickness')
                item.ai_length = result.get('length')
                item.ai_description = result.get('description')
                item.ai_color = result.get('primary_color') or None
                if not item.color and result.get('primary_color'):
                    item.color = result['primary_color']
                item.ai_analyzed = True
                db.session.commit()
                ok += 1
                yield f"data: {json.dumps({'type': 'progress', 'done': i + 1, 'total': total, 'item': item.name, 'ok': True})}\n\n"
            else:
                db.session.rollback()
                errors += 1
                yield f"data: {json.dumps({'type': 'progress', 'done': i + 1, 'total': total, 'item': item.name, 'ok': False, 'error': last_error})}\n\n"

        yield f"data: {json.dumps({'type': 'done', 'ok': ok, 'errors': errors, 'total': total})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={'X-Accel-Buffering': 'no', 'Cache-Control': 'no-cache'},
    )
