"""
routes/complete.py — "Complète ma tenue"

Étant donné un vêtement ancre, propose les meilleures pièces complémentaires
depuis la garde-robe de l'utilisateur, slot par slot.

Deux moteurs (auto-détectés) :
  - Local  : cosine FashionCLIP + harmonie couleurs + cohérence formalisme
  - Claude : fallback si l'ancre n'est pas indexée ou clé API dispo
"""
import json
import logging
import math
import os
from typing import Optional

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

from config import ANTHROPIC_MODEL, OCCASIONS
from extensions import db
from models import ClothingItem, ItemEmbedding, Outfit, UserSetting
from utils.auth import get_ctx

log = logging.getLogger(__name__)
complete_bp = Blueprint("complete", __name__)

# Mapping catégorie → slot (copie légère pour éviter import circulaire)
_CAT_SLOT = {
    "Hauts": "top", "T-shirts": "top", "Pulls & Sweats": "top", "Sport": "top",
    "Vestes & Manteaux": "outer",
    "Pantalons": "bottom", "Jeans": "bottom", "Shorts": "bottom", "Robes & Jupes": "bottom",
    "Chaussures": "shoes",
    "Accessoires": "accessory",
}
_SLOT_LABELS = {
    "top": "Hauts", "bottom": "Bas", "shoes": "Chaussures",
    "outer": "Vestes & Manteaux", "accessory": "Accessoires",
}
_SLOT_ICONS = {
    "top": "👕", "bottom": "👖", "shoes": "👟", "outer": "🧥", "accessory": "👜",
}
# Ordre d'affichage des slots
_SLOT_ORDER = ["top", "bottom", "shoes", "outer", "accessory"]


# ---------------------------------------------------------------------------
# Helpers auth
# ---------------------------------------------------------------------------

def _uid() -> Optional[int]:
    return session.get("user_id")


def _api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if key:
        return key
    uid = _uid()
    return UserSetting.get(uid, "anthropic_key", "") if uid else ""


# ---------------------------------------------------------------------------
# Scoring couleur (inline — évite les imports privés de scoring.py)
# ---------------------------------------------------------------------------

_NEUTRALS = {
    "noir", "blanc", "gris", "beige", "camel", "marron", "crème", "creme",
    "navy", "marine", "bleu marine", "anthracite", "taupe", "ivoire", "nude",
}
_WARM = {"rouge", "orange", "jaune", "bordeaux", "corail", "terracotta", "rouille", "or"}
_COOL = {"bleu", "vert", "violet", "turquoise", "kaki", "indigo", "menthe", "cyan", "lavande"}
_PASTEL = {"rose", "lilas", "mint", "saumon", "pêche"}
_COLOR_COMPAT = {
    ("neutral", "neutral"): 1.00, ("neutral", "warm"): 0.92, ("neutral", "cool"): 0.92,
    ("neutral", "pastel"): 0.90, ("neutral", "other"): 0.80,
    ("warm", "warm"): 0.72,   ("warm", "pastel"): 0.68, ("warm", "cool"): 0.45,
    ("cool", "cool"): 0.72,   ("cool", "pastel"): 0.70,
    ("pastel", "pastel"): 0.75, ("other", "other"): 0.55,
}


def _color_group(color: Optional[str]) -> str:
    if not color:
        return "neutral"
    c = color.lower().strip()
    if c in _NEUTRALS:
        return "neutral"
    if c in _WARM:
        return "warm"
    if c in _COOL:
        return "cool"
    if c in _PASTEL:
        return "pastel"
    for grp, s in [("neutral", _NEUTRALS), ("warm", _WARM), ("cool", _COOL)]:
        if any(n in c for n in s):
            return grp
    return "other"


def _color_compat(c1: Optional[str], c2: Optional[str]) -> float:
    g1, g2 = _color_group(c1), _color_group(c2)
    return _COLOR_COMPAT.get(tuple(sorted([g1, g2])), 0.60)


def _cosine(a, b) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


# Mots-clés couleur à détecter dans les noms d'articles quand le champ color est absent/générique
_COLOR_NAME_MAP = {
    "pink": "rose", "rose": "rose",
    "red": "rouge", "rouge": "rouge",
    "blue": "bleu", "bleu": "bleu",
    "green": "vert", "vert": "vert",
    "yellow": "jaune", "jaune": "jaune",
    "purple": "violet", "violet": "violet",
    "orange": "orange",
    "brown": "marron", "marron": "marron",
    "black": "noir", "noir": "noir",
    "white": "blanc", "blanc": "blanc",
    "beige": "beige",
    "grey": "gris", "gray": "gris", "gris": "gris",
    "navy": "marine", "marine": "marine",
    "khaki": "kaki", "kaki": "kaki",
    "camel": "camel",
    "bordeaux": "bordeaux",
    "coral": "corail", "corail": "corail",
    "turquoise": "turquoise",
    "lavender": "lavande", "lavande": "lavande",
    "cream": "crème", "crème": "crème", "ivory": "ivoire",
    "gold": "or", "silver": "argent",
    "olive": "olive", "khaki": "kaki",
}
_GENERIC_COLORS = {"autre", "multicolore", "divers", "multi", "color", "colour", ""}


