import base64
import os
import time
import urllib.parse
import uuid
from io import BytesIO

import requests
from PIL import Image
from flask import current_app

from config import (
    ANTHROPIC_MODEL,
    BASE_DIR,
    OUTFIT_FOLDER,
    POLLINATIONS_ENHANCE,
    POLLINATIONS_FIXED_SEED,
    POLLINATIONS_HEIGHT,
    POLLINATIONS_MODEL,
    POLLINATIONS_SAFE,
    POLLINATIONS_WIDTH,
)


def _clean_text(value):
    if not value:
        return ''
    return ' '.join(
        str(value)
        .replace('/', ' ')
        .replace('\\', ' ')
        .replace('|', ' ')
        .replace('\n', ' ')
        .replace('\r', ' ')
        .split()
    ).strip()


def _normalize_category(cat):
    cat = _clean_text(cat).lower()
    mapping = {
        'hauts': 'top',
        't-shirts': 't-shirt',
        'pulls & sweats': 'sweatshirt',
        'vestes & manteaux': 'jacket',
        'pantalons': 'pants',
        'jeans': 'jeans',
        'shorts': 'shorts',
        'robes & jupes': 'dress or skirt',
        'chaussures': 'shoes',
        'accessoires': 'accessories',
        'sous-vêtements': 'underwear',
        'sport': 'sportswear',
        'autre': 'garment',
    }
    return mapping.get(cat, cat if cat else 'garment')


def _normalize_color(color):
    color = _clean_text(color).lower()
    mapping = {
        'blanc': 'white', 'noir': 'black', 'gris': 'gray', 'beige': 'beige',
        'marron': 'brown', 'camel': 'camel', 'rouge': 'red', 'rose': 'pink',
        'orange': 'orange', 'jaune': 'yellow', 'vert': 'green', 'bleu': 'blue',
        'violet': 'purple', 'multicolore': 'multicolor', 'imprimé': 'printed',
        'marine': 'navy', 'bordeaux': 'burgundy', 'kaki': 'khaki',
        'écru': 'ecru', 'crème': 'cream', 'ivoire': 'ivory',
        'anthracite': 'charcoal', 'taupe': 'taupe', 'nude': 'nude',
    }
    return mapping.get(color, color)


def _normalize_length(length):
    length = _clean_text(length).lower()
    mapping = {
        'court': 'short', 'mi-long': 'mid-length', 'long': 'long',
        'très long': 'full-length', 'maxi': 'maxi', 'midi': 'midi',
        'mini': 'mini', 'crop': 'cropped', 'cropped': 'cropped',
        'ankle': 'ankle-length', 'knee': 'knee-length',
    }
    return mapping.get(length, length)


def _normalize_season(season):
    season = _clean_text(season).lower()
    mapping = {
        'printemps': 'spring',
        'été': 'summer',
        'automne': 'autumn',
        'hiver': 'winter',
        'toutes saisons': 'all-season',
    }
    return mapping.get(season, season)


def _normalize_occasion(occasion):
    occasion = _clean_text(occasion).lower()
    mapping = {
        'quotidien': 'everyday casual wear',
        'travail': 'smart workwear',
        'soirée': 'evening outfit',
        'sport': 'sport outfit',
        'voyage': 'travel outfit',
        'cérémonie': 'formal ceremony outfit',
        'autre': 'fashion styling',
    }
    return mapping.get(occasion, occasion)


_MATERIAL_TEXTURE_MAP = {
    'denim': 'realistic denim texture',
    'jean': 'realistic denim texture',
    'wool': 'realistic knit wool texture',
    'laine': 'realistic knit wool texture',
    'knit': 'realistic knit texture',
    'maille': 'realistic knit texture',
    'leather': 'realistic leather texture',
    'cuir': 'realistic leather texture',
    'cotton': 'realistic cotton texture',
    'coton': 'realistic cotton texture',
    'silk': 'realistic silk texture',
    'soie': 'realistic silk texture',
    'linen': 'realistic linen texture',
    'lin': 'realistic linen texture',
    'synthetic': 'realistic synthetic fabric texture',
    'polyester': 'realistic synthetic fabric texture',
    'velvet': 'realistic velvet texture',
    'velours': 'realistic velvet texture',
    'suede': 'realistic suede texture',
    'nylon': 'realistic nylon texture',
    'fleece': 'realistic fleece texture',
}

_FIT_MAP = {
    'slim': 'slim fit',
    'skinny': 'skinny fit',
    'regular': 'regular fit',
    'oversized': 'oversized fit',
    'oversize': 'oversized fit',
    'relaxed': 'relaxed fit',
    'loose': 'loose fit',
    'tapered': 'tapered fit',
    'cropped': 'cropped cut',
    'fitted': 'fitted silhouette',
}

