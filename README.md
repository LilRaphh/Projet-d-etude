# SmartWear — Scraper

## Structure

```
scraper/
├── config.py          # Constantes, schéma JSON cible, valeurs autorisées
├── models.py          # Dataclass Product + validation
├── scrapers/
│   ├── __init__.py
│   ├── base.py        # Classe abstraite commune (helpers partagés)
│   ├── mango.py       # Scraper Mango  (requests + BeautifulSoup)
│   ├── nike.py        # Scraper Nike   (requests + BeautifulSoup)
│   ├── jules.py       # Scraper Jules  (Playwright)
│   └── celio.py       # Scraper Célio  (Playwright)
├── pipeline.py        # Normalisation + enrichissement Gemini + MongoDB
├── main.py            # Point d'entrée unique
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── .env.example
```

## Schéma produit (sortie JSON / MongoDB)

| Champ          | Type        | Valeurs                                              |
|----------------|-------------|------------------------------------------------------|
| name           | str         |                                                      |
| price_value    | float       |                                                      |
| currency       | str         | EUR, USD                                             |
| description    | str         |                                                      |
| genre          | str         | Enfant, Adolescent, Adulte                           |
| sexe           | str         | Femme, Homme, Fille, Garçon                          |
| sizes          | list[int]   | [36, 37, 38 …] — chaussures uniquement               |
| taille         | list[str]   | [S, M, L, XL, XXL] — vêtements uniquement            |
| color          | str         |                                                      |
| rating         | float       | 1.0 – 5.0                                            |
| type           | str         | Vêtement, Chaussures, Autre                          |
| categorie      | str         | Haut, Bas, Robe/Combinaison, Manteau/Veste, Autre    |
| style          | str         | Jean, Pull, T-shirt, Sneakers, Manteau …             |
| image          | str         | URL                                                  |
| url            | str         | URL                                                  |
| brand_source   | str         | Mango, Nike, Jules, Celio                            |
| age            | int         | Rempli par Gemini                                    |
| categorie_age  | str         | (18;25), (26;40) … Rempli par Gemini                 |
| saison         | str         | Été, Automne, Hiver, Printemps — Rempli par Gemini   |

## Lancement

### En local
```bash
cp .env.example .env
pip install -r requirements.txt
playwright install chromium

# Tous les scrapers
python main.py

# Scrapers spécifiques
python main.py --scrapers mango nike

# Sans enrichissement IA
python main.py --no-ai
```

### Via Docker
```bash
cp .env.example .env
docker-compose up --build scraper
```

### Stack complète (Scraper + MongoDB + Django)
```bash
docker-compose up --build
```

## Variables d'environnement

| Variable              | Description                        |
|-----------------------|------------------------------------|
| MONGO_URI             | URI MongoDB (auto dans Docker)     |
| GOOGLE_GEMINI_API_KEY | Clé API Gemini                     |
| DJANGO_SECRET_KEY     | Clé secrète Django                 |
