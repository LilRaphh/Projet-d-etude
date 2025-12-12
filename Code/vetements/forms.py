from django import forms
from .models import Vetement

class VetementForm(forms.ModelForm):
    class Meta:
        model = Vetement
        fields = ["nom", "type", "marque", "style", "taille", "photo"]

    def clean_photo(self):
        photo = self.cleaned_data.get("photo")
        if not photo:
            raise forms.ValidationError("La photo est obligatoire.")
        return photo
