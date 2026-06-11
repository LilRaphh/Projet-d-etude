# =============================================================
#  scrapers/asos.py — Scraper ASOS (Playwright, headless=False)
#
#  Site    : asos.com/fr (catalogue France, EUR)
#  Méthode : Playwright en mode visible (ASOS bloque headless)
#            Sur Linux sans display → Xvfb via pyvirtualdisplay
#  Données :
#    - Listing  → sélecteurs DOM a[href*="/prd/"]
#    - Produit  → window.asos.pdp.config.product (JSON dans le HTML)
#    - Prix     → API v4/stockprice (fetch depuis le contexte navigateur)
# =============================================================

import re
import json
import logging
import os
import sys
from typing import List, Optional

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
except ImportError as e:
    raise ImportError("playwright requis : pip install playwright && playwright install chromium") from e

from pipeline.scrapers.base import BaseScraper
from pipeline.models import Product

logger = logging.getLogger(__name__)

ASOS_CATALOG = [
    # (genre, sexe, type_hint, url)
    # ── Homme ──────────────────────────────────────────────────────────
    ("Adulte", "Homme", "Vêtement",   "https://www.asos.com/fr/homme/t-shirts-et-debardeurs/cat/?cid=7616"),
    ("Adulte", "Homme", "Vêtement",   "https://www.asos.com/fr/homme/chemises/cat/?cid=3602"),
    ("Adulte", "Homme", "Vêtement",   "https://www.asos.com/fr/homme/sweats-et-sweats-a-capuche/cat/?cid=5668"),
    ("Adulte", "Homme", "Vêtement",   "https://www.asos.com/fr/homme/vestes-et-manteaux/cat/?cid=3606"),
    ("Adulte", "Homme", "Vêtement",   "https://www.asos.com/fr/homme/pantalons-et-chinos/cat/?cid=4910"),
    ("Adulte", "Homme", "Vêtement",   "https://www.asos.com/fr/homme/jeans/cat/?cid=4208"),
    ("Adulte", "Homme", "Vêtement",   "https://www.asos.com/fr/homme/shorts/cat/?cid=7078"),
    ("Adulte", "Homme", "Chaussures", "https://www.asos.com/fr/homme/chaussures-bottes-et-baskets/cat/?cid=5773"),
    # ── Femme ──────────────────────────────────────────────────────────
    ("Adulte", "Femme", "Vêtement",   "https://www.asos.com/fr/femme/robes/cat/?cid=8799"),
    ("Adulte", "Femme", "Vêtement",   "https://www.asos.com/fr/femme/tops/cat/?cid=4169"),
    ("Adulte", "Femme", "Vêtement",   "https://www.asos.com/fr/femme/manteaux-et-vestes/cat/?cid=2641"),
    ("Adulte", "Femme", "Vêtement",   "https://www.asos.com/fr/femme/pantalons-et-leggings/cat/?cid=2640"),
    ("Adulte", "Femme", "Vêtement",   "https://www.asos.com/fr/femme/jeans/cat/?cid=3630"),
    ("Adulte", "Femme", "Vêtement",   "https://www.asos.com/fr/femme/shorts/cat/?cid=9263"),
    ("Adulte", "Femme", "Chaussures", "https://www.asos.com/fr/femme/chaussures/cat/?cid=4172"),
]

