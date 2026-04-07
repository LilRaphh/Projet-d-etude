# =============================================================
#  scrapers/nike.py — Scraper Nike (Playwright)
# =============================================================

import re
import json
import logging
from typing import List, Optional

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
except ImportError as e:
    raise ImportError("playwright requis : pip install playwright && playwright install chromium") from e

from pipeline.scrapers.base import BaseScraper
from pipeline.models import Product

logger = logging.getLogger(__name__)


NIKE_CATALOG = [
    ("Chaussures", "Adulte", "Homme", "https://www.nike.com/fr/w/hommes-chaussures-nik1zy7ok"),
    ("Chaussures", "Adulte", "Femme", "https://www.nike.com/fr/w/femmes-chaussures-5e1x6zy7ok"),
    ("Vêtement",   "Adulte", "Homme", "https://www.nike.com/fr/w/hommes-vetements-6ymx6znik1"),
    ("Vêtement",   "Adulte", "Femme", "https://www.nike.com/fr/w/femmes-vetements-5e1x6z6ymx6"),
]


class NikeScraper(BaseScraper):
    BRAND_SOURCE = "Nike"

    # ------------------------------------------------------------------
    def _get_product_urls(self, page, catalogue_url: str) -> List[str]:
        """Extrait les URLs produits depuis une page catalogue Nike via Playwright."""
        try:
            page.goto(catalogue_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(4000)
        except PWTimeout:
            logger.warning(f"[Nike] Timeout catalogue : {catalogue_url}")
            return []

        urls = set()

        # Méthode 1 : liens produits dans le DOM
        links = page.query_selector_all("a.product-card__link-overlay")
        for link in links:
            href = link.get_attribute("href") or ""
            if href:
                urls.add("https://www.nike.com" + href if href.startswith("/") else href)

        # Méthode 2 : JSON embarqué dans le HTML
        raw = page.content()
        found = re.findall(r'"productUrl":"(https?://www\.nike\.com[^"]+)"', raw)
        urls.update(found)

        return list(urls)

    # ------------------------------------------------------------------
    def _scrape_product(
        self,
        page,
        url: str,
        genre: str,
        sexe: str,
        p_type: str,
    ) -> Optional[Product]:
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)
        except PWTimeout:
            logger.warning(f"[Nike] Timeout produit : {url}")
            return None

        # Nom
        try:
            name = page.locator("h1").first.inner_text(timeout=5000).strip()
        except Exception:
            name = ""

        # Fallback : extraire le nom depuis l'URL
        if not name:
            try:
                slug = url.split("/t/")[1].split("/")[0]  # ex: "chaussure-air-max-plus-pour-db8pEVry"
                slug = re.sub(r'-pour-\w+$', '', slug)    # supprimer "-pour-XXXXXXX"
                # Supprimer les préfixes de type de produit
                slug = re.sub(r'^(chaussure|chaussures)-de?-?(running|course|route|basket|sport|ville|costume)-?(sur-route-)?', '', slug)
                slug = re.sub(r'^(chaussure|chaussures|veste|pantalon|short|haut|survete?ment|tee?-?shirt|tunique|collant)-', '', slug)
                slug = re.sub(r'^(a-capuche|de?-?running|de?-?fitness|de?-?sport)-', '', slug)
                name = slug.replace("-", " ").title()
            except Exception:
                name = "Inconnu"

        # Prix
        price, currency = None, "EUR"
        try:
            price_text = page.locator("[data-testid='currentPrice-container']").first.inner_text(timeout=5000)
            price, currency = self.parse_price(price_text)
        except Exception:
            pass

        # Description
        description = ""
        try:
            desc = page.locator("[data-testid='product-description']").first.inner_text(timeout=5000)
            description = desc.strip()
        except Exception:
            pass

        # Couleur — on prend seulement le premier coloris
        color = None
        try:
            color_raw = page.locator("[data-testid='product-description-color-description']").first.inner_text(timeout=5000)
            color_raw = color_raw.replace("Couleur affichée :", "").strip()
            # "Noir/Cool Grey/Blanc" → "Noir"
            color = color_raw.split("/")[0].strip()
        except Exception:
            pass

        # Rating
        rating = None
        try:
            rating_text = page.locator("[data-testid='reviews-summary-rating']").first.inner_text(timeout=3000)
            m = re.search(r'(\d+[.,]\d+)', rating_text)
            if m:
                rating = float(m.group(1).replace(',', '.'))
        except Exception:
            pass

        # Tailles — attendre le sélecteur de tailles
        raw_sizes: List[str] = []
        try:
            page.wait_for_selector("[data-testid='pdp-grid-selector-item']", timeout=5000)
            raw_sizes = page.evaluate("""() => {
                const items = document.querySelectorAll("[data-testid='pdp-grid-selector-item']");
                return Array.from(items)
                    .map(el => el.querySelector('label')?.innerText?.trim() || el.innerText.trim())
                    .filter(t => t.length > 0);
            }""")
        except Exception:
            # Fallback : chercher d'autres sélecteurs de tailles Nike
            try:
                raw_sizes = page.evaluate("""() => {
                    const selectors = [
                        '[data-testid="size-selector"] button',
                        '.size-grid-dropdown__item',
                        '[aria-label*="Taille"]',
                        'button[aria-label*="EU"]',
                    ];
                    for (const sel of selectors) {
                        const els = Array.from(document.querySelectorAll(sel));
                        if (els.length > 0)
                            return els.map(e => e.innerText.trim()).filter(t => t.length > 0);
                    }
                    return [];
                }""")
            except Exception:
                raw_sizes = []

        # Image
        image = None
        try:
            img = page.locator("img[data-testid='hero-image']").first
            image = img.get_attribute("src", timeout=3000)
        except Exception:
            try:
                img = page.locator("img").first
                image = img.get_attribute("src", timeout=3000)
            except Exception:
                pass

        is_shoe = (p_type == "Chaussures")

        # Conversion tailles chaussures en int si possible
        if is_shoe:
            sizes_int = []
            for s in raw_sizes:
                m = re.search(r'(\d+[.,]?\d*)', s)
                if m:
                    try:
                        sizes_int.append(int(float(m.group(1).replace(',', '.'))))
                    except Exception:
                        pass
            sizes_out = sizes_int if sizes_int else []
            taille_out = []
        else:
            sizes_out = []
            # Filtrer les tailles vêtements valides
            valid = {"XS", "S", "M", "L", "XL", "XXL", "XXXL", "3XL", "4XL"}
            taille_out = [s for s in raw_sizes if s.upper() in valid] or raw_sizes

        return Product(
            name         = name,
            price_value  = price,
            currency     = currency or "EUR",
            description  = description,
            genre        = genre,
            sexe         = sexe,
            sizes        = sizes_out,
            taille       = taille_out,
            color        = color,
            rating       = rating,
            type         = p_type,
            categorie    = self.infer_categorie(name, description, p_type),
            style        = self.infer_style(name, description),
            image        = image,
            url          = url,
            brand_source = self.BRAND_SOURCE,
        )

    # ------------------------------------------------------------------
    def run(self) -> List[Product]:
        all_products: List[Product] = []

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                ),
                locale="fr-FR",
            )
            page = context.new_page()

            for p_type, genre, sexe, cat_url in NIKE_CATALOG:
                logger.info(f"[Nike] Catalogue : {p_type} / {sexe}")

                product_urls = self._get_product_urls(page, cat_url)
                logger.info(f"[Nike] {len(product_urls)} URLs trouvées")
                product_urls = product_urls

                for url in product_urls:
                    self.sleep(4.0, 8.0)
                    try:
                        product = self._scrape_product(page, url, genre, sexe, p_type)
                        if product:
                            all_products.append(product)
                            logger.info(f"  ✓ {product.name}")
                    except Exception as e:
                        logger.warning(f"[Nike] Erreur sur {url} : {e}")
                        try:
                            page.close()
                            page = context.new_page()
                        except Exception:
                            pass
                        continue

                self.sleep(8.0, 15.0)

            browser.close()

        logger.info(f"[Nike] Total : {len(all_products)} produits")
        return all_products