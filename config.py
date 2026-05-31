import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
THUMB_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads', 'thumbs')
OUTFIT_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads', 'outfits')
THUMB_SIZE = (500, 500)
ALLOWED_EXT = {'png', 'jpg', 'jpeg', 'webp', 'gif'}

POLLINATIONS_MODEL = os.environ.get('POLLINATIONS_MODEL', 'flux')
POLLINATIONS_WIDTH = int(os.environ.get('POLLINATIONS_WIDTH', 832))
POLLINATIONS_HEIGHT = int(os.environ.get('POLLINATIONS_HEIGHT', 1216))
POLLINATIONS_ENHANCE = os.environ.get('POLLINATIONS_ENHANCE', 'true').lower() == 'true'
POLLINATIONS_SAFE = os.environ.get('POLLINATIONS_SAFE', 'false').lower() == 'true'
POLLINATIONS_FIXED_SEED = os.environ.get('POLLINATIONS_FIXED_SEED', '').strip()

ANTHROPIC_MODEL = os.environ.get('ANTHROPIC_MODEL', 'claude-sonnet-4-5')
ITEMS_PER_PAGE = int(os.environ.get('ITEMS_PER_PAGE', 24))

CATEGORIES = [
    'Hauts', 'T-shirts', 'Pulls & Sweats', 'Vestes & Manteaux',
    'Pantalons', 'Jeans', 'Shorts', 'Robes & Jupes',
    'Chaussures', 'Accessoires', 'Sous-vêtements', 'Sport', 'Autre'
]
SEASONS = ['Printemps', 'Été', 'Automne', 'Hiver', 'Toutes saisons']

def _shoe_sizes():
    sizes = []
    n = 30
    while n <= 50:
        full = int(n)
        sizes.append(str(full) if n == full else f"{full}½")
        n = round(n + 0.5, 1)
    return sizes

_LETTER      = ['XXS', 'XS', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL']
_NUM_GARMENT = ['34', '36', '38', '40', '42', '44', '46', '48', '50', '52', '54', '56']
_NUM_JEANS   = ['26', '27', '28', '29', '30', '31', '32', '33', '34', '36', '38', '40', '42', '44']

SIZES_BY_CATEGORY = {
    'Hauts':             _LETTER + _NUM_GARMENT,
    'T-shirts':          _LETTER,
    'Pulls & Sweats':    _LETTER + _NUM_GARMENT,
    'Vestes & Manteaux': _LETTER + _NUM_GARMENT,
    'Pantalons':         ['XS', 'S', 'M', 'L', 'XL', 'XXL'] + _NUM_GARMENT,
    'Jeans':             ['XS', 'S', 'M', 'L', 'XL', 'XXL'] + _NUM_JEANS,
    'Shorts':            ['XS', 'S', 'M', 'L', 'XL', 'XXL'] + _NUM_GARMENT[:8],
    'Robes & Jupes':     _LETTER + _NUM_GARMENT,
    'Chaussures':        _shoe_sizes(),
    'Accessoires':       ['Taille unique', 'XS/S', 'S/M', 'M/L', 'L/XL'],
    'Sous-vêtements':    _LETTER + _NUM_GARMENT,
    'Sport':             _LETTER,
    'Autre':             _LETTER + _NUM_GARMENT + ['Taille unique'],
}

# Kept for backwards compat (boutique scraper, seed scripts, etc.)
SIZES = _LETTER + _NUM_GARMENT + _shoe_sizes() + ['Taille unique']
COLORS = [
    'Blanc', 'Noir', 'Gris', 'Beige', 'Marron', 'Camel', 'Rouge', 'Rose',
    'Orange', 'Jaune', 'Vert', 'Bleu', 'Violet', 'Multicolore', 'Imprimé'
]
CONDITIONS = ['Neuf', 'Excellent', 'Bon', 'Correct', 'Usé']
OCCASIONS = ['Quotidien', 'Travail', 'Soirée', 'Sport', 'Voyage', 'Cérémonie', 'Autre']

GENDERS = ['Homme', 'Femme']
AESTHETICS = ['Casual', 'Chic', 'Streetwear', 'Sport', 'Bohème', 'Minimaliste', 'Vintage', 'Business', 'Autre']
BUDGETS = ['Économique', 'Moyen', 'Premium', 'Luxe']


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY:
        raise RuntimeError(
            "La variable d'environnement SECRET_KEY est obligatoire.\n"
            "Générez-en une : python -c \"import secrets; print(secrets.token_hex(32))\"\n"
            "Puis ajoutez-la dans un fichier .env ou exportez-la : export SECRET_KEY=<valeur>"
        )
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', f"sqlite:///{os.path.join(BASE_DIR, 'wardrobe.db')}")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAX_CONTENT_LENGTH = 20 * 1024 * 1024
    RATELIMIT_STORAGE_URI = os.environ.get('REDIS_URL', 'memory://')
    CACHE_TYPE = os.environ.get('CACHE_TYPE', 'SimpleCache')
    CACHE_DEFAULT_TIMEOUT = 300
    TEMPLATES_AUTO_RELOAD = True
    from datetime import timedelta
    PERMANENT_SESSION_LIFETIME = timedelta(days=30)  # durée si "se souvenir de moi" coché
