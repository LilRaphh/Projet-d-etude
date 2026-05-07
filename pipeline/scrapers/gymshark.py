# =============================================================
#  scrapers/gymshark.py — Scraper Gymshark (hybride Playwright + requests)
#
#  Site : gymshark.com (catalogue international, USD)
#  Architecture : Next.js SSR headless (ex-Shopify)
#
#  Stratégie :
#    1. Playwright → pages de collection (produits chargés en JS)
#       pour collecter les URLs produit
#    2. requests.get → pages produit individuelles (SSR)
#       → __NEXT_DATA__ embarqué dans le HTML initial
#          props.pageProps.productData.product  : données du variant courant
#          props.pageProps.productData.variants : devise (currencyCode)
# =============================================================

import re
import json
import logging
from html import unescape
from typing import List, Optional

from pipeline.scrapers.base import BaseScraper
from pipeline.models import Product

logger = logging.getLogger(__name__)

BASE_URL = "https://www.gymshark.com"

GYMSHARK_CATALOG = [
    ("Adulte", "Homme", "/collections/t-shirts-tops/mens"),
    ("Adulte", "Homme", "/collections/hoodies-sweatshirts/mens"),
    ("Adulte", "Homme", "/collections/joggers/mens"),
    ("Adulte", "Homme", "/collections/shorts/mens"),
    ("Adulte", "Homme", "/collections/jackets/mens"),
    ("Adulte", "Femme", "/collections/t-shirts-tops/womens"),
    ("Adulte", "Femme", "/collections/leggings/womens"),
    ("Adulte", "Femme", "/collections/sports-bras/womens"),
    ("Adulte", "Femme", "/collections/shorts/womens"),
    ("Adulte", "Femme", "/collections/hoodies-sweatshirts/womens"),
    ("Adulte", "Femme", "/collections/jackets/womens"),
]

VALID_SIZES = {"2XS", "XXS", "XS", "S", "M", "L", "XL", "XXL", "XXXL", "2XL", "3XL", "4XL"}


class GymsharkScraper(BaseScraper):
    BRAND_SOURCE = "Gymshark"

    # ------------------------------------------------------------------
    def _fetch_next_data(self, url: str) -> Optional[dict]:
        """
        Fetch une page produit via HTTP simple (Next.js SSR) et extrait
        __NEXT_DATA__ → props.pageProps.productData
        """
        try:
            resp = self.session.get(url, timeout=15)
            if resp.status_code != 200:
                logger.debug(f"[Gymshark] {resp.status_code} → {url}")
                return None
            m = re.search(
                r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
                resp.text, re.S,
            )
            if not m:
                return None
            nd = json.loads(m.group(1))
            return nd.get("props", {}).get("pageProps", {}).get("productData")
        except Exception as e:
            logger.debug(f"[Gymshark] Erreur fetch {url} : {e}")
            return None

    # ------------------------------------------------------------------
    def _to_product(self, pd: dict, url: str, genre: str, sexe: str) -> Optional[Product]:
        """
        Convertit productData → Product.

        pd.product  : données du variant visible sur cette URL
          .title          → nom produit (sans marque)
          .colour         → couleur du variant
          .price          → prix (int/float)
          .description    → HTML
          .availableSizes → [{"size": "xs", "inStock": true, …}]
          .media          → [{"src": "https://...", "url": "https://..."}]
          .rating         → {"average": 3.8, "count": 71, "range": 5}

        pd.variants[0].currencyCode : devise (ex: "USD")
        """
        p = pd.get("product", {})
        if not p:
            return None

        name = (p.get("title") or "").strip()
        if not name:
            return None

        colour      = (p.get("colour") or "").strip() or None
        description = unescape(re.sub(r"<[^>]+>", " ", p.get("description") or "")).strip()
        price       = p.get("price")
        price_val   = float(price) if price is not None else None

        # Devise depuis le premier variant (USD pour le site international)
        variants  = pd.get("variants", [])
        currency  = variants[0].get("currencyCode", "USD") if variants else "USD"

        # Tailles disponibles (en stock)
        raw_sizes = p.get("availableSizes") or []
        taille    = [
            s["size"].upper()
            for s in raw_sizes
            if s.get("inStock", True)
        ]
        taille = [s for s in taille if s in VALID_SIZES] or taille

        # Image
        media  = p.get("media") or []
        image  = (media[0].get("src") or media[0].get("url")) if media else None

        # Rating
        rating = None
        r = p.get("rating")
        if isinstance(r, dict) and r.get("average"):
            try:
                rating = float(r["average"])
            except (ValueError, TypeError):
                pass
        elif isinstance(r, (int, float)):
            rating = float(r)

        is_shoe = any(k in name.lower() for k in ["shoe", "sneaker", "trainer", "boot", "sandal"])
        p_type  = "Chaussures" if is_shoe else "Vêtement"

        return Product(
            name         = f"{name} - {colour}" if colour else name,
            price_value  = price_val,
            currency     = currency,
            description  = description,
            genre        = genre,
            sexe         = sexe,
            sizes        = [],
            taille       = taille,
            color        = colour,
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
        from playwright.sync_api import sync_playwright

        all_products: List[Product] = []

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1280, "height": 900})
            page    = context.new_page()
            seen_urls: set = set()

            for genre, sexe, collection_path in GYMSHARK_CATALOG:
                list_url = BASE_URL + collection_path
                logger.info(f"[Gymshark] {genre}/{sexe} → {list_url}")

                # ── Collecte des URLs produit via Playwright ─────────
                try:
                    page.goto(list_url, wait_until="networkidle", timeout=60_000)

                    for sel in ["#onetrust-accept-btn-handler", "button[id*='accept']"]:
                        try:
                            page.click(sel, timeout=2_000)
                            page.wait_for_timeout(300)
                            break
                        except Exception:
                            pass

                    for _ in range(8):
                        page.mouse.wheel(0, 2000)
                        page.wait_for_timeout(500)

                    product_urls: List[str] = page.evaluate("""() => {
                        const seen = new Set();
                        const out  = [];
                        document.querySelectorAll('a[href*="/products/"]').forEach(a => {
                            const href = a.href.split('?')[0].split('#')[0];
                            if (!seen.has(href)) { seen.add(href); out.push(href); }
                        });
                        return out;
                    }""")
                    logger.info(f"[Gymshark] {len(product_urls)} URLs détectées")

                except Exception as exc:
                    logger.warning(f"[Gymshark] Erreur listing {list_url} : {exc}")
                    continue

                # ── Fetch produit via requests (SSR / __NEXT_DATA__) ─
                for idx, p_url in enumerate(product_urls, 1):
                    if p_url in seen_urls:
                        continue
                    seen_urls.add(p_url)

                    logger.info(f"  [{idx}/{len(product_urls)}] {p_url}")
                    self.sleep(0.4, 0.9)

                    try:
                        pd = self._fetch_next_data(p_url)
                        if pd:
                            product = self._to_product(pd, p_url, genre, sexe)
                            if product:
                                all_products.append(product)
                                logger.info(
                                    f"      ✓ {product.name[:55]} | "
                                    f"{product.price_value} {product.currency} | "
                                    f"tailles={product.taille}"
                                )
                    except Exception as exc:
                        logger.warning(f"  ✗ Erreur {p_url} : {exc}")

            browser.close()

        logger.info(f"[Gymshark] Total : {len(all_products)} produits")
        return all_products
