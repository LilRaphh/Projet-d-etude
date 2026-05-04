from flask import Blueprint, flash, redirect, render_template, request
from sqlalchemy import distinct

from config import CATEGORIES, COLORS, CONDITIONS, ITEMS_PER_PAGE, SEASONS, SIZES
from extensions import db
from models import ClothingItem
from utils.auth import current_user, get_ctx, login_required
from utils.images import delete_images, save_image
from utils.tags import get_tags
from utils.weather import WeatherService

main_bp = Blueprint('main', __name__)


def _parse_price(raw: str):
    """Parse un prix utilisateur. Accepte virgule ou point. Retourne None si invalide."""
    if not raw:
        return None
    try:
        return float(raw.replace(',', '.'))
    except ValueError:
        return None


@main_bp.route('/')
def index():
    ctx = get_ctx()
    me = ctx['me']

    if not me:
        return render_template(
            'index.html',
            items=[],
            total=0,
            brands=[],
            cats=CATEGORIES,
            colors=COLORS,
            seasons=SEASONS,
            af=dict(search='', category='', color='', season='', brand='', fav=False, sort='newest'),
            **ctx,
        )

    q = me.items
    af = dict(
        search=request.args.get('search', '').strip(),
        category=request.args.get('category', ''),
        color=request.args.get('color', ''),
        season=request.args.get('season', ''),
        brand=request.args.get('brand', ''),
        fav=request.args.get('fav', '') == '1',
        sort=request.args.get('sort', 'newest'),
    )

    if af['search']:
        like = f"%{af['search']}%"
        q = q.filter(db.or_(ClothingItem.name.ilike(like), ClothingItem.brand.ilike(like), ClothingItem.notes.ilike(like)))
    if af['category']:
        q = q.filter_by(category=af['category'])
    if af['color']:
        q = q.filter_by(color=af['color'])
    if af['season']:
        q = q.filter_by(season=af['season'])
    if af['brand']:
        q = q.filter(ClothingItem.brand.ilike(f"%{af['brand']}%"))
    if af['fav']:
        q = q.filter_by(is_favorite=True)

    sort_map = {
        'newest': ClothingItem.created_at.desc(),
        'oldest': ClothingItem.created_at.asc(),
        'az': ClothingItem.name.asc(),
        'za': ClothingItem.name.desc(),
        'worn': ClothingItem.times_worn.desc(),
    }

    page = request.args.get('page', 1, type=int)
    pagination = q.order_by(sort_map.get(af['sort'], ClothingItem.created_at.desc())).paginate(
        page=page, per_page=ITEMS_PER_PAGE, error_out=False
    )

    # Requêtes distinct pour éviter le N+1 (ne charge pas tous les items)
    brands = sorted([
        row[0] for row in
        db.session.query(distinct(ClothingItem.brand))
                  .filter(ClothingItem.user_id == me.id, ClothingItem.brand.isnot(None))
                  .order_by(ClothingItem.brand)
                  .all()
    ])

    return render_template(
        'index.html',
        items=pagination.items,
        pagination=pagination,
        brands=brands,
        total=pagination.total,
        cats=CATEGORIES,
        colors=COLORS,
        seasons=SEASONS,
        af=af,
        **ctx,
    )


@main_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    ctx = get_ctx()
    me = ctx['me']

    if request.method == 'POST':
        img, th = save_image(request.files.get('image'))
        price_raw = request.form.get('price', '').strip()

        item = ClothingItem(
            user_id=me.id,
            name=request.form['name'].strip(),
            category=request.form['category'],
            brand=request.form.get('brand', '').strip() or None,
            size=request.form.get('size', '') or None,
            color=request.form.get('color', '') or None,
            season=request.form.get('season', '') or None,
            condition=request.form.get('condition', '') or None,
            price=_parse_price(price_raw),
            notes=request.form.get('notes', '').strip() or None,
            is_favorite=bool(request.form.get('is_favorite')),
            image_path=img,
            thumb_path=th,
            tags=get_tags(request.form.get('tags', '')),
        )
        db.session.add(item)
        db.session.commit()
        flash('Vêtement ajouté !', 'success')
        return redirect('/')

    return render_template(
        'item_form.html',
        item=None,
        back='/',
        cats=CATEGORIES,
        sizes=SIZES,
        colors=COLORS,
        seasons=SEASONS,
        conds=CONDITIONS,
        etags='',
        **ctx,
    )


@main_bp.route('/edit/<int:iid>', methods=['GET', 'POST'])
@login_required
def edit(iid):
    ctx = get_ctx()
    me = ctx['me']
    item = me.items.filter_by(id=iid).first()

    if not item:
        flash("Vêtement introuvable.", "error")
        return redirect('/')

    if request.method == 'POST':
        file_obj = request.files.get('image')
        if file_obj and file_obj.filename:
            delete_images(item)
            item.image_path, item.thumb_path = save_image(file_obj)

        price_raw = request.form.get('price', '').strip()
        item.name = request.form['name'].strip()
        item.category = request.form['category']
        item.brand = request.form.get('brand', '').strip() or None
        item.size = request.form.get('size', '') or None
        item.color = request.form.get('color', '') or None
        item.season = request.form.get('season', '') or None
        item.condition = request.form.get('condition', '') or None
        parsed_price = _parse_price(price_raw)
        if price_raw and parsed_price is None:
            flash("Prix invalide, il a été ignoré.", "warning")
        item.price = parsed_price
        item.notes = request.form.get('notes', '').strip() or None
        item.is_favorite = bool(request.form.get('is_favorite'))
        item.tags = get_tags(request.form.get('tags', ''))

        db.session.commit()
        flash('Vêtement mis à jour !', 'success')
        return redirect(f'/item/{iid}')

    return render_template(
        'item_form.html',
        item=item,
        back=f'/item/{iid}',
        cats=CATEGORIES,
        sizes=SIZES,
        colors=COLORS,
        seasons=SEASONS,
        conds=CONDITIONS,
        etags=', '.join(t.name for t in item.tags),
        **ctx,
    )


