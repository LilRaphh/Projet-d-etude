#!/usr/bin/env python3
"""
finetune/prepare_dataset.py
Génère un dataset JSONL d'instruction-tuning depuis la couche Gold de la
pipeline Medallion (finetune/data/gold.jsonl).
Fallback automatique vers SmartWear_DB.json si Gold n'existe pas encore.

Usage :
    python -m finetune.prepare_dataset               # lit depuis gold.jsonl
    python -m finetune.prepare_dataset --db finetune/data/gold.jsonl
    python -m finetune.prepare_dataset --val-split 0.1

Sortie : finetune/data/train.jsonl + finetune/data/val.jsonl
Format : ShareGPT  {"conversations": [{"from":"human","value":"..."},{"from":"gpt","value":"..."}]}
"""
import argparse
import json
import os
import random
from pathlib import Path
from typing import List, Dict

# ── Chemins ──────────────────────────────────────────────────────────────────
ROOT       = Path(__file__).parent.parent
GOLD_PATH  = Path(__file__).parent / "data" / "gold.jsonl"
DB_PATH    = ROOT / "pipeline" / "output" / "SmartWear_DB.json"
OUTPUT_DIR = Path(__file__).parent / "data"

# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt_price(p: dict) -> str:
    if p.get("price_value") is None:
        return "prix non disponible"
    currency = p.get("currency") or "EUR"
    symbol = "€" if currency == "EUR" else "$"
    return f"{p['price_value']:.2f} {symbol}"


def _fmt_sizes(p: dict) -> str:
    sizes = p.get("taille") or []
    if not sizes:
        sizes = [str(s) for s in (p.get("sizes") or [])]
    return ", ".join(sizes) if sizes else "tailles non précisées"


def _product_summary(p: dict) -> str:
    """Résumé textuel compact d'un produit."""
    parts = [f"**{p['name']}** ({p.get('brand_source', '?')})"]
    if p.get("style"):
        parts.append(f"Style : {p['style']}")
    if p.get("categorie"):
        parts.append(f"Catégorie : {p['categorie']}")
    if p.get("color"):
        parts.append(f"Couleur : {p['color']}")
    parts.append(f"Prix : {_fmt_price(p)}")
    if p.get("description"):
        desc = p["description"][:120].rstrip()
        if len(p["description"]) > 120:
            desc += "…"
        parts.append(f"Description : {desc}")
    return " | ".join(parts)


# ═════════════════════════════════════════════════════════════════════════════
#  GÉNÉRATEURS D'EXEMPLES
# ═════════════════════════════════════════════════════════════════════════════

def gen_classification(products: List[dict]) -> List[dict]:
    """
    Type 1 — Classification
    Entrée : nom + description + marque
    Sortie : JSON {type, categorie, style, sexe, genre, color}
    """
    examples = []
    for p in products:
        if not (p.get("type") and p.get("categorie") and p.get("style")):
            continue

        human = (
            f"Classifie ce produit de mode.\n\n"
            f"Nom : {p['name']}\n"
            f"Marque : {p.get('brand_source', 'inconnue')}\n"
        )
        if p.get("description"):
            human += f"Description : {p['description']}\n"

        answer = {
            "type":      p.get("type"),
            "categorie": p.get("categorie"),
            "style":     p.get("style"),
            "sexe":      p.get("sexe"),
            "genre":     p.get("genre"),
            "couleur":   p.get("color"),
        }
        answer = {k: v for k, v in answer.items() if v is not None}

        examples.append(_conv(human, json.dumps(answer, ensure_ascii=False, indent=2)))
    return examples


def gen_style_search(products: List[dict]) -> List[dict]:
    """
    Type 2 — Recherche par critères de style
    Regroupe les produits par (sexe, style, categorie) et génère des requêtes naturelles.
    """
    examples = []

    # Index par style
    by_style: Dict[str, List[dict]] = {}
    for p in products:
        key = (p.get("sexe") or ""), (p.get("style") or ""), (p.get("categorie") or "")
        by_style.setdefault(key, []).append(p)

    for (sexe, style, cat), group in by_style.items():
        if not style or not cat or len(group) < 2:
            continue

        sample = random.sample(group, min(4, len(group)))

        # Variantes de questions pour diversifier
        templates = [
            f"Je cherche {_article(style)} {style.lower()} {_pour_genre(sexe)} à acheter. Qu'est-ce que tu as ?",
            f"Montre-moi des {style.lower()}s {_pour_genre(sexe)} disponibles.",
            f"Quelles options de {style.lower()} {_pour_genre(sexe)} avez-vous en stock ?",
            f"Je veux un {style.lower()} {_pour_genre(sexe)}, quelles références sont disponibles ?",
        ]
        human = random.choice(templates)

        lines = [f"Voici les {style.lower()}s {_pour_genre(sexe)} disponibles :\n"]
        for i, p in enumerate(sample, 1):
            lines.append(f"{i}. {_product_summary(p)}")
            if p.get("url"):
                lines.append(f"   → {p['url']}")
        answer = "\n".join(lines)

        examples.append(_conv(human, answer))

    return examples


