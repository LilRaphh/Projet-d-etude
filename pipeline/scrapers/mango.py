# =============================================================
#  scrapers/mango.py — Scraper Mango
# =============================================================

import re
import logging
from typing import List, Optional

from pipeline.scrapers.base import BaseScraper
from pipeline.models import Product

logger = logging.getLogger(__name__)


# Catalogue : (genre_raw, sexe_raw, style_hint, url)
MANGO_CATALOG = [
    # Femme
    ("Adulte",          "Femme",   "Pull",    "https://shop.mango.com/fr/fr/c/femme/pulls-et-cardigans_f9a8c868"),
    ("Adulte",          "Femme",   "Manteau", "https://shop.mango.com/fr/fr/c/femme/manteau_d1b967bc"),
    ("Adulte",          "Femme",   "Robe",    "https://shop.mango.com/fr/fr/c/femme/robes-et-combinaisons_e6bb8705"),
    ("Adulte",          "Femme",   "Sneakers","https://shop.mango.com/fr/fr/c/femme/chaussure_826dba0a"),
    # Homme
    ("Adulte",          "Homme",   "Manteau", "https://shop.mango.com/fr/fr/c/homme/manteaux_3a5ade78"),
    ("Adulte",          "Homme",   "Pull",    "https://shop.mango.com/fr/fr/c/homme/gilets-et-pull-overs_89e09112"),
    ("Adulte",          "Homme",   "Pantalon","https://shop.mango.com/fr/fr/c/homme/pantalons_b126cc9c"),
    ("Adulte",          "Homme",   "Veste",   "https://shop.mango.com/fr/fr/c/homme/vestes_b5a3a3f6"),
    # Adolescent
    ("Adolescent",     "Femme",   "Manteau", "https://shop.mango.com/fr/fr/c/teen/teena/manteaux-et-vestes_8573c85c"),
    ("Adolescent",     "Femme",   "Pull",    "https://shop.mango.com/fr/fr/c/teen/teena/pulls-et-cardigans_48d543e1"),
    ("Adolescent",     "Femme",   "Jean",    "https://shop.mango.com/fr/fr/c/teen/teena/jeans_98b73358"),
    ("Adolescent",     "Femme",   "Robe",    "https://shop.mango.com/fr/fr/c/teen/teena/robes-et-combinaisons_b05dc3e4"),
    # Enfant Fille
    ("Enfant",         "Fille",   "Manteau", "https://shop.mango.com/fr/fr/c/enfants/fille/manteaux-et-vestes_39dace35"),
    ("Enfant",         "Fille",   "Jean",    "https://shop.mango.com/fr/fr/c/enfants/fille/jeans_a9530c83"),
    # Enfant Garçon
    ("Enfant",         "Garçon",  "Manteau", "https://shop.mango.com/fr/fr/c/enfants/garcon/manteaux-et-vestes_3311d26e"),
    ("Enfant",         "Garçon",  "T-shirt", "https://shop.mango.com/fr/fr/c/enfants/garcon/t-shirts_d4d4580c"),
]

TRASH_NAMES = {
    "disponible plus", "selection", "performance",
    "exclusivité internet", "essentials", "vêtement", "selectioned",
    "new now", "events", "celebration",
}


