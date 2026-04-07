# ai/ — Moteur IA local

Module de recommandation de vêtements par embeddings visuels et textuels, sans dépendance cloud obligatoire.

## Fichiers

| Fichier | Rôle |
|---------|------|
| `pipeline.py` | Orchestrateur : coordonne vision → embeddings → scoring → explication |
| `vision.py` | Extraction de features visuelles depuis les photos (FashionCLIP) |
| `embeddings.py` | Stockage et recherche des embeddings dans SQLite |
| `scoring.py` | Calcul du score de similarité et classement des recommandations |
| `rules.py` | Règles métier (saison, occasion, cohérence couleurs) |
| `explainer.py` | Génération d'explications textuelles via Ollama |
| `ollama_setup.py` | Détection et configuration automatique d'Ollama au démarrage |

## Flux de recommandation

```
Photo d'un vêtement
    → vision.py         — embedding visuel (FashionCLIP)
    → embeddings.py     — recherche des k plus proches voisins en base
    → scoring.py        — score combiné (similarité + règles métier)
    → rules.py          — filtres saison / occasion / couleur
    → explainer.py      — explication en langage naturel (Ollama)
    → résultat affiché dans /ai-recommend
```

## Dépendances

Incluses dans `requirements.txt` à la racine :

```
torch
transformers
accelerate
```

FashionCLIP est téléchargé automatiquement à la première utilisation (HuggingFace Hub). En mode offline (`HF_HUB_OFFLINE=1`), le modèle doit être présent dans le cache local.

## Ollama (optionnel)

`ollama_setup.py` détecte Ollama au démarrage de l'app et configure le modèle. Sans Ollama, les explications sont générées par un template textuel simple.