def _effective_color(color: Optional[str], name: str = "") -> Optional[str]:
    """
    Retourne la couleur la plus précise possible :
    - Couleur stockée si elle est non-neutre/non-générique
    - Si stockée est neutre ou absente, tente de lire une couleur non-neutre dans le nom
    """
    stored = (color or "").strip().lower()
    name_lower = f" {name.lower()} "

    if not stored or stored in _GENERIC_COLORS:
        # Pas de couleur stockée : chercher dans le nom
        for kw, resolved in _COLOR_NAME_MAP.items():
            if f" {kw} " in name_lower or f"-{kw}" in name_lower or f"{kw}-" in name_lower:
                return resolved
        return stored or None

    # Couleur stockée présente mais neutre : le nom peut révéler une couleur plus précise
    if _color_group(stored) == "neutral":
        for kw, resolved in _COLOR_NAME_MAP.items():
            if (f" {kw} " in name_lower or f"-{kw}" in name_lower or f"{kw}-" in name_lower) \
                    and _color_group(resolved) != "neutral":
                return resolved

    return stored


# ---------------------------------------------------------------------------
# Moteur local (FashionCLIP)
# ---------------------------------------------------------------------------

def _complete_local(anchor: ClothingItem, user_id: int, occasion: str) -> dict:
    """
    Retourne un dict slot → liste de candidats triés par score.
    Nécessite que l'ancre ET au moins quelques items soient indexés.
    """
    from ai.rules import OCCASION_FORMALITY

    anchor_slot = _CAT_SLOT.get(anchor.category)

    # Slots à compléter
    if anchor.category == "Robes & Jupes":
        needed = {"shoes", "outer", "accessory"}
    elif anchor_slot:
        needed = {s for s in _SLOT_ORDER if s not in (anchor_slot, "accessory")}
    else:
        needed = {s for s in _SLOT_ORDER if s != "accessory"}

    # Embedding de l'ancre
    anchor_emb_row = ItemEmbedding.query.filter_by(item_id=anchor.id, user_id=user_id).first()
    anchor_emb = json.loads(anchor_emb_row.embedding_json) if anchor_emb_row else None

    # Tous les items + embeddings de l'utilisateur
    all_emb_rows = ItemEmbedding.query.filter_by(user_id=user_id).all()
    all_items = {i.id: i for i in ClothingItem.query.filter_by(user_id=user_id).all()}

    anchor_formality = anchor.ai_formality or 2
    f_range = OCCASION_FORMALITY.get(occasion or "Autre", (1, 5))
    # Couleur effective de l'ancre : ai_color (toujours détectée) > color (user) > nom
    anchor_color = _effective_color(anchor.ai_color or anchor.color, anchor.name)

    candidates: dict = {}

    for row in all_emb_rows:
        iid = row.item_id
        if iid == anchor.id:
            continue
        item = all_items.get(iid)
        if not item:
            continue
        slot = _CAT_SLOT.get(item.category)
        if not slot or slot not in needed:
            continue

        emb = json.loads(row.embedding_json)

        # Harmonie des couleurs : ai_color > color > extraction depuis le nom
        item_color = _effective_color(item.ai_color or item.color, item.name)
        color_s = _color_compat(anchor_color, item_color)

        # Cohérence de formalisme
        item_f = item.ai_formality or 2
        formality_s = max(0.0, 1.0 - abs(anchor_formality - item_f) / 4.0)

        # Bonus occasion (soft)
        in_range = (f_range[0] - 1) <= item_f <= (f_range[1] + 1)
        occasion_b = 0.05 if in_range else 0.0

        if anchor_emb:
            # Mode complet : similarité visuelle + couleur + formalisme
            sim = max(0.0, _cosine(anchor_emb, emb))
            total = 0.50 * sim + 0.30 * color_s + 0.20 * formality_s + occasion_b
        else:
            # Pas d'embedding ancre : couleur devient le facteur principal
            total = 0.65 * color_s + 0.35 * formality_s + occasion_b

        candidates.setdefault(slot, []).append({
            "id": item.id,
            "name": item.name,
            "category": item.category,
            "color": item.color or "",
            "brand": item.brand or "",
            "thumb": item.thumb_path or item.image_path or "",
            "times_worn": item.times_worn or 0,
            "ai_analyzed": item.ai_analyzed,
            "score": round(total, 3),
            "score_pct": round(total * 100),
            "breakdown": {
                "style": round(sim * 100) if anchor_emb else None,
                "color": round(color_s * 100),
                "formality": round(formality_s * 100),
            },
        })

    # Trier par score, garder top 4 par slot
    for slot in candidates:
        candidates[slot].sort(key=lambda x: x["score"], reverse=True)
        candidates[slot] = candidates[slot][:4]

    return candidates


