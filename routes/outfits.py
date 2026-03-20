import os

from flask import Blueprint, jsonify, redirect, render_template, request

from config import BASE_DIR, OCCASIONS, SEASONS
from extensions import db
from models import ClothingItem, Outfit, UserSetting
from utils.ai import generate_image, generate_prompt_with_claude
from utils.auth import current_user, get_ctx, login_required

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

    anthropic_key = UserSetting.get(me.id, 'anthropic_key', '') or os.environ.get('ANTHROPIC_API_KEY', '')
    pollinations_key = UserSetting.get(me.id, 'pollinations_key', '') or os.environ.get('POLLINATIONS_API_KEY', '')
    image_gen_model = UserSetting.get(me.id, 'image_gen_model', '').strip() or None
    local_sd_url = UserSetting.get(me.id, 'local_sd_url', '').strip() or None
    local_sd_checkpoint = UserSetting.get(me.id, 'local_sd_checkpoint', '').strip() or None

    prompt, err = generate_prompt_with_claude(outfit, api_key=anthropic_key)
    if err:
        return jsonify(error=err), 500

    img_path, err2 = generate_image(
        prompt, api_key=pollinations_key, outfit=outfit,
        image_model=image_gen_model,
        local_url=local_sd_url, local_checkpoint=local_sd_checkpoint,
    )
    if err2:
        return jsonify(error=err2), 500

    if outfit.generated_image:
        old = os.path.join(BASE_DIR, 'static', outfit.generated_image)
        if os.path.isfile(old):
            os.remove(old)

    outfit.generated_image = img_path
    outfit.ai_prompt = prompt
    db.session.commit()
    return jsonify(image_path=img_path, prompt=prompt)
