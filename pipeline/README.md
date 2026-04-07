# pipeline/ — SmartWear Scraping Pipeline

Collecte automatisée de produits mode depuis 7 marques, avec normalisation du schéma, déduplication, audit qualité, et export JSON / MongoDB.

## Structure

```
pipeline/
├── config.py           ← constantes (chemins, schéma, valeurs autorisées)
├── models.py           ← dataclass Product + validation / normalisation
├── pipeline.py         ← normalisation + sauvegarde JSON + upsert MongoDB
├── audit.py            ← déduplication, nettoyage descriptions, inférence sexe/catégorie
├── check.py            ← vérification des incohérences style/catégorie
├── logging_config.py   ← logs JSON structurés (Airflow, Grafana/Loki, ELK)
├── run.py              ← point d'entrée CLI
├── requirements.txt    ← dépendances isolées (requests, playwright, pymongo…)
├── scrapers/           ← un fichier par marque
│   ├── base.py         ← classe abstraite BaseScraper
│   ├── mango.py
│   ├── nike.py         ← Playwright (JS)
│   ├── jules.py        ← Playwright (JS)
│   ├── kappa.py        ← API Shopify
│   ├── lecoqsportif.py ← API Shopify
│   ├── lotto.py        ← API Shopify
│   └── tacchini.py     ← API Shopify
├── dags/
│   └── scraping_dag.py ← DAG Airflow
└── output/             ← JSON générés (gitignored)
    └── SmartWear_DB.json
```

## Lancement CLI

```bash
pip install -r pipeline/requirements.txt
playwright install chromium          # requis pour Nike et Jules

python -m pipeline.run                              # tous les scrapers
python -m pipeline.run --scrapers mango kappa       # scrapers choisis
python -m pipeline.run --log-level DEBUG
```

## Flux d'exécution

```
scraper_X.run()           ← collecte les produits (Product dataclass)
    ↓
SmartWearPipeline.run()   ← normalise + sauvegarde output/SmartWear_DB.json
    ↓
run_audit()               ← dédoublonne, nettoie, infère les champs manquants
    ↓
run_check()               ← signale les incohérences style/catégorie restantes
```

## Airflow

Le DAG `dags/scraping_dag.py` crée une task par scraper (parallèles) puis enchaîne pipeline → audit → check. Schedule par défaut : **chaque nuit à 3h UTC**.

```bash
# Déploiement
ln -s $(pwd)/pipeline/dags/scraping_dag.py $AIRFLOW_HOME/dags/

# Ou copie directe
cp pipeline/dags/scraping_dag.py $AIRFLOW_HOME/dags/
```

## Logs structurés

`logging_config.py` écrit chaque log en JSON sur stdout (capturé par Airflow) et dans `pipeline/logs/pipeline_<timestamp>.jsonl` (rotation 10 Mo, 5 fichiers).

Format d'une ligne :
```json
{"ts": "2026-04-07T03:00:01+00:00", "level": "INFO", "logger": "pipeline.scrapers.mango", "scraper": "mango", "msg": "..."}
```

Compatible Grafana/Loki (`logfmt` ou `json` parser), ELK (Logstash JSON input), et tout outil qui consomme des fichiers `.jsonl`.

## Schéma produit

| Champ | Type | Valeurs autorisées |
|-------|------|--------------------|
| `name` | str | — |
| `price_value` | float | — |
| `currency` | str | `EUR`, `USD` |
| `genre` | str | `Enfant`, `Adolescent`, `Adulte` |
| `sexe` | str | `Femme`, `Homme`, `Fille`, `Garçon` |
| `type` | str | `Vêtement`, `Chaussures`, `Autre` |
| `categorie` | str | `Haut`, `Bas`, `Robe/Combinaison`, `Manteau/Veste`, `Autre` |
| `style` | str | Jean, Pull, T-shirt, Hoodie… (26 valeurs) |
| `taille` | list[str] | XS, S, M, L, XL, XXL, XXXL |
| `sizes` | list[int] | pointures (chaussures uniquement) |

## MongoDB (optionnel)

Définissez `MONGO_URI` dans `.env`. Le pipeline fait un upsert par `url` — pas de doublons en base même sur plusieurs runs.

```
MONGO_URI=mongodb://user:pass@localhost:27017/smartwear?authSource=admin
```
