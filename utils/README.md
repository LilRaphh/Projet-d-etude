# utils/ — Services partagés

Utilitaires transverses utilisés par les routes et les modules IA.

## Fichiers

| Fichier | Rôle |
|---------|------|
| `weather.py` | Service météo centralisé (Open-Meteo) — géocodage, météo courante, prévisions 7 jours |
| `crypto.py` | Chiffrement / déchiffrement des clés API (Fernet dérivé de `SECRET_KEY`) |
| `auth.py` | Décorateurs de protection des routes (`@login_required`, etc.) |
| `images.py` | Validation, redimensionnement et sauvegarde des photos uploadées |
| `tags.py` | Parsing et normalisation des tags vêtements |

## WeatherService (`weather.py`)

Deux méthodes statiques :

- `WeatherService.get_current(city)` — météo courante (température, ressenti, vent, humidité, icône WMO) — utilisée dans le header global et la page styliste.
- `WeatherService.get_forecast(city)` — prévisions complètes 7 jours + horaire 24h — utilisée dans `/forecast`.

Aucune clé API requise (Open-Meteo est gratuit et open source).