_SHOE_SUBCATS = {'shoe', 'sneaker', 'boot', 'loafer', 'sandal', 'mule', 'oxford', 'derby', 'moccasin', 'espadrille'}

_CATEGORY_LAYER_LABEL = {
    'T-shirts':         'T-SHIRT',
    'Hauts':            'TOP',
    'Pulls & Sweats':   'SWEATER',
    'Vestes & Manteaux':'JACKET',
    'Pantalons':        'PANTS',
    'Jeans':            'JEANS',
    'Shorts':           'SHORTS',
    'Robes & Jupes':    'DRESS',
    'Chaussures':       'SHOES',
    'Accessoires':      'ACCESSORY',
    'Sport':            'SPORT TOP',
    'Sous-vêtements':   'UNDERWEAR',
}


def _is_shoe_item(it) -> bool:
    cat = _normalize_category(it.category)
    sub = _clean_text(getattr(it, 'ai_subcategory', '') or '').lower()
    return 'shoe' in cat or 'chaussure' in it.category.lower() or any(k in sub for k in _SHOE_SUBCATS)


def _item_visual_token(it) -> str:
    """Builds the richest possible visual description for one garment item."""
    ai_analyzed = getattr(it, 'ai_analyzed', False)
    ai_description = _clean_text(getattr(it, 'ai_description', '') or '')
    ai_subcategory = _clean_text(getattr(it, 'ai_subcategory', '') or '').lower()
    ai_material = _clean_text(getattr(it, 'ai_material', '') or '').lower()
    ai_pattern = _clean_text(getattr(it, 'ai_pattern', '') or '').lower()
    ai_fit = _clean_text(getattr(it, 'ai_fit', '') or '').lower()
    ai_length = _normalize_length(getattr(it, 'ai_length', '') or '')
    ai_secondary_color = _normalize_color(getattr(it, 'ai_secondary_color', '') or '')
    # Prefer AI-detected color (always up-to-date) over user-set color
    color = _normalize_color(getattr(it, 'ai_color', '') or it.color or '')
    category = _normalize_category(it.category)
    brand = _clean_text(it.brand)

    # Shoes with AI analysis: ai_description IS the Flux image_gen_prompt — use verbatim
    if _is_shoe_item(it) and ai_analyzed and ai_description:
        return ai_description

    # Build structured token for all other items
    parts = []
    if color:
        if ai_secondary_color and ai_secondary_color != color:
            parts.append(f'{color} and {ai_secondary_color}')
        else:
            parts.append(color)

    garment_type = ai_subcategory if ai_subcategory else category
    if ai_pattern and ai_pattern not in ('plain', 'solid', 'uni', 'none', ''):
        garment_type = f'{ai_pattern}-patterned {garment_type}'
    parts.append(garment_type)

    if ai_material:
        texture = _MATERIAL_TEXTURE_MAP.get(ai_material, '')
        if texture:
            parts.append(texture.replace('realistic ', '').replace(' texture', ''))
        else:
            parts.append(ai_material)

    if ai_fit:
        parts.append(_FIT_MAP.get(ai_fit, ai_fit))

    if ai_length and ai_length not in ('regular', 'standard', 'mi-long', ''):
        parts.append(f'{ai_length}-length')

    if brand:
        parts.append(f'by {brand}')

    return ' '.join(parts).strip() or category


DECOR_PROMPTS = {
    'studio':      'white seamless studio background, soft box lighting, e-commerce product photography',
    'rue':         'urban street background, city sidewalk, natural daylight, editorial fashion photography',
    'nature':      'outdoor nature setting, green park, soft diffused natural light',
    'cafe':        'cozy parisian cafe interior, warm ambient lighting, blurred bokeh background',
    'appartement': 'modern minimalist apartment interior, living room, natural window light',
    'plage':       'beach setting, golden sand, ocean horizon, bright natural sunlight',
    'bureau':      'modern office interior, professional environment, clean background',
    'nuit':        'night city background, bokeh street lights, evening atmosphere, dramatic lighting',
}


