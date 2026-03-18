"""
Wardrobe v5 — app.py
Lancement : python app.py
Réseau    : python app.py --host
"""
from dotenv import load_dotenv
load_dotenv()

import logging
import os
import socket
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler

from flask import Flask, flash, redirect, request, session

from config import BASE_DIR, Config, OUTFIT_FOLDER, THUMB_FOLDER, UPLOAD_FOLDER
from extensions import cache, csrf, db, limiter
from models import UserSetting
from routes import register_blueprints


def _configure_logging(app):
    level = logging.DEBUG if app.debug else logging.INFO
    formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s %(name)s — %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )
    console = logging.StreamHandler()
    console.setLevel(level)
    console.setFormatter(formatter)
    app.logger.addHandler(console)

    log_dir = os.environ.get('LOG_DIR')
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
        fh = RotatingFileHandler(
            os.path.join(log_dir, 'wardrobe.log'),
            maxBytes=5_000_000,
            backupCount=3,
        )
        fh.setLevel(logging.WARNING)
        fh.setFormatter(formatter)
        app.logger.addHandler(fh)

    app.logger.setLevel(level)


def _get_global_weather():
    uid = session.get("user_id")
    if not uid:
        return None
    city = UserSetting.get(uid, "city", "")
    if not city:
        return None
    from utils.weather import WeatherService
    return WeatherService.get_current(city)


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    cache.init_app(app)

    register_blueprints(app)

    _configure_logging(app)

    for directory in (UPLOAD_FOLDER, THUMB_FOLDER, OUTFIT_FOLDER):
        os.makedirs(directory, exist_ok=True)

    with app.app_context():
        from models import ClothingItem, Outfit, Tag, User, UserSetting  # noqa: F401
        db.create_all()

    # ── Error handlers ─────────────────────────────────────────────────────────
    from flask_wtf.csrf import CSRFError
    from utils.auth import get_ctx

    @app.errorhandler(CSRFError)
    def csrf_error(e):
        app.logger.warning(f"CSRF error: {e}")
        flash('Requête invalide (token expiré). Veuillez réessayer.', 'error')
        return redirect(request.referrer or '/'), 400

    @app.errorhandler(404)
    def not_found(e):
        app.logger.warning(f"404 — {request.path}")
        try:
            ctx = get_ctx()
        except Exception:
            ctx = {}
        from flask import render_template
        return render_template('errors/404.html', **ctx), 404

    @app.errorhandler(500)
    def server_error(e):
        app.logger.error(f"500 — {e}", exc_info=True)
        from flask import render_template
        return render_template('errors/500.html'), 500

    @app.errorhandler(429)
    def too_many_requests(e):
        from flask import render_template
        return render_template('errors/429.html'), 429

    # ── Context processor ──────────────────────────────────────────────────────
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