def gen_outfit_advice(products: List[dict]) -> List[dict]:
    """
    Type 3 — Conseil outfit : assembler haut + bas + chaussures
    """
    examples = []

    hauts     = [p for p in products if p.get("categorie") == "Haut" and p.get("sexe")]
    bas_list  = [p for p in products if p.get("categorie") == "Bas" and p.get("sexe")]
    chaussures = [p for p in products if p.get("type") == "Chaussures" and p.get("sexe")]

    for _ in range(min(600, len(hauts))):
        haut = random.choice(hauts)
        sexe = haut.get("sexe", "")
        bas_match  = [b for b in bas_list  if b.get("sexe") == sexe] or bas_list
        shoe_match = [s for s in chaussures if s.get("sexe") == sexe] or chaussures

        if not bas_match or not shoe_match:
            continue

        bas  = random.choice(bas_match)
        shoe = random.choice(shoe_match)

        occasions = ["quotidien", "travail", "soirée", "week-end", "sport décontracté"]
        occasion  = random.choice(occasions)
        saison    = random.choice(["printemps", "été", "automne", "hiver"])

        human = (
            f"Compose-moi une tenue complète pour {occasion} en {saison} "
            f"{'pour une femme' if sexe == 'Femme' else 'pour un homme' if sexe == 'Homme' else ''}."
        )

        total = sum(
            p.get("price_value") or 0 for p in [haut, bas, shoe]
        )
        haut_style = (haut.get('style') or 'haut').lower()
        bas_style  = (bas.get('style') or 'bas').lower()
        answer = (
            f"Voici une tenue complète pour {occasion} en {saison} :\n\n"
            f"**Haut** — {_product_summary(haut)}\n\n"
            f"**Bas** — {_product_summary(bas)}\n\n"
            f"**Chaussures** — {_product_summary(shoe)}\n\n"
            f"Budget total estimé : {total:.2f} €\n\n"
            f"Cette tenue associe {haut_style} et "
            f"{bas_style} pour un look adapté à {occasion}."
        )
        examples.append(_conv(human, answer))

    return examples


def gen_product_qa(products: List[dict]) -> List[dict]:
    """
    Type 4 — Q/R sur un produit spécifique (taille, prix, description)
    """
    examples = []
    questions_templates = [
        ("Quelles tailles sont disponibles pour {name} de {brand} ?",
         "Le produit **{name}** ({brand}) est disponible en : {sizes}."),
        ("Quel est le prix de {name} chez {brand} ?",
         "**{name}** chez {brand} est proposé à {price}."),
        ("Décris-moi {name} de {brand}.",
         "**{name}** de {brand} : {desc} — {price}, disponible en {sizes}."),
        ("Est-ce que {name} de {brand} est adapté pour {sexe} ?",
         "Oui, **{name}** de {brand} est conçu pour {sexe_full}. "
         "Il s'agit d'un {style} ({cat}), proposé à {price}."),
    ]

    sampled = random.sample(products, min(500, len(products)))
    for p in sampled:
        name  = p["name"]
        brand = p.get("brand_source", "cette marque")
        price = _fmt_price(p)
        sizes = _fmt_sizes(p)
        desc  = (p.get("description") or "Pas de description disponible.")[:200]
        sexe  = p.get("sexe") or "tous"
        sexe_full = {"Femme": "les femmes", "Homme": "les hommes",
                     "Fille": "les filles", "Garçon": "les garçons"}.get(sexe, sexe)
        style = p.get("style") or "article"
        cat   = p.get("categorie") or "vêtement"

        q_tmpl, a_tmpl = random.choice(questions_templates)
        human  = q_tmpl.format(name=name, brand=brand, sexe=sexe)
        answer = a_tmpl.format(
            name=name, brand=brand, price=price, sizes=sizes,
            desc=desc, sexe=sexe, sexe_full=sexe_full, style=style, cat=cat,
        )
        examples.append(_conv(human, answer))

    return examples


