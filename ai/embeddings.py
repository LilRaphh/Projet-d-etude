"""
ai/embeddings.py — Brique embeddings : FashionCLIP (HuggingFace) + SQLite natif.

Les embeddings sont stockés dans la table `item_embeddings` via SQLAlchemy.
Zéro dépendance externe au-delà de torch + transformers.

Premier démarrage : téléchargement automatique de patrickjohncyh/fashion-clip (~600 MB)
vers ~/.cache/huggingface/
"""
import json
import logging
import os
from typing import List, Optional

import torch
from PIL import Image
from transformers import CLIPModel, CLIPProcessor

log = logging.getLogger(__name__)

FASHIONCLIP_MODEL = os.environ.get("FASHIONCLIP_MODEL", "patrickjohncyh/fashion-clip")


# Singletons — chargés une seule fois au premier appel
_model: Optional[CLIPModel] = None
_processor: Optional[CLIPProcessor] = None
_model_loading: bool = False
_model_ready: bool = False


def is_model_ready() -> bool:
    """Retourne True si FashionCLIP est chargé en mémoire."""
    return _model_ready


def _get_model():
    global _model, _processor, _model_loading, _model_ready
    if _model is not None:
        return _model, _processor
    if _model_loading:
        raise RuntimeError("FashionCLIP est en cours de chargement, réessayez dans quelques secondes.")
    _model_loading = True
    try:
        log.info("Chargement de FashionCLIP (%s)…", FASHIONCLIP_MODEL)
        device = _best_device()
        _processor = CLIPProcessor.from_pretrained(FASHIONCLIP_MODEL)
        _model = CLIPModel.from_pretrained(FASHIONCLIP_MODEL).to(device)
        _model.eval()
        _model_ready = True
        log.info("FashionCLIP prêt sur %s.", device)
    except Exception as e:
        _model_loading = False
        raise RuntimeError(f"Impossible de charger FashionCLIP : {e}")
    finally:
        _model_loading = False
    return _model, _processor


def _best_device() -> str:
    if torch.cuda.is_available():
        return "cuda"
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def _device_of_model() -> torch.device:
    model, _ = _get_model()
    return next(model.parameters()).device


# ---------------------------------------------------------------------------
# Encodage
# ---------------------------------------------------------------------------

def encode_image(image_path: str) -> List[float]:
    """Retourne l'embedding FashionCLIP (512-dim) d'une image, normalisé L2."""
    model, processor = _get_model()
    device = _device_of_model()
    image = Image.open(image_path).convert("RGB")
    inputs = processor(images=image, return_tensors="pt", padding=True)
    inputs = {k: v.to(device) for k, v in inputs.items()}
    with torch.no_grad():
        features = model.get_image_features(**inputs)
        features = features / features.norm(dim=-1, keepdim=True)
    return features.squeeze().cpu().tolist()


def encode_text(text: str) -> List[float]:
    """Retourne l'embedding FashionCLIP d'un texte, normalisé L2."""
    model, processor = _get_model()
    device = _device_of_model()
    inputs = processor(
        text=[text],
        return_tensors="pt",
        padding=True,
        truncation=True,
        max_length=77,
    )
    inputs = {k: v.to(device) for k, v in inputs.items()}
    with torch.no_grad():
        features = model.get_text_features(**inputs)
        features = features / features.norm(dim=-1, keepdim=True)
    return features.squeeze().cpu().tolist()


# ---------------------------------------------------------------------------
# Stockage vectoriel — SQLite via SQLAlchemy (remplace ChromaDB)
# ---------------------------------------------------------------------------

def store_item(
    item_id: int,
    user_id: int,
    embedding: List[float],
    metadata: dict,
    description: str,
) -> None:
    """Stocke ou met à jour l'embedding d'un item dans SQLite."""
    from extensions import db
    from models import ItemEmbedding

    emb_json = json.dumps(embedding)
    meta_json = json.dumps(metadata)

    row = ItemEmbedding.query.filter_by(item_id=item_id, user_id=user_id).first()
    if row:
        row.embedding_json = emb_json
        row.metadata_json = meta_json
        row.description = description
    else:
        db.session.add(
            ItemEmbedding(
                item_id=item_id,
                user_id=user_id,
                embedding_json=emb_json,
                metadata_json=meta_json,
                description=description,
            )
        )
    db.session.commit()


def get_user_items_with_embeddings(user_id: int) -> List[dict]:
    """Récupère tous les items indexés d'un utilisateur depuis SQLite."""
    from models import ItemEmbedding

    rows = ItemEmbedding.query.filter_by(user_id=user_id).all()
    items = []
    for row in rows:
        try:
            embedding = json.loads(row.embedding_json)
            metadata = json.loads(row.metadata_json)
        except (json.JSONDecodeError, TypeError):
            log.warning("Embedding corrompu pour item_id=%d, ignoré.", row.item_id)
            continue
        items.append(
            {
                "chroma_id": f"u{row.user_id}_i{row.item_id}",
                "item_id": row.item_id,
                "embedding": embedding,
                "metadata": metadata,
                "description": row.description or "",
            }
        )
    return items


def delete_item(item_id: int, user_id: int) -> None:
    """Supprime l'embedding d'un item."""
    from extensions import db
    from models import ItemEmbedding

    row = ItemEmbedding.query.filter_by(item_id=item_id, user_id=user_id).first()
    if row:
        db.session.delete(row)
        db.session.commit()


def collection_count(user_id: int) -> int:
    """Nombre d'items indexés pour un utilisateur."""
    from models import ItemEmbedding
    try:
        return ItemEmbedding.query.filter_by(user_id=user_id).count()
    except Exception:
        return 0
