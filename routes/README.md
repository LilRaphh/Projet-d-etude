# routes/ — Blueprints Flask

Chaque fichier est un blueprint enregistré dans `app.py` via `routes/__init__.py`.

## Blueprints

| Fichier | Préfixe | Rôle |
|---------|---------|------|
| `auth.py` | `/` | Inscription, connexion, déconnexion |
| `main.py` | `/` | Page d'accueil, garde-robe, fiche vêtement, paramètres |
| `outfits.py` | `/outfits` | Création et gestion des tenues, génération d'image IA |
| `stylist.py` | `/stylist` | Suggestions IA adaptées à la météo et à l'occasion |
| `ai_recommend.py` | `/ai-recommend` | Recommandations par similarité visuelle (FashionCLIP) |
| `profile.py` | `/profile` | Profil utilisateur (genre, esthétique, budget) |
| `api.py` | `/api` | Endpoints JSON internes (AJAX, autocomplétion tags) |

## Conventions

- Chaque blueprint a son propre `url_prefix` et son nom unique.
- La protection CSRF est globale (Flask-WTF) — les routes AJAX POST reçoivent le token via header `X-CSRFToken`.
- Le rate limiting est appliqué au niveau blueprint (Flask-Limiter) pour les routes sensibles.
