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
        total=me.items.count(),
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
            price=float(price_raw) if price_raw else None,
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
        item.price = float(price_raw) if price_raw else None
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
    for key in ('app_name', 'accent', 'currency', 'anthropic_key', 'pollinations_key', 'city'):
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


@main_bp.route('/mentions-legales')
def mentions_legales():
    return render_template('mentions_legales.html', **get_ctx())


@main_bp.route('/confidentialite')
def confidentialite():
    return render_template('confidentialite.html', **get_ctx())


@main_bp.route('/contact')
def contact():
    return render_template('contact.html', **get_ctx())