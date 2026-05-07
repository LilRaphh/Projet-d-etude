from .admin import admin_bp
from .ai_recommend import ai_bp
from .api import api_bp
from .auth import auth_bp
from .boutique import boutique_bp
from .complete import complete_bp
from .main import main_bp
from .outfits import outfits_bp
from .profile import profile_bp
from .style_check import style_check_bp
from routes.stylist import stylist_bp


def register_blueprints(app):
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(outfits_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(stylist_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(ai_bp)
    app.register_blueprint(style_check_bp)
    app.register_blueprint(boutique_bp)
    app.register_blueprint(complete_bp)
    app.register_blueprint(admin_bp)