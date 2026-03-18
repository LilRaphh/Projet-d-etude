import os
import urllib.parse
import uuid
from io import BytesIO

import requests
from PIL import Image
from flask import current_app

from config import (
    ANTHROPIC_MODEL,
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


def build_prompt(outfit):
    garments = []
    has_shoes = False
    texture_hints = set()
    style_hints = set()

    for it in outfit.items:
        color = _clean_text(it.color).lower()
        category = _normalize_category(it.category)
        brand = _clean_text(it.brand)
        name = _clean_text(it.name)
        notes = _clean_text(it.notes).lower()

        token_parts = []
        if color:
            token_parts.append(color)
        token_parts.append(category)
        if brand:
            token_parts.append(f'by {brand}')
        if name:
            token_parts.append(f'model {name}')

        garment_text = ' '.join(token_parts).strip()
        garments.append(garment_text)

        if 'shoe' in category:
            has_shoes = True
        if any(x in notes for x in ['denim', 'jean']):
            texture_hints.add('realistic denim texture')
        if any(x in notes for x in ['laine', 'wool', 'maille', 'knit']):
            texture_hints.add('realistic knit texture')
        if any(x in notes for x in ['cuir', 'leather']):
            texture_hints.add('realistic leather texture')
        if any(x in notes for x in ['coton', 'cotton']):
            texture_hints.add('realistic cotton texture')
        if any(x in notes for x in ['oversize', 'oversized']):
            style_hints.add('balanced oversized fit')
        if any(x in notes for x in ['cargo']):
            style_hints.add('modern utility styling')
        if any(x in notes for x in ['minimal', 'sobre', 'clean']):
            style_hints.add('minimal clean styling')

    garments_text = ', '.join(garments) if garments else 'modern coordinated casual outfit'
    occasion_text = _normalize_occasion(outfit.occasion) if outfit.occasion else 'fashion lookbook styling'
    season_text = _normalize_season(outfit.season) if outfit.season else 'all-season'
    texture_text = ', '.join(sorted(texture_hints)) if texture_hints else 'realistic cotton, denim, knit and leather textures'
    style_text = ', '.join(sorted(style_hints)) if style_hints else 'coherent modern styling'
    footwear_text = 'matching premium footwear visible' if has_shoes else 'complete outfit styling with appropriate footwear visible'

    return (
    f"Realistic full-body fashion studio photograph of a premium male fashion mannequin wearing {garments_text}. "
    f"Outfit purpose: {occasion_text}. Season: {season_text}. "
    "Straight front view, mannequin standing naturally, centered composition, entire body visible from head to toe, "
    "hands visible, feet visible, realistic proportions, elegant retail display mannequin, smooth matte surface, "
    "high-end fashion store mannequin, no wooden mannequin, no articulated artist dummy. "
    "Clean white seamless studio background, soft diffused professional studio lighting, "
    "premium e-commerce fashion photography, high-end editorial lookbook. "
    f"{texture_text}, {style_text}, accurate garment layering, accurate colors, "
    f"{footwear_text}, sharp focus, ultra detailed, realistic fabrics, natural folds, no visage."
    )


def build_negative_prompt():
    return (
        'blurry, low quality, low resolution, jpeg artifacts, bad anatomy, bad hands, '
        'extra fingers, extra limbs, duplicate clothing, duplicate body parts, deformed body, '
        'cropped head, cropped feet, missing shoes, floating garments, unrealistic fabric, '
        'wrong proportions, warped clothes, distorted face, bad lighting, overexposed, '
        'underexposed, cluttered background, text, watermark, logo, multiple mannequins, '
        'side view, back view, sitting pose, bent body, unrealistic shadows'
    )


def generate_prompt_with_claude(outfit, api_key=None):
    if not api_key:
        api_key = os.environ.get('ANTHROPIC_API_KEY', '').strip()
    if not api_key:
        return build_prompt(outfit), None

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        desc = build_prompt(outfit)
        notes = f"\nAdditional notes: {_clean_text(outfit.description)}" if outfit.description else ''

        message = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=350,
            messages=[{
                'role': 'user',
                'content': (
                    'Generate one single English image-generation prompt for a realistic fashion photo. '
                    'The subject must be a male mannequin wearing the described outfit. '
                    'White seamless studio background. Full body, front view, head-to-toe visible. '
                    'Keep it specific, concise, and optimized for photorealistic fashion generation. '
                    'Reply ONLY with the prompt, no quotes, no markdown.\n\n'
                    f'Base description: {desc}{notes}'
                )
            }]
        )
        return message.content[0].text.strip(), None
    except Exception as exc:
        current_app.logger.warning(f'Claude API error: {exc} — using fallback prompt')
        return build_prompt(outfit), None


def generate_image(prompt, api_key=None):
    clean_prompt = ' '.join(str(prompt).split()).strip()
    negative_prompt = build_negative_prompt()
    encoded_prompt = urllib.parse.quote(clean_prompt, safe='')
    encoded_negative = urllib.parse.quote(negative_prompt, safe='')

    seed = POLLINATIONS_FIXED_SEED if POLLINATIONS_FIXED_SEED else str(uuid.uuid4().int % 99999)
    if not api_key:
        api_key = os.environ.get('POLLINATIONS_API_KEY', '').strip()

    url = (
        f'https://gen.pollinations.ai/image/{encoded_prompt}'
        f'?width={POLLINATIONS_WIDTH}'
        f'&height={POLLINATIONS_HEIGHT}'
        f'&seed={seed}'
        f'&model={POLLINATIONS_MODEL}'
        f"&enhance={'true' if POLLINATIONS_ENHANCE else 'false'}"
        f"&safe={'true' if POLLINATIONS_SAFE else 'false'}"
        f'&negative_prompt={encoded_negative}'
    )

    headers = {'User-Agent': 'Wardrobe/5.0'}
    if api_key:
        headers['Authorization'] = f'Bearer {api_key}'

    current_app.logger.info(
        f'Calling Pollinations | model={POLLINATIONS_MODEL} '
        f'| size={POLLINATIONS_WIDTH}x{POLLINATIONS_HEIGHT} '
        f"| seed={seed} | key={'yes' if bool(api_key) else 'no'}"
    )

    try:
        resp = requests.get(url, timeout=120, headers=headers)
        current_app.logger.info(
            f"Pollinations response: {resp.status_code}, content-type: {resp.headers.get('content-type')}"
        )

        if not resp.ok:
            body = ''
            try:
                body = resp.text[:800]
            except Exception:
                pass
            current_app.logger.error(f'Pollinations error body: {body}')
            return None, f'Erreur Pollinations {resp.status_code}'

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
        return None, 'Timeout — Pollinations a mis trop de temps. Réessayez.'
    except requests.RequestException as exc:
        current_app.logger.error(f'HTTP request error during image generation: {exc}')
        return None, 'Erreur réseau pendant la génération.'
    except Exception as exc:
        current_app.logger.error(f'Image generation error: {exc}')
        return None, str(exc)
