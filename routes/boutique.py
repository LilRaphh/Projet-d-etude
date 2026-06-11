"""
routes/boutique.py
Page "Boutique" — affiche les produits scrapés depuis SmartWear_DB.json
"""
import json
import logging
import os
import random
import re
import threading
import uuid
from pathlib import Path

from flask import Blueprint, jsonify, render_template, request

_logger = logging.getLogger(__name__)

from extensions import db
from models import ClothingItem, WishlistItem
from utils.auth import current_user, get_ctx, login_required
from utils.currency import apply_to_products, convert_price, get_rate, normalize as normalize_currency, symbol as currency_symbol

boutique_bp = Blueprint('boutique', __name__)

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'pipeline', 'output', 'SmartWear_DB.json')
PER_PAGE = 24

_cache = None
_filters = None  # {'brands': [...], 'types': [...], 'cats': [...], 'styles': [...], 'sexes': [...]}
_cache_mtime = None   # dernière date de modification du JSON au moment du chargement
_scraping_in_progress = False
_cache_lock = threading.Lock()

# ── Filtres qualité produit ───────────────────────────────────────────────────

_CHILD_SEXE = frozenset(['fille', 'garçon', 'garcon'])

_NON_CLOTHING_STARTS = (
    # ── Éclairage ────────────────────────────────────────────────────
    'lampe', 'lampadaire', 'lustre', 'plafonnier', 'liseuse',
    'veilleuse', 'luminaire', 'abat-jour', 'bougie', 'bougies',
    'cierge', 'bougeoir', 'applique ', 'applique en', 'suspension ',
    # ── Vaisselle & cuisine ───────────────────────────────────────────
    'verre', 'assiette', 'tasse', 'mug', 'bol', 'coupe ', 'flûte ',
    'pichet', 'carafe', 'théière', 'cafetière', 'saladier',
    'couteau', 'cuillère', 'fourchette', 'sabre', 'couvert',
    'casserole', 'poêle', 'moule ', 'fouet ', 'spatule', 'passoire',
    'louche', 'râpe ', 'économe', 'ustensile', 'torchon', 'nappe',
    'plat ', 'plat à', 'cocotte', 'rouleau', 'ouvre-',
    'tire-bouchon', 'pince ',
    # ── Déco & maison ────────────────────────────────────────────────
    'coussin', 'vase', 'plateau', 'miroir', 'plaid', 'peluche',
    'canapé', 'plante', 'jouet', 'magnet', 'cadre', 'tableau',
    'sculpture', 'objet', 'outil ', 'panier', 'corbeille',
    'anneaux de', 'anneau de', 'rideau', 'rideaux',
    'poignée', 'crochet ', 'patère', 'porte-manteau',
    # ── Literie / linge de maison ─────────────────────────────────────
    'drap', 'drap-housse', 'taie', 'housse', 'couette', 'traversin',
    'oreiller', 'serviette',
    # ── Papeterie & livres ────────────────────────────────────────────
    'carnet', 'cahier', 'affiche', 'poster', 'stylo', 'crayon',
    'livre', 'crayons', 'jeu de', 'planche de stickers', 'agenda',
    # ── Audio / tech ─────────────────────────────────────────────────
    'enceinte ', 'haut-parleur',
    # ── Beauté / cosmétiques / parfumerie ─────────────────────────────
    'parfum ', "parfum d'intérieur",
    'eau de parfum', 'eau de cologne', 'eau de toilette',
    'diffuseur', 'savon', 'lotion', 'gel douche',
    'sérum ', 'élixir ', 'exfoliant', 'masque ', 'masque visage',
    'crème ', 'baume ', 'contour des yeux', 'huile corps',
    "huile d'", 'huile d', 'le sérum',
    'vernis ', 'fond de teint', 'trudon -',
    'rasoir ', 'rasoir anti', 'défriseur', 'repassage',
    'détachant', 'désodorisant', 'nettoyant ',
    # ── Alimentation / épicerie ───────────────────────────────────────
    'chocolat ', 'barre de chocolat', 'confiture', 'biscuit',
    'épices', 'sel de', 'miel ', 'sauce ', 'vinaigre', 'thé ',
    # ── Coffrets & sets ───────────────────────────────────────────────
    'coffret', 'lot de', 'lot 4', 'lot 12', 'set de',
    'duo de', 'ensemble de',
    # ── Vaisselle EN (bowl, cup, jar…) ───────────────────────────────
    'bowl', 'cup ', 'jar ', 'pot ', 'dish ',
    # ── Pins, bijoux non-vestimentaires ──────────────────────────────
    'badge ', 'badge merci', 'broche ',
    'médaille', 'medaille', 'collier ', 'bracelet ', 'bague ',
    'pendentif', 'médaillon', 'boucles d',
    # ── Maroquinerie ─────────────────────────────────────────────────
    'mallette', 'valise', 'portefeuille', 'porte-monnaie',
    # ── Divers ────────────────────────────────────────────────────────
    'adhésif bougie', 'boîte', 'boite', 'gourde', 'thermos',
)
_NON_CLOTHING_STARTS = _NON_CLOTHING_STARTS + ('gervasoni',)

