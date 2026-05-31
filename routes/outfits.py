import base64
import json
import os
import uuid

from flask import Blueprint, flash, jsonify, redirect, render_template, request
from PIL import Image, ImageOps

from config import BASE_DIR, OCCASIONS, OUTFIT_FOLDER, SEASONS, UPLOAD_FOLDER
from extensions import db
from models import ClothingItem, Outfit, UserSetting
from utils.ai import generate_image, generate_prompt_with_claude
from utils.auth import current_user, get_ctx, login_required
from utils.images import allowed

outfits_bp = Blueprint('outfits', __name__, url_prefix='/outfits')


def _parse_rating(raw: str):
    """Parse une note 1-5 depuis le formulaire. Retourne None si invalide."""
    if not raw:
        return None
    try:
        v = int(raw)
        return v if 1 <= v <= 5 else None
    except ValueError:
        return None


@outfits_bp.route('')
@login_required
def outfits():
    ctx = get_ctx()
    me = ctx['me']
    return render_template('outfits.html', outfits=me.outfits.order_by(Outfit.created_at.desc()).all(), **ctx)


@outfits_bp.route('/new', methods=['GET', 'POST'])
@login_required
def outfit_new():
    ctx = get_ctx()
    me = ctx['me']
    all_items = me.items.order_by(ClothingItem.category, ClothingItem.name).all()

    if request.method == 'POST':
        raw = [x.strip() for x in request.form.get('item_ids', '').split(',') if x.strip()]
        items = [me.items.filter_by(id=int(i)).first() for i in raw if i.isdigit()]
        items = [i for i in items if i]
        rating = request.form.get('rating', '')

        outfit = Outfit(
            user_id=me.id,
            name=request.form['name'].strip(),
            description=request.form.get('description', '').strip() or None,
            occasion=request.form.get('occasion', '') or None,
            season=request.form.get('season', '') or None,
            rating=_parse_rating(rating),
            items=items,
        )
        db.session.add(outfit)
        db.session.commit()
        return redirect(f'/outfits/{outfit.id}')

    return render_template(
        'outfit_form.html',
        outfit=None,
        all_items=all_items,
        selected_ids='',
        selected_ids_list=[],
        occasions=OCCASIONS,
        seasons=SEASONS,
        **ctx,
    )


@outfits_bp.route('/<int:oid>')
@login_required
def outfit_detail(oid):
    ctx = get_ctx()
    me = ctx['me']
    outfit = me.outfits.filter_by(id=oid).first()
    if not outfit:
        flash("Tenue introuvable.", "error")
        return redirect('/outfits')
    return render_template('outfit_detail.html', outfit=outfit, **ctx)


@outfits_bp.route('/<int:oid>/edit', methods=['GET', 'POST'])
@login_required
def outfit_edit(oid):
    ctx = get_ctx()
    me = ctx['me']
    outfit = me.outfits.filter_by(id=oid).first()
    if not outfit:
        flash("Tenue introuvable.", "error")
        return redirect('/outfits')

    all_items = me.items.order_by(ClothingItem.category, ClothingItem.name).all()

    if request.method == 'POST':
        raw = [x.strip() for x in request.form.get('item_ids', '').split(',') if x.strip()]
        items = [me.items.filter_by(id=int(i)).first() for i in raw if i.isdigit()]

        outfit.items = [i for i in items if i]
        rating = request.form.get('rating', '')
        outfit.name = request.form['name'].strip()
        outfit.description = request.form.get('description', '').strip() or None
        outfit.occasion = request.form.get('occasion', '') or None
        outfit.season = request.form.get('season', '') or None
        outfit.rating = _parse_rating(rating)
        db.session.commit()
        return redirect(f'/outfits/{oid}')

    selected = [str(it.id) for it in outfit.items]
    return render_template(
        'outfit_form.html',
        outfit=outfit,
        all_items=all_items,
        selected_ids=','.join(selected),
        selected_ids_list=selected,
        occasions=OCCASIONS,
        seasons=SEASONS,
        **ctx,
    )


