from django.shortcuts import render
from django.db.models import Q
from .models import ShiftSchedule

def index(request):
    shifts = ShiftSchedule.objects.filter(is_active=True).select_related('pharmacy')
    return render(request, 'pharmacies/index.html', {'shifts': shifts})

def pharmacy_search(request):
    query = request.GET.get('q', '').strip()
    lat = request.GET.get('lat')
    lng = request.GET.get('lng')
    
    shifts = ShiftSchedule.objects.filter(is_active=True).select_related('pharmacy')
    
    # 1. البحث اليدوي النصي: يقتصر حصرياً على اسم الصيدلية فقط
    if query:
        shifts = shifts.filter(pharmacy__name__icontains=query)
        
    # 2. البحث الجغرافي عبر الـ GPS: يعمل بشكل مستقل ومرن
    elif lat and lng:
        try:
            user_lat = float(lat)
            user_lng = float(lng)
            shifts = sorted(
                shifts, 
                key=lambda s: ((s.pharmacy.latitude or 0) - user_lat)**2 + ((s.pharmacy.longitude or 0) - user_lng)**2
            )
        except ValueError:
            pass

    context = {'shifts': shifts, 'query': query}
    
    # استجابة سريعة لقوائم HTMX
    if request.headers.get('HX-Request'):
        return render(request, 'pharmacies/partials/pharmacy_list.html', context)
        
    return render(request, 'pharmacies/index.html', context)