_NON_CLOTHING_CONTAINS = (
    # Parfumerie / beauté apparaissant au milieu du nom
    'eau de parfum', 'eau de cologne', "parfum d'intérieur",
    'diffuseur parfumé', ' bougies', ' - bougie', ' - carnet',
    ' assiette', ' canapé', ' bowl', ' n°', '– lettres',
    'en verre soufflé', 'en porcelaine', 'en céramique',
    'en grès', 'en laiton', 'en lin lavé', 'en percale',
    # Maroquinerie au milieu du nom (format "Marque – Porte-clé – Couleur")
    'porte-clé', 'porte-clés', 'porte clé', 'keychain',
    'sac à dos', 'sac bandoulière',
    '– mallette', '– valise', '– portefeuille',
    '– vernis', '– parfum',
)

# Marques concept-stores : on rejette tout article sans style NI catégorie reconnus.
_CONCEPT_STORE_BRANDS = frozenset(['Merci'])


def _is_adult_clothing(p: dict) -> bool:
    """Retourne False pour les articles enfants ou non-vestimentaires."""
    if (p.get('sexe') or '').lower().strip() in _CHILD_SEXE:
        return False
    name = (p.get('name') or '').lower().strip()
    for kw in _NON_CLOTHING_STARTS:
        if name.startswith(kw):
            return False
    if re.search(r'\bmugs?\b', name):
        return False
    for kw in _NON_CLOTHING_CONTAINS:
        if kw in name:
            return False
    # Concept-stores : tout article sans style ET sans catégorie reconnus = non-vêtement
    if p.get('brand_source') in _CONCEPT_STORE_BRANDS:
        if (p.get('style') or 'Autre') == 'Autre' and (p.get('categorie') or 'Autre') == 'Autre':
            return False
    return True


def _run_scrape_background():
    global _scraping_in_progress
    try:
        from pipeline.run import run, SCRAPERS
        _logger.info("Auto-scrape démarré — DB boutique vide.")
        run(list(SCRAPERS.keys()))
        reset_boutique_cache()
        _logger.info("Auto-scrape terminé — cache boutique rechargé.")
    except Exception as exc:
        _logger.error("Auto-scrape échoué : %s", exc)
    finally:
        _scraping_in_progress = False


def _load_products():
    global _cache, _filters, _cache_mtime, _scraping_in_progress

    # Invalide le cache si le fichier JSON a été modifié depuis le dernier chargement
    try:
        current_mtime = os.path.getmtime(DB_PATH)
    except OSError:
        current_mtime = None

    if _cache is None or current_mtime != _cache_mtime:
        with _cache_lock:
            if _cache is None or current_mtime != _cache_mtime:
                try:
                    with open(DB_PATH, encoding='utf-8') as f:
                        raw = json.load(f)
                    _cache = [p for p in raw if _is_adult_clothing(p)]
                    _cache_mtime = current_mtime
                    from collections import Counter
                    brand_counts = Counter(p['brand_source'] for p in _cache if p.get('brand_source'))
                    _filters = {
                        'brands':       sorted(brand_counts.keys()),
                        'brand_counts': dict(brand_counts),
                        'types':        sorted({p['type']      for p in _cache if p.get('type')}),
                        'cats':         sorted({p['categorie'] for p in _cache if p.get('categorie')}),
                        'styles':       sorted({p['style']     for p in _cache if p.get('style')}),
                        'sexes':        sorted({p['sexe']      for p in _cache if p.get('sexe')}),
                    }
                except (FileNotFoundError, json.JSONDecodeError):
                    _cache = []
                    _cache_mtime = current_mtime
                    _filters = {'brands': [], 'brand_counts': {}, 'types': [], 'cats': [], 'styles': [], 'sexes': []}
    if not _cache and not _scraping_in_progress:
        _scraping_in_progress = True
        threading.Thread(target=_run_scrape_background, daemon=True).start()
    return _cache