@outfits_bp.route('/<int:oid>/delete', methods=['POST'])
@login_required
def outfit_delete(oid):
    me = current_user()
    outfit = me.outfits.filter_by(id=oid).first()
    if outfit:
        if outfit.generated_image:
            path = os.path.join(BASE_DIR, 'static', outfit.generated_image)
            if os.path.isfile(path):
                os.remove(path)
        db.session.delete(outfit)
        db.session.commit()
    return redirect('/outfits')


@outfits_bp.route('/<int:oid>/generate', methods=['POST'])
@login_required
def outfit_generate(oid):
    me = current_user()
    outfit = me.outfits.filter_by(id=oid).first()

    if not outfit:
        return jsonify(error='Tenue introuvable.'), 404
    if not outfit.items:
        return jsonify(error='Ajoutez au moins un vêtement à la tenue avant de générer.'), 400

    data = request.get_json(force=True, silent=True) or {}
    decor = data.get('decor', '').strip() or None
    use_face = data.get('use_face', False)

    anthropic_key = UserSetting.get(me.id, 'anthropic_key', '') or os.environ.get('ANTHROPIC_API_KEY', '')
    pollinations_key = UserSetting.get(me.id, 'pollinations_key', '') or os.environ.get('POLLINATIONS_API_KEY', '')
    image_gen_model = UserSetting.get(me.id, 'image_gen_model', '').strip() or None
    local_sd_url = UserSetting.get(me.id, 'local_sd_url', '').strip() or None
    local_sd_checkpoint = UserSetting.get(me.id, 'local_sd_checkpoint', '').strip() or None

    face_path = None
    if use_face:
        face_rel = f'uploads/faces/{me.id}.jpg'
        candidate = os.path.join(BASE_DIR, 'static', face_rel)
        if os.path.isfile(candidate):
            face_path = candidate

    person_mode = face_path is not None
    gender = (me.gender or 'Homme').strip()

    try:
        prompt, err = generate_prompt_with_claude(outfit, api_key=anthropic_key, person_mode=person_mode, decor=decor, gender=gender)
        if err:
            return jsonify(error=err), 422

        img_path, err2 = generate_image(
            prompt, api_key=pollinations_key, outfit=outfit,
            image_model=image_gen_model,
            local_url=local_sd_url, local_checkpoint=local_sd_checkpoint,
            face_path=face_path, person_mode=person_mode,
            public_base_url=request.host_url.rstrip('/'),
            gender=gender,
        )
        if err2:
            return jsonify(error=err2), 422
    except Exception as exc:
        import traceback
        from flask import current_app
        current_app.logger.error(f'outfit_generate exception: {exc}\n{traceback.format_exc()}')
        return jsonify(error=f'Erreur interne : {exc}'), 500

    if outfit.generated_image:
        old = os.path.join(BASE_DIR, 'static', outfit.generated_image)
        if os.path.isfile(old):
            os.remove(old)

    outfit.generated_image = img_path
    outfit.ai_prompt = prompt
    db.session.commit()
    return jsonify(image_path=img_path, prompt=prompt)


@outfits_bp.route('/gen-face', methods=['GET'])
@login_required
def gen_face_status():
    me = current_user()
    face_rel = f'uploads/faces/{me.id}.jpg'
    exists = os.path.isfile(os.path.join(BASE_DIR, 'static', face_rel))
    return jsonify(has_face=exists, url=f'/static/{face_rel}' if exists else None)


