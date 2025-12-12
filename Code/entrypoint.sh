#!/bin/bash
set -e

# Appliquer les migrations
python manage.py makemigrations --noinput
python manage.py migrate --noinput

# Créer un superutilisateur si aucun n’existe
echo "from django.contrib.auth.models import User;
import os;
username = os.getenv('DJANGO_SUPERUSER_USERNAME', 'admin');
email = os.getenv('DJANGO_SUPERUSER_EMAIL', 'admin@example.com');
password = os.getenv('DJANGO_SUPERUSER_PASSWORD', 'adminpass');
if not User.objects.filter(username=username).exists():
    User.objects.create_superuser(username, email, password);
    print(f'Superuser \"{username}\" créé avec succès.');
else:
    print(f'Superuser \"{username}\" déjà existant.');" | python manage.py shell

# Lancer le serveur
python manage.py runserver 0.0.0.0:8000
