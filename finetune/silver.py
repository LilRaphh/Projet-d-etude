#!/usr/bin/env python3
"""
finetune/silver.py  —  Couche Silver
Nettoyage et validation depuis bronze.jsonl :
  - Déduplication (URL exacte + nom/marque normalisé)
  - Validation des champs (type, catégorie, style, prix)
  - Nettoyage texte (HTML, whitespace, caractères de contrôle)
  - Filtrage outliers (prix aberrants, noms trop courts)
  - Rapport détaillé des rejets par motif

Usage :
    python -m finetune.silver
    python -m finetune.silver --input finetune/data/bronze.jsonl
"""
import argparse
import json
import logging
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Optional, Tuple, List

OUTPUT_DIR = Path(__file__).parent / "data"
BRONZE_IN  = OUTPUT_DIR / "bronze.jsonl"
SILVER_OUT = OUTPUT_DIR / "silver.jsonl"

logging.basicConfig(level=logging.INFO, format="[Silver] %(message)s")
log = logging.getLogger("silver")

# ── Valeurs autorisées (alignées avec pipeline/config.py) ──────────────────
VALID_TYPES  = {"Vêtement", "Chaussures", "Autre"}
VALID_CATS   = {"Haut", "Bas", "Robe/Combinaison", "Manteau/Veste", "Autre"}
VALID_STYLES = {
    "Jean", "Pull", "T-shirt", "Crop-top", "Robe", "Combinaison",
    "Chemise", "Sweat", "Hoodie", "Polo", "Veste", "Manteau", "Short",
    "Pantalon", "Legging", "Jupe", "Débardeur", "Cardigan",
    "Blazer", "Parka", "Doudoune", "Sneakers", "Bottines",
    "Sandales", "Mocassins", "Derbies", "Autre",
}
VALID_SEXES  = {"Femme", "Homme", "Fille", "Garçon"}
VALID_GENRES = {"Enfant", "Adolescent", "Adulte"}

MIN_PRICE    = 0.50    # €
MAX_PRICE    = 2000.0  # €
MIN_NAME_LEN = 3
MAX_NAME_LEN = 250


# ═══════════════════════════════════════════════════════════════════════════
#  Nettoyage texte
# ═══════════════════════════════════════════════════════════════════════════

_HTML_TAG     = re.compile(r"<[^>]+>")
_MULTI_SPACE  = re.compile(r"[ \t]+")
_MULTI_NL     = re.compile(r"\n{3,}")
_CTRL_CHARS   = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean_text(text: Optional[str]) -> Optional[str]:
    """Nettoie une chaîne : HTML, whitespace, caractères de contrôle."""
    if not text or not isinstance(text, str):
        return None
    text = _HTML_TAG.sub(" ", text)
    text = _CTRL_CHARS.sub("", text)
    text = text.replace("\xa0", " ")          # non-breaking space
    text = _MULTI_SPACE.sub(" ", text)
    text = _MULTI_NL.sub("\n\n", text)
    text = text.strip()
    return text or None


def normalize_key(name: str, brand: str) -> str:
    """Clé de déduplication normalisée (nom+marque insensible à la casse/accents)."""
    def _norm(s: str) -> str:
        s = s.lower().strip()
        s = unicodedata.normalize("NFD", s)
        s = "".join(c for c in s if unicodedata.category(c) != "Mn")
        s = re.sub(r"[^a-z0-9 ]", "", s)
        s = re.sub(r"\s+", " ", s).strip()
        return s
    return f"{_norm(name)}|{_norm(brand)}"


# ═══════════════════════════════════════════════════════════════════════════
#  Validation d'un enregistrement
# ═══════════════════════════════════════════════════════════════════════════

