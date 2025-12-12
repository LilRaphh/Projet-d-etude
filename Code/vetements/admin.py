from django.contrib import admin
from .models import ClothingItem

@admin.register(ClothingItem)
class ClothingItemAdmin(admin.ModelAdmin):
    # Colonnes visibles dans la liste admin
    list_display = (
        'name', 'category', 'color', 'style',
        'season', 'price', 'created_at', 'updated_at'
    )
    
    # Champs sur lesquels tu peux chercher
    search_fields = (
        'name', 'category', 'color', 'style', 'api_id'
    )
    
    # Filtres latéraux dans l'interface admin
    list_filter = (
        'category', 'color', 'style', 'season'
    )
    
    # Champs non éditables dans le formulaire
    readonly_fields = ('created_at', 'updated_at')
    
    # Ordre par défaut
    ordering = ('-created_at',)

    # Optionnel : regrouper les champs dans des sections
    fieldsets = (
        ("Informations générales", {
            "fields": ("name", "category", "description", "image_url")
        }),
        ("Détails supplémentaires", {
            "fields": ("color", "style", "season", "price")
        }),
        ("Métadonnées", {
            "fields": ("api_id", "created_at", "updated_at")
        }),
    )