def build_prompt(outfit, person_mode=False, decor=None, gender='Homme'):
    garments = []
    has_shoes = False
    texture_hints = set()
    style_hints = set()

    for it in _sorted_outfit_items(outfit):
        token = _item_visual_token(it)
        if token:
            layer_label = _CATEGORY_LAYER_LABEL.get(it.category, 'ITEM')
            garments.append(f'[{layer_label}] {token}')

        ai_subcategory = _clean_text(getattr(it, 'ai_subcategory', '') or '').lower()
        ai_style = _clean_text(getattr(it, 'ai_style', '') or '').lower()
        ai_material = _clean_text(getattr(it, 'ai_material', '') or '').lower()

        if _is_shoe_item(it):
            has_shoes = True

        if ai_style:
            style_hints.add(f'{ai_style} styling')

        for keyword, texture_label in _MATERIAL_TEXTURE_MAP.items():
            if keyword in ai_material:
                texture_hints.add(texture_label)
                break

    garments_text = ', '.join(garments) if garments else 'modern coordinated casual outfit'
    occasion_text = _normalize_occasion(outfit.occasion) if outfit.occasion else 'fashion lookbook'
    season_text = _normalize_season(outfit.season) if outfit.season else 'all-season'
    texture_parts = sorted(texture_hints) if texture_hints else ['realistic fabric textures']
    style_parts = sorted(style_hints) if style_hints else ['coherent modern styling']
    footwear_part = 'shoes on feet' if has_shoes else 'complete footwear visible'

    background = DECOR_PROMPTS.get(decor, decor) if decor else 'white seamless background, soft box lighting'
    is_female = gender.lower() in ('femme', 'female', 'woman', 'f')
    gender_subject = 'woman' if is_female else 'man'
    gender_adj = 'feminine' if is_female else 'masculine'
    fashion_label = "women's fashion" if is_female else "men's fashion"

    if person_mode:
        return (
            f"Keep the exact same person from the reference photo — preserve their face, hair, skin tone, and body shape identically. "
            f"Replace ALL their clothing with these exact garments: {garments_text}. "
            f"{', '.join(texture_parts)}, {', '.join(style_parts)}. "
            f"Full body, front view, head to toe, {footwear_part}. "
            f"{background}. "
            f"Occasion: {occasion_text}, season: {season_text}. "
            f"Photorealistic, 8K, sharp focus, accurate garment colors, preserve face identity completely."
        )

    return (
        f"ghost mannequin product photography, invisible mannequin, front view, full body, "
        f"two arms visible, arms slightly away from body, two legs, symmetrical upright posture, "
        f"{fashion_label} e-commerce, {background}, "
        f"{garments_text}, "
        f"{', '.join(texture_parts)}, {', '.join(style_parts)}, "
        f"{occasion_text}, {season_text}, "
        f"accurate garment shapes and colors, sharp fabric details, 8K, photorealistic, "
        f"no visible person, no skin, no face, floating clothes effect"
    )


def build_negative_prompt(person_mode=False, gender='Homme'):
    base = (
        'blurry, low quality, low resolution, jpeg artifacts, compression artifacts, '
        'overexposed, underexposed, bad lighting, harsh shadows, cluttered background, '
        'text, watermark, logo, signature, '
        'bad anatomy, deformed body, wrong proportions, extra limbs, missing limbs, '
        'missing arms, no arms, armless, fused arms, merged arms, arms hidden, arms behind back, '
        'missing legs, no legs, fused legs, '
        'floating garments, '
        'wrong garment color, color shift, inaccurate colors, missing garment, extra clothing, '
        'duplicate clothing, warped clothes, unrealistic fabric, incorrect pattern, '
        'floating fabric, wrinkle artifacts, '
        'cropped feet, partial body, side view, back view, '
        'sitting pose, lying down, bent body, '
    )
    if person_mode:
        return base + (
            'different person, changed face, changed hair, altered skin tone, '
            'ugly face, deformed face, distorted face, bad face, disfigured, '
            'cartoon, anime, illustration, painting, sketch, '
            'multiple people, two people, group, crowd'
        )
    return base + (
        'person, human, body, face, head, skin, visible model, '
        'flat lay, overhead view, top-down, '
        'wrong garment shape, wrong cut, wrong silhouette, '
        'multiple separate items, messy arrangement'
    )


