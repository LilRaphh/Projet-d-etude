"""
utils/photo_item_extractor.py — Détection et découpe de vêtements dans une photo complète.

Backend principal : OWL-ViT (google/owlvit-base-patch32)
  → Modèle de détection zero-shot dédié, précis au pixel, ~3s sur CPU.
  → Téléchargement automatique la première fois (~600MB, puis offline).

Fallback : qwen2.5vl via Ollama si OWL-ViT non disponible.
"""

import base64
import io
import json
import logging
import os
import re
import threading
import uuid
from dataclasses import dataclass
from typing import List, Optional, Tuple

import requests as _requests
from PIL import Image, ImageOps

from config import BASE_DIR, CATEGORIES

log = logging.getLogger(__name__)

# ─── Chemins ─────────────────────────────────────────────────────────────────

_SOURCE_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads', 'extractions', 'source')
_CROPS_FOLDER  = os.path.join(BASE_DIR, 'static', 'uploads', 'extractions', 'crops')
_THUMBS_FOLDER = os.path.join(_CROPS_FOLDER, 'thumbs')
_THUMB_SIZE    = (500, 500)

# ─── OWL-ViT ─────────────────────────────────────────────────────────────────

_OWLVIT_MODEL  = 'google/owlvit-base-patch32'
_HF_HOME       = os.environ.get('HF_HOME', os.path.expanduser('~/.cache/huggingface'))
_HF_CACHE      = os.path.join(_HF_HOME, 'hub')
_OWLVIT_CACHE  = os.path.join(_HF_CACHE, 'models--google--owlvit-base-patch32')

# Labels de détection (vocabulaire ouvert, anglais = meilleurs résultats avec CLIP)
_DETECTION_QUERIES = [
    "t-shirt", "shirt", "blouse", "polo shirt", "tank top",
    "sweater", "hoodie", "sweatshirt", "cardigan",
    "jacket", "coat", "blazer", "down jacket", "raincoat",
    "pants", "trousers", "jeans", "shorts", "leggings",
    "dress", "skirt",
    "shoes", "sneakers", "boots", "sandals", "high heels", "loafers",
    "hat", "baseball cap", "beanie",
    "bag", "backpack", "handbag",
    "belt", "scarf", "tie", "glasses", "sunglasses",
]

# (catégorie, nom français) par label détecté
_LABEL_META = {
    "t-shirt":       ("T-shirts",          "T-shirt"),
    "shirt":         ("Hauts",             "Chemise"),
    "blouse":        ("Hauts",             "Blouse"),
    "polo shirt":    ("T-shirts",          "Polo"),
    "tank top":      ("Hauts",             "Débardeur"),
    "sweater":       ("Pulls & Sweats",    "Pull"),
    "hoodie":        ("Pulls & Sweats",    "Sweat à capuche"),
    "sweatshirt":    ("Pulls & Sweats",    "Sweat"),
    "cardigan":      ("Pulls & Sweats",    "Cardigan"),
    "jacket":        ("Vestes & Manteaux", "Veste"),
    "coat":          ("Vestes & Manteaux", "Manteau"),
    "blazer":        ("Vestes & Manteaux", "Blazer"),
    "down jacket":   ("Vestes & Manteaux", "Doudoune"),
    "raincoat":      ("Vestes & Manteaux", "Imperméable"),
    "pants":         ("Pantalons",         "Pantalon"),
    "trousers":      ("Pantalons",         "Pantalon"),
    "jeans":         ("Jeans",             "Jean"),
    "shorts":        ("Shorts",            "Short"),
    "leggings":      ("Pantalons",         "Legging"),
    "dress":         ("Robes & Jupes",     "Robe"),
    "skirt":         ("Robes & Jupes",     "Jupe"),
    "shoes":         ("Chaussures",        "Chaussures"),
    "sneakers":      ("Chaussures",        "Sneakers"),
    "boots":         ("Chaussures",        "Bottes"),
    "sandals":       ("Chaussures",        "Sandales"),
    "high heels":    ("Chaussures",        "Talons"),
    "loafers":       ("Chaussures",        "Mocassins"),
    "hat":           ("Accessoires",       "Chapeau"),
    "baseball cap":  ("Accessoires",       "Casquette"),
    "beanie":        ("Accessoires",       "Bonnet"),
    "bag":           ("Accessoires",       "Sac"),
    "backpack":      ("Accessoires",       "Sac à dos"),
    "handbag":       ("Accessoires",       "Sac à main"),
    "belt":          ("Accessoires",       "Ceinture"),
    "scarf":         ("Accessoires",       "Écharpe"),
    "tie":           ("Accessoires",       "Cravate"),
    "glasses":       ("Accessoires",       "Lunettes"),
    "sunglasses":    ("Accessoires",       "Lunettes de soleil"),
}