def gen_brand_knowledge(products: List[dict]) -> List[dict]:
    """
    Type 5 — Connaissance des marques (catalogue, positionnement)
    """
    examples = []
    brands: Dict[str, List[dict]] = {}
    for p in products:
        b = p.get("brand_source")
        if b:
            brands.setdefault(b, []).append(p)

    for brand, items in brands.items():
        styles   = list({p["style"]    for p in items if p.get("style")})
        cats     = list({p["categorie"] for p in items if p.get("categorie")})
        sexes    = list({p["sexe"]     for p in items if p.get("sexe")})
        prices   = [p["price_value"] for p in items if p.get("price_value")]
        avg_price = sum(prices) / len(prices) if prices else 0

        questions = [
            f"Que propose la marque {brand} dans ta base de données ?",
            f"Parle-moi de l'offre {brand}.",
            f"Qu'est-ce que je peux trouver chez {brand} ?",
        ]
        human = random.choice(questions)
        answer = (
            f"**{brand}** propose {len(items)} articles dans notre catalogue.\n\n"
            f"- Styles disponibles : {', '.join(styles[:8])}\n"
            f"- Catégories : {', '.join(cats)}\n"
            f"- Public cible : {', '.join(sexes)}\n"
            f"- Prix moyen : {avg_price:.2f} €\n\n"
            f"Exemple de produits : "
            + " | ".join(p["name"] for p in random.sample(items, min(3, len(items))))
        )
        examples.append(_conv(human, answer))

    return examples


# ── Utilitaires ───────────────────────────────────────────────────────────────

def _conv(human: str, gpt: str) -> dict:
    return {
        "conversations": [
            {"from": "human", "value": human.strip()},
            {"from": "gpt",   "value": gpt.strip()},
        ]
    }


def _article(word: str) -> str:
    vowels = "aeiouAEIOUéèêëàâîï"
    return "un" if word and word[0] not in vowels else "un"


def _pour_genre(sexe: str) -> str:
    return {"Femme": "pour femme", "Homme": "pour homme",
            "Fille": "pour fille", "Garçon": "pour garçon"}.get(sexe, "")


# ═════════════════════════════════════════════════════════════════════════════
#  MAIN
# ═════════════════════════════════════════════════════════════════════════════

def build_dataset(db_path: Path) -> List[dict]:
    """
    Charge les produits depuis db_path.
    Accepte JSON (SmartWear_DB.json) ou JSONL (gold.jsonl).
    """
    with open(db_path, encoding="utf-8") as f:
        first_char = f.read(1)
        f.seek(0)
        if first_char == "[":
            # JSON array (SmartWear_DB.json brut)
            products = json.load(f)
        else:
            # JSONL (gold.jsonl, silver.jsonl…)
            products = [json.loads(line) for line in f if line.strip()]

    print(f"Produits chargés : {len(products)}")

    random.seed(42)
    all_examples: List[dict] = []

    generators = [
        ("Classification",    gen_classification),
        ("Recherche style",   gen_style_search),
        ("Conseil outfit",    gen_outfit_advice),
        ("Q/R produit",       gen_product_qa),
        ("Connaissance marque", gen_brand_knowledge),
    ]

    for label, fn in generators:
        ex = fn(products)
        print(f"  {label:<22} → {len(ex):>5} exemples")
        all_examples.extend(ex)

    random.shuffle(all_examples)
    print(f"\nTotal : {len(all_examples)} exemples")
    return all_examples


def split_and_save(examples: List[dict], output_dir: Path, val_ratio: float = 0.05):
    output_dir.mkdir(parents=True, exist_ok=True)

    cut = int(len(examples) * (1 - val_ratio))
    train = examples[:cut]
    val   = examples[cut:]

    train_path = output_dir / "train.jsonl"
    val_path   = output_dir / "val.jsonl"

    for path, data in [(train_path, train), (val_path, val)]:
        with open(path, "w", encoding="utf-8") as f:
            for row in data:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"\nDataset sauvegardé :")
    print(f"  Train : {len(train):>5} exemples → {train_path}")
    print(f"  Val   : {len(val):>5} exemples → {val_path}")
    return train_path, val_path


def main():
    # Résolution du chemin source par défaut : Gold > DB brute
    default_db = str(GOLD_PATH) if GOLD_PATH.exists() else str(DB_PATH)
    source_label = "gold.jsonl" if GOLD_PATH.exists() else "SmartWear_DB.json (Gold absent, lance d'abord: python -m finetune.medallion)"

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--db",
        default=default_db,
        help=f"Source des produits (défaut : {source_label})",
    )
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR), help="Dossier de sortie")
    parser.add_argument("--val-split",  default=0.05, type=float, help="Fraction de validation (défaut 5%%)")
    args = parser.parse_args()

    source = Path(args.db)
    if not source.exists():
        raise SystemExit(f"Source introuvable : {source}\nLance d'abord : python -m finetune.medallion")

    print(f"Source : {source}")
    examples = build_dataset(source)
    split_and_save(examples, Path(args.output_dir), args.val_split)


if __name__ == "__main__":
    main()