def _build_claude_garment_context(outfit):
    """Construit la liste détaillée des vêtements pour le contexte Claude."""
    lines = []
    for it in _sorted_outfit_items(outfit):
        parts = []
        layer_label = _CATEGORY_LAYER_LABEL.get(it.category, 'ITEM')
        parts.append(f'layer: {layer_label}')
        # Use AI-detected color first (more accurate), fall back to user-set color
        color = _clean_text(getattr(it, 'ai_color', '') or it.color or '')
        if color:
            parts.append(f'color: {color}')
        ai_secondary = _clean_text(getattr(it, 'ai_secondary_color', '') or '')
        if ai_secondary and ai_secondary.lower() != color.lower():
            parts.append(f'secondary color: {ai_secondary}')
        category = _normalize_category(it.category)
        ai_sub = _clean_text(getattr(it, 'ai_subcategory', '') or '')
        parts.append(f'type: {ai_sub if ai_sub else category}')
        ai_material = _clean_text(getattr(it, 'ai_material', '') or '')
        if ai_material:
            parts.append(f'material: {ai_material}')
        ai_pattern = _clean_text(getattr(it, 'ai_pattern', '') or '')
        if ai_pattern and ai_pattern.lower() not in ('plain', 'solid', 'uni'):
            parts.append(f'pattern: {ai_pattern}')
        ai_fit = _clean_text(getattr(it, 'ai_fit', '') or '')
        if ai_fit:
            parts.append(f'fit: {ai_fit}')
        ai_length = _clean_text(getattr(it, 'ai_length', '') or '')
        if ai_length and ai_length.lower() not in ('regular', 'standard'):
            parts.append(f'length: {ai_length}')
        ai_desc = _clean_text(getattr(it, 'ai_description', '') or '')
        if ai_desc:
            # For shoes: ai_description IS the Flux image_gen_prompt — preserve fully
            if _is_shoe_item(it):
                parts.append(f'flux_visual_prompt: {ai_desc}')
            else:
                parts.append(f'details: {ai_desc[:160]}')
        brand = _clean_text(it.brand)
        if brand:
            parts.append(f'brand: {brand}')
        lines.append('• ' + ', '.join(parts))
    return '\n'.join(lines)


def generate_prompt_with_claude(outfit, api_key=None, person_mode=False, decor=None, gender='Homme'):
    if not api_key:
        api_key = os.environ.get('ANTHROPIC_API_KEY', '').strip()
    if not api_key:
        return build_prompt(outfit, person_mode=person_mode, decor=decor, gender=gender), None

    is_female = gender.lower() in ('femme', 'female', 'woman', 'f')
    gender_subject = 'woman' if is_female else 'man'
    fashion_label = "women's fashion" if is_female else "men's fashion"
    gender_adj = 'feminine' if is_female else 'masculine'
    opposite_gender_rule = 'NEVER male — NEVER multiple people' if is_female else 'NEVER female — NEVER multiple people'

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        garment_context = _build_claude_garment_context(outfit)
        occasion_text = _normalize_occasion(outfit.occasion) if outfit.occasion else 'fashion lookbook'
        season_text = _normalize_season(outfit.season) if outfit.season else 'all-season'
        outfit_notes = f'\nOutfit notes: {_clean_text(outfit.description)}' if outfit.description else ''

        background_text = DECOR_PROMPTS.get(decor, decor) if decor else 'white seamless studio background, soft box lighting'

        if person_mode:
            subject_rules = (
                '- TASK: Edit the reference photo — keep the EXACT same person (same face, hair, skin tone, body shape, pose)\n'
                '- Replace ALL clothing in the reference with the garments listed below\n'
                '- Do NOT change the person\'s appearance in any way\n'
                '- Full body, front view, head to toe\n'
                '- Quality: photorealistic, 8K, sharp focus, preserve face identity\n'
            )
        else:
            subject_rules = (
                f'- Style: ghost mannequin / invisible mannequin product photography, front view, full body\n'
                f'- {fashion_label} e-commerce\n'
                '- Two arms MUST be visible, slightly away from body — two legs MUST be visible — symmetrical upright posture\n'
                '- NO visible person, NO skin, NO face — floating clothes effect\n'
                '- Reproduce EXACT garment shapes, cuts, and details as described\n'
                '- Quality: photorealistic, 8K, sharp fabric textures, accurate colors\n'
            )

        message = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=500,
            messages=[{
                'role': 'user',
                'content': (
                    'You are an expert fashion image prompt engineer for FLUX diffusion models.\n'
                    'Write ONE English image generation prompt, comma-separated descriptors, max 160 words.\n\n'
                    'RULES:\n'
                    + subject_rules +
                    f'- Background: {background_text}\n'
                    '- MANDATORY: describe EVERY garment listed — no item may be omitted or generalized\n'
                    '- For EACH garment: prefix with its layer label (e.g. "[PANTS]"), then state exact color, material, silhouette, and key visual details\n'
                    '- For any item with a "flux_visual_prompt:" field: insert that text VERBATIM for that item\n'
                    '- Layer order in prompt: shoes → pants/skirt → top → outerwear\n'
                    '- Be visually precise — no poetic or abstract language\n'
                    '- Reply ONLY with the prompt, no explanation, no markdown, no quotes\n\n'
                    f'Occasion: {occasion_text} | Season: {season_text}{outfit_notes}\n\n'
                    f'Garments:\n{garment_context}'
                )
            }]
        )
        return message.content[0].text.strip(), None
    except Exception as exc:
        current_app.logger.warning(f'Claude API error: {exc} — using fallback prompt')
        return build_prompt(outfit, person_mode=person_mode, decor=decor, gender=gender), None


