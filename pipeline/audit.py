# =============================================================
#  pipeline/audit.py — Vérification et correction automatique du JSON
# =============================================================
import argparse
import json
import logging
import os
import re
import sys

from pipeline.config import OUTPUT_DIR

logger = logging.getLogger(__name__)

INPUT_FILE    = os.path.join(OUTPUT_DIR, "SmartWear_DB.json")
OUTPUT_FILE   = os.path.join(OUTPUT_DIR, "SmartWear_DB.json")
REJECTED_FILE = os.path.join(OUTPUT_DIR, "SmartWear_rejected.json")
CUSTOM_KW_FILE = os.path.join(OUTPUT_DIR, "non_clothing_keywords.json")

# Mots présents dans les noms de produits manifestement non-vestimentaires.
# Appliqué à TOUTE la base lors de l'audit (substring sur le nom en minuscules).
_NON_CLOTHING_NAME_KEYWORDS = frozenset([
    # ── Literie / linge de maison ─────────────────────────────────────
    "drap ", "drap-housse", "taie d", "housse de couette",
    # ── Éclairage ────────────────────────────────────────────────────
    "lampe ", "lampadaire", "applique en", "applique murale",
    "abat-jour", "lustre", "luminaire", "suspension ",
    # ── Rideaux / quincaillerie ───────────────────────────────────────
    "anneaux de rideaux", "anneau de rideau", "rideau ",
    "tringle à rideaux", "patère", "porte-manteau",
    # ── Maison / déco ────────────────────────────────────────────────
    "bougie", "candle", "vase", "coussin", "plaid", "nappe",
    "torchon", "plateau", "miroir", "cadre photo",
    # ── Vaisselle & cuisine ───────────────────────────────────────────
    "vaisselle", "assiette", "tasse", "mug", "carafe", "verre ",
    "casserole", "théière", "cafetière", "saladier",
    # ── Audio / tech ─────────────────────────────────────────────────
    "enceinte ", "haut-parleur", "casque audio",
    # ── Entretien / soin textile ──────────────────────────────────────
    "rasoir anti", "rasoir ", "défriseur", "détachant ",
    # ── Beauté / cosmétiques / parfumerie ─────────────────────────────
    "eau de toilette", "eau de parfum", "eau de cologne",
    "parfum d'intérieur", "diffuseur parfumé",
    "huile essentielle", "crème hydratante",
    "sérum ", "élixir ", "masque visage", "baume lèvres",
    "vernis ", "fond de teint",
    # ── Pins, bijoux & accessoires ────────────────────────────────────
    "badge ", "badge merci", "broche ",
    "bague ", "collier ", "bracelet ", "pendentif ",
    # ── Maroquinerie non-vestimentaire ───────────────────────────────
    "porte-clé", "porte-clés", "porte clé", "keychain",
    "mallette", "valise", "sac à dos", "sac bandoulière",
    "portefeuille", "porte-monnaie",
    # ── Papeterie / édition ───────────────────────────────────────────
    "stylo", "agenda", "affiche ", "poster ",
    # ── Alimentation / épicerie ───────────────────────────────────────
    "chocolat", "biscuit", "confiture", "café moulu", "thé ",
    "épices", "sel de", "miel ", "sauce ", "vinaigre",
    # ── Plantes / jardinage ───────────────────────────────────────────
    "pot de fleurs", "plante verte",
])

STYLE_TO_CATEGORIE = {
    "T-shirt": "Haut", "Pull": "Haut", "Sweat": "Haut", "Hoodie": "Haut",
    "Chemise": "Haut", "Débardeur": "Haut", "Crop-top": "Haut",
    "Cardigan": "Haut", "Polo": "Haut",
    "Jean": "Bas", "Pantalon": "Bas", "Short": "Bas", "Legging": "Bas", "Jupe": "Bas",
    "Veste": "Manteau/Veste", "Blazer": "Manteau/Veste", "Manteau": "Manteau/Veste",
    "Doudoune": "Manteau/Veste", "Parka": "Manteau/Veste",
    "Robe": "Robe/Combinaison", "Combinaison": "Robe/Combinaison",
    "Sneakers": "Chaussures", "Bottines": "Chaussures", "Sandales": "Chaussures",
    "Mocassins": "Chaussures", "Derbies": "Chaussures",
}


