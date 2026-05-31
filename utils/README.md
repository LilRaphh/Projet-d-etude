# utils/ — Services partagés

Utilitaires transverses utilisés par les routes et les modules IA.

## Fichiers

| Fichier | Rôle |
|---------|------|
| `auth.py` | Décorateurs de protection des routes (`@login_required`, `get_ctx()`) |
| `weather.py` | Service météo centralisé (Open-Meteo) — géocodage, météo courante, prévisions 7 jours |
| `crypto.py` | Chiffrement / déchiffrement des clés API (Fernet dérivé de `SECRET_KEY`) |
| `images.py` | Validation des uploads (magic bytes), redimensionnement et sauvegarde des photos |
| `mail.py` | Envoi d'e-mails (vérification de compte, réinitialisation de mot de passe) |
| `tags.py` | Parsing et normalisation des tags vêtements |

## WeatherService (`weather.py`)

Deux méthodes statiques, aucune clé API requise (Open-Meteo est gratuit et open source) :

- `WeatherService.get_current(city)` — météo courante (température, ressenti, vent, humidité, icône WMO). Résultat mis en cache 5 min par utilisateur dans Flask-Caching.
- `WeatherService.get_forecast(city)` — prévisions complètes 7 jours + horaire 24h pour `/forecast`.

## CryptoService (`crypto.py`)

Les clés API saisies par l'utilisateur (Anthropic, Groq…) ne sont jamais stockées en clair.  
`CryptoService` dérive une clé Fernet à partir de `SECRET_KEY` et chiffre/déchiffre à la volée.  
Si `FERNET_KEY` est définie dans `.env`, elle est utilisée directement.

## Validation des uploads (`images.py`)

Les fichiers uploadés sont validés par **magic bytes** (pas seulement l'extension) via la lib `filetype`. Seuls `png`, `jpg`, `jpeg`, `webp` et `gif` sont acceptés. Les images sont ensuite redimensionnées et converties en JPEG avant sauvegarde (`THUMB_SIZE = 500×500`).
