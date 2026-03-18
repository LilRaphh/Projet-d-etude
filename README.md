# Wardrobe v5 — Garde-robe + Tenues + IA

Application Flask de gestion de garde-robe personnelle avec génération d'images IA et suggestions de tenues par Claude.

---

## Installation

```bash
python -m venv .venv
source .venv/bin/activate          # Mac/Linux
# .venv\Scripts\activate           # Windows

pip install -r requirements.txt
```

---

## Configuration

Copiez `.env.example` en `.env` et remplissez les valeurs :

```bash
cp .env.example .env
```

La variable `SECRET_KEY` est **obligatoire**. Générez-en une :

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Collez la valeur dans votre `.env` :

```
SECRET_KEY=<votre-clé-générée>
```

> Le fichier `.env` ne doit jamais être commité (il est dans `.gitignore`).

---

## Lancement

```bash
python app.py            # localhost seulement
python app.py --host     # accessible sur le réseau local (PC + téléphone)
python app.py --debug    # mode développeur avec rechargement auto
```

---

## Génération d'images IA

### Sans clé (gratuit, automatique)
L'app génère automatiquement un prompt et utilise **Flux via Pollinations.ai** (gratuit, sans inscription).

### Avec clé Claude (optionnel, meilleurs résultats)
Claude analyse la tenue et génère un prompt optimisé avant l'image.

Entrez votre clé dans **⚙️ Paramètres** de l'application.
Elle est stockée **chiffrée** en base de données (Fernet/AES-256).

Obtenez une clé : https://console.anthropic.com

---

## Fonctionnalités

- **Garde-robe** — ajout de vêtements avec photo, catégorie, marque, taille, couleur, saison, condition, prix, notes, tags
- **Tenues** — créez des combinaisons, notez-les, suivez le nombre de ports
- **Génération IA** — image mannequin générée pour chaque tenue (Pollinations + Claude optionnel)
- **Styliste IA** — suggestions de tenues adaptées à la météo et à l'occasion via Claude
- **Météo** — prévisions 7 jours intégrées (Open-Meteo, sans API key)
- **Paramètres** — nom de l'app, couleur d'accent, devise, ville, clés API

---

## Architecture de génération d'image

```
Bouton "Générer"
    → POST /outfits/<id>/generate
    → Claude API (si clé dispo) → prompt fashion optimisé
        OU fallback → prompt auto-construit
    → Pollinations.ai Flux (gratuit) → image JPG
    → Sauvegarde dans static/uploads/outfits/
    → Mis à jour en base
    → Affiché sans rechargement de page
```

---

## Sécurité

- `SECRET_KEY` obligatoire au démarrage (pas de fallback hardcodé)
- Clés API chiffrées en base (Fernet dérivé de `SECRET_KEY`)
- Protection CSRF sur tous les formulaires et appels AJAX
- Rate limiting sur login (10/min) et register (5/min)
- Validation des uploads par magic bytes (extension + type MIME réel)
- Passwords hashés (werkzeug)

---

## Variables d'environnement

| Variable | Obligatoire | Description |
|----------|-------------|-------------|
| `SECRET_KEY` | Oui | Clé secrète Flask (sessions, CSRF) |
| `FERNET_KEY` | Non | Clé de chiffrement (dérivée de SECRET_KEY si absente) |
| `PORT` | Non | Port d'écoute (défaut : 5000) |
| `LOG_DIR` | Non | Dossier de logs fichier (défaut : console uniquement) |
| `ANTHROPIC_MODEL` | Non | Modèle Claude (défaut : claude-sonnet-4-5) |
| `ITEMS_PER_PAGE` | Non | Items par page dans la galerie (défaut : 24) |
| `CACHE_TYPE` | Non | Backend cache (défaut : SimpleCache) |
| `REDIS_URL` | Non | URL Redis pour cache/rate limiting en production |

---

## Réinitialiser la base de données

```bash
python app.py --reset-db
```