# ─── Couleurs ─────────────────────────────────────────────────────────────────

_KNOWN_COLORS = [
    'Blanc', 'Noir', 'Gris', 'Beige', 'Marron', 'Camel', 'Rouge', 'Rose',
    'Orange', 'Jaune', 'Vert', 'Bleu', 'Violet', 'Multicolore', 'Imprimé',
]
_COLOR_REF = [
    ('Blanc',  (240, 240, 240)), ('Noir',   (30,  30,  30)),
    ('Gris',   (130, 130, 130)), ('Beige',  (220, 195, 160)),
    ('Camel',  (185, 140, 90)),  ('Marron', (110, 65,  35)),
    ('Rouge',  (200, 30,  30)),  ('Rose',   (230, 130, 150)),
    ('Orange', (225, 110, 30)),  ('Jaune',  (235, 210, 30)),
    ('Vert',   (50,  145, 60)),  ('Bleu',   (35,  75,  200)),
    ('Violet', (115, 45,  175)),
]

# ─── Régions par défaut (fallback si aucun modèle disponible) ─────────────────

_REGION_FALLBACK = {
    'Hauts':             {'x':  4, 'y': 14, 'w': 92, 'h': 36},
    'T-shirts':          {'x':  4, 'y': 14, 'w': 92, 'h': 34},
    'Pulls & Sweats':    {'x':  3, 'y': 12, 'w': 94, 'h': 42},
    'Vestes & Manteaux': {'x':  2, 'y':  9, 'w': 96, 'h': 52},
    'Pantalons':         {'x':  5, 'y': 48, 'w': 90, 'h': 36},
    'Jeans':             {'x':  5, 'y': 48, 'w': 90, 'h': 36},
    'Shorts':            {'x':  8, 'y': 48, 'w': 84, 'h': 26},
    'Robes & Jupes':     {'x':  3, 'y': 12, 'w': 94, 'h': 72},
    'Chaussures':        {'x':  8, 'y': 76, 'w': 84, 'h': 24},
    'Accessoires':       {'x': 10, 'y':  0, 'w': 80, 'h': 24},
    'Sous-vêtements':    {'x': 10, 'y': 40, 'w': 80, 'h': 34},
    'Sport':             {'x':  4, 'y': 12, 'w': 92, 'h': 70},
    'Autre':             {'x':  4, 'y':  8, 'w': 92, 'h': 82},
}

# Régions corporelles garanties pour photos en pied (utilisées si < 3 articles trouvés)
_BODY_BASELINE = [
    ('Haut',      'Vestes & Manteaux', {'x':  5, 'y':  7, 'w': 90, 'h': 48}),
    ('Bas',       'Pantalons',         {'x': 10, 'y': 43, 'w': 80, 'h': 40}),
    ('Chaussures','Chaussures',        {'x': 12, 'y': 78, 'w': 76, 'h': 22}),
]


@dataclass
class DetectedItem:
    name: str
    category: str
    color: str
    bbox_pct: dict
    crop_path: str
    crop_thumb_path: str
    session_id: str


# ─── Gestion du téléchargement OWL-ViT ───────────────────────────────────────

# État partagé du téléchargement en cours
_dl_state: dict = {'status': 'idle', 'progress': 0, 'error': None}
_dl_lock = threading.Lock()


def is_owlvit_cached() -> bool:
    """Vérifie si le modèle OWL-ViT est présent dans le cache HuggingFace."""
    return os.path.isdir(_OWLVIT_CACHE) and bool(os.listdir(_OWLVIT_CACHE))


def get_download_state() -> dict:
    with _dl_lock:
        return dict(_dl_state)


