"""
Validators de sécurité partagés.
Centralisés ici pour éviter la duplication entre routes/boutique.py,
routes/auth.py, routes/main.py et utils/ai.py.
"""
import ipaddress
from urllib.parse import urljoin, urlparse

# Hostnames bloqués explicitement (metadata cloud, loopback nommé)
_BLOCKED_HOSTS = frozenset({'localhost', 'metadata.google.internal'})


def is_safe_image_url(url: str) -> bool:
    """Retourne True si l'URL peut être fetchée côté serveur sans risque SSRF.

    Bloque : schèmes non-HTTP, loopback, IPs privées, link-local, réservées,
    et les noms d'hôtes connus (localhost, metadata GCP).
    """
    if not url:
        return False
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https'):
        return False
    host = (parsed.hostname or '').lower()
    if host in _BLOCKED_HOSTS:
        return False
    try:
        addr = ipaddress.ip_address(host)
        if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
            return False
    except ValueError:
        pass  # nom de domaine public — autorisé
    return True


def is_safe_redirect_target(target: str, host_url: str) -> bool:
    """Retourne True si target est une URL de même origine (anti open-redirect).

    Args:
        target:   URL ou chemin cible (peut être relatif).
        host_url: URL de base de l'application (request.host_url).
    """
    if not target:
        return False
    ref = urlparse(host_url)
    test = urlparse(urljoin(host_url, target))
    return test.scheme in ('http', 'https') and ref.netloc == test.netloc


def is_local_url(url: str) -> bool:
    """Retourne True si l'URL pointe vers localhost (pour Ollama / SD local).

    Accepte uniquement les adresses loopback et le hostname 'localhost'.
    Rejet de tout autre hôte pour bloquer le pivot SSRF vers des services internes.
    """
    if not url:
        return False
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https'):
        return False
    host = (parsed.hostname or '').lower()
    if host == 'localhost':
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False
