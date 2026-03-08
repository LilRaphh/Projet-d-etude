# 👗 Wardrobe v4 — Garde-robe + Tenues + IA

## Installation

```bash
pip install flask flask-sqlalchemy pillow requests
pip install anthropic   # optionnel, améliore la génération IA
```

## Lancement

```bash
python app.py            # localhost seulement
python app.py --host     # PC + téléphone (même WiFi)
python app.py --debug    # mode développeur
```

---

## Génération d'images IA

### Sans clé (gratuit, automatique)
L'app génère automatiquement un prompt basique et utilise **Flux AI via Pollinations.ai** (gratuit, sans inscription).

### Avec clé Claude (optionnel, meilleurs résultats)
Claude analyse votre tenue et génère un prompt optimisé avant l'image.

```bash
# Windows
set ANTHROPIC_API_KEY=sk-ant-...

# Mac/Linux
export ANTHROPIC_API_KEY=sk-ant-...
```

Ou entrez votre clé directement dans **⚙️ Paramètres** de l'application.

Obtenez une clé sur : https://console.anthropic.com

---

## Nouvelles fonctionnalités v4

- **Page Tenues** (`/outfits`) — créez des combinaisons de vêtements
- **Sélecteur visuel** — cliquez sur vos pièces pour les ajouter à une tenue
- **Métadonnées tenues** — occasion, saison, note 1-5 étoiles, commentaires
- **Génération IA** — image mannequin générée depuis la page détail d'une tenue
- **Compteur de port** — suivez combien de fois vous avez mis une tenue
- **Navigation améliorée** — onglet Tenues avec compteur dans le header

---

## Architecture de génération

```
Bouton "Générer" 
    → POST /outfits/<id>/generate
    → Claude API (si clé dispo) → prompt fashion optimisé
        OU fallback → prompt basique auto-construit
    → Pollinations.ai Flux (gratuit) → image JPG 512×768
    → Sauvegarde dans static/uploads/outfits/
    → Mis à jour dans wardrobe.db
    → Affiché instantanément sans rechargement
```
