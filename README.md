# 🚀 Application Django 

## 1. Présentation générale

Cette application est développée avec **Django** et a pour objectif de fournir une base web robuste intégrant :
- une architecture Django propre et modulaire,
- une base de données PostgreSQL (hébergée sur Neon),
- un environnement prêt pour le développement local et l’industrialisation (Docker).

Ce README constitue **la documentation de référence** pour comprendre, lancer, maintenir et déboguer l’application.

---

## 2. Technologies utilisées

- Python 3.10+
- Django 4+
- PostgreSQL (Neon)
- Docker & Docker Compose
- HTML / CSS (templates Django)

---

## 3. Architecture du projet

```text
project_root/
├── manage.py
├── README.md
├── requirements.txt
├── .env
│
├── config/
│   ├── settings.py
│   ├── urls.py
│   ├── asgi.py
│   └── wsgi.py
│
├── apps/
│   └── vetements/
│       ├── models.py
│       ├── views.py
│       ├── urls.py
│       ├── admin.py
│       └── migrations/
│
├── templates/
├── static/
└── docker/
```

**Principes clés :**
- `config` : configuration globale Django
- `apps` : logique métier
- séparation stricte configuration / métier

---

## 4. Installation du projet

### 4.1 Pré-requis

- Python installé
- Accès à une base PostgreSQL
- pip ou équivalent
- (optionnel) Docker

### 4.2 Installation des dépendances

```bash
pip install -r requirements.txt
```

Vérification Django :
```bash
python -c "import django; print(django.get_version())"
```

---

## 5. Variables d’environnement

Le fichier `.env` est obligatoire.

```env
DEBUG=True
SECRET_KEY=your_secret_key
DATABASE_URL=postgresql://user:password@host:port/dbname
```

Vérification :
```bash
python manage.py shell
```

```python
from django.conf import settings
settings.DATABASES
```

---

## 6. Base de données

### 6.1 Configuration PostgreSQL (Neon)

```python
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "neondb",
        "HOST": "...neon.tech",
        "PORT": "5432",
        "OPTIONS": {"sslmode": "require"},
    }
}
```

### 6.2 Migrations

```bash
python manage.py makemigrations
python manage.py migrate
```

Vérification :
```bash
python manage.py dbshell
```

```sql
\dt
```

---

## 7. Lancement de l’application

```bash
python manage.py runserver
```

Accès :
```
http://127.0.0.1:8000/
```

---

## 8. Routage (URLs)

### 8.1 URLs globales

```python
path("", include("apps.vetements.urls"))
```

### 8.2 URLs applicatives

```python
path("catalogue/", catalogue, name="catalogue")
```

---

## 9. Templates et Static

### Templates

```python
TEMPLATES[0]["DIRS"] = [BASE_DIR / "templates"]
```

### Static

```python
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
```

---

## 10. Interface d’administration

Création d’un superutilisateur :
```bash
python manage.py createsuperuser
```

Accès :
```
/admin
```

---

## 11. Docker (optionnel)

```bash
docker compose up --build
```

Points de vigilance :
- ports exposés,
- accès réseau à Neon,
- variables injectées via `.env`.

---

## 12. Commandes utiles

```bash
python manage.py runserver
python manage.py makemigrations
python manage.py migrate
python manage.py shell
python manage.py dbshell
python manage.py createsuperuser
```

---

## 13. Débogage & erreurs fréquentes

### Table inexistante
Cause : migrations non appliquées.

### Mauvaise base de données
Cause : mauvais `.env` chargé.

### Page introuvable (404)
Cause : URLs non incluses.

---

## 14. Bonnes pratiques

- Toujours migrer après modification d’un modèle
- Ne jamais versionner le `.env`
- Isoler la logique métier dans les apps
- Documenter chaque nouvelle fonctionnalité

---

## 15. Conclusion

Ce README permet :
- une prise en main rapide du projet,
- un lancement sans erreur,
- une base saine pour le développement et la production.

Il sert de **document de référence technique**.
