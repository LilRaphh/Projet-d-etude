"""
Reseed demo_homme : 28 vêtements variés + ai_analyzed=False pour re-analyse IA.
Usage : python reseed_homme.py
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

DB_PATH = os.path.join(os.path.dirname(__file__), "pipeline", "output", "SmartWear_DB.json")
TARGET_EMAIL = "demo.homme@vitrine.fr"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
COLOR_MAP = {
    "blanc": "Blanc", "white": "Blanc", "ecru": "Blanc", "crème": "Blanc", "cream": "Blanc", "ivoire": "Blanc",
    "noir": "Noir", "black": "Noir",
    "gris": "Gris", "grey": "Gris", "gray": "Gris", "anthracite": "Gris",
    "beige": "Beige", "sable": "Beige", "taupe": "Beige", "naturel": "Beige",
    "marron": "Marron", "brown": "Marron", "chocolat": "Marron", "cognac": "Marron",
    "camel": "Camel",
    "rouge": "Rouge", "red": "Rouge", "bordeaux": "Rouge",
    "rose": "Rose", "pink": "Rose",
    "orange": "Orange",
    "jaune": "Jaune", "yellow": "Jaune",
    "vert": "Vert", "green": "Vert", "olive": "Vert", "kaki": "Vert", "khaki": "Vert", "sauge": "Vert",
    "bleu": "Bleu", "blue": "Bleu", "marine": "Bleu", "navy": "Bleu", "indigo": "Bleu",
    "violet": "Violet", "purple": "Violet",
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
    "Sneakers": "Chaussures", "Sandales": "Chaussures", "Bottines": "Chaussures", "Mocassins": "Chaussures",
}

NAME_TO_CATEGORY = {
    "t-shirt": "T-shirts", "tee-shirt": "T-shirts", "tee shirt": "T-shirts",
    "polo": "T-shirts",
    "chemise": "Hauts", "surchemise": "Hauts",
    "pull": "Pulls & Sweats", "pullover": "Pulls & Sweats", "gilet": "Pulls & Sweats", "cardigan": "Pulls & Sweats",
    "sweat": "Pulls & Sweats", "sweatshirt": "Pulls & Sweats", "hoodie": "Pulls & Sweats",
    "veste": "Vestes & Manteaux", "blouson": "Vestes & Manteaux", "blazer": "Vestes & Manteaux",
    "manteau": "Vestes & Manteaux", "coat": "Vestes & Manteaux", "trench": "Vestes & Manteaux",
    "jean": "Jeans",
    "pantalon": "Pantalons", "chino": "Pantalons", "trouser": "Pantalons",
    "short": "Shorts",
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

def guess_category(item: dict) -> str:
    name = item.get("name", "").lower()
    for kw, cat in NAME_TO_CATEGORY.items():
        if kw in name:
            return cat
    style_cat = STYLE_TO_CATEGORY.get(item.get("style", ""), "")
    if style_cat:
        return style_cat
    if item.get("type") == "Chaussures":
        return "Chaussures"
    return "Autre"


def download_image(url: str):
    try:
        r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            return None, None
        ext = url.split("?")[0].rsplit(".", 1)[-1].lower()
        if ext not in ("jpg", "jpeg", "png", "webp"):
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
# Sélection — 28 items répartis sur 5 catégories
# ---------------------------------------------------------------------------
def pick(pool, brand_filter=None, kws=None, excl=None, style=None, seed=0, n=1, color_filter=None):
    filtered = pool
    if brand_filter:
        filtered = [d for d in filtered if d.get("brand_source") in brand_filter]
    if kws:
        filtered = [d for d in filtered if any(k in d.get("name", "").lower() for k in kws)]
    if excl:
        filtered = [d for d in filtered if not any(k in d.get("name", "").lower() for k in excl)]
    if style:
        filtered = [d for d in filtered if d.get("style") == style]
    if color_filter:
        filtered = [d for d in filtered if any(c in (d.get("color") or "").lower() for c in color_filter)]
    filtered = [d for d in filtered if d.get("image")]
    random.seed(seed)
    sample = random.sample(filtered, min(n, len(filtered)))
    return sample[:n]


def build_selection(scraped):
    HAUTS = {"A.P.C.", "AMI Paris", "Maison Labiche", "BonneGueule", "Stüssy", "Palace"}
    BAS = {"A.P.C.", "AMI Paris", "BonneGueule", "Merci"}
    OUTERWEAR = {"A.P.C.", "AMI Paris", "BonneGueule", "Maison Labiche"}
    CHAUSSURES = {"BonneGueule", "Filling Pieces", "Merci"}

    male = [d for d in scraped if d.get("sexe") in ("Homme", "Mixte")]

    items = []

    # === HAUTS (10 items) ===
    # 3 T-shirts
    items += pick(male, HAUTS, kws=["t-shirt", "tee-shirt", "tee shirt"], excl=["femme", "crop"], seed=101)
    items += pick(male, {"Maison Labiche"}, style="T-shirt", excl=["femme"], seed=102)
    items += pick(male, {"Stüssy"}, style="T-shirt", seed=103)
    # 2 chemises
    items += pick(male, {"A.P.C.", "BonneGueule"}, kws=["chemise", "surchemise", "shirt"], excl=["sweat","pull"], seed=104)
    items += pick(male, {"AMI Paris"}, kws=["chemise", "shirt"], excl=["sweat"], seed=105)
    # 2 pulls
    items += pick(male, {"AMI Paris"}, style="Pull", excl=["femme"], seed=106)
    items += pick(male, {"BonneGueule"}, style="Pull", seed=107)
    # 2 sweats / hoodies
    items += pick(male, {"Stüssy", "Palace"}, style="Sweat", seed=108)
    items += pick(male, {"Palace", "Stüssy"}, style="Hoodie", seed=109)
    # 1 polo
    items += pick(male, {"AMI Paris", "Maison Labiche"}, style="Polo", seed=110)

    # === BAS (7 items) ===
    # 2 pantalons
    items += pick(male, {"AMI Paris", "A.P.C."}, style="Pantalon", excl=["jean", "denim"], seed=201)
    items += pick(male, {"BonneGueule"}, style="Pantalon", excl=["jean", "denim", "short"], seed=202)
    # 2 jeans
    items += pick(male, {"A.P.C.", "Merci"}, style="Jean", seed=203)
    items += pick(male, {"A.P.C.", "Merci"}, style="Jean", seed=204)
    # 1 short
    items += pick(male, {"Stüssy", "Palace", "A.P.C."}, style="Short", excl=["maillot"], seed=205)
    # 2 items supplémentaires (chino, cargo ou jean différent)
    items += pick(male, {"BonneGueule", "AMI Paris"}, kws=["chino", "cargo", "pantalon"], excl=["jean", "denim"], seed=206)
    items += pick(male, {"A.P.C.", "AMI Paris"}, style="Jean", seed=207)

    # === OUTERWEAR (4 items) ===
    items += pick(male, OUTERWEAR, style="Veste", excl=["femme", "jupe", "robe"], seed=301)
    items += pick(male, {"A.P.C.", "AMI Paris"}, style="Veste", excl=["femme"], seed=302)
    items += pick(male, OUTERWEAR, style="Manteau", excl=["femme"], seed=303)
    items += pick(male, {"AMI Paris", "A.P.C.", "BonneGueule"}, kws=["blouson", "bomber", "overshirt"], seed=304)

    # === CHAUSSURES (5 items) ===
    items += pick(male, {"BonneGueule"}, style="Sneakers", seed=401)
    items += pick(male, {"BonneGueule"}, style="Sneakers", seed=402)
    items += pick(male, {"Filling Pieces"}, kws=[], excl=[], seed=403,
                  color_filter=None)  # n'importe quel FP avec image
    fp_shoes = [d for d in scraped if d.get("brand_source") == "Filling Pieces" and d.get("type") == "Chaussures" and d.get("image")]
    if fp_shoes:
        random.seed(403)
        items += random.sample(fp_shoes, min(1, len(fp_shoes)))
    merci_shoes = [d for d in scraped
                   if d.get("brand_source") == "Merci"
                   and any(k in d.get("name", "").lower() for k in ["karhu", "filling", "autry", "new balance", "salomon", "sneaker", "baskets"])
                   and d.get("image")]
    if merci_shoes:
        random.seed(404)
        items += random.sample(merci_shoes, min(2, len(merci_shoes)))

    # Dédupliquer par nom
    seen = set()
    unique = []
    for it in items:
        key = it.get("name", "")[:40].lower()
        if key not in seen and it.get("image"):
            seen.add(key)
            unique.append(it)

    return unique


# ---------------------------------------------------------------------------
# Insertion en base
# ---------------------------------------------------------------------------
def item_from_scraped(scraped_item: dict, user_id: int) -> ClothingItem:
    brand = scraped_item.get("brand_source", "")
    category = guess_category(scraped_item)
    size = scraped_item["taille"][0] if scraped_item.get("taille") else "M"
    color = normalize_color(scraped_item.get("color", ""))
    season = SEASON_RULES.get(category, "Toutes saisons")

    print(f"    [{brand}] {scraped_item['name'][:50]}…")
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
        notes=(scraped_item.get("description", "")[:500] if scraped_item.get("description") else None),
        image_path=img_path,
        thumb_path=thumb_path,
        ai_analyzed=False,  # Force re-analyse avec le prompt amélioré
        ai_formality=2,
    )


# ---------------------------------------------------------------------------
# FashionCLIP embeddings
# ---------------------------------------------------------------------------
def generate_embeddings(user):
    try:
        from ai.embeddings import encode_image, store_item, is_model_ready, _get_model
    except ImportError as e:
        print(f"    [SKIP] FashionCLIP non disponible ({e})")
        return

    if not is_model_ready():
        print("  Chargement FashionCLIP…")
        try:
            _get_model()
        except RuntimeError:
            import time
            for _ in range(120):
                if is_model_ready():
                    break
                time.sleep(1)
            else:
                print("    [SKIP] FashionCLIP timeout.")
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
    print(f"  → {ok}/{len(items)} embeddings générés")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def reseed():
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(THUMB_FOLDER, exist_ok=True)

    print("Chargement SmartWear_DB…")
    with open(DB_PATH) as f:
        scraped = json.load(f)
    print(f"  {len(scraped)} produits disponibles")

    items = build_selection(scraped)
    print(f"  Sélection : {len(items)} vêtements pour demo_homme\n")

    app = create_app()
    with app.app_context():
        user = User.query.filter_by(email=TARGET_EMAIL).first()
        if not user:
            print(f"[ERREUR] Compte {TARGET_EMAIL} introuvable. Lance seed_demo.py d'abord.")
            sys.exit(1)

        # Reset propre
        ClothingItem.query.filter_by(user_id=user.id).delete()
        db.session.commit()
        print(f"[RESET] {user.username} — anciens items supprimés\n")

        print("Insertion des vêtements…")
        for s_item in items:
            ci = item_from_scraped(s_item, user.id)
            db.session.add(ci)

        db.session.commit()
        count = ClothingItem.query.filter_by(user_id=user.id).count()
        print(f"\n  → {count} vêtements insérés (ai_analyzed=False : tous à re-analyser)\n")

        print("Génération des embeddings FashionCLIP…")
        generate_embeddings(user)

    print("\n" + "="*55)
    print(f"demo_homme prêt avec {count} vêtements.")
    print("→ Connecte-toi et va dans Garde-robe → Analyser tout")
    print(f"  Email : {TARGET_EMAIL}  /  Pass : Vitrine2024!")


if __name__ == "__main__":
    reseed()
