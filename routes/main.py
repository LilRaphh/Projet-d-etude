from flask import Blueprint, flash, redirect, render_template, request
import requests

from config import CATEGORIES, COLORS, CONDITIONS, SEASONS, SIZES
from extensions import db
from models import ClothingItem
from utils.auth import current_user, get_ctx, login_required
from utils.images import delete_images, save_image
from utils.tags import get_tags

main_bp = Blueprint('main', __name__)

WMO = {
    0: "Ciel dégagé",
    1: "Principalement dégagé",
    2: "Partiellement nuageux",
    3: "Couvert",
    45: "Brouillard",
    48: "Brouillard givrant",
    51: "Bruine légère",
    53: "Bruine modérée",
    55: "Bruine forte",
    61: "Pluie légère",
    63: "Pluie modérée",
    65: "Pluie forte",
    71: "Neige légère",
    73: "Neige modérée",
    75: "Neige forte",
    80: "Averses légères",
    81: "Averses modérées",
    82: "Averses violentes",
    95: "Orage",
    96: "Orage avec grêle",
    99: "Orage violent",
}


def weather_icon(code):
    if code == 0:
        return "☀️"
    if code <= 2:
        return "🌤️"
    if code <= 3:
        return "☁️"
    if code <= 48:
        return "🌫️"
    if code <= 67:
        return "🌧️"
    if code <= 77:
        return "❄️"
    if code <= 82:
        return "🌦️"
    return "⛈️"


def get_forecast(city):
    try:
        geo = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 1, "language": "fr", "format": "json"},
            timeout=6,
        ).json()

        if not geo.get("results"):
            return None, "Ville introuvable."

        place = geo["results"][0]

        data = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": place["latitude"],
                "longitude": place["longitude"],
                "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m,relative_humidity_2m",
                "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,precipitation_sum,wind_speed_10m_max",
                "hourly": "temperature_2m,weather_code,precipitation_probability,wind_speed_10m",
                "forecast_days": 7,
                "timezone": "auto",
            },
            timeout=6,
        ).json()

        current = data.get("current", {})
        daily = data.get("daily", {})
        hourly = data.get("hourly", {})

        current_view = {
            "city": place["name"],
            "temp": round(current.get("temperature_2m", 0)),
            "feels": round(current.get("apparent_temperature", 0)),
            "wind": round(current.get("wind_speed_10m", 0)),
            "hum": round(current.get("relative_humidity_2m", 0)),
            "code": current.get("weather_code", 0),
            "label": WMO.get(current.get("weather_code", 0), "Variable"),
            "icon": weather_icon(current.get("weather_code", 0)),
        }

        days = []
        dates = daily.get("time", [])
        codes = daily.get("weather_code", [])
        tmax = daily.get("temperature_2m_max", [])
        tmin = daily.get("temperature_2m_min", [])
        rain_prob = daily.get("precipitation_probability_max", [])
        rain_sum = daily.get("precipitation_sum", [])
        wind_max = daily.get("wind_speed_10m_max", [])

        for i in range(len(dates)):
            code = codes[i]
            days.append({
                "date": dates[i],
                "code": code,
                "label": WMO.get(code, "Variable"),
                "icon": weather_icon(code),
                "temp_max": round(tmax[i]) if tmax[i] is not None else None,
                "temp_min": round(tmin[i]) if tmin[i] is not None else None,
                "rain_prob": rain_prob[i],
                "rain_sum": rain_sum[i],
                "wind_max": round(wind_max[i]) if wind_max[i] is not None else None,
            })

        hours = []
        hourly_times = hourly.get("time", [])
        hourly_temp = hourly.get("temperature_2m", [])
        hourly_code = hourly.get("weather_code", [])
        hourly_rain = hourly.get("precipitation_probability", [])
        hourly_wind = hourly.get("wind_speed_10m", [])

        limit = min(24, len(hourly_times))
        for i in range(limit):
            code = hourly_code[i]
            hours.append({
                "time": hourly_times[i],
                "temp": round(hourly_temp[i]) if hourly_temp[i] is not None else None,
                "code": code,
                "label": WMO.get(code, "Variable"),
                "icon": weather_icon(code),
                "rain_prob": hourly_rain[i],
                "wind": round(hourly_wind[i]) if hourly_wind[i] is not None else None,
            })

        return {
            "place": {
                "name": place.get("name"),
                "latitude": place.get("latitude"),
                "longitude": place.get("longitude"),
                "country": place.get("country"),
                "admin1": place.get("admin1"),
            },
            "current": current_view,
            "days": days,
            "hours": hours,
        }, None

    except Exception:
        return None, "Impossible de récupérer les prévisions météo pour le moment."


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

    items = q.order_by(sort_map.get(af['sort'], ClothingItem.created_at.desc())).all()
    brands = sorted({it.brand for it in me.items if it.brand})

    return render_template(
        'index.html',
        items=items,
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

    forecast_data, error = get_forecast(city)
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