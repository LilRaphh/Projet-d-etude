"""
routes/boutique.py
Page "Boutique" — affiche les produits scrapés depuis SmartWear_DB.json
"""
import json
import os
import random
import re
import uuid
from pathlib import Path

from flask import Blueprint, jsonify, render_template, request

from extensions import db
from models import ClothingItem, WishlistItem
from utils.auth import current_user, get_ctx, login_required

boutique_bp = Blueprint('boutique', __name__)

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'pipeline', 'output', 'SmartWear_DB.json')
PER_PAGE = 24

_cache = None

# ── Filtres qualité produit ───────────────────────────────────────────────────

_CHILD_SEXE = frozenset(['fille', 'garçon', 'garcon'])

_NON_CLOTHING_STARTS = (
    # Bougies & éclairage
    'bougie', 'bougies', 'cierge', 'bougeoir', 'lampe', 'suspension',
    # Vaisselle & cuisine
    'tasse', 'assiette', 'verre', 'couteau', 'cuillère', 'fourchette',
    'sabre', 'bol', 'pichet', 'carafe', 'théière', 'cafetière',
    'torchon', 'nappe', 'serviette',
    # Déco & maison
    'coussin', 'drap', 'taie', 'housse', 'vase', 'plateau', 'peluche',
    'canapé', 'miroir', 'plaid', 'plante', 'gourde', 'jouet', 'magnet',
    # Papeterie & livres
    'carnet', 'affiche', 'stylo', 'livre', 'crayons', 'jeu de',
    'planche de stickers', 'poster',
    # Beauté & parfumerie
    'diffuseur', 'parfum ', 'eau de parfum', 'eau de cologne',
    'trudon -', 'savon', 'lotion', 'gel douche', 'le sérum',
    "huile d'", 'huile d',
    # Coffrets & sets maison
    'coffret', 'lot de', 'lot 4', 'lot 12', 'set de',
    'duo de bougies', 'ensemble de',
    # Divers
    'adhésif bougie', 'adhesif bougie', 'boîte', 'boite',
)
_NON_CLOTHING_STARTS = _NON_CLOTHING_STARTS + ('gervasoni',)

_NON_CLOTHING_CONTAINS = (
    'eau de parfum', 'eau de cologne', "parfum d'intérieur",
    'diffuseur parfumé', ' bougies', ' - bougie', ' - carnet',
    ' assiette', ' canapé',
)


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
    return True


def _load_products():
    global _cache
    if _cache is None:
        try:
            with open(DB_PATH, encoding='utf-8') as f:
                raw = json.load(f)
            _cache = [p for p in raw if _is_adult_clothing(p)]
        except (FileNotFoundError, json.JSONDecodeError):
            _cache = []
    return _cache


def reset_boutique_cache():
    """Invalide le cache produit — à appeler après chaque scraping."""
    global _cache
    _cache = None


