# SmartWear — Garde-robe intelligente

Application Flask de gestion de garde-robe personnelle, couplée à un pipeline de scraping de données mode.

---

## Deux modules, une base de code

| Module | Rôle |
|--------|------|
| **App Flask** (racine) | Gestion de la garde-robe, tenues, IA stylist, météo |
| **pipeline/** | Scraping de catalogues mode, normalisation, export MongoDB |

---

## App Flask

### Fonctionnalités

- **Garde-robe** — ajout de vêtements (photo, catégorie, marque, taille, couleur, saison, condition, prix, notes, tags)
- **Tenues** — créez des combinaisons, notez-les, suivez le nombre de ports
- **Génération IA** — image mannequin générée pour chaque tenue via Flux (Pollinations.ai, gratuit) ou Claude (optionnel)
- **Styliste IA** — suggestions de tenues adaptées à la météo et à l'occasion, powered by Claude + Ollama
- **Recommandation IA locale** — moteur de recommandation par similarité d'embeddings (FashionCLIP), sans cloud
- **Météo** — prévisions 7 jours intégrées (Open-Meteo, sans clé API)
- **Paramètres** — nom de l'app, couleur d'accent, devise, ville, clés API

### Architecture

```
app.py              ← point d'entrée Flask
config.py           ← constantes et classe Config
extensions.py       ← instances SQLAlchemy, CSRF, cache, limiter
models.py           ← modèles SQLAlchemy (User, ClothingItem, Outfit…)
routes/             ← blueprints Flask (auth, main, outfits, stylist, api…)
ai/                 ← moteur IA local (embeddings, scoring, pipeline)
utils/              ← services partagés (météo, crypto, images, tags)
templates/          ← templates Jinja2
static/             ← CSS, JS, uploads photos
```

### Sécurité

- `SECRET_KEY` obligatoire au démarrage
- Clés API chiffrées en base (Fernet / AES-256)
- Protection CSRF sur tous les formulaires et appels AJAX
- Rate limiting sur login (10/min) et register (5/min)
- Validation des uploads par magic bytes
- Passwords hashés (werkzeug)

---

## Pipeline de scraping

Collecte automatisée depuis 7 marques (Mango, Nike, Jules, Le Coq Sportif, Sergio Tacchini, Kappa, Lotto), avec normalisation du schéma, déduplication, export JSON / MongoDB.

Pilotable en CLI ou via Apache Airflow. Voir [pipeline/README.md](pipeline/README.md).

---

## Installation

Voir [INSTALL.md](INSTALL.md).
