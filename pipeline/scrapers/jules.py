# =============================================================
#  scrapers/jules.py — Scraper Jules (Playwright)
# =============================================================

import re
import logging
from typing import List
from html import unescape

from pipeline.scrapers.base import BaseScraper
from pipeline.models import Product

logger = logging.getLogger(__name__)


# Catalogue Jules : (genre, sexe, url)
JULES_CATALOG = [
    ("Adulte", "Homme", "https://www.jules.com/fr-fr/l/bas/?prefn1=F3_internalCategory&prefv1=Pantalon|Jean&sz=200"),
    ("Adulte", "Homme", "https://www.jules.com/fr-fr/l/hauts/?sz=200"),
    ("Adulte", "Homme", "https://www.jules.com/fr-fr/l/veste/?sz=200"),
    ("Adulte", "Homme", "https://www.jules.com/fr-fr/l/manteau-blouson/?sz=200"),
    ("Adulte", "Homme", "https://www.jules.com/fr-fr/l/chaussures/?sz=200"),
]

JULES_BASE = "https://www.jules.com"


class JulesScraper(BaseScraper):
    """
    Utilise Playwright (headless) car Jules charge ses données
    en JavaScript côté client.
    """
    BRAND_SOURCE = "Jules"

    def run(self) -> List[Product]:
        # Import local pour ne pas imposer Playwright si non utilisé
        from playwright.sync_api import sync_playwright

        all_products: List[Product] = []

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1280, "height": 800})
            page = context.new_page()

            for genre, sexe, list_url in JULES_CATALOG:
                logger.info(f"[Jules] {genre}/{sexe} → {list_url}")

                # ── Chargement de la liste ──────────────────────────
                page.goto(list_url, wait_until="networkidle", timeout=60_000)

                # Scroll pour déclencher le lazy-loading
                for _ in range(5):
                    page.mouse.wheel(0, 1500)
                    page.wait_for_timeout(500)

                # Récupération des URLs produits (filtrées /fr-fr/p/)
                product_urls: List[str] = page.evaluate("""() => {
                    const anchors = Array.from(
                        document.querySelectorAll('a[href*="/fr-fr/p/"]')
                    );
                    const clean = anchors.map(a => a.href.split('#')[0].split('?')[0]);
                    return [...new Set(clean)].filter(u => u.includes('/fr-fr/p/'));
                }""")

                logger.info(f"[Jules] {len(product_urls)} produits détectés")

                # ── Scraping de chaque produit ───────────────────────
                for idx, p_url in enumerate(product_urls, 1):
                    logger.info(f"  [{idx}/{len(product_urls)}] {p_url}")
                    try:
                        page.goto(p_url, wait_until="domcontentloaded", timeout=30_000)
                        page.wait_for_timeout(800)

                        # Variantes de couleur
                        variant_urls: List[str] = []
                        for el in page.query_selector_all("a.color-attribute"):
                            href = el.get_attribute("href") or ""
                            v_url = (
                                href if href.startswith("http")
                                else JULES_BASE + href
                            ).split('?')[0]
                            if v_url not in variant_urls:
                                variant_urls.append(v_url)

                        if not variant_urls:
                            variant_urls = [p_url]

                        for v_url in variant_urls:
                            page.goto(v_url, wait_until="domcontentloaded", timeout=30_000)
                            page.wait_for_timeout(1500)

                            # JSON-LD embarqué
                            data = page.evaluate("""() => {
                                const s = document.querySelector(
                                    'script[type="application/ld+json"]'
                                );
                                return s ? JSON.parse(s.innerText) : null;
                            }""")

                            if not data:
                                continue
                            if isinstance(data, list):
                                data = data[0]

                            raw_name = data.get("name", "Produit")
                            color    = data.get("color", None)
                            desc_raw = data.get("description", "")
                            desc = unescape(re.sub(r'<[^>]+>', '', desc_raw or '')).strip()

                            # Rating
                            rating = None
                            agg = data.get("aggregateRating", {})
                            if agg and agg.get("ratingValue"):
                                try:
                                    rating = float(str(agg["ratingValue"]).replace(',', '.'))
                                except ValueError:
                                    pass

                            # Prix
                            offer = data.get("offers", {})
                            price_val = None
                            currency  = offer.get("priceCurrency", "EUR")
                            try:
                                price_val = float(str(offer.get("price", 0)).replace(',', '.'))
                            except (ValueError, TypeError):
                                pass

                            # Tailles disponibles
                            raw_sizes: List[str] = page.evaluate("""() => {
                                const selectors = [
                                    '.size-attribute .label',
                                    '.size-btn',
                                    '[data-attr="size"] .selectable',
                                    '[data-attr="size"] button',
                                    '.attribute-size .swatch-circle',
                                    'button[data-size]',
                                    '.sizes .size',
                                ];
                                for (const sel of selectors) {
                                    const els = Array.from(document.querySelectorAll(sel));
                                    if (els.length > 0) {
                                        return els.map(e => e.innerText.trim()).filter(t => t.length > 0);
                                    }
                                }
                                return [];
                            }""")
                            
                            # Image
                            images = data.get("image", [])
                            image  = images[0] if isinstance(images, list) and images else (
                                images if isinstance(images, str) else None
                            )

                            # Déduction type
                            is_shoe = any(
                                k in raw_name.lower()
                                for k in ["chaussure", "basket", "bottine", "derby", "mocassin", "boot", "espadrille"]
                            )
                            p_type = "Chaussures" if is_shoe else "Vêtement"

                            product = Product(
                                name        = f"{raw_name} - {color}" if color else raw_name,
                                price_value = price_val,
                                currency    = currency,
                                description = desc,
                                genre       = genre,
                                sexe        = sexe,
                                sizes       = raw_sizes if is_shoe else [],
                                taille      = [] if is_shoe else raw_sizes,
                                color       = color,
                                rating      = rating,
                                type        = p_type,
                                categorie   = self.infer_categorie(raw_name, desc, p_type),
                                style       = self.infer_style(raw_name, desc),
                                image       = image,
                                url         = v_url,
                                brand_source= self.BRAND_SOURCE,
                            )
                            all_products.append(product)
                            logger.info(f"      ✓ {raw_name} ({color})")

                    except Exception as exc:
                        logger.warning(f"  ✗ Erreur produit Jules : {exc}")

            browser.close()

        logger.info(f"[Jules] Total : {len(all_products)} produits")
        return all_products
