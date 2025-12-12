from django.urls import path
from . import views

urlpatterns = [
    path('', views.accueil, name='accueil'),
    path('about/', views.about, name='about'),
    path('catalogue/', views.catalogue, name='catalogue'),
]