@outfits_bp.route('/gen-face', methods=['POST'])
@login_required
def gen_face_upload():
    me = current_user()
    f = request.files.get('face')
    if not f:
        return jsonify(error='Aucun fichier.'), 400
    if not allowed(f.filename, f.stream):
        return jsonify(error='Format non supporté (JPEG, PNG, WebP).'), 400

    face_dir = os.path.join(UPLOAD_FOLDER, 'faces')
    os.makedirs(face_dir, exist_ok=True)
    dest = os.path.join(face_dir, f'{me.id}.jpg')

    f.stream.seek(0)
    img = Image.open(f.stream).convert('RGB')
    img.thumbnail((1024, 1024), Image.LANCZOS)
    img.save(dest, 'JPEG', quality=90, optimize=True)

    return jsonify(ok=True, url=f'/static/uploads/faces/{me.id}.jpg')


@outfits_bp.route('/gen-face', methods=['DELETE'])
@login_required
def gen_face_delete():
    me = current_user()
    dest = os.path.join(UPLOAD_FOLDER, 'faces', f'{me.id}.jpg')
    if os.path.isfile(dest):
        os.remove(dest)
    return jsonify(ok=True)


@outfits_bp.route('/<int:oid>/upload-photo', methods=['POST'])
@login_required
def outfit_upload_photo(oid):
    me = current_user()
    outfit = me.outfits.filter_by(id=oid).first()
    if not outfit:
        return jsonify(error='Tenue introuvable.'), 404

    f = request.files.get('photo')
    if not f or not f.filename:
        return jsonify(error='Aucun fichier envoyé.'), 400
    if not allowed(f.filename, f.stream):
        return jsonify(error='Format non supporté. Utilisez JPEG, PNG ou WebP.'), 400

    if outfit.user_photo:
        old = os.path.join(BASE_DIR, 'static', outfit.user_photo)
        if os.path.isfile(old):
            os.remove(old)

    img = ImageOps.exif_transpose(Image.open(f.stream)).convert('RGB')
    os.makedirs(OUTFIT_FOLDER, exist_ok=True)
    filename = f'user_{uuid.uuid4().hex}.jpg'
    img.save(os.path.join(OUTFIT_FOLDER, filename), 'JPEG', quality=90, optimize=True)

    rel_path = f'uploads/outfits/{filename}'
    outfit.user_photo = rel_path
    db.session.commit()
    return jsonify(photo_path=rel_path)


@outfits_bp.route('/<int:oid>/analyze-style', methods=['POST'])
@login_required
def outfit_analyze_style(oid):
    me = current_user()
    outfit = me.outfits.filter_by(id=oid).first()
    if not outfit:
        return jsonify(error='Tenue introuvable.'), 404

    # Priorité : photo perso > image générée
    img_rel = outfit.user_photo or outfit.generated_image
    if not img_rel:
        return jsonify(error='Aucune image disponible. Uploadez une photo ou générez une image IA d\'abord.'), 400

    abs_path = os.path.join(BASE_DIR, 'static', img_rel)
    if not os.path.isfile(abs_path):
        return jsonify(error='Fichier image introuvable.'), 400

    try:
        from io import BytesIO
        buf = BytesIO()
        Image.open(abs_path).convert('RGB').save(buf, 'JPEG', quality=85)
        image_b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
    except Exception as exc:
        return jsonify(error=f'Impossible de lire l\'image : {exc}'), 500

    from routes.style_check import analyze_outfit_image
    result, err = analyze_outfit_image(image_b64, 'image/jpeg')
    if err:
        status = 429 if ('429' in err or 'Quota' in err) else 500
        return jsonify(error=err), status

    outfit.style_analysis = json.dumps(result, ensure_ascii=False)
    db.session.commit()
    return jsonify(result)


@outfits_bp.route('/<int:oid>/delete-photo', methods=['POST'])
@login_required
def outfit_delete_photo(oid):
    me = current_user()
    outfit = me.outfits.filter_by(id=oid).first()
    if not outfit:
        return jsonify(error='Tenue introuvable.'), 404

    if outfit.user_photo:
        path = os.path.join(BASE_DIR, 'static', outfit.user_photo)
        if os.path.isfile(path):
            os.remove(path)
        outfit.user_photo = None
        db.session.commit()
    return jsonify(ok=True)
