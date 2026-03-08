from .api import api_bp
from .auth import auth_bp
from .main import main_bp
from .outfits import outfits_bp
from routes.stylist import stylist_bp



def register_blueprints(app):
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(outfits_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(stylist_bp)