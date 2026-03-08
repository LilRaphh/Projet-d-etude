import os

from flask import Blueprint, jsonify, redirect, render_template, request

from config import BASE_DIR, OCCASIONS, SEASONS
from extensions import db
from models import ClothingItem, Outfit, UserSetting
from utils.ai import generate_image, generate_prompt_with_claude
from utils.auth import current_user, get_ctx, login_required

outfits_bp = Blueprint('outfits', __name__, url_prefix='/outfits')


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
            rating=int(rating) if rating else None,
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
        return redirect('/outfits')
    return render_template('outfit_detail.html', outfit=outfit, **ctx)


@outfits_bp.route('/<int:oid>/edit', methods=['GET', 'POST'])
@login_required
def outfit_edit(oid):
    ctx = get_ctx()
    me = ctx['me']
    outfit = me.outfits.filter_by(id=oid).first()
    if not outfit:
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
        outfit.rating = int(rating) if rating else None
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

    stored_anthropic_key = UserSetting.get(me.id, 'anthropic_key', '')
    if stored_anthropic_key and not os.environ.get('ANTHROPIC_API_KEY'):
        os.environ['ANTHROPIC_API_KEY'] = stored_anthropic_key

    stored_pollinations_key = UserSetting.get(me.id, 'pollinations_key', '')
    if stored_pollinations_key and not os.environ.get('POLLINATIONS_API_KEY'):
        os.environ['POLLINATIONS_API_KEY'] = stored_pollinations_key

    prompt, err = generate_prompt_with_claude(outfit)
    if err:
        return jsonify(error=err), 500

    img_path, err2 = generate_image(prompt)
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