@boutique_bp.route('/boutique')
@login_required
def boutique():
    ctx = get_ctx()
    products = _load_products()

    # --- Filtres ---
    q_search = request.args.get('search', '').strip().lower()
    q_brand  = request.args.get('brand', '')
    q_type   = request.args.get('type', '')
    q_cat    = request.args.get('categorie', '')
    q_style  = request.args.get('style', '')
    q_sexe   = request.args.get('sexe', '')
    q_price_max = request.args.get('price_max', '', type=str).strip()
    try:
        price_max = float(q_price_max) if q_price_max else None
    except ValueError:
        price_max = None

    filtered = products
    if q_search:
        filtered = [p for p in filtered if q_search in (p.get('name') or '').lower()
                    or q_search in (p.get('description') or '').lower()]
    if q_brand:
        filtered = [p for p in filtered if p.get('brand_source') == q_brand]
    if q_type:
        filtered = [p for p in filtered if p.get('type') == q_type]
    if q_cat:
        filtered = [p for p in filtered if p.get('categorie') == q_cat]
    if q_style:
        filtered = [p for p in filtered if p.get('style') == q_style]
    if q_sexe:
        filtered = [p for p in filtered if p.get('sexe') == q_sexe]
    if price_max is not None:
        filtered = [p for p in filtered if p.get('price_value') is not None and p['price_value'] <= price_max]

    total = len(filtered)

    # --- Pagination ---
    page = request.args.get('page', 1, type=int)
    if page < 1:
        page = 1
    total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    if page > total_pages:
        page = total_pages
    offset = (page - 1) * PER_PAGE
    page_items = filtered[offset:offset + PER_PAGE]

    # --- Options de filtres (valeurs présentes dans les données) ---
    all_brands  = sorted({p['brand_source'] for p in products if p.get('brand_source')})
    all_types   = sorted({p['type'] for p in products if p.get('type')})
    all_cats    = sorted({p['categorie'] for p in products if p.get('categorie')})
    all_styles  = sorted({p['style'] for p in products if p.get('style')})
    all_sexes   = sorted({p['sexe'] for p in products if p.get('sexe')})

    af = dict(
        search=request.args.get('search', ''),
        brand=q_brand, type=q_type, categorie=q_cat,
        style=q_style, sexe=q_sexe, price_max=q_price_max,
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
        all_types=all_types,
        all_cats=all_cats,
        all_styles=all_styles,
        all_sexes=all_sexes,
        wardrobe_items=wardrobe_items,
        user_gender=me.gender if me else '',
        wishlisted_urls=wishlisted_urls,
        wishlist_count=wishlist_count,
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
    'top':       ['bottom', 'shoes', 'outer'],
    'outer':     ['top', 'bottom', 'shoes'],
    'bottom':    ['top', 'shoes', 'outer'],
    'shoes':     ['top', 'bottom', 'outer'],
    'full':      ['shoes', 'outer'],
    'accessory': ['top', 'bottom', 'shoes'],
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
                  'sandal', 'running', 'jordan', 'air max', 'tennis shoe']
_TOP_KW       = ['t-shirt', 'tshirt', 'polo', 'chemise', 'top', 'débardeur', 'haut', 'maillot']
_ACCESSORY_KW = ['pochette', 'sacoche', 'cabas', 'tote', 'portefeuille', 'porte-monnaie',
                  'ceinture', 'bracelet', 'collier', 'bague', 'montre', 'lunette',
                  'chapeau', 'bob ', 'bonnet', 'casquette', 'béret', 'écharpe', 'foulard',
                  'gant ', 'mitaine', 'sac à', 'sac de', 'backpack', 'wallet']


def _boutique_slot(p: dict) -> str:
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

    anchor_slot  = _WARDROBE_SLOT.get(item.category, 'top')
    needed_slots = _NEEDED_SLOTS.get(anchor_slot, ['top', 'bottom', 'shoes'])
    user_gender  = (me.gender or '').strip()

    # Valeurs acceptées par genre (inclut variantes enfant + mixte + vide)
    _GENDER_ACCEPT = {
        'Homme': {'homme', 'mixte', 'unisexe', ''},
        'Femme': {'femme',  'mixte', 'unisexe', ''},
    }
    accepted = _GENDER_ACCEPT.get(user_gender)

    products = _load_products()

    if accepted is not None:
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
            timeout=60,
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
    return jsonify(conseil=result.get('conseil', ''), products=selected, anchor=anchor_data)


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
    existing = WishlistItem.query.filter_by(user_id=me.id, product_url=url).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()
        return jsonify(wishlisted=False)

    snapshot = {k: data.get(k) for k in [
        'name', 'price_value', 'currency', 'color', 'brand_source',
        'image', 'url', 'type', 'categorie', 'style', 'sexe', 'description',
        'taille', 'sizes', 'rating',
    ]}
    w = WishlistItem(
        user_id=me.id,
        product_url=url,
        product_json=json.dumps(snapshot, ensure_ascii=False),
    )
    db.session.add(w)
    db.session.commit()
    return jsonify(wishlisted=True)


@boutique_bp.route('/boutique/wishlist')
@login_required
def boutique_wishlist_page():
    ctx = get_ctx()
    me = ctx['me']
    rows = WishlistItem.query.filter_by(user_id=me.id).order_by(WishlistItem.added_at.desc()).all()
    products = [json.loads(w.product_json) for w in rows]
    wishlisted_urls = {w.product_url for w in rows}
    return render_template(
        'wishlist.html',
        products=products,
        total=len(products),
        wishlisted_urls=wishlisted_urls,
        **ctx,
    )
