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
