"""
ai/ollama_setup.py — Démarrage automatique d'Ollama et pull des modèles manquants.

Appelé au lancement de l'app. Tout se passe en arrière-plan : l'app reste disponible
pendant que les modèles se téléchargent.
"""
import logging
import os
import shutil
import subprocess
import threading
import time

import requests
from typing import List

log = logging.getLogger(__name__)

OLLAMA_BASE = os.environ.get("OLLAMA_URL", "http://localhost:11434")
VISION_MODEL = os.environ.get("VISION_MODEL", "qwen2.5vl:7b")
TEXT_MODEL = os.environ.get("TEXT_MODEL", "qwen2.5vl:7b")

# Délai max pour qu'Ollama soit prêt après le lancement (secondes)
_OLLAMA_START_TIMEOUT = 30


def _is_ollama_running() -> bool:
    try:
        r = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def _installed_models() -> List[str]:
    try:
        r = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=5)
        r.raise_for_status()
        return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        return []


def _start_ollama_server():
    """Lance `ollama serve` en subprocess détaché si Ollama n'est pas déjà actif."""
    if _is_ollama_running():
        log.info("Ollama déjà actif sur %s", OLLAMA_BASE)
        return True

    if not shutil.which("ollama"):
        log.warning("Commande `ollama` introuvable — installez Ollama (https://ollama.com)")
        return False

    log.info("Démarrage d'Ollama en arrière-plan…")
    try:
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,  # détaché du processus Flask
        )
    except OSError as e:
        log.error("Impossible de lancer Ollama : %s", e)
        return False

    # Attente que le serveur soit prêt
    for _ in range(_OLLAMA_START_TIMEOUT):
        time.sleep(1)
        if _is_ollama_running():
            log.info("Ollama prêt.")
            return True

    log.warning("Ollama n'a pas répondu dans les %ds impartis.", _OLLAMA_START_TIMEOUT)
    return False


def _pull_model(model: str):
    """Pull un modèle Ollama. Bloquant, à appeler dans un thread dédié."""
    log.info("Pull du modèle Ollama '%s'… (peut prendre plusieurs minutes)", model)
    try:
        result = subprocess.run(
            ["ollama", "pull", model],
            capture_output=True,
            text=True,
            timeout=3600,  # 1h max
        )
        if result.returncode == 0:
            log.info("Modèle '%s' installé avec succès.", model)
        else:
            log.error("Échec du pull '%s' : %s", model, result.stderr.strip())
    except subprocess.TimeoutExpired:
        log.error("Timeout lors du pull de '%s'.", model)
    except Exception as e:
        log.error("Erreur pull '%s' : %s", model, e)


def _setup_models():
    """Vérifie et pull les modèles manquants (dans un thread)."""
    if not _start_ollama_server():
        return

    installed = _installed_models()
    needed = {VISION_MODEL}
    if TEXT_MODEL != VISION_MODEL:
        needed.add(TEXT_MODEL)

    missing = [
        m for m in needed
        if not any(m.split(":")[0] in installed_name for installed_name in installed)
    ]

    if not missing:
        log.info("Tous les modèles Ollama sont disponibles : %s", list(needed))
        return

    for model in missing:
        _pull_model(model)


def ensure_ollama(app=None):
    """
    Point d'entrée : lance Ollama et pull les modèles manquants en arrière-plan.
    Appeler depuis create_app() ou le bloc __main__.
    """
    def _run():
        try:
            _setup_models()
        except Exception as e:
            log.exception("Erreur inattendue dans ensure_ollama : %s", e)

    t = threading.Thread(target=_run, name="ollama-setup", daemon=True)
    t.start()
    log.info("Initialisation Ollama lancée en arrière-plan (thread %s).", t.name)