def reset_boutique_cache():
    """Invalide le cache produit — à appeler après chaque scraping."""
    global _cache, _filters, _cache_mtime
    _cache = None
    _filters = None
    _cache_mtime = None


@boutique_bp.route('/boutique')
@login_required
def boutique():
    ctx = get_ctx()
    products = _load_products()

    # --- Devise utilisateur ---
    _cur_code = normalize_currency(ctx.get('currency', 'EUR'))
    _cur_rate  = get_rate(_cur_code)
    _cur_sym   = currency_symbol(_cur_code)

    # --- Catégories rapides (pills) ---
    QUICK_GROUPS = {
        'tshirts':   {'label': 'T-Shirts',          'icon': '👕', 'styles': ['T-shirt']},
        'shorts':    {'label': 'Shorts',             'icon': '🩳', 'styles': ['Short']},
        'pulls':     {'label': 'Pulls & Sweats',     'icon': '🧥', 'styles': ['Pull', 'Sweat', 'Hoodie', 'Cardigan', 'Crop-top']},
        'chemises':  {'label': 'Chemises & Polos',   'icon': '👔', 'styles': ['Chemise', 'Polo', 'Débardeur']},
        'pantalons': {'label': 'Pantalons & Jeans',  'icon': '👖', 'styles': ['Pantalon', 'Jean', 'Legging', 'Chinos']},
        'vestes':    {'label': 'Vestes & Blazers',   'icon': '🧣', 'styles': ['Veste', 'Blazer']},
        'manteaux':  {'label': 'Manteaux',           'icon': '🧤', 'styles': ['Manteau', 'Doudoune', 'Parka', 'Trench']},
        'robes':     {'label': 'Robes & Jupes',      'icon': '👗', 'styles': ['Robe', 'Jupe', 'Combinaison']},
        'chaussures':{'label': 'Chaussures',         'icon': '👟', 'styles': None},  # filtre par type
    }

    # --- Filtres ---
    q_search  = request.args.get('search', '').strip().lower()
    q_brands  = [v for v in request.args.getlist('brand')     if v]
    q_types   = [v for v in request.args.getlist('type')      if v]
    q_cats    = [v for v in request.args.getlist('categorie') if v]
    q_styles  = [v for v in request.args.getlist('style')     if v]
    q_sexes   = [v for v in request.args.getlist('sexe')      if v]
    q_group   = request.args.get('group', '')
    q_price_max = request.args.get('price_max', '', type=str).strip()
    try:
        price_max = float(q_price_max) if q_price_max else None
    except ValueError:
        price_max = None

    filtered = products
    if q_search:
        filtered = [p for p in filtered if q_search in (p.get('name') or '').lower()
                    or q_search in (p.get('description') or '').lower()]
    if q_brands:
        q_brands_set = set(q_brands)
        filtered = [p for p in filtered if p.get('brand_source') in q_brands_set]
    if q_types:
        filtered = [p for p in filtered if p.get('type') in q_types]
    if q_cats:
        filtered = [p for p in filtered if p.get('categorie') in q_cats]
    if q_styles:
        filtered = [p for p in filtered if p.get('style') in q_styles]
    if q_group and q_group in QUICK_GROUPS:
        grp_styles = QUICK_GROUPS[q_group]['styles']
        if grp_styles:
            filtered = [p for p in filtered if p.get('style') in grp_styles]
        else:
            filtered = [p for p in filtered if p.get('type') == 'Chaussures']
    if q_sexes:
        sexes_lower = {sx.lower() for sx in q_sexes} | {'mixte', 'unisexe'}
        filtered = [p for p in filtered if (p.get('sexe') or '').lower() in sexes_lower]
    if price_max is not None:
        price_max_eur = price_max / _cur_rate if _cur_rate and _cur_rate != 1.0 else price_max
        filtered = [p for p in filtered if p.get('price_value') is not None and p['price_value'] <= price_max_eur]

    total = len(filtered)

    # --- Pagination ---
    page = request.args.get('page', 1, type=int)
    if page < 1:
        page = 1
    total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    if page > total_pages:
        page = total_pages
    offset = (page - 1) * PER_PAGE
    page_items = apply_to_products(filtered[offset:offset + PER_PAGE], _cur_rate, _cur_sym)

    # --- Options de filtres (pré-calculées à l'init du cache) ---
    _flt = _filters or {}
    all_brands      = _flt.get('brands', [])
    brand_counts    = _flt.get('brand_counts', {})
    all_types       = _flt.get('types', [])
    all_cats        = _flt.get('cats', [])
    all_styles      = _flt.get('styles', [])
    all_sexes       = _flt.get('sexes', [])

    af = dict(
        search=request.args.get('search', ''),
        brands=q_brands,
        types=q_types,
        categories=q_cats,
        styles=q_styles,
        sexes=q_sexes,
        price_max=q_price_max,
        group=q_group,
    )

    me = ctx['me']
    wishlisted_urls = set()
    wishlist_count = 0
    if me:
        wl = WishlistItem.query.filter_by(user_id=me.id).with_entities(WishlistItem.product_url).all()
        wishlisted_urls = {row[0] for row in wl}
        wishlist_count = len(wishlisted_urls)

    wardrobe_items = []
    if me:
        wardrobe_items = [
            {
                'id': it.id,
                'name': it.name,
                'category': it.category,
                'color': it.color or '',
                'brand': it.brand or '',
                'ai_style': it.ai_style or '',
                'season': it.season or '',
                'thumb': it.thumb_path or it.image_path or '',
            }
            for it in me.items.order_by(ClothingItem.category, ClothingItem.name).all()
        ]

    return render_template(
        'boutique.html',
        items=page_items,
        total=total,
        page=page,
        total_pages=total_pages,
        af=af,
        all_brands=all_brands,
        brand_counts=brand_counts,
        quick_groups=QUICK_GROUPS,
        all_types=all_types,
        all_cats=all_cats,
        all_styles=all_styles,
        all_sexes=all_sexes,
        wardrobe_items=wardrobe_items,
        user_gender=me.gender if me else '',
        wishlisted_urls=wishlisted_urls,
        wishlist_count=wishlist_count,
        scraping_in_progress=_scraping_in_progress,
        user_currency_code=_cur_code,
        user_currency_sym=_cur_sym,
        **ctx,
    )