# Pages marques spécifiques vendues sur ASOS
# Les URLs utilisent le moteur de recherche ASOS (pas besoin de cid)
ASOS_BRAND_PAGES = [
    # ── Streetwear / Workwear ──────────────────────────────────────────
    ("Adulte", "Homme", "Vêtement",   "https://www.asos.com/fr/recherche/?q=carhartt+wip"),
    ("Adulte", "Homme", "Vêtement",   "https://www.asos.com/fr/recherche/?q=dickies+homme"),
    ("Adulte", "Homme", "Vêtement",   "https://www.asos.com/fr/recherche/?q=champion+homme"),
    ("Adulte", "Femme", "Vêtement",   "https://www.asos.com/fr/recherche/?q=champion+femme"),
    ("Adulte", "Homme", "Vêtement",   "https://www.asos.com/fr/recherche/?q=fila+homme"),
    ("Adulte", "Femme", "Vêtement",   "https://www.asos.com/fr/recherche/?q=fila+femme"),
    # ── Denim / Premium casual ─────────────────────────────────────────
    ("Adulte", "Homme", "Vêtement",   "https://www.asos.com/fr/recherche/?q=levis+homme"),
    ("Adulte", "Femme", "Vêtement",   "https://www.asos.com/fr/recherche/?q=levis+femme"),
    ("Adulte", "Homme", "Vêtement",   "https://www.asos.com/fr/recherche/?q=wrangler"),
    ("Adulte", "Homme", "Vêtement",   "https://www.asos.com/fr/recherche/?q=tommy+hilfiger+homme"),
    ("Adulte", "Femme", "Vêtement",   "https://www.asos.com/fr/recherche/?q=tommy+hilfiger+femme"),
    ("Adulte", "Homme", "Vêtement",   "https://www.asos.com/fr/recherche/?q=calvin+klein+jeans+homme"),
    ("Adulte", "Femme", "Vêtement",   "https://www.asos.com/fr/recherche/?q=calvin+klein+jeans+femme"),
    ("Adulte", "Homme", "Vêtement",   "https://www.asos.com/fr/recherche/?q=polo+ralph+lauren+homme"),
    ("Adulte", "Femme", "Vêtement",   "https://www.asos.com/fr/recherche/?q=polo+ralph+lauren+femme"),
    ("Adulte", "Homme", "Vêtement",   "https://www.asos.com/fr/recherche/?q=lacoste+homme"),
    ("Adulte", "Homme", "Vêtement",   "https://www.asos.com/fr/recherche/?q=fred+perry+homme"),
    # ── Outdoor / Sport ───────────────────────────────────────────────
    ("Adulte", "Homme", "Vêtement",   "https://www.asos.com/fr/recherche/?q=the+north+face+homme"),
    ("Adulte", "Femme", "Vêtement",   "https://www.asos.com/fr/recherche/?q=the+north+face+femme"),
    ("Adulte", "Homme", "Vêtement",   "https://www.asos.com/fr/recherche/?q=columbia+homme"),
    ("Adulte", "Homme", "Vêtement",   "https://www.asos.com/fr/recherche/?q=adidas+originals+homme"),
    ("Adulte", "Femme", "Vêtement",   "https://www.asos.com/fr/recherche/?q=adidas+originals+femme"),
    ("Adulte", "Homme", "Vêtement",   "https://www.asos.com/fr/recherche/?q=puma+homme"),
    ("Adulte", "Femme", "Vêtement",   "https://www.asos.com/fr/recherche/?q=puma+femme"),
    ("Adulte", "Homme", "Vêtement",   "https://www.asos.com/fr/recherche/?q=reebok+homme"),
    # ── Chaussures ────────────────────────────────────────────────────
    ("Adulte", "Homme", "Chaussures", "https://www.asos.com/fr/recherche/?q=new+balance+homme"),
    ("Adulte", "Femme", "Chaussures", "https://www.asos.com/fr/recherche/?q=new+balance+femme"),
    ("Adulte", "Homme", "Chaussures", "https://www.asos.com/fr/recherche/?q=vans+homme"),
    ("Adulte", "Femme", "Chaussures", "https://www.asos.com/fr/recherche/?q=vans+femme"),
    ("Adulte", "Homme", "Chaussures", "https://www.asos.com/fr/recherche/?q=converse+homme"),
    ("Adulte", "Femme", "Chaussures", "https://www.asos.com/fr/recherche/?q=converse+femme"),
    ("Adulte", "Homme", "Chaussures", "https://www.asos.com/fr/recherche/?q=dr+martens+homme"),
    ("Adulte", "Femme", "Chaussures", "https://www.asos.com/fr/recherche/?q=dr+martens+femme"),
]

