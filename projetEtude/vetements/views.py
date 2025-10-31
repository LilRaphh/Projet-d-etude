from django.shortcuts import render
from .models import ClothingItem  # ← on importe le modèle

def accueil(request):
    return render(request, 'vetements/accueil.html')

def about(request):
    return render(request, 'vetements/about.html')

def catalogue(request):
    vetements = ClothingItem.objects.all().order_by('-created_at')  # ← récupère les données réelles
    return render(request, 'vetements/catalogue.html', {'vetements': vetements})