# ── Détection de slot ────────────────────────────────────────────────────────

_WARDROBE_SLOT = {
    'Hauts': 'top', 'T-shirts': 'top', 'Sport': 'top', 'Autre': 'top',
    'Pulls & Sweats': 'outer', 'Vestes & Manteaux': 'outer',
    'Pantalons': 'bottom', 'Jeans': 'bottom', 'Shorts': 'bottom',
    'Robes & Jupes': 'full',
    'Chaussures': 'shoes',
    'Accessoires': 'accessory',
}

_NEEDED_SLOTS = {
    'top':       ['bottom', 'shoes'],
    'outer':     ['top', 'bottom', 'shoes'],
    'bottom':    ['top', 'shoes'],
    'shoes':     ['top', 'bottom'],
    'full':      ['shoes'],
    'accessory': ['top', 'bottom'],
}

_SLOT_LABELS = {
    'top':   'haut (t-shirt, polo, chemise)',
    'outer': 'veste, sweat ou cardigan',
    'bottom': 'bas (pantalon, jean, short)',
    'shoes': 'chaussures',
}

_OUTER_KW     = ['veste', 'manteau', 'blouson', 'parka', 'doudoune', 'coupe-vent', 'bomber',
                  'trench', 'sweat', 'pull', 'cardigan', 'hoodie', 'polaire', 'gilet', 'zip']
_BOTTOM_KW    = ['pantalon', 'jean', 'short', 'bermuda', 'jogging', 'legging', 'cargo',
                  'chino', 'jupe', 'robe']
