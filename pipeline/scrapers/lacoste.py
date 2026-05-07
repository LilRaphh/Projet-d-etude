# =============================================================
#  scrapers/lacoste.py — Scraper Lacoste (Playwright)
#
#  Site : lacoste.com/fr (catalogue France, EUR)
#  Technique : Playwright headless — site JS-heavy
#  Données : JSON-LD embarqué sur les pages produit
# =============================================================

import re
import logging
from typing import List
from html import unescape

from pipeline.scrapers.base import BaseScraper
from pipeline.models import Product

logger = logging.getLogger(__name__)

BASE_URL = "https://www.lacoste.com"

LACOSTE_CATALOG = [
    ("Adulte", "Homme",  f"{BASE_URL}/fr/lacoste/homme/vetements/"),
    ("Adulte", "Femme",  f"{BASE_URL}/fr/lacoste/femme/vetements/"),
    ("Enfant", "Fille",  f"{BASE_URL}/fr/lacoste/enfants/fille/vetements/"),
    ("Enfant", "Garçon", f"{BASE_URL}/fr/lacoste/enfants/garcon/vetements/"),
]


class LacosteScraper(BaseScraper):
    """
    Utilise Playwright car le catalogue Lacoste est rendu côté client.
    Extrait les JSON-LD <script type="application/ld+json"> sur chaque page produit.
    """
    BRAND_SOURCE = "Lacoste"

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

            for genre, sexe, list_url in LACOSTE_CATALOG:
                logger.info(f"[Lacoste] {genre}/{sexe} → {list_url}")

                try:
                    page.goto(list_url, wait_until="networkidle", timeout=60_000)

                    # Fermeture du bandeau cookies si présent
                    for selector in [
                        "#onetrust-accept-btn-handler",
                        "[data-testid='cookie-accept']",
                        "button[class*='accept']",
                        "#didomi-notice-agree-button",
                    ]:
                        try:
                            page.click(selector, timeout=2_000)
                            page.wait_for_timeout(400)
                            break
                        except Exception:
                            pass

                    # Scroll pour déclencher le lazy-loading
                    for _ in range(10):
                        page.mouse.wheel(0, 2000)
                        page.wait_for_timeout(600)

                    # Collecte des URLs produit depuis la page de listing
                    product_urls: List[str] = page.evaluate("""() => {
                        const seen = new Set();
                        const results = [];
                        document.querySelectorAll('a[href]').forEach(a => {
                            const href = a.href.split('?')[0].split('#')[0];
                            // Les pages produit Lacoste se terminent en .html
                            // et ne sont pas des pages de catégorie
                            if (
                                href.endsWith('.html') &&
                                href.includes('/fr/lacoste/') &&
                                !seen.has(href)
                            ) {
                                seen.add(href);
                                results.push(href);
                            }
                        });
                        return results;
                    }""")

                    logger.info(f"[Lacoste] {len(product_urls)} produits détectés")

                    for idx, p_url in enumerate(product_urls, 1):
                        logger.info(f"  [{idx}/{len(product_urls)}] {p_url}")
                        try:
                            page.goto(p_url, wait_until="domcontentloaded", timeout=30_000)
                            page.wait_for_timeout(1_000)

                            # Extraction JSON-LD (structured data produit)
                            data = page.evaluate("""() => {
                                const scripts = document.querySelectorAll(
                                    'script[type="application/ld+json"]'
                                );
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
                                continue

                            name     = data.get("name", "Produit Lacoste")
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

                            # Tailles disponibles (non désactivées)
                            raw_sizes: List[str] = page.evaluate("""() => {
                                const selectors = [
                                    '[data-qa="size-selector"] button:not([disabled]):not([aria-disabled="true"])',
                                    '.size-selector__item:not(.size-selector__item--unavailable)',
                                    '[class*="SizeSelector"] button:not([disabled])',
                                    '[class*="size-btn"]:not([disabled])',
                                    'button[data-size]',
                                ];
                                for (const sel of selectors) {
                                    const els = Array.from(document.querySelectorAll(sel));
                                    if (els.length > 0) {
                                        return els.map(e => e.innerText.trim()).filter(t => t.length > 0 && t.length < 10);
                                    }
                                }
                                return [];
                            }""")

                            # Image
                            images = data.get("image", [])
                            image  = images[0] if isinstance(images, list) and images else (
                                images if isinstance(images, str) else None
                            )

                            is_shoe = any(
                                k in name.lower()
                                for k in ["chaussure", "basket", "sneaker", "espadrille",
                                          "boot", "bottine", "sandal", "mocassin"]
                            )
                            p_type = "Chaussures" if is_shoe else "Vêtement"

                            product = Product(
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
                            )
                            all_products.append(product)
                            logger.info(f"      ✓ {name} ({color})")

                        except Exception as exc:
                            logger.warning(f"  ✗ Erreur produit Lacoste : {exc}")

                except Exception as exc:
                    logger.warning(f"[Lacoste] Erreur catégorie {list_url} : {exc}")

            browser.close()

        logger.info(f"[Lacoste] Total : {len(all_products)} produits")
        return all_products
