"""
routes/boutique.py
Page "Boutique" — affiche les produits scrapés depuis SmartWear_DB.json
"""
import json
import os

from flask import Blueprint, render_template, request

from utils.auth import get_ctx, login_required

boutique_bp = Blueprint('boutique', __name__)

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'pipeline', 'output', 'SmartWear_DB.json')
PER_PAGE = 24

_cache = None


def _load_products():
    global _cache
    if _cache is None:
        try:
            with open(DB_PATH, encoding='utf-8') as f:
                _cache = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            _cache = []
    return _cache


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
        **ctx,
    )