def start_owlvit_download() -> bool:
    """Lance le téléchargement en arrière-plan. Retourne False si déjà en cours."""
    with _dl_lock:
        if _dl_state['status'] == 'downloading':
            return False
        _dl_state['status']   = 'downloading'
        _dl_state['progress'] = 0
        _dl_state['error']    = None

    t = threading.Thread(target=_download_worker, daemon=True, name='owlvit-download')
    t.start()
    return True


_IGNORE_PATTERNS = frozenset(['*.msgpack', '*.h5', 'flax_model*', 'tf_model*', 'rust_model*'])


def _should_skip(fname: str) -> bool:
    import fnmatch
    return any(fnmatch.fnmatch(fname, p) for p in _IGNORE_PATTERNS)


def _download_worker():
    """Thread de téléchargement : télécharge fichier par fichier pour suivre la progression."""
    old_offline = os.environ.get('HF_HUB_OFFLINE')
    os.environ.pop('HF_HUB_OFFLINE', None)
    try:
        from huggingface_hub import list_repo_files, hf_hub_download

        files = [f for f in list_repo_files(_OWLVIT_MODEL) if not _should_skip(f)]
        total = max(len(files), 1)

        for i, filename in enumerate(files):
            with _dl_lock:
                _dl_state['progress'] = int(i / total * 95)
                _dl_state['current_file'] = filename
            log.info("OWL-ViT : %d/%d — %s", i + 1, total, filename)
            hf_hub_download(_OWLVIT_MODEL, filename)

        with _dl_lock:
            _dl_state['status']   = 'done'
            _dl_state['progress'] = 100
            _dl_state.pop('current_file', None)
        log.info("OWL-ViT téléchargé avec succès dans %s", _OWLVIT_CACHE)
    except Exception as exc:
        with _dl_lock:
            _dl_state['status'] = 'error'
            _dl_state['error']  = str(exc)[:300]
            _dl_state.pop('current_file', None)
        log.exception("Échec du téléchargement OWL-ViT")
    finally:
        if old_offline is not None:
            os.environ['HF_HUB_OFFLINE'] = old_offline


# ─── Chargement OWL-ViT (lazy, singleton) ────────────────────────────────────

_processor = None
_model     = None
_model_lock = threading.Lock()


def _load_owlvit():
    """Charge processor + model en mémoire. Thread-safe."""
    global _processor, _model
    if _processor is not None:
        return _processor, _model
    with _model_lock:
        if _processor is None:
            log.info("Chargement OWL-ViT en mémoire…")
            from transformers import OwlViTForObjectDetection, OwlViTProcessor
            import torch
            _processor = OwlViTProcessor.from_pretrained(_OWLVIT_MODEL)
            _model     = OwlViTForObjectDetection.from_pretrained(_OWLVIT_MODEL)
            _model.eval()
            log.info("OWL-ViT chargé.")
    return _processor, _model


# ─── Détection OWL-ViT ───────────────────────────────────────────────────────

def _iou(a: dict, b: dict) -> float:
    """Intersection over Union de deux boîtes {x,y,w,h}."""
    ax2, ay2 = a['x'] + a['w'], a['y'] + a['h']
    bx2, by2 = b['x'] + b['w'], b['y'] + b['h']
    ix1 = max(a['x'], b['x']); iy1 = max(a['y'], b['y'])
    ix2 = min(ax2, bx2);       iy2 = min(ay2, by2)
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    inter = (ix2 - ix1) * (iy2 - iy1)
    union = a['w']*a['h'] + b['w']*b['h'] - inter
    return inter / union if union > 0 else 0.0


def _nms(detections: List[dict], iou_thr: float = 0.45) -> List[dict]:
    """Non-Maximum Suppression : supprime les boîtes redondantes."""
    detections = sorted(detections, key=lambda d: d['score'], reverse=True)
    kept = []
    for det in detections:
        if all(_iou(det['bbox_pct'], k['bbox_pct']) < iou_thr for k in kept):
            kept.append(det)
    return kept


