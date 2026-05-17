"""
Routes pour le calendrier de garde-robe.
Permet de planifier les vêtements/tenues par jour avec météo intégrée.
"""
import calendar
from datetime import date, datetime, timedelta

from flask import Blueprint, jsonify, render_template, request, session

from extensions import db, limiter
from models import ClothingItem, Outfit, UserSetting
from utils.auth import login_required

bp = Blueprint('calendar', __name__, url_prefix='/calendar')


@bp.route('/')
@login_required
def index():
    """Affiche le calendrier du mois/semaine en cours ou demandé."""
    uid = session['user_id']
    
    # Paramètres de navigation
    view_mode = request.args.get('view', 'month')  # 'month' ou 'week'
    
    try:
        year = int(request.args.get('year', datetime.now().year))
        month = int(request.args.get('month', datetime.now().month))
        week = int(request.args.get('week', datetime.now().isocalendar()[1]))
    except (ValueError, TypeError):
        year = datetime.now().year
        month = datetime.now().month
        week = datetime.now().isocalendar()[1]

    # Validation
    if not (1 <= month <= 12):
        month = datetime.now().month
    if year < 1900 or year > 2100:
        year = datetime.now().year

    # Génération du calendrier selon le mode
    if view_mode == 'week':
        # Vue semaine : du lundi au dimanche
        jan_first = date(year, 1, 1)
        week_start = jan_first + timedelta(weeks=week-1)
        # Ajuster au lundi de la semaine
        week_start = week_start - timedelta(days=week_start.weekday())
        week_end = week_start + timedelta(days=6)
        
        cal_data = {
            'mode': 'week',
            'week_number': week,
            'week_start': week_start,
            'week_end': week_end,
            'days': [(week_start + timedelta(days=i)) for i in range(7)]
        }
        
        # Navigation semaine
        prev_week = week - 1 if week > 1 else 52
        prev_year = year if week > 1 else year - 1
        next_week = week + 1 if week < 52 else 1
        next_year = year if week < 52 else year + 1
        
    else:
        # Vue mois (existante)
        cal = calendar.monthcalendar(year, month)
        month_name = calendar.month_name[month]
        
        cal_data = {
            'mode': 'month',
            'cal': cal,
            'month': month,
            'month_name': month_name,
        }
        
        # Navigation mois
        if month == 1:
            prev_month, prev_year = 12, year - 1
        else:
            prev_month, prev_year = month - 1, year
        if month == 12:
            next_month, next_year = 1, year + 1
        else:
            next_month, next_year = month + 1, year

    # Récupération de la météo
    city = UserSetting.get(uid, 'city', '')
    weather_data = {}
    
    if city:
        try:
            from utils.weather import WeatherService
            forecast = WeatherService.get_forecast(city)
            
            if forecast and isinstance(forecast, tuple) and forecast[0]:
                data = forecast[0]
                days = data.get('days', [])
                
                for day in days:
                    if day and isinstance(day, dict):
                        date_key = day.get('date', '')
                        if date_key:
                            weather_data[date_key] = {
                                'icon': day.get('icon', '☀️'),
                                'temp_max': day.get('temp_max'),
                                'temp_min': day.get('temp_min'),
                            }
        except Exception:
            pass

    # Récupération des entrées selon le mode
    from models import CalendarEntry
    
    if view_mode == 'week':
        first_day = week_start
        last_day = week_end + timedelta(days=1)
    else:
        first_day = date(year, month, 1)
        if month == 12:
            last_day = date(year + 1, 1, 1)
        else:
            last_day = date(year, month + 1, 1)
    
    entries_query = CalendarEntry.query.filter(
        CalendarEntry.user_id == uid,
        CalendarEntry.date >= first_day,
        CalendarEntry.date < last_day
    ).all()

    # Grouper par date
    entries_by_date = {}
    for entry in entries_query:
        date_str = entry.date.strftime('%Y-%m-%d')
        if date_str not in entries_by_date:
            entries_by_date[date_str] = []
        
        # Préparer les données d'entrée
        entry_data = {
            'id': entry.id,
            'item_name': entry.item_name,
            'outfit_name': entry.outfit_name,
            'item_thumb': entry.item_thumb,
            'is_outfit': entry.outfit_id is not None,
            'outfit_items': entry.outfit_items if entry.outfit_id else []
        }
        entries_by_date[date_str].append(entry_data)

    # Contexte utilisateur
    from utils.auth import get_ctx
    ctx = get_ctx()

    # Données de navigation selon le mode
    if view_mode == 'week':
        nav_data = {
            'prev_year': prev_year,
            'prev_week': prev_week,
            'next_year': next_year,
            'next_week': next_week,
        }
    else:
        nav_data = {
            'prev_year': prev_year,
            'prev_month': prev_month,
            'next_year': next_year,
            'next_month': next_month,
        }

    return render_template(
        'calendar.html',
        **ctx,
        **cal_data,
        **nav_data,
        view_mode=view_mode,
        year=year,
        week=week if view_mode == 'week' else None,
        weather=weather_data,
        entries=entries_by_date,
        today=datetime.now().strftime('%Y-%m-%d'),
        city=city,
        datetime=datetime,  # Pour le template
    )


