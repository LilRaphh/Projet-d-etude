from django.urls import path
from . import views

urlpatterns = [
    path('', views.accueil, name='accueil'),
    path('about/', views.about, name='about'),
    path('catalogue/', views.catalogue, name='catalogue'),
    path("vetements/", views.vetements_list, name="vetements_list"),
    path("vetements/new/", views.vetement_create, name="vetement_create"),
    path("vetements/<int:pk>/", views.vetement_detail, name="vetement_detail"),
    path("vetements/<int:pk>/edit/", views.vetement_update, name="vetement_update"),
]
