"""
Seed vitrine : crée 2 comptes démo avec des produits réels issus du pipeline de scraping.
Usage : python seed_demo.py
"""
from dotenv import load_dotenv
load_dotenv()

import hashlib
import io
import json
import os
import random
import sys

os.environ.setdefault("HF_HUB_OFFLINE", "1")

import requests
from PIL import Image

from app import create_app
from config import THUMB_FOLDER, THUMB_SIZE, UPLOAD_FOLDER
from extensions import db
from models import ClothingItem, User

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DB_PATH = os.path.join(os.path.dirname(__file__), "pipeline", "output", "SmartWear_DB.json")
ACCOUNTS = [
    {"username": "demo_homme", "email": "demo.homme@vitrine.fr", "password": "Vitrine2024!", "gender": "Homme"},
    {"username": "demo_femme", "email": "demo.femme@vitrine.fr", "password": "Vitrine2024!", "gender": "Femme"},
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
COLOR_MAP = {
    "blanc": "Blanc", "white": "Blanc", "ecru": "Blanc", "crème": "Blanc", "cream": "Blanc", "ivoire": "Blanc",
    "noir": "Noir", "black": "Noir",
    "gris": "Gris", "grey": "Gris", "gray": "Gris", "anthracite": "Gris",
    "beige": "Beige", "sable": "Beige", "taupe": "Beige", "noisette": "Beige", "caramel": "Beige",
    "marron": "Marron", "brown": "Marron", "chocolat": "Marron", "cognac": "Marron",
    "camel": "Camel", "caramel": "Camel",
    "rouge": "Rouge", "red": "Rouge", "bordeaux": "Rouge", "wine": "Rouge", "vin": "Rouge",
    "rose": "Rose", "pink": "Rose",
    "orange": "Orange",
    "jaune": "Jaune", "yellow": "Jaune",
    "vert": "Vert", "green": "Vert", "olive": "Vert", "kaki": "Vert", "khaki": "Vert", "sauge": "Vert",
    "bleu": "Bleu", "blue": "Bleu", "marine": "Bleu", "navy": "Bleu", "indigo": "Bleu",
    "violet": "Violet", "purple": "Violet", "lilas": "Violet",
}

def normalize_color(raw: str) -> str:
    if not raw:
        return "Multicolore"
    low = raw.lower()
    for k, v in COLOR_MAP.items():
        if k in low:
            return v
    return "Multicolore"


STYLE_TO_CATEGORY = {
    "T-shirt": "T-shirts", "Polo": "T-shirts",
    "Chemise": "Hauts", "Crop-top": "Hauts",
    "Pull": "Pulls & Sweats", "Sweat": "Pulls & Sweats", "Hoodie": "Pulls & Sweats", "Cardigan": "Pulls & Sweats",
    "Veste": "Vestes & Manteaux", "Manteau": "Vestes & Manteaux", "Blazer": "Vestes & Manteaux",
    "Jean": "Jeans", "Pantalon": "Pantalons", "Short": "Shorts",
    "Robe": "Robes & Jupes", "Jupe": "Robes & Jupes", "Combinaison": "Robes & Jupes",
    "Sneakers": "Chaussures", "Sandales": "Chaussures", "Bottines": "Chaussures", "Mocassins": "Chaussures",
}

NAME_TO_CATEGORY = {
    "t-shirt": "T-shirts", "tee-shirt": "T-shirts",
    "polo": "T-shirts",
    "chemise": "Hauts", "surchemise": "Hauts",
    "pull": "Pulls & Sweats", "pullover": "Pulls & Sweats", "gilet": "Pulls & Sweats", "cardigan": "Pulls & Sweats",
    "sweat": "Pulls & Sweats", "sweatshirt": "Pulls & Sweats", "hoodie": "Pulls & Sweats",
    "veste": "Vestes & Manteaux", "blouson": "Vestes & Manteaux", "blazer": "Vestes & Manteaux",
    "manteau": "Vestes & Manteaux", "coat": "Vestes & Manteaux", "trench": "Vestes & Manteaux",
    "jean": "Jeans",
    "pantalon": "Pantalons", "chino": "Pantalons",
    "short": "Shorts",
    "jupe": "Robes & Jupes", "robe": "Robes & Jupes",
    "baskets": "Chaussures", "sneakers": "Chaussures", "bottines": "Chaussures",
    "boots": "Chaussures", "mocassins": "Chaussures", "loafer": "Chaussures",
}

SEASON_RULES = {
    "Pulls & Sweats": "Hiver", "Vestes & Manteaux": "Automne",
    "Shorts": "Été", "T-shirts": "Été",
    "Jeans": "Toutes saisons", "Pantalons": "Toutes saisons",
    "Hauts": "Toutes saisons", "Robes & Jupes": "Printemps",
    "Chaussures": "Toutes saisons",
}

AI_STYLE_MAP = {
    "Isabel Marant": "chic", "Rouje": "chic", "AMI Paris": "chic", "A.P.C.": "minimaliste",
    "Maison Labiche": "casual", "Balzac Paris": "casual", "BonneGueule": "casual",
    "Merci": "minimaliste",
}

def guess_category(item: dict) -> str:
    name = item.get("name", "").lower()
    for kw, cat in NAME_TO_CATEGORY.items():
        if kw in name:
            return cat
    return STYLE_TO_CATEGORY.get(item.get("style", ""), "Autre")


def download_image(url: str):
    """Télécharge et enregistre l'image + miniature. Retourne (image_path, thumb_path)."""
    try:
        r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            return None, None
        ext = url.split("?")[0].rsplit(".", 1)[-1].lower()
        if ext not in ("jpg", "jpeg", "png", "webp", "gif"):
            ext = "jpg"
        digest = hashlib.md5(url.encode()).hexdigest()
        fname = f"{digest}.{ext}"
        img_path = os.path.join(UPLOAD_FOLDER, fname)
        thumb_name = f"thumb_{digest}.{ext}"
        thumb_path = os.path.join(THUMB_FOLDER, thumb_name)

        if not os.path.exists(img_path):
            with open(img_path, "wb") as f:
                f.write(r.content)

        if not os.path.exists(thumb_path):
            img = Image.open(io.BytesIO(r.content)).convert("RGB")
            img.thumbnail(THUMB_SIZE)
            img.save(thumb_path)

        return f"uploads/{fname}", f"uploads/thumbs/{thumb_name}"
    except Exception as e:
        print(f"    [IMG ERR] {url[:60]} → {e}")
        return None, None


# ---------------------------------------------------------------------------
# Sélection des produits scrapés
# ---------------------------------------------------------------------------
def load_scraped_db():
    with open(DB_PATH) as f:
        return json.load(f)


def pick(pool, kws, excl=[], seed=0, n=1, no_taille=False):
    filtered = [d for d in pool
        if d.get("image") and d.get("price_value") and d.get("color")
        and (no_taille or d.get("taille"))
        and any(k in d["name"].lower() for k in kws)
        and not any(k in d["name"].lower() for k in excl)
    ]
    random.seed(seed)
    sample = random.sample(filtered, min(n, len(filtered)))
    return sample[:n]


def build_selections(scraped):
    BONS = {"Isabel Marant", "A.P.C.", "AMI Paris", "Rouje", "Maison Labiche", "Balzac Paris", "Merci", "BonneGueule"}
    h_pool = [d for d in scraped if d.get("sexe") in ("Homme", "Mixte") and d.get("brand_source") in BONS]
    f_pool = [d for d in scraped if d.get("sexe") in ("Femme", "Mixte") and d.get("brand_source") in BONS]
    merci = [d for d in scraped if d.get("brand_source") == "Merci"]

    jean_pool_h = [d for d in h_pool if any(k in d["name"].lower() for k in ["jean droit", "jean killy", "jean slim"])]
    basket_pool = [d for d in merci if any(k in d["name"].lower() for k in ["baskets", "gel ", "new balance", "autry", "salomon"])]

    homme = (
        pick(h_pool, ["t-shirt"], ["femme", "sans manches"], seed=1)
        + pick(h_pool, ["t-shirt"], ["femme"], seed=51, n=3)[1:2]   # 2e T-shirt différent
        + pick(h_pool, ["chemise", "surchemise"], ["sweat", "hoodie"], seed=3)
        + pick(h_pool, ["pull", "pullover"], ["pantalon", "short", "sans manches"], seed=4)
        + pick(h_pool, ["sweat", "sweatshirt"], ["short", "pant", "hello kitty"], seed=5)
        + pick(h_pool, ["veste", "blouson"], ["jupe", "robe", "pant"], seed=6)
        + pick(h_pool, ["manteau"], ["maillot"], seed=7)
        + pick(h_pool, ["pantalon", "chino"], ["jean", "denim", "short"], seed=8)
        + pick(h_pool, ["short"], ["sweat", "jogging", "maillot"], seed=9)
        + pick(h_pool, ["polo"], ["robe"], seed=10)
        + pick(jean_pool_h, ["jean"], [], seed=11)
        + pick(jean_pool_h, ["jean"], [], seed=52, n=3)[1:2]        # 2e jean différent
        + pick(basket_pool, ["baskets", "gel", "new balance", "autry", "salomon"], [], seed=13, no_taille=True)
    )

    femme = (
        pick(f_pool, ["t-shirt"], ["homme"], seed=20)
        + pick(f_pool, ["chemise", "surchemise"], ["sweat"], seed=21)
        + pick(f_pool, ["pull", "pullover"], ["pantalon", "sans manches"], seed=22)
        + pick(f_pool, ["sweat", "sweatshirt"], ["short"], seed=23)
        + pick(f_pool, ["veste", "blazer"], ["jupe", "robe"], seed=24)
        + pick(f_pool, ["manteau", "trench"], [], seed=25)
        + pick(f_pool, ["pantalon"], ["jean", "denim", "short"], seed=26)
        + pick(f_pool, ["jupe"], [], seed=27)
        + pick(f_pool, ["robe"], ["polo"], seed=28)
        + pick(f_pool, ["robe"], ["polo"], seed=29, n=2)[1:2]
        # Jeans vrais
        + pick([d for d in f_pool if "jean droit" in d["name"].lower() or "jean jane" in d["name"].lower()],
               ["jean"], [], seed=30)
        + pick([d for d in f_pool if "jean droit" in d["name"].lower() or "jean jane" in d["name"].lower()],
               ["jean"], [], seed=31, n=2)[1:2]
        # Baskets et bottines
        + pick([d for d in merci if any(k in d["name"].lower() for k in ["baskets", "gel ", "autry"])
                and "homme" not in d["name"].lower()],
               ["baskets", "gel", "autry"], ["mid"], seed=32, no_taille=True)
        + pick([d for d in scraped if d.get("brand_source") in ("Balzac Paris", "Rouje", "Isabel Marant")
                and any(k in d["name"].lower() for k in ["bottine", "boot"])],
               ["bottine", "boot"], [], seed=33, no_taille=True)
    )

    return homme, femme


# ---------------------------------------------------------------------------
# Insertion en base
# ---------------------------------------------------------------------------
def item_from_scraped(scraped_item: dict, user_id: int) -> ClothingItem:
    brand = scraped_item.get("brand_source", "")
    category = guess_category(scraped_item)
    size = scraped_item["taille"][0] if scraped_item.get("taille") else "M"
    color = normalize_color(scraped_item.get("color", ""))
    season = SEASON_RULES.get(category, "Toutes saisons")
    ai_style = AI_STYLE_MAP.get(brand, "casual")

    print(f"    Téléchargement image : {scraped_item['name'][:50]}...")
    img_path, thumb_path = download_image(scraped_item["image"])

    return ClothingItem(
        user_id=user_id,
        name=scraped_item["name"],
        category=category,
        brand=brand,
        size=size,
        color=color,
        season=season,
        condition="Excellent",
        price=scraped_item.get("price_value"),
        notes=scraped_item.get("description", "")[:500] if scraped_item.get("description") else None,
        image_path=img_path,
        thumb_path=thumb_path,
        ai_style=ai_style,
        ai_formality=2,
        ai_pattern="uni",
        ai_material=None,
        ai_analyzed=True,
    )


# ---------------------------------------------------------------------------
# FashionCLIP embeddings
# ---------------------------------------------------------------------------
def _generate_embeddings(user):
    """Génère et stocke les embeddings FashionCLIP pour tous les items du user."""
    try:
        from ai.embeddings import encode_image, store_item, is_model_ready, _get_model
    except ImportError as e:
        print(f"    [SKIP] FashionCLIP non disponible ({e})")
        return

    # Attendre que FashionCLIP finisse son chargement (warm-up thread de l'app)
    if not is_model_ready():
        print("  Chargement de FashionCLIP (peut prendre 1-2 min au premier lancement)...")
        try:
            _get_model()  # charge synchroniquement si pas encore en cours
        except RuntimeError:
            # En cours de chargement dans un thread → attendre
            import time
            for _ in range(120):
                if is_model_ready():
                    break
                time.sleep(1)
            else:
                print("    [SKIP] FashionCLIP n'a pas répondu dans les 2 min.")
                return

    items = user.items.all()
    ok = 0
    for item in items:
        if not item.image_path:
            continue
        img_abs = os.path.join(os.path.dirname(__file__), "static", item.image_path)
        if not os.path.exists(img_abs):
            continue
        try:
            embedding = encode_image(img_abs)
            metadata = {
                "name": item.name,
                "category": item.category,
                "color": item.color or "",
                "season": item.season or "",
                "style": item.ai_style or "",
                "formality": item.ai_formality or 2,
            }
            description = item.ai_description or f"{item.name} — {item.category}"
            store_item(item.id, user.id, embedding, metadata, description)
            ok += 1
        except Exception as e:
            print(f"    [EMBED ERR] {item.name[:40]} → {e}")
    print(f"  -> {ok}/{len(items)} embeddings générés\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def seed():
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(THUMB_FOLDER, exist_ok=True)

    print("Chargement de la base scrapée...")
    scraped = load_scraped_db()
    print(f"  {len(scraped)} produits chargés")

    homme_items, femme_items = build_selections(scraped)
    print(f"  Sélection : {len(homme_items)} homme, {len(femme_items)} femme")

    wardrobes = {"demo_homme": homme_items, "demo_femme": femme_items}

    app = create_app()
    with app.app_context():
        for account in ACCOUNTS:
            existing = User.query.filter_by(email=account["email"]).first()
            if existing:
                # Supprimer les anciens items du compte vitrine pour repartir propre
                existing.items.delete()
                db.session.commit()
                print(f"[RESET] Compte {account['email']} — anciens items supprimés")
                user = existing
            else:
                user = User(
                    email=account["email"],
                    username=account["username"],
                    gender=account["gender"],
                    email_verified=True,
                )
                user.set_password(account["password"])
                db.session.add(user)
                db.session.flush()
                print(f"[OK] Compte créé : {account['email']} (id={user.id})")

            print(f"  Insertion des vêtements pour {account['username']}...")
            for s_item in wardrobes[account["username"]]:
                ci = item_from_scraped(s_item, user.id)
                db.session.add(ci)

            db.session.commit()
            count = user.items.count()
            print(f"  -> {count} vêtements insérés")

            # Génération des embeddings FashionCLIP pour que le stylist IA locale fonctionne
            print("  Génération des embeddings FashionCLIP...")
            _generate_embeddings(user)

    print("=" * 50)
    print("Comptes vitrine prêts :")
    for a in ACCOUNTS:
        print(f"  [{a['gender']}]  {a['email']}  /  {a['password']}")


if __name__ == "__main__":
    seed()