_SHOES_KW     = ['chaussure', 'sneaker', 'basket', 'boot', 'botte', 'mocassin', 'espadrille',
                  'sandal', 'running', 'jordan', 'air max', 'tennis shoe',
                  'footwear', 'trainer', 'loafer', 'derby', 'mule', 'ballerine', 'sabot']
_TOP_KW       = ['t-shirt', 'tshirt', 'polo', 'chemise', 'top', 'débardeur', 'haut', 'maillot']
_ACCESSORY_KW = ['pochette', 'sacoche', 'cabas', 'tote', 'portefeuille', 'porte-monnaie',
                  'ceinture', 'bracelet', 'collier', 'bague', 'montre', 'lunette',
                  'chapeau', 'bob ', 'bonnet', 'casquette', 'béret', 'écharpe', 'foulard',
                  'gant ', 'mitaine', 'sac à', 'sac de', 'backpack', 'wallet',
                  # Chaussettes & collants → accessoire, pas haut/bas
                  'chaussette', 'socquette', 'mi-chaussette', 'collant', 'bas résille']


# Marques qui ne vendent que des chaussures — slot forcé même si le nom ne contient
# aucun mot-clé chaussure (ex : "ALBATROSS 82", "Low Plain", "Dart")
_SHOE_ONLY_BRANDS = frozenset(['karhu', 'filling pieces'])


def _boutique_slot(p: dict) -> str:
    if (p.get('brand_source') or '').lower() in _SHOE_ONLY_BRANDS:
        return 'shoes'
    text = ' '.join(filter(None, [
        p.get('categorie', ''), p.get('type', ''), p.get('name', '')
    ])).lower()
    if any(k in text for k in _ACCESSORY_KW):
        return 'accessory'
    if any(k in text for k in _SHOES_KW):
        return 'shoes'
    if any(k in text for k in _BOTTOM_KW):
        return 'bottom'
    if any(k in text for k in _OUTER_KW):
        return 'outer'
    if any(k in text for k in _TOP_KW):
        return 'top'
    return 'top'


# ── Endpoint ─────────────────────────────────────────────────────────────────

@boutique_bp.route('/boutique/complete-wardrobe', methods=['POST'])
@login_required
def boutique_complete_wardrobe():
    try:
        return _complete_wardrobe_inner()
    except Exception as exc:
        import traceback
        import logging
        logging.getLogger(__name__).exception("boutique_complete_wardrobe crash")
        return jsonify(error=f"Erreur serveur : {str(exc)[:200]}"), 500