def _infer_sexe(name: str) -> str:
    n = name.lower()
    if any(k in n for k in ["men's", "mens ", "man's", " men ", " homme", "uomo", "hombre"]):
        return "Homme"
    if any(k in n for k in ["women's", "womens ", "woman's", " women ", " femme", "donna", "mujer"]):
        return "Femme"
    if any(k in n for k in ["kid", "kids", "youth", "junior", "baby", "boy", "girl",
                              "enfant", "fille", "garçon"]):
        return "Mixte"
    return "Mixte"


def _clean_description(text: str) -> str:
    if not text:
        return text
    text = re.sub(r'[\r\n]+', ' ', text)
    text = re.sub(r' {2,}', ' ', text)
    return text.strip()


def _deduplicate(products: list) -> tuple:
    seen, unique, dupes = set(), [], 0
    for p in products:
        key = (
            (p.get("name") or "").strip().lower(),
            (p.get("color") or "").strip().lower(),
            (p.get("brand_source") or "").strip().lower(),
        )
        if key in seen:
            dupes += 1
        else:
            seen.add(key)
            unique.append(p)
    return unique, dupes


# Marques connues comme concept-stores (mélangent vêtements et non-vêtements).
# Le check "double Autre + sans tailles" n'est appliqué que pour ces marques.
_CONCEPT_STORE_BRANDS = frozenset(["Merci"])

# Mots qui, présents N'IMPORTE OÙ dans le candidat avant " – ",
# signalent un nom de produit plutôt qu'une marque.
# Règle : un VRAI nom de marque n'inclut aucun de ces noms communs.
_MERCI_NON_BRAND_WORDS = frozenset([
    # ── Vêtements (types, pas des marques) ───────────────────────────
    "bonnet", "bob", "casquette", "chapeau", "béret", "beanie",
    "chemise", "chemisier", "crewneck", "sweat", "pull", "pullover",
    "hoodie", "cardigan", "débardeur", "polo", "top",
    "t-shirt", "tee-shirt", "tee",
    "jean", "jeans", "pantalon", "chinos", "short", "legging", "jupe",
    "veste", "blazer", "manteau", "doudoune", "parka", "trench",
    "robe", "combinaison", "salopette", "kimono",
    "chaussettes", "chaussons", "chaussures", "sneakers", "basket",
    "bottines", "mocassins", "sandales", "escarpins",
    # ── Éclairage / luminaires ────────────────────────────────────────
    "lampe", "lampadaire", "applique", "lustre", "plafonnier",
    "spot", "liseuse", "veilleuse", "luminaire", "abat-jour",
    # ── Literie / linge de maison ─────────────────────────────────────
    "drap", "housse", "taie", "couette", "traversin", "oreiller",
    "plaid", "coussin", "serviette", "torchon", "nappe",
    # ── Vaisselle & cuisine ───────────────────────────────────────────
    "verre", "assiette", "bol", "tasse", "mug", "coupe", "flûte",
    "carafe", "pichet", "théière", "cafetière", "saladier", "plateau",
    "casserole", "poêle", "moule", "passoire", "fouet", "spatule",
    "couteau", "fourchette", "cuillère",
    # ── Déco / maison ────────────────────────────────────────────────
    "vase", "bougie", "bougeoir", "miroir", "cadre", "tableau",
    "sculpture", "objet", "panier", "corbeille",
    # ── Papeterie / édition ───────────────────────────────────────────
    "carnet", "cahier", "stylo", "crayon", "livre", "affiche",
    "poster", "calendrier", "agenda",
    # ── Audio / tech ─────────────────────────────────────────────────
    "enceinte", "casque",
    # ── Beauté / cosmétiques / parfumerie ─────────────────────────────
    "parfum", "cologne", "toilette",           # "eau de parfum / cologne / toilette"
    "crème", "sérum", "huile", "baume", "gel",
    "masque", "exfoliant", "lotion", "savon",
    "vernis", "fond", "rouge", "mascara",      # maquillage
    "diffuseur",
    # ── Alimentation ─────────────────────────────────────────────────
    "chocolat", "biscuit", "confiture", "café", "thé",
    "épices", "sel", "poivre", "miel", "sauce", "vinaigre",
    "barre",                                    # barre de chocolat / barre céréales
    # ── Accessoires non-vestimentaires ───────────────────────────────
    "badge", "broche", "médaille", "bandana",
    "étole", "châle", "foulard",               # accessoires tissus (description produit)
    "bague", "collier", "bracelet", "pendentif", "boucles",
    "cabas", "sac", "pochette", "tote",
    "bouteille", "gourde", "thermos",
    "carte", "chariot", "banane",
])