class MangoScraper(BaseScraper):
    BRAND_SOURCE = "Mango"
    BASE_URL = "https://shop.mango.com"

    # ------------------------------------------------------------------
    def _clean_name(self, raw: str, url: str) -> str:
        raw_lower = raw.lower()
        # Filtre si le nom contient un tag marketing
        if any(trash in raw_lower for trash in TRASH_NAMES) or len(raw) < 3:
            m = re.search(r'/([^/]+)_\d+', url)
            if m:
                return m.group(1).replace('-', ' ').capitalize()
            return None  # ← None = on ignore ce produit
        return raw

    # ------------------------------------------------------------------
    def _scrape_product_page(self, url: str) -> dict:
        """Retourne les détails bruts d'une page produit Mango."""
        soup = self.get(url)
        if not soup:
            return {}

        # Prix
        price_tag = (
            soup.find('span', class_=re.compile(r"finalPrice|SinglePrice_finalPrice", re.I))
            or soup.find('span', class_=re.compile(r"SinglePrice_center", re.I))
        )
        price, currency = None, "EUR"
        if price_tag:
            price, currency = self.parse_price(price_tag.get_text())

        # Couleur
        color = None
        sel = soup.find('span', class_=re.compile(r"selected", re.I))
        if sel and sel.find('img'):
            color = (
                sel.find('img').get('alt', '')
                .replace('Couleur ', '')
                .replace(' sélectionnée', '')
                .strip()
            )

        # Tailles
        raw_sizes = []
        for item in soup.find_all(['div', 'button'], class_=re.compile(r"sizeItem|sizePicker", re.I)):
            if item.find(class_=re.compile(r"notifyMe|unavailable", re.I)):
                continue
            s_tag = item.find(class_=re.compile(r"textActionM|size-label", re.I))
            if s_tag:
                val = s_tag.get_text(strip=True)
                if val and val not in raw_sizes:
                    raw_sizes.append(val)

        # Description
        desc_meta = soup.find('meta', {'property': 'og:description'})
        desc = desc_meta['content'] if desc_meta else ""

        # Image
        og_img = soup.find('meta', {'property': 'og:image'})
        image = og_img['content'] if og_img else None

        return {
            "price": price,
            "currency": currency,
            "color": color,
            "raw_sizes": raw_sizes,
            "description": desc,
            "image": image,
        }

    # ------------------------------------------------------------------
    def _scrape_category(
        self,
        cat_url: str,
        genre: str,
        sexe: str,
        style_hint: str,
    ) -> List[Product]:
        """Scrape une page de liste Mango et retourne les produits."""
        logger.info(f"[Mango] {genre} / {sexe} / {style_hint}")

        soup = self.get(cat_url, timeout=20)
        if not soup:
            return []

        products: List[Product] = []
        seen: set = set()

        for link in soup.find_all('a', href=re.compile(r'/p/')):
            href = link.get('href', '')
            full_url = href if href.startswith('http') else self.BASE_URL + href
            clean_url = full_url.split('?')[0]

            if clean_url in seen:
                continue
            seen.add(clean_url)

            # Nom brut
            tag = link.find(['p', 'span']) or link.find_next(['p', 'span'])
            raw_name = tag.get_text(strip=True) if tag else "Vêtement"
            name = self._clean_name(raw_name, clean_url)
            if name is None:
                continue

            # Thumbnail dans la liste
            img_tag = link.find('img')
            thumb = img_tag.get('src') if img_tag else None

            self.sleep(0.5, 1.2)
            details = self._scrape_product_page(clean_url)

            if not details.get('price') and not details.get('raw_sizes'):
                continue   # produit vide → on ignore

            # Détermine le type
            is_shoe = style_hint in ("Sneakers", "Bottines", "Sandales", "Mocassins", "Derbies")
            p_type = "Chaussures" if is_shoe else "Vêtement"

            product = Product(
                name        = name,
                price_value = details.get('price'),
                currency    = details.get('currency', 'EUR'),
                description = details.get('description', ''),
                genre       = genre,
                sexe        = sexe,
                sizes       = details['raw_sizes'] if is_shoe else [],
                taille      = [] if is_shoe else details['raw_sizes'],
                color       = details.get('color'),
                rating      = None,   # Mango ne l'expose pas
                type        = p_type,
                categorie   = self.infer_categorie(name, details.get('description', ''), p_type),
                style       = self.infer_style(name, details.get('description', '')),
                image       = details.get('image') or thumb,
                url         = clean_url,
                brand_source= self.BRAND_SOURCE,
            )
            products.append(product)
            logger.info(f"  ✓ {name}")

        return products

    # ------------------------------------------------------------------
    def run(self) -> List[Product]:
        all_products: List[Product] = []

        for genre, sexe, style_hint, url in MANGO_CATALOG:
            cat_products = self._scrape_category(url, genre, sexe, style_hint)
            all_products.extend(cat_products)
            logger.info(f"[Mango] +{len(cat_products)} produits ({genre}/{sexe}/{style_hint})")
            self.sleep(1.0, 2.5)

        logger.info(f"[Mango] Total : {len(all_products)} produits")
        return all_products
