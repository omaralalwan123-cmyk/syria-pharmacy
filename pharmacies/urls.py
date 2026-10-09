from django.urls import path
from .views import pharmacy_search_view

app_name = 'pharmacies'

urlpatterns = [
    path('', pharmacy_search_view, name='search'),
]