def validate(record: dict) -> Tuple[bool, List[str], List[str]]:
    """
    Valide et nettoie un enregistrement Silver.
    Retourne (is_valid, errors, warnings).
      - errors  → enregistrement rejeté
      - warnings → corrigé mais conservé (loggé dans _silver_flags)
    """
    errors   = []
    warnings = []
    r        = record  # alias court

    # ── Nom ───────────────────────────────────────────────────────────────
    name = clean_text(r.get("name"))
    if not name:
        errors.append("name_missing")
    elif len(name) < MIN_NAME_LEN:
        errors.append(f"name_too_short({len(name)})")
    elif len(name) > MAX_NAME_LEN:
        warnings.append(f"name_truncated({len(name)}→{MAX_NAME_LEN})")
        name = name[:MAX_NAME_LEN].rsplit(" ", 1)[0]
    r["name"] = name

    # ── Marque ────────────────────────────────────────────────────────────
    if not r.get("brand_source"):
        errors.append("brand_missing")

    # ── Type / Catégorie / Style ──────────────────────────────────────────
    for field, valid_set in [
        ("type",      VALID_TYPES),
        ("categorie", VALID_CATS),
        ("style",     VALID_STYLES),
    ]:
        val = r.get(field)
        if val is not None and val not in valid_set:
            warnings.append(f"{field}_invalid({val!r}→None)")
            r[field] = None

    # ── Sexe / Genre ──────────────────────────────────────────────────────
    for field, valid_set in [("sexe", VALID_SEXES), ("genre", VALID_GENRES)]:
        val = r.get(field)
        if val is not None and val not in valid_set:
            warnings.append(f"{field}_invalid({val!r}→None)")
            r[field] = None

    # ── Prix ──────────────────────────────────────────────────────────────
    price = r.get("price_value")
    if price is not None:
        try:
            price = float(price)
            if price < MIN_PRICE:
                warnings.append(f"price_too_low({price}→None)")
                r["price_value"] = None
            elif price > MAX_PRICE:
                warnings.append(f"price_too_high({price}→None)")
                r["price_value"] = None
            else:
                r["price_value"] = round(price, 2)
        except (ValueError, TypeError):
            warnings.append("price_not_numeric→None")
            r["price_value"] = None

    # ── Description ───────────────────────────────────────────────────────
    r["description"] = clean_text(r.get("description"))

    # ── Tailles ───────────────────────────────────────────────────────────
    for field in ("taille", "sizes"):
        val = r.get(field)
        if val is not None and not isinstance(val, list):
            warnings.append(f"{field}_not_list→[]")
            r[field] = []

    # ── URL ───────────────────────────────────────────────────────────────
    url = (r.get("url") or "").strip()
    if url and not url.startswith("http"):
        warnings.append("url_invalid→None")
        r["url"] = None

    is_valid = len(errors) == 0
    return is_valid, errors, warnings


# ═══════════════════════════════════════════════════════════════════════════
#  Pipeline Silver
# ═══════════════════════════════════════════════════════════════════════════

def clean(input_path: Path, output_path: Path) -> dict:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    seen_urls:  set = set()
    seen_names: set = set()

    rejection_counts: defaultdict = defaultdict(int)
    warning_counts:   defaultdict = defaultdict(int)

    total = written = rejected = deduped = 0

    with open(input_path, encoding="utf-8") as inp, \
         open(output_path, "w", encoding="utf-8") as out:

        for line in inp:
            line = line.strip()
            if not line:
                continue
            total += 1
            record = json.loads(line)

            # ── Déduplication URL ─────────────────────────────────────────
            url = (record.get("url") or "").strip()
            if url and url in seen_urls:
                rejection_counts["duplicate_url"] += 1
                deduped += 1
                rejected += 1
                continue
            if url:
                seen_urls.add(url)

            # ── Déduplication nom+marque ──────────────────────────────────
            name_key = normalize_key(
                record.get("name") or "",
                record.get("brand_source") or "",
            )
            if name_key in seen_names:
                rejection_counts["duplicate_name_brand"] += 1
                deduped += 1
                rejected += 1
                continue
            seen_names.add(name_key)

            # ── Validation + nettoyage ────────────────────────────────────
            is_valid, errors, warnings = validate(record)

            if not is_valid:
                for e in errors:
                    rejection_counts[e] += 1
                rejected += 1
                continue

            for w in warnings:
                warning_counts[w.split("(")[0]] += 1

            # ── Métadonnées Silver ────────────────────────────────────────
            record["_layer"]        = "silver"
            record["_silver_flags"] = warnings if warnings else []

            out.write(json.dumps(record, ensure_ascii=False) + "\n")
            written += 1

    stats = {
        "layer":            "silver",
        "input_path":       str(input_path),
        "output_path":      str(output_path),
        "total_read":       total,
        "written":          written,
        "rejected":         rejected,
        "deduped":          deduped,
        "rejection_reasons": dict(rejection_counts),
        "warnings_applied": dict(warning_counts),
        "retention_rate":   f"{written/total*100:.1f}%" if total else "0%",
    }

    log.info("Nettoyage terminé")
    log.info("  Lus       : %d", total)
    log.info("  Écrits    : %d  (%s conservés)", written, stats["retention_rate"])
    log.info("  Rejetés   : %d  (dont %d doublons)", rejected, deduped)
    if rejection_counts:
        log.info("  Motifs de rejet :")
        for reason, count in sorted(rejection_counts.items(), key=lambda x: -x[1]):
            log.info("    %-35s %d", reason, count)
    if warning_counts:
        log.info("  Corrections appliquées :")
        for w, count in sorted(warning_counts.items(), key=lambda x: -x[1]):
            log.info("    %-35s %d", w, count)

    return stats


def main():
    parser = argparse.ArgumentParser(description="Couche Silver — nettoyage & validation")
    parser.add_argument("--input",  default=str(BRONZE_IN),  help="bronze.jsonl")
    parser.add_argument("--output", default=str(SILVER_OUT), help="silver.jsonl")
    args = parser.parse_args()

    stats = clean(Path(args.input), Path(args.output))
    print(json.dumps(stats, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
