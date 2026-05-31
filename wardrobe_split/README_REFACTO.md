# wardrobe_split/ — Archive de refactorisation

Ce dossier contient une version intermédiaire de l'app créée lors d'une étape de refactorisation (découpage du `app.py` monolithique en blueprints).

**Ce code est obsolète.** La version active est à la racine du projet.

## Différences avec la version courante

| Aspect | wardrobe_split/ | Racine (version active) |
|--------|----------------|------------------------|
| Blueprints | 4 (auth, main, outfits, api) | 12 (+ stylist, ai, style_check, boutique, complete, calendar, profile, admin) |
| IA | Basique | FashionCLIP, Ollama, Claude, Groq |
| Auth | Login/Register | + vérification e-mail, reset mot de passe |
| Docker | Non | Oui (`Dockerfile` + `docker-compose.yml`) |

## Structure (à titre de référence)

```
wardrobe_split/
├── app.py          ← point d'entrée
├── config.py       ← constantes
├── extensions.py   ← SQLAlchemy, CSRF
├── models.py       ← modèles (sous-ensemble)
└── routes/         ← auth, main, outfits, api
```
