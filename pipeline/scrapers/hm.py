# =============================================================
#  scrapers/hm.py — Scraper H&M (Playwright)
#
#  Site : hm.com/fr_fr (catalogue France, EUR)
#  Technique : Playwright headless — chargement JS + scroll infini
#  Données : JSON-LD embarqué sur les pages produit
# =============================================================

import re
import logging
from typing import List
from html import unescape

from pipeline.scrapers.base import BaseScraper
from pipeline.models import Product

logger = logging.getLogger(__name__)

BASE_URL = "https://www2.hm.com"

HM_CATALOG = [
    ("Adulte", "Femme",  f"{BASE_URL}/fr_fr/femme/produits/voir-tout.html"),
    ("Adulte", "Homme",  f"{BASE_URL}/fr_fr/homme/produits/voir-tout.html"),
    ("Enfant", "Fille",  f"{BASE_URL}/fr_fr/kids/shop-enfants-par-genre/filles.html"),
    ("Enfant", "Garçon", f"{BASE_URL}/fr_fr/kids/shop-enfants-par-genre/garcons.html"),
]

# Sélecteurs CSS pour trouver les liens produits H&M
PRODUCT_LINK_SELECTORS = [
    'a[href*="productpage"]',
    'a[href*="/fr_fr/productpage"]',
    'li.product-item a',
    'article a[href*="product"]',
]

# Sélecteurs CSS pour les tailles H&M
SIZE_SELECTORS = [
    '[data-testid="size-option"]:not(.disabled):not([aria-disabled="true"])',
    '.product-detail-size-guide button:not([disabled])',
    '[class*="SizeSelector"] button:not([disabled])',
    'ul.sizes-list li:not(.disabled) button',
    'button.size:not([disabled])',
    '[class*="size-item"]:not([class*="sold-out"]):not([class*="unavailable"])',
]


class HmScraper(BaseScraper):
    """
    Utilise Playwright car H&M charge ses produits via JavaScript et scroll infini.
    Extrait les JSON-LD <script type="application/ld+json"> sur chaque page produit.
    """
    BRAND_SOURCE = "H&M"

    # ------------------------------------------------------------------
    def _collect_product_urls(self, page, list_url: str) -> List[str]:
        """Charge la page de listing, scroll pour charger les produits, retourne les URLs."""
        page.goto(list_url, wait_until="networkidle", timeout=60_000)

        # Fermeture du bandeau cookies OneTrust
        for selector in [
            "#onetrust-accept-btn-handler",
            "button#onetrust-accept-btn-handler",
            "[data-testid='accept-all-cookies']",
            "#didomi-notice-agree-button",
        ]:
            try:
                page.click(selector, timeout=3_000)
                page.wait_for_timeout(500)
                break
            except Exception:
                pass

        # Scroll intensif pour charger le maximum de produits
        for _ in range(15):
            page.mouse.wheel(0, 2500)
            page.wait_for_timeout(700)

        # Extraction des URLs produit
        selector_js = " || ".join([f'document.querySelectorAll("{s}").length > 0' for s in PRODUCT_LINK_SELECTORS])
        product_urls: List[str] = page.evaluate("""(selectors) => {
            const seen = new Set();
            const results = [];
            for (const sel of selectors) {
                document.querySelectorAll(sel).forEach(a => {
                    const href = a.href ? a.href.split('?')[0].split('#')[0] : '';
                    if (href && !seen.has(href)) {
                        seen.add(href);
                        results.push(href);
                    }
                });
            }
            return results;
        }""", PRODUCT_LINK_SELECTORS)

        return product_urls

    # ------------------------------------------------------------------
    def _parse_product_page(self, page, p_url: str, genre: str, sexe: str) -> List[Product]:
        """Visite une page produit et extrait les données via JSON-LD."""
        page.goto(p_url, wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_timeout(1_000)

        data = page.evaluate("""() => {
            const scripts = document.querySelectorAll('script[type="application/ld+json"]');
            for (const s of scripts) {
                try {
                    const d = JSON.parse(s.innerText);
                    const obj = Array.isArray(d) ? d[0] : d;
                    if (obj && obj['@type'] === 'Product') {
                        return obj;
                    }
                } catch(e) {}
            }
            return null;
        }""")

        if not data:
            return []

        name     = data.get("name", "Produit H&M")
        color    = data.get("color") or None
        desc_raw = data.get("description", "")
        desc     = unescape(re.sub(r'<[^>]+>', '', desc_raw or '')).strip()

        # Prix
        offer = data.get("offers", {})
        if isinstance(offer, list):
            offer = offer[0] if offer else {}
        price_val = None
        try:
            price_val = float(str(offer.get("price", 0)).replace(',', '.'))
        except (ValueError, TypeError):
            pass

        # Rating
        rating = None
        agg = data.get("aggregateRating", {})
        if agg and agg.get("ratingValue"):
            try:
                rating = float(str(agg["ratingValue"]).replace(',', '.'))
            except ValueError:
                pass

        # Tailles
        raw_sizes: List[str] = page.evaluate("""(selectors) => {
            for (const sel of selectors) {
                const els = Array.from(document.querySelectorAll(sel));
                if (els.length > 0) {
                    return els
                        .map(e => e.innerText ? e.innerText.trim() : e.textContent.trim())
                        .filter(t => t.length > 0 && t.length < 12);
                }
            }
            return [];
        }""", SIZE_SELECTORS)

        # Image
        images = data.get("image", [])
        image  = images[0] if isinstance(images, list) and images else (
            images if isinstance(images, str) else None
        )

        is_shoe = any(
            k in name.lower()
            for k in ["chaussure", "basket", "sneaker", "espadrille",
                       "boot", "bottine", "sandal", "mocassin", "shoe"]
        )
        p_type = "Chaussures" if is_shoe else "Vêtement"

        return [Product(
            name        = f"{name} - {color}" if color else name,
            price_value = price_val,
            currency    = "EUR",
            description = desc,
            genre       = genre,
            sexe        = sexe,
            sizes       = raw_sizes if is_shoe else [],
            taille      = [] if is_shoe else raw_sizes,
            color       = color,
            rating      = rating,
            type        = p_type,
            categorie   = self.infer_categorie(name, desc, p_type),
            style       = self.infer_style(name, desc),
            image       = image,
            url         = p_url,
            brand_source= self.BRAND_SOURCE,
        )]

    # ------------------------------------------------------------------
    def run(self) -> List[Product]:
        from playwright.sync_api import sync_playwright

        all_products: List[Product] = []

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 1280, "height": 900},
                locale="fr-FR",
            )
            page = context.new_page()

            for genre, sexe, list_url in HM_CATALOG:
                logger.info(f"[H&M] {genre}/{sexe} → {list_url}")

                try:
                    product_urls = self._collect_product_urls(page, list_url)
                    logger.info(f"[H&M] {len(product_urls)} produits détectés")

                    seen_urls: set = set()
                    for idx, p_url in enumerate(product_urls, 1):
                        if p_url in seen_urls:
                            continue
                        seen_urls.add(p_url)

                        logger.info(f"  [{idx}/{len(product_urls)}] {p_url}")
                        try:
                            products = self._parse_product_page(page, p_url, genre, sexe)
                            for p in products:
                                all_products.append(p)
                                logger.info(f"      ✓ {p.name[:50]} ({p.color})")
                        except Exception as exc:
                            logger.warning(f"  ✗ Erreur produit H&M : {exc}")

                except Exception as exc:
                    logger.warning(f"[H&M] Erreur catégorie {list_url} : {exc}")

            browser.close()

        logger.info(f"[H&M] Total : {len(all_products)} produits")
        return all_products