# ---------------------------------------------------------------------------
# Moteur Claude (fallback metadata)
# ---------------------------------------------------------------------------

def _complete_claude(anchor: ClothingItem, user_id: int, occasion: str) -> tuple:
    key = _api_key()
    if not key:
        return None, "Clé API Anthropic manquante — ajoutez-la dans les Paramètres ⚙️."

    anchor_slot = _CAT_SLOT.get(anchor.category)
    if anchor.category == "Robes & Jupes":
        needed_slots = ["shoes", "outer"]
    elif anchor_slot:
        needed_slots = [s for s in _SLOT_ORDER if s not in (anchor_slot, "accessory")]
    else:
        needed_slots = [s for s in _SLOT_ORDER if s != "accessory"]

    all_items = ClothingItem.query.filter_by(user_id=user_id).all()

    # Formatage ancre
    anchor_desc = (
        f"ID:{anchor.id} | {anchor.name} | {anchor.category}"
        + (f" | {anchor.color}" if anchor.color else "")
        + (f" | {anchor.brand}" if anchor.brand else "")
        + (f" | style:{anchor.ai_style}" if anchor.ai_style else "")
        + (f" | formalisme:{anchor.ai_formality}/5" if anchor.ai_formality else "")
    )

    # Formatage garde-robe
    lines = []
    items_map = {}
    for item in all_items:
        if item.id == anchor.id:
            continue
        slot = _CAT_SLOT.get(item.category)
        if not slot or slot not in needed_slots:
            continue
        parts = [f"ID:{item.id}", item.name, item.category]
        if item.color:   parts.append(item.color)
        if item.brand:   parts.append(item.brand)
        if item.ai_style: parts.append(f"style:{item.ai_style}")
        parts.append(f"porté:{item.times_worn or 0}x")
        lines.append(" | ".join(parts))
        items_map[item.id] = item

    if not lines:
        return None, "Pas assez de vêtements dans les catégories complémentaires."

    slot_labels = {
        "top": "hauts (top)", "bottom": "bas (bottom)",
        "shoes": "chaussures (shoes)", "outer": "vestes/manteaux (outer)",
    }
    slots_str = ", ".join(slot_labels.get(s, s) for s in needed_slots)

    try:
        import anthropic

        msg = anthropic.Anthropic(api_key=key).messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=600,
            system=(
                "Tu es un styliste expert. Tu proposes des associations de vêtements "
                "en utilisant UNIQUEMENT les IDs listés. "
                "Tu réponds UNIQUEMENT en JSON valide, sans texte ni balises markdown."
            ),
            messages=[{
                "role": "user",
                "content": (
                    f"Vêtement ancre : {anchor_desc}\n"
                    f"Occasion : {occasion or 'Quotidien'}\n\n"
                    f"Garde-robe disponible :\n{chr(10).join(lines)}\n\n"
                    f"Pour chaque slot manquant ({slots_str}), "
                    "propose les 3 IDs les plus compatibles avec l'ancre (du meilleur au moins bon).\n"
                    "JSON strict (utilise uniquement les slots nécessaires) :\n"
                    '{"slots":{"top":[id,id,id],"bottom":[id,id,id],"shoes":[id,id,id],"outer":[id,id,id]}}'
                ),
            }],
        )

        raw = msg.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw.strip())

        # Construire les candidats enrichis
        candidates = {}
        for slot, ids in data.get("slots", {}).items():
            if slot not in needed_slots:
                continue
            slot_items = []
            for iid in ids:
                item = items_map.get(int(iid))
                if item:
                    slot_items.append({
                        "id": item.id,
                        "name": item.name,
                        "category": item.category,
                        "color": item.color or "",
                        "brand": item.brand or "",
                        "thumb": item.thumb_path or item.image_path or "",
                        "times_worn": item.times_worn or 0,
                        "ai_analyzed": item.ai_analyzed,
                        "score": None,       # Claude ne donne pas de score numérique
                        "score_pct": None,
                        "breakdown": None,
                    })
            if slot_items:
                candidates[slot] = slot_items

        return candidates, None

    except json.JSONDecodeError:
        return None, "Réponse IA invalide. Réessayez."
    except Exception as exc:
        log.exception("_complete_claude")
        return None, str(exc)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@complete_bp.route("/complete/<int:item_id>")
