# =============================================================
#  config.py — Configuration centrale SmartWear Scraper
# =============================================================
import os
from dotenv import load_dotenv

# ==========================
#  Clé API Gemini
# ==========================
load_dotenv()
GOOGLE_GEMINI_API_KEY = os.getenv("GOOGLE_GEMINI_API_KEY")
GEMINI_MODEL_NAME    = "gemini-2.0-flash"

# ==========================
#  Dossier de sortie
#  En Docker, on monte un volume sur /app/output
# ==========================
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")

# ==========================
#  Headers HTTP communs
# ==========================
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9",
}

# ==========================
#  Valeurs autorisées — schéma cible
# ==========================

GENRE_VALUES   = ["Enfant", "Adolescent", "Adulte"]

SEXE_VALUES    = ["Femme", "Homme", "Fille", "Garçon"]

TYPE_VALUES    = ["Vêtement", "Chaussures", "Autre"]

CATEGORIE_VALUES = ["Haut", "Bas", "Robe/Combinaison", "Manteau/Veste", "Autre"]

STYLE_VALUES   = [
    "Jean", "Pull", "T-shirt", "Crop-top", "Robe", "Combinaison",
    "Chemise", "Sweat", "Hoodie", "Veste", "Manteau", "Short",
    "Pantalon", "Legging", "Jupe", "Débardeur", "Cardigan",
    "Blazer", "Parka", "Doudoune", "Sneakers", "Bottines",
    "Sandales", "Mocassins", "Derbies", "Autre",
]

CURRENCY_VALUES = ["EUR", "USD"]

# ==========================
#  Template d'un produit (schéma MongoDB)
# ==========================
PRODUCT_SCHEMA = {
    "name":        None,   # str
    "price_value": None,   # float
    "currency":    None,   # "EUR" | "USD"
    "description": None,   # str
    "genre":       None,   # GENRE_VALUES
    "sexe":        None,   # SEXE_VALUES
    "sizes":       [],     # [36, 37, 38 …]  → chaussures (int)
    "taille":      [],     # ["S","M","L" …] → vêtements  (str)
    "color":       None,   # str
    "rating":      None,   # float 1-5 | None
    "type":        None,   # TYPE_VALUES
    "categorie":   None,   # CATEGORIE_VALUES
    "style":       None,   # STYLE_VALUES
    "image":       None,   # str (URL)
    "url":         None,   # str (URL)
    "brand_source":     None,   # "Mango" | "Nike" | "Jules" | "Celio"
}
