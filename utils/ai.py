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


def build_prompt(outfit):
    garments = []
    has_shoes = False
    texture_hints = set()
    style_hints = set()
    fit_hints = set()
    pattern_hints = set()

    for it in outfit.items:
        color = _normalize_color(it.color)
        category = _normalize_category(it.category)
        brand = _clean_text(it.brand)
        notes = _clean_text(it.notes).lower()

        # Champs IA — prioritaires sur les notes textuelles
        ai_subcategory = _clean_text(getattr(it, 'ai_subcategory', '') or '').lower()
        ai_material = _clean_text(getattr(it, 'ai_material', '') or '').lower()
        ai_pattern = _clean_text(getattr(it, 'ai_pattern', '') or '').lower()
        ai_fit = _clean_text(getattr(it, 'ai_fit', '') or '').lower()
        ai_style = _clean_text(getattr(it, 'ai_style', '') or '').lower()
        ai_secondary_color = _normalize_color(getattr(it, 'ai_secondary_color', '') or '')
        ai_length = _normalize_length(getattr(it, 'ai_length', '') or '')
        ai_description = _clean_text(getattr(it, 'ai_description', '') or '')
        ai_analyzed = getattr(it, 'ai_analyzed', False)

        # Construction du token de vêtement
        token_parts = []
        if color:
            color_token = color
            if ai_secondary_color and ai_secondary_color != color:
                color_token += f' and {ai_secondary_color}'
            token_parts.append(color_token)

        # Préférer la sous-catégorie IA (plus précise) à la catégorie générique
        garment_type = ai_subcategory if ai_subcategory else category
        if ai_pattern and ai_pattern not in ('plain', 'solid', 'uni'):
            garment_type = f'{ai_pattern} {garment_type}'
        token_parts.append(garment_type)

        if ai_fit:
            mapped_fit = _FIT_MAP.get(ai_fit, ai_fit)
            token_parts.append(mapped_fit)
            fit_hints.add(mapped_fit)
        if ai_length and ai_length not in ('regular', 'standard'):
            token_parts.append(f'{ai_length}-length')

        if brand:
            token_parts.append(f'by {brand}')

        garment_text = ' '.join(token_parts).strip()

        # Si la description IA est disponible, extraire les détails visuels clés
        # (on ne prend pas la description brute pour ne pas noyer le prompt)
        if ai_analyzed and ai_description:
            # Extraire max 2 adjectifs visuels pertinents depuis la description
            desc_words = ai_description.lower().split()
            visual_keywords = [
                w for w in desc_words
                if w in {
                    'distressed', 'washed', 'faded', 'embroidered', 'printed',
                    'ribbed', 'cable-knit', 'quilted', 'waxed', 'raw', 'hem',
                    'tapered', 'flared', 'pleated', 'button-up', 'zip-up',
                    'hooded', 'crewneck', 'turtleneck', 'v-neck', 'collarless',
                    'double-breasted', 'single-breasted', 'patch', 'cargo',
                    'elasticated', 'drawstring',
                }
            ]
            if visual_keywords:
                garment_text = f'{", ".join(visual_keywords[:2])} {garment_text}'

        garments.append(garment_text)

        # Catégorie chaussures
        if 'shoe' in category or 'shoe' in garment_type or 'sneaker' in garment_type or 'boot' in garment_type:
            has_shoes = True

        # Textures — source IA prioritaire, fallback sur les notes
        material_source = ai_material if ai_material else notes
        for keyword, texture_label in _MATERIAL_TEXTURE_MAP.items():
            if keyword in material_source:
                texture_hints.add(texture_label)
                break  # une texture par vêtement suffit

        # Hints de style
        if ai_style:
            style_hints.add(f'{ai_style} styling')
        else:
            if any(x in notes for x in ['oversize', 'oversized']):
                style_hints.add('balanced oversized fit')
            if any(x in notes for x in ['cargo']):
                style_hints.add('modern utility styling')
            if any(x in notes for x in ['minimal', 'sobre', 'clean']):
                style_hints.add('minimal clean styling')

        # Patterns globaux
        if ai_pattern and ai_pattern not in ('plain', 'solid', 'uni', ''):
            pattern_hints.add(ai_pattern)

    garments_text = ' | '.join(garments) if garments else 'modern coordinated casual outfit'
    occasion_text = _normalize_occasion(outfit.occasion) if outfit.occasion else 'fashion lookbook'
    season_text = _normalize_season(outfit.season) if outfit.season else 'all-season'
    texture_parts = sorted(texture_hints) if texture_hints else ['realistic fabric textures']
    style_parts = sorted(style_hints) if style_hints else ['coherent modern styling']
    pattern_part = f', {", ".join(sorted(pattern_hints))} pattern' if pattern_hints else ''
    footwear_part = 'shoes on feet' if has_shoes else 'complete footwear visible'

    # Prompt compact orienté Flux : sujet → vêtements → contexte → qualité
    # Les virgules séparant les tokens sont comprises nativement par Flux/SDXL
    return (
        f"full body studio fashion photo, male clothing mannequin, front view, head to toe, "
        f"{garments_text}, "
        f"{', '.join(texture_parts)}{pattern_part}, "
        f"{', '.join(style_parts)}, "
        f"{occasion_text}, {season_text}, {footwear_part}, "
        "white seamless background, soft box lighting, accurate garment colors, "
        "e-commerce product photography, photorealistic, 8K, sharp focus, "
        "no face, no skin, matte mannequin surface"
    )