def _complete_wardrobe_inner():
    data    = request.get_json(force=True) or {}
    item_id = data.get('item_id')
    prompt  = data.get('prompt', '').strip()

    try:
        budget_max = float(data['budget_max']) if data.get('budget_max') else None
    except (TypeError, ValueError):
        budget_max = None

    if not item_id:
        return jsonify(error='Vêtement manquant'), 400

    me = current_user()
    item = me.items.filter_by(id=item_id).first()
    if not item:
        return jsonify(error='Vêtement introuvable'), 404

    # Devise utilisateur (pour filtre budget + affichage prix)
    from utils.auth import get_ctx as _get_ctx
    _ctx = _get_ctx()
    _cur_code = normalize_currency(_ctx.get('currency', 'EUR'))
    _cur_rate  = get_rate(_cur_code)
    _cur_sym   = currency_symbol(_cur_code)

    # budget_max est exprimé dans la devise utilisateur → convertir en EUR pour le filtre
    if budget_max is not None and _cur_rate and _cur_rate != 1.0:
        budget_max = budget_max / _cur_rate

    anchor_slot  = _WARDROBE_SLOT.get(item.category, 'top')
    needed_slots = _NEEDED_SLOTS.get(anchor_slot, ['top', 'bottom', 'shoes'])
    user_gender  = (me.gender or '').strip().lower()

    # Toujours filtrer : sexe de l'utilisateur + mixte + unisexe + vide
    # Si genre inconnu, on garde mixte/unisexe/vide uniquement
    _GENDER_SEXE = {'homme': 'homme', 'femme': 'femme'}
    gender_sexe = _GENDER_SEXE.get(user_gender)
    accepted = {'mixte', 'unisexe', ''}
    if gender_sexe:
        accepted.add(gender_sexe)

    products = _load_products()

    products = [
        p for p in products
        if (p.get('sexe') or '').lower() in accepted
    ]

    # Grouper par slot détecté
    by_slot: dict = {}
    for p in products:
        by_slot.setdefault(_boutique_slot(p), []).append(p)

    # Budget par pièce : on divise le total par le nombre de slots à compléter
    n_slots = len(needed_slots)
    per_piece_budget = (budget_max / n_slots) if budget_max and n_slots else None

    # Échantillonner : 8 articles par slot nécessaire
    slot_samples: dict = {}
    for slot in needed_slots:
        pool = by_slot.get(slot, [])
        if per_piece_budget is not None:
            pool = [p for p in pool if p.get('price_value') is not None and p['price_value'] <= per_piece_budget]
        if pool:
            slot_samples[slot] = random.sample(pool, min(8, len(pool)))

    if not slot_samples:
        return jsonify(error="Pas assez d'articles en boutique pour compléter cette tenue."), 400

    def _clean(s) -> str:
        return re.sub(r'[\x00-\x1f\x7f]', ' ', str(s or '')).strip()

    # Construire le catalogue par section avec indices globaux
    idx = 0
    idx_to_product: dict = {}
    sections = []
    for slot in needed_slots:
        prods = slot_samples.get(slot)
        if not prods:
            continue
        label = _SLOT_LABELS.get(slot, slot)
        lines = []
        for p in prods:
            price = f"{p['price_value']:.0f}€" if p.get('price_value') else 'N/A'
            lines.append(
                f"[{idx}] {_clean(p.get('name'))} | {_clean(p.get('color'))} | "
                f"{_clean(p.get('brand_source'))} | {price}"
            )
            idx_to_product[idx] = p
            idx += 1
        sections.append(f"=== {label.upper()} ===\n" + "\n".join(lines))

    anchor_desc = (
        f"{item.name} ({item.category}"
        + (f", {item.color}" if item.color else "")
        + (f", {item.ai_style}" if item.ai_style else "")
        + (f", {item.brand}" if item.brand else "") + ")"
    )
    needed_desc = " + ".join(_SLOT_LABELS.get(s, s) for s in needed_slots if s in slot_samples)

    # Format plat : une clé par slot avec l'entier entre crochets, plus facile à suivre pour le LLM
    slot_keys   = [s for s in needed_slots if s in slot_samples]
    example_ids = {s: i for i, s in enumerate(slot_keys)}
    example_json = json.dumps(
        {**{s: example_ids[s] for s in slot_keys}, "conseil": "explication courte"},
        ensure_ascii=False
    )

    system_msg = (
        "Tu es un conseiller mode expert. "
        "Tu dois choisir EXACTEMENT UN numéro par catégorie dans le catalogue. "
        "Utilise UNIQUEMENT les chiffres entre crochets [ ] comme valeurs. "
        f"Réponds UNIQUEMENT en JSON valide sans markdown, exemple : {example_json}"
    )
    user_msg = (
        f"Pièce existante : {anchor_desc}\n"
        f"Catégories à compléter : {needed_desc}\n"
        + (f"Budget total maximum pour la tenue : {budget_max:.0f}€ (environ {per_piece_budget:.0f}€ par pièce)\n" if budget_max else "")
        + (f"Style voulu : {prompt}\n" if prompt else "")
        + "\nCatalogue (retourne le chiffre entre [ ] pour chaque catégorie) :\n\n"
        + "\n\n".join(sections)
        + "\n\nRéponds avec le JSON uniquement :"
    )

    def _sanitize(s: str) -> str:
        return re.sub(r'[\x00-\x1f\x7f]', ' ', str(s)).strip()

    def _parse_llm_json(raw: str):
        # 1. Supprimer les blocs markdown ```json ... ```
        raw = re.sub(r'```(?:json)?\s*', '', raw).strip()
        raw = re.sub(r'```\s*$', '', raw).strip()
        # 2. Extraire entre le premier { et le dernier }
        start, end = raw.find('{'), raw.rfind('}')
        if start == -1 or end == -1:
            return None
        raw = raw[start:end + 1]
        # 3. Tentative directe
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
        # 4. Réparer virgule manquante entre valeur numérique et clé suivante
        fixed = re.sub(r'(\d)\s*\n\s*"', r'\1,\n"', raw)
        # 5. Supprimer virgule traînante avant } ou ]
        fixed = re.sub(r',\s*([}\]])', r'\1', fixed)
        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            pass
        # 6. Extraction regex slot par slot en dernier recours
        result = {}
        for key in ('top', 'outer', 'bottom', 'shoes', 'full', 'accessory', 'conseil'):
            m = re.search(rf'"{key}"\s*:\s*(\d+|"[^"]*")', raw)
            if m:
                val = m.group(1)
                try:
                    result[key] = int(val)
                except ValueError:
                    result[key] = val.strip('"')
        return result or None

    system_msg = _sanitize(system_msg)
    user_msg   = _sanitize(user_msg)

    try:
        import requests as req
        from ai.vision import OLLAMA_BASE, VISION_MODEL

        resp = req.post(
            f"{OLLAMA_BASE}/api/chat",
            json={
                "model": VISION_MODEL,
                "messages": [
                    {"role": "system", "content": system_msg},
                    {"role": "user",   "content": user_msg},
                ],
                "stream": False,
                "format": "json",
                "options": {"temperature": 0.15},
            },
            timeout=180,
        )
        resp.raise_for_status()
        raw = _sanitize(resp.json().get("message", {}).get("content", ""))
        result = _parse_llm_json(raw)
        if result is None:
            return jsonify(error="Réponse Ollama invalide (JSON introuvable)."), 500
    except Exception as exc:
        return jsonify(error=f"Ollama indisponible : {str(exc)[:120]}"), 500

    # Récupérer les produits sélectionnés dans l'ordre des slots
    selected = []
    seen_indices = set()
    for slot in needed_slots:
        raw_idx = result.get(slot)
        if raw_idx is None:
            continue
        try:
            i = int(raw_idx)
        except (TypeError, ValueError):
            continue
        if i in seen_indices or i not in idx_to_product:
            continue
        seen_indices.add(i)
        selected.append(idx_to_product[i])

    anchor_data = {
        'id': item.id, 'name': item.name, 'category': item.category,
        'color': item.color or '', 'brand': item.brand or '',
        'thumb': item.thumb_path or item.image_path or '',
    }
    selected_converted = apply_to_products(selected, _cur_rate, _cur_sym)
    return jsonify(conseil=result.get('conseil', ''), products=selected_converted, anchor=anchor_data, currency_sym=_cur_sym)


