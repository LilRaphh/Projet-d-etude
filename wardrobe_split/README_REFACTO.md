# Wardrobe v5 — version découpée

## Structure

- `app.py` : point d'entrée Flask
- `config.py` : constantes et configuration
- `extensions.py` : extensions Flask (ici `db`)
- `models.py` : tous les modèles SQLAlchemy
- `routes/` : routes séparées par domaine
  - `auth.py`
  - `main.py`
  - `outfits.py`
  - `api.py`
- `utils/` : helpers réutilisables
  - `auth.py`
  - `images.py`
  - `tags.py`
  - `ai.py`

## Lancement

Depuis le dossier `wardrobe_split` :

```bash
python app.py
python app.py --debug
python app.py --host
```

## Important

Cette version reprend **la logique de ton `app.py` monolithique** mais suppose que tes templates existent bien côté projet :

- `index.html`
- `login.html`
- `register.html`
- `item_form.html`
- `item_detail.html`
- `outfits.html`
- `outfit_form.html`
- `outfit_detail.html`

Si chez toi les noms réels diffèrent (`add_edit.html`, `detail.html`, etc.), il faudra soit renommer les templates, soit ajuster les `render_template(...)`.
