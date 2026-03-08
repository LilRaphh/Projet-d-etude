"""
Wardrobe v5 — app.py
Lancement : python app.py
Réseau    : python app.py --host
"""
import os
import socket
import sys

from flask import Flask

from config import BASE_DIR, Config, OUTFIT_FOLDER, THUMB_FOLDER, UPLOAD_FOLDER
from extensions import db
from routes import register_blueprints


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