def _encode_shoe_reference(outfit):
    """Retourne (item, jpeg_bytes) de la première chaussure avec image, sinon (None, None)."""
    shoe_categories = {'chaussures', 'shoes', 'shoe'}
    for it in outfit.items:
        cat = _clean_text(it.category).lower()
        ai_sub = _clean_text(getattr(it, 'ai_subcategory', '') or '').lower()
        is_shoe = (
            cat in shoe_categories
            or 'chaussure' in cat
            or 'shoe' in ai_sub
            or 'sneaker' in ai_sub
            or 'boot' in ai_sub
            or 'loafer' in ai_sub
            or 'sandal' in ai_sub
        )
        if not is_shoe:
            continue
        img_rel = it.thumb_path or it.image_path
        if not img_rel:
            continue
        abs_path = os.path.join(BASE_DIR, 'static', img_rel)
        if not os.path.isfile(abs_path):
            continue
        try:
            buf = BytesIO()
            Image.open(abs_path).convert('RGB').save(buf, 'JPEG', quality=85)
            return it, buf.getvalue()
        except Exception:
            continue
    return None, None


_LAYER_ORDER = [
    'Accessoires', 'Vestes & Manteaux', 'Pulls & Sweats', 'Hauts', 'T-shirts',
    'Sport', 'Robes & Jupes', 'Pantalons', 'Jeans', 'Shorts',
    'Sous-vêtements', 'Chaussures', 'Autre',
]


def _sorted_outfit_items(outfit):
    """Retourne les articles triés tête → pieds selon _LAYER_ORDER."""
    # Charger tous les items une seule fois pour éviter les problèmes de lazy-loading
    all_items = list(outfit.items)
    order_map = {cat: i for i, cat in enumerate(_LAYER_ORDER)}
    return sorted(all_items, key=lambda it: order_map.get(it.category, len(_LAYER_ORDER)))