def build_negative_prompt():
    return (
        # Qualité générale
        'blurry, low quality, low resolution, jpeg artifacts, compression artifacts, '
        'overexposed, underexposed, bad lighting, harsh shadows, cluttered background, '
        'text, watermark, logo, signature, '
        # Anatomie / corps
        'face, skin, human face, visible skin, human model, person, realistic human, '
        'bad anatomy, deformed body, wrong proportions, extra limbs, missing limbs, '
        'floating garments, '
        # Vêtements
        'wrong garment color, color shift, inaccurate colors, missing garment, extra clothing, '
        'duplicate clothing, warped clothes, unrealistic fabric, incorrect pattern, '
        'floating fabric, wrinkle artifacts, '
        # Pose / cadrage
        'cropped head, cropped feet, partial body, side view, back view, '
        'sitting pose, lying down, bent body, tilted mannequin, '
        # Mannequin
        'wooden mannequin, articulated dummy, toy figure, CGI dummy, '
        'multiple mannequins, ghost mannequin'
    )


def _build_claude_garment_context(outfit):
    """Construit la liste détaillée des vêtements pour le contexte Claude."""
    lines = []
    for it in outfit.items:
        parts = []
        color = _clean_text(it.color)
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
            parts.append(f'details: {ai_desc[:120]}')
        brand = _clean_text(it.brand)
        if brand:
            parts.append(f'brand: {brand}')
        lines.append('• ' + ', '.join(parts))
    return '\n'.join(lines)


def generate_prompt_with_claude(outfit, api_key=None):
    if not api_key:
        api_key = os.environ.get('ANTHROPIC_API_KEY', '').strip()
    if not api_key:
        return build_prompt(outfit), None

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        garment_context = _build_claude_garment_context(outfit)
        occasion_text = _normalize_occasion(outfit.occasion) if outfit.occasion else 'fashion lookbook'
        season_text = _normalize_season(outfit.season) if outfit.season else 'all-season'
        outfit_notes = f'\nOutfit notes: {_clean_text(outfit.description)}' if outfit.description else ''

        message = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=400,
            messages=[{
                'role': 'user',
                'content': (
                    'You are a fashion image prompt engineer specializing in FLUX diffusion models.\n'
                    'Write ONE English image generation prompt, comma-separated keywords, max 120 words.\n\n'
                    'RULES:\n'
                    '- Subject: male clothing mannequin (no face, no skin, matte surface)\n'
                    '- Shot: full body, front view, head to toe, white seamless studio background\n'
                    '- Lighting: soft box studio lighting\n'
                    '- Style: e-commerce product photography, photorealistic, 8K, sharp focus\n'
                    '- Describe EACH garment with its EXACT color, material, fit, and distinctive details\n'
                    '- Respect the garment layer order (bottom to top)\n'
                    '- End with quality tags: photorealistic, sharp focus, accurate colors\n'
                    '- Reply ONLY with the prompt, no quotes, no markdown, no explanation\n\n'
                    f'Occasion: {occasion_text} | Season: {season_text}{outfit_notes}\n\n'
                    f'Garments to wear:\n{garment_context}'
                )
            }]
        )
        return message.content[0].text.strip(), None
    except Exception as exc:
        current_app.logger.warning(f'Claude API error: {exc} — using fallback prompt')
        return build_prompt(outfit), None


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


def _save_pollinations_response(resp):
    """Sauvegarde la réponse image Pollinations en JPEG. Retourne le chemin relatif."""
    os.makedirs(OUTFIT_FOLDER, exist_ok=True)
    filename = f'{uuid.uuid4().hex}.jpg'
    path = os.path.join(OUTFIT_FOLDER, filename)
    Image.open(BytesIO(resp.content)).convert('RGB').save(path, 'JPEG', quality=92, optimize=True)
    return f'uploads/outfits/{filename}'


