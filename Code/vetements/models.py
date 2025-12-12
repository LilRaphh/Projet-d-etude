from django.db import models

class ClothingItem(models.Model):
    api_id = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=255)
    category = models.CharField(max_length=100, blank=True, null=True)
    image_url = models.URLField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    # Champs supplémentaires que tu pourras enrichir :
    color = models.CharField(max_length=50, blank=True, null=True)
    style = models.CharField(max_length=50, blank=True, null=True)
    season = models.CharField(max_length=50, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.name} ({self.category})"


class Vetement(models.Model):

    class TypeVetement(models.TextChoices):
        HAUT = "haut", "Haut"
        BAS = "bas", "Bas"
        PANTALON = "pantalon", "Pantalon"
        SHORT = "short", "Short"
        ROBE = "robe", "Robe"
        VESTE = "veste", "Veste"
        CHAUSSURES = "chaussures", "Chaussures"
        AUTRE = "autre", "Autre"

    class Taille(models.TextChoices):
        XS = "XS", "XS"
        S = "S", "S"
        M = "M", "M"
        L = "L", "L"
        XL = "XL", "XL"
        XXL = "XXL", "XXL"

    nom = models.CharField(max_length=120)
    type = models.CharField(max_length=20, choices=TypeVetement.choices)
    marque = models.CharField(max_length=120)
    style = models.CharField(max_length=120, blank=True, null=True)
    taille = models.CharField(max_length=5, choices=Taille.choices)
    photo = models.ImageField(upload_to="vetements/")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.nom} - {self.marque} ({self.type})"
