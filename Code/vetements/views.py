from .models import ClothingItem  # ← on importe le modèle
from django.shortcuts import render, get_object_or_404, redirect
from .models import Vetement
from .forms import VetementForm

def accueil(request):
    derniers_vetements = Vetement.objects.order_by("-created_at")[:6]

    return render(request, "vetements/accueil.html", {
        "derniers_vetements": derniers_vetements
    })

def about(request):
    return render(request, 'vetements/about.html')

def catalogue(request):
    vetements = ClothingItem.objects.all().order_by('-created_at')  # ← récupère les données réelles
    return render(request, 'vetements/catalogue.html', {'vetements': vetements})


def vetements_list(request):
    vetements = Vetement.objects.order_by("-created_at")
    return render(request, "vetements/list.html", {
        "vetements": vetements
    })

def vetement_create(request):
    if request.method == "POST":
        form = VetementForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            return redirect("vetements_list")
    else:
        form = VetementForm()

    return render(request, "vetements/form.html", {
        "form": form,
        "title": "Ajouter un vêtement"
    })

def vetement_detail(request, pk):
    vetement = get_object_or_404(Vetement, pk=pk)
    return render(request, "vetements/detail.html", {
        "vetement": vetement
    })

def vetement_update(request, pk):
    vetement = get_object_or_404(Vetement, pk=pk)

    if request.method == "POST":
        form = VetementForm(request.POST, request.FILES, instance=vetement)
        if form.is_valid():
            form.save()
            return redirect("vetement_detail", pk=vetement.pk)
    else:
        form = VetementForm(instance=vetement)

    return render(request, "vetements/form.html", {
        "form": form,
        "title": "Modifier le vêtement"
    })

