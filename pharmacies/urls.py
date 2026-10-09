from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('search/', views.pharmacy_search, name='pharmacy_search'),
]