# ── Ajout d'un article boutique à la garde-robe ──────────────────────────────

_STATIC_DIR = Path(__file__).parent.parent / 'static'


def _download_image(url: str, user_id: int):
    """Télécharge l'image distante et retourne le chemin relatif (ex. uploads/3/boutique_abc.jpg)."""
    try:
        import requests as req
        dest_dir = _STATIC_DIR / 'uploads' / str(user_id)
        dest_dir.mkdir(parents=True, exist_ok=True)
        ext = url.split('?')[0].rsplit('.', 1)[-1][:5].lower()
        if ext not in {'jpg', 'jpeg', 'png', 'webp', 'gif'}:
            ext = 'jpg'
        filename = f"boutique_{uuid.uuid4().hex[:12]}.{ext}"
        r = req.get(url, timeout=15, stream=True, headers={'User-Agent': 'Mozilla/5.0'})
        r.raise_for_status()
        with open(dest_dir / filename, 'wb') as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)
        return f"uploads/{user_id}/{filename}"
    except Exception:
        return None


@boutique_bp.route('/boutique/add-to-wardrobe', methods=['POST'])
@login_required
def boutique_add_to_wardrobe():
    data = request.get_json(force=True) or {}
    me = current_user()

    name = (data.get('name') or '').strip()[:120]
    if not name:
        return jsonify(error='Nom manquant'), 400

    category  = (data.get('categorie') or data.get('category') or 'Autre')[:60]
    brand     = (data.get('brand_source') or data.get('brand') or '')[:80] or None
    color     = (data.get('color') or '')[:40] or None
    ai_style  = (data.get('style') or '')[:40] or None
    price_val = data.get('price_value')
    image_url = data.get('image') or ''
    source_url = data.get('url') or ''

    notes_parts = []
    if data.get('description'):
        notes_parts.append(data['description'][:300])
    if source_url:
        notes_parts.append(f"Source boutique : {source_url}")
    notes = '\n\n'.join(notes_parts) or None

    image_path = _download_image(image_url, me.id) if image_url else None

    item = ClothingItem(
        user_id=me.id,
        name=name,
        category=category,
        brand=brand,
        color=color,
        price=float(price_val) if price_val else None,
        notes=notes,
        image_path=image_path,
        ai_style=ai_style,
    )
    db.session.add(item)
    db.session.commit()
    return jsonify(ok=True, item_id=item.id, name=item.name)


