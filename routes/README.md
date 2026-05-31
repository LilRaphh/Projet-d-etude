# routes/ — Blueprints Flask

Chaque fichier est un blueprint enregistré dans `app.py` via `routes/__init__.py`.

## Blueprints

| Fichier | Préfixe URL | Rôle |
|---------|-------------|------|
| `auth.py` | `/` | Inscription, connexion, déconnexion, vérification e-mail, réinitialisation mot de passe |
| `main.py` | `/` | Page d'accueil, galerie garde-robe, fiche vêtement, paramètres |
| `outfits.py` | `/outfits` | Création et gestion des tenues, génération d'image IA (Pollinations / Claude) |
| `complete.py` | `/` | Complétion de tenue — suggestions pour compléter un look depuis un vêtement ancre |
| `stylist.py` | `/` | Suggestions IA adaptées à la météo et à l'occasion (Claude + Ollama) |
| `ai_recommend.py` | `/ai` | Recommandations par similarité visuelle (FashionCLIP) |
| `style_check.py` | `/` | Vérification de style via analyse de photo (Groq Vision / Claude) |
| `boutique.py` | `/` | Catalogue scrapé — parcourir, ajouter à la garde-robe ou à la wishlist |
| `calendar.py` | `/calendar` | Calendrier de tenues — planification jour par jour |
| `profile.py` | `/` | Profil utilisateur — genre, esthétique, budget, tailles par défaut |
| `api.py` | `/api` | Endpoints JSON internes (AJAX, autocomplétion tags, streaming IA) |
| `admin.py` | `/admin` | Administration (réservé aux comptes admin) |

## Conventions

- Chaque blueprint a son propre nom unique ; les conflits de noms de routes sont évités par le préfixe de blueprint.
- La protection CSRF est globale (Flask-WTF) — les routes AJAX POST reçoivent le token via le header `X-CSRFToken`.
- Le rate limiting est appliqué par Flask-Limiter sur les routes sensibles (login, register, upload, génération IA).
- Les routes protégées utilisent `@login_required` depuis `utils/auth.py`.