def complete(item_id: int):
    uid = _uid()
    if not uid:
        return redirect(url_for("auth.login"))

    anchor = ClothingItem.query.filter_by(id=item_id, user_id=uid).first_or_404()
    ctx = get_ctx()

    anchor_slot = _CAT_SLOT.get(anchor.category, "")
    anchor_indexed = ItemEmbedding.query.filter_by(item_id=item_id, user_id=uid).first() is not None
    indexed_count = ItemEmbedding.query.filter_by(user_id=uid).count()

    return render_template(
        "complete.html",
        anchor=anchor,
        anchor_slot=anchor_slot,
        anchor_slot_label=_SLOT_LABELS.get(anchor_slot, anchor_slot),
        anchor_indexed=anchor_indexed,
        indexed_count=indexed_count,
        occasions=OCCASIONS,
        has_api_key=bool(_api_key()),
        slot_labels=_SLOT_LABELS,
        slot_icons=_SLOT_ICONS,
        slot_order=_SLOT_ORDER,
        **ctx,
    )


@complete_bp.route("/api/complete/<int:item_id>", methods=["POST"])
def complete_api(item_id: int):
    uid = _uid()
    if not uid:
        return jsonify(ok=False, error="Non connecté"), 401

    anchor = ClothingItem.query.filter_by(id=item_id, user_id=uid).first()
    if not anchor:
        return jsonify(ok=False, error="Vêtement introuvable"), 404

    data = request.get_json(force=True) or {}
    occasion = data.get("occasion", "Quotidien").strip()
    force_mode = data.get("mode", "auto")  # "auto" | "local" | "claude"

    anchor_slot = _CAT_SLOT.get(anchor.category)
    anchor_indexed = ItemEmbedding.query.filter_by(item_id=item_id, user_id=uid).first() is not None
    indexed_count = ItemEmbedding.query.filter_by(user_id=uid).count()

    # Choisir le moteur
    use_local = (
        force_mode == "local"
        or (force_mode == "auto" and indexed_count >= 3)
    )

    mode_used = "local"
    candidates = {}
    error = None

    if use_local:
        try:
            candidates = _complete_local(anchor, uid, occasion)
            mode_used = "local"
        except Exception as exc:
            log.exception("complete_local failed, falling back to Claude")
            candidates = {}

    # Fallback ou mode forcé Claude
    if not candidates and _api_key():
        candidates, error = _complete_claude(anchor, uid, occasion)
        mode_used = "claude"
    elif not candidates and not use_local:
        error = (
            "Aucun vêtement indexé. "
            "Analysez vos vêtements avec l'IA locale pour activer ce mode, "
            "ou ajoutez une clé API Anthropic dans les Paramètres."
        )

    if error and not candidates:
        return jsonify(ok=False, error=error)

    # Sérialisation anchor
    anchor_data = {
        "id": anchor.id,
        "name": anchor.name,
        "category": anchor.category,
        "slot": anchor_slot,
        "color": anchor.color or "",
        "brand": anchor.brand or "",
        "thumb": anchor.thumb_path or anchor.image_path or "",
        "ai_style": anchor.ai_style or "",
        "ai_formality": anchor.ai_formality,
        "indexed": anchor_indexed,
    }

    # Ordonner les slots
    ordered = {
        s: candidates[s]
        for s in _SLOT_ORDER
        if s in candidates and candidates[s]
    }

    return jsonify(
        ok=True,
        anchor=anchor_data,
        slots=ordered,
        mode=mode_used,
        slot_labels=_SLOT_LABELS,
        slot_icons=_SLOT_ICONS,
    )


@complete_bp.route("/api/complete/save", methods=["POST"])
def complete_save():
    uid = _uid()
    if not uid:
        return jsonify(ok=False, error="Non connecté"), 401

    data = request.get_json(force=True) or {}
    anchor_id = data.get("anchor_id")
    selected_ids = [int(i) for i in data.get("item_ids", []) if i is not None]
    occasion = data.get("occasion", "")

    all_ids = list({anchor_id, *selected_ids} - {None})
    if len(all_ids) < 2:
        return jsonify(ok=False, error="Sélectionnez au moins 2 pièces."), 400

    items = [
        ClothingItem.query.filter_by(id=iid, user_id=uid).first()
        for iid in all_ids
    ]
    items = [it for it in items if it]

    outfit = Outfit(
        name=data.get("name", "Tenue complète").strip(),
        description=data.get("description", ""),
        occasion=occasion,
        user_id=uid,
        items=items,
    )
    db.session.add(outfit)
    db.session.commit()
    return jsonify(ok=True, outfit_id=outfit.id)
