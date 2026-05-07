# =============================================================
#  pipeline/config.py — Configuration centrale SmartWear Scraper
# =============================================================
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ==========================
#  Clé API Gemini
# ==========================
GOOGLE_GEMINI_API_KEY = os.getenv("GOOGLE_GEMINI_API_KEY")
GEMINI_MODEL_NAME = "gemini-2.0-flash"

# ==========================
#  Dossiers
# ==========================
PIPELINE_DIR = Path(__file__).parent
OUTPUT_DIR = str(PIPELINE_DIR / "output")
LOG_DIR = str(PIPELINE_DIR / "logs")

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
GENRE_VALUES = ["Enfant", "Adolescent", "Adulte"]
SEXE_VALUES = ["Femme", "Homme", "Fille", "Garçon"]
TYPE_VALUES = ["Vêtement", "Chaussures", "Autre"]
CATEGORIE_VALUES = ["Haut", "Bas", "Robe/Combinaison", "Manteau/Veste", "Autre"]
STYLE_VALUES = [
    "Jean", "Pull", "T-shirt", "Crop-top", "Robe", "Combinaison",
    "Chemise", "Sweat", "Hoodie", "Polo", "Veste", "Manteau", "Short",
    "Pantalon", "Legging", "Jupe", "Débardeur", "Cardigan",
    "Blazer", "Parka", "Doudoune", "Sneakers", "Bottines",
    "Sandales", "Mocassins", "Derbies", "Autre",
]
CURRENCY_VALUES = ["EUR", "USD", "GBP"]

# ==========================
#  Template d'un produit (schéma MongoDB)
# ==========================
PRODUCT_SCHEMA = {
    "name":         None,
    "price_value":  None,
    "currency":     None,
    "description":  None,
    "genre":        None,
    "sexe":         None,
    "sizes":        [],
    "taille":       [],
    "color":        None,
    "rating":       None,
    "type":         None,
    "categorie":    None,
    "style":        None,
    "image":        None,
    "url":          None,
    "brand_source": None,
}