@main_bp.route('/item/<int:iid>')
@login_required
def detail(iid):
    ctx = get_ctx()
    me = ctx['me']
    item = me.items.filter_by(id=iid).first()
    if not item:
        flash("Vêtement introuvable.", "error")
        return redirect('/')
    return render_template('item_detail.html', item=item, **ctx)


@main_bp.route('/delete/<int:iid>', methods=['POST'])
@login_required
def delete(iid):
    me = current_user()
    item = me.items.filter_by(id=iid).first()
    if item:
        delete_images(item)
        db.session.delete(item)
        db.session.commit()
        flash('Supprimé.', 'info')
    return redirect('/')


@main_bp.route('/settings', methods=['POST'])
@login_required
def save_settings():
    from models import UserSetting

    me = current_user()
    for key in ('app_name', 'accent', 'currency', 'city'):
        value = request.form.get(key, '').strip()
        if value:
            UserSetting.set(me.id, key, value)
        else:
            UserSetting.delete(me.id, key)
    for key in ('anthropic_key', 'pollinations_key'):
        value = request.form.get(key, '').strip()
        if value:
            UserSetting.set(me.id, key, value)
    flash('Paramètres sauvegardés !', 'success')
    return redirect(request.referrer or '/')


@main_bp.route('/forecast')
@login_required
def forecast():
    from models import UserSetting

    ctx = get_ctx()
    me = ctx['me']
    city = UserSetting.get(me.id, "city", "").strip()

    if not city:
        flash("Ajoutez d'abord une ville dans les paramètres pour afficher les prévisions.", "info")
        return redirect(request.referrer or '/')

    forecast_data, error = WeatherService.get_forecast(city)
    return render_template(
        'forecast.html',
        forecast=forecast_data,
        forecast_error=error,
        city=city,
        **ctx,
    )


@main_bp.route('/settings/ai', methods=['GET'])
@login_required
def settings_ai_get():
    from models import UserSetting
    from ai.vision import check_ollama

    ctx = get_ctx()
    me = ctx['me']
    ollama_info = check_ollama()
    current_settings = {
        'vision_model': UserSetting.get(me.id, 'vision_model', ''),
        'image_gen_model': UserSetting.get(me.id, 'image_gen_model', ''),
        'pollinations_key': UserSetting.get(me.id, 'pollinations_key', ''),
        'anthropic_key': UserSetting.get(me.id, 'anthropic_key', ''),
        'local_sd_url': UserSetting.get(me.id, 'local_sd_url', ''),
        'local_sd_checkpoint': UserSetting.get(me.id, 'local_sd_checkpoint', ''),
    }
    return render_template(
        'settings_ai.html',
        ollama_info=ollama_info,
        current_settings=current_settings,
        **ctx,
    )


@main_bp.route('/settings/ai', methods=['POST'])
@login_required
def settings_ai_post():
    from models import UserSetting

    me = current_user()
    for key in ('vision_model', 'image_gen_model', 'local_sd_url', 'local_sd_checkpoint'):
        value = request.form.get(key, '').strip()
        if value:
            UserSetting.set(me.id, key, value)
        else:
            UserSetting.delete(me.id, key)
    # Clés API : on ne sauvegarde que si non vide pour ne pas écraser une clé existante
    for key in ('pollinations_key', 'anthropic_key'):
        value = request.form.get(key, '').strip()
        if value:
            UserSetting.set(me.id, key, value)
    flash('Paramètres IA sauvegardés !', 'success')
    return redirect('/settings/ai')


@main_bp.route('/add-bulk', methods=['GET'])
@login_required
def add_bulk():
    ctx = get_ctx()
    return render_template(
        'add_bulk.html',
        cats=CATEGORIES,
        colors=COLORS,
        seasons=SEASONS,
        **ctx,
    )


@main_bp.route('/api/add-bulk', methods=['POST'])
@login_required
def add_bulk_post():
    from flask import jsonify
    me = current_user()

    count = request.form.get('count', '0')
    try:
        count = int(count)
    except ValueError:
        return jsonify({'error': 'Paramètre count invalide'}), 400

    if count < 1 or count > 40:
        return jsonify({'error': 'Entre 1 et 40 vêtements par import'}), 400

    created = []
    errors = []

    for i in range(count):
        name = request.form.get(f'name_{i}', '').strip()
        if not name:
            errors.append({'index': i, 'error': 'Nom requis'})
            continue

        category = request.form.get(f'category_{i}', '') or CATEGORIES[0]
        color = request.form.get(f'color_{i}', '') or None
        season = request.form.get(f'season_{i}', '') or None
        brand = request.form.get(f'brand_{i}', '').strip() or None

        img, th = save_image(request.files.get(f'image_{i}'))

        item = ClothingItem(
            user_id=me.id,
            name=name,
            category=category,
            brand=brand,
            color=color,
            season=season,
            image_path=img,
            thumb_path=th,
        )
        db.session.add(item)
        db.session.flush()  # get item.id before commit
        created.append({'id': item.id, 'name': name, 'has_image': bool(img)})

    db.session.commit()
    return jsonify({'created': created, 'errors': errors})


@main_bp.route('/mentions-legales')
def mentions_legales():
    return render_template('mentions_legales.html', **get_ctx())


@main_bp.route('/confidentialite')
def confidentialite():
    return render_template('confidentialite.html', **get_ctx())


@main_bp.route('/contact')
def contact():
    return render_template('contact.html', **get_ctx())