def _generate_with_kontext(prompt, shoe_item, shoe_bytes, seed, encoded_negative, headers, image_model=None):
    """
    Génère une image via FLUX.1-Kontext (Pollinations) en POST multipart
    avec la photo de la chaussure comme référence visuelle.
    """
    ai_sub = _clean_text(getattr(shoe_item, 'ai_subcategory', '') or '')
    shoe_label = ai_sub if ai_sub else 'shoe'

    kontext_prompt = (
        f'Keep the exact design, colorway, sole shape and branding of the reference {shoe_label}. '
        f'{prompt}'
    )

    kontext_model = image_model if image_model else 'kontext'
    params = {
        'width': POLLINATIONS_WIDTH,
        'height': POLLINATIONS_HEIGHT,
        'seed': seed,
        'model': kontext_model,
        'enhance': 'false',
        'safe': 'true' if POLLINATIONS_SAFE else 'false',
        'negative_prompt': urllib.parse.unquote(encoded_negative),
    }

    current_app.logger.info(
        f'Calling Pollinations kontext (POST) | shoe={shoe_label} | model={kontext_model} '
        f'| size={POLLINATIONS_WIDTH}x{POLLINATIONS_HEIGHT} | seed={seed}'
    )

    try:
        encoded_prompt = urllib.parse.quote(kontext_prompt, safe='')
        url = f'https://gen.pollinations.ai/image/{encoded_prompt}'
        files = {'image': ('shoe.jpg', shoe_bytes, 'image/jpeg')}
        resp = requests.post(url, params=params, files=files, headers=headers, timeout=300)
        current_app.logger.info(
            f'Kontext response: {resp.status_code}, '
            f'content-type: {resp.headers.get("content-type")}'
        )
        if not resp.ok:
            current_app.logger.warning(f'Kontext error {resp.status_code}: {resp.text[:400]}')
            return None, f'Kontext {resp.status_code}'
        ct = (resp.headers.get('content-type') or '').lower()
        if 'image' not in ct:
            current_app.logger.warning(f'Kontext non-image response: {ct}')
            return None, f'Kontext réponse invalide ({ct})'
        return _save_pollinations_response(resp), None
    except requests.Timeout:
        current_app.logger.warning('Kontext timeout — fallback standard')
        return None, 'Kontext timeout'
    except Exception as exc:
        current_app.logger.error(f'Kontext error: {exc}')
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


def generate_image(prompt, api_key=None, outfit=None, image_model=None, local_url=None, local_checkpoint=None):
    clean_prompt = ' '.join(str(prompt).split()).strip()
    negative_prompt = build_negative_prompt()
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
        negative_prompt = build_negative_prompt()
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

    # Kontext (image-to-image) uniquement si l'utilisateur l'a explicitement choisi
    if effective_model == 'kontext':
        shoe_item, shoe_bytes = _encode_shoe_reference(outfit) if outfit else (None, None)
        if shoe_item and shoe_bytes:
            result = _generate_with_kontext(
                clean_prompt, shoe_item, shoe_bytes,
                seed, encoded_negative, headers,
                image_model=effective_model,
            )
            if result[0] is not None:
                return result
            current_app.logger.warning('Kontext failed, falling back to standard generation')

    # Génération standard
    encoded_prompt = urllib.parse.quote(clean_prompt, safe='')
    url = (
        f'https://gen.pollinations.ai/image/{encoded_prompt}'
        f'?width={POLLINATIONS_WIDTH}'
        f'&height={POLLINATIONS_HEIGHT}'
        f'&seed={seed}'
        f'&model={effective_model}'
        f"&enhance={'true' if POLLINATIONS_ENHANCE else 'false'}"
        f"&safe={'true' if POLLINATIONS_SAFE else 'false'}"
        f'&negative_prompt={encoded_negative}'
    )

    current_app.logger.info(
        f'Calling Pollinations | model={effective_model} '
        f'| size={POLLINATIONS_WIDTH}x{POLLINATIONS_HEIGHT} '
        f"| seed={seed} | key={'yes' if bool(api_key) else 'no'}"
    )

    try:
        resp = requests.get(url, timeout=300, headers=headers)
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
            if resp.status_code == 402:
                return None, (
                    f'Solde Pollinations insuffisant pour le modèle « {effective_model} ». '
                    'Changez de modèle dans Paramètres IA (choisissez Flux — gratuit) '
                    'ou rechargez votre solde sur pollinations.ai.'
                )
            if resp.status_code == 401:
                return None, 'Clé API Pollinations invalide ou expirée. Vérifiez dans Paramètres IA.'
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
        return None, 'Timeout — génération trop longue (> 5 min). Réessayez.'
    except requests.RequestException as exc:
        current_app.logger.error(f'HTTP request error during image generation: {exc}')
        return None, 'Erreur réseau pendant la génération.'
    except Exception as exc:
        current_app.logger.error(f'Image generation error: {exc}')
        return None, str(exc)