def _build_outfit_composite(outfit):
    """
    Collage vertical tête→pieds — priorité aux thumb_path (article isolé).
    Rendu : 2 colonnes, fond blanc, padding entre cellules, portrait.
    """
    items = _sorted_outfit_items(outfit)
    cells = []
    for it in items:
        # Priorité au thumb (article seul) ; image_path peut contenir un mannequin habillé
        img_rel = it.thumb_path or it.image_path
        if not img_rel:
            continue
        abs_path = os.path.join(BASE_DIR, 'static', img_rel)
        if not os.path.isfile(abs_path):
            continue
        try:
            cells.append(Image.open(abs_path).convert('RGB'))
        except Exception as exc:
            current_app.logger.warning(f'Cannot load image for item {it.id}: {exc}')
            continue

    current_app.logger.info(f'_build_outfit_composite: {len(items)} items, {len(cells)} with photos')
    if not cells:
        return None

    CELL = 480        # taille de chaque vignette
    PAD  = 16         # espacement entre vignettes
    BG   = (250, 250, 250)

    resized = []
    for img in cells:
        img.thumbnail((CELL, CELL), Image.LANCZOS)
        cell = Image.new('RGB', (CELL, CELL), BG)
        cell.paste(img, ((CELL - img.width) // 2, (CELL - img.height) // 2))
        resized.append(cell)

    # 2 colonnes sauf pour 1 article seul
    cols = 1 if len(resized) == 1 else 2
    rows = (len(resized) + cols - 1) // cols

    W = cols * CELL + (cols + 1) * PAD
    H = rows * CELL + (rows + 1) * PAD
    composite = Image.new('RGB', (W, H), BG)
    for i, cell in enumerate(resized):
        r, c = divmod(i, cols)
        x = PAD + c * (CELL + PAD)
        y = PAD + r * (CELL + PAD)
        composite.paste(cell, (x, y))

    buf = BytesIO()
    composite.save(buf, 'JPEG', quality=92)
    return buf.getvalue()


def _save_composite_as_outfit(composite_bytes):
    """Sauvegarde le composite PIL directement comme image de tenue. Retourne le chemin relatif."""
    os.makedirs(OUTFIT_FOLDER, exist_ok=True)
    filename = f'{uuid.uuid4().hex}.jpg'
    path = os.path.join(OUTFIT_FOLDER, filename)
    with open(path, 'wb') as f:
        f.write(composite_bytes)
    return f'uploads/outfits/{filename}'


def _save_pollinations_response(resp):
    """Sauvegarde la réponse image Pollinations en JPEG. Retourne le chemin relatif."""
    os.makedirs(OUTFIT_FOLDER, exist_ok=True)
    filename = f'{uuid.uuid4().hex}.jpg'
    path = os.path.join(OUTFIT_FOLDER, filename)
    Image.open(BytesIO(resp.content)).convert('RGB').save(path, 'JPEG', quality=92, optimize=True)
    return f'uploads/outfits/{filename}'


def _is_public_url(url):
    """Vérifie que l'URL est accessible publiquement (pas localhost)."""
    return bool(url) and not any(h in url for h in ('localhost', '127.0.0.1', '0.0.0.0'))


def _generate_with_kontext_url(prompt, image_url, seed, encoded_negative, headers, label='ref'):
    """
    Génère via FLUX.1-Kontext (GET) avec une image de référence passée par URL publique.
    Nouveau format API Pollinations — remplace les anciens appels multipart POST.
    """
    params = {
        'width': POLLINATIONS_WIDTH,
        'height': POLLINATIONS_HEIGHT,
        'seed': seed,
        'model': 'kontext',
        'enhance': 'false',
        'safe': 'true' if POLLINATIONS_SAFE else 'false',
        'negative_prompt': urllib.parse.unquote(encoded_negative),
        'nologo': 'true',
        'image': image_url,
    }
    encoded_prompt = urllib.parse.quote(prompt, safe='')
    url = f'https://enter.pollinations.ai/prompt/{encoded_prompt}'
    current_app.logger.info(
        f'Kontext GET ({label}) | img={image_url[:70]} | size={POLLINATIONS_WIDTH}x{POLLINATIONS_HEIGHT} | seed={seed}'
    )
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=300)
        current_app.logger.info(
            f'Kontext {label} response: {resp.status_code}, content-type: {resp.headers.get("content-type")}'
        )
        if not resp.ok:
            current_app.logger.warning(f'Kontext {label} error {resp.status_code}: {resp.text[:400]}')
            return None, f'Kontext {resp.status_code}'
        ct = (resp.headers.get('content-type') or '').lower()
        if 'image' not in ct:
            return None, f'Kontext réponse invalide ({ct})'
        return _save_pollinations_response(resp), None
    except requests.Timeout:
        current_app.logger.warning(f'Kontext {label} timeout')
        return None, f'Kontext {label} timeout'
    except Exception as exc:
        current_app.logger.error(f'Kontext {label} error: {exc}')
        return None, str(exc)


def _generate_local_a1111(prompt, negative_prompt, url, checkpoint, width, height, seed):
    """Génération locale via AUTOMATIC1111 (txt2img API)."""
    payload = {
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "width": width,
        "height": height,
        "steps": 25,
        "cfg_scale": 7.0,
        "sampler_name": "DPM++ 2M Karras",
        "seed": int(seed) if str(seed).isdigit() else -1,
    }
    if checkpoint:
        payload["override_settings"] = {"sd_model_checkpoint": checkpoint}
    try:
        resp = requests.post(f"{url.rstrip('/')}/sdapi/v1/txt2img", json=payload, timeout=300)
        resp.raise_for_status()
        images = resp.json().get("images", [])
        if not images:
            return None, "A1111 n'a retourné aucune image."
        img_bytes = base64.b64decode(images[0])
        os.makedirs(OUTFIT_FOLDER, exist_ok=True)
        filename = f'{uuid.uuid4().hex}.jpg'
        path = os.path.join(OUTFIT_FOLDER, filename)
        Image.open(BytesIO(img_bytes)).convert('RGB').save(path, 'JPEG', quality=92, optimize=True)
        return f'uploads/outfits/{filename}', None
    except requests.ConnectionError:
        return None, "AUTOMATIC1111 inaccessible. Vérifiez que le serveur tourne sur l'URL configurée."
    except requests.Timeout:
        return None, "AUTOMATIC1111 timeout — génération trop longue."
    except Exception as exc:
        current_app.logger.error(f'A1111 error: {exc}')
        return None, str(exc)


def _generate_local_comfyui(prompt, negative_prompt, url, checkpoint, width, height, seed):
    """Génération locale via ComfyUI (workflow KSampler minimal)."""
    int_seed = int(seed) if str(seed).isdigit() else uuid.uuid4().int % 999999
    workflow = {
        "1": {"inputs": {"ckpt_name": checkpoint or "v1-5-pruned-emaonly.safetensors"}, "class_type": "CheckpointLoaderSimple"},
        "2": {"inputs": {"text": prompt, "clip": ["1", 1]}, "class_type": "CLIPTextEncode"},
        "3": {"inputs": {"text": negative_prompt, "clip": ["1", 1]}, "class_type": "CLIPTextEncode"},
        "4": {"inputs": {"width": width, "height": height, "batch_size": 1}, "class_type": "EmptyLatentImage"},
        "5": {
            "inputs": {
                "seed": int_seed, "steps": 25, "cfg": 7.0,
                "sampler_name": "dpmpp_2m", "scheduler": "karras", "denoise": 1.0,
                "model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0], "latent_image": ["4", 0],
            },
            "class_type": "KSampler",
        },
        "6": {"inputs": {"samples": ["5", 0], "vae": ["1", 2]}, "class_type": "VAEDecode"},
        "7": {"inputs": {"filename_prefix": "wardrobe", "images": ["6", 0]}, "class_type": "SaveImage"},
    }
    try:
        base = url.rstrip('/')
        r = requests.post(f"{base}/prompt", json={"prompt": workflow}, timeout=30)
        r.raise_for_status()
        prompt_id = r.json()["prompt_id"]
    except requests.ConnectionError:
        return None, "ComfyUI inaccessible. Vérifiez que le serveur tourne sur l'URL configurée."
    except Exception as exc:
        return None, f"ComfyUI erreur soumission : {exc}"

    deadline = time.time() + 300
    while time.time() < deadline:
        time.sleep(3)
        try:
            history = requests.get(f"{base}/history/{prompt_id}", timeout=10).json()
        except Exception:
            continue
        if prompt_id not in history:
            continue
        for node_out in history[prompt_id].get("outputs", {}).values():
            for img_info in node_out.get("images", []):
                try:
                    img_resp = requests.get(
                        f"{base}/view",
                        params={"filename": img_info["filename"], "subfolder": img_info.get("subfolder", ""), "type": img_info.get("type", "output")},
                        timeout=30,
                    )
                    os.makedirs(OUTFIT_FOLDER, exist_ok=True)
                    filename = f'{uuid.uuid4().hex}.jpg'
                    path = os.path.join(OUTFIT_FOLDER, filename)
                    Image.open(BytesIO(img_resp.content)).convert('RGB').save(path, 'JPEG', quality=92, optimize=True)
                    return f'uploads/outfits/{filename}', None
                except Exception as exc:
                    return None, f"ComfyUI erreur récupération image : {exc}"
    return None, "ComfyUI timeout — génération trop longue (> 5 min)."


def generate_image(prompt, api_key=None, outfit=None, image_model=None, local_url=None, local_checkpoint=None, face_path=None, person_mode=False, public_base_url=None, gender='Homme'):
    clean_prompt = ' '.join(str(prompt).split()).strip()

    # Kontext (image-to-image) is unavailable — "keep same person" prompt passed to text-only
    # flux generates a woman. Override with ghost mannequin prompt so the outfit is correct.
    if person_mode and outfit:
        clean_prompt = build_prompt(outfit, person_mode=False, gender=gender)
        person_mode = False
        current_app.logger.info('person_mode: Kontext unavailable — overriding with ghost mannequin prompt')

    negative_prompt = build_negative_prompt(person_mode=person_mode, gender=gender)
    encoded_negative = urllib.parse.quote(negative_prompt, safe='')

    seed = POLLINATIONS_FIXED_SEED if POLLINATIONS_FIXED_SEED else str(uuid.uuid4().int % 99999)
    if not api_key:
        api_key = os.environ.get('POLLINATIONS_API_KEY', '').strip()

    headers = {'User-Agent': 'Wardrobe/5.0'}
    if api_key:
        headers['Authorization'] = f'Bearer {api_key}'

    effective_model = image_model if image_model else POLLINATIONS_MODEL

    # Génération locale (A1111 ou ComfyUI)
    if effective_model in ('local-a1111', 'local-comfyui'):
        negative_prompt = build_negative_prompt(gender=gender)
        local_base = (local_url or 'http://localhost:7860').rstrip('/')
        current_app.logger.info(
            f'Local generation | provider={effective_model} | url={local_base} '
            f'| checkpoint={local_checkpoint or "default"}'
        )
        if effective_model == 'local-a1111':
            return _generate_local_a1111(
                clean_prompt, negative_prompt, local_base,
                local_checkpoint, POLLINATIONS_WIDTH, POLLINATIONS_HEIGHT, seed,
            )
        else:
            return _generate_local_comfyui(
                clean_prompt, negative_prompt, local_base,
                local_checkpoint, POLLINATIONS_WIDTH, POLLINATIONS_HEIGHT, seed,
            )

    # Toujours essayer flux text-only en premier — le composite PIL n'est qu'un fallback
    # (le composite montre les photos produits d'origine, pas une vraie image générée)

    # Génération standard — deux endpoints selon qu'une clé est fournie ou non
    # gen.pollinations.ai  → endpoint authentifié (requis si api_key)
    # image.pollinations.ai → endpoint public gratuit (fallback sans clé)
    encoded_prompt = urllib.parse.quote(clean_prompt, safe='')

    def _build_url(use_auth_endpoint: bool) -> str:
        base_params = (
            f'?width={POLLINATIONS_WIDTH}'
            f'&height={POLLINATIONS_HEIGHT}'
            f'&seed={seed}'
            f'&model={effective_model}'
            f"&enhance={'true' if POLLINATIONS_ENHANCE else 'false'}"
            f"&safe={'true' if POLLINATIONS_SAFE else 'false'}"
            f'&nologo=true'
        )
        if use_auth_endpoint:
            return f'https://gen.pollinations.ai/image/{encoded_prompt}{base_params}&negative_prompt={encoded_negative}'
        return f'https://image.pollinations.ai/prompt/{encoded_prompt}{base_params}'

    def _attempt(use_auth: bool, hdrs: dict):
        u = _build_url(use_auth)
        endpoint_name = 'gen.pollinations.ai' if use_auth else 'image.pollinations.ai'
        current_app.logger.info(
            f'Calling {endpoint_name} | model={effective_model} '
            f'| size={POLLINATIONS_WIDTH}x{POLLINATIONS_HEIGHT} '
            f"| seed={seed} | key={'yes' if bool(api_key) else 'no'}"
        )
        return requests.get(u, timeout=300, headers=hdrs)

    try:
        # Premier essai : endpoint authentifié si clé dispo, public sinon
        resp = _attempt(use_auth=bool(api_key), hdrs=headers)
        current_app.logger.info(
            f"Pollinations response: {resp.status_code}, content-type: {resp.headers.get('content-type')}"
        )

        # Si 401/403 (auth refusée), réessai sur l'endpoint public sans clé
        if resp.status_code in (401, 403) and api_key:
            current_app.logger.warning(
                f'Pollinations auth error {resp.status_code} — retrying without key on public endpoint'
            )
            fallback_headers = {'User-Agent': 'Wardrobe/5.0'}
            resp = _attempt(use_auth=False, hdrs=fallback_headers)
            current_app.logger.info(
                f"Pollinations fallback response: {resp.status_code}, content-type: {resp.headers.get('content-type')}"
            )

        if not resp.ok:
            body = ''
            try:
                body = resp.text[:800]
            except Exception:
                pass
            current_app.logger.error(f'Pollinations error {resp.status_code}: {body}')
            if resp.status_code == 402:
                return None, (
                    f'Solde Pollinations insuffisant pour le modèle « {effective_model} ». '
                    'Changez de modèle dans Paramètres IA (choisissez Flux — gratuit) '
                    'ou rechargez votre solde sur pollinations.ai.'
                )
            if resp.status_code in (401, 403):
                return None, (
                    'Génération d\'image refusée par Pollinations. '
                    'Vérifiez votre clé API dans Paramètres IA ou laissez le champ vide pour utiliser la version gratuite.'
                )
            return None, f'Erreur Pollinations {resp.status_code} — réessayez dans quelques instants.'

        ct = (resp.headers.get('content-type') or '').lower()
        if 'image' not in ct:
            body = ''
            try:
                body = resp.text[:800]
            except Exception:
                pass
            current_app.logger.error(f'Unexpected content-type={ct}, body={body}')
            return None, f'Réponse invalide de Pollinations ({ct})'

        os.makedirs(OUTFIT_FOLDER, exist_ok=True)
        filename = f'{uuid.uuid4().hex}.jpg'
        path = os.path.join(OUTFIT_FOLDER, filename)
        img = Image.open(BytesIO(resp.content)).convert('RGB')
        img.save(path, 'JPEG', quality=92, optimize=True)
        return f'uploads/outfits/{filename}', None
    except requests.Timeout:
        current_app.logger.warning('Pollinations timeout — falling back to PIL composite')
    except requests.RequestException as exc:
        current_app.logger.error(f'HTTP request error during image generation: {exc} — falling back to PIL composite')
    except Exception as exc:
        current_app.logger.error(f'Image generation error: {exc} — falling back to PIL composite')

    # Fallback final : composite PIL des vraies photos (si flux a échoué ou timeout)
    if outfit:
        try:
            composite = _build_outfit_composite(outfit)
            if composite:
                current_app.logger.info('Flux failed — using PIL photo composite as fallback')
                return _save_composite_as_outfit(composite), None
        except Exception as exc:
            current_app.logger.error(f'PIL composite fallback also failed: {exc}')

    return None, 'Génération échouée. Vérifiez votre connexion et réessayez.'