# ── Wishlist ──────────────────────────────────────────────────────────────────

@boutique_bp.route('/boutique/wishlist/toggle', methods=['POST'])
@login_required
def boutique_wishlist_toggle():
    data = request.get_json(force=True) or {}
    url = (data.get('url') or '').strip()
    if not url:
        return jsonify(error='URL manquante'), 400

    me = current_user()
    all_urls = [w.product_url for w in WishlistItem.query.filter_by(user_id=me.id).all()]
    _logger.info("TOGGLE user=%s url=%r stored_count=%d url_in_stored=%s", me.id, url, len(all_urls), url in all_urls)
    existing = WishlistItem.query.filter_by(user_id=me.id, product_url=url).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()
        _logger.info("TOGGLE supprimé id=%s", existing.id)
        return jsonify(wishlisted=False)

    snapshot = {k: data.get(k) for k in [
        'name', 'price_value', 'currency', 'color', 'brand_source',
        'image', 'url', 'type', 'categorie', 'style', 'sexe', 'description',
        'taille', 'sizes', 'rating',
    ]}
    try:
        initial_price = float(snapshot.get('price_value')) if snapshot.get('price_value') is not None else None
    except (TypeError, ValueError):
        initial_price = None
    w = WishlistItem(
        user_id=me.id,
        product_url=url,
        product_json=json.dumps(snapshot, ensure_ascii=False),
        last_known_price=initial_price,
    )
    db.session.add(w)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify(wishlisted=True)
    return jsonify(wishlisted=True)


@boutique_bp.route('/boutique/wishlist')
@login_required
def boutique_wishlist_page():
    ctx = get_ctx()
    me = ctx['me']
    rows = WishlistItem.query.filter_by(user_id=me.id).order_by(WishlistItem.added_at.desc()).all()

    # ── Détection des baisses de prix ────────────────────────────────────────
    current_prices = {p['url']: p.get('price_value') for p in _load_products() if p.get('url')}
    dropped = []
    changed = False
    for row in rows:
        if not row.price_alert or row.last_known_price is None:
            continue
        raw = current_prices.get(row.product_url)
        try:
            current_price = float(raw) if raw is not None else None
        except (TypeError, ValueError):
            current_price = None
        if current_price is not None and current_price < row.last_known_price:
            product = json.loads(row.product_json)
            dropped.append({
                'name': product.get('name', row.product_url),
                'old_price': row.last_known_price,
                'new_price': current_price,
                'currency': product.get('currency', '€'),
            })
        if current_price is not None:
            row.last_known_price = current_price
            changed = True
    if changed:
        db.session.commit()
    if dropped and me.email_verified:
        from utils.mail import send_price_alert_email
        send_price_alert_email(me, dropped)

    # Devise utilisateur pour l'affichage
    _cur_code = normalize_currency(ctx.get('currency', 'EUR'))
    _cur_rate  = get_rate(_cur_code)
    _cur_sym   = currency_symbol(_cur_code)

    products = apply_to_products([json.loads(w.product_json) for w in rows], _cur_rate, _cur_sym)

    # Convertir aussi les montants dans les alertes de baisse
    if dropped and _cur_rate != 1.0:
        dropped = [
            {**d, 'old_price': round(d['old_price'] * _cur_rate, 2),
                  'new_price': round(d['new_price'] * _cur_rate, 2),
                  'currency': _cur_sym}
            for d in dropped
        ]
    elif dropped:
        dropped = [{**d, 'currency': _cur_sym} for d in dropped]

    wishlisted_urls = {w.product_url for w in rows}
    return render_template(
        'wishlist.html',
        products=products,
        total=len(products),
        wishlisted_urls=wishlisted_urls,
        price_drops=dropped,
        user_currency_sym=_cur_sym,
        **ctx,
    )
