from django.shortcuts import render
from django.db.models import Q
from .models import Pharmacy, ShiftSchedule

def index(request):
    shifts = ShiftSchedule.objects.filter(is_active=True).select_related('pharmacy')
    return render(request, 'pharmacies/index.html', {'shifts': shifts})

def pharmacy_search(request):
    query = request.GET.get('q', '').strip()
    
    shifts = ShiftSchedule.objects.filter(is_active=True).select_related('pharmacy')
    
    if query:
        # البحث في الاسم والهاتف والعنوان
        shifts = shifts.filter(
            Q(pharmacy__name__icontains=query) |
            Q(pharmacy__phone__icontains=query) |
            Q(pharmacy__address_details__icontains=query)
        )
        
    return render(request, 'pharmacies/partials/pharmacy_list.html', {'shifts': shifts})
