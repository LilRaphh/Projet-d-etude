# Installation

## Prérequis

- Python 3.10+
- (Optionnel) Ollama pour l'IA locale — [ollama.com](https://ollama.com)
- (Optionnel) MongoDB pour le pipeline de scraping

---

## App Flask

### 1. Environnement virtuel

```bash
python -m venv .venv
source .venv/bin/activate        # Mac / Linux
# .venv\Scripts\activate         # Windows
pip install -r requirements.txt
```

### 2. Configuration

```bash
cp .env.example .env
```

Éditez `.env` et renseignez au minimum `SECRET_KEY` :

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Variables disponibles :

| Variable | Obligatoire | Défaut | Description |
|----------|:-----------:|--------|-------------|
| `SECRET_KEY` | **Oui** | — | Clé secrète Flask (sessions, CSRF) |
| `FERNET_KEY` | Non | dérivée de `SECRET_KEY` | Chiffrement des clés API en base |
| `PORT` | Non | `5000` | Port d'écoute |
| `LOG_DIR` | Non | console uniquement | Dossier de logs fichier |
| `ANTHROPIC_MODEL` | Non | `claude-sonnet-4-5` | Modèle Claude |
| `ITEMS_PER_PAGE` | Non | `24` | Items par page dans la galerie |
| `CACHE_TYPE` | Non | `SimpleCache` | Backend cache Flask |
| `REDIS_URL` | Non | `memory://` | Redis pour cache/rate limiting en prod |

### 3. Lancement

```bash
python app.py                # localhost:5000
python app.py --host         # accessible sur le réseau local
python app.py --debug        # rechargement auto + logs DEBUG
```

### 4. Réinitialiser la base de données

```bash
python app.py --reset-db
```

---

## IA locale (Ollama)

L'app détecte et configure Ollama automatiquement au démarrage si disponible.

```bash
# Installer Ollama : https://ollama.com
ollama pull llama3.2          # ou tout autre modèle
```

Le modèle utilisé est configurable dans **⚙️ Paramètres** de l'app.

---

## Pipeline de scraping

Le pipeline a ses propres dépendances, isolées dans `pipeline/requirements.txt` :

```bash
pip install -r pipeline/requirements.txt
playwright install chromium   # pour Jules et Nike (scraping JS)
```

Variables supplémentaires dans `.env` :

| Variable | Description |
|----------|-------------|
| `MONGO_URI` | URI MongoDB (optionnel — export JSON toujours actif) |
| `GOOGLE_GEMINI_API_KEY` | Clé Gemini (optionnel) |

Lancement :

```bash
python -m pipeline.run                          # tous les scrapers
python -m pipeline.run --scrapers mango nike    # scrapers choisis
python -m pipeline.run --log-level DEBUG
```

Pour Airflow, voir [pipeline/README.md](pipeline/README.md).
