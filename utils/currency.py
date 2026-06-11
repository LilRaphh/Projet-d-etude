"""
utils/currency.py
Conversion de devises via open.er-api.com (gratuit, sans clé API).
Les taux sont mis en cache 1 heure en mémoire.
"""
import json
import logging
import time
from urllib.request import urlopen

_logger = logging.getLogger(__name__)

# ISO code → symbole affiché
CURRENCIES = {
    'EUR': '€',
    'USD': '$',
    'GBP': '£',
    'CHF': 'Fr.',
    'CAD': 'CA$',
    'JPY': '¥',
    'AUD': 'A$',
    'SEK': 'kr',
    'NOK': 'kr',
    'DKK': 'kr',
    'PLN': 'zł',
    'CZK': 'Kč',
    'MAD': 'MAD',
    'TND': 'TND',
}

# Anciennes valeurs stockées sous forme de symbole → code ISO
_LEGACY = {
    '€': 'EUR', '$': 'USD', '£': 'GBP', '¥': 'JPY',
    'CHF': 'CHF', 'CA$': 'CAD', 'A$': 'AUD',
}

_cache = {}   # 'EUR' -> {'rates': {code: float, ...}, 'ts': float}
_TTL = 3600         # secondes avant revalidation


def normalize(raw: str) -> str:
    """Convertit une valeur stockée (code ISO ou ancien symbole) en code ISO."""
    raw = (raw or 'EUR').strip()
    upper = raw.upper()
    if upper in CURRENCIES:
        return upper
    return _LEGACY.get(raw, 'EUR')


def symbol(code: str) -> str:
    """Retourne le symbole d'affichage pour un code ISO."""
    return CURRENCIES.get(normalize(code), code)


def get_rate(target: str) -> float:
    """Retourne le taux de change : 1 EUR = X <target>.
    Retourne 1.0 en cas d'échec réseau (pas d'exception levée).
    """
    iso = normalize(target)
    if iso == 'EUR':
        return 1.0

    now = time.time()
    cached = _cache.get('EUR')
    if cached and now - cached['ts'] < _TTL:
        return float(cached['rates'].get(iso, 1.0))

    try:
        with urlopen('https://open.er-api.com/v6/latest/EUR', timeout=5) as resp:
            data = json.loads(resp.read())
        if data.get('result') == 'success':
            _cache['EUR'] = {'rates': data['rates'], 'ts': now}
            _logger.debug('Taux EUR récupérés depuis open.er-api.com')
            return float(data['rates'].get(iso, 1.0))
        _logger.warning('open.er-api.com: résultat inattendu %s', data.get('result'))
    except Exception:
        _logger.warning('Impossible de récupérer les taux de change', exc_info=True)
    return 1.0


def convert_price(price_eur, rate):  # type: (float | None, float) -> float | None
    """Convertit un prix en EUR vers la devise cible."""
    if price_eur is None:
        return None
    return round(price_eur * rate, 2)


def apply_to_products(products, rate, sym):
    """Retourne de nouveaux dicts avec price_value converti et currency mis à jour.
    Ne modifie pas les dicts originaux (cache intact).
    """
    if rate == 1.0:
        return [{**p, 'currency': sym} for p in products]
    return [
        {
            **p,
            'price_value': convert_price(p.get('price_value'), rate),
            'currency': sym,
        }
        for p in products
    ]
