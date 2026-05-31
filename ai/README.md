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
| `ollama_setup.py` | Détection, démarrage et pull des modèles Ollama au lancement de l'app |

## Flux de recommandation

```
Photo d'un vêtement
    → vision.py         — embedding visuel (FashionCLIP)
    → embeddings.py     — recherche des k plus proches voisins en base
    → scoring.py        — score combiné (similarité cosinus + règles métier)
    → rules.py          — filtres saison / occasion / couleur
    → explainer.py      — explication en langage naturel (Ollama)
    → résultat affiché dans /ai-recommend
```

## Dépendances

Incluses dans `requirements.txt` à la racine :

```
torch>=2.1.0
transformers>=4.40.0
accelerate>=0.27.0
```

**FashionCLIP** est téléchargé automatiquement depuis HuggingFace Hub au premier démarrage.  
Le cache est contrôlé par `$HF_HOME` (défaut : `~/.cache/huggingface`).

En mode offline (`HF_HUB_OFFLINE=1`), le modèle doit être présent dans le cache local.  
En Docker, ce mode est désactivé au premier démarrage (`HF_HUB_OFFLINE=0`) pour permettre le téléchargement initial, puis l'app le réactive en mémoire pour les runs suivants.

## Ollama

`ollama_setup.py` s'exécute en arrière-plan au démarrage de l'app :

1. Vérifie si Ollama est déjà actif sur `$OLLAMA_URL` (défaut : `http://localhost:11434`)
2. Si non, tente de lancer `ollama serve` en subprocess
3. Pull les modèles manquants (`$VISION_MODEL`, `$TEXT_MODEL` — défaut : `qwen2.5vl:7b`)

Sans Ollama, les explications sont générées par un template textuel simple (mode dégradé).

## Variables d'environnement

| Variable | Défaut | Description |
|----------|--------|-------------|
| `OLLAMA_URL` | `http://localhost:11434` | URL du serveur Ollama |
| `VISION_MODEL` | `qwen2.5vl:7b` | Modèle vision Ollama |
| `TEXT_MODEL` | `qwen2.5vl:7b` | Modèle texte Ollama |
| `HF_HOME` | `~/.cache/huggingface` | Dossier du cache HuggingFace |
| `HF_HUB_OFFLINE` | `1` (app) / `0` (Docker init) | Mode offline HuggingFace |