# Un vrai nom de marque ne contient JAMAIS de prépositions/articles français au milieu.
# "Drap housse EN gaze DE coton" → "en", "de" → pas une marque.
# "Carhartt WIP" → aucune préposition → marque.
_FRENCH_FUNCTION_WORDS = frozenset([
    "en", "de", "du", "des", "au", "aux",
    "la", "le", "les", "un", "une",
    "à", "par", "pour", "sur", "sous", "avec", "d",
])

# Corrections de casse pour les marques mal capitalisées dans les titres Merci.
_BRAND_CASING_MAP = {
    "carhartt wip":   "Carhartt WIP",
    "a.p.c":          "A.P.C.",
    "a.p.c.":         "A.P.C.",
    "apc":            "A.P.C.",
    "ami paris":      "AMI Paris",
    "amiparis":       "AMI Paris",
    "maison kitsune": "Maison Kitsuné",
    "maison kitsuné": "Maison Kitsuné",
    "épice":          "Épice",
    "epice":          "Épice",
}


_MERCI_URL_DOMAIN = "merci-merci.com"


def _looks_like_product_name(candidate: str) -> bool:
    """Retourne True si le candidat ressemble à un nom de produit (pas une marque)."""
    words = candidate.lower().split()
    # Contient un mot de la liste produit → pas une marque
    if any(w in _MERCI_NON_BRAND_WORDS for w in words):
        return True
    # Contient une préposition/article français → description de produit, pas une marque
    # Exception : "x" est autorisé (collaborations : "Dôen x Merci")
    if any(w in _FRENCH_FUNCTION_WORDS for w in words if w != "x"):
        return True
    return False


def _repair_corrupted_merci_brands(products: list) -> tuple:
    """Répare les items Merci dont la marque a été mal extraite lors d'un précédent audit.
    Identifie les items Merci (par leur URL) dont brand_source est un nom de produit,
    reconstruit le nom original ('brand_source – name') et remet brand_source = 'Merci'."""
    repaired = 0
    for p in products:
        url = (p.get("url") or "").lower()
        if _MERCI_URL_DOMAIN not in url:
            continue
        brand = p.get("brand_source") or ""
        if not brand or brand.lower() == "merci":
            continue
        if _looks_like_product_name(brand):
            p["name"]         = f"{brand} – {p.get('name') or ''}".strip(" –")
            p["brand_source"] = "Merci"
            repaired += 1
    logger.info("[Audit] Items Merci réparés (mauvaise marque) : %d", repaired)
    return products, repaired


