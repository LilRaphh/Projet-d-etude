from django.core.management.base import BaseCommand
from vetements.models import ClothingItem
from decimal import Decimal

class Command(BaseCommand):
    help = 'Seeds the database with sample clothing items'

    def handle(self, *args, **kwargs):
        self.stdout.write('Seeding data...')
        
        items = [
            {
                'api_id': 'seed_001',
                'name': 'T-Shirt Coton Bio',
                'category': 'Hauts',
                'price': Decimal('25.00'),
                'description': 'T-shirt basique en coton bio, très confortable.',
                'image_url': 'https://placehold.co/400x600?text=T-Shirt',
                'color': 'Blanc',
                'style': 'Casual',
                'season': 'Été'
            },
            {
                'api_id': 'seed_002',
                'name': 'Jean Slim Brut',
                'category': 'Bas',
                'price': Decimal('59.99'),
                'description': 'Jean slim coupe moderne, toile résistante.',
                'image_url': 'https://placehold.co/400x600?text=Jean',
                'color': 'Bleu',
                'style': 'Casual',
                'season': 'Toutes saisons'
            },
            {
                'api_id': 'seed_003',
                'name': 'Veste en Cuir',
                'category': 'Manteaux',
                'price': Decimal('120.50'),
                'description': 'Veste en cuir véritable, style motard.',
                'image_url': 'https://placehold.co/400x600?text=Veste',
                'color': 'Noir',
                'style': 'Rock',
                'season': 'Automne/Hiver'
            },
            {
                'api_id': 'seed_004',
                'name': 'Robe d\'été à fleurs',
                'category': 'Robes',
                'price': Decimal('45.00'),
                'description': 'Robe légère parfaite pour les beaux jours.',
                'image_url': 'https://placehold.co/400x600?text=Robe',
                'color': 'Rouge',
                'style': 'Bohème',
                'season': 'Été'
            },
             {
                'api_id': 'seed_005',
                'name': 'Sneakers Blanches',
                'category': 'Chaussures',
                'price': Decimal('89.00'),
                'description': 'Sneakers urbaines confortables.',
                'image_url': 'https://placehold.co/400x600?text=Sneakers',
                'color': 'Blanc',
                'style': 'Sportswear',
                'season': 'Toutes saisons'
            },
        ]

        for item_data in items:
            obj, created = ClothingItem.objects.update_or_create(
                api_id=item_data['api_id'],
                defaults=item_data
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'Created: {obj.name}'))
            else:
                self.stdout.write(f'Updated: {obj.name}')

        self.stdout.write(self.style.SUCCESS('Data seeding completed successfully.'))
