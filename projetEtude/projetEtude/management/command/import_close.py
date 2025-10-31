import requests
from django.core.management.base import BaseCommand
from myapp.models import ClothingItem

class Command(BaseCommand):
    help = "Import clothes from Fake Store API"

    API_URL = "https://api.escuelajs.co/api/v1/products"

    def handle(self, *args, **options):
        self.stdout.write("Fetching data from API …")
        resp = requests.get(self.API_URL)
        resp.raise_for_status()
        items = resp.json()
        count = 0

        for item in items:
            # exemple d’adaptation des champs
            api_id = str(item.get("id"))
            name = item.get("title")
            category = item.get("category", {}).get("name") if item.get("category") else item.get("category")
            image_url = item.get("images")[0] if item.get("images") else None
            description = item.get("description")
            price = item.get("price")

            obj, created = ClothingItem.objects.update_or_create(
                api_id=api_id,
                defaults={
                    "name": name,
                    "category": category,
                    "image_url": image_url,
                    "description": description,
                    "price": price
                }
            )
            if created:
                count += 1

        self.stdout.write(self.style.SUCCESS(f"Imported/updated {count} new items"))