def _detect_owlvit(image: Image.Image, threshold: float = 0.10) -> List[dict]:
    """
    Détecte les vêtements avec OWL-ViT.
    Retourne une liste de {label, score, bbox_pct, category, name_fr}.
    """
    import torch

    processor, model = _load_owlvit()
    W, H = image.size

    inputs = processor(
        text=[_DETECTION_QUERIES],
        images=image,
        return_tensors='pt',
    )
    with torch.no_grad():
        outputs = model(**inputs)

    target_sizes = torch.tensor([(H, W)])
    results = processor.post_process_grounded_object_detection(
        outputs=outputs,
        target_sizes=target_sizes,
        threshold=threshold,
        text_labels=[_DETECTION_QUERIES],
    )[0]

    detections = []
    scores  = results['scores'].tolist()
    labels  = results.get('text_labels') or [_DETECTION_QUERIES[i] for i in results['labels'].tolist()]
    boxes   = results['boxes'].tolist()

    for score, label, box in zip(scores, labels, boxes):
        xmin, ymin, xmax, ymax = box
        xmin = max(0.0, xmin); ymin = max(0.0, ymin)
        xmax = min(float(W), xmax); ymax = min(float(H), ymax)
        if xmax <= xmin or ymax <= ymin:
            continue

        category, name_fr = _LABEL_META.get(label, ('Autre', label.title()))
        detections.append({
            'label':    label,
            'score':    score,
            'category': category,
            'name_fr':  name_fr,
            'bbox_pct': {
                'x': xmin / W * 100,
                'y': ymin / H * 100,
                'w': (xmax - xmin) / W * 100,
                'h': (ymax - ymin) / H * 100,
            },
        })

    return _nms(detections)


# ─── Fallback Ollama ──────────────────────────────────────────────────────────

_OLLAMA_BASE    = os.environ.get('OLLAMA_URL', 'http://localhost:11434')
_OLLAMA_TIMEOUT = int(os.environ.get('OLLAMA_TIMEOUT', '300'))
_OLLAMA_MAX_PX  = 768


def _encode_for_ollama(image_path: str) -> str:
    img = Image.open(image_path).convert('RGB')
    w, h = img.size
    if max(w, h) > _OLLAMA_MAX_PX:
        scale = _OLLAMA_MAX_PX / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=85, optimize=True)
    return base64.b64encode(buf.getvalue()).decode()


def _ollama_prompt() -> str:
    cats   = ', '.join(f'"{c}"' for c in CATEGORIES)
    colors = ', '.join(f'"{c}"' for c in _KNOWN_COLORS)
    return f"""Analyse cette photo de mode. Liste chaque vêtement et accessoire visible sur la personne.

Réponds UNIQUEMENT avec ce JSON (plusieurs articles attendus pour une photo en pied) :
{{"items":[
  {{"name":"Veste","category":"Vestes & Manteaux","color":"Noir","bbox":{{"x1":5,"y1":8,"x2":95,"y2":55}}}},
  {{"name":"Pantalon","category":"Pantalons","color":"Gris","bbox":{{"x1":10,"y1":44,"x2":90,"y2":82}}}},
  {{"name":"Chaussures","category":"Chaussures","color":"Marron","bbox":{{"x1":15,"y1":80,"x2":85,"y2":100}}}}
]}}

Règles importantes :
- bbox = pourcentages 0-100 (x1,y1=haut-gauche, x2,y2=bas-droit). Couvre UNIQUEMENT l'article, pas tout le corps.
- Catégories valides : {cats}
- Couleurs valides : {colors}
- Nom court en français (ex: "Veste en cuir", "Jean slim", "Sneakers blancs")
- Liste TOUS les articles : haut, veste, pantalon, chaussures, ceinture, lunettes, sac, casquette, etc.
- Pour une photo en pied, il y a généralement 3 à 7 articles visibles."""


def _parse_json(text: str) -> Optional[dict]:
    text = text.strip()
    if '```' in text:
        for seg in text.split('```'):
            s = seg.strip().lstrip('json').strip()
            if s.startswith('{'):
                text = s; break
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r'\{.*\}', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    return None


