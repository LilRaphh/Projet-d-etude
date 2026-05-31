# Installation

## Prérequis communs

- Python 3.11+
- (Optionnel) [Ollama](https://ollama.com) — LLM local pour le styliste et les explications
- (Optionnel) MongoDB — export du pipeline de scraping
- (Docker) Docker Desktop ou Docker Engine + Compose v2

---

## Option A — Docker

La méthode la plus simple : tout tourne en conteneur, rien à installer manuellement.

### 1. Configurer `.env`

```bash
cp .env.example .env
```

Remplissez au minimum ces deux variables :

```env
SECRET_KEY=<généré ci-dessous>
ANTHROPIC_API_KEY=sk-ant-...
```

Générer une `SECRET_KEY` :
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 2. Démarrer

```bash
docker compose up -d --build
```

App disponible sur **http://localhost:5001**.

### 3. Premier démarrage — modèle Ollama

L'app tente de puller le modèle automatiquement, mais c'est plus rapide de le faire manuellement :

```bash
docker exec wardrobe_ollama ollama pull qwen2.5vl:7b
```

### 4. Migrer une base existante

Si vous avez déjà un `wardrobe.db` local, copiez-le dans le volume Docker :

```bash
docker cp wardrobe.db wardrobe_app:/app/data/wardrobe.db
docker compose restart app
```

### Commandes utiles

```bash
docker compose logs -f app        # logs en temps réel
docker compose down               # arrêter
docker compose down -v            # arrêter + supprimer les volumes
docker compose up -d              # relancer (sans rebuild)
docker compose up -d --build      # relancer avec rebuild de l'image
```

### Volumes persistants

| Volume Docker | Contenu |
|---------------|---------|
| `uploads` | Photos uploadées (`static/uploads/`) |
| `app_data` | Base SQLite + cache HuggingFace (FashionCLIP) |
| `ollama_data` | Modèles Ollama |

---

## Option B — Environnement local

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

Éditez `.env` :

| Variable | Obligatoire | Défaut | Description |
|----------|:-----------:|--------|-------------|
| `SECRET_KEY` | **Oui** | — | Clé secrète Flask (sessions, CSRF) |
| `ANTHROPIC_API_KEY` | **Oui** | — | Clé API Anthropic (Claude) |
| `FERNET_KEY` | Non | dérivée de `SECRET_KEY` | Chiffrement des clés API en base |
| `PORT` | Non | `5001` | Port d'écoute |
| `DATABASE_URL` | Non | `sqlite:///wardrobe.db` | URI SQLAlchemy (SQLite ou PostgreSQL) |
| `OLLAMA_URL` | Non | `http://localhost:11434` | URL du serveur Ollama |
| `LOG_DIR` | Non | console uniquement | Dossier de logs fichier |
| `ANTHROPIC_MODEL` | Non | `claude-sonnet-4-5` | Modèle Claude utilisé |
| `ITEMS_PER_PAGE` | Non | `24` | Items par page dans la galerie |
| `CACHE_TYPE` | Non | `SimpleCache` | Backend cache Flask |
| `REDIS_URL` | Non | `memory://` | Redis pour cache et rate limiting en prod |

### 3. Lancement

```bash
python app.py                # http://localhost:5001
python app.py --host         # accessible sur le réseau local (0.0.0.0)
python app.py --debug        # rechargement auto + logs DEBUG
python app.py --reset-db     # réinitialise la base de données
```

---

## IA locale (Ollama)

L'app détecte Ollama au démarrage et tente de lancer le serveur si nécessaire.

```bash
# Installer depuis https://ollama.com, puis :
ollama pull qwen2.5vl:7b    # modèle par défaut
```

Le modèle actif est configurable via `VISION_MODEL` et `TEXT_MODEL` dans `.env`.  
Sans Ollama, le styliste IA et les explications tombent en mode dégradé (templates textuels).

---

## FashionCLIP (embeddings locaux)

Téléchargé automatiquement depuis HuggingFace Hub au premier démarrage. Le cache est stocké dans `$HF_HOME` (par défaut `~/.cache/huggingface`).

En mode offline (`HF_HUB_OFFLINE=1`), le modèle doit être présent dans le cache local — c'est le comportement par défaut en production Docker pour éviter les appels réseau inutiles.

---

## Pipeline de scraping

Le pipeline a ses propres dépendances, isolées dans `pipeline/requirements.txt` :

```bash
pip install -r pipeline/requirements.txt
playwright install chromium          # requis pour Nike et Jules (scraping JS)
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

---

## Stack de monitoring (optionnel)

Grafana + Loki + Promtail pour visualiser les logs de l'app et du pipeline.

```bash
docker compose -f docker-compose.monitoring.yml up -d
```

- Grafana → http://localhost:3000 (admin / admin)
- Stats pipeline → http://localhost:8888/stats.json
