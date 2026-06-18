<div align="center">

# SmartWear

**Garde-robe intelligente — IA locale · Scraping mode · Planification tenues**

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-3.0+-000000?style=flat-square&logo=flask&logoColor=white)](https://flask.palletsprojects.com)
[![Docker](https://img.shields.io/badge/Docker-ready-2496ED?style=flat-square&logo=docker&logoColor=white)](https://docker.com)
[![Claude API](https://img.shields.io/badge/Claude-Sonnet_4.6-D97706?style=flat-square)](https://anthropic.com)
[![Ollama](https://img.shields.io/badge/Ollama-local_LLM-000000?style=flat-square)](https://ollama.ai)

</div>

---

SmartWear est une application web de gestion de garde-robe personnelle combinant un moteur IA hybride (local + cloud) avec un pipeline de scraping de 28 marques de mode. Elle permet d'organiser ses vêtements, générer des suggestions de tenues adaptées à la météo, vérifier la cohérence stylistique et découvrir de nouveaux articles — le tout depuis une interface web.

---

## Table des matières

- [Fonctionnalités](#fonctionnalités)
- [Architecture](#architecture)
- [Stack technique](#stack-technique)
- [Démarrage rapide](#démarrage-rapide)
- [Variables d'environnement](#variables-denvironnement)
- [Pipeline de scraping](#pipeline-de-scraping)
- [Scripts utilitaires](#scripts-utilitaires)
- [Monitoring](#monitoring)
- [Sécurité](#sécurité)
- [Documentation par module](#documentation-par-module)

---

## Fonctionnalités

### Garde-robe & tenues

| Fonctionnalité | Description |
|----------------|-------------|
| **Garde-robe** | Ajout de vêtements avec photo, catégorie, marque, taille, couleur, saison, condition, prix et tags personnalisés |
| **Tenues** | Créez et notez des combinaisons, suivez les ports, générez une photo mannequin via Flux (Pollinations.ai) |
| **Complétion de tenue** | Suggère les pièces manquantes à partir d'un vêtement ancre (IA locale + Claude) |
| **Calendrier** | Planifiez vos tenues jour par jour avec prévisions météo 7 jours (Open-Meteo, sans clé) |
| **Ajout depuis photo** | Extrait et catégorise automatiquement les vêtements d'une photo uploadée |
| **Import en masse** | Importez jusqu'à 40 vêtements simultanément avec photos |

### IA & recommandations

| Fonctionnalité | Technologie |
|----------------|-------------|
| **Styliste IA** | Suggestions adaptées à la météo et à l'occasion — Claude API + Ollama |
| **Similarité visuelle** | Moteur d'embeddings FashionCLIP 100 % local, sans cloud, sans ChromaDB |
| **Vérification de style** | Analyse de cohérence sur photo ou tenue existante — vision multimodale |
| **Boutique intelligente** | Catalogue scrapé (28 marques), ajout direct en garde-robe ou wishlist |
| **Alerte de prix** | Surveillance automatique des articles en wishlist avec notification e-mail de baisse |

### Compte & paramètres

- Inscription avec vérification e-mail, connexion sécurisée, réinitialisation de mot de passe
- Profil utilisateur : genre, esthétique, budget, tailles par défaut, bio
- Paramètres personnalisables : devise, ville météo, clés API chiffrées, couleur d'accent, GIF de chargement
- Dashboard administrateur pour la gestion des utilisateurs

---

## Architecture

```
Projet-d-etude/
│
├── app.py                    # Fabrique Flask + create_app(), migrations auto, warmup IA
├── config.py                 # Constantes globales (catégories, tailles, couleurs) + class Config
├── extensions.py             # Instances partagées : db, csrf, limiter, cache
├── models.py                 # 10 modèles SQLAlchemy (User, ClothingItem, Outfit, …)
│
├── routes/                   # 13 blueprints Flask (1 domaine = 1 fichier)
│   ├── auth.py               # Inscription, connexion, vérification e-mail, reset mdp
│   ├── main.py               # Galerie garde-robe, filtrage, tri, paramètres
│   ├── outfits.py            # CRUD tenues, génération image IA, analyse de style
│   ├── stylist.py            # Suggestions météo-adaptées (Claude + Ollama)
│   ├── ai_recommend.py       # Recommandations par similarité visuelle (FashionCLIP)
│   ├── style_check.py        # Analyse de cohérence stylistique
│   ├── complete.py           # Complétion de tenue depuis un vêtement ancre
│   ├── add_from_photo.py     # Extraction de vêtements depuis une photo
│   ├── boutique.py           # Catalogue scrapé + wishlist + alertes prix
│   ├── calendar.py           # Planification calendrier + météo intégrée
│   ├── profile.py            # Profil, préférences, suppression de compte
│   ├── api.py                # Endpoints AJAX internes (tags, streaming, etc.)
│   └── admin.py              # Dashboard administration
│
├── ai/                       # Moteur IA local
│   ├── pipeline.py           # Orchestrateur : vision → embeddings → scoring → explication
│   ├── vision.py             # Qwen2.5-VL (Ollama) — analyse visuelle des vêtements
│   ├── embeddings.py         # FashionCLIP — stockage vectoriel SQLite + similarité cosinus
│   ├── scoring.py            # Score de compatibilité (embeddings + règles métier)
│   ├── rules.py              # Filtres saison, occasion, cohérence couleurs
│   ├── explainer.py          # Génération d'explications en langage naturel (Ollama)
│   └── ollama_setup.py       # Détection, lancement et pull de modèles Ollama
│
├── utils/                    # Services partagés
│   ├── security.py           # Validators SSRF, open-redirect, localhost-only (centralisés)
│   ├── auth.py               # current_user(), @login_required, get_ctx()
│   ├── images.py             # Validation magic bytes, anti-decompression-bomb, thumbnails
│   ├── ai.py                 # Génération image (Pollinations / SD local) + prompts Claude
│   ├── mail.py               # Envoi SMTP : vérification, reset, alertes prix
│   ├── crypto.py             # Chiffrement Fernet pour les clés API tierces
│   ├── currency.py           # Conversion de devises avec mise en cache
│   ├── weather.py            # WeatherService (Open-Meteo — géolocalisation + prévisions)
│   └── tags.py               # Parsing et normalisation des tags
│
├── pipeline/                 # Module de scraping indépendant (process batch)
│   ├── run.py                # CLI (argparse) — point d'entrée
│   ├── pipeline.py           # Normalisation, déduplication, export JSON / MongoDB
│   ├── scrapers/             # 28 scrapers (Playwright + BeautifulSoup4)
│   │   ├── base.py           # Classe de base commune
│   │   ├── shopify_base.py   # Classe de base pour les marques sur Shopify
│   │   └── *.py              # Nike, Mango, H&M, Lacoste, Kappa, APC, Jacquemus, …
│   └── dags/                 # DAG Apache Airflow (3h UTC quotidien)
│
├── finetune/                 # Pipeline de fine-tuning LLM (offline)
│   ├── bronze.py / silver.py / gold.py   # Étapes médaillon de nettoyage des données
│   ├── prepare_dataset.py / train.py     # Préparation dataset + entraînement LoRA
│   └── data/*.jsonl          # Jeux de données d'entraînement / validation
│
├── scripts/                  # Scripts utilitaires à lancer depuis la racine
│   ├── seed_demo.py          # Crée 2 comptes démo avec vêtements réels du catalogue
│   └── reseed_homme.py       # Réinitialise le compte demo_homme (28 pièces variées)
│
├── monitoring/               # Stack d'observabilité (optionnelle)
│   ├── loki-config.yml       # Agrégation des logs
│   ├── promtail-config.yml   # Collecte des logs applicatifs
│   └── grafana-provisioning/ # Dashboards et datasources auto-provisionnés
│
├── templates/                # 32 templates Jinja2 (base + pages + erreurs + admin)
├── static/uploads/           # Fichiers uploadés par les utilisateurs (gitignored)
├── data/wardrobe.db          # Base SQLite (dev / prod léger)
│
├── docker-compose.yml                # App + ngrok
├── docker-compose.monitoring.yml     # Grafana + Loki + Promtail
└── Dockerfile                        # Image Python 3.11-slim + Playwright
```

---

## Stack technique

| Couche | Technologie | Rôle |
|--------|-------------|------|
| **Web** | Flask 3+ | Serveur, blueprints, CSRF global, rate limiting |
| **Base de données** | SQLite / SQLAlchemy | Persistance (switchable PostgreSQL via `DATABASE_URL`) |
| **Embeddings locaux** | FashionCLIP (HuggingFace / PyTorch) | Similarité visuelle sans dépendance cloud |
| **LLM local** | Ollama — qwen2.5vl:7b | Analyse vision + génération de texte en local |
| **LLM cloud** | Anthropic Claude Sonnet 4.6 | Suggestions avancées, analyse stylistique |
| **Génération d'images** | Pollinations.ai (Flux) | Photos mannequin pour les tenues (gratuit) |
| **Météo** | Open-Meteo | Prévisions 7 jours, sans clé API |
| **Cache** | SimpleCache (dev) / Redis (prod) | Cache serveur configurable |
| **Scraping** | Playwright + BeautifulSoup4 | Sites JS-heavy et HTML statique |
| **Monitoring** | Grafana + Loki + Promtail | Dashboards et agrégation de logs |

---

## Démarrage rapide

### Prérequis

- Docker & Docker Compose **ou** Python 3.11+
- Une clé API Anthropic (fonctionnalités IA cloud — optionnel)
- [Ollama](https://ollama.ai) installé localement (IA locale — optionnel)

---

### Option A — Docker (recommandé)

```bash
# 1. Copier et configurer l'environnement
cp .env.example .env
# Ouvrir .env et renseigner au minimum : SECRET_KEY

# 2. Lancer l'application
docker compose up -d --build

# 3. Accéder à l'app
# → http://localhost:5001
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
```

### Recommandées

```env
ANTHROPIC_API_KEY=sk-ant-...       # Clé API Anthropic (fonctionnalités IA cloud)
ANTHROPIC_MODEL=claude-sonnet-4-6  # Modèle Claude (défaut : claude-sonnet-4-6)
PORT=5001                          # Port du serveur
LOG_DIR=./logs                     # Répertoire de logs (stdout si absent)
ITEMS_PER_PAGE=24                  # Pagination de la galerie
```

### Optionnelles

```env
# Base de données
DATABASE_URL=sqlite:///wardrobe.db # SQLite (défaut) ou postgresql://...

# Cache
CACHE_TYPE=SimpleCache             # SimpleCache (dev) | RedisCache (prod)
REDIS_URL=redis://localhost:6379   # Cache Redis distribué

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

# Mandataire / réseau
TRUSTED_PROXY=<ip>                # IP du reverse proxy de confiance (X-Forwarded-For)
NGROK_AUTHTOKEN=...               # Token ngrok (optionnel)

# Pipeline
MONGO_URI=mongodb://...           # MongoDB pour sortie scraper (optionnel)
```

---

## Pipeline de scraping

Module Python **indépendant** de l'application Flask. Collecte les catalogues de 28 marques de mode, normalise le schéma produit, déduplique et exporte en JSON (ou MongoDB).

**Marques supportées :** Mango, Nike, H&M, ASOS, Lacoste, Kappa, Jules, Le Coq Sportif, Sergio Tacchini, Lotto, APC, Jacquemus, Isabel Marant, Rouje, Ami Paris, Balzac Paris, Maison Labiche, Bonnegueule, Gymshark, Filling Pieces, Stüssy, Palace, Cabaïa, Merci, Karhu, et d'autres via Shopify API.

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

Le pipeline inclut un **DAG Apache Airflow** (`pipeline/dags/scraping_dag.py`) pour une exécution planifiée quotidienne à 3h UTC, et un dashboard de monitoring (`pipeline/dashboard.py`) avec statistiques en temps réel.

Voir [pipeline/README.md](pipeline/README.md) pour la documentation complète.

---

## Scripts utilitaires

Les scripts de maintenance se lancent **depuis la racine du projet** :

```bash
# Créer 2 comptes démo (demo_homme / demo_femme) avec vêtements réels du catalogue
python scripts/seed_demo.py

# Réinitialiser uniquement le compte demo_homme (28 pièces variées, prêt pour la démo IA)
python scripts/reseed_homme.py
```

> Ces scripts requièrent que `pipeline/output/SmartWear_DB.json` existe (lancer d'abord `python -m pipeline.run`).

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

Les logs applicatifs sont émis en JSON structuré compatible Loki/ELK. Les métriques couvrent : tentatives de connexion, uploads, durée de génération IA, performance des scrapers.

---

## Sécurité

| Mesure | Détail |
|--------|--------|
| **Démarrage protégé** | L'app refuse de démarrer sans `SECRET_KEY` |
| **CSRF global** | Flask-WTF sur tous les formulaires et endpoints AJAX, y compris la déconnexion |
| **Rate limiting** | Login, register, reset mdp, resend vérification et endpoints IA protégés par Flask-Limiter |
| **Hachage des mots de passe** | Werkzeug PBKDF2-SHA256 |
| **Vérification e-mail** | Token à usage unique (24 h) — révoque les anciens tokens à chaque nouvelle demande |
| **Reset de mot de passe** | Token à usage unique (expiration 1 h) |
| **Chiffrement des clés API** | Clés tierces (Anthropic, Pollinations) stockées chiffrées en base (Fernet / AES-128-CBC) |
| **Validation des fichiers** | Contrôle par magic bytes (filetype), pas uniquement l'extension |
| **Anti-decompression bomb** | `PIL.Image.MAX_IMAGE_PIXELS = 50 MP` + catch `DecompressionBombError` |
| **Protection SSRF** | `utils/security.py` bloque les IPs privées, loopback et link-local sur tout fetch serveur |
| **Localhost-only pour SD/Ollama** | `is_local_url()` interdit tout hôte autre que `localhost` / `127.x` |
| **Anti open-redirect** | `is_safe_redirect_target()` valide l'origine sur tous les redirects paramétriques |
| **Anti XSS stocké** | Validation du schème d'URL (`http`/`https` uniquement) avant persistance en wishlist |
| **Pas d'open-redirect admin** | Redirect post-reset hardcodé vers `/admin/users/{id}` (plus de paramètre `back`) |
| **Suppression de compte sécurisée** | Efface les fichiers images, le GIF, la photo de visage et les entrées calendrier avant `DELETE` |
| **Commit-first pour les images** | Le fichier remplaçant est écrit, la DB committée, puis l'ancien fichier supprimé |
| **Proxy de confiance** | `X-Forwarded-For` pris en compte uniquement si `TRUSTED_PROXY` est configuré |

---

## Documentation par module

| Module | Documentation |
|--------|---------------|
| Routes & blueprints | [routes/README.md](routes/README.md) |
| Moteur IA local | [ai/README.md](ai/README.md) |
| Services utilitaires | [utils/README.md](utils/README.md) |
| Pipeline de scraping | [pipeline/README.md](pipeline/README.md) |
| Installation complète | [INSTALL.md](INSTALL.md) |

---

## Justification des choix techniques

### Flask plutôt que FastAPI ou Django

Flask a été préféré à ses deux alternatives principales pour des raisons opposées : FastAPI est conçu autour des APIs REST asynchrones et du typage strict, ce qui aurait compliqué l'intégration des templates Jinja2 et la gestion des sessions côté serveur. Django, à l'inverse, impose une structure trop rigide (ORM propriétaire, routing déclaratif, admin généré) pour un projet expérimental qui a évolué par itérations rapides. Flask offre l'équilibre : suffisamment structuré via les blueprints pour organiser 13 domaines fonctionnels, suffisamment léger pour ne pas contraindre les choix d'architecture IA.

### SQLite + SQLAlchemy plutôt qu'une base managée

SQLite a été choisi comme base par défaut pour trois raisons concrètes : zéro infrastructure à provisionner, portabilité totale (la base est un fichier unique), et performances largement suffisantes pour un usage mono-utilisateur à faible concurrence. SQLAlchemy abstrait le dialecte SQL, ce qui permet de basculer vers PostgreSQL via un simple changement de `DATABASE_URL` sans modifier une ligne de code applicatif — testé et validé. Les embeddings FashionCLIP (vecteurs flottants) sont stockés en JSON dans SQLite plutôt que dans un moteur vectoriel dédié (ChromaDB, Pinecone) : à l'échelle d'une garde-robe personnelle (< 1 000 articles), la recherche par similarité cosinus en mémoire est sous-milliseconde et élimine une dépendance externe.

### Architecture IA hybride : local + cloud

Le moteur IA combine délibérément deux niveaux. **Ollama + Qwen2.5-VL** (local) assure l'analyse visuelle des vêtements à l'upload : pas de coût par requête, pas de donnée personnelle envoyée vers un tiers, fonctionnement hors ligne. **Claude API** (cloud) intervient sur les tâches à haute valeur sémantique — suggestions stylistiques contextualisées, analyse de cohérence d'ensemble, génération de prompts complexes — où la qualité du raisonnement justifie le coût. Cette séparation évite aussi de saturer l'API cloud sur des opérations routinières (catégorisation, extraction d'attributs).

### FashionCLIP plutôt qu'un embedding généraliste

Un modèle généraliste comme CLIP d'OpenAI traite les images de mode comme n'importe quelle image naturelle. FashionCLIP (`patrickjohncyh/fashion-clip`) est fine-tuné sur un corpus de 700 000 produits fashion, ce qui produit des espaces d'embedding où la proximité cosinus reflète réellement la similarité vestimentaire (couleur, coupe, style, matière) plutôt qu'une ressemblance visuelle générique. Le modèle tient en ~400 Mo et s'exécute en CPU, ce qui le rend utilisable sans GPU.

### Pollinations.ai plutôt que Stable Diffusion hébergé

La génération d'images de tenues sur mannequin aurait pu reposer entièrement sur un SD local. Pollinations.ai (Flux) a été retenu comme solution par défaut pour deux raisons : gratuité sans clé API obligatoire, et qualité immédiatement exploitable sans configuration de checkpoint, LoRA ou prompt engineering spécialisé. L'option SD local (A1111 / ComfyUI) reste disponible via `local_sd_url` pour les utilisateurs qui préfèrent la confidentialité ou le contrôle total.

### Playwright + BeautifulSoup4 pour le scraping

Les 28 marques ciblées se répartissent en deux catégories techniques. Les marques sur Shopify exposent une API JSON (`/products.json`) exploitable directement via `requests` + `BeautifulSoup4` — rapide, stable, peu gourmand. Les marques avec sites JS-heavy (rendu React/Next.js côté client) nécessitent un navigateur sans tête : Playwright a été préféré à Selenium pour sa gestion native des contextes asynchrones, son API plus moderne et sa meilleure détection des requêtes réseau. La classe `shopify_base.py` factorise les 18 marques Shopify, limitant à ~60 lignes chaque scraper spécifique.

### Open-Meteo plutôt que OpenWeatherMap

Open-Meteo fournit des prévisions 7 jours avec résolution horaire, géolocalisation par nom de ville, et données de couverture nuageuse — sans clé API, sans quota, sans compte. OpenWeatherMap propose des données équivalentes mais impose un enregistrement et une limite sur le plan gratuit. Pour un projet académique où la météo est une fonctionnalité d'appoint (suggestions de tenues), éliminer cette friction d'onboarding a simplifié le déploiement.

### Grafana + Loki plutôt qu'ELK ou Datadog

La stack ELK (Elasticsearch + Logstash + Kibana) aurait requis 4–8 Go de RAM pour Elasticsearch seul. Datadog est un SaaS payant. Loki (agrégation de logs à la Prometheus, sans indexation full-text) + Promtail (collecteur) + Grafana (visualisation) tourne en moins de 512 Mo au total et s'intègre en une dizaine de lignes de configuration. La stack est optionnelle et entièrement découplée de l'application via `docker-compose.monitoring.yml` séparé.

### Fernet pour le chiffrement des clés API

Les clés API tierces (Anthropic, Pollinations) saisies par l'utilisateur dans l'interface sont stockées chiffrées en base. Fernet (AES-128-CBC + HMAC-SHA256, bibliothèque `cryptography`) a été retenu pour sa simplicité d'usage : une clé symétrique dérivée de `SECRET_KEY`, un appel à `Fernet.encrypt()` / `decrypt()`, et une résistance aux attaques par altération (l'HMAC invalide tout chiffré modifié). L'alternative — stocker en clair et compter sur les permissions de la base — était inacceptable dès lors que la base SQLite peut être exfiltrée comme un fichier ordinaire.