def _normalize_bbox(raw) -> Optional[dict]:
    """Accepte {x1,y1,x2,y2}, {x,y,w,h}, {xmin,…}, valeurs 0-1 ou 0-1000."""
    if not isinstance(raw, dict):
        return None

    def _f(*keys):
        for k in keys:
            v = raw.get(k)
            if v is not None:
                try: return float(v)
                except (TypeError, ValueError): pass
        return None

    x1 = _f('x1','xmin','left');  y1 = _f('y1','ymin','top')
    x2 = _f('x2','xmax','right'); y2 = _f('y2','ymax','bottom')

    if x1 is None:
        x1 = _f('x'); y1 = _f('y')
        w  = _f('w','width'); h = _f('h','height')
        if None not in (x1, y1, w, h):
            x2 = x1 + w; y2 = y1 + h

    if None in (x1, y1, x2, y2):
        return None

    max_v = max(x1, y1, x2, y2)
    if max_v <= 1.0:
        x1,y1,x2,y2 = x1*100,y1*100,x2*100,y2*100
    elif max_v > 100:
        x1,y1,x2,y2 = x1/10,y1/10,x2/10,y2/10

    if x1 > x2: x1,x2 = x2,x1
    if y1 > y2: y1,y2 = y2,y1
    x1=max(0.0,min(99.0,x1)); y1=max(0.0,min(99.0,y1))
    x2=max(x1+1,min(100.0,x2)); y2=max(y1+1,min(100.0,y2))
    w,h = x2-x1, y2-y1
    return {'x':x1,'y':y1,'w':w,'h':h} if w>=2 and h>=2 else None


def _add_body_fallbacks(detections: List[dict]) -> List[dict]:
    """
    Si moins de 3 articles détectés, complète avec les régions corporelles de base.
    Évite les doublons via IoU avec les détections existantes.
    """
    if len(detections) >= 3:
        return detections
    existing = [d['bbox_pct'] for d in detections]
    result = list(detections)
    for name, category, region in _BODY_BASELINE:
        if any(_iou(region, bbox) > 0.25 for bbox in existing):
            continue
        result.append({
            'label': name, 'score': 0.3,
            'category': category, 'name_fr': name,
            'bbox_pct': region.copy(), 'color_hint': '',
        })
    return result


def _detect_ollama(image_path: str, model: str) -> List[dict]:
    """Détection via Ollama (fallback). Retourne la même structure que _detect_owlvit."""
    img_b64 = _encode_for_ollama(image_path)
    payload = {
        'model': model, 'format': 'json',
        'messages': [{'role':'user','content':_ollama_prompt(),'images':[img_b64]}],
        'stream': False,
        'options': {'temperature': 0.1, 'seed': 42},
    }
    try:
        resp = _requests.post(f'{_OLLAMA_BASE}/api/chat', json=payload, timeout=_OLLAMA_TIMEOUT)
        if resp.status_code == 404:
            raise RuntimeError(f"Modèle '{model}' introuvable. Lancez : ollama pull {model}")
        resp.raise_for_status()
    except _requests.ConnectionError:
        raise RuntimeError("Ollama inaccessible. Vérifiez que le service est démarré.")
    except _requests.Timeout:
        raise RuntimeError(f"Timeout Ollama ({_OLLAMA_TIMEOUT}s).")
    except RuntimeError:
        raise
    except _requests.RequestException as e:
        raise RuntimeError(f"Erreur Ollama : {e}")

    raw_text = resp.json().get('message', {}).get('content', '')
    log.debug("Réponse Ollama brute : %.300s", raw_text)
    parsed = _parse_json(raw_text)
    if not parsed:
        log.warning("Réponse Ollama non parseable : %.200s", raw_text)
        return []

    out = []
    for item in parsed.get('items', []):
        name = (item.get('name') or '').strip()
        if not name:
            continue
        cat = item.get('category', 'Autre')
        if cat not in CATEGORIES:
            cat = 'Autre'
        color = item.get('color', '')
        if color not in _KNOWN_COLORS:
            color = ''
        bbox = _normalize_bbox(item.get('bbox') or item.get('bbox_pct') or item.get('box'))
        if bbox is None:
            bbox = _REGION_FALLBACK.get(cat, _REGION_FALLBACK['Autre']).copy()
        out.append({'label': name, 'score': 1.0, 'category': cat, 'name_fr': name,
                    'bbox_pct': bbox, 'color_hint': color})
    out = _add_body_fallbacks(out)
    log.info("Ollama pipeline : %d article(s) final (avec régions corporelles)", len(out))
    return out


# ─── Couleur dominante ────────────────────────────────────────────────────────

def _nearest_color(r: int, g: int, b: int) -> str:
    best, bd = 'Gris', float('inf')
    for name, (cr,cg,cb) in _COLOR_REF:
        d = (r-cr)**2 + (g-cg)**2 + (b-cb)**2
        if d < bd:
            bd, best = d, name
    return best


