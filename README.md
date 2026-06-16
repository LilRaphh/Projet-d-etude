<div align="center">

# SmartWear

**Garde-robe intelligente — IA locale · Scraping mode · Planification tenues**

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-3.0+-000000?style=flat-square&logo=flask&logoColor=white)](https://flask.palletsprojects.com)
[![Docker](https://img.shields.io/badge/Docker-ready-2496ED?style=flat-square&logo=docker&logoColor=white)](https://docker.com)
[![Claude API](https://img.shields.io/badge/Claude-API-D97706?style=flat-square)](https://anthropic.com)
[![Ollama](https://img.shields.io/badge/Ollama-local_LLM-000000?style=flat-square)](https://ollama.ai)

</div>

---

SmartWear est une application web de gestion de garde-robe personnelle qui combine un moteur IA hybride (local + cloud) avec un pipeline de scraping de 28 marques de mode. Elle vous permet d'organiser vos vêtements, générer des suggestions de tenues adaptées à la météo, vérifier la cohérence stylistique et découvrir de nouveaux articles — le tout depuis une interface web.

---

## Table des matières

- [Fonctionnalités](#fonctionnalités)
- [Architecture](#architecture)
- [Stack technique](#stack-technique)
- [Démarrage rapide](#démarrage-rapide)
- [Variables d'environnement](#variables-denvironnement)
- [Pipeline de scraping](#pipeline-de-scraping)
- [Monitoring](#monitoring)
- [Sécurité](#sécurité)
- [Documentation par module](#documentation-par-module)

---

## Fonctionnalités

### Garde-robe & tenues

| Fonctionnalité | Description |
|----------------|-------------|
| **Garde-robe** | Ajout de vêtements avec photo, catégorie, marque, taille, couleur, saison, condition, prix et tags personnalisés |
| **Tenues** | Créez et notez des combinaisons, suivez les ports, générez une photo mannequin via Flux (Pollinations.ai, gratuit) |
| **Complétion de tenue** | Suggère les pièces manquantes à partir d'un vêtement ancre (IA locale + Claude) |
| **Calendrier** | Planifiez vos tenues jour par jour avec prévisions météo 7 jours (Open-Meteo, sans clé) |
| **Ajout depuis photo** | Extrait et catégorise automatiquement les vêtements d'une photo uploadée |

### IA & recommandations

| Fonctionnalité | Technologie |
|----------------|-------------|
| **Styliste IA** | Suggestions adaptées à la météo et à l'occasion — Claude API + Ollama |
| **Similarité visuelle** | Moteur d'embeddings FashionCLIP 100% local, sans cloud, sans ChromaDB |
| **Vérification de style** | Analyse de cohérence sur photo ou tenue existante — vision multimodale |
| **Boutique intelligente** | Catalogue scrapé (28 marques), ajout direct en garde-robe ou wishlist |
| **Alerte de prix** | Surveillance automatique des articles en wishlist avec notification de baisse |

### Compte & paramètres

- Inscription avec vérification e-mail, connexion, réinitialisation de mot de passe
- Profil utilisateur : genre, esthétique, budget, tailles par défaut
- Paramètres personnalisables : devise, ville, clés API chiffrées, couleur d'accent
- Dashboard administrateur pour la gestion des utilisateurs et des données système

---

## Architecture

```
Projet-d-etude/
│
├── app.py                    # Fabrique Flask + create_app()
├── config.py                 # Constantes globales (catégories, tailles, couleurs) + classe Config
├── extensions.py             # Instances partagées (SQLAlchemy, CSRF, Limiter, Cache)
├── models.py                 # 10 modèles SQLAlchemy
│
├── routes/                   # 13 blueprints Flask
│   ├── auth.py               # Inscription, connexion, vérification e-mail, reset mot de passe
│   ├── main.py               # Galerie garde-robe, filtrage, tri
│   ├── outfits.py            # CRUD tenues, génération image IA, analyse de style
│   ├── stylist.py            # Suggestions météo-adaptées (Claude + Ollama)
│   ├── ai_recommend.py       # Recommandations par similarité visuelle (FashionCLIP)
│   ├── style_check.py        # Analyse de cohérence stylistique
│   ├── complete.py           # Complétion de tenue depuis un vêtement ancre
│   ├── add_from_photo.py     # Extraction de vêtements depuis une photo
│   ├── boutique.py           # Catalogue scrapé + gestion wishlist
│   ├── calendar.py           # Planification calendrier + météo
│   ├── profile.py            # Profil utilisateur et préférences
│   ├── api.py                # Endpoints AJAX internes (tags, streaming, etc.)
│   └── admin.py              # Dashboard administration
│
├── ai/                       # Moteur IA local
│   ├── pipeline.py           # Orchestrateur (vision → embeddings → scoring → explication)
│   ├── vision.py             # FashionCLIP + Qwen2.5-VL — analyse visuelle
│   ├── embeddings.py         # Stockage vectoriel SQLite + recherche par similarité
│   ├── scoring.py            # Combinaison embeddings + règles métier
│   ├── rules.py              # Filtres saison, occasion, cohérence couleurs
│   ├── explainer.py          # Explications en langage naturel (Ollama)
│   └── ollama_setup.py       # Détection, lancement et pull de modèles Ollama
│
├── utils/                    # Services partagés
│   ├── auth.py               # Décorateur @login_required + helper get_ctx()
│   ├── weather.py            # WeatherService (Open-Meteo — géolocalisation + prévisions)
│   ├── crypto.py             # Chiffrement Fernet pour clés API
│   ├── images.py             # Validation magic bytes, redimensionnement, sauvegarde
│   ├── mail.py               # Envoi e-mail (vérification, reset)
│   ├── ai.py                 # Wrapper Anthropic Claude API
│   ├── currency.py           # Conversion EUR/USD avec mise en cache
│   └── tags.py               # Parsing et normalisation des tags
│
├── pipeline/                 # Module de scraping indépendant
│   ├── run.py                # CLI (argparse)
│   ├── pipeline.py           # Normalisation, déduplication, export JSON
│   ├── scrapers/             # 28 scrapers de marques (Playwright + BeautifulSoup)
│   └── dags/                 # DAG Apache Airflow (3h UTC quotidien)
│
├── templates/                # 24 templates Jinja2
├── static/uploads/           # Photos uploadées (gitignored)
├── monitoring/               # Config Loki, Promtail, Grafana
│
├── docker-compose.yml                # App + ngrok
├── docker-compose.monitoring.yml     # Grafana + Loki + Promtail
└── Dockerfile                        # Image Python 3.11-slim + Playwright
```

---

## Stack technique

| Couche | Technologie | Rôle |
|--------|-------------|------|
| **Web** | Flask 3+ | Serveur web, blueprints, CSRF, rate limiting |
| **Base de données** | SQLite / SQLAlchemy | Persistance (switchable PostgreSQL via `DATABASE_URL`) |
| **Embeddings locaux** | FashionCLIP (HuggingFace / PyTorch) | Similarité visuelle sans dépendance cloud |
| **LLM local** | Ollama — qwen2.5vl:7b | Analyse vision + génération texte en local |
| **LLM cloud** | Anthropic Claude API | Suggestions avancées, analyse stylistique |
| **Génération d'images** | Pollinations.ai (Flux) | Photos mannequin pour les tenues (gratuit) |
| **Météo** | Open-Meteo | Prévisions 7 jours, gratuit, sans clé API |
| **Cache** | SimpleCache (dev) / Redis (prod) | Cache serveur configurable |
| **Scraping** | Playwright + BeautifulSoup4 | Sites JS-heavy et HTML statique |
| **Monitoring** | Grafana + Loki + Promtail | Dashboards et agrégation de logs |

---

## Démarrage rapide

### Prérequis

- Docker & Docker Compose **ou** Python 3.11+
- Une clé API Anthropic (pour les fonctionnalités IA cloud)
- [Ollama](https://ollama.ai) installé localement (optionnel — pour l'IA locale)

---

### Option A — Docker (recommandé)

```bash
# 1. Copier et configurer l'environnement
cp .env.example .env
# Ouvrir .env et renseigner au minimum : SECRET_KEY et ANTHROPIC_API_KEY

# 2. Lancer l'application
docker compose up -d --build

# 3. Accéder à l'app
# http://localhost:5001
# Interface ngrok : http://localhost:4040
```

**Migrer une base existante :**
```bash
docker cp wardrobe.db wardrobe_app:/app/data/wardrobe.db
```

> **Note :** Ollama tourne nativement sur l'hôte. Depuis Docker, il est accessible via `host.docker.internal:11434` (configuré automatiquement).

---

### Option B — Environnement local

```bash
# 1. Créer et activer l'environnement virtuel
python -m venv .venv
source .venv/bin/activate          # Windows : .venv\Scripts\activate

# 2. Installer les dépendances
pip install -r requirements.txt

# 3. Configurer l'environnement
cp .env.example .env               # Renseigner SECRET_KEY (obligatoire)

# 4. Lancer l'application
python app.py                      # http://localhost:5001
python app.py --host               # Accessible sur le réseau local
python app.py --debug              # Rechargement auto + logs DEBUG
python app.py --reset-db           # Réinitialiser la base de données
```

---

## Variables d'environnement

### Obligatoires

```env
SECRET_KEY=<hex-32-bytes>          # Générer : python -c "import secrets; print(secrets.token_hex(32))"
ANTHROPIC_API_KEY=sk-ant-...       # Clé API Anthropic (fonctionnalités IA cloud)
```

### Recommandées

```env
PORT=5001                          # Port du serveur (défaut : 5000)
ANTHROPIC_MODEL=claude-sonnet-4-5  # Modèle Claude (défaut : sonnet)
LOG_DIR=./logs                     # Répertoire de logs (stdout si absent)
ITEMS_PER_PAGE=24                  # Pagination de la galerie
```

### Optionnelles

```env
# Cache
CACHE_TYPE=SimpleCache             # SimpleCache (dev) | RedisCache (prod)
REDIS_URL=redis://localhost:6379   # Cache Redis distribué

# Base de données
DATABASE_URL=sqlite:///wardrobe.db # SQLite (défaut) ou PostgreSQL

# IA locale
OLLAMA_URL=http://localhost:11434  # URL du serveur Ollama
VISION_MODEL=qwen2.5vl:7b         # Modèle de vision Ollama
TEXT_MODEL=qwen2.5vl:7b           # Modèle texte Ollama
HF_HOME=/path/to/huggingface      # Cache des modèles HuggingFace
HF_HUB_OFFLINE=1                  # Mode hors ligne (après premier téléchargement)

# Chiffrement
FERNET_KEY=<base64>               # Clé Fernet (dérivée de SECRET_KEY si absent)

# Génération d'images
POLLINATIONS_MODEL=flux            # Modèle Pollinations (défaut : flux)
POLLINATIONS_WIDTH=832
POLLINATIONS_HEIGHT=1216
POLLINATIONS_ENHANCE=true

# Tunneling
NGROK_AUTHTOKEN=...               # Token ngrok (optionnel)

# Pipeline
MONGO_URI=mongodb://...           # MongoDB pour sortie scraper (optionnel)
```

---

## Pipeline de scraping

Module Python **indépendant** de l'application Flask. Collecte les catalogues de 28 marques de mode, normalise le schéma produit, déduplique et exporte en JSON (ou MongoDB).

**Marques supportées :** Mango, Nike, H&M, ASOS, Lacoste, Kappa, Jules, Le Coq Sportif, Sergio Tacchini, Lotto, et 18 autres via Shopify API.

```bash
# Installer les dépendances du pipeline
pip install -r pipeline/requirements.txt
playwright install chromium        # Pour les sites JavaScript-heavy

# Lancer tous les scrapers
python -m pipeline.run

# Lancer des scrapers spécifiques
python -m pipeline.run --scrapers mango nike kappa

# Mode verbose
python -m pipeline.run --log-level DEBUG
```

Le pipeline inclut un **DAG Apache Airflow** (`pipeline/dags/scraping_dag.py`) pour une exécution planifiée quotidienne à 3h UTC, ainsi qu'un dashboard de monitoring (`pipeline/dashboard.py`) avec statistiques et graphiques en temps réel.

Voir [pipeline/README.md](pipeline/README.md) pour la documentation complète.

---

## Monitoring

La stack de monitoring est optionnelle et découplée de l'application principale.

```bash
# Lancer Grafana + Loki + Promtail
docker compose -f docker-compose.monitoring.yml up -d

# Grafana      → http://localhost:3000  (admin / admin)
# Loki         → http://localhost:3100
# Stats JSON   → http://localhost:8888/stats.json
```

Les logs applicatifs sont émis en JSON structuré compatible Loki/ELK. Les métriques incluent : tentatives de connexion, uploads, durée de génération IA, performance des scrapers.

---

## Sécurité

| Mesure | Détail |
|--------|--------|
| **Démarrage protégé** | L'app refuse de démarrer sans `SECRET_KEY` |
| **Chiffrement des clés API** | Clés tierces stockées chiffrées en base (Fernet / AES-256) |
| **CSRF global** | Flask-WTF sur tous les formulaires et endpoints AJAX |
| **Rate limiting** | Routes login, register, upload et IA protégées |
| **Validation des fichiers** | Contrôle par magic bytes (pas uniquement l'extension) |
| **Hachage des mots de passe** | Werkzeug PBKDF2 |
| **Vérification e-mail** | Obligatoire à l'inscription (token 24h) |
| **Reset de mot de passe** | Token à usage unique (expiration 1h) |

---

## Documentation par module

| Module | Documentation |
|--------|---------------|
| Routes & blueprints | [routes/README.md](routes/README.md) |
| Moteur IA local | [ai/README.md](ai/README.md) |
| Services utilitaires | [utils/README.md](utils/README.md) |
| Pipeline de scraping | [pipeline/README.md](pipeline/README.md) |
| Installation complète | [INSTALL.md](INSTALL.md) |
