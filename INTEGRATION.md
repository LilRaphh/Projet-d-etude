# Intégration du Styliste IA

## Fichiers à placer

| Fichier | Destination |
|---------|------------|
| `routes/stylist.py` | `ton_projet/routes/stylist.py` |
| `templates/stylist.html` | `ton_projet/templates/stylist.html` |
| `templates/base.html` | Remplace `ton_projet/templates/base.html` |

## Enregistrer le blueprint (1 ligne)

Dans ton fichier `routes/__init__.py`, ajoute :

```python
from routes.stylist import stylist_bp
app.register_blueprint(stylist_bp)
```

## Clé API

```bash
# Windows
set ANTHROPIC_API_KEY=sk-ant-...

# Mac / Linux
export ANTHROPIC_API_KEY=sk-ant-...
```

Ou entre-la directement dans les Paramètres de l'app (champ ajouté dans base.html).

## Dépendances

Déjà dans ton requirements.txt :
- `requests` — pour Open-Meteo (météo)
- `anthropic` — pour Claude (suggestions)