def extract_dominant_color(crop: Image.Image) -> str:
    try:
        small = crop.convert('RGB').resize((40,40), Image.LANCZOS)
        px = list(small.getdata())
        px = [p for p in px
              if not (p[0]>238 and p[1]>238 and p[2]>238)
              and not (p[0]<18  and p[1]<18  and p[2]<18)] or px
        r = sorted(p[0] for p in px)[len(px)//2]
        g = sorted(p[1] for p in px)[len(px)//2]
        b = sorted(p[2] for p in px)[len(px)//2]
        return _nearest_color(r, g, b)
    except Exception:
        return ''


# ─── Sauvegarde ───────────────────────────────────────────────────────────────

def save_source_photo(file_obj, session_id: str) -> Optional[str]:
    os.makedirs(_SOURCE_FOLDER, exist_ok=True)
    ext  = file_obj.filename.rsplit('.', 1)[-1].lower() if '.' in file_obj.filename else 'jpg'
    dest = os.path.join(_SOURCE_FOLDER, f'{session_id}.{ext}')
    try:
        img = Image.open(file_obj.stream)
        img = ImageOps.exif_transpose(img)
        if img.mode not in ('RGB','RGBA'):
            img = img.convert('RGB')
        img.save(dest, optimize=True, quality=90)
        return dest
    except Exception:
        log.exception("Sauvegarde photo source échouée : %s", dest)
        return None


def _crop_region(img: Image.Image, bbox: dict, margin: float = 0.03) -> Image.Image:
    W, H = img.size
    x1 = max(0.0, (bbox['x']/100 - margin) * W)
    y1 = max(0.0, (bbox['y']/100 - margin) * H)
    x2 = min(float(W), ((bbox['x']+bbox['w'])/100 + margin) * W)
    y2 = min(float(H), ((bbox['y']+bbox['h'])/100 + margin) * H)
    return img.crop((int(x1), int(y1), int(x2), int(y2)))


def _save_crop(crop: Image.Image, session_id: str) -> Tuple[str, str]:
    os.makedirs(_CROPS_FOLDER, exist_ok=True)
    os.makedirs(_THUMBS_FOLDER, exist_ok=True)
    name = f'{session_id}_{uuid.uuid4().hex}.jpg'
    rgb  = crop.convert('RGB')
    rgb.save(os.path.join(_CROPS_FOLDER, name), optimize=True, quality=88)
    thumb = ImageOps.fit(rgb, _THUMB_SIZE, Image.LANCZOS)
    thumb.save(os.path.join(_THUMBS_FOLDER, name), optimize=True, quality=82)
    return f'uploads/extractions/crops/{name}', f'uploads/extractions/crops/thumbs/{name}'


# ─── Pipeline principal ───────────────────────────────────────────────────────

def extract_items_from_photo(
    source_path: str,
    session_id: str,
    ollama_model: str,
) -> List[DetectedItem]:
    """
    Détecte et découpe les vêtements d'une photo.
    Utilise OWL-ViT si disponible (rapide, précis), sinon Ollama en fallback.
    """
    img = Image.open(source_path)
    img = ImageOps.exif_transpose(img)
    if img.mode not in ('RGB','RGBA'):
        img = img.convert('RGB')

    # Choisir le backend
    if is_owlvit_cached():
        log.info("Backend : OWL-ViT")
        raw_detections = _detect_owlvit(img)
    else:
        log.info("Backend : Ollama (%s)", ollama_model)
        raw_detections = _detect_ollama(source_path, ollama_model)

    if not raw_detections:
        return []

    results: List[DetectedItem] = []
    for det in raw_detections:
        bbox = det['bbox_pct']
        try:
            crop       = _crop_region(img, bbox)
            crop_path, thumb_path = _save_crop(crop, session_id)
        except Exception:
            log.exception("Découpage échoué pour '%s'", det.get('name_fr'))
            continue

        color = det.get('color_hint', '') or extract_dominant_color(crop)

        name_fr   = det.get('name_fr', det.get('label', 'Article'))
        full_name = f"{name_fr} {color.lower()}".strip() if color else name_fr

        results.append(DetectedItem(
            name=full_name,
            category=det['category'],
            color=color,
            bbox_pct=bbox,
            crop_path=crop_path,
            crop_thumb_path=thumb_path,
            session_id=session_id,
        ))

    return results
