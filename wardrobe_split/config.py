import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
THUMB_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads', 'thumbs')
OUTFIT_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads', 'outfits')
THUMB_SIZE = (500, 500)
ALLOWED_EXT = {'png', 'jpg', 'jpeg', 'webp', 'gif'}

POLLINATIONS_MODEL = os.environ.get('POLLINATIONS_MODEL', 'zimage')
POLLINATIONS_WIDTH = int(os.environ.get('POLLINATIONS_WIDTH', 768))
POLLINATIONS_HEIGHT = int(os.environ.get('POLLINATIONS_HEIGHT', 1152))
POLLINATIONS_ENHANCE = os.environ.get('POLLINATIONS_ENHANCE', 'false').lower() == 'true'
POLLINATIONS_SAFE = os.environ.get('POLLINATIONS_SAFE', 'false').lower() == 'true'
POLLINATIONS_FIXED_SEED = os.environ.get('POLLINATIONS_FIXED_SEED', '').strip()

CATEGORIES = [
    'Hauts', 'T-shirts', 'Pulls & Sweats', 'Vestes & Manteaux',
    'Pantalons', 'Jeans', 'Shorts', 'Robes & Jupes',
    'Chaussures', 'Accessoires', 'Sous-vêtements', 'Sport', 'Autre'
]
SEASONS = ['Printemps', 'Été', 'Automne', 'Hiver', 'Toutes saisons']
SIZES = [
    'XXS', 'XS', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL',
    '34', '36', '38', '40', '42', '44', '46', '48',
    '35', '36', '37', '38', '39', '40', '41', '42', '43', '44', '45', '46',
    'Taille unique'
]
COLORS = [
    'Blanc', 'Noir', 'Gris', 'Beige', 'Marron', 'Camel', 'Rouge', 'Rose',
    'Orange', 'Jaune', 'Vert', 'Bleu', 'Violet', 'Multicolore', 'Imprimé'
]
CONDITIONS = ['Neuf', 'Excellent', 'Bon', 'Correct', 'Usé']
OCCASIONS = ['Quotidien', 'Travail', 'Soirée', 'Sport', 'Voyage', 'Cérémonie', 'Autre']


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'wardrobe-secret-v5')
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{os.path.join(BASE_DIR, 'wardrobe.db')}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAX_CONTENT_LENGTH = 20 * 1024 * 1024