_PDP_PRODUCT_RE = re.compile(
    r'window\.asos\.pdp\.config\.product\s*=\s*(\{")',
)

_KEYSTORE_RE = re.compile(r'keyStoreDataversion=([a-z0-9\-]+)', re.IGNORECASE)


class AsosScraper(BaseScraper):
    BRAND_SOURCE = "ASOS"

    # ------------------------------------------------------------------
    def _launch_browser(self, pw):
        """Lance Chromium en mode visible (contournement anti-bot ASOS)."""
        return pw.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--start-maximized",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )

    def _new_context(self, browser):
        return browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="fr-FR",
            no_viewport=True,
        )

    # ------------------------------------------------------------------
    def _accept_cookies(self, page):
        for selector in [
            "#onetrust-accept-btn-handler",
            "button[data-auto-id='cookie-accept-button']",
            "[data-testid='accept-cookies']",
        ]:
            try:
                page.click(selector, timeout=3000)
                page.wait_for_timeout(500)
                return
            except Exception:
                pass

    # ------------------------------------------------------------------
    def _get_product_urls(self, page, cat_url: str) -> List[str]:
        try:
            page.goto(cat_url, wait_until="domcontentloaded", timeout=30000)
        except PWTimeout:
            logger.warning(f"[ASOS] Timeout catalogue : {cat_url}")
            return []

        self._accept_cookies(page)
        page.wait_for_timeout(3000)

        # Scroll pour charger plus de produits
        for _ in range(8):
            page.mouse.wheel(0, 2500)
            page.wait_for_timeout(700)

        urls: List[str] = page.evaluate("""() => {
            const s = new Set();
            document.querySelectorAll('a[href]').forEach(a => {
                if (a.href.includes('/prd/'))
                    s.add(a.href.split('?')[0].split('#')[0]);
            });
            return Array.from(s);
        }""")

        return urls

    # ------------------------------------------------------------------
    def _extract_keystore(self, page) -> str:
        """Extrait la valeur keyStoreDataversion depuis le HTML de la page."""
        try:
            raw = page.content()
            m = _KEYSTORE_RE.search(raw)
            return m.group(1) if m else "7qyyrb1-46"
        except Exception:
            return "7qyyrb1-46"

    # ------------------------------------------------------------------
    def _extract_product_json(self, raw_html: str) -> Optional[dict]:
        """
        Extrait window.asos.pdp.config.product = {...} depuis le HTML.
        ASOS injecte le JSON complet du produit dans un script inline.
        """
        m = _PDP_PRODUCT_RE.search(raw_html)
        if not m:
            return None

        start = m.start(1)  # position de '{"'
        depth = 0
        for i, c in enumerate(raw_html[start:start + 200_000]):
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(raw_html[start : start + i + 1])
                    except json.JSONDecodeError:
                        return None
        return None

    # ------------------------------------------------------------------
    def _fetch_price(self, page, product_id: int, keystore: str) -> Optional[float]:
        """Appelle l'API stockprice v4 depuis le contexte du navigateur."""
        try:
            result = page.evaluate(f"""async () => {{
                const url = "https://www.asos.com/api/product/catalogue/v4/stockprice" +
                    "?productIds={product_id}&store=FR&currency=EUR&keyStoreDataversion={keystore}";
                const r = await fetch(url, {{credentials: "include"}});
                if (!r.ok) return null;
                const data = await r.json();
                return data[0]?.productPrice?.current?.value ?? null;
            }}""")
            return float(result) if result is not None else None
        except Exception as e:
            logger.debug(f"[ASOS] Erreur fetch prix produit {product_id} : {e}")
            return None

    # ------------------------------------------------------------------
    def _scrape_product(
        self, page, url: str, genre: str, sexe: str, type_hint: str, keystore: str
    ) -> Optional[Product]:
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(5000)
        except PWTimeout:
            logger.warning(f"[ASOS] Timeout produit : {url}")
            return None

        raw = page.content()
        data = self._extract_product_json(raw)
        if not data:
            logger.debug(f"[ASOS] JSON produit introuvable : {url}")
            return None

        name = (data.get("name") or "").strip()
        if not name:
            return None

        # Variants → tailles disponibles
        variants = data.get("variants", [])
        available_sizes = [
            v["size"] for v in variants
            if isinstance(v, dict) and v.get("isAvailable") and v.get("size")
        ]
        # Couleur (premier variant disponible)
        color = next(
            (v.get("colour") for v in variants if isinstance(v, dict) and v.get("colour")),
            None,
        )

        # Image principale
        image = None
        for img in data.get("images", []):
            if isinstance(img, dict) and img.get("isPrimary"):
                raw_url = img.get("url", "")
                image = ("https://" + raw_url) if raw_url and not raw_url.startswith("http") else raw_url
                break

        # Description
        desc_raw = data.get("description", "") or ""
        if isinstance(desc_raw, list):
            desc_raw = " ".join(desc_raw)
        description = str(desc_raw).strip()[:500]

        # Rating depuis window.state.ratings (déjà chargé)
        rating = None
        try:
            rating_raw = page.evaluate(
                "() => window.state?.ratings?.averageOverallRating ?? null"
            )
            if rating_raw is not None:
                rating = float(rating_raw)
        except Exception:
            pass

        # Prix via API stockprice
        product_id = data.get("id")
        price = self._fetch_price(page, product_id, keystore) if product_id else None

        return self._make_product(
            name, price, description, genre, sexe,
            available_sizes, color, rating, type_hint, image, url,
        )

    # ------------------------------------------------------------------
    @staticmethod
    def _normalize_taille(raw_sizes: List[str]) -> List[str]:
        """
        Normalise les formats de taille ASOS vers les valeurs standard du pipeline.

        Conversions :
          "XS - Chest 32-34" / "S - EU 36-38" → extraire la base ("XS", "S"…)
          "2XL"              → "XXL"
          "3XL" / "4XL"     → "XXXL"
          "EU 32/34"         → "XS", "EU 36" → "S", etc. (mapping numérique)
          "W28 L30" (jean)   → ignoré (pas de correspondance XS/S/M/L)
        """
        VALID = {"XS", "S", "M", "L", "XL", "XXL", "XXXL"}
        REMAP = {"2XL": "XXL", "3XL": "XXXL", "4XL": "XXXL"}
        # EU numeric → standard (approximation femme/coupe européenne)
        EU_MAP: dict = {
            32: "XS", 33: "XS", 34: "XS",
            35: "S",  36: "S",  37: "S",
            38: "M",  39: "M",
            40: "L",  41: "L",
            42: "XL", 43: "XL",
            44: "XXL", 45: "XXL",
            46: "XXXL", 47: "XXXL", 48: "XXXL",
        }

        result: List[str] = []
        for raw in raw_sizes:
            s = str(raw).strip()

            # "XS - Chest 32-34" ou "S - EU 36-38" → garder la partie avant " - "
            if " - " in s:
                s = s.split(" - ")[0].strip()

            # Remplacements directs
            upper = s.upper()
            s = REMAP.get(upper, s)

            # Taille standard
            if s.upper() in VALID:
                token = s.upper()
                if token not in result:
                    result.append(token)
                continue

            # EU numeric : "EU 36", "EU36"
            eu_m = re.match(r"EU\s*(\d+)", s, re.IGNORECASE)
            if eu_m:
                num = int(eu_m.group(1))
                std = EU_MAP.get(num)
                if std and std not in result:
                    result.append(std)
                continue

            # W/L jean : "W28 L30", "W30", etc. → approximation par tour de taille
            wl_m = re.match(r"W\s*(\d+)", s, re.IGNORECASE)
            if wl_m:
                w = int(wl_m.group(1))
                std = (
                    "XS"   if w <= 29 else
                    "S"    if w <= 31 else
                    "M"    if w <= 33 else
                    "L"    if w <= 35 else
                    "XL"   if w <= 37 else
                    "XXL"  if w <= 40 else
                    "XXXL"
                )
                if std not in result:
                    result.append(std)

        return result

    # ------------------------------------------------------------------
    def _make_product(
        self,
        name: str,
        price: Optional[float],
        description: str,
        genre: str,
        sexe: str,
        raw_sizes: List[str],
        color: Optional[str],
        rating: Optional[float],
        type_hint: str,
        image: Optional[str],
        url: str,
    ) -> Product:
        is_shoe = (type_hint == "Chaussures") or any(
            k in name.lower()
            for k in ["sneaker", "basket", "chaussure", "boot", "bottine", "sandal", "mocassin"]
        )
        p_type = "Chaussures" if is_shoe else "Vêtement"

        if is_shoe:
            sizes_out: List[int] = []
            for s in raw_sizes:
                m = re.search(r"(\d+[.,]?\d*)", s)
                if m:
                    try:
                        sizes_out.append(int(float(m.group(1).replace(",", "."))))
                    except ValueError:
                        pass
            taille_out: List[str] = []
        else:
            sizes_out = []
            taille_out = self._normalize_taille(raw_sizes)

        return Product(
            name         = name,
            price_value  = price,
            currency     = "EUR",
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
    @staticmethod
    def _need_virtual_display() -> bool:
        """Retourne True si on est sur Linux sans DISPLAY (typiquement Docker)."""
        return sys.platform.startswith("linux") and not os.environ.get("DISPLAY")

    # ------------------------------------------------------------------
    def run(self) -> List[Product]:
        all_products: List[Product] = []

        vdisplay = None
        if self._need_virtual_display():
            try:
                from pyvirtualdisplay import Display
                vdisplay = Display(visible=False, size=(1280, 900))
                vdisplay.start()
                logger.info("[ASOS] Virtual display Xvfb démarré (Linux sans DISPLAY)")
            except Exception as e:
                logger.warning(f"[ASOS] Impossible de démarrer Xvfb : {e} — tentative headless")

        try:
            with sync_playwright() as pw:
                browser = self._launch_browser(pw)
                ctx = self._new_context(browser)
                page = ctx.new_page()

                # Extraire le keyStoreDataversion depuis la homepage ASOS
                try:
                    page.goto(
                        "https://www.asos.com/fr/", wait_until="domcontentloaded", timeout=20000
                    )
                    page.wait_for_timeout(2000)
                    self._accept_cookies(page)
                    keystore = self._extract_keystore(page)
                    logger.info(f"[ASOS] keyStoreDataversion = {keystore}")
                except Exception:
                    keystore = "7qyyrb1-46"

                for genre, sexe, type_hint, cat_url in ASOS_CATALOG + ASOS_BRAND_PAGES:
                    label = cat_url.split("q=")[-1] if "recherche" in cat_url else cat_url.split("/cat/")[0].rstrip("/").split("/")[-1]
                    logger.info(f"[ASOS] {genre}/{sexe}/{type_hint} — {label}")

                    product_urls = self._get_product_urls(page, cat_url)
                    logger.info(f"[ASOS] {len(product_urls)} URLs trouvées")

                    for url in product_urls:
                        self.sleep(3.0, 6.0)
                        try:
                            product = self._scrape_product(page, url, genre, sexe, type_hint, keystore)
                            if product:
                                all_products.append(product)
                                logger.info(f"  ✓ {product.name} — {product.price_value}€ — {product.taille or product.sizes}")
                        except Exception as e:
                            logger.warning(f"[ASOS] Erreur sur {url} : {e}")
                            try:
                                page.close()
                                page = ctx.new_page()
                            except Exception:
                                pass

                    self.sleep(8.0, 15.0)

                browser.close()
        finally:
            if vdisplay is not None:
                vdisplay.stop()
                logger.info("[ASOS] Virtual display Xvfb arrêté")

        logger.info(f"[ASOS] Total : {len(all_products)} produits")
        return all_products
