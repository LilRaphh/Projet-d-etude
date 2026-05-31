# SmartWear — Garde-robe intelligente

Application web de gestion de garde-robe personnelle, couplée à un moteur IA local et un pipeline de scraping mode.

---

## Fonctionnalités

### Garde-robe & tenues
- **Garde-robe** — ajout de vêtements avec photo, catégorie, marque, taille, couleur, saison, condition, prix, tags
- **Tenues** — créez et notez des combinaisons, suivez le nombre de ports, générez une image mannequin via Flux (Pollinations.ai, gratuit)
- **Complétion de tenue** — suggère les pièces manquantes pour compléter une tenue à partir d'un vêtement ancre (IA locale + Claude)
- **Calendrier** — planifiez vos tenues jour par jour

### IA & style
- **Styliste IA** — suggestions de tenues adaptées à la météo et à l'occasion (Claude + Ollama)
- **Recommandation locale** — moteur de similarité par embeddings visuels FashionCLIP, sans cloud
- **Vérification de style** — analyse d'une photo ou d'une tenue existante (Groq Vision / Claude)
- **Boutique intelligente** — parcourez le catalogue scrapé, ajoutez des articles directement à votre garde-robe ou liste de souhaits

### Compte & paramètres
- **Authentification** — inscription, connexion, vérification e-mail, réinitialisation de mot de passe
- **Profil** — genre, esthétique, budget, tailles par défaut
- **Météo** — prévisions 7 jours intégrées (Open-Meteo, sans clé API)
- **Paramètres** — nom de l'app, couleur d'accent, devise, ville, clés API chiffrées

---

## Architecture

```
app.py              ← point d'entrée Flask + create_app()
config.py           ← constantes et classe Config
extensions.py       ← instances SQLAlchemy, CSRF, cache, limiter
models.py           ← modèles SQLAlchemy (User, ClothingItem, Outfit…)
routes/             ← 11 blueprints Flask
ai/                 ← moteur IA local (FashionCLIP, Ollama, scoring)
utils/              ← services partagés (météo, crypto, images, mail)
templates/          ← templates Jinja2
static/             ← CSS, JS, photos uploadées
pipeline/           ← scraping de catalogues mode (module indépendant)
```

### Stack technique

| Couche | Technologie |
|--------|-------------|
| Web framework | Flask 3+ |
| Base de données | SQLite via SQLAlchemy |
| Embeddings locaux | FashionCLIP (HuggingFace / PyTorch) |
| LLM local | Ollama (qwen2.5vl ou autre) |
| LLM cloud | Anthropic Claude API |
| Génération d'images | Pollinations.ai (Flux, gratuit) |
| Météo | Open-Meteo (gratuit, sans clé) |
| Cache | SimpleCache (dev) / Redis (prod) |

### Sécurité

- `SECRET_KEY` obligatoire au démarrage — l'app refuse de démarrer sans elle
- Clés API tierces chiffrées en base (Fernet / AES-256)
- Protection CSRF globale (Flask-WTF) sur formulaires et AJAX
- Rate limiting sur les routes sensibles (login, register, upload)
- Validation des fichiers uploadés par magic bytes (pas seulement l'extension)
- Mots de passe hashés (Werkzeug PBKDF2)

---

## Démarrage rapide

### Option A — Docker (recommandé)

```bash
cp .env.example .env
# Éditez .env : SECRET_KEY et ANTHROPIC_API_KEY obligatoires

docker compose up -d --build
```

App disponible sur **http://localhost:5001**.

Pour migrer une base existante :
```bash
docker cp wardrobe.db wardrobe_app:/app/data/wardrobe.db
```

Voir [INSTALL.md](INSTALL.md#docker) pour les détails (volumes, Ollama, cache HuggingFace).

### Option B — Environnement local

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # puis remplir SECRET_KEY

python app.py          # http://localhost:5001
```

Voir [INSTALL.md](INSTALL.md) pour la configuration complète.

---

## Modules

| Module | Documentation |
|--------|---------------|
| App Flask (racine) | ce fichier |
| Routes & blueprints | [routes/README.md](routes/README.md) |
| Moteur IA local | [ai/README.md](ai/README.md) |
| Services utilitaires | [utils/README.md](utils/README.md) |
| Pipeline de scraping | [pipeline/README.md](pipeline/README.md) |
| Installation complète | [INSTALL.md](INSTALL.md) |

---

## Pipeline de scraping (module indépendant)

Collecte automatisée depuis 7 marques (Mango, Nike, Jules, Le Coq Sportif, Sergio Tacchini, Kappa, Lotto), avec normalisation du schéma, déduplication, export JSON / MongoDB. Pilotable en CLI ou via Apache Airflow.

```bash
pip install -r pipeline/requirements.txt
python -m pipeline.run
```

Voir [pipeline/README.md](pipeline/README.md).