@bp.route('/wardrobe')
@login_required
def get_wardrobe():
    """Endpoint JSON pour récupérer tous les vêtements et tenues de l'utilisateur."""
    uid = session['user_id']
    
    items = ClothingItem.query.filter_by(user_id=uid).all()
    outfits = Outfit.query.filter_by(user_id=uid).all()

    return jsonify({
        'items': [{
            'id': i.id,
            'name': i.name,
            'category': i.category,
            'color': i.color,
            'thumb': i.thumb_path,
        } for i in items],
        'outfits': [{
            'id': o.id,
            'name': o.name,
            'occasion': o.occasion,
            'thumb': None,
        } for o in outfits],
    })


@bp.route('/stats')
@login_required
def get_stats():
    """Retourne les statistiques de port par vêtement."""
    uid = session['user_id']
    from models import CalendarEntry
    
    # Récupérer toutes les entrées de calendrier de l'utilisateur
    entries = CalendarEntry.query.filter_by(user_id=uid).all()
    
    # Compter les ports par vêtement
    wear_count = {}
    for entry in entries:
        for item_id in entry.all_item_ids:
            wear_count[item_id] = wear_count.get(item_id, 0) + 1
    
    return jsonify(wear_count)


@bp.route('/entry', methods=['POST'])
@login_required
@limiter.limit("30 per minute")
def add_entry():
    """Ajoute une entrée au calendrier."""
    uid = session['user_id']
    data = request.get_json()

    if not data or 'date' not in data:
        return jsonify({'error': 'Date manquante'}), 400

    try:
        entry_date = datetime.strptime(data['date'], '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return jsonify({'error': 'Format de date invalide'}), 400

    item_id = data.get('item_id')
    outfit_id = data.get('outfit_id')

    if not item_id and not outfit_id:
        return jsonify({'error': 'Vêtement ou tenue requis'}), 400

    # Vérifier que l'item/outfit appartient bien à l'utilisateur
    if item_id:
        item = ClothingItem.query.filter_by(id=item_id, user_id=uid).first()
        if not item:
            return jsonify({'error': 'Vêtement introuvable'}), 404
    
    if outfit_id:
        outfit = Outfit.query.filter_by(id=outfit_id, user_id=uid).first()
        if not outfit:
            return jsonify({'error': 'Tenue introuvable'}), 404

    from models import CalendarEntry
    
    # Créer l'entrée
    entry = CalendarEntry(
        user_id=uid,
        date=entry_date,
        item_id=item_id,
        outfit_id=outfit_id,
    )
    db.session.add(entry)
    db.session.commit()

    return jsonify({
        'id': entry.id,
        'item_name': entry.item_name,
        'outfit_name': entry.outfit_name,
        'item_thumb': entry.item_thumb,
        'is_outfit': outfit_id is not None,
        'outfit_items': entry.outfit_items,
    }), 201


@bp.route('/entry/<int:entry_id>', methods=['DELETE'])
@login_required
@limiter.limit("30 per minute")
def delete_entry(entry_id):
    """Supprime une entrée du calendrier."""
    uid = session['user_id']
    
    from models import CalendarEntry
    
    entry = CalendarEntry.query.filter_by(id=entry_id, user_id=uid).first()
    if not entry:
        return jsonify({'error': 'Entrée introuvable'}), 404

    db.session.delete(entry)
    db.session.commit()

    return jsonify({'success': True}), 200