def _load_custom_keywords() -> frozenset:
    """Charge les mots-clés custom ajoutés depuis le Streamlit."""
    if not os.path.exists(CUSTOM_KW_FILE):
        return frozenset()
    try:
        with open(CUSTOM_KW_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return frozenset(kw.lower().strip() for kw in data if kw.strip())
    except Exception:
        return frozenset()


def _remove_non_clothing(products: list) -> tuple:
    """Supprime les produits dont le nom signale clairement un article non-vestimentaire.
    Pour les concept-stores, supprime aussi les articles sans style ni catégorie reconnus.
    Les articles rejetés sont sauvegardés dans SmartWear_rejected.json."""
    custom_kw = _load_custom_keywords()
    all_kw    = _NON_CLOTHING_NAME_KEYWORDS | custom_kw

    kept, rejected = [], []
    for p in products:
        name  = (p.get("name") or "").lower()
        brand = (p.get("brand_source") or "")
        reason = None

        # Mots-clés (built-in + custom) dans le nom
        matched = next((kw for kw in all_kw if kw in name), None)
        if matched:
            reason = f"keyword:{matched}"

        # Concept-stores : rejet si aucun style ET aucune catégorie connus
        elif brand in _CONCEPT_STORE_BRANDS:
            style     = p.get("style") or "Autre"
            categorie = p.get("categorie") or "Autre"
            type_     = p.get("type") or ""
            if style == "Autre" and categorie == "Autre" and type_ != "Chaussures":
                reason = "concept-store:double-autre"

        if reason:
            logger.debug("[Audit] Rejeté (%s) : %s", reason, p.get("name"))
            rejected.append({**p, "_reject_reason": reason})
        else:
            kept.append(p)

    # Sauvegarder les rejetés pour inspection dans le dashboard
    try:
        with open(REJECTED_FILE, "w", encoding="utf-8") as f:
            json.dump(rejected, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.warning("[Audit] Impossible d'écrire rejected.json : %s", e)

    return kept, len(rejected)


def _is_merci_brand(candidate: str) -> bool:
    """Retourne True si le candidat est une vraie marque externe (pas un nom de produit)."""
    if not candidate or len(candidate) > 50 or not candidate[0].isupper():
        return False
    return not _looks_like_product_name(candidate)


def _normalize_brand(brand: str) -> str:
    return _BRAND_CASING_MAP.get(brand.lower(), brand)


def _fix_merci_brands(products: list) -> tuple:
    """Pour les items Merci dont le nom contient 'Marque – Produit',
    extrait la vraie marque et nettoie le nom.
    Ignore les préfixes qui sont des types produits (bonnet, chemise…)."""
    fixed = 0
    for p in products:
        if (p.get("brand_source") or "").lower() != "merci":
            continue
        name = p.get("name") or ""
        for sep in [" – ", " - "]:
            if sep in name:
                candidate, rest = name.split(sep, 1)
                candidate = candidate.strip()
                if _is_merci_brand(candidate):
                    p["brand_source"] = _normalize_brand(candidate)
                    p["name"]         = rest.strip()
                    fixed += 1
                break  # ne tester qu'un séparateur par nom
    return products, fixed


def _fix_categorie(p: dict) -> tuple:
    style = p.get("style")
    if not style or style not in STYLE_TO_CATEGORIE:
        return p, False
    expected = STYLE_TO_CATEGORIE[style]
    if p.get("categorie") != expected:
        p["categorie"] = expected
        return p, True
    return p, False


def run_audit(input_file: str = INPUT_FILE) -> dict:
    """Point d'entrée réutilisable (Airflow, CLI, tests)."""
    if not os.path.exists(input_file):
        logger.error("[Audit] Fichier introuvable : %s", input_file)
        return {}

    with open(input_file, encoding="utf-8") as f:
        products = json.load(f)

    total = len(products)
    logger.info("[Audit] %d produits chargés", total)

    products, dupes_removed = _deduplicate(products)

    # 1. Réparer les items corrompus par un précédent audit (mauvaise extraction de marque)
    products, _ = _repair_corrupted_merci_brands(products)

    # 2. Extraction correcte des vraies marques AVANT le filtre non-vestimentaire
    products, brands_fixed = _fix_merci_brands(products)
    logger.info("[Audit] Marques Merci corrigées : %d", brands_fixed)

    products, non_clothing_removed = _remove_non_clothing(products)
    logger.info("[Audit] Non-vestimentaires supprimés : %d", non_clothing_removed)

    desc_fixed = 0
    for p in products:
        original = p.get("description") or ""
        cleaned = _clean_description(original)
        if cleaned != original:
            p["description"] = cleaned
            desc_fixed += 1

    sexe_fixed = 0
    for p in products:
        if not p.get("sexe"):
            p["sexe"] = _infer_sexe(p.get("name", ""))
            sexe_fixed += 1

    cat_fixed = 0
    for p in products:
        p, fixed = _fix_categorie(p)
        if fixed:
            cat_fixed += 1

    stats = {
        "total_initial":        total,
        "dupes_removed":        dupes_removed,
        "brands_fixed":         brands_fixed,
        "non_clothing_removed": non_clothing_removed,
        "desc_fixed":           desc_fixed,
        "sexe_fixed":           sexe_fixed,
        "cat_fixed":            cat_fixed,
        "total_final":          len(products),
    }

    logger.info(
        "[Audit] Doublons: %d | Descriptions: %d | Sexe: %d | Catégories: %d | Final: %d",
        dupes_removed, desc_fixed, sexe_fixed, cat_fixed, len(products),
    )

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(products, f, indent=2, ensure_ascii=False)
    logger.info("[Audit] Sauvegardé → %s", OUTPUT_FILE)

    return stats


def main():
    parser = argparse.ArgumentParser(description="Audit & correction SmartWear_DB.json")
    parser.add_argument("--input", default=INPUT_FILE)
    args = parser.parse_args()

    stats = run_audit(args.input)
    if stats:
        print(f"\n{'='*55}")
        print(f"  Produits initiaux        : {stats['total_initial']}")
        print(f"  Doublons supprimés       : {stats['dupes_removed']}")
        print(f"  Non-vestimentaires retirés: {stats['non_clothing_removed']}")
        print(f"  Descriptions nettoyées   : {stats['desc_fixed']}")
        print(f"  Sexe inférés             : {stats['sexe_fixed']}")
        print(f"  Catégories corrigées     : {stats['cat_fixed']}")
        print(f"  Produits finaux          : {stats['total_final']}")
        print(f"{'='*55}\n")


if __name__ == "__main__":
    main()
