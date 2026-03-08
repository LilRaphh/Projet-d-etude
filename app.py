"""
Wardrobe v5 — app.py
Lancement : python app.py
Réseau    : python app.py --host
"""
import os
import socket
import sys
from datetime import datetime

import requests
from flask import Flask, session

from config import BASE_DIR, Config, OUTFIT_FOLDER, THUMB_FOLDER, UPLOAD_FOLDER
from extensions import db
from models import UserSetting
from routes import register_blueprints


def _get_global_weather():
    uid = session.get("user_id")
    if not uid:
        return None

    city = UserSetting.get(uid, "city", "")
    if not city:
        return None

    try:
        geo = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={
                "name": city,
                "count": 1,
                "language": "fr",
                "format": "json",
            },
            timeout=4,
        ).json()

        if not geo.get("results"):
            return None

        result = geo["results"][0]

        weather_data = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": result["latitude"],
                "longitude": result["longitude"],
                "current": "temperature_2m,weather_code",
                "timezone": "auto",
            },
            timeout=4,
        ).json()

        current = weather_data.get("current", {})
        temp = round(current.get("temperature_2m", 0))
        code = current.get("weather_code", 0)

        if code == 0:
            icon = "☀️"
            label = "Ciel dégagé"
        elif code <= 2:
            icon = "🌤️"
            label = "Peu nuageux"
        elif code <= 3:
            icon = "☁️"
            label = "Couvert"
        elif code <= 48:
            icon = "🌫️"
            label = "Brouillard"
        elif code <= 67:
            icon = "🌧️"
            label = "Pluie"
        elif code <= 77:
            icon = "❄️"
            label = "Neige"
        elif code <= 82:
            icon = "🌦️"
            label = "Averses"
        else:
            icon = "⛈️"
            label = "Orage"

        return {
            "city": result["name"],
            "temp": temp,
            "icon": icon,
            "label": label,
        }

    except Exception:
        return None


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    register_blueprints(app)

    for directory in (UPLOAD_FOLDER, THUMB_FOLDER, OUTFIT_FOLDER):
        os.makedirs(directory, exist_ok=True)

    with app.app_context():
        from models import ClothingItem, Outfit, Tag, User, UserSetting  # noqa: F401
        db.create_all()

    @app.context_processor
    def inject_global_ui():
        return {
            "global_weather": _get_global_weather(),
            "current_year": datetime.now().year,
        }

    return app


app = create_app()


if __name__ == '__main__':
    if '--reset-db' in sys.argv:
        with app.app_context():
            db.drop_all()
            db.create_all()
        print('Base réinitialisée.')
        sys.exit(0)

    host = '0.0.0.0' if '--host' in sys.argv else '127.0.0.1'
    port = int(os.environ.get('PORT', 5000))
    debug = '--debug' in sys.argv

    if host == '0.0.0.0':
        try:
            ip = socket.gethostbyname(socket.gethostname())
        except Exception:
            ip = 'votre-IP-locale'
        print(f'\n  Wardrobe v5\n  Local  → http://localhost:{port}\n  Réseau → http://{ip}:{port}\n')
    else:
        print(f'\n  Wardrobe v5  →  http://localhost:{port}\n')

    app.run(host=host, port=port, debug=debug, threaded=